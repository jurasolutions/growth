"""The mail intake: real parsing from raw bytes against a strict IMAP double (test strategy,
"mail" seam). Nothing touches a real mailbox.

Ids cite the PRD's criteria as `IW-W1`, the functional review's blockers as `IW-F1` and its "should
fix" list as `IW-FS9` (the PRD has its own S1 to S7), the technical review's as `IW-B5` and `IW-N5`,
and the adversarial table as `IW-A7`.
"""

from __future__ import annotations

import imaplib
import json

import pytest

from inbox_world import (
    DKIM_FAIL,
    DKIM_PASS,
    NOW,
    REFUSED_LOGIN,
    Forbidden,
    StrictIMAP,
    enquiry_mail,
    mailbox_env,
    raw_mail,
)
from jura_growth import config, db, pause, runner, suppression
from jura_growth.agents.inbox import mail, store
from jura_growth.agents.outreach import replies, sync
from test_outreach_sync import live_sends
from test_scout_support import at, outbox, scout_env  # noqa: F401


@pytest.fixture(autouse=True)
def second_mailbox_unset(monkeypatch):
    for name in ("ENQUIRY_IMAP_HOST", "ENQUIRY_IMAP_PORT", "ENQUIRY_IMAP_USER", "ENQUIRY_IMAP_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def items(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM inbox_items ORDER BY id")


def thread_of(item: dict) -> dict:
    return json.loads(item["thread_json"])


def lead_status(conn, lead_id):
    return db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,))


def replies_counted(conn) -> int:
    return db.scalar(conn, "SELECT count(*) FROM outreach_replies")


# --- W1: read-only, every 15 minutes in its window ------------------------------


def test_iw_w1_the_mailbox_only_ever_sees_examine_and_peek(conn, monkeypatch):
    """IW-W1: `EXAMINE`, `BODY.PEEK`, nothing marked read, moved or deleted. The double fails the
    test on anything else, so this holds for every other test in this file too."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(), raw_mail("Ali <ali@shop.example>", body="Hello there")])

    mail.intake(conn)

    assert len(items(conn)) == 2
    assert fake.selected and all(readonly for _, readonly in fake.selected)
    assert fake.fetch_specs and all("BODY.PEEK" in spec for spec in fake.fetch_specs)
    assert set(fake.verbs) <= {"login", "list", "select", "search", "fetch"}
    assert fake.logged_out


def test_iw_w1_the_double_refuses_anything_that_would_change_the_mailbox():
    """IW-W1: the proof above is only as good as this."""
    fake = StrictIMAP()
    with pytest.raises(Forbidden):
        fake.select("INBOX")
    with pytest.raises(Forbidden):
        fake.fetch("1", "(BODY[])")
    for verb in ("store", "copy", "move", "expunge", "append", "delete"):
        with pytest.raises(Forbidden):
            getattr(fake, verb)


@pytest.mark.parametrize(
    "moment, reads",
    [
        ("2026-10-26T06:59:00+08:00", False),
        ("2026-10-26T07:00:00+08:00", True),
        ("2026-10-26T12:15:00+08:00", True),
        ("2026-10-26T23:45:00+08:00", True),
        ("2026-10-26T23:45:30+08:00", True),
        ("2026-10-27T00:00:00+08:00", False),
        ("2026-10-26T03:00:00+08:00", False),
    ],
)
def test_iw_w1_the_window_is_checked_in_code(monkeypatch, conn, moment, reads):
    """IW-W1, PRD §4: launchd can fire early, so an early run just skips."""
    at(monkeypatch, moment)
    fake = mailbox_env(monkeypatch, [raw_mail(when="2026-10-26T01:00:00+08:00")])

    outcome = runner.run("inbox-check")

    assert outcome.status == "ok"
    assert ("login" in fake.verbs) is reads


def test_iw_w1_the_schedule_is_every_15_minutes_from_0700_to_2345():
    """IW-W1: checked as data, never installed."""
    assert config.settings()["jobs"]["inbox-check"]["schedule"] == {
        "daily_every": {"start": "07:00", "end": "23:45", "minutes": 15}
    }


def test_iw_w1_a_quiet_check_leaves_a_trace_and_no_run_row(conn, monkeypatch):
    """IW-W1, ADR 0001: nothing to triage in this ticket, so it never starts Claude."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])

    outcome = runner.run("inbox-check")

    assert outcome.status == "ok"
    assert db.scalar(conn, "SELECT count(*) FROM runs WHERE job = 'inbox-check'") == 0
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'run.quiet'") == 1
    assert len(items(conn)) == 1


def test_iw_w1_no_mailbox_set_up_is_a_quiet_run(conn, monkeypatch):
    """IW-W1: it can't connect to anything, and that isn't a failure."""
    at(monkeypatch, NOW)

    assert runner.run("inbox-check").status == "ok"
    assert items(conn) == []


# --- W5: a message counted once --------------------------------------------------


def test_iw_w5_running_twice_records_nothing_new(conn, monkeypatch):
    """IW-W5: the second check doesn't even fetch the body again."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail()])

    mail.intake(conn)
    bodies = fake.body_fetches
    mail.intake(conn)

    assert len(items(conn)) == 1
    assert fake.body_fetches == bodies


def test_iw_w5_one_message_in_both_mailboxes_is_one_item(conn, monkeypatch):
    """IW-W5: two mailboxes delivering one enquiry."""
    at(monkeypatch, NOW)
    message = enquiry_mail(message_id="<same@resend.example>")
    second = StrictIMAP([message])
    mailbox_env(monkeypatch, [message], second=second)

    mail.intake(conn)

    assert len(items(conn)) == 1
    assert "login" in second.verbs


def test_iw_w5_two_messages_with_the_same_words_are_two_items(conn, monkeypatch):
    """IW-W5: it dedupes on the Message-ID, not the text."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="Hello?"), raw_mail(body="Hello?")])

    mail.intake(conn)

    assert len(items(conn)) == 2


