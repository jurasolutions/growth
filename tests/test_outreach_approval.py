"""Live outreach waits for the approval buttons (AC-M8.11).

Ticket 01 added "approval gate not installed" to `live_problems()`. From MC-06
the line reads "approval buttons not set up", and it clears only when Ting Yu
sets `approvals.discord_buttons: true` after checking the buttons work (ticket
15). While it shows, live `send-due` and `requeue-shadow` refuse, even when
every other pre-condition holds.
"""

import yaml
from click.testing import CliRunner

from jura_growth import config, db, paths
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


SHIPPED_SCOUT = paths.REPO_ROOT / "config" / "scout.yaml"

# What only the machine can answer: the real .env, the real inputs/ and Cloudflare D1.
MACHINE_ONLY = ("RESEND_API_KEY_OUTREACH", "UNSUBSCRIBE_SECRET", "do-not-contact.csv", "D1 is not configured")


def use_the_shipped_scout_config(monkeypatch) -> dict:
    """config/scout.yaml exactly as it ships, without the tests' shadow baseline."""
    shipped = yaml.safe_load(SHIPPED_SCOUT.read_text(encoding="utf-8"))
    monkeypatch.setattr(config, "agent_config", lambda agent: shipped if agent == "scout" else {})
    return shipped


def test_the_shipped_scout_config_goes_live_from_levi_at_jurasolutions():
    """Ting Yu's go-live decisions of 2026-10-31, as config/scout.yaml ships them."""
    shipped = yaml.safe_load(SHIPPED_SCOUT.read_text(encoding="utf-8"))
    assert shipped["mode"] == "live"
    assert shipped["legal_review_done"] is True
    assert shipped["sending_domain"] == "jurasolutions.sg"
    assert shipped["from_local_part"] == "levi"


def test_the_shipped_legal_review_flag_says_it_was_waived_not_done():
    """The flag reads true only because Ting Yu waived the review; the file must say so beside it."""
    text = SHIPPED_SCOUT.read_text(encoding="utf-8")
    before_flag = text.split("legal_review_done:", 1)[0].splitlines()[-3:]
    comment = " ".join(before_flag)
    assert "WAIVED, not done" in comment and "Ting Yu" in comment and "2026-10-31" in comment
    assert "no legal view exists" in comment


def test_the_shipped_config_leaves_only_what_the_machine_can_answer(monkeypatch):
    """E14, after U17 passed on 2026-10-31, and go-live on 2026-10-31: the buttons switch ships
    on and config/scout.yaml ships live, so no settings line remains. Only the .env secrets, the
    do-not-contact file and D1 (all absent in a test) may still refuse."""
    use_the_shipped_scout_config(monkeypatch)
    assert config.settings()["approvals"]["discord_buttons"] is True
    problems = send.live_problems()
    assert problems, "a test has no .env, so live mode must still refuse here"
    assert all(any(word in p for word in MACHINE_ONLY) for p in problems), problems
    assert not any("config/scout.yaml" in p or "config/settings.yaml" in p for p in problems)
    assert not any(p.startswith(BUTTONS) or OLD_LINE in p for p in problems)


def test_the_shipped_config_sends_from_levi_with_the_fixed_sender_name(monkeypatch):
    use_the_shipped_scout_config(monkeypatch)
    assert send.from_address() == "\"Ting Yu, Jura Solutions\" <levi@jurasolutions.sg>"


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
