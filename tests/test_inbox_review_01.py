"""Regressions from code review 01 (`reviews/code-review-01.md`), one group per finding, at the
same seams as the rest of the inbox tests. P and S numbers are the review's own: `test_p1_...`.
"""

from __future__ import annotations

import email
import json
import sqlite3

import pytest

from discord_double import discord_double  # noqa: F401
from inbox_world import triage_all
from inbox_world import DKIM_PASS, NOW, StrictIMAP, enquiry_mail, mailbox_env, raw_mail, trust_servers
from jura_growth import caps, config, db, discord, pause, privacy, runner, suppression
from jura_growth.agents import inbox
from jura_growth.agents.inbox import job, mail, report, store
from jura_growth.agents.outreach import replies, sync
from test_outreach_sync import live_sends
from test_scout_support import at, imap_env, outbox, reply_message, scout_env  # noqa: F401


@pytest.fixture(autouse=True)
def servers_trusted(scout_env, monkeypatch):  # noqa: F811
    trust_servers(monkeypatch)


@pytest.fixture(autouse=True)
def second_mailbox_unset(monkeypatch):
    for name in ("ENQUIRY_IMAP_HOST", "ENQUIRY_IMAP_PORT", "ENQUIRY_IMAP_USER", "ENQUIRY_IMAP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def items(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM inbox_items ORDER BY id")


def lead_status(conn, lead_id):
    return db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,))


def counted(conn) -> int:
    return db.scalar(conn, "SELECT count(*) FROM outreach_replies")


SIGNATURE = "\nJane Tan\nDirector of Operations\nAcme Logistics Pte Ltd\n10 Anson Road\nacme.example\n"


# --- P-1 and P-9: the table itself is `test_inbox_replies.OPT_OUT_TABLE` ----------------


def test_p9_an_opt_out_with_a_signature_suppresses_through_the_check(conn, monkeypatch):
    """P-9: through the intake, with the signature kept on the stored text."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    words = "Please stop emailing me." + SIGNATURE
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body=words)])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"
    assert "Director of Operations" in items(conn)[0]["text"]


# --- P-2: a lead's domain doesn't skip the noise rule -------------------------------------


def _bulk(lead):
    domain = lead["domain"]
    return [
        raw_mail(f"News <news@{domain}>", when="2026-10-26T11:00:00+08:00", body="Click here to unsubscribe",
                 subject="Our newsletter", List_Id="<news.x>", List_Unsubscribe="<https://x/u>"),
        raw_mail(f"Billing <noreply@{domain}>", when="2026-10-26T11:01:00+08:00", body="Your invoice is ready."),
        raw_mail(f"Delivery <mailer-daemon@{domain}>", when="2026-10-26T11:02:00+08:00", body="Delivery failed."),
    ]


def test_p2_bulk_mail_from_a_leads_domain_is_noise_at_intake(conn, monkeypatch):
    """P-2: a newsletter can't unsubscribe a lead, and a no-reply notice can't mark one replied."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, _bulk(lead))
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert [i["state"] for i in items(conn)] == [store.NOISE] * 3
    assert counted(conn) == 0
    assert lead_status(conn, lead["lead_id"]) == "contacted"
    assert suppression.is_suppressed(conn, f"news@{lead['domain']}") is None


def test_p2_the_1645_check_shares_the_rule(conn, monkeypatch):
    """P-2: one rule, so the 16:45 check can't drift from it."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    imap_env(monkeypatch, _bulk(lead))
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    assert "0 replies detected" in sync.run(conn)

    assert lead_status(conn, lead["lead_id"]) == "contacted"
    assert suppression.is_suppressed(conn, f"news@{lead['domain']}") is None


def test_p2_the_address_we_emailed_is_still_their_reply_whatever_its_headers(conn, monkeypatch):
    """P-2, R3: the rule is for a domain match. A contact can't be hidden by a header."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Tell me more.",
                                       List_Unsubscribe="<https://x/u>")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert items(conn)[0]["lead_id"] == lead["lead_id"]
    assert lead_status(conn, lead["lead_id"]) == "replied"