def test_iw_w5_a_message_with_no_message_id_is_still_counted_once(conn, monkeypatch):
    """IW-W5: the fallback key is stable between checks."""
    at(monkeypatch, NOW)
    raw = b"From: Ali <ali@shop.example>\nSubject: Hi\nDate: Mon, 26 Oct 2026 09:00:00 +0800\n\nHello there\n"
    mailbox_env(monkeypatch, [raw])

    mail.intake(conn)
    mail.intake(conn)

    assert len(items(conn)) == 1


def test_the_conversation_key_groups_one_person_in_one_thread(conn, monkeypatch):
    """F8 builds on it: same person and thread together, anyone or anything else apart."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [
        raw_mail(subject="Invoices", body="How much is it?"),
        raw_mail(subject="Re: Fwd: RE: invoices", body="And for two sites?"),
        raw_mail("Ali <ali@shop.example>", subject="Invoices", body="Hello there"),
        raw_mail(subject="Something else", body="Different matter"),
    ])

    mail.intake(conn)

    first, again, other_person, other_thread = items(conn)
    assert first["conversation"] == again["conversation"]
    assert first["conversation"] != other_person["conversation"]
    assert first["conversation"] != other_thread["conversation"]


# --- W6, F1, F2, S9: a lead's reply --------------------------------------------


def test_iw_w6_a_reply_does_what_replies_py_does_within_the_check(conn, monkeypatch):
    """IW-W6: follow-ups cancelled, lead marked replied, within the 15-minute check."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:02:00+08:00", body="Tell me more.")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert lead_status(conn, lead["lead_id"]) == "replied"
    assert replies_counted(conn) == 1
    [item] = items(conn)
    assert item["lead_id"] == lead["lead_id"] and item["state"] == store.NEW


def test_iw_w6_iw_fs9_the_1645_check_counts_and_posts_nothing_again(conn, monkeypatch):
    """IW-W6, IW-FS9: `jane@acme` writes at 10:02; 16:45 finds nothing to count or post."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    message = raw_mail(f"Jane <jane@{lead['domain']}>", when="2026-10-26T11:02:00+08:00", body="Tell me more.")
    mailbox_env(monkeypatch, [message])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")
    mail.intake(conn)
    assert outbox("outreach-replies") == []

    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    summary = sync.run(conn)

    assert "0 replies detected" in summary
    assert replies_counted(conn) == 1
    assert [p for p in outbox("outreach-replies") if "**Reply**" in p["content"]] == []


def test_iw_w6_the_reverse_order_counts_once_and_still_records_the_person(conn, monkeypatch):
    """IW-W6: 16:45 got there first, as with `inbox` paused. Nobody is counted twice, and the
    person is still an item, because that post didn't say what they wrote."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T16:40:00+08:00", body="Tell me more.")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    sync.run(conn)
    assert replies_counted(conn) == 1

    at(monkeypatch, "2026-10-26T17:00:00+08:00")
    mail.intake(conn)

    assert replies_counted(conn) == 1
    [item] = items(conn)
    assert item["state"] == store.NEW and item["reported_at"] is None


def test_iw_w6_a_reply_already_counted_long_ago_isnt_reported_again(conn, monkeypatch):
    """IW-W6, functional edges: rows from before this change aren't reposted."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T16:40:00+08:00", body="Tell me more.")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    sync.run(conn)

    at(monkeypatch, "2026-10-29T09:00:00+08:00")
    mail.intake(conn)

    [item] = items(conn)
    assert item["reported_at"] is not None and item["stale"] == 1
    assert replies_counted(conn) == 1


def test_iw_w6_with_inbox_paused_the_1645_check_does_all_of_it(conn, monkeypatch):
    """IW-W6, S10: a paused inbox can't chase someone who said stop."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T15:00:00+08:00", body="Please remove me")])
    at(monkeypatch, "2026-10-26T15:15:00+08:00")
    pause.pause(conn, "inbox", "testing", notify=False)

    assert runner.run("inbox-check").status == "skipped"
    assert "login" not in fake.verbs
    assert replies_counted(conn) == 0

    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    sync.run(conn)
    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"
    assert lead_status(conn, lead["lead_id"]) == "unsubscribed"


def test_iw_f1_an_opt_out_suppresses_and_gets_no_draft(conn, monkeypatch):
    """IW-F1: suppressed, reported naming the rule, never triaged."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Please remove me")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"
    [item] = items(conn)
    assert item["state"] == store.REPORTED
    assert "remove" in item["note"]


def test_iw_f1_a_real_question_goes_on_to_triage(conn, monkeypatch):
    """IW-F1: not suppressed, follow-ups cancelled, and left for a draft."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00",
                                       body="How do we stop retyping invoices?")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert suppression.is_suppressed(conn, lead["email"]) is None
    assert lead_status(conn, lead["lead_id"]) == "replied"
    assert items(conn)[0]["state"] == store.NEW


