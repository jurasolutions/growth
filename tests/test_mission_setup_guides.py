"""AC-M14.1: the setup guides for mission control, and the digest the morning brief read (MC-09).

The guides are drafted in the feature folder (`.scratch/mission-control/setup/`, ticket review N4);
the release persona copies them to `outputs/growth/setup/` after the merge, where E6 checks them
again. The 17:30 digest keeps writing `daily-summary.json` after the brief line is retired.
"""

from __future__ import annotations

import json

from jura_growth import discord, paths, runner

SETUP = paths.REPO_ROOT / ".scratch" / "mission-control" / "setup"


def test_the_morning_brief_guide_tells_ting_yu_to_remove_the_line():
    text = (SETUP / "morning-brief.md").read_text(encoding="utf-8")
    assert "Remove the Jura growth line" in text
    assert "#mission-control" in text and "09:00" in text


def test_the_dispatch_contract_no_longer_says_the_one_pager_carries_the_grid():
    contract = (paths.REPO_ROOT / "docs" / "dispatch-contract.md").read_text(encoding="utf-8")
    assert "with the 14-day grid" not in contract
    assert "morning picture" in contract


def test_the_discord_guide_names_both_new_channels_and_approvals_notifies_on_all_messages():
    text = (SETUP / "discord.md").read_text(encoding="utf-8")
    for channel in ("mission-control", "approvals"):
        assert f"`{channel}`" in text and f"DISCORD_WEBHOOK_{channel.upper().replace('-', '_')}=" in text
    assert "right-click `#approvals` → notification settings → **all messages**" in text.lower()


def test_every_configured_channel_is_in_the_discord_guide():
    text = (SETUP / "discord.md").read_text(encoding="utf-8")
    for channel in discord.channels():
        assert f"| `{channel}` |" in text, channel
        assert f"`{discord.env_name(channel)}=`" in text, channel


def test_the_1730_digest_still_writes_daily_summary_json(conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T17:30:00+08:00")
    outcome = runner.run("digest", ignore_schedule=True)
    assert outcome.status == "ok", outcome
    summary = json.loads((paths.data_dir() / "daily-summary.json").read_text())
    assert summary["date"] == "2026-11-10" and summary["brief_line"]


def test_every_configured_channel_has_an_empty_webhook_line_in_the_env_example():
    """Final review St2: a setup copied from `.env.example` names every channel's webhook, with
    no value, each under a comment."""
    lines = (paths.REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for channel in discord.channels():
        name = discord.env_name(channel)
        assert f"{name}=" in lines, f"{name} is missing from .env.example"
    for line in lines:
        if line.startswith("DISCORD_WEBHOOK_"):
            assert line.endswith("="), f"{line.split('=')[0]} has a value in .env.example"
    for name in ("DISCORD_WEBHOOK_APPROVALS=", "DISCORD_WEBHOOK_MISSION_CONTROL="):
        assert lines[lines.index(name) - 1].startswith("# "), f"{name} has no comment"
