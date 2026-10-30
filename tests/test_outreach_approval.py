"""Live outreach waits for the approval buttons (AC-M8.11).

Ticket 01 added "approval gate not installed" to `live_problems()`. From MC-06
the line reads "approval buttons not set up", and it clears only when Ting Yu
sets `approvals.discord_buttons: true` after checking the buttons work (ticket
15). While it shows, live `send-due` and `requeue-shadow` refuse, even when
every other pre-condition holds.
"""

from click.testing import CliRunner

from jura_growth import config, db
from jura_growth.agents.outreach import requeue, send
from jura_growth.cli import cli

import pytest

from test_scout_support import MONDAY_10AM, at, fake_resend, live_ready, outbox, scout_env, seed  # noqa: F401

BUTTONS = "approval buttons not set up"
OLD_LINE = "approval gate not installed"


def every_other_check_holds(monkeypatch):
    live_ready(monkeypatch, approval_buttons=False)
    return fake_resend(monkeypatch)


def test_live_problems_lists_the_buttons_when_all_else_is_ready(monkeypatch):
    every_other_check_holds(monkeypatch)
    problems = send.live_problems()
    assert len(problems) == 1 and problems[0].startswith(BUTTONS)
    assert "approvals.discord_buttons: true" in problems[0]


def test_the_shipped_buttons_switch_is_on_and_live_stays_refused_by_the_other_preconditions():
    """E14, after U17 passed on 2026-10-31: the buttons switch ships on, so its line is gone, but
    live outreach stays refused until the legal review and the other live pre-conditions are met."""
    assert config.settings()["approvals"]["discord_buttons"] is True
    problems = send.live_problems()
    assert not any(p.startswith(BUTTONS) for p in problems)
    assert any("legal_review_done" in p for p in problems)
    assert not any(OLD_LINE in p for p in problems)


def test_the_line_clears_only_when_the_switch_is_true(monkeypatch):
    live_ready(monkeypatch, approval_buttons=True)
    assert send.live_problems() == []
    live_ready(monkeypatch, approval_buttons=False)
    assert [p for p in send.live_problems() if p.startswith(BUTTONS)]


def test_a_truthy_string_is_not_true(monkeypatch):
    live_ready(monkeypatch)
    patched = dict(config.settings())
    patched["approvals"] = {"discord_buttons": "yes"}
    monkeypatch.setattr(config, "settings", lambda: patched)
    assert any(p.startswith(BUTTONS) for p in send.live_problems())


def test_live_send_due_refuses_and_never_calls_resend(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    sent = every_other_check_holds(monkeypatch)
    result = send.send_due(conn)
    assert result.summary.startswith("live sending refused") and BUTTONS in result.summary
    assert sent == []
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message,)) == "queued"
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == 0
    assert any(BUTTONS in p["content"] for p in outbox("alerts"))


def test_requeue_shadow_refuses(conn, monkeypatch):
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    shadow = seed(conn, 1)["message_id"]
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW")
    at(monkeypatch, "2026-10-29T09:00:00+08:00")
    every_other_check_holds(monkeypatch)
    with pytest.raises(requeue.RequeueError, match=BUTTONS):
        requeue.requeue_shadow(conn)
    result = CliRunner().invoke(cli, ["outreach", "requeue-shadow"])
    assert result.exit_code == 1 and BUTTONS in result.output
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (shadow,)) == "shadow"
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == 0


def test_outreach_status_shows_live_mode_would_refuse(monkeypatch):
    every_other_check_holds(monkeypatch)
    result = CliRunner().invoke(cli, ["outreach", "status"])
    assert result.exit_code == 0, result.output
    assert "live mode would refuse:" in result.output and BUTTONS in result.output