def test_iw_f2_a_colleague_counts_as_the_lead(conn, monkeypatch):
    """IW-F2: a sender on a lead's domain is that lead's reply, so the item carries the lead."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Jane Tan <jane.tan@{lead['domain']}>", when="2026-10-26T11:00:00+08:00", body="Tell me more.")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    [item] = items(conn)
    assert item["lead_id"] == lead["lead_id"]
    assert lead_status(conn, lead["lead_id"]) == "replied"


def test_iw_f2_mail_naming_a_message_jura_sent_is_that_leads_reply(conn, monkeypatch):
    """IW-F2: from any address, when `In-Reply-To` or `References` names a message Jura sent."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    store.remember_outgoing(conn, "<sent-1@jurasolutions.sg>", lead_id=lead["lead_id"])
    mailbox_env(monkeypatch, [raw_mail("Consultant <helper@agency.example>", when="2026-10-26T11:00:00+08:00", body="Answering for them.",
                                       In_Reply_To="<sent-1@jurasolutions.sg>")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert items(conn)[0]["lead_id"] == lead["lead_id"]
    assert lead_status(conn, lead["lead_id"]) == "replied"


def test_iw_w6_an_auto_reply_from_a_contact_is_not_their_reply(conn, monkeypatch):
    """IW-W6, IW-R2: as `replies.py` has it, an out-of-office cancels nothing, and it's noise."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="I am away.",
                                       subject="Out of office", Auto_Submitted="auto-replied")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert replies_counted(conn) == 0
    assert lead_status(conn, lead["lead_id"]) == "contacted"
    assert items(conn)[0]["state"] == store.NOISE


# --- W7: how far back a check looks ------------------------------------------------


def since_of(fake: StrictIMAP) -> str:
    return fake.searches[0][1]


def test_iw_w7_the_first_run_looks_back_seven_days(conn, monkeypatch):
    """IW-W7: mail older than `first_run_days` is ignored."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(when="2026-10-10T09:00:00+08:00", body="Too old to see"), raw_mail()])

    mail.intake(conn)

    assert since_of(fake) == "19-Oct-2026"
    assert [i["text"] for i in items(conn)] == ["Do you work with clinics?"]


@pytest.mark.parametrize(
    "later, since",
    [
        ("2026-10-26T10:15:00+08:00", "25-Oct-2026"),  # the next slot
        ("2026-10-29T10:00:00+08:00", "25-Oct-2026"),  # off for 3 days: loses nothing
        ("2026-12-09T10:00:00+08:00", "25-Oct-2026"),  # 44 days: still inside the limit
        ("2026-12-25T10:00:00+08:00", "10-Nov-2026"),  # 60 days: 45 days back from today
    ],
)
def test_iw_w7_later_checks_look_back_to_the_last_good_one_less_a_day(conn, monkeypatch, later, since):
    """IW-W7: a Mac that was off loses nothing, and the 45-day limit bounds a long absence."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [])
    mail.intake(conn)
    fake.searches.clear()

    at(monkeypatch, later)
    mail.intake(conn)

    assert since_of(fake) == since


def test_iw_w7_a_failed_check_leaves_the_stamp_where_it_was(conn, monkeypatch):
    """IW-W7, IW-B5: the next good check still looks back past the failure."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [])
    mail.intake(conn)

    at(monkeypatch, "2026-10-29T10:00:00+08:00")
    fake.fail_at["search"] = OSError("network down")
    mail.intake(conn)
    del fake.fail_at["search"]
    fake.searches.clear()

    at(monkeypatch, "2026-10-29T10:15:00+08:00")
    mail.intake(conn)

    assert since_of(fake) == "25-Oct-2026"


# --- W8: website enquiries ---------------------------------------------------------


def test_iw_w8_an_enquiry_is_the_person_in_its_reply_to_with_came_from_kept(conn, monkeypatch):
    """IW-W8: `no_reply@` is taken as the visitor, and the `Came from:` line stays."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail()])

    mail.intake(conn)

    [item] = items(conn)
    assert item["source"] == "enquiry"
    assert item["sender_address"] == "jane.tan@acme.example"
    assert item["sender_domain"] == "acme.example"
    assert item["sender_name"] == "Jane Tan"
    assert "Came from: apps/quote-builder" in item["text"]
    assert "We retype every invoice." in item["text"]
    assert item["state"] == store.NEW
    assert thread_of(item)["reply_to"] == "jane.tan@acme.example"


def test_iw_w8_a_visitors_words_are_never_cut_as_if_they_were_quoted(conn, monkeypatch):
    """IW-W8: an enquiry isn't a reply, so "From:" and ">" in it are what they typed."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail(message="From: our branch office\n> we retype it all")])

    mail.intake(conn)

    assert "From: our branch office\n> we retype it all" in items(conn)[0]["text"]


def test_iw_w8_a_second_mailbox_adds_its_mail(conn, monkeypatch):
    """IW-W8: `ENQUIRY_IMAP_*` set."""
    at(monkeypatch, NOW)
    second = StrictIMAP([enquiry_mail()])
    mailbox_env(monkeypatch, [raw_mail()], second=second)

    mail.intake(conn)

    assert sorted(i["source"] for i in items(conn)) == ["email", "enquiry"]
    assert all(readonly for _, readonly in second.selected)


def test_iw_w8_a_half_configured_second_mailbox_is_a_gap_and_the_first_still_works(conn, monkeypatch):
    """IW-W8: `ENQUIRY_IMAP_HOST` alone."""
    from jura_growth import health

    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])
    monkeypatch.setenv("ENQUIRY_IMAP_HOST", "imap.enquiry.test")

    mail.intake(conn)

    assert len(items(conn)) == 1
    names = [gap.name for gap in health.setup_gaps()]
    assert "ENQUIRY_IMAP_USER" in names and "ENQUIRY_IMAP_PASSWORD" in names and "OUTREACH_IMAP_HOST" not in names


