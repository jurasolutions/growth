"""`outreach requeue-shadow`: after the shadow trial, shadow emails become live
candidates that go through every send-time check again."""

import json

import pytest
from click.testing import CliRunner

from jura_growth import db, paths, suppression
from jura_growth.agents.outreach import compose, requeue, send, store
from jura_growth.agents.scout import registry
from jura_growth.cli import cli

from test_scout_support import approve_due, at, fake_resend, live_ready, scout_env, seed  # noqa: F401


def shadow_trial(conn, monkeypatch, count=3):
    """A shadow trial on Monday 26 October: `count` leads, each shadow-sent."""
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    seeded = [seed(conn, n) for n in range(1, count + 1)]
    for index in range(count):
        at(monkeypatch, f"2026-10-26T{10 + index}:00:00+08:00")
        assert send.send_due(conn).summary.startswith("SHADOW")
    return seeded


def go_live(monkeypatch):
    at(monkeypatch, "2026-10-29T09:00:00+08:00")  # Thursday, before the window
    live_ready(monkeypatch)
    return fake_resend(monkeypatch)


def status_of(conn, message_id):
    return db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message_id,))


def test_shadow_sends_never_add_to_contacted_domains(conn, monkeypatch):
    shadow_trial(conn, monkeypatch)
    assert db.scalar(conn, "SELECT count(*) FROM contacted_domains") == 0


def test_refused_unless_live_sending_is_ready(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 1)
    with pytest.raises(requeue.RequeueError, match="mode is 'shadow'"):
        requeue.requeue_shadow(conn)
    result = CliRunner().invoke(cli, ["outreach", "requeue-shadow"])
    assert result.exit_code == 1 and "live mode would refuse" in result.output and "legal_review_done" in result.output
    assert status_of(conn, seeded[0]["message_id"]) == "shadow"


def test_requeued_emails_send_live_with_a_live_token(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 3)
    shadow_text = db.scalar(conn, "SELECT body_text FROM outreach_messages WHERE id = ?", (seeded[0]["message_id"],))
    assert compose.NO_SECRET_SIG in shadow_text  # the trial ran without the secret
    sent = go_live(monkeypatch)

    plan = requeue.requeue_shadow(conn)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    assert [i["shadow_id"] for i in plan.requeued] == [s["message_id"] for s in seeded] and plan.skipped == []
    for item, original in zip(plan.requeued, seeded):
        new = db.one(conn, "SELECT * FROM outreach_messages WHERE id = ?", (item["message_id"],))
        assert new["status"] == "queued" and new["mode"] is None and new["sent_at"] is None
        assert new["requeued_from"] == original["message_id"] and new["send_after"] == "2026-10-29"
        assert compose.NO_SECRET_SIG not in new["body_text"]
        old = db.one(conn, "SELECT status, mode, sent_at FROM outreach_messages WHERE id = ?", (original["message_id"],))
        assert old["status"] == "requeued" and old["mode"] == "shadow" and old["sent_at"]  # the record stays
        assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (original["lead_id"],)) == "queued"

    at(monkeypatch, "2026-10-29T10:00:00+08:00")
    assert send.send_due(conn).summary == f"sent message {plan.requeued[0]['message_id']} to alderlogistics.sg"
    payload = json.loads(sent[0].content)
    token_url = compose.unsubscribe_url(seeded[0]["email"], "test-secret")
    assert token_url in payload["text"] and payload["headers"]["List-Unsubscribe"].startswith(f"<{token_url}>")
    assert db.one(conn, "SELECT 1 FROM contacted_domains WHERE domain = 'alderlogistics.sg'")
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded[0]["lead_id"],)) == "contacted"


def test_requeue_is_idempotent(conn, monkeypatch):
    shadow_trial(conn, monkeypatch, 2)
    go_live(monkeypatch)
    assert len(requeue.requeue_shadow(conn).requeued) == 2
    rows = db.scalar(conn, "SELECT count(*) FROM outreach_messages")
    again = requeue.requeue_shadow(conn)
    assert again.requeued == [] and again.skipped == []
    assert db.scalar(conn, "SELECT count(*) FROM outreach_messages") == rows
    assert "no shadow emails to requeue" in CliRunner().invoke(cli, ["outreach", "requeue-shadow"]).output


