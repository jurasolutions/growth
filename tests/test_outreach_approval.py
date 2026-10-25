"""Live outreach waits for the approval gate (AC-M8.11).

Before MC-06 lands, `live_problems()` lists "approval gate not installed",
and live `send-due` and `requeue-shadow` refuse even when every other
pre-condition holds. MC-06 replaces the line with "approval buttons not set
up" and extends this file with its two states.
"""

from click.testing import CliRunner

from jura_growth import db
from jura_growth.agents.outreach import requeue, send
from jura_growth.cli import cli

import pytest

from test_scout_support import MONDAY_10AM, at, fake_resend, live_ready, outbox, scout_env, seed  # noqa: F401

GATE = "approval gate not installed"


def every_other_check_holds(monkeypatch):
    live_ready(monkeypatch, approval_gate=False)
    return fake_resend(monkeypatch)


def test_live_problems_lists_the_missing_approval_gate_when_all_else_is_ready(monkeypatch):
    every_other_check_holds(monkeypatch)
    problems = send.live_problems()
    assert len(problems) == 1 and problems[0].startswith(GATE)


def test_live_problems_lists_it_in_shadow_mode_too(monkeypatch):
    assert any(p.startswith(GATE) for p in send.live_problems())


def test_live_send_due_refuses_and_never_calls_resend(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    sent = every_other_check_holds(monkeypatch)
    result = send.send_due(conn)
    assert result.summary.startswith("live sending refused") and GATE in result.summary
    assert sent == []
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message,)) == "queued"
    assert any(GATE in p["content"] for p in outbox("alerts"))


def test_requeue_shadow_refuses(conn, monkeypatch):
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    shadow = seed(conn, 1)["message_id"]
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    at(monkeypatch, "2026-10-29T09:00:00+08:00")
    every_other_check_holds(monkeypatch)
    with pytest.raises(requeue.RequeueError, match=GATE):
        requeue.requeue_shadow(conn)
    result = CliRunner().invoke(cli, ["outreach", "requeue-shadow"])
    assert result.exit_code == 1 and GATE in result.output
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (shadow,)) == "shadow"


def test_outreach_status_shows_live_mode_would_refuse(monkeypatch):
    every_other_check_holds(monkeypatch)
    result = CliRunner().invoke(cli, ["outreach", "status"])
    assert result.exit_code == 0, result.output
    assert "live mode would refuse:" in result.output and GATE in result.output