def test_iw_w8_a_mailbox_that_fails_doesnt_stop_the_other(conn, monkeypatch):
    """IW-W8, IW-B5: each mailbox stands alone."""
    at(monkeypatch, NOW)
    second = StrictIMAP([enquiry_mail()])
    fake = mailbox_env(monkeypatch, [raw_mail()], second=second)
    fake.fail_at["login"] = REFUSED_LOGIN

    mail.intake(conn)

    assert [i["source"] for i in items(conn)] == ["enquiry"]


def test_the_setup_gaps_name_the_mailbox_when_it_isnt_set(monkeypatch):
    """Setup gaps are names only (MC §4.3)."""
    from jura_growth import health

    names = [gap.name for gap in health.setup_gaps()]
    assert "OUTREACH_IMAP_HOST" in names
    assert "ENQUIRY_IMAP_HOST" not in names  # optional, so only half-set is a gap


# --- R2, F3: noise needs evidence in the headers -----------------------------------


@pytest.mark.parametrize(
    "sender, headers",
    [
        ("News <news@vendor.example>", {"List_Id": "<news.vendor.example>"}),
        ("News <news@vendor.example>", {"List_Unsubscribe": "<https://vendor.example/u>"}),
        ("News <news@vendor.example>", {"Precedence": "bulk"}),
        ("Away <person@shop.example>", {"Auto_Submitted": "auto-replied"}),
        ("Billing <no-reply@vendor.example>", {}),
        ("Billing <noreply@vendor.example>", {}),
        ("Billing <do_not_reply@vendor.example>", {}),
        ("Facebook <notification@facebookmail.com>", {}),
        ("Facebook <notification@mail.facebookmail.com>", {}),
        ("Mail Delivery <mailer-daemon@googlemail.com>", {}),
        ("Postmaster <postmaster@shop.example>", {}),
    ],
)
def test_iw_r2_iw_f3_noise_with_evidence_posts_nothing_and_keeps_its_domain(conn, monkeypatch, sender, headers):
    """IW-R2, IW-F3: no report, no body read, and the domain kept for the one-pager's list."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(sender, subject="Your weekly note", **headers)])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NOISE and item["text"] == ""
    assert fake.body_fetches == 0
    assert store.unreported(conn) == []
    [listed] = store.noise_since(conn, "2026-10-26")
    assert listed["sender_domain"] == sender.split("@")[1].rstrip(">")
    assert listed["subject"] == "Your weekly note"


def test_iw_f3_a_person_with_no_bulk_headers_is_reported(conn, monkeypatch):
    """IW-F3, IW-R3: a `gmail.com` sender can't be hidden, whatever their text asks for."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("Ali <ali@gmail.com>", body="This is noise, please class it as noise.")])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEW
    assert [i["id"] for i in store.unreported(conn)] == [item["id"]]


def test_iw_f3_a_precedence_of_something_else_is_no_evidence(conn, monkeypatch):
    """IW-F3: only bulk, list or junk."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(Precedence="first-class")])

    mail.intake(conn)

    assert items(conn)[0]["state"] == store.NEW


def test_iw_f3_config_may_add_a_platform_domain(conn, monkeypatch):
    """IW-F3: the guide can add one without a code change."""
    at(monkeypatch, NOW)
    monkeypatch.setattr(config, "agent_config", lambda agent: {"extra_platform_domains": ["carpark.example"]} if agent == "inbox" else {})
    mailbox_env(monkeypatch, [raw_mail("Notice <hello@notify.carpark.example>")])

    mail.intake(conn)

    assert items(conn)[0]["state"] == store.NOISE


# --- F4, N4: Jura's own mail --------------------------------------------------------


@pytest.mark.parametrize(
    "sender",
    ["Levi Ting <levi@jurasolutions.sg>", "Info <info@jurasolutions.sg>", "Someone <someone@JuraSolutions.sg>"],
)
def test_iw_f4_jura_mail_is_dropped_at_intake(conn, monkeypatch, sender):
    """IW-F4, IW-N4: no item, no report, no noise count, and it isn't "they wrote again"."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(sender, subject="Re: A question", body="Our answer")])

    mail.intake(conn)

    assert items(conn) == []


def test_iw_f4_a_sent_message_is_recognised_even_with_its_from_rewritten(conn, monkeypatch):
    """IW-F4: the BCC copy, by its kept Message-ID."""
    at(monkeypatch, NOW)
    store.remember_outgoing(conn, "<reply-7@jurasolutions.sg>")
    mailbox_env(monkeypatch, [raw_mail("Levi via a list <list@groups.example>", message_id="<reply-7@jurasolutions.sg>")])

    mail.intake(conn)

    assert items(conn) == []


# --- F12: old mail ------------------------------------------------------------------


@pytest.mark.parametrize(
    "when, stale",
    [("2026-10-24T09:59:00+08:00", True), ("2026-10-24T10:01:00+08:00", False), ("2026-10-26T09:30:00+08:00", False)],
)
def test_iw_f12_mail_older_than_48_hours_gets_no_draft(conn, monkeypatch, when, stale):
    """IW-F12: reported, with no draft, and saying so."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(when=when)])

    mail.intake(conn)

    [item] = items(conn)
    assert bool(item["stale"]) is stale
    assert item["state"] == (store.REPORTED if stale else store.NEW)
    if stale:
        assert "older than 48 hours" in item["note"]
    assert item["reported_at"] is None  # still owed a report


def test_iw_f12_old_mail_from_a_contact_still_stops_their_follow_ups(conn, monkeypatch):
    """IW-F12, IW-W6: too old for a draft is not too old to count."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Tell me more.")])
    at(monkeypatch, "2026-10-29T09:00:00+08:00")

    mail.intake(conn)

    assert lead_status(conn, lead["lead_id"]) == "replied"
    assert items(conn)[0]["stale"] == 1