# --- P-3: outreach mail keeps no Message-ID, so the domain match covers it -----------------


def test_p3_a_colleague_answering_outreach_is_covered_by_the_domain_with_no_kept_id(conn, monkeypatch):
    """P-3: nothing writes `inbox_outgoing` for outreach, and F2 still holds for its colleagues."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    assert db.scalar(conn, "SELECT count(*) FROM inbox_outgoing") == 0
    mailbox_env(monkeypatch, [raw_mail(f"Jane <jane@{lead['domain']}>", when="2026-10-26T11:00:00+08:00", body="Tell me more.",
                                       In_Reply_To="<whatever-resend-gave-it@amazonses.example>")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert lead_status(conn, lead["lead_id"]) == "replied"


def test_p3_someone_elsewhere_answering_outreach_is_still_reported(conn, monkeypatch):
    """P-3, the limit stated: not matched to the lead, and not lost either."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail("Helper <helper@agency.example>", when="2026-10-26T11:00:00+08:00", body="Answering for them.",
                                       In_Reply_To="<whatever-resend-gave-it@amazonses.example>")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEW and item["lead_id"] is None
    assert lead_status(conn, lead["lead_id"]) == "contacted"


def test_p3_the_gap_is_stated_where_a_reader_finds_the_table():
    """P-3: a table with no writer yet says so, and says what covers outreach meanwhile."""
    doc = store.remember_outgoing.__doc__
    assert "ticket 03" in doc and "domain" in doc


# --- P-4: nothing is silently swallowed today -----------------------------------------------


def test_p4_the_digest_counts_noise_including_junk(conn, monkeypatch):
    """P-4: the list arrives with ticket 04's section. Until then a cold reply in Junk still counts."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("News <news@vendor.example>", List_Id="<x>")],
                junk=[raw_mail("Ali <ali@gmail.com>", subject="Are you real?")])

    mail.intake(conn)

    part = inbox.digest(conn, "2026-10-26")
    assert part["figures"]["inbox_noise"] == 2
    assert [r["sender_domain"] for r in store.noise_since(conn, "2026-10-26")] == ["vendor.example", "gmail.com"]


# --- P-5: a precheck never raises, so it can't auto-pause the mail --------------------------


def _locked(*args, **kwargs):
    raise sqlite3.OperationalError("database is locked")


def test_p5_a_locked_database_in_the_intake_doesnt_fail_the_run(conn, monkeypatch):
    """P-5: the row was never written, so the next check tries again."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])
    monkeypatch.setattr(store, "record", _locked)

    outcomes = [runner.run("inbox-check") for _ in range(4)]

    assert [o.status for o in outcomes] == ["ok"] * 4
    assert pause.is_paused(conn, "inbox") is None
    assert db.scalar(conn, "SELECT count(*) FROM runs WHERE job = 'inbox-check'") == 0