def test_suppressed_do_not_contact_and_contacted_companies_are_left_alone(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 5)
    go_live(monkeypatch)
    suppression.add(conn, email_hash_value=suppression.email_hash(seeded[0]["email"]), reason="unsubscribe", source="d1:unsubscribe-link")
    suppression.add(conn, domain=seeded[1]["domain"], reason="manual", source="test")
    (paths.inputs_dir() / "do-not-contact.csv").write_text("company,domain,reason\nCedar Logistics,,\n")
    store.record_contacted(conn, seeded[3]["domain"])  # contacted live some other way

    plan = requeue.requeue_shadow(conn)
    assert [i["lead_id"] for i in plan.requeued] == [seeded[4]["lead_id"]]
    reasons = {i["lead_id"]: i["reason"] for i in plan.skipped}
    assert "suppressed" in reasons[seeded[0]["lead_id"]] and "…@alderlogistics.sg" in reasons[seeded[0]["lead_id"]]
    assert "birchlogistics.sg is suppressed" in reasons[seeded[1]["lead_id"]]
    assert "do-not-contact" in reasons[seeded[2]["lead_id"]]
    assert "contacted before" in reasons[seeded[3]["lead_id"]]
    for item in seeded[:4]:
        assert status_of(conn, item["message_id"]) == "shadow"
        assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (item["lead_id"],)) == "shadow_sent"


def test_since_and_lead_filters(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 2)
    at(monkeypatch, "2026-10-27T08:00:00+08:00")
    later = seed(conn, 3)
    at(monkeypatch, "2026-10-27T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    go_live(monkeypatch)
    plan = requeue.requeue_shadow(conn, since="2026-10-27", dry_run=True)
    assert [i["lead_id"] for i in plan.requeued] == [later["lead_id"]]
    plan = requeue.requeue_shadow(conn, lead_ids=[seeded[1]["lead_id"]])
    assert [i["lead_id"] for i in plan.requeued] == [seeded[1]["lead_id"]]
    assert status_of(conn, seeded[0]["message_id"]) == "shadow"


def test_dry_run_changes_nothing(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 2)
    go_live(monkeypatch)
    before = db.rows(conn, "SELECT id, status FROM outreach_messages ORDER BY id")
    result = CliRunner().invoke(cli, ["outreach", "requeue-shadow", "--dry-run"])
    assert result.exit_code == 0 and "would requeue shadow message" in result.output and "2 would requeue" in result.output
    assert db.rows(conn, "SELECT id, status FROM outreach_messages ORDER BY id") == before
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded[0]["lead_id"],)) == "shadow_sent"


def test_email_that_no_longer_passes_the_gate_is_left_alone(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 1)
    go_live(monkeypatch)
    tools = [t for t in json.loads(registry.path().read_text()) if t["slug"] != "delivery-order-maker"]
    registry.path().write_text(json.dumps(tools))  # its tool was unpublished
    plan = requeue.requeue_shadow(conn)
    assert plan.requeued == [] and "brand check" in plan.skipped[0]["reason"]
    assert status_of(conn, seeded[0]["message_id"]) == "shadow"


def test_requeued_email_still_passes_every_send_time_check(conn, monkeypatch):
    seeded = shadow_trial(conn, monkeypatch, 2)
    sent = go_live(monkeypatch)
    plan = requeue.requeue_shadow(conn)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    suppression.add(conn, email=seeded[0]["email"], reason="unsubscribe", source="reply")  # after the requeue
    at(monkeypatch, "2026-10-29T10:00:00+08:00")
    result = send.send_due(conn)
    assert result.summary.startswith(f"sent message {plan.requeued[1]['message_id']}") and "skipped message" in result.summary
    assert status_of(conn, plan.requeued[0]["message_id"]) == "skipped"
    assert len(sent) == 1


def test_requeued_emails_count_against_the_live_warm_up(conn, monkeypatch):
    shadow_trial(conn, monkeypatch, 5)
    at(monkeypatch, "2026-10-27T08:00:00+08:00")
    for n in range(6, 9):
        seed(conn, n)
    for hour in (10, 11, 12):
        at(monkeypatch, f"2026-10-27T{hour}:00:00+08:00")
        send.send_due(conn)
    go_live(monkeypatch)
    assert len(requeue.requeue_shadow(conn).requeued) == 8
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    sends = 0
    for hour in range(9, 17):
        for minute in (0, 10, 20, 30, 40, 50):
            at(monkeypatch, f"2026-10-29T{hour:02d}:{minute:02d}:00+08:00")
            summary = send.send_due(conn).summary
            sends += bool(summary and summary.startswith("sent message"))
    assert sends == 5  # warm-up day 1, live
