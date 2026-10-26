"""The Monday community run proposes joins as the Jura Page (browser publishing PRD §5.4; BP-06).

Rows traced: AC-P5.1 line 4 end to end (the run proposes no more than the weekly cap allows, a
fourth proposal in the ISO week is refused) and AC-P9.1 still holding for `community` (its
Facebook fetch denies, no browser tools). The run is the whole `community` job with the fake
`claude` binary (seam S10's fake, on the community job).
"""

from __future__ import annotations

import json

import pytest

import publish_fake
import publish_world as pw
from jura_growth import config, db, headless, runner
from jura_growth.agents import community
from jura_growth.agents.publish import items

CHROME = "mcp__claude-in-chrome__"


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    pw.community_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, "2026-11-09T07:30:00+08:00")  # Monday, the community run


def context() -> dict:
    result = pw.invoke("community", "context", "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


# --- AC-P9.1 still holds, with propose-join in the community run's commands -----------------------------


def commands() -> tuple[str, ...]:
    declared = community.permissions("community")
    assert declared is not None
    return declared.commands


def test_the_community_run_may_propose_joins_and_still_never_opens_facebook():
    assert "community propose-join" in commands()
    allowed, denied = headless.claude_rules("community")
    assert "Bash(jura-growth community propose-join:*)" in allowed or any("propose-join" in rule for rule in allowed)
    assert "WebFetch(domain:facebook.com)" in denied and "WebFetch(domain:*.facebook.com)" in denied
    built, _ = runner.claude_command("community", config.settings()["jobs"]["community"])
    assert "--chrome" not in built and CHROME not in " ".join(built) and "ClaudeInChromeDomain" not in " ".join(built)


def test_proposing_a_join_never_joins_or_confirms_anything_itself():
    declared = commands()
    assert "community set" not in declared and not any(c.startswith("publish ") for c in declared)


def test_the_community_prompt_proposes_joins_within_the_room_and_still_never_opens_facebook():
    from jura_growth import paths

    prompt = (paths.REPO_ROOT / "prompts" / "community.md").read_text(encoding="utf-8")
    section = prompt.split("## Part 1b", 1)[1].split("\n## ", 1)[0]
    assert "jura-growth community propose-join <id>" in section
    assert "joins.left" in section and "joins.candidates" in section
    assert "Never fetch facebook.com" in prompt  # the research rule stands (ticket 02)
    assert "never opens the group" in section.lower() or "never open" in section.lower()


# --- what the run reads: the joins it may propose --------------------------------------------------------


def test_context_lists_the_groups_a_join_may_be_proposed_for_and_the_weeks_room(conn, world):
    open_group = pw.not_joined(conn)
    pw.group(conn)  # joined as the Page already
    pw.not_joined(conn, pages_allowed="no")
    pw.not_joined(conn, fit="possible")
    pw.not_joined(conn, join_status="requested")
    waiting = pw.not_joined(conn)
    items.create_join(conn, waiting, run_id=None)
    legacy = pw.not_joined(conn, joined=1, joined_as=None)  # joined by Ting Yu as himself

    joins = context()["joins"]

    assert joins["browser"] is True
    assert joins["cap"] == 3 and joins["proposed_this_week"] == 1 and joins["left"] == 2
    assert [g["id"] for g in joins["candidates"]] == [open_group, legacy]
    assert set(joins["candidates"][0]) >= {"id", "name", "url", "fit_reason", "audience"}


def test_with_community_browser_off_the_run_proposes_no_join(conn, world, monkeypatch):
    pw.community_config(monkeypatch, browser=False)
    pw.not_joined(conn)
    joins = context()["joins"]
    assert joins["browser"] is False and joins["left"] == 0 and joins["candidates"] == []


# --- AC-P5.1 line 4 end to end: the Monday run and the weekly cap --------------------------------------------


def test_the_monday_run_proposes_no_more_than_the_weekly_cap(conn, tmp_path, monkeypatch):
    fake = publish_fake.install(tmp_path, monkeypatch)
    fake.community(lambda data: data.update(browser=True))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, "2026-11-09T07:30:00+08:00")
    groups = [pw.not_joined(conn) for _ in range(4)]
    fake.scenario([{"cli": ["community", "context", "--json"]},
                   *[{"cli": ["community", "propose-join", str(group)]} for group in groups]],
                  "OK: register updated; 3 joins proposed")

    outcome = runner.run("community", ignore_schedule=True)

    assert outcome.status == "ok", outcome
    calls = fake.cli
    assert [c["exit"] for c in calls[1:]] == [0, 0, 0, 1]
    assert "the cap is 3 a week" in calls[-1]["output"]
    proposed = db.rows(conn, "SELECT ref FROM publish_items WHERE kind = 'community_join' ORDER BY id")
    assert [int(row["ref"]) for row in proposed] == groups[:3]
    assert json.loads(calls[0]["output"])["joins"]["left"] == 3