def test_p5_failures_spread_across_good_checks_never_add_up_to_a_pause(conn, monkeypatch):
    """P-5: a good check leaves no run row, so anything that failed would count as "in a row"."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [])
    real = report.report_due

    for _ in range(4):
        monkeypatch.setattr(report, "report_due", lambda conn: 1 / 0)
        assert runner.run("inbox-check").status == "ok"
        monkeypatch.setattr(report, "report_due", real)
        for _ in range(3):
            assert runner.run("inbox-check").status == "ok"

    assert pause.is_paused(conn, "inbox") is None


@pytest.mark.parametrize("step", ["intake", "report"])
def test_p5_a_real_bug_is_still_seen_once_a_day(conn, monkeypatch, step):
    """P-5: nothing raises, and after two hours of it he hears once, with a health line."""
    mailbox_env(monkeypatch, [])
    if step == "intake":
        monkeypatch.setattr(mail, "intake", lambda conn: 1 / 0)
    else:
        monkeypatch.setattr(report, "report_due", lambda conn: 1 / 0)

    for moment in ("2026-10-26T09:00:00+08:00", "2026-10-26T11:00:00+08:00", "2026-10-26T11:15:00+08:00"):
        at(monkeypatch, moment)
        job.precheck(conn)

    [alert] = outbox("alerts")
    assert "ZeroDivisionError" in alert["content"]
    assert inbox.health(conn)


def test_p5_the_guard_holds_when_even_the_log_is_locked(conn, monkeypatch):
    """P-5: the failure path writes to the same database that just failed."""
    at(monkeypatch, NOW)
    monkeypatch.setattr(mail, "intake", _locked)
    monkeypatch.setattr(store, "set_state", _locked)
    monkeypatch.setattr(store, "clear_state", _locked)

    assert isinstance(job.precheck(conn), str)


def test_p5_a_mailbox_that_hits_a_bug_doesnt_stop_the_other(conn, monkeypatch):
    """P-5: per mailbox, not only per check."""
    at(monkeypatch, NOW)
    second = StrictIMAP([enquiry_mail()])
    fake = mailbox_env(monkeypatch, [raw_mail()], second=second)
    fake.fail_at["search"] = ValueError("a bug")

    found = mail.intake(conn)

    assert found.failed == 1
    assert [i["source"] for i in items(conn)] == ["enquiry"]


# --- P-6: two checks counting one reply ------------------------------------------------------


def test_p6_a_reply_counted_between_the_look_and_the_write_is_not_an_error(conn, monkeypatch):
    """P-6: both jobs run at 16:45. The 16:45 check doesn't fail, or post, or count it twice."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    message = reply_message(lead["email"], when="2026-10-26T16:40:00+08:00", body="Tell me more.")
    imap_env(monkeypatch, [message])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    key = replies.message_key(email.message_from_bytes(message), lead["email"],
                              replies.received_at(email.message_from_bytes(message)))
    contact = replies.sent_contacts(conn).match(lead["email"], email.message_from_bytes(message))
    assert replies.apply_reply(conn, contact, lead["email"], replies.received_at(email.message_from_bytes(message)), key, False, post=False)
    monkeypatch.setattr(replies, "counted", lambda conn, key: False)  # it looked just before that write

    assert "0 replies detected" in sync.run(conn)

    assert counted(conn) == 1
    assert [p for p in outbox("outreach-replies") if "**Reply**" in p["content"]] == []


# --- P-7, P-8, P-13: what a mailbox refuses or shifts -----------------------------------------


def test_p7_a_refused_header_fetch_doesnt_move_the_stamp(conn, monkeypatch):
    """P-7: B5 rule 3, the stamp moves only for a check that finished."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail()])
    fake.refuse_headers = True

    found = mail.intake(conn)

    assert found.failed == 1
    assert store.get_state(conn, "mail.last_success.levi") is None

    fake.refuse_headers = False
    mail.intake(conn)
    assert len(items(conn)) == 1 and store.get_state(conn, "mail.last_success.levi")


def test_p7_a_refused_header_fetch_is_a_failed_16_45_check_not_a_quiet_one(conn, monkeypatch):
    """P-7: `sync.run` says the reply check failed, as for any other refusal."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    fake = mailbox_env(monkeypatch, [raw_mail(f"Info <{seeded[0]['email']}>", when="2026-10-26T15:00:00+08:00")])
    fake.refuse_headers = True
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    assert "reply check failed" in sync.run(conn)


