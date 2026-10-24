"""Suppression sync from D1, auto-pause, reply detection, follow-ups,
retention and the digest figures."""

import httpx
import pytest
from click.testing import CliRunner

from jura_growth import db, pause, runner, suppression, timeutil
from jura_growth.agents import outreach
from jura_growth.agents.outreach import queue as queue_mod
from jura_growth.agents.outreach import replies, send, store, sync
from jura_growth.cli import cli

from test_scout_support import (  # noqa: F401
    MONDAY_10AM,
    add,
    at,
    d1_env,
    fake_d1,
    fake_resend,
    imap_env,
    lead_data,
    live_ready,
    outbox,
    reply_message,
    scout_env,
    seed,
)


def d1_row(email, reason, *, source="resend-webhook", resend_id=None, with_email=True, created="2026-10-26 11:00:00"):
    return {
        "email_hash": suppression.email_hash(email),
        "email": email if with_email else None,
        "reason": reason,
        "source": source,
        "resend_email_id": resend_id,
        "created_at": created,
    }


class D1:
    """The site's append-only D1 suppression table: one row per event, each
    with the next id. It answers every query with every row, so the sync has to
    skip what it has already processed by itself."""

    def __init__(self):
        self.rows = []

    def __call__(self, request):
        for number, row in enumerate(self.rows, 1):
            row.setdefault("id", number)
        return httpx.Response(200, json={"success": True, "result": [{"results": list(self.rows)}]})


def live_sends(conn, monkeypatch, count):
    """Seed `count` leads and send each live on Monday 26 October."""
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    seeded = [seed(conn, n) for n in range(1, count + 1)]
    live_ready(monkeypatch)
    table = D1()
    fake_d1(monkeypatch, table)
    sent = fake_resend(monkeypatch)
    for index in range(count):
        at(monkeypatch, f"2026-10-26T{10 + index // 6:02d}:{(index % 6) * 10:02d}:00+08:00")
        assert send.send_due(conn).summary.startswith("sent message")
    assert len(sent) == count
    for item in seeded:
        item["resend_id"] = db.scalar(conn, "SELECT resend_id FROM outreach_messages WHERE id = ?", (item["message_id"],))
    return seeded, table


# --- D1: bounces, unsubscribes, complaints ---------------------------------


def test_simulated_bounce_marks_the_message_and_suppresses(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    first = seeded[0]
    table.rows.append(d1_row(first["email"], "bounce", resend_id=first["resend_id"]))
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    summary = sync.run(conn)
    assert "1 new suppression (0 unsubscribe, 1 bounce, 0 complaint)" in summary
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "bounced"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (first["lead_id"],)) == "bounced"
    assert suppression.is_suppressed(conn, first["email"]) == "bounce"
    assert any("Bounce" in p["content"] for p in outbox("outreach-replies"))
    assert pause.is_paused(conn, "outreach") is None  # one bounce in 50 is 2%
    # the address can't come back as a new lead
    assert add(conn, lead_data(1)).status == "rejected"


def test_resync_adds_no_duplicates(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    table.rows.append(d1_row(seeded[0]["email"], "bounce", resend_id=seeded[0]["resend_id"]))
    sync.run(conn)
    second = sync.run(conn)
    assert "0 new suppressions" in second
    assert db.scalar(conn, "SELECT count(*) FROM suppression") == 1


def test_test_unsubscribe_is_suppressed_within_one_sync(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    d1_env(monkeypatch)
    table = D1()
    fake_d1(monkeypatch, table)
    # The site's unsubscribe function stores the hash only (no address in the URL).
    table.rows.append(d1_row(seeded["email"], "unsubscribe", source="unsubscribe-link", with_email=False))
    summary = sync.run(conn)
    assert "1 unsubscribe" in summary
    assert suppression.is_suppressed(conn, seeded["email"]) == "unsubscribe"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded["lead_id"],)) == "unsubscribed"
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (seeded["message_id"],)) == "cancelled"
    assert any("Unsubscribe" in p["content"] for p in outbox("outreach-replies"))


