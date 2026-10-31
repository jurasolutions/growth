"""The morning order (morning brief PRD SC1, SC4, SC5, SC7).

The drafting jobs run before 09:00, and the one-pager at 09:00 reports what they left. Times come
from the PRD, not from the code, so a change to `config/settings.yaml` has to be a change to the PRD.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from jura_growth import config, paths, slots

MORNING = {
    "scout-research": {"business_days": "06:30"},
    "app-factory": {"daily": "07:00"},
    "social": {"daily": "07:30"},
    "community": {"weekly": {"day": "mon", "time": "08:00"}},
    "outreach-requests": {"business_days": "08:30"},
    "one-pager": {"daily": "09:00"},
}
# The approvals-first PRD moves the digest to 18:05; that branch changes its line here when it lands.
THE_REST = {
    "heartbeat": {"daily": "12:00"},
    "scout-send": {"business_days_every": {"start": "09:30", "end": "16:30", "minutes": 10}},
    "scout-sync": {"business_days": "16:45"},
    "digest": {"daily": "17:30"},
    "publish": {"daily_every": {"start": "09:00", "end": "17:40", "minutes": 20}},
    "backup": {"daily": "23:30"},
}


def jobs() -> dict:
    return config.settings()["jobs"]


def weekday(day: date) -> bool:
    return day.weekday() < 5


# --- SC1 and SC5: the times ----------------------------------------------------------------------


@pytest.mark.parametrize("job,shape", MORNING.items(), ids=MORNING)
def test_each_morning_job_has_the_prds_time(job, shape):
    assert jobs()[job]["schedule"] == shape


@pytest.mark.parametrize("job,shape", THE_REST.items(), ids=THE_REST)
def test_nothing_else_moves(job, shape):
    assert jobs()[job]["schedule"] == shape


def test_those_are_all_the_jobs():
    assert set(jobs()) == set(MORNING) | set(THE_REST)


def test_community_stays_weekly():
    assert list(jobs()["community"]["schedule"]) == ["weekly"]


def test_the_new_job_sits_after_scout_sync_and_the_one_pager_stays_after_the_digest():
    names = list(jobs())
    assert names[names.index("scout-sync") + 1] == "outreach-requests"
    assert names[names.index("digest") + 1] == "one-pager"


def test_outreach_requests_is_a_quiet_command_job_of_the_outreach_agent():
    assert jobs()["outreach-requests"] == {
        "agent": "outreach",
        "kind": "command",
        "command": ["outreach", "raise-due"],
        "quiet": True,
        "schedule": {"business_days": "08:30"},
    }


# --- SC4: no overlap, even at the job timeout ------------------------------------------------------


# 2 Nov 2026 is a Monday; these seven days run to the next Sunday.
@pytest.mark.parametrize("day", [date(2026, 11, 2) + timedelta(days=n) for n in range(7)], ids=lambda d: f"{d:%a}")
def test_every_morning_slot_ends_by_the_next_and_by_the_one_pager(day):
    timeout = timedelta(minutes=config.settings()["claude"]["timeout_minutes"])
    assert timeout == timedelta(minutes=30)
    today = sorted(at for job in MORNING for at in slots.slot_times(jobs()[job]["schedule"], day, weekday))
    assert today[-1].hour == 9, "the one-pager is the last of the morning"
    for earlier, later in zip(today, today[1:]):
        assert earlier + timeout <= later, f"{earlier:%H:%M} can overlap {later:%H:%M}"


def test_the_six_jobs_fall_in_the_prds_order_on_a_monday():
    found = sorted((slots.slot_times(jobs()[job]["schedule"], date(2026, 11, 2), weekday)[0], job) for job in MORNING)
    assert [job for _, job in found] == list(MORNING)


# --- SC7: what the docs say ------------------------------------------------------------------------


def readme_schedule() -> dict[str, str]:
    """README's job table: job name to its "When" cell."""
    text = (paths.REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return dict(re.findall(r"^\| `([a-z-]+)` \| ([^|]+) \| (?:headless Claude|command) \|$", text, re.M))


def test_readme_lists_every_job_with_its_time():
    table = readme_schedule()
    assert set(table) == set(jobs())
    for job, shape in {**MORNING, **THE_REST}.items():
        words = str(shape)
        for hhmm in re.findall(r"\d\d:\d\d", words):
            assert hhmm in table[job], f"README has {table[job]!r} for {job}"


# A file's own job and the time it has left behind. New times reuse some old ones (06:30 is now
# scout's, 07:30 is now social's), so a time is stale only beside the job that used to hold it.
OLD_TIMES = [
    ("06:30", ["docs/app-factory.md", "prompts/app-factory.md", "jura_growth/agents/apps"]),
    ("07:00", ["docs/social.md", "prompts/social.md", "config/social.yaml", "jura_growth/agents/social"]),
    ("07:30", ["docs/community.md", "prompts/community.md", "jura_growth/agents/community"]),
    ("09:00", ["prompts/scout.md", "config/scout.yaml", "jura_growth/agents/scout"]),
    ("08:00", [".env.example", ".scratch/mission-control/setup/discord.md"]),
]


@pytest.mark.parametrize("old,places", OLD_TIMES, ids=[old for old, _ in OLD_TIMES])
def test_a_moved_jobs_own_files_no_longer_name_its_old_time(old, places):
    stale = []
    for place in places:
        root = paths.REPO_ROOT / place
        assert root.exists(), f"{place} is gone, so this search proves nothing"
        for path in [root] if root.is_file() else sorted(root.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if old in line:
                    stale.append(f"{path.relative_to(paths.REPO_ROOT)}:{number}: {line.strip()}")
    assert stale == []


def test_the_scout_guide_gives_research_its_new_time():
    text = (paths.REPO_ROOT / "docs" / "scout.md").read_text(encoding="utf-8")
    assert "**06:30 `scout-research`**" in text
    assert "**08:30 `outreach-requests`**" in text
    assert "09:00 `scout-research`" not in text


def test_the_discord_guide_says_the_post_carries_the_morning_picture():
    guide = (paths.REPO_ROOT / ".scratch" / "mission-control" / "setup" / "discord.md").read_text(encoding="utf-8")
    assert "14-day grid" not in guide
    assert guide.count("morning picture") == 2


def test_the_one_pager_runs_at_09_00_in_the_setup_guide():
    guide = (paths.REPO_ROOT / ".scratch" / "mission-control" / "setup" / "morning-brief.md").read_text(encoding="utf-8")
    assert "09:00" in guide and "08:00" not in guide
