"""What goes out is byte for byte what the claimed approval covers (code review 06: B1, Sp1, Sec2).

- B1: the claim re-reads the email inside its transaction and checks its hash against the
  approval before Resend is called; an email read stale by the run is never sent.
- Sp1: a claimed send that may have reached Resend is retried only inside Resend's 24-hour
  idempotency window; after that the email is marked uncertain and Ting Yu is alerted.
- Sec2: the hash covers the exact bytes, so two drafts that only normalise alike don't match.
"""

import httpx

from jura_growth import approvals, caps, db
from jura_growth.agents.outreach import approval, send

from test_scout_support import at, decide, fake_resend, live_ready, outbox, scout_env, seed  # noqa: F401

TUESDAY_10 = "2026-11-10T10:00:00+08:00"
UNAPPROVED = "An unapproved line."


def approved(conn, monkeypatch):
    live_ready(monkeypatch)
    at(monkeypatch, "2026-11-10T09:00:00+08:00")
    seeded = seed(conn, 1)
    request = approval.live_request(conn, seeded["message_id"])
    assert decide(conn, request, "approve", monkeypatch).answer == "recorded"
    return seeded, request


def stale_read(monkeypatch, change):
    """`due()` returns rows as they read before an out-of-band write was put back."""
    real = send.due

    def due(conn, **kwargs):
        return [change(dict(row)) for row in real(conn, **kwargs)]

    monkeypatch.setattr(send, "due", due)


def with_unapproved_line(row):
    row["draft_body"] = row["draft_body"] + "\n\n" + UNAPPROVED
    return row


def bodies(sent):
    return [__import__("json").loads(r.content)["text"] for r in sent]


def status_of(conn, message_id):
    return db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message_id,))


def test_a_stale_read_of_the_draft_never_sends_the_unapproved_text(conn, monkeypatch):
    """B1, the reviewer's repro: the run read a different draft than the one approved."""
    seeded, request = approved(conn, monkeypatch)
    stale_read(monkeypatch, with_unapproved_line)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, TUESDAY_10)
    result = send.send_due(conn)
    assert sent == [] and "isn't sent" in (result.summary or result.note)
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'approval.used'") == 0


def test_a_stale_read_on_a_retry_never_sends_the_unapproved_text(conn, monkeypatch):
    """B1 on the retry path: the claim already used, the second attempt read stale."""
    seeded, request = approved(conn, monkeypatch)
    sent = fake_resend(monkeypatch, lambda r: httpx.Response(500, json={"message": "internal"}))
    at(monkeypatch, TUESDAY_10)
    assert "will retry" in send.send_due(conn).summary
    stale_read(monkeypatch, with_unapproved_line)
    sent2 = fake_resend(monkeypatch)
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    send.send_due(conn)
    assert len(sent) == 1 and sent2 == []
    assert all(UNAPPROVED not in text for text in bodies(sent))
    assert status_of(conn, seeded["message_id"]) == "queued"


def test_a_stale_recipient_is_never_sent_to(conn, monkeypatch):
    seeded, request = approved(conn, monkeypatch)
    real = send.queue.recipient
    calls = []

    def recipient(conn_, lead_id):
        lead, row = real(conn_, lead_id)
        calls.append(1)
        if len(calls) == 1:  # the run's first read, before the claim
            row = {**row, "email": "someone.else@alderlogistics.sg"}
        return lead, row

    monkeypatch.setattr(send.queue, "recipient", recipient)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, TUESDAY_10)
    send.send_due(conn)
    assert sent == [] and approvals.get(conn, request.id).used_at is None


def test_the_email_sent_is_the_one_the_claim_checked(conn, monkeypatch):
    seeded, request = approved(conn, monkeypatch)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, TUESDAY_10)
    assert send.send_due(conn).summary.startswith("sent message")
    message = db.one(conn, "SELECT subject, draft_body, body_text FROM outreach_messages WHERE id = ?", (seeded["message_id"],))
    payload = __import__("json").loads(sent[0].content)
    assert approval.content_hash_of(payload["to"][0], payload["subject"], message["draft_body"]) == request.content_hash
    assert payload["text"] == message["body_text"] and payload["text"].startswith(message["draft_body"])


# --- Sec2: exact bytes ------------------------------------------------------------------


def test_drafts_that_only_normalise_alike_do_not_match(conn, monkeypatch):
    """The reviewer's repro: an NFD body against an NFC approval."""
    seeded, request = approved(conn, monkeypatch)
    conn.execute("UPDATE outreach_messages SET draft_body = replace(draft_body, 'Hi there', 'Café there') WHERE id = ?",
                 (seeded["message_id"],))
    approval.raise_due(conn)
    nfc = approval.live_request(conn, seeded["message_id"])
    conn.execute("UPDATE outreach_messages SET draft_body = replace(draft_body, 'Café', 'Café') WHERE id = ?",
                 (seeded["message_id"],))
    kind = approvals.kinds()[approval.KIND].kind
    assert approvals.content_hash(kind.content(conn, nfc.subject)) != nfc.content_hash


# --- Sp1: the retry window --------------------------------------------------------------


def crashed_after_resend(conn, monkeypatch):
    seeded, request = approved(conn, monkeypatch)
    sent = fake_resend(monkeypatch)

    def dies(*args, **kwargs):
        raise SystemExit("the Mac lost power")

    real_mark = send._mark_sent
    monkeypatch.setattr(send, "_mark_sent", dies)
    at(monkeypatch, TUESDAY_10)
    try:
        send.send_due(conn)
    except SystemExit:
        pass
    monkeypatch.setattr(send, "_mark_sent", real_mark)
    assert len(sent) == 1 and approvals.get(conn, request.id).used_at == TUESDAY_10
    return seeded, request, sent


def test_the_window_closes_before_resends_24_hours(conn, monkeypatch):
    seeded, request, sent = crashed_after_resend(conn, monkeypatch)
    assert caps.OUTREACH_RETRY_WINDOW_HOURS < 24
    at(monkeypatch, "2026-11-11T09:30:00+08:00")  # 23h30m after the claim: past the window
    result = send.send_due(conn)
    assert len(sent) == 1 and status_of(conn, seeded["message_id"]) == "uncertain"
    assert "may already have gone out" in (result.summary or result.note)


def test_inside_the_window_the_retry_goes_under_the_same_key(conn, monkeypatch):
    seeded, request, sent = crashed_after_resend(conn, monkeypatch)
    at(monkeypatch, "2026-11-10T16:30:00+08:00")
    assert send.send_due(conn).summary.startswith("sent message")
    assert [r.headers["idempotency-key"] for r in sent] == [f"jura-outreach-{seeded['message_id']}"] * 2


def test_past_the_window_the_email_is_uncertain_alerted_and_never_retried(conn, monkeypatch):
    seeded, request, sent = crashed_after_resend(conn, monkeypatch)
    from jura_growth import pause

    pause.pause(conn, "outreach", "Resend quota", notify=False)
    at(monkeypatch, "2026-11-12T10:00:00+08:00")  # two days later, after a resume
    pause.resume(conn, "outreach")
    send.send_due(conn)
    at(monkeypatch, "2026-11-12T10:10:00+08:00")
    send.send_due(conn)
    assert len(sent) == 1
    row = db.one(conn, "SELECT status, error FROM outreach_messages WHERE id = ?", (seeded["message_id"],))
    assert row["status"] == "uncertain" and "fresh approval" in row["error"]
    assert any("may already have gone out" in p["content"] for p in outbox("alerts"))
    assert approval.live_request(conn, seeded["message_id"]) is None
    assert approval.without_request(conn) == []
