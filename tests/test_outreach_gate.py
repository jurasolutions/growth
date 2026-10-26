"""The outreach gate (MC SC8, §5.8; ticket 06): no live email without a claimed approval.

Requests track capacity (A14): they are raised only in live mode, only for emails due today,
and only up to today's remaining quota, counting the pending and approved-but-unused requests
already open. `send-due` in live mode considers only approved emails.
"""

from datetime import timedelta

import pytest

from jura_growth import db, timeutil
from jura_growth.agents.outreach import approval, queue as queue_mod, requeue, send, store

from test_scout_support import (  # noqa: F401
    at,
    configure,
    decide,
    fake_resend,
    live_ready,
    outreach_requests,
    scout_env,
    seed,
)

TUESDAY = "2026-11-10"


def status_of(conn, message_id):
    return db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message_id,))


def open_requests(conn) -> int:
    return len([a for a in outreach_requests(conn) if a.live])


def warm_up_day_3(conn, monkeypatch, day=TUESDAY):
    """Live, nothing sent today, warm-up day 3 (cap 5)."""
    live_ready(monkeypatch)
    at(monkeypatch, f"{day}T09:05:00+08:00")
    first = timeutil.now_sgt() - timedelta(days=2)
    store.set_state(conn, "first_live_send_at", timeutil.stamp(first))
    assert send.daily_cap(conn, "live")[0] == 5 and send.quota(conn, "live")[0] == 5