# --- S11: who a reply goes to --------------------------------------------------------


def test_iw_fs11_a_reply_goes_to_reply_to_when_it_is_set(conn, monkeypatch):
    """IW-FS11."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(Reply_To="Office <office@clinic.example>")])

    mail.intake(conn)

    assert thread_of(items(conn)[0])["reply_to"] == "office@clinic.example"


def test_iw_fs11_otherwise_to_from(conn, monkeypatch):
    """IW-FS11."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()])

    mail.intake(conn)

    assert thread_of(items(conn)[0])["reply_to"] == "priya@clinic.example"


def test_iw_fs11_copied_people_are_counted_and_not_included(conn, monkeypatch):
    """IW-FS11: each would need its own suppression check, so the card names them."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(Cc="A <a@clinic.example>, B <b@clinic.example>, Levi <levi@jurasolutions.sg>")])

    mail.intake(conn)

    thread = thread_of(items(conn)[0])
    assert thread["copied"] == 2
    assert thread["reply_to"] == "priya@clinic.example"


# --- S16: the Junk folder ---------------------------------------------------------------


def test_iw_fs16_junk_is_read_read_only_and_only_ever_lists(conn, monkeypatch):
    """IW-FS16: no draft, no report, no body read: a line with the domain and subject."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [], junk=[raw_mail("Ali <ali@gmail.com>", subject="Are you real?")])

    mail.intake(conn)

    assert ("Junk", True) in fake.selected
    [item] = items(conn)
    assert item["state"] == store.NOISE and item["text"] == ""
    assert fake.body_fetches == 0
    [listed] = store.noise_since(conn, "2026-10-26")
    assert listed["sender_domain"] == "gmail.com" and listed["subject"] == "Are you real?"
    assert "junk" in listed["note"]


def test_iw_fs16_a_contact_in_junk_only_lists_too(conn, monkeypatch):
    """IW-FS16: the rule is the folder's, and the 16:45 check reads INBOX as it always has."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [], junk=[raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Please remove me")])
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert items(conn)[0]["state"] == store.NOISE
    assert replies_counted(conn) == 0


@pytest.mark.parametrize("junk_name", ["Spam", "[Gmail]/Spam", "Junk E-mail"])
def test_iw_fs16_a_special_use_folder_is_found_whatever_it_is_called(conn, monkeypatch, junk_name):
    """IW-FS16: Gmail and Zoho name it differently; the `\\Junk` flag says which it is."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [], junk=[raw_mail(subject="Hello")], junk_name=junk_name)

    mail.intake(conn)

    assert (junk_name, True) in fake.selected
    assert len(items(conn)) == 1


def test_iw_fs16_no_junk_folder_is_fine(conn, monkeypatch):
    """IW-FS16: a mailbox with none still counts as a good check."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail()], junk_name=None)

    mail.intake(conn)

    assert len(items(conn)) == 1
    assert store.get_state(conn, "mail.last_success.levi")


# --- B5 rules 1 to 3 --------------------------------------------------------------------


@pytest.mark.parametrize(
    "verb, error",
    [
        ("login", OSError("no route to host")),
        ("select", imaplib.IMAP4.abort("socket error: EOF")),
        ("search", TimeoutError("timed out")),
        ("fetch", OSError("connection reset")),
    ],
)
def test_iw_b5_a_network_fault_doesnt_fail_the_run(conn, monkeypatch, verb, error):
    """IW-B5 rule 1: three flaps would otherwise pause mail for good."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail()])
    fake.fail_at[verb] = error

    outcomes = [runner.run("inbox-check") for _ in range(4)]

    assert [o.status for o in outcomes] == ["ok"] * 4
    assert pause.is_paused(conn, "inbox") is None
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'inbox.mail_failed'") == 4
    assert outbox("alerts") == []  # not yet: see the next two tests


def test_iw_b5_failing_for_two_hours_alerts_once_a_day(conn, monkeypatch):
    """IW-B5 rule 1: no good check for 2 hours is one alert a day and a health line."""
    from jura_growth.agents import inbox

    fake = mailbox_env(monkeypatch, [])
    fake.fail_at["search"] = OSError("network down")
    for moment in ("2026-10-26T09:00:00+08:00", "2026-10-26T10:45:00+08:00"):
        at(monkeypatch, moment)
        mail.intake(conn)
    assert outbox("alerts") == []

    for moment in ("2026-10-26T11:00:00+08:00", "2026-10-26T11:15:00+08:00"):
        at(monkeypatch, moment)
        mail.intake(conn)
    assert len(outbox("alerts")) == 1
    assert any("mail" in line.lower() for line in inbox.health(conn))

    at(monkeypatch, "2026-10-27T09:00:00+08:00")
    mail.intake(conn)
    assert len(outbox("alerts")) == 1  # the outbox file is per day, so this is the second day's
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'inbox.health'") == 2


