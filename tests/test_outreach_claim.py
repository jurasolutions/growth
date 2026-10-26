"""The claim before Resend (MC §4.6 A6, §5.8; ticket 06).

- G8 / AC-M4.4: two connections claim one approval at once; exactly one succeeds.
- G23 / AC-M4.5: Resend accepted, the process died before the mark; the next slot retries under
  the same `Idempotency-Key` with no second claim, and only while the content still matches.
- G24: the completion write never re-checks a deadline.
- AC-M4.7: with the kind's plug-in not loaded, nothing is claimed or raised, and `expire_due()`
  leaves the record alone.
- X13: `JURA_GROWTH_RESEND_BASE_URL` points Resend at the UAT stub, and both refuse a data folder
  that isn't temporary. The suite never uses the stub for its own sends.
"""

import io
import threading
from contextlib import redirect_stdout

import httpx
import pytest

from jura_growth import approvals, db, paths
from jura_growth.agents import outreach
from jura_growth.agents.outreach import approval, send

from test_scout_support import at, decide, fake_resend, live_ready, outreach_requests, scout_env, seed  # noqa: F401

TUESDAY_10 = "2026-11-10T10:00:00+08:00"


def approved(conn, monkeypatch, n=1):
    live_ready(monkeypatch)
    at(monkeypatch, "2026-11-10T09:00:00+08:00")
    seeded = seed(conn, n)
    request = approval.live_request(conn, seeded["message_id"])
    assert decide(conn, request, "approve", monkeypatch).answer == "recorded"
    return seeded, request


def used_events(conn):
    return db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'approval.used'")


def test_two_connections_claiming_one_approval_at_once_one_wins(conn, monkeypatch):
    """G8, AC-M4.4."""
    seeded, request = approved(conn, monkeypatch)
    barrier, results = threading.Barrier(2), []

    def claim():
        other = db.connect()
        try:
            barrier.wait(5)
            with db.transaction(other):
                approvals.use(other, approval.KIND, request.subject, run_id=None)
            results.append("claimed")
        except approvals.NotApproved as refused:
            results.append(refused.reason)
        finally:
            other.close()

    threads = [threading.Thread(target=claim) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert sorted(results) == ["claimed", "used"]
    assert used_events(conn) == 1


def test_a_crash_after_resend_retries_under_the_same_key_with_no_second_claim(conn, monkeypatch):
    """G23, AC-M4.5."""
    seeded, request = approved(conn, monkeypatch)
    sent = fake_resend(monkeypatch)
    real_mark = send._mark_sent

    def dies(*args, **kwargs):
        raise SystemExit("the Mac lost power")

    monkeypatch.setattr(send, "_mark_sent", dies)
    at(monkeypatch, TUESDAY_10)
    with pytest.raises(SystemExit):
        send.send_due(conn)
    assert len(sent) == 1 and approvals.get(conn, request.id).used_at
    row = db.one(conn, "SELECT status, attempts FROM outreach_messages WHERE id = ?", (seeded["message_id"],))
    assert dict(row) == {"status": "queued", "attempts": 1}

    monkeypatch.setattr(send, "_mark_sent", real_mark)
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    assert send.send_due(conn).summary.startswith(f"sent message {seeded['message_id']}")
    keys = [r.headers["idempotency-key"] for r in sent]
    assert keys == [f"jura-outreach-{seeded['message_id']}"] * 2
    assert used_events(conn) == 1
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (seeded["message_id"],)) == "sent"
    assert outreach_requests(conn)[-1].id == request.id  # no new request was raised for the retry


def test_a_retry_whose_email_changed_after_its_claim_is_not_sent(conn, monkeypatch):
    seeded, request = approved(conn, monkeypatch)
    sent = fake_resend(monkeypatch, lambda r: httpx.Response(500, json={"message": "internal"}))
    at(monkeypatch, TUESDAY_10)
    assert "will retry" in send.send_due(conn).summary
    conn.execute("UPDATE outreach_messages SET subject = subject || ' (edited)' WHERE id = ?", (seeded["message_id"],))
    at(monkeypatch, "2026-11-10T10:10:00+08:00")
    result = send.send_due(conn)
    assert len(sent) == 1 and "isn't sent again" in (result.summary or result.note)
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (seeded["message_id"],)) == "failed"
    assert used_events(conn) == 1