def test_p8_a_refused_body_is_left_for_the_next_check(conn, monkeypatch):
    """P-8: "Please remove me" is honoured, not lost behind one refused fetch."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Please remove me")])
    fake.refuse_bodies = True
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert items(conn) == [] and counted(conn) == 0
    assert store.get_state(conn, "mail.last_success.levi") is None

    fake.refuse_bodies = False
    mail.intake(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"
    assert store.get_state(conn, "mail.last_success.levi")


def test_p8_a_message_that_stays_refused_is_reported_once_it_is_old(conn, monkeypatch):
    """P-8: it can't wait forever, or the person is never seen."""
    at(monkeypatch, "2026-10-29T10:00:00+08:00")
    fake = mailbox_env(monkeypatch, [raw_mail(when="2026-10-26T09:00:00+08:00")])
    fake.refuse_bodies = True

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEEDS_HAND_REPLY and "couldn't be read" in item["note"]


def test_p8_the_1645_check_waits_for_a_refused_body_too(conn, monkeypatch):
    """P-8: the same hole in the older path."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T15:00:00+08:00", body="Please remove me")])
    fake.refuse_bodies = True
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)
    assert counted(conn) == 0

    fake.refuse_bodies = False
    sync.run(conn)
    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"


def test_p13_a_body_that_isnt_this_messages_is_left_for_the_next_check(conn, monkeypatch):
    """P-13: the numbers shifted, so one person's words can't appear under another's name."""
    at(monkeypatch, NOW)
    theirs = raw_mail("Ali <ali@shop.example>", body="Ali's own words here")
    fake = mailbox_env(monkeypatch, [theirs])
    fake.bodies_instead[1] = raw_mail("Priya <priya@clinic.example>", body="Priya's private words")

    mail.intake(conn)

    assert items(conn) == []
    assert store.get_state(conn, "mail.last_success.levi") is None

    fake.bodies_instead.clear()
    mail.intake(conn)
    assert items(conn)[0]["text"] == "Ali's own words here"


def test_p13_an_opt_out_in_someone_elses_body_suppresses_nobody_at_16_45(conn, monkeypatch):
    """P-13: the wrong address would be suppressed for good."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T15:00:00+08:00", body="Tell me more.")])
    fake.bodies_instead[1] = raw_mail("Other <other@x.example>", when="2026-10-26T15:00:00+08:00", body="Please remove me")
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)

    assert suppression.is_suppressed(conn, lead["email"]) is None


# --- P-10, P-11: one rule, about a person's own words ------------------------------------------


@pytest.mark.parametrize("path", ["intake", "1645"])
def test_p10_a_subject_jura_wrote_isnt_their_words(conn, monkeypatch, path):
    """P-10: an outreach subject the rule matches would suppress everyone who answered it."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    conn.execute("UPDATE outreach_messages SET subject = 'Stop emailing invoices by hand' WHERE lead_id = ?", (lead["lead_id"],))
    message = raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", subject="Re: Stop emailing invoices by hand",
                       body="Tell me more, please, about how this works for a team of twenty.")
    mailbox_env(monkeypatch, [message])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    mail.intake(conn) if path == "intake" else sync.run(conn)

    assert suppression.is_suppressed(conn, lead["email"]) is None
    assert lead_status(conn, lead["lead_id"]) == "replied"


