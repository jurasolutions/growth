"""Regressions from code review 04, one per finding (`reviews/code-review-04.md`).

Blocking: P-1 (`done` can't launder an item past "never sent again"), P-2 (a redraft's ask ends with its
card), SEC-1 (only a row a reply caused, and nothing since, can be lifted), SEC-2 (only the message that
caused it can lift it, so a stranger's `Reply-To` lifts nothing). The should-fix items follow them.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from discord_double import discord_double  # noqa: F401 - a fixture
from inbox_world import mailbox_env, raw_mail
from jura_growth import approvals, backup, config, db, discord, suppression
from jura_growth.agents.inbox import kinds, mail, one_pager, send, signals, store, triage
from jura_growth.cli import cli
from jura_growth.origin import Origin
from test_inbox_email_reply import DRAFT, PRIYA, approved, box, carded, request_for, sent, triaged  # noqa: F401
from test_inbox_email_reply import arrives as arrives_raw
from test_outreach_sync import live_sends
from test_scout_support import at, decide, fake_d1, reply_message, scout_env  # noqa: F401

VICTIM = "victim@other.example"
EVIL = "evil@bad.example"


@pytest.fixture(autouse=True)
def control(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")


def remote(*words) -> dict:
    result = CliRunner().invoke(cli, ["remote", "--actor", "discord:111", "--json", "--", *words], obj={"origin": Origin.ssh()})
    return json.loads(result.output)


def arrives(conn, box, raw: bytes | None = None) -> dict:
    return arrives_raw(conn, box, raw or raw_mail())


def reload(conn, item: dict) -> dict:
    return store.get(conn, item["id"])


def label(item: dict) -> str:
    return store.label(item["id"])


def opted_out(conn, box, raw: bytes | None = None) -> dict:
    """Their own message asks not to be contacted, and triage classes it so: this message suppressed them."""
    item = arrives(conn, box, raw)
    assert triage.submit(conn, {"id": label(item), "class": "opt-out"}).exit_code == 0
    return reload(conn, item)


# --- P-1: `done` then `draft` never resends or reopens ------------------------------------------------


@pytest.mark.parametrize("state", [store.UNKNOWN, store.FAILED, store.UNVERIFIED])
def test_iw_n13_done_then_draft_refuses_what_could_not_have_a_draft_before(conn, box, sent, discord_double, state):
    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], state)
    before = remote("inbox", "draft", label(item))
    assert before["exit_code"] == 1

    assert remote("inbox", "done", label(item))["exit_code"] == 0
    after = remote("inbox", "draft", label(item))

    assert after["exit_code"] == 1, after
    assert reload(conn, item)["state"] == state  # clearing doesn't erase what it was
    assert reload(conn, item)["asked_at"] is None


def test_iw_n13_an_unknown_reply_is_never_sent_again_after_done_and_draft(conn, box, sent, discord_double, monkeypatch):
    """The review's sequence: a claim goes uncertain, he clears it, and he asks for a draft."""
    item, _ = approved(conn, box, monkeypatch)
    send.send_due(conn)
    posts = len(sent)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.UNKNOWN, note="It may have gone out.")
        conn.execute("UPDATE inbox_items SET sent_at = NULL WHERE id = ?", (item["id"],))

    assert remote("inbox", "done", label(item))["exit_code"] == 0
    assert remote("inbox", "draft", label(item))["exit_code"] == 1
    send.send_due(conn)

    assert len(sent) == posts
    assert reload(conn, item)["state"] == store.UNKNOWN


def test_iw_n13_a_claimed_item_refuses_a_draft_whatever_its_state_reads(conn, box, sent, discord_double, monkeypatch):
    """A claim happened, so an email may be out, whichever state the row has come to."""
    item, record = approved(conn, box, monkeypatch)
    with db.transaction(conn):
        approvals.use(conn, kinds.KIND, kinds.subject_of(item["id"]), run_id=None)
        store.set_item_state(conn, item["id"], store.DONE)
    body = remote("inbox", "draft", label(item))
    assert body["exit_code"] == 1 and "may have" in body["text"], record.id