def test_one_click_post_unsubscribe_is_suppressed_before_the_next_send(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    first, second = seed(conn, 1), seed(conn, 2)
    d1_env(monkeypatch)
    table = D1()
    fake_d1(monkeypatch, table)
    table.rows.append(d1_row(first["email"], "unsubscribe", source="unsubscribe-post", with_email=False))
    result = send.send_due(conn)
    assert result.summary.startswith(f"SHADOW message {second['message_id']}")
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "cancelled"


def test_complaint_pauses_outreach_and_resume_restarts_it(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    waiting = seed(conn, 2)
    table.rows.append(d1_row(seeded[0]["email"], "complaint", resend_id=seeded[0]["resend_id"]))
    at(monkeypatch, "2026-10-26T13:00:00+08:00")
    result = send.send_due(conn)
    assert "paused" in result.summary and "complaint" in result.summary
    assert "complaint" in pause.is_paused(conn, "outreach")
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (seeded[0]["message_id"],)) == "complained"
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (waiting["message_id"],)) == "queued"
    assert any("Paused `outreach`" in p["content"] for p in outbox("alerts"))

    at(monkeypatch, "2026-10-26T13:10:00+08:00")
    assert send.send_due(conn).summary is None  # still paused
    assert CliRunner().invoke(cli, ["resume", "outreach"]).exit_code == 0
    at(monkeypatch, "2026-10-26T13:20:00+08:00")
    assert send.send_due(conn).summary == f"sent message {waiting['message_id']} to birchlogistics.sg"


def test_complaint_after_an_unsubscribe_still_pauses(conn, monkeypatch):
    # Review finding F1: "report spam and unsubscribe". The one-click POST
    # suppressed the address first, so the complaint after it was dropped.
    seeded, table = live_sends(conn, monkeypatch, 1)
    first = seeded[0]
    table.rows.append(d1_row(first["email"], "unsubscribe", source="unsubscribe-post", with_email=False, created="2026-10-26 11:00:00"))
    sync.run(conn)
    assert pause.is_paused(conn, "outreach") is None
    table.rows.append(d1_row(first["email"], "complaint", resend_id=first["resend_id"], created="2026-10-26 12:00:00"))
    summary = sync.run(conn)
    assert "1 new suppression (0 unsubscribe, 0 bounce, 1 complaint)" in summary
    assert "complaint" in pause.is_paused(conn, "outreach")  # PRD 5.7: any complaint pauses
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "complained"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (first["lead_id"],)) == "complained"


def test_complaint_after_a_reply_unsubscribe_still_pauses(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    first = seeded[0]
    suppression.add(conn, email=first["email"], reason="unsubscribe", source="reply")  # what replies._record does
    table.rows.append(d1_row(first["email"], "complaint", resend_id=first["resend_id"], created="2026-10-26 12:00:00"))
    sync.run(conn)
    assert "complaint" in pause.is_paused(conn, "outreach")


def test_bounce_after_an_unsubscribe_still_marks_the_bounce(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    first = seeded[0]
    table.rows.append(d1_row(first["email"], "unsubscribe", source="unsubscribe-link", with_email=False))
    table.rows.append(d1_row(first["email"], "bounce", resend_id=first["resend_id"], created="2026-10-26 11:05:00"))
    sync.run(conn)
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "bounced"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (first["lead_id"],)) == "bounced"


def test_a_later_unsubscribe_never_weakens_a_complaint(conn, monkeypatch):
    # The webhook and the one-click POST arrive in either order.
    seeded, table = live_sends(conn, monkeypatch, 1)
    first = seeded[0]
    table.rows.append(d1_row(first["email"], "complaint", resend_id=first["resend_id"]))
    table.rows.append(d1_row(first["email"], "unsubscribe", source="unsubscribe-post", with_email=False, created="2026-10-26 11:01:00"))
    table.rows.append(d1_row(first["email"], "manual", source="manual", created="2026-10-26 11:02:00"))
    sync.run(conn)
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (first["lead_id"],)) == "complained"
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "complained"
    assert "complaint" in pause.is_paused(conn, "outreach")