def test_p10_their_own_opt_out_under_that_subject_still_counts(conn, monkeypatch):
    """P-10: only the subject is set aside."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    conn.execute("UPDATE outreach_messages SET subject = 'Stop emailing invoices by hand' WHERE lead_id = ?", (lead["lead_id"],))
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00",
                                       subject="Re: Stop emailing invoices by hand", body="Please remove me")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"


@pytest.mark.parametrize("path", ["intake", "1645"])
def test_p11_an_encoded_subject_reads_the_same_in_both_checks(conn, monkeypatch, path):
    """P-11: `=?utf-8?q?please_stop?=` is "please stop"."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    raw = (
        f"From: Info <{lead['email']}>\nSubject: =?utf-8?q?please_stop?=\nDate: Mon, 26 Oct 2026 15:00:00 +0800\n"
        "Message-ID: <encoded@acme.example>\n\n" + " ".join(["word"] * 30) + "\n"
    ).encode()
    mailbox_env(monkeypatch, [raw])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    mail.intake(conn) if path == "intake" else sync.run(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"


# --- P-12: a setting it can't read isn't a quiet day ------------------------------------------


def test_p12_a_keychain_value_it_cant_read_alerts_instead_of_reading_as_quiet(conn, monkeypatch):
    """P-12: `is_set` never asks the Keychain, so a missing entry looked like nothing to do."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])
    monkeypatch.setenv("OUTREACH_IMAP_PASSWORD", "keychain:jura-growth-missing")
    monkeypatch.setattr(config, "_keychain", lambda service: None)

    found = mail.intake(conn)
    mail.intake(conn)

    assert found.failed == 1
    [alert] = outbox("alerts")
    assert "levi" in alert["content"] and "jura-growth-missing" not in alert["content"]
    assert inbox.health(conn)


def test_p12_no_settings_at_all_is_still_quiet(conn, monkeypatch):
    """P-12: not set up isn't a fault. It is a setup gap."""
    at(monkeypatch, NOW)

    assert mail.intake(conn).failed == 0
    assert outbox("alerts") == []


# --- S-1: only a verdict counts as a signature ---------------------------------------------------


def _signed(value: str) -> bool:
    return mail._signed_by_jura(email.message_from_string(f"Authentication-Results: {value}\n\n"))


@pytest.mark.parametrize(
    "value, signed",
    [
        ("mx.zoho.com; dkim=none; spf=pass smtp.mailfrom=dkim=pass.header.d=jurasolutions.sg@evil.test", False),
        ("mx.zoho.com; dkim=fail (dkim=pass header.d=jurasolutions.sg) header.d=jurasolutions.sg; spf=fail", False),
        ("mx.zoho.com; dkim=pass header.d=evil.test; dkim=fail header.d=jurasolutions.sg", False),
        ('mx.zoho.com; spf=pass smtp.mailfrom="a;dkim=pass header.d=jurasolutions.sg"', False),
        ("mx.zoho.com; dkim=pass header.d=jurasolutions.sg.evil.test", False),
        ("mx.zoho.com; dkim=pass header.d=notjurasolutions.sg", False),
        ("dkim=pass header.d=jurasolutions.sg", False),  # no server named: not a verdict
        (DKIM_PASS, True),
        ("mx.zoho.com; dkim=pass (2048-bit key) header.d=jurasolutions.sg header.s=resend", True),
        ("mx.zoho.com; dkim=pass header.i=@jurasolutions.sg", True),
        ("mx.zoho.com; dkim=pass header.d=send.jurasolutions.sg", True),
        ("mx.zoho.com; spf=pass; dkim=pass header.d=evil.test; dkim=pass header.d=jurasolutions.sg", True),
    ],
)
def test_s1_only_a_dkim_verdict_clause_counts(value, signed):
    """S-1: strip comments and quotes, split on `;`, and require a clause that starts `dkim=pass`."""
    assert _signed(value) is signed


def test_s1_the_forged_enquiry_keeps_its_warning(conn, monkeypatch, discord_double):  # noqa: F811
    """S-1: end to end, the report the Security reviewer printed."""
    at(monkeypatch, NOW)
    forged = "mx.zoho.com; dkim=none; spf=pass smtp.mailfrom=dkim=pass.header.d=jurasolutions.sg@evil.test"
    mailbox_env(monkeypatch, [enquiry_mail(visitor="attacker@evil.test", authentication=forged)])

    mail.intake(conn)
    triage_all(conn)
    report.report_due(conn)

    [post] = discord_double.contents("mission-control")
    assert "Website enquiry" not in post and "isn't signed by Jura" in post


# --- S-2: no masked link survives, however it is nested --------------------------------------------


@pytest.mark.parametrize(
    "written",
    [
        "[[x](http://a.test)](http://b.test)",
        "[[Approve I-0007]](https://evil.test/a)",
        "[a]( https://evil.test )",
        "[a](<https://evil.test>)",
        "[[[a](http://a.test)](http://b.test)](http://c.test)",
    ],
)
def test_s2_no_masked_link_survives_the_quote(written):
    """S-2: nothing that reads `](` is left, and no scheme in a link target is left clickable."""
    shown = report.quoted(written)
    assert "](" not in shown
    assert "://" not in shown


def test_s2_a_spoiler_pair_never_survives():
    """S-2: `|||hide|||` kept one."""
    assert "||" not in report.quoted("|||hide|||")
    assert "||" not in report.quoted("||||")


def test_s2_ordinary_brackets_and_links_are_left_alone():
    """S-2: it neutralises the syntax, and a bare address stays as they wrote it."""
    assert report.quoted("See [1] and (2) at https://clinic.example/a") == "> See [1] and (2) at https://clinic.example/a"


# --- S-3: their words can't blank the frame around them ---------------------------------------------


def test_s3_a_subject_cant_blank_the_senders_domain(conn, monkeypatch, discord_double):  # noqa: F811
    """S-3: the frame says who it was, whatever the subject says."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("A <a@evil.example>", subject="evil.example", body="Hello there")])

    mail.intake(conn)
    triage_all(conn)
    report.report_due(conn)

    [post] = discord_double.contents("mission-control")
    assert post.startswith("**I-0001 · Email** · evil.example,")


def test_s3_their_words_cant_blank_a_warning_or_an_alert(conn, monkeypatch, discord_double):  # noqa: F811
    """S-3: the unsigned warning, and an alert later in the same process."""
    from inbox_world import DKIM_FAIL

    at(monkeypatch, NOW)
    warning = "isn't signed by Jura"
    fake = mailbox_env(monkeypatch, [enquiry_mail(visitor="a@evil.example", authentication=DKIM_FAIL, message=warning)])
    mail.intake(conn)
    triage_all(conn)
    report.report_due(conn)
    fake.fail_at["login"] = replies.imaplib.IMAP4.error("refused")
    mail.intake(conn)

    [post] = discord_double.contents("mission-control")
    assert f"but it {warning}" in post
    assert "refused the login" in discord_double.contents("alerts")[0]


def test_s3_a_named_address_in_their_text_teaches_the_frame_nothing(conn, monkeypatch, discord_double):  # noqa: F811
    """S-3: `next.email@x` written in a quote can't mask "Next" and "Email" in the frame around it."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="Write to next.email@evil.example please")])

    mail.intake(conn)
    triage_all(conn)
    report.report_due(conn)

    [post] = discord_double.contents("mission-control")
    assert post.startswith("**I-0001 · Email**") and "\nNo reply needed" in post
    assert "n***@evil.example" in post


def test_s3_the_conversation_class_learns_nothing_and_widens_nothing():
    """S-3: at the seam, plain text around it is judged as if the quote weren't there."""
    quote = "next.email@evil.example"
    assert privacy.for_discord(f"Next: x\n> {quote}", conversation=[quote]) == "Next: x\n> n***@evil.example"


# --- S-4: forging a colleague doesn't change a lead --------------------------------------------------


def _colleague(lead, authentication=None, **kwargs):
    headers = {"Authentication_Results": authentication} if authentication else {}
    return raw_mail(f"Nobody <nobody-real@{lead['domain']}>", when="2026-10-26T11:00:00+08:00", subject="stop", body="Hello",
                    **headers, **kwargs)


@pytest.mark.parametrize(
    "verdict",
    [
        "mx.example.test; dmarc=fail header.from=x",
        "mx.example.test; dkim=fail; spf=fail smtp.mailfrom=x@evil.test",
        # R-4: a pass, but only for someone else's domain.
        "mx.example.test; spf=pass smtp.mailfrom=evil.test; dkim=pass header.d=evil.test; dmarc=none",
        "mx.example.test; dkim=pass header.d=evil.test",
        "mx.example.test; spf=pass smtp.mailfrom=x@evil.test",
    ],
)
@pytest.mark.parametrize("path", ["intake", "1645"])
def test_s4_a_failed_verdict_on_a_domain_match_changes_nothing_and_is_still_reported(conn, monkeypatch, verdict, path):
    """S-4: the forged address isn't suppressed and the lead stays as it was."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [_colleague(lead, verdict)])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn) if path == "intake" else sync.run(conn)

    assert lead_status(conn, lead["lead_id"]) == "contacted"
    assert suppression.is_suppressed(conn, f"nobody-real@{lead['domain']}") is None
    if path == "intake":
        [item] = items(conn)
        assert item["state"] == store.NEW and item["lead_id"] is None


@pytest.mark.parametrize(
    "verdict",
    [
        None,  # no verdict at all: N-2, whether the real server adds one is a UAT check
        "mx.example.test; dkim=none; spf=none",  # a small company with neither set up
        "mx.example.test; dmarc=pass header.from=x",
        "mx.example.test; spf=fail; dkim=pass header.d={domain}",
        "mx.example.test; spf=pass smtp.mailfrom=jane@{domain}; dmarc=none",  # R-4: an aligned pass
        "mx.example.test; dkim=pass header.d=mail.{domain}; dkim=pass header.d=evil.test",
    ],
)
def test_s4_without_a_failed_verdict_a_colleague_still_counts(conn, monkeypatch, verdict):
    """S-4: F2 must hold on a domain with no signing set up, because a chased person can't be undone."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [_colleague(lead, verdict.format(domain=lead["domain"]) if verdict else None)])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert items(conn)[0]["lead_id"] == lead["lead_id"]


def test_s4_the_address_we_emailed_is_not_judged_by_its_verdict(conn, monkeypatch):
    """S-4: forging an emailed address always worked, and honouring it is the safe direction."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Please remove me",
                                       Authentication_Results="mx.example.test; dmarc=fail")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"


# --- T-1: shared helpers --------------------------------------------------------------------------------


def test_t1_mentions_are_defused_by_one_rule():
    """T-1: remote, the run update and the report share `discord.defuse_mentions`."""
    for text in ("@everyone", "@here", "<@111>", "<@&222>", "<#333>"):
        assert text not in discord.defuse_mentions(text)
    assert discord.defuse_mentions("mail me at a@b.test") == "mail me at a@b.test"


@pytest.mark.parametrize("configured, read", [(None, 20), (5, 20), (45, 45)])
def test_t1_a_floor_is_shared(configured, read):
    """T-1: `caps.at_least` pairs with `caps.effective`."""
    assert caps.at_least(20, configured) == read


# --- nits worth pinning ---------------------------------------------------------------------------------


def test_w6_with_inbox_paused_the_1645_check_posts_and_cancels_a_queued_follow_up(conn, monkeypatch):
    """W6, the review's test gap: the post itself, and a queued follow-up cancelled."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    columns = [r["name"] for r in db.rows(conn, "PRAGMA table_info(outreach_messages)") if r["name"] != "id"]
    chosen = {"kind": "'follow_up'", "status": "'queued'", "sent_at": "NULL", "resend_id": "NULL"}
    queued = conn.execute(
        f"INSERT INTO outreach_messages ({', '.join(columns)}) SELECT {', '.join(chosen.get(c, c) for c in columns)} "
        "FROM outreach_messages WHERE lead_id = ? LIMIT 1", (lead["lead_id"],),
    ).lastrowid
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T15:00:00+08:00", body="Tell me more.")])
    pause.pause(conn, "inbox", "testing", notify=False)
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    assert runner.run("inbox-check").status == "skipped"
    sync.run(conn)

    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (queued,)) == "cancelled"
    assert [p for p in outbox("outreach-replies") if "**Reply**" in p["content"]]


