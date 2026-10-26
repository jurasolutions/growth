"""What Ting Yu's answer, or his silence, does to an outreach email (MC §5.7, the
`outreach-email` row; AC-M8.4 to AC-M8.8 and AC-M8.10; ticket 06).

- Skip: the message is cancelled ("skipped by Ting Yu") and the lead becomes `declined_by_ty`,
  a final status. A skip wins until the claim; after the send it answers "already sent".
- Unanswered past the decide-by: cancelled ("not approved in time"); the lead stays new.
- Approved but never reached by the limits, past the use-by: cancelled ("approved but the
  limits didn't reach it"); the record is expired with `used_at` empty; the lead stays new.
- A cancellation (an unsubscribe, a bounce, a reply) makes the content gone, so the request is
  superseded at the next read or claim, and the card says why in the lead's own terms.
"""

import pytest

from jura_growth import approvals, cards, db, timeutil
from jura_growth.agents.outreach import approval, queue as queue_mod, send, store, sync

from test_outreach_sync import D1, d1_row
from test_scout_support import (  # noqa: F401
    at,
    configure,
    decide,
    fake_d1,
    fake_resend,
    live_ready,
    outreach_requests,
    scout_env,
    seed,
)

FRIDAY_0912 = "2026-11-06T09:12:00+08:00"


def now_at(monkeypatch, moment):
    at(monkeypatch, moment)
    return timeutil.now_sgt()


def lead_status(conn, lead_id):
    return db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,))


def message_row(conn, message_id):
    return dict(db.one(conn, "SELECT status, error FROM outreach_messages WHERE id = ?", (message_id,)))


def raised_friday(conn, monkeypatch):
    """Lead 1's first email, queued and its request raised in live mode on Fri 6 Nov, 09:12."""
    live_ready(monkeypatch)
    at(monkeypatch, FRIDAY_0912)
    seeded = seed(conn, 1)
    [request] = outreach_requests(conn)
    assert request.decide_by == "2026-11-10T16:30:00+08:00"
    return seeded, request


def approved_tuesday(conn, monkeypatch):
    seeded, request = raised_friday(conn, monkeypatch)
    at(monkeypatch, "2026-11-10T10:00:00+08:00")
    assert decide(conn, request, "approve", monkeypatch).answer == "recorded"
    assert approvals.get(conn, request.id).use_by == "2026-11-13T16:30:00+08:00"
    return seeded, request


# --- silence ------------------------------------------------------------------------


def test_an_unanswered_request_expires_after_its_decide_by_and_the_lead_stays_new(conn, monkeypatch):
    """AC-M8.4 (G4a, G5)."""
    seeded, request = raised_friday(conn, monkeypatch)
    approvals.expire_due(conn, now_at(monkeypatch, "2026-11-10T16:29:59+08:00"))
    assert approvals.get(conn, request.id).status == "pending"
    approvals.expire_due(conn, now_at(monkeypatch, "2026-11-10T16:31:00+08:00"))
    expired = approvals.get(conn, request.id)
    assert expired.status == "expired" and expired.close_reason == "not approved in time"
    assert message_row(conn, seeded["message_id"]) == {"status": "cancelled", "error": "not approved in time"}
    assert lead_status(conn, seeded["lead_id"]) == "new"


def test_send_due_never_sends_an_unanswered_request_at_its_decide_by(conn, monkeypatch):
    """AC-M8.4 through send-due, before any lapse is written."""
    seeded, request = raised_friday(conn, monkeypatch)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T16:30:00+08:00")
    assert send.send_due(conn).summary is None and sent == []
    assert decide(conn, request, "approve", monkeypatch).answer == "expired"
    assert message_row(conn, seeded["message_id"])["status"] == "cancelled"


def test_an_approval_the_limits_never_reached_lapses_at_its_use_by(conn, monkeypatch):
    """AC-M8.5 (G4b, G5)."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    approvals.expire_due(conn, now_at(monkeypatch, "2026-11-13T16:29:59+08:00"))
    assert approvals.get(conn, request.id).status == "approved"
    approvals.expire_due(conn, now_at(monkeypatch, "2026-11-13T16:31:00+08:00"))
    lapsed = approvals.get(conn, request.id)
    assert lapsed.status == "expired" and lapsed.used_at is None
    assert message_row(conn, seeded["message_id"]) == {"status": "cancelled", "error": "approved but the limits didn't reach it"}
    assert lead_status(conn, seeded["lead_id"]) == "new"


def test_an_approval_is_still_claimable_one_second_before_its_use_by(conn, monkeypatch):
    seeded, request = approved_tuesday(conn, monkeypatch)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-13T16:29:59+08:00")
    assert send.send_due(conn).summary.startswith(f"sent message {seeded['message_id']}")
    assert len(sent) == 1 and approvals.get(conn, request.id).used_at == "2026-11-13T16:29:59+08:00"


def test_a_lapse_never_reopens_a_lead_that_moved_on(conn, monkeypatch):
    seeded, request = approved_tuesday(conn, monkeypatch)
    conn.execute("UPDATE leads SET status = 'replied' WHERE id = ?", (seeded["lead_id"],))
    approvals.expire_due(conn, now_at(monkeypatch, "2026-11-13T16:31:00+08:00"))
    assert lead_status(conn, seeded["lead_id"]) == "replied"


# --- skip ---------------------------------------------------------------------------


def test_a_skip_cancels_the_email_and_closes_the_lead_for_good(conn, monkeypatch):
    """AC-M8.6: the lead becomes declined_by_ty, a final status."""
    seeded, request = raised_friday(conn, monkeypatch)
    assert decide(conn, request, "skip", monkeypatch).answer == "recorded"
    assert message_row(conn, seeded["message_id"]) == {"status": "cancelled", "error": "skipped by Ting Yu"}
    assert lead_status(conn, seeded["lead_id"]) == "declined_by_ty" and "declined_by_ty" in store.FINAL_LEAD_STATUSES
    with pytest.raises(queue_mod.QueueError, match="declined_by_ty"):
        queue_mod.queue(conn, seeded["lead_id"], {"subject": "Again", "body": "Hi there", "tool": "quote-builder"})


def test_a_skip_after_approval_wins_until_the_claim(conn, monkeypatch):
    """AC-M8.7, first half (G17)."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    assert decide(conn, request, "skip", monkeypatch).answer == "recorded"
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    send.send_due(conn)
    assert sent == [] and message_row(conn, seeded["message_id"])["status"] == "cancelled"
    assert lead_status(conn, seeded["lead_id"]) == "declined_by_ty"