def test_a_processed_d1_event_is_never_applied_again(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    calls = fake_d1(monkeypatch, table)
    table.rows.append(d1_row(seeded[0]["email"], "complaint", resend_id=seeded[0]["resend_id"]))
    sync.run(conn)
    pause.resume(conn, "outreach")
    alerts = len(outbox("alerts"))
    summary = sync.run(conn)  # the fake D1 still returns the old complaint
    assert "0 new suppressions" in summary
    assert pause.is_paused(conn, "outreach") is None
    assert len(outbox("alerts")) == alerts
    assert calls[0]["params"] == [0] and calls[-1]["params"] == [1]  # D1 is asked only for later events


def test_a_sync_that_fails_part_way_keeps_nothing_and_is_retried_whole(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    first = seeded[0]
    table.rows.append(d1_row(first["email"], "complaint", resend_id=first["resend_id"]))
    table.rows.append(d1_row("someone@else.sg", "spam-report"))  # a reason the contract doesn't allow
    summary = sync.run(conn)
    assert "suppression sync failed" in summary
    assert "suppression sync from D1 failed" in pause.is_paused(conn, "outreach")
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "sent"
    assert suppression.is_suppressed(conn, first["email"]) is None

    table.rows[1]["reason"] = "complaint"  # the site fixes its row
    pause.resume(conn, "outreach")
    summary = sync.run(conn)
    assert "2 new suppressions (0 unsubscribe, 0 bounce, 2 complaint)" in summary
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (first["message_id"],)) == "complained"
    assert "complaint" in pause.is_paused(conn, "outreach")
    pause.resume(conn, "outreach")
    assert "0 new suppressions" in sync.run(conn)


def _three_unsubscribes_synced(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    for n in range(3):
        table.rows.append(d1_row(f"person{n}@elsewhere.sg", "unsubscribe", created=f"2026-10-26 11:0{n}:00"))
    sync.run(conn)
    return seeded[0], table


def test_a_d1_table_recreated_behind_the_cursor_fails_closed(conn, monkeypatch):
    first, table = _three_unsubscribes_synced(conn, monkeypatch)
    # The site's table is dropped and recreated (ids start again at 1); a complaint arrives.
    table.rows[:] = [d1_row(first["email"], "complaint", resend_id=first["resend_id"])]
    summary = sync.run(conn)
    assert "suppression sync failed" in summary and "event 3" in summary
    assert "suppression sync from D1 failed" in pause.is_paused(conn, "outreach")
    assert any("Paused `outreach`" in p["content"] for p in outbox("alerts"))


def test_a_d1_table_rewritten_at_the_cursor_fails_closed(conn, monkeypatch):
    first, table = _three_unsubscribes_synced(conn, monkeypatch)
    # Recreated and refilled past the old cursor: id 3 is now a different event.
    table.rows[:] = [
        d1_row(f"new{n}@elsewhere.sg", "unsubscribe", created=f"2026-10-27 09:0{n}:00") for n in range(3)
    ] + [d1_row(first["email"], "complaint", resend_id=first["resend_id"], created="2026-10-27 09:05:00")]
    summary = sync.run(conn)
    assert "suppression sync failed" in summary
    assert "suppression sync from D1 failed" in pause.is_paused(conn, "outreach")


def test_a_d1_row_without_an_id_fails_the_sync_and_pauses(conn, monkeypatch):
    # The old contract (email_hash as the primary key, no id) can't be read safely.
    d1_env(monkeypatch)
    fake_d1(monkeypatch, [d1_row("a@b.sg", "complaint")])
    summary = sync.run(conn)
    assert "suppression sync failed" in summary and "append-only" in summary
    assert "suppression sync from D1 failed" in pause.is_paused(conn, "outreach")


def test_bounce_rate_above_three_percent_pauses(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 3)
    table.rows.append(d1_row(seeded[0]["email"], "bounce", resend_id=seeded[0]["resend_id"]))
    sync.run(conn)
    assert pause.is_paused(conn, "outreach") is None
    table.rows.append(d1_row(seeded[1]["email"], "bounce", resend_id=seeded[1]["resend_id"], created="2026-10-26 12:00:00"))
    summary = sync.run(conn)
    assert "bounce rate" in pause.is_paused(conn, "outreach") and "paused" in summary


def test_failed_sync_pauses_outreach(conn, monkeypatch):
    d1_env(monkeypatch)
    fake_d1(monkeypatch, lambda request: httpx.Response(503, text="unavailable"))
    summary = sync.run(conn)
    assert "suppression sync failed" in summary
    assert "suppression sync from D1 failed" in pause.is_paused(conn, "outreach")


def test_unconfigured_d1_is_a_warning_in_shadow(conn):
    assert "D1 not configured" in sync.run(conn) and "fine in shadow mode" in sync.run(conn)
    assert pause.is_paused(conn, "outreach") is None


def test_sync_job_records_a_run(isolated, monkeypatch):
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    outcome = runner.run("scout-sync")
    assert outcome.status == "ok" and outcome.summary.startswith("sync: ")
    with db.session() as c:
        assert db.scalar(c, "SELECT agent FROM runs WHERE job = 'scout-sync'") == "outreach"


# --- auto-pause on brand failures ------------------------------------------


def test_two_brand_failures_in_a_row_pause_and_resume_resets(conn):
    assert not store.record_qa(conn, "a", False, ["x"])
    assert store.record_qa(conn, "a", False, ["x"])
    assert "brand check in a row" in pause.is_paused(conn, "outreach")
    pause.resume(conn, "outreach")
    assert not store.record_qa(conn, "b", False, ["x"])
    assert pause.is_paused(conn, "outreach") is None
    assert not store.record_qa(conn, "b", True, [])
    assert not store.record_qa(conn, "c", False, ["x"])  # a pass in between breaks the run


# --- reply detection -------------------------------------------------------


def test_reply_marks_the_lead_replied_without_storing_the_body(conn, monkeypatch):
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = imap_env(
        monkeypatch,
        [
            reply_message(lead["email"], when="2026-10-26T14:00:00+08:00", body="Thanks, this is useful. Can we talk on Thursday?"),
            reply_message("someone@else.sg", when="2026-10-26T14:05:00+08:00", body="Unrelated"),
        ],
    )
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    summary = sync.run(conn)
    assert "1 reply detected" in summary
    assert fake.readonly is True and all("PEEK" in spec for spec in fake.fetch_specs)
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead["lead_id"],)) == "replied"
    assert suppression.is_suppressed(conn, lead["email"]) is None
    columns = [r["name"] for r in db.rows(conn, "PRAGMA table_info(outreach_replies)")]
    assert columns == ["id", "lead_id", "contact_id", "message_key", "received_at", "unsubscribe", "detected_at"]
    assert any("**Reply** from alderlogistics.sg" in p["content"] for p in outbox("outreach-replies"))
    assert "0 replies detected" in sync.run(conn)  # the same reply is counted once
    assert db.scalar(conn, "SELECT count(*) FROM outreach_replies") == 1