def test_iw_r4_a_cleared_line_leaves_the_list_and_stays_cleared(conn, box, sent, discord_double):
    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.UNKNOWN)
    assert label(item) in remote("inbox", "list")["text"]
    remote("inbox", "done", label(item))
    assert label(item) not in remote("inbox", "list")["text"]
    assert "nothing open" in remote("inbox", "done", label(item))["text"]


def test_iw_s3_a_cleared_unverified_message_stays_out_of_what_triage_reads(conn, box, sent, discord_double):
    """N3: its words aren't proved to be anyone's, and clearing it doesn't prove them."""
    item = arrives(conn, box, raw_mail(body="UNPROVED words"))
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.UNVERIFIED)
    remote("inbox", "done", label(item))
    assert "UNPROVED" not in json.dumps(store.history(conn, item["conversation"]))


def test_iw_s2_a_needs_you_item_he_cleared_can_still_have_a_draft(conn, box, sent, discord_double):
    """Nothing was sent, so this is only him changing his mind."""
    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY)
    remote("inbox", "done", label(item))
    assert reload(conn, item)["state"] == store.DONE
    assert remote("inbox", "draft", label(item))["exit_code"] == 0


# --- P-2: a redraft's ask ends with its card ------------------------------------------------------------


def next_message(conn, box) -> dict:
    return arrives(conn, box, raw_mail(subject="A question about invoices", body="Thanks, that is all I needed."))


def test_iw_e1_a_skip_ends_the_redraft_and_his_guidance_reaches_nothing_later(conn, box, sent, discord_double, monkeypatch):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "offer", "them", "a", "free", "call")
    decide(conn, old, "skip", monkeypatch)

    found = reload(conn, item)
    assert found["asked_at"] is None and found["guidance"] is None

    next_message(conn, box)
    [given] = triage.hand_out(conn)["conversations"]
    assert given["guidance"] is None and given["must_draft"] is False


def test_iw_e1_a_send_ends_the_redraft_and_his_guidance_reaches_nothing_later(conn, box, sent, discord_double, monkeypatch):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    decide(conn, old, "approve", monkeypatch)
    send.send_due(conn)

    found = reload(conn, item)
    assert found["state"] == store.SENT and found["asked_at"] is None and found["guidance"] is None

    next_message(conn, box)
    [given] = triage.hand_out(conn)["conversations"]
    assert given["guidance"] is None and given["must_draft"] is False


def test_iw_e1_the_claim_itself_ends_the_redraft_while_the_send_is_under_way(conn, box, sent, discord_double, monkeypatch):
    """A retry can leave it `sending` for up to 23 hours, with nothing else moving its state."""
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    decide(conn, old, "approve", monkeypatch)

    assert send._claim(conn, item["id"]) is not None

    found = reload(conn, item)
    assert found["state"] == store.SENDING and found["asked_at"] is None and found["guidance"] is None


def test_iw_e1_a_supersede_ends_the_redraft_once_the_new_message_is_answered(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    newer = next_message(conn, box)
    triaged(conn, newer, draft="We help with invoices.")

    found = reload(conn, item)
    assert found["state"] == store.SUPERSEDED and found["asked_at"] is None and found["guidance"] is None


def test_iw_e1_an_old_ask_left_on_a_closed_row_isnt_read(conn, box, sent, discord_double):
    """Whatever left it there: only an item still open carries an ask."""
    item = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.SKIPPED)
        conn.execute("UPDATE inbox_items SET asked_at = '2026-10-26T09:00:00+08:00', guidance = 'stale' WHERE id = ?", (item["id"],))
    next_message(conn, box)
    [given] = triage.hand_out(conn)["conversations"]
    assert given["guidance"] is None and given["must_draft"] is False


def test_iw_d5_his_guidance_still_carries_while_the_card_is_open(conn, box, sent, discord_double):
    _, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    next_message(conn, box)
    [given] = triage.hand_out(conn)["conversations"]
    assert given["guidance"] == "shorter" and given["must_draft"] is True


# --- P-3 -------------------------------------------------------------------------------------------------