def test_completion_never_rechecks_a_deadline(conn, monkeypatch):
    """G24: claimed one second before the use-by, marked sent after it."""
    seeded, request = approved(conn, monkeypatch)
    use_by = approvals.get(conn, request.id).use_by

    def slow(request_):
        at(monkeypatch, "2026-11-13T16:30:05+08:00")
        return httpx.Response(200, json={"id": "re-slow"})

    fake_resend(monkeypatch, slow)
    at(monkeypatch, "2026-11-13T16:29:59+08:00")
    assert use_by == "2026-11-13T16:30:00+08:00"
    assert send.send_due(conn).summary.startswith("sent message")
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at == "2026-11-13T16:29:59+08:00"
    assert approvals.expire_due(conn) == [] and approvals.get(conn, request.id) == record
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'approval.expired'") == 0


def test_without_its_plugin_the_kind_fails_closed(conn, monkeypatch):
    """AC-M4.7: `use()` refuses, `expire_due()` leaves the record alone, and nothing is raised."""
    seeded, request = approved(conn, monkeypatch)
    later = seed(conn, 2)["message_id"]

    def broken():
        raise ImportError("the outreach plug-in failed to load")

    monkeypatch.setattr(outreach, "approval_kinds", broken)
    assert approval.KIND not in approvals.kinds()
    sent = fake_resend(monkeypatch)
    at(monkeypatch, TUESDAY_10)
    send.send_due(conn)
    assert sent == [] and approvals.get(conn, request.id).used_at is None
    assert approval.raise_due(conn) == [] and later
    before = approvals.get(conn, request.id)
    at(monkeypatch, "2026-11-20T10:00:00+08:00")
    assert approvals.expire_due(conn) == [] and approvals.get(conn, request.id) == before


# --- the UAT stub (X13) ------------------------------------------------------------------


def stub_env(monkeypatch, url="http://127.0.0.1:8025"):
    monkeypatch.setenv(send.RESEND_BASE_ENV, url)


def test_the_suite_sends_to_the_real_resend_address_through_the_double():
    assert send.resend_url() == "https://api.resend.com/emails"


def test_the_base_url_points_resend_at_a_local_stub_from_a_temporary_data_folder(monkeypatch):
    stub_env(monkeypatch)
    assert send.resend_url() == "http://127.0.0.1:8025/emails"
    live_ready(monkeypatch)
    assert send.live_problems() == []


@pytest.mark.parametrize("url", ["https://api.resend.com", "http://example.com:8025", "https://127.0.0.1:8025"])
def test_the_base_url_must_be_a_local_stub(monkeypatch, url):
    stub_env(monkeypatch, url)
    live_ready(monkeypatch)
    assert any(send.RESEND_BASE_ENV in p for p in send.live_problems())
    with pytest.raises(send.ResendStubRefused):
        send.resend_url()


def test_the_base_url_is_refused_unless_the_data_folder_is_temporary(monkeypatch):
    stub_env(monkeypatch)
    live_ready(monkeypatch)
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(paths.JURA_ROOT / "data" / "growth"))
    assert any("not a temporary folder" in p for p in send.live_problems())
    with pytest.raises(send.ResendStubRefused, match="not a temporary folder"):
        send.resend_url()


def test_the_stub_refuses_a_data_folder_that_isnt_temporary(monkeypatch):
    import resend_stub

    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(paths.JURA_ROOT / "data" / "growth"))
    out = io.StringIO()
    with redirect_stdout(out):
        assert resend_stub.main(["--port", "0"]) == 2
    assert "not a temporary folder" in out.getvalue()
    monkeypatch.delenv("JURA_GROWTH_DATA_DIR")
    assert "isn't set" in resend_stub.refusal()


def test_a_live_send_reaches_the_stub_once_under_its_idempotency_key(conn, monkeypatch):
    import resend_stub

    seeded, request = approved(conn, monkeypatch)
    out = io.StringIO()
    server = resend_stub.server(0, out=out)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        stub_env(monkeypatch, f"http://127.0.0.1:{server.server_address[1]}")
        monkeypatch.setattr(send, "resend_client", lambda: httpx.Client(timeout=5))
        at(monkeypatch, TUESDAY_10)
        assert send.send_due(conn).summary.startswith("sent message")
    finally:
        server.shutdown()
        server.server_close()
    [line] = [l for l in out.getvalue().splitlines() if l.startswith("POST")]
    assert f"jura-outreach-{seeded['message_id']}" in line and "to=info@alderlogistics.sg" in line
    assert "re_test_key" not in out.getvalue()
    assert db.scalar(conn, "SELECT resend_id FROM outreach_messages WHERE id = ?", (seeded["message_id"],)) == "stub-1"
