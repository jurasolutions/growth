"""When Discord can't be reached, nothing else breaks.

A Mac waking from sleep or on flaky Wi-Fi is exactly when runs fail and the
webhook is unreachable, so the failure path (alert, then auto-pause) must hold
up without Discord. Regression tests for the foundation review's B2.
"""

import socket

import httpx
import pytest
from click.testing import CliRunner

from jura_growth import config, db, discord, pause, runner
from jura_growth.cli import cli
from test_scout_support import outbox


@pytest.fixture
def discord_down(monkeypatch):
    """Point #alerts at a local port nothing listens on, so every post is refused."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}/x"
    monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", url)
    return url


@pytest.fixture
def failing_job(monkeypatch):
    """A job, `boomer`, that fails every time it runs."""
    base = config.settings()
    patched = dict(base)
    patched["jobs"] = {
        **base["jobs"],
        "boomer": {"agent": "boomer", "kind": "command", "command": ["no-such-command"], "schedule": {"daily": "06:00"}},
    }
    monkeypatch.setattr(config, "settings", lambda: patched)
    return "boomer"


def test_three_failures_pause_the_agent_when_discord_is_down(discord_down, failing_job):
    statuses = [runner.run(failing_job).status for _ in range(4)]

    assert statuses == ["failed", "failed", "failed", "skipped"]
    with db.session() as c:
        assert pause.is_paused(c, "boomer") == "3 failed runs in a row"


def test_cli_run_exits_with_the_runs_own_status_when_discord_is_down(discord_down, failing_job):
    result = CliRunner().invoke(cli, ["run", failing_job], catch_exceptions=False)

    assert result.exit_code == 1
    assert result.output.startswith("boomer: failed")
    assert "Traceback" not in result.output


def test_undelivered_alert_lands_in_the_outbox(discord_down, failing_job):
    runner.run(failing_job)

    records = outbox()
    assert [r["channel"] for r in records] == ["alerts"]
    assert "`boomer` failed" in records[0]["content"]


@pytest.mark.parametrize(
    "transport_error",
    [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout],
    ids=["dns-or-refused", "connect-timeout", "read-timeout"],
)
def test_unreachable_webhook_saves_to_outbox_without_quoting_the_url(conn, monkeypatch, transport_error):
    monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://discord.com/api/webhooks/1/secret")

    def handler(request):
        raise transport_error(f"could not reach {request.url}", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = discord.post(conn, "alerts", "hello", client=client)

    assert not result.delivered
    assert "saved to outbox" in result.reason and "secret" not in result.reason
    assert outbox("alerts")[-1]["content"] == "hello"
    events = db.rows(conn, "SELECT payload_json FROM events WHERE kind = 'discord.error'")
    assert events and all("secret" not in e["payload_json"] for e in events)


@pytest.mark.parametrize(
    "body",
    [
        {"text": "<html><body>You are being rate limited.</body></html>", "headers": {"content-type": "text/html"}},
        {"json": {"retry_after": "abc"}},
        {"json": {"retry_after": -1}},
        {"json": []},
    ],
    ids=["html-page", "non-numeric-retry-after", "negative-retry-after", "not-an-object"],
)
def test_rate_limit_answer_without_a_usable_wait_saves_to_outbox(conn, monkeypatch, body):
    monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://discord.com/api/webhooks/1/secret")
    waits = []
    monkeypatch.setattr(discord.time, "sleep", waits.append)

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, **body)))
    result = discord.post(conn, "alerts", "hello", client=client)

    assert not result.delivered
    assert "saved to outbox" in result.reason and "secret" not in result.reason
    assert outbox("alerts")[-1]["content"] == "hello"
    assert all(0 <= seconds <= 10 for seconds in waits)


@pytest.mark.parametrize("asked, waited", [(2.5, 2.5), (60, 10.0)], ids=["as-asked", "capped"])
def test_rate_limit_waits_as_asked_then_delivers(conn, monkeypatch, asked, waited):
    monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://discord.com/api/webhooks/1/secret")
    waits = []
    monkeypatch.setattr(discord.time, "sleep", waits.append)
    answers = iter([httpx.Response(429, json={"retry_after": asked}), httpx.Response(204)])

    client = httpx.Client(transport=httpx.MockTransport(lambda request: next(answers)))
    result = discord.post(conn, "alerts", "hello", client=client)

    assert result.delivered
    assert waits == [waited]


def test_auto_pause_runs_whatever_happens_to_the_alert(failing_job, monkeypatch):
    def broken_alert(*args, **kwargs):
        raise RuntimeError("alert broke")

    monkeypatch.setattr(discord, "alert", broken_alert)

    for _ in range(3):
        with pytest.raises(RuntimeError, match="alert broke"):
            runner.run(failing_job)

    with db.session() as c:
        assert pause.is_paused(c, "boomer") == "3 failed runs in a row"