def test_the_old_mail_wording_follows_the_configured_hours(conn, monkeypatch):
    """The review's nit: `old_after_hours` can be lowered, and the words then have to agree."""
    at(monkeypatch, NOW)
    monkeypatch.setattr(config, "agent_config", lambda agent: {"old_after_hours": 24} if agent == "inbox" else {})
    mailbox_env(monkeypatch, [raw_mail(when="2026-10-24T09:00:00+08:00")])

    mail.intake(conn)

    assert "older than 24 hours" in items(conn)[0]["note"]
    assert json.loads(items(conn)[0]["thread_json"])["reply_to"]


# --- R-5: a sender's own Authentication-Results counts for nothing ---------------------------


def test_r5_with_no_trusted_server_a_senders_own_pass_isnt_a_signature(conn, monkeypatch):
    """R-5: as shipped, before UAT names the server. A forged enquiry stays a stranger."""
    at(monkeypatch, NOW)
    trust_servers(monkeypatch, "nobody-yet.test")
    mailbox_env(monkeypatch, [enquiry_mail(visitor="attacker@evil.test", authentication=DKIM_PASS)])

    mail.intake(conn)

    [item] = items(conn)
    assert item["source"] == "email" and "isn't signed" in item["note"]


def test_r5_only_a_header_naming_a_trusted_server_counts_however_far_down(conn, monkeypatch):
    """R-5: the server's own header wins, and a sender's above it is skipped."""
    trust_servers(monkeypatch, "mx.real.test")
    raw = (
        "Authentication-Results: mx.forged.test; dkim=pass header.d=jurasolutions.sg\n"
        "Authentication-Results: mx.real.test; dkim=fail header.d=jurasolutions.sg\n\n"
    )
    assert not mail._signed_by_jura(email.message_from_string(raw))
    raw = "Authentication-Results: MX.Real.Test; dkim=pass header.d=jurasolutions.sg\n\n"
    assert mail._signed_by_jura(email.message_from_string(raw))