def test_iw_b5_a_refused_login_alerts_straight_away_and_never_shows_a_secret(conn, monkeypatch):
    """IW-B5 rule 1: waiting won't fix an auth failure. No host, user or password in the alert."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [])
    fake.fail_at["login"] = REFUSED_LOGIN

    mail.intake(conn)
    mail.intake(conn)

    [alert] = outbox("alerts")
    assert "login" in alert["content"].lower()
    for secret in ("imap.example.test", "levi@jurasolutions.sg", "app-password-not-real"):
        assert secret not in alert["content"]


def test_iw_b5_a_good_check_clears_the_failure(conn, monkeypatch):
    """IW-B5 rule 1: the health line goes, and the two-hour clock starts again."""
    from jura_growth.agents import inbox

    at(monkeypatch, "2026-10-26T09:00:00+08:00")
    fake = mailbox_env(monkeypatch, [])
    fake.fail_at["search"] = OSError("network down")
    mail.intake(conn)
    at(monkeypatch, "2026-10-26T11:00:00+08:00")
    mail.intake(conn)
    assert inbox.health(conn)

    del fake.fail_at["search"]
    at(monkeypatch, "2026-10-26T11:15:00+08:00")
    mail.intake(conn)

    assert inbox.health(conn) == []


def test_iw_b5_no_transaction_is_open_across_the_network(conn, monkeypatch):
    """IW-B5 rule 2: fetch first, then commit per message, so a decision never waits on IMAP."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = mailbox_env(monkeypatch, [
        raw_mail(f"Info <{lead['email']}>", when="2026-10-26T11:00:00+08:00", body="Tell me more."),
        raw_mail(when="2026-10-26T11:01:00+08:00"),
        raw_mail("News <news@vendor.example>", when="2026-10-26T11:02:00+08:00", List_Id="<x>"),
    ], junk=[raw_mail("Ali <ali@gmail.com>", when="2026-10-26T11:03:00+08:00")])
    fake.watch(conn)
    at(monkeypatch, "2026-10-26T11:15:00+08:00")

    mail.intake(conn)

    assert len(items(conn)) == 4


def test_iw_b5_each_message_is_kept_when_a_later_one_fails(conn, monkeypatch):
    """IW-B5 rule 2: commit per message, so what was read before the fault stays."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(), raw_mail(body="Second message here")])
    real_fetch = fake.fetch
    calls = {"n": 0}

    def flaky(numbers, spec):
        if "HEADER.FIELDS" not in spec:
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("connection reset")
        return real_fetch(numbers, spec)

    monkeypatch.setattr(fake, "fetch", flaky)

    mail.intake(conn)

    assert len(items(conn)) == 1


def test_iw_b5_a_body_budget_takes_the_oldest_first_and_the_rest_wait(conn, monkeypatch):
    """IW-B5 rule 3: `INBOX_BODIES_PER_CHECK` bodies, then the next check. The stamp stays."""
    at(monkeypatch, NOW)
    monkeypatch.setattr(config, "agent_config", lambda agent: {"bodies_per_check": 2} if agent == "inbox" else {})
    fake = mailbox_env(monkeypatch, [raw_mail(body=f"Message number {n} here") for n in range(5)])

    mail.intake(conn)

    assert [i["text"] for i in items(conn)] == ["Message number 0 here", "Message number 1 here"]
    assert fake.body_fetches == 2
    assert store.get_state(conn, "mail.last_success.levi") is None

    mail.intake(conn)
    mail.intake(conn)

    assert len(items(conn)) == 5
    assert store.get_state(conn, "mail.last_success.levi")


def test_iw_b5_a_wall_clock_budget_stops_the_check(conn, monkeypatch):
    """IW-B5 rule 3: 120 seconds, and the stamp moves only for a check that finished."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(body=f"Message number {n} here") for n in range(3)])
    ticks = iter(range(0, 100_000, 50))  # every look at the clock is 50 seconds later
    monkeypatch.setattr(mail.time, "monotonic", lambda: float(next(ticks)))

    mail.intake(conn)

    assert 0 < len(items(conn)) < 3
    assert store.get_state(conn, "mail.last_success.levi") is None
    assert fake.logged_out


# --- the adversarial table ---------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "Hello\r\n Bcc: x@evil.test",
        "=?utf-8?b?SGVsbG8NCkJjYzogeEBldmlsLnRlc3Q=?=",  # RFC 2047: "Hello\r\nBcc: x@evil.test"
        "A folded\n subject line",
    ],
)
def test_iw_a7_a_subject_cant_carry_a_header(conn, monkeypatch, subject):
    """IW-A7: raw, encoded and folded line breaks all end as one clean line."""
    at(monkeypatch, NOW)
    raw = (
        f"From: Ali <ali@shop.example>\nSubject: {subject}\nDate: Mon, 26 Oct 2026 09:00:00 +0800\n"
        "Message-ID: <a7@shop.example>\n\nHello there\n"
    ).encode()
    mailbox_env(monkeypatch, [raw])

    mail.intake(conn)

    [item] = items(conn)
    assert not set(item["subject"]) & {"\r", "\n", "\x00"}
    assert json.loads(item["thread_json"])["reply_to"] == "ali@shop.example"


@pytest.mark.parametrize(
    "header, value",
    [
        ("Reply-To", "a@x.test, b@y.test"),
        ("Reply-To", "undisclosed: a@x.test, b@y.test;"),
        ("Reply-To", "not an address"),
        ("Reply-To", "a@@x.test"),
        ("Reply-To", "levi@jurasolutions.sg"),
    ],
)
def test_iw_a8_iw_a9_a_reply_address_that_isnt_one_person_means_a_hand_reply(conn, monkeypatch, header, value):
    """IW-A8, IW-A9: one validated address, or `needs-you` and nothing can be sent."""
    at(monkeypatch, NOW)
    raw = (
        f"From: Ali <ali@shop.example>\n{header}: {value}\nSubject: Hi\nDate: Mon, 26 Oct 2026 09:00:00 +0800\n"
        "Message-ID: <a8@shop.example>\n\nHello there\n"
    ).encode()
    mailbox_env(monkeypatch, [raw])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEEDS_YOU
    assert thread_of(item)["reply_to"] is None
    assert [i["id"] for i in store.unreported(conn)] == [item["id"]]