def test_iw_s1_a_redraft_landing_after_an_approve_keeps_his_yes(conn, box, sent, discord_double, monkeypatch):
    item, old = carded(conn, box)
    remote("inbox", "redraft", old.id, "shorter")
    decide(conn, old, "approve", monkeypatch)

    outcome = triage.submit(conn, {"id": label(item), "class": "question", "draft": "We help with invoices."})

    assert outcome.exit_code == 0
    assert approvals.get(conn, old.id).status == approvals.APPROVED
    found = reload(conn, item)
    assert found["draft"] == DRAFT and found["asked_at"] is None and found["guidance"] is None
    assert request_for(conn, item).id == old.id


# --- SEC-1: only a row whose source is a reply ------------------------------------------------------------


@pytest.mark.parametrize("reason, source, says", [
    ("manual", "cli", "manual"),
    ("unsubscribe", "d1:link", "unsubscribe"),
    ("bounce", "d1:resend", "bounce"),
    ("complaint", "d1:resend", "complaint"),
])
def test_iw_e2_an_event_landing_on_a_replys_row_takes_it_over_and_is_refused_with_the_reason(conn, box, sent, discord_double, reason, source, says):
    item = opted_out(conn, box)
    with db.transaction(conn):
        assert suppression.add(conn, email=PRIYA, reason=reason, source=source) is False

    assert suppression.source_of(conn, PRIYA) == source
    body = remote("inbox", "unsuppress", label(item))

    assert body["exit_code"] == 1 and says in body["text"], body
    assert suppression.is_suppressed(conn, PRIYA) == reason


def test_iw_e2_a_reply_landing_on_someone_elses_row_doesnt_take_it_over(conn):
    with db.transaction(conn):
        suppression.add(conn, email=PRIYA, reason="manual", source="cli")
        suppression.add(conn, email=PRIYA, reason="unsubscribe", source=suppression.FROM_A_REPLY)
    assert suppression.source_of(conn, PRIYA) == "cli"
    assert suppression.is_suppressed(conn, PRIYA) == "manual"


def test_iw_e2_the_manual_command_on_a_replys_row_is_refused_a_lift(conn, box, sent, discord_double):
    """The review's reproduction, through the real command."""
    item = opted_out(conn, box)
    CliRunner().invoke(cli, ["suppression", "add", PRIYA, "--reason", "manual"])
    assert remote("inbox", "unsuppress", label(item))["exit_code"] == 1
    assert suppression.is_suppressed(conn, PRIYA) == "manual"


def test_iw_e2_a_d1_sync_landing_on_a_replys_row_is_refused_a_lift(conn, box, sent, discord_double, monkeypatch):
    item = opted_out(conn, box)
    rows = [{"id": 1, "email_hash": suppression.email_hash(PRIYA), "email": PRIYA, "reason": "complaint", "source": "resend",
             "resend_email_id": None, "created_at": "2026-10-26T09:00:00+08:00"}]
    fake_d1(monkeypatch, rows)
    suppression.sync_from_d1(conn, lambda events: None)
    fake_d1(monkeypatch, [])
    assert remote("inbox", "unsuppress", label(item))["exit_code"] == 1
    assert suppression.is_suppressed(conn, PRIYA) == "complaint"


def test_iw_e2_secrets_that_cant_be_read_are_no_answer_from_the_website(conn, box, sent, discord_double, monkeypatch):
    """A locked Keychain under SSH: `configured()` reads false, and that must not read as nothing there."""
    item = opted_out(conn, box)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "keychain:jura-growth-cloudflare")
    monkeypatch.setattr(config, "_keychain", lambda service: None)
    config.reset_caches()

    body = remote("inbox", "unsuppress", label(item))

    assert body["exit_code"] == 1 and "can't be read" in body["text"], body
    assert suppression.is_suppressed(conn, PRIYA)


def test_iw_e2_a_website_never_set_up_has_nothing_to_hold(conn, box, sent, discord_double, monkeypatch):
    item = opted_out(conn, box)
    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "D1_DATABASE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_env_file", lambda: {})
    config.reset_caches()
    assert remote("inbox", "unsuppress", label(item))["exit_code"] == 0