def test_r5_an_only_arc_header_from_the_server_is_no_verdict(monkeypatch):
    """R-5: the reviewer's probe: the sender's header, and only `ARC-Authentication-Results` from the server."""
    trust_servers(monkeypatch, "mx.real.test")
    raw = (
        "ARC-Authentication-Results: i=1; mx.real.test; dkim=fail\n"
        "Authentication-Results: mx.forged.test; dkim=pass header.d=jurasolutions.sg\n\n"
    )
    assert not mail._signed_by_jura(email.message_from_string(raw))


def test_r5_a_senders_own_failure_blocks_nobody_either(conn, monkeypatch):
    """R-5: no verdict both ways, so a real colleague can't be stopped by a header they didn't write."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    trust_servers(monkeypatch, "mx.real.test")
    mailbox_env(monkeypatch, [_colleague(lead, "mx.forged.test; dmarc=fail")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert items(conn)[0]["lead_id"] == lead["lead_id"]


def test_r5_the_shipped_config_trusts_no_server_until_uat_names_one(monkeypatch):
    """R-5: a guess here would be trusted, so it ships empty."""
    monkeypatch.undo()
    config.reset_caches()
    assert config.agent_config("inbox")["auth_servers"] == []
    assert replies._auth_servers() == frozenset()


def test_r5_the_setting_is_read_from_config_in_any_case(monkeypatch):
    """R-5: an id is compared in lower case, as `verdicts` reads the header."""
    monkeypatch.undo()
    monkeypatch.setattr(config, "agent_config", lambda agent: {"auth_servers": ["MX.Real.Test"]} if agent == "inbox" else {})
    assert replies._auth_servers() == frozenset({"mx.real.test"})