def test_iw_a8_a_from_with_two_addresses_means_a_hand_reply(conn, monkeypatch):
    """IW-A8: nobody is guessed at, and no reply could go to the second address."""
    at(monkeypatch, NOW)
    raw = (
        b"From: a@x.test, b@y.test\nSubject: Hi\nDate: Mon, 26 Oct 2026 09:00:00 +0800\n"
        b"Message-ID: <two@x.test>\n\nHello there\n"
    )
    mailbox_env(monkeypatch, [raw])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEEDS_YOU and thread_of(item)["reply_to"] is None


def test_iw_a8_a_display_name_cant_borrow_an_address(conn, monkeypatch):
    """IW-A8: `"levi@jurasolutions.sg" <x@evil.test>` is x@evil.test, not Jura's own mail."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail('"levi@jurasolutions.sg" <x@evil.test>')])

    mail.intake(conn)

    [item] = items(conn)
    assert item["sender_domain"] == "evil.test"
    assert thread_of(item)["reply_to"] == "x@evil.test"


def test_iw_a8_thread_headers_are_clean_and_capped(conn, monkeypatch):
    """IW-A8: 500 ids in `References`, and junk among them, can't become outgoing headers."""
    at(monkeypatch, NOW)
    references = " ".join(f"<id{n}@mail.example>" for n in range(500)) + " not-an-id <bad id@x>"
    mailbox_env(monkeypatch, [raw_mail(message_id="<own@mail.example>", In_Reply_To="<parent@mail.example> junk", References=references)])

    mail.intake(conn)

    thread = thread_of(items(conn)[0])
    assert thread["message_id"] == "<own@mail.example>"
    assert thread["in_reply_to"] == "<parent@mail.example>"
    assert len(thread["references"]) == 20 and thread["references"][-1] == "<id499@mail.example>"
    assert all(reference.startswith("<") and " " not in reference for reference in thread["references"])


def test_iw_a9_a_forged_enquiry_is_an_ordinary_stranger(conn, monkeypatch):
    """IW-A9, IW-F3: without Jura's DKIM pass it isn't an enquiry, and it's still reported."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail(visitor="attacker@evil.test", authentication=DKIM_FAIL, came_from="apps/spoofed")])

    mail.intake(conn)

    [item] = items(conn)
    assert item["source"] == "email"
    assert item["sender_domain"] == "evil.test"
    assert item["state"] == store.NEW
    assert item["sender_name"] == ""  # "Jura Solutions" is what it claims, not who it is
    assert "isn't signed" in item["note"]


def test_iw_a9_only_the_receivers_own_authentication_header_counts(conn, monkeypatch):
    """IW-A9: the sender can add a passing header of their own below the receiver's."""
    at(monkeypatch, NOW)
    raw = (
        "Authentication-Results: mx.example.test; dkim=fail header.d=jurasolutions.sg\n"
        f"Authentication-Results: {DKIM_PASS}\n"
        "From: Jura Solutions <no_reply@jurasolutions.sg>\nReply-To: x@evil.test\nSubject: Enquiry from X\n"
        "Date: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <forged@evil.test>\n\nName: X\n"
    ).encode()
    mailbox_env(monkeypatch, [raw])

    mail.intake(conn)

    assert items(conn)[0]["source"] == "email"


def test_iw_a9_dkim_from_another_domain_isnt_jura(conn, monkeypatch):
    """IW-A9: a pass for evil.test says nothing about the form."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail(authentication="mx.example.test; dkim=pass header.d=evil.test")])

    mail.intake(conn)

    assert items(conn)[0]["source"] == "email"


def test_iw_a9_an_enquiry_naming_jura_as_the_person_never_gets_a_draft(conn, monkeypatch):
    """IW-A9: no mail loop, even with a good signature."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [enquiry_mail(visitor="info@jurasolutions.sg")])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEEDS_YOU
    assert thread_of(item)["reply_to"] is None


NO_DATE = b"From: Ali <ali@shop.example>\nSubject: No date\nMessage-ID: <no-date@shop.example>\n\nHello there\n"
NO_FROM = b"Subject: No sender\nDate: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <no-from@shop.example>\n\nHello there\n"
BARE = b"\n\nHello there\n"
BAD_CHARSET = (
    b"From: Ali <ali@shop.example>\nSubject: Hi\nDate: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <cs@shop.example>\n"
    b"Content-Type: text/plain; charset=not-a-charset\n\nHello \xff there\n"
)
BAD_ENCODED_SUBJECT = (
    b"From: =?not-a-charset?b?QWxp?= <ali@shop.example>\nSubject: =?not-a-charset?q?Hi?= \xff\xfe\n"
    b"Date: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <es@shop.example>\n\nHello there\n"
)
HTML_ONLY = (
    b"From: Ali <ali@shop.example>\nSubject: Hi\nDate: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <h@shop.example>\n"
    b"Content-Type: text/html; charset=utf-8\n\n<html><head><style>p {color: red}</style><script>alert('x')</script></head>"
    b"<body><p>Hello &amp; welcome</p></body></html>\n"
)
NESTED = (
    b"From: Ali <ali@shop.example>\nSubject: Fwd\nDate: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <n@shop.example>\n"
    b'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="b1"\n\n--b1\nContent-Type: text/plain\n\nSee attached.\n'
    b"--b1\nContent-Type: message/rfc822\n\nFrom: inner@x.test\nSubject: Inner\n\nInner text must not be read\n--b1--\n"
)
ATTACHED = (
    b"From: Ali <ali@shop.example>\nSubject: Quote\nDate: Mon, 26 Oct 2026 09:00:00 +0800\nMessage-ID: <at@shop.example>\n"
    b'MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="b1"\n\n--b1\nContent-Type: text/plain\n\nSee the file.\n'
    b"--b1\nContent-Type: application/pdf\nContent-Disposition: attachment; filename*=utf-8''quote%E2%80%AE.pdf\n"
    b"Content-Transfer-Encoding: base64\n\nU0VDUkVULUFUVEFDSE1FTlQtQllURVM=\n--b1--\n"
)