# --- SEC-2: only the message that caused it ------------------------------------------------------------


def victim_opted_out(conn, box) -> dict:
    return opted_out(conn, box, raw_mail(f"Victim <{VICTIM}>", subject="Their own mail", body="Please leave me out of this."))


def stranger_naming_the_victim(conn, box) -> dict:
    return arrives(conn, box, raw_mail(f"Evil <{EVIL}>", subject="A trick", body="Hello there", Reply_To=VICTIM))


def test_iw_a9_a_strangers_reply_to_cant_lift_anyones_opt_out(conn, box, sent, discord_double):
    victim_opted_out(conn, box)
    trick = stranger_naming_the_victim(conn, box)

    body = remote("inbox", "unsuppress", label(trick))

    assert body["exit_code"] == 1, body
    assert suppression.is_suppressed(conn, VICTIM) == "unsubscribe"


def test_iw_a9_the_engine_doesnt_offer_the_lift_on_a_strangers_mail(conn, box, sent, discord_double):
    victim_opted_out(conn, box)
    trick = stranger_naming_the_victim(conn, box)
    conn.execute("UPDATE inbox_items SET state = ? WHERE id = ?", (store.REPORTED, trick["id"]))

    body = remote("inbox", "draft", label(trick))

    assert body["exit_code"] == 1 and "unsuppress" not in body["text"], body


def test_iw_e2_a_later_message_from_them_isnt_what_suppressed_them(conn, box, sent, discord_double):
    first = victim_opted_out(conn, box)
    later = arrives(conn, box, raw_mail(f"Victim <{VICTIM}>", subject="Another", body="One more thing"))

    body = remote("inbox", "unsuppress", label(later))

    assert body["exit_code"] == 1 and label(first) in body["text"], body
    assert suppression.is_suppressed(conn, VICTIM)
    assert remote("inbox", "unsuppress", label(first))["exit_code"] == 0
    assert suppression.is_suppressed(conn, VICTIM) is None


def test_iw_e2_the_answer_names_the_domain_it_lifted(conn, box, sent, discord_double):
    item = opted_out(conn, box)
    assert "clinic.example" in remote("inbox", "unsuppress", label(item))["text"]


def test_iw_e2_only_the_senders_own_address_is_lifted(conn, box, sent, discord_double):
    """Their own mail, with a `Reply-To` naming someone who opted out separately: that one stays."""
    item = opted_out(conn, box, raw_mail(f"Priya <{PRIYA}>", subject="Own", body="Leave me out.", Reply_To=VICTIM))
    with db.transaction(conn):
        suppression.add(conn, email=VICTIM, reason="unsubscribe", source=suppression.FROM_A_REPLY)
    assert remote("inbox", "unsuppress", label(item))["exit_code"] == 0
    assert suppression.is_suppressed(conn, PRIYA) is None
    assert suppression.is_suppressed(conn, VICTIM) == "unsubscribe"