def test_a_skip_after_the_send_answers_already_sent(conn, monkeypatch):
    """AC-M8.7, second half (G18)."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T10:40:00+08:00")
    assert send.send_due(conn).summary.startswith("sent message")
    used = approvals.get(conn, request.id)
    answer = decide(conn, used, "skip", monkeypatch)
    assert answer.answer == "already-used"
    assert "already sent at 10:40" in answer.text and "can't be undone" in answer.text
    assert approvals.get(conn, request.id) == used


# --- a cancellation supersedes lazily (AC-M8.8) ----------------------------------------


def unsubscribe_at_1645(conn, monkeypatch, seeded):
    table = D1()
    table.rows.append(d1_row(seeded["email"], "unsubscribe", source="unsubscribe-link", created="2026-11-10 16:44:00"))
    fake_d1(monkeypatch, table)
    at(monkeypatch, "2026-11-10T16:45:00+08:00")
    assert sync.sync_suppression(conn).ok


def test_an_unsubscribe_supersedes_an_approved_email_at_the_next_read(conn, monkeypatch):
    """AC-M8.8 (G25), and the card's note."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    unsubscribe_at_1645(conn, monkeypatch, seeded)
    assert approvals.get(conn, request.id).status == "approved"  # nothing hooks the cancellation itself
    approvals.expire_due(conn)
    superseded = approvals.get(conn, request.id)
    assert superseded.status == "superseded" and superseded.used_at is None
    assert cards.status_line(conn, superseded) == "Superseded: lead unsubscribed"
    assert [a for a in outreach_requests(conn) if a.live] == []


def test_an_unsubscribe_supersedes_an_approved_email_at_the_next_send_due(conn, monkeypatch):
    """AC-M8.8: the next live send-due reads its own open requests first."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    unsubscribe_at_1645(conn, monkeypatch, seeded)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-11T09:30:00+08:00")
    send.send_due(conn)
    assert sent == [] and approvals.get(conn, request.id).status == "superseded"


@pytest.mark.parametrize(
    "lead, message, note",
    [
        ("bounced", "cancelled", "lead bounced"),
        ("replied", "cancelled", "lead replied"),
        ("complained", "cancelled", "lead complained"),
        ("suppressed", "skipped", "address suppressed"),
        ("do_not_contact", "skipped", "company on the do-not-contact list"),
        ("queued", "dropped", "dropped by the brand check at send time"),
    ],
)
def test_the_supersede_note_reads_the_items_own_state(conn, monkeypatch, lead, message, note):
    seeded, request = approved_tuesday(conn, monkeypatch)
    conn.execute("UPDATE outreach_messages SET status = ? WHERE id = ?", (message, seeded["message_id"]))
    conn.execute("UPDATE leads SET status = ? WHERE id = ?", (lead, seeded["lead_id"]))
    approvals.expire_due(conn)
    assert cards.status_line(conn, approvals.get(conn, request.id)) == f"Superseded: {note}"


def test_a_changed_email_says_so_and_names_the_new_request(conn, monkeypatch):
    seeded, request = approved_tuesday(conn, monkeypatch)
    conn.execute("UPDATE outreach_messages SET subject = subject || '.' WHERE id = ?", (seeded["message_id"],))
    approval.raise_due(conn)
    newer = outreach_requests(conn)[-1]
    assert newer.id != request.id and newer.status == "pending"
    assert cards.status_line(conn, approvals.get(conn, request.id)) == f"Superseded: the email changed; see {newer.id}"


# --- shadow (AC-M8.10) -----------------------------------------------------------------


def test_an_approved_email_shadow_sent_after_a_switch_back_keeps_its_approval_until_its_use_by(conn, monkeypatch):
    """AC-M8.10, second half (G20)."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    configure(monkeypatch, mode="shadow", legal_review_done=True, sending_domain="hello.jurasolutions.sg")
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    approvals.expire_due(conn)
    kept = approvals.get(conn, request.id)
    assert kept.status == "approved" and kept.used_at is None
    approvals.expire_due(conn, now_at(monkeypatch, "2026-11-13T16:30:00+08:00"))
    lapsed = approvals.get(conn, request.id)
    assert lapsed.status == "expired" and lapsed.used_at is None
    assert message_row(conn, seeded["message_id"])["status"] == "shadow"
    assert lead_status(conn, seeded["lead_id"]) == "shadow_sent"


def test_shadow_mode_is_the_kinds_own_switch(conn, monkeypatch):
    """At the seam: in shadow mode `use()` refuses without claiming."""
    seeded, request = approved_tuesday(conn, monkeypatch)
    configure(monkeypatch, mode="shadow")
    with db.transaction(conn):
        with pytest.raises(approvals.NotApproved) as refused:
            approvals.use(conn, approval.KIND, approval.subject_of(seeded["message_id"]), run_id=None)
    assert refused.value.reason == "switched-off" and "shadow" in refused.value.text
    assert approvals.get(conn, request.id).used_at is None