@pytest.mark.parametrize("body", ["Please remove us from your list.", "STOP", "unsubscribe"])
def test_reply_asking_to_stop_suppresses(conn, monkeypatch, body):
    seeded, _ = live_sends(conn, monkeypatch, 1)
    imap_env(monkeypatch, [reply_message(seeded[0]["email"], when="2026-10-26T15:00:00+08:00", body=body)])
    sync.run(conn)
    assert suppression.is_suppressed(conn, seeded[0]["email"]) == "unsubscribe"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded[0]["lead_id"],)) == "unsubscribed"


def test_quoted_footer_and_auto_replies_do_not_count(conn, monkeypatch):
    seeded, _ = live_sends(conn, monkeypatch, 2)
    quoted = (
        "Sounds interesting, call me next week.\n\nOn Mon, 26 Oct 2026 at 10:00, Ting Yu wrote:\n"
        "> Not interested? Unsubscribe here: https://jurasolutions.sg/unsubscribe?t=x, or reply \"unsubscribe\".\n"
    )
    imap_env(
        monkeypatch,
        [
            reply_message(seeded[0]["email"], when="2026-10-26T15:00:00+08:00", body=quoted),
            reply_message(seeded[1]["email"], when="2026-10-26T15:00:00+08:00", body="I am away. Please remove...", subject="Out of office", auto="auto-replied"),
        ],
    )
    sync.run(conn)
    assert suppression.is_suppressed(conn, seeded[0]["email"]) is None
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded[0]["lead_id"],)) == "replied"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded[1]["lead_id"],)) == "contacted"


def test_reply_detection_is_off_without_secrets(conn):
    assert replies.check(conn) is None
    assert "reply detection off" in sync.run(conn)


# --- follow-ups ------------------------------------------------------------


FOLLOW_UP = {
    "kind": "follow_up",
    "subject": "A short follow-up on free tools",
    "body": "Hi again,\n\nFollowing up on my note last week about delivery orders. The free tools are all at "
    "jurasolutions.sg/apps, and a reply is all it takes to tell me how orders work for your team.",
}


def test_follow_up_only_after_five_business_days_with_reply_detection(conn, monkeypatch):
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead_id = seeded[0]["lead_id"]
    at(monkeypatch, "2026-11-02T09:00:00+08:00")
    assert sync.follow_ups_due(conn) == []  # no reply detection yet
    imap_env(monkeypatch, [])
    at(monkeypatch, "2026-10-30T09:00:00+08:00")  # Friday: 4 business days
    assert sync.follow_ups_due(conn) == []
    with pytest.raises(queue_mod.QueueError, match="only 4 business days"):
        queue_mod.queue(conn, lead_id, FOLLOW_UP)
    at(monkeypatch, "2026-11-02T09:00:00+08:00")  # Monday: 5 business days
    due = sync.follow_ups_due(conn)
    assert [d["lead_id"] for d in due] == [lead_id] and due[0]["first_subject"].startswith("A free delivery order maker")
    queued = queue_mod.queue(conn, lead_id, FOLLOW_UP)
    assert queued.status == "queued" and queued.send_after == "2026-11-02"
    at(monkeypatch, "2026-11-02T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("sent message")
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,)) == "followed_up"
    with pytest.raises(queue_mod.QueueError):
        queue_mod.queue(conn, lead_id, FOLLOW_UP)
    assert sync.follow_ups_due(conn) == []