def test_iw_e2_an_opt_out_in_the_words_at_intake_can_be_lifted_from_its_own_report(conn, box, sent, discord_double, monkeypatch):
    """The other way in: the closed phrase list at intake, on a real emailed lead, and its note."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    mailbox_env(monkeypatch, [reply_message(lead["email"], when="2026-10-26T15:00:00+08:00", body="unsubscribe")])
    at(monkeypatch, "2026-10-26T15:10:00+08:00")
    mail.intake(conn)
    [item] = db.rows(conn, "SELECT * FROM inbox_items")
    assert f"/growth inbox unsuppress {label(item)}" in item["note"]
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead["lead_id"],)) == "unsubscribed"

    assert remote("inbox", "unsuppress", label(item))["exit_code"] == 0

    assert suppression.is_suppressed(conn, lead["email"]) is None
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead["lead_id"],)) == "replied"
    assert db.scalar(conn, "SELECT unsubscribe FROM outreach_replies WHERE message_key = ?", (item["key"],)) == 0


# --- SEC-3 and SEC-4 -------------------------------------------------------------------------------------


def test_iw_e2_a_domain_row_beside_it_stops_the_lift(conn, box, sent, discord_double):
    item = opted_out(conn, box)
    with db.transaction(conn):
        suppression.add(conn, domain="clinic.example", reason="manual", source="cli")

    body = remote("inbox", "unsuppress", label(item))

    assert body["exit_code"] == 1 and "whole domain" in body["text"], body
    assert suppression.source_of(conn, PRIYA) == suppression.FROM_A_REPLY
    assert suppression.is_suppressed(conn, PRIYA)


def two_contact_lead(conn, *, boss_suppressed: bool) -> int:
    now = "2026-10-20T09:00:00+08:00"
    conn.execute("INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel, status, created_at, updated_at) "
                 "VALUES (50, 'Clinic', 'Clinic', 'clinic.example', 'https://clinic.example', 'health', 70, '[]', 'email', 'unsubscribed', ?, ?)", (now, now))
    for address in (PRIYA, "boss@clinic.example"):
        conn.execute("INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at) "
                     "VALUES (50, ?, ?, 'https://clinic.example', 'named', 1, ?, ?)", (address, suppression.email_hash(address), now, now))
    if boss_suppressed:
        suppression.add(conn, email="boss@clinic.example", reason="unsubscribe", source="d1:link")
    return 50


def test_iw_e2_restoring_a_lead_doesnt_undo_a_colleagues_unsubscribe(conn, box, sent, discord_double):
    item = opted_out(conn, box)
    with db.transaction(conn):
        lead = two_contact_lead(conn, boss_suppressed=True)
        conn.execute("UPDATE inbox_items SET lead_id = ? WHERE id = ?", (lead, item["id"]))
        boss = db.scalar(conn, "SELECT id FROM contacts WHERE email = 'boss@clinic.example'")
        conn.execute("INSERT INTO outreach_replies (lead_id, contact_id, message_key, received_at, unsubscribe, detected_at) VALUES (50, ?, 'boss-key', ?, 1, ?)",
                     (boss, item["recorded_at"], item["recorded_at"]))
        conn.execute("INSERT INTO outreach_replies (lead_id, contact_id, message_key, received_at, unsubscribe, detected_at) VALUES (50, NULL, ?, ?, 1, ?)",
                     (item["key"], item["recorded_at"], item["recorded_at"]))

    assert remote("inbox", "unsuppress", label(item))["exit_code"] == 0

    assert suppression.is_suppressed(conn, PRIYA) is None
    assert suppression.is_suppressed(conn, "boss@clinic.example")
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = 50") == "unsubscribed"
    assert db.scalar(conn, "SELECT unsubscribe FROM outreach_replies WHERE message_key = 'boss-key'") == 1
    assert db.scalar(conn, "SELECT unsubscribe FROM outreach_replies WHERE message_key = ?", (item["key"],)) == 0


# --- SEC-5 and P-12 --------------------------------------------------------------------------------------


@pytest.mark.parametrize("words, kept", [
    (("inbox", "rewrd", "A-0001", "Dear", "PRIVATETYPO"), ["inbox", "rewrd"]),
    (("inbox", "reword", "Dear", "PRIVATETYPO"), ["inbox", "reword"]),  # the right command, with no id: the first word is his
    (("rewrd", "PRIVATETYPO", "more"), ["rewrd", "PRIVATETYPO"]),  # the first two words of anything refused
])
def test_iw_d6_a_typo_keeps_almost_none_of_his_words_in_the_event_that_is_never_pruned(conn, words, kept):
    remote(*words)
    [event] = db.rows(conn, "SELECT payload_json FROM events WHERE kind = 'remote.command'")
    assert json.loads(event["payload_json"])["words"] == kept


@pytest.mark.parametrize("words", [("inbox", "done", "I-" + "9" * 30), ("inbox", "reword", "A-" + "9" * 30, "x"), ("inbox", "unsuppress", "I-" + "9" * 30)])
def test_iw_d6_an_id_too_big_for_sqlite_is_only_a_refusal(conn, words):
    body = remote(*words)
    assert body["exit_code"] == 2 and body["text"].startswith("refused:") and "Overflow" not in body["text"]


# --- P-4 -------------------------------------------------------------------------------------------------


def test_iw_s2_done_clears_what_it_can_and_says_the_card_still_waits(conn, box, sent, discord_double):
    older = arrives(conn, box)
    with db.transaction(conn):
        store.set_item_state(conn, older["id"], store.LAPSED)
    newer = arrives(conn, box, raw_mail(subject="A question about invoices", body="Still there?"))
    triaged(conn, newer)
    record = request_for(conn, newer)

    body = remote("inbox", "done", label(older))

    assert body["exit_code"] == 0 and record.id in body["text"] and "still waits" in body["text"]
    assert reload(conn, older)["state"] == store.DONE and reload(conn, newer)["state"] == store.WAITING


# --- P-5, P-6, P-11, S-1 ----------------------------------------------------------------------------------


def test_iw_r2_the_list_shows_every_noise_sender_where_the_one_pager_caps_them(conn):
    for number in range(30):
        key = f"n{number}"
        store.record(conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=f"s{number}.example", state=store.NOISE, note="a list"))
    for number in range(8):
        key = f"j{number}"
        store.record(conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=f"j{number}.example", subject=f"Subject {number}",
                                          state=store.NOISE, note=store.JUNK_NOTE))
    conn.commit()

    capped = "\n".join(one_pager.lines(conn, "2020-01-01"))
    whole = "\n".join(one_pager.lines(conn, "2020-01-01", limit=None))

    assert "and 18 more" in capped and "and 3 more" in capped
    assert "and 18 more" not in whole and "and 3 more" not in whole
    assert sum(f"s{number}.example" in whole for number in range(30)) == 30
    assert sum(f"Subject {number}" in whole for number in range(8)) == 8


def complaint(conn, domain="acme.example") -> None:
    conn.execute("INSERT INTO events (ts, agent, level, kind, payload_json) VALUES ('2026-10-26T16:45:00+08:00', 'outreach', 'info', 'outreach.suppressed', ?)",
                 (json.dumps({"reason": "complaint", "source": "resend", "domains": [domain], "message": 1}),))


def test_iw_s12_the_first_check_doesnt_report_every_complaint_in_history(conn):
    complaint(conn, "old.example")
    signals.report_complaints(conn)
    assert db.rows(conn, "SELECT * FROM inbox_items") == []

    complaint(conn, "new.example")
    signals.report_complaints(conn)
    [item] = db.rows(conn, "SELECT * FROM inbox_items")
    assert "new.example" in item["note"] and "old.example" not in item["note"]


def test_iw_s12_a_first_check_with_no_events_still_sees_the_first_complaint(conn):
    signals.report_complaints(conn)
    complaint(conn)
    signals.report_complaints(conn)
    assert len(db.rows(conn, "SELECT * FROM inbox_items")) == 1


def test_iw_n9_a_break_glued_to_a_word_is_still_a_break(conn, box, sent, discord_double):
    item, old = carded(conn, box)
    assert remote("inbox", "reword", old.id, "Soon\\n\\nafter.")["exit_code"] == 0
    assert reload(conn, item)["draft"] == "Soon\n\nafter."


def test_iw_n6_config_may_shorten_the_outbox_and_never_lengthen_it(conn, monkeypatch):
    real = config.settings()
    monkeypatch.setattr(config, "settings", lambda: {**real, "retention": {**real.get("retention", {}), "outbox_days": 400}})
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-30T23:30:00+08:00")
    folder = discord.outbox_dir()
    folder.mkdir(parents=True, exist_ok=True)
    old = folder / "2026-11-01.jsonl"
    old.write_text("{}\n")
    backup.prune_outbox()
    assert not old.exists()


def test_iw_s7_a_complaints_alert_says_what_it_is(conn, box, sent, discord_double):
    from jura_growth.agents.inbox import report

    signals.report_complaints(conn)
    complaint(conn)
    signals.report_complaints(conn)
    report.alert_high(conn)
    assert any("spam complaint" in text for text in discord_double.contents("alerts"))

