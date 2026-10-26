"""The UAT stand-in for D1 (ticket 18; X13).

`JURA_GROWTH_D1_BASE_URL` points the D1 client at the local stub (`uv run python -m
tests.resend_stub`), so UAT's suppression sync and D1 checks never reach Cloudflare. The client
honours it only for a loopback http URL and a temporary data folder, and refuses anything else
without falling back to Cloudflare. The suite's own D1 traffic still goes through the double.
"""

from __future__ import annotations

import io
import threading

import httpx
import pytest

import resend_stub
from jura_growth import cloudflare, paths, suppression
from jura_growth.agents.outreach import send, sync
from jura_growth.agents.scout import registry

from test_scout_support import MONDAY_10AM, at, d1_env, fake_resend, live_ready, scout_env  # noqa: F401

UNSUBSCRIBED = "owner@unsubscribed.example.sg"
LOCAL = "http://127.0.0.1:8025"


def both_stubs(monkeypatch, url: str = LOCAL) -> None:
    """Resend and D1 pointed at one stub, as `uat.md`'s window sets them."""
    monkeypatch.setenv(send.RESEND_BASE_ENV, url)
    monkeypatch.setenv(cloudflare.BASE_ENV, url)


@pytest.fixture
def stub(monkeypatch):
    """The stub on a free loopback port, holding one unsubscribe, with the D1 client pointed at it."""
    out = io.StringIO()
    server = resend_stub.server(0, out=out, suppression=[
        {"email_hash": suppression.email_hash(UNSUBSCRIBED), "email": UNSUBSCRIBED, "reason": "unsubscribe",
         "source": "site", "resend_email_id": None, "created_at": "2026-11-16 09:00:00"},
    ])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    both_stubs(monkeypatch, f"http://127.0.0.1:{server.server_address[1]}")
    try:
        yield out
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_sync_reads_suppression_from_the_stub_without_cloudflare_credentials(conn, stub):
    result = sync.sync_suppression(conn)
    assert result.configured and result.ok, result.error
    assert result.new == 1 and result.unsubscribes == 1
    assert suppression.is_suppressed(conn, UNSUBSCRIBED)
    assert "FROM suppression" in stub.getvalue()


def test_live_problems_count_the_stub_as_d1(stub, monkeypatch):
    live_ready(monkeypatch)
    for name in cloudflare.SECRETS:
        monkeypatch.delenv(name)
    assert cloudflare.configured()
    assert send.live_problems() == []


# --- the stubs are a pair (review 18, SEC-1) ---------------------------------------------------

PAIR = "the UAT stub stands in for Resend and D1 together"


@pytest.mark.parametrize("have, missing", [
    (cloudflare.BASE_ENV, send.RESEND_BASE_ENV),  # a stubbed suppression list must never meet real Resend
    (send.RESEND_BASE_ENV, cloudflare.BASE_ENV),  # stubbed sends must never be checked against real D1
])
def test_one_stub_without_the_other_is_refused_and_send_due_sends_nothing(conn, monkeypatch, have, missing):
    live_ready(monkeypatch)
    monkeypatch.setenv(have, LOCAL)
    sent = fake_resend(monkeypatch)
    expected = f"{have} is set but {missing} isn't: {PAIR}"
    assert [p for p in send.live_problems() if p.startswith(expected)]
    with pytest.raises(send.ResendStubRefused, match=PAIR):
        send.resend_url()
    with pytest.raises(cloudflare.D1StubRefused, match=PAIR):
        cloudflare.query("SELECT 1")
    at(monkeypatch, MONDAY_10AM)
    result = send.send_due(conn)
    assert result.note.startswith("live sending refused") and expected in result.note
    assert sent == []


def test_with_real_credentials_set_the_query_still_goes_to_the_stub_with_none_of_them(monkeypatch):
    d1_env(monkeypatch)
    monkeypatch.setenv(send.RESEND_BASE_ENV, "http://localhost:8026/")
    monkeypatch.setenv(cloudflare.BASE_ENV, "http://localhost:8026/")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"success": True, "result": [{"results": [{"one": 1}]}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert cloudflare.query("SELECT 1 AS one", client=client) == [{"one": 1}]
    (request,) = seen
    assert str(request.url) == "http://localhost:8026/accounts/uat/d1/database/uat/query"
    assert request.headers["Authorization"] == "Bearer uat-stub"
    assert "cf-test-token-not-real" not in str(request.headers) + request.content.decode()


def test_toolbox_usage_comes_from_the_stub(monkeypatch):
    server = resend_stub.server(0, out=io.StringIO(), app_usage=[
        {"app_slug": "quote-builder", "day": "2999-01-01", "opens": 5, "completions": 2},
    ])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    both_stubs(monkeypatch, f"http://127.0.0.1:{server.server_address[1]}")
    try:
        assert registry.usage() == {"quote-builder": {"opens": 5, "completions": 2}}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_stub_answers_read_queries_only(conn, stub):
    with pytest.raises(cloudflare.D1Error, match="SELECT queries only"):
        cloudflare.query("DELETE FROM suppression")
    with pytest.raises(cloudflare.D1Error, match="D1 stub"):
        cloudflare.query("SELECT 1; DELETE FROM suppression")
    assert sync.sync_suppression(conn).new == 1


# --- the refusal --------------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://api.cloudflare.com/client/v4",
    "http://example.com:8025",
    "https://127.0.0.1:8025",
    "http://127.0.0.1.example.com:8025",
    "http://10.0.0.5:8025",
])
def test_an_override_that_isnt_a_local_stub_is_refused_and_cloudflare_is_never_asked(conn, monkeypatch, url):
    d1_env(monkeypatch)  # real-looking credentials too: the refusal must not fall back to Cloudflare
    monkeypatch.setenv(cloudflare.BASE_ENV, url)
    with pytest.raises(cloudflare.D1StubRefused, match=f"{cloudflare.BASE_ENV} must point at the local UAT stub"):
        cloudflare.query("SELECT 1")
    live_ready(monkeypatch)
    assert any(p.startswith(f"{cloudflare.BASE_ENV} must point at the local UAT stub") for p in send.live_problems())
    result = sync.sync_suppression(conn)
    assert not result.ok and cloudflare.BASE_ENV in result.error
    assert registry.usage() == {}


def test_the_override_is_refused_unless_the_data_folder_is_temporary(monkeypatch):
    monkeypatch.setenv(cloudflare.BASE_ENV, "http://127.0.0.1:8025")
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(paths.JURA_ROOT / "data" / "growth"))
    assert "not a temporary folder" in (cloudflare.stub_problem() or "")
    with pytest.raises(cloudflare.D1StubRefused, match="not a temporary folder"):
        cloudflare.query("SELECT 1")


def test_without_the_override_the_client_is_unchanged():
    assert cloudflare.stub_problem() is None
    assert not cloudflare.configured()