def test_shadow_mode_raises_nothing(conn, monkeypatch):
    """AC-M8.10, first half: shadow raises and claims nothing; shadow recording works as today."""
    at(monkeypatch, f"{TUESDAY}T09:05:00+08:00")
    seeded = [seed(conn, n) for n in (1, 2)]
    at(monkeypatch, f"{TUESDAY}T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    assert approval.raise_due(conn) == []
    assert outreach_requests(conn) == []
    assert status_of(conn, seeded[0]["message_id"]) == "shadow"


def test_queue_raises_requests_only_up_to_todays_quota(conn, monkeypatch):
    """AC-M8.2 (G35): 15 first emails due today on warm-up day 3, so 5 requests."""
    warm_up_day_3(conn, monkeypatch)
    queued = [seed(conn, n) for n in range(1, 16)]
    requests = outreach_requests(conn)
    assert len(requests) == 5 and all(r.status == "pending" for r in requests)
    assert [approval.message_id(r.subject) for r in requests] == [q["message_id"] for q in queued[:5]]
    assert all(status_of(conn, q["message_id"]) == "queued" for q in queued)

    at(monkeypatch, f"{TUESDAY}T09:30:00+08:00")
    sent = fake_resend(monkeypatch)
    result = send.send_due(conn)
    assert result.summary is None and sent == []
    assert "5 waiting for a decision" in result.note and "10 waiting for a request slot" in result.note
    assert len(outreach_requests(conn)) == 5


def test_sends_and_skips_open_room_for_more_requests(conn, monkeypatch):
    """AC-M8.2: 3 of the 5 sent and 2 skipped, so 2 more are raised; open requests never pass
    today's remaining quota (G35)."""
    warm_up_day_3(conn, monkeypatch)
    [seed(conn, n) for n in range(1, 16)]
    first_five = outreach_requests(conn)
    for request in first_five[:3]:
        decide(conn, request, "approve", monkeypatch)
    for request in first_five[3:]:
        decide(conn, request, "skip", monkeypatch)
    sent = fake_resend(monkeypatch)
    for slot in ("09:30", "09:40", "09:50"):
        at(monkeypatch, f"{TUESDAY}T{slot}:00+08:00")
        assert send.send_due(conn).summary.startswith("sent message")
        assert open_requests(conn) <= send.quota(conn, "live")[0]
    assert len(sent) == 3
    more = outreach_requests(conn)[5:]
    assert len(more) == 2 and all(r.status == "pending" for r in more)
    assert send.quota(conn, "live")[0] == 2 and open_requests(conn) == 2


def test_live_send_due_sends_nothing_while_the_request_is_pending(conn, monkeypatch):
    """AC-M8.1."""
    warm_up_day_3(conn, monkeypatch)
    message = seed(conn, 1)["message_id"]
    [pending] = outreach_requests(conn)
    assert pending.status == "pending"
    sent = fake_resend(monkeypatch)
    at(monkeypatch, f"{TUESDAY}T10:00:00+08:00")
    result = send.send_due(conn)
    assert result.summary is None and sent == []
    assert status_of(conn, message) == "queued" and pending.status == "pending"


def follow_up(conn, lead_id: int, send_after: str) -> int:
    first = db.one(conn, "SELECT * FROM outreach_messages WHERE lead_id = ? AND kind = 'first'", (lead_id,))
    return conn.execute(
        "INSERT INTO outreach_messages (lead_id, contact_id, kind, tool_slug, subject, draft_body, body_text, body_html, "
        "send_after, queued_at, status) VALUES (?, ?, 'follow_up', ?, ?, ?, ?, ?, ?, ?, 'queued')",
        (lead_id, first["contact_id"], first["tool_slug"], "Re: " + first["subject"], "A short follow-up. " + first["draft_body"],
         first["body_text"], first["body_html"], send_after, timeutil.stamp()),
    ).lastrowid


def test_a_follow_up_raises_no_request_until_its_day(conn, monkeypatch):
    """AC-M8.3: queued five business days ahead (the clock stepped day by day, holidays included)."""
    at(monkeypatch, "2026-11-05T08:00:00+08:00")
    seeded = seed(conn, 1)
    conn.execute("UPDATE outreach_messages SET status = 'sent', mode = 'live', sent_at = ? WHERE id = ?",
                 (timeutil.stamp(), seeded["message_id"]))
    later = follow_up(conn, seeded["lead_id"], "2026-11-13")  # Fri 6, Tue 10, Wed 11, Thu 12, Fri 13
    live_ready(monkeypatch)
    fake_resend(monkeypatch)
    for day in ("2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"):
        at(monkeypatch, f"{day}T10:00:00+08:00")
        send.send_due(conn)
        approval.raise_due(conn)
        assert outreach_requests(conn) == [], day
    at(monkeypatch, "2026-11-13T10:00:00+08:00")
    send.send_due(conn)
    [request] = outreach_requests(conn)
    assert request.subject == approval.subject_of(later) and request.status == "pending"


def test_requeue_shadow_in_live_mode_raises_requests_only_up_to_todays_quota(conn, monkeypatch):
    """AC-M8.13 (G35), from Terminal: 40 shadow emails requeued, 5 requests on warm-up day 1."""
    seeded = []
    for day, numbers in (("2026-11-03", range(1, 16)), ("2026-11-04", range(16, 31)), ("2026-11-05", range(31, 41))):
        at(monkeypatch, f"{day}T08:00:00+08:00")  # the scout adds at most 15 leads a day
        seeded += [seed(conn, n) for n in numbers]
    for item in seeded:
        conn.execute("UPDATE outreach_messages SET status = 'shadow', mode = 'shadow', sent_at = ? WHERE id = ?",
                     (timeutil.stamp(), item["message_id"]))
        store.set_lead_status(conn, [item["lead_id"]], "shadow_sent")
    at(monkeypatch, f"{TUESDAY}T09:00:00+08:00")
    live_ready(monkeypatch)
    plan = requeue.requeue_shadow(conn)
    assert len(plan.requeued) == 40
    requests = outreach_requests(conn)
    assert len(requests) == 5 == send.quota(conn, "live")[0]
    assert [approval.message_id(r.subject) for r in requests] == [i["message_id"] for i in plan.requeued[:5]]
    assert plan.requests == [r.id for r in requests]


def test_a_paused_outreach_raises_nothing(conn, monkeypatch):
    warm_up_day_3(conn, monkeypatch)
    from jura_growth import pause

    pause.pause(conn, "outreach", "by hand", notify=False)
    seed(conn, 1)
    assert outreach_requests(conn) == []


def test_queue_says_whether_it_raised_a_request(conn, monkeypatch):
    warm_up_day_3(conn, monkeypatch)
    configure(monkeypatch, mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg", send={"per_day": 1})
    first = seed(conn, 1)
    second = seed(conn, 2)
    lead = db.one(conn, "SELECT id FROM leads WHERE id = ?", (first["lead_id"],))
    assert lead
    [request] = outreach_requests(conn)
    assert approval.message_id(request.subject) == first["message_id"]
    assert approval.live_request(conn, first["message_id"]).id == request.id
    assert approval.live_request(conn, second["message_id"]) is None


@pytest.mark.parametrize("command", ["queue", "send-due", "requeue-shadow"])
def test_no_request_is_raised_while_the_buttons_are_off(conn, monkeypatch, command):
    """AC-M8.11: while "approval buttons not set up" shows, nothing raises a request."""
    at(monkeypatch, f"{TUESDAY}T09:05:00+08:00")
    seed(conn, 1)
    live_ready(monkeypatch, approval_buttons=False)
    if command == "queue":
        seed(conn, 2)
    elif command == "send-due":
        at(monkeypatch, f"{TUESDAY}T10:00:00+08:00")
        send.send_due(conn)
    else:
        with pytest.raises(requeue.RequeueError):
            requeue.requeue_shadow(conn)
    assert outreach_requests(conn) == []


def test_queue_result_names_the_request(conn, monkeypatch):
    warm_up_day_3(conn, monkeypatch)
    lead = seed(conn, 1, queue=False)
    from test_scout_support import body_for

    result = queue_mod.queue(conn, lead["lead_id"], {"subject": "A free delivery order maker for Alder Logistics",
                                                      "body": body_for("Alder Logistics"), "tool": "delivery-order-maker"})
    assert result.status == "queued" and result.approval == outreach_requests(conn)[0].id


def test_the_spacing_probability_counts_approved_emails_only(conn, monkeypatch):
    """AC-M8.12: 9 queued, 2 approved, 5 left today and 43 slots at 09:30, so the chance is
    2/43 (not 5/43): a draw of 0.07 sends nothing."""
    at(monkeypatch, f"{TUESDAY}T08:00:00+08:00")
    [seed(conn, n) for n in range(1, 10)]
    live_ready(monkeypatch)
    approval.raise_due(conn)
    for request in outreach_requests(conn, "pending")[:2]:
        decide(conn, request, "approve", monkeypatch)
    sent = fake_resend(monkeypatch)
    monkeypatch.setattr(send, "chance", lambda: 0.07)
    at(monkeypatch, f"{TUESDAY}T09:30:00+08:00")
    result = send.send_due(conn)
    assert result.summary is None and "spacing: not this slot (5% chance" in result.note and sent == []
    monkeypatch.setattr(send, "chance", lambda: 0.04)
    assert send.send_due(conn).summary.startswith("sent message") and len(sent) == 1