def test_reply_before_the_follow_up_cancels_it(conn, monkeypatch):
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    fake = imap_env(monkeypatch, [])
    at(monkeypatch, "2026-11-02T09:00:00+08:00")
    queued = queue_mod.queue(conn, lead["lead_id"], FOLLOW_UP)
    fake.messages.append(reply_message(lead["email"], when="2026-11-02T09:30:00+08:00", body="Yes, tell me more."))
    at(monkeypatch, "2026-11-02T10:00:00+08:00")
    send.send_due(conn)
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (queued.message_id,)) == "cancelled"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead["lead_id"],)) == "replied"


def test_follow_ups_due_command(isolated):
    result = CliRunner().invoke(cli, ["outreach", "follow-ups-due"])
    assert "follow-ups are off" in result.output


# --- retention -------------------------------------------------------------


def test_leads_that_never_replied_are_deleted_after_24_months(conn, monkeypatch):
    at(monkeypatch, "2024-09-02T08:00:00+08:00")
    old = seed(conn, 1)
    kept = seed(conn, 2)
    live_ready(monkeypatch)
    fake_d1(monkeypatch, [])
    fake_resend(monkeypatch)
    at(monkeypatch, "2024-09-02T10:00:00+08:00")
    send.send_due(conn)
    conn.execute(
        "INSERT INTO outreach_replies (lead_id, contact_id, message_key, received_at, unsubscribe, detected_at) "
        "VALUES (?, NULL, 'k', '2024-09-03T10:00:00+08:00', 0, '2024-09-03T10:00:00+08:00')",
        (kept["lead_id"],),
    )
    at(monkeypatch, "2026-10-26T16:45:00+08:00")
    result = sync.retention(conn)
    assert result["leads_deleted"] == 1
    assert db.one(conn, "SELECT 1 FROM leads WHERE id = ?", (old["lead_id"],)) is None
    assert db.scalar(conn, "SELECT count(*) FROM contacts WHERE lead_id = ?", (old["lead_id"],)) == 0
    assert db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE lead_id = ?", (old["lead_id"],)) == 0
    assert db.one(conn, "SELECT 1 FROM leads WHERE id = ?", (kept["lead_id"],))
    assert db.one(conn, "SELECT 1 FROM contacted_domains WHERE domain = 'alderlogistics.sg'")
    # the company is still never approached again
    again = add(conn, lead_data(1))
    assert again.status == "rejected" and "contacted before" in again.reasons[0]


# --- digest ----------------------------------------------------------------


def test_digest_figures(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seed(conn, 1)
    seed(conn, 2)
    send.send_due(conn)
    suppression.add(conn, email="info@birchlogistics.sg", reason="unsubscribe", source="d1:unsubscribe-link")
    part = outreach.digest(conn, timeutil.today_str())
    figures = part["figures"]
    assert figures["emails_shadow"] == 1 and figures["emails_sent"] == 0 and figures["unsubscribes"] == 1
    assert figures["emails_queued"] == 1 and figures["replies"] == 0 and figures["bounces"] == 0
    assert "1 shadow email (not sent)" in part["lines"][0] and "1 shadow email" in part["brief"]


def test_full_digest_includes_scout_and_outreach(isolated, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    with db.session() as c:
        seed(c, 1)
        send.send_due(c)
    result = CliRunner().invoke(cli, ["digest", "--no-post"])
    assert result.exit_code == 0
    assert "Scout: 1 new lead" in result.output and "Outreach (shadow)" in result.output


def test_suppress_command_cancels_the_queue(isolated, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    with db.session() as c:
        seeded = seed(c, 1)
    result = CliRunner().invoke(cli, ["outreach", "suppress", "alderlogistics.sg"])
    assert result.exit_code == 0 and "cancelled 1" in result.output
    with db.session() as c:
        assert suppression.is_suppressed(c, seeded["email"]) == "manual (domain)"
        assert db.scalar(c, "SELECT status FROM leads WHERE id = ?", (seeded["lead_id"],)) == "suppressed"