@pytest.mark.parametrize("raw", [NO_DATE, NO_FROM, BARE, BAD_CHARSET, BAD_ENCODED_SUBJECT, HTML_ONLY, NESTED, ATTACHED],
                         ids=["no-date", "no-from", "bare", "bad-charset", "bad-encoded-subject", "html-only", "nested", "attached"])
def test_iw_a12_malformed_mail_doesnt_stop_the_batch(conn, monkeypatch, raw):
    """IW-A12: no crash, and the message after it is still read."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw, raw_mail(body="The next message")])

    mail.intake(conn)

    found = items(conn)
    assert len(found) == 2 and found[1]["text"] == "The next message"
    for item in found:
        assert not set(item["text"] + item["subject"] + item["sender_name"]) & {"\x00", "‮"}


def test_iw_a12_no_sender_means_a_hand_reply(conn, monkeypatch):
    """IW-A12: it's still reported, and nothing can be sent."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [NO_FROM])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEEDS_YOU and item["sender_domain"] == ""


def test_iw_a12_no_date_counts_as_new(conn, monkeypatch):
    """IW-A12: it can't be judged too old, so a person isn't denied a draft by a missing header."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [NO_DATE])

    mail.intake(conn)

    [item] = items(conn)
    assert item["state"] == store.NEW and item["stale"] == 0


def test_iw_a12_html_only_mail_reads_as_its_words(conn, monkeypatch):
    """IW-A12: script and style are gone, entities decoded."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [HTML_ONLY])

    mail.intake(conn)

    assert items(conn)[0]["text"] == "Hello & welcome"


def test_iw_a12_a_message_inside_a_message_isnt_read_as_their_words(conn, monkeypatch):
    """IW-A12: nested rfc822."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [NESTED])

    mail.intake(conn)

    assert items(conn)[0]["text"] == "See attached."


def test_iw_a12_attachments_are_named_and_their_bytes_kept_nowhere(conn, monkeypatch):
    """IW-A12, PRD §3: names noted, never opened, never stored."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [ATTACHED])

    mail.intake(conn)

    [item] = items(conn)
    assert json.loads(item["attachments_json"]) == ["quote.pdf"]
    everything = json.dumps(item, default=str)
    assert "SECRET-ATTACHMENT" not in everything and "U0VDUkVU" not in everything


def test_iw_a12_a_message_that_cant_be_parsed_at_all_is_still_reported(conn, monkeypatch):
    """IW-A12: whatever goes wrong with one message, the person isn't lost and the batch goes on."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(body="First message"), raw_mail(body="Second message")])
    real = replies.own_text
    calls = {"n": 0}

    def explode(message):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("a parser bug")
        return real(message)

    monkeypatch.setattr(replies, "own_text", explode)

    mail.intake(conn)

    first, second = items(conn)
    assert first["state"] == store.NEEDS_YOU and "couldn't be read" in first["note"]
    assert second["text"] == "Second message"
    assert fake.logged_out


def test_iw_a6_a_huge_message_is_read_only_part_way_and_still_reported(conn, monkeypatch):
    """IW-A6: 1 MB of body: the fetch is partial, and at most 4,000 characters are stored."""
    at(monkeypatch, NOW)
    fake = mailbox_env(monkeypatch, [raw_mail(body="word " * 200_000)])

    mail.intake(conn)

    [item] = items(conn)
    assert len(item["text"]) == 4000 and item["text_cut"] == 1
    assert any(f"<0.{replies.MAX_BODY_BYTES}>" in spec for spec in fake.fetch_specs)


def test_iw_r1_someone_who_writes_below_the_quote_still_has_words(conn, monkeypatch):
    """IW-R1: a bottom-poster's own text isn't lost to the quote rule."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail(body="> You wrote this first\n> and this\n\nYes, tell me more.")])

    mail.intake(conn)

    assert items(conn)[0]["text"] == "Yes, tell me more."


def test_iw_a14_nothing_a_person_wrote_reaches_the_event_log(conn, monkeypatch):
    """IW-A14: run records and events hold ids and domains, never text or an address."""
    at(monkeypatch, NOW)
    mailbox_env(monkeypatch, [raw_mail("Jane Tan <jane.tan@acme.example>", subject="Private subject line here",
                                       body="My number is +65 9123 4567 and this is private.")])

    assert runner.run("inbox-check").status == "ok"

    events = json.dumps(db.rows(conn, "SELECT kind, payload_json FROM events"))
    for planted in ("Private subject line", "jane.tan@", "Jane Tan", "9123", "this is private"):
        assert planted not in events
    assert "acme.example" in events  # domains are allowed, and say which message
