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
    assert "#mission-control" in text and "08:00" in text


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
