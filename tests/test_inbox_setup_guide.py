"""The setup guide and UAT Part B (inbox watch ticket 06). They are what Ting Yu follows on the real
accounts, because no test may touch them. The guide is drafted in the feature folder, and the release
copies it to `outputs/growth/setup/`. Both are `.scratch/`, which ships with the branch."""

from __future__ import annotations

import pytest

from jura_growth import paths

FEATURE = paths.REPO_ROOT / ".scratch" / "inbox-watch"
GUIDE = (FEATURE / "setup" / "inbox-watch.md").read_text(encoding="utf-8")
UAT = (FEATURE / "reviews" / "uat.md").read_text(encoding="utf-8")
PART_B = UAT[UAT.index("# Part B"):]


@pytest.mark.parametrize("words", [
    "does the watch see enough without clicking",
    "`auth_servers`",
    "Authentication-Results",
    "ENQUIRY_IMAP_HOST",
    "Does `info@` need the second mailbox",
    "`#mission-control` to notify on **all messages**",
    "Restart the Mac",
    "A message you move from Junk to the inbox stays noise",
    "answer it by hand",
    "may have posted, check here before answering by hand",
    "Page's activity log",
])
def test_iw_d4_the_setup_guide_covers(words):
    assert words.casefold() in GUIDE.casefold()


def _order(text: str, *words: str) -> None:
    places = [text.index(word) for word in words]
    assert places == sorted(places), words


def test_iw_d4_the_guide_pauses_the_browser_jobs_before_it_installs_the_schedule():
    _order(GUIDE, "jura-growth pause inbox-browser", "jura-growth schedule install", "jura-growth resume inbox-browser")


def test_iw_d4_the_guide_checks_the_watch_before_any_reply():
    _order(GUIDE, "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.")
    _order(GUIDE, "does the watch see enough without clicking".capitalize(), "## 6. The first replies")


def test_uat_part_b_opens_with_the_pause_before_schedule_install():
    _order(PART_B, "## A. Before you start", "jura-growth pause inbox-browser", "jura-growth schedule install", "## B.")
    first_step = PART_B[PART_B.index("## A. Before you start"):PART_B.index("schedule install")]
    assert "resume" not in first_step


def test_uat_part_a_is_stubs_and_comes_first():
    assert UAT.index("# Part A") < UAT.index("# Part B")
    assert "pytest" in UAT[UAT.index("# Part A"):UAT.index("# Part B")]


def test_uat_part_b_reads_the_auth_servers_id_from_a_real_enquiry():
    assert "Authentication-Results" in PART_B and "auth_servers" in PART_B and "config/inbox.yaml" in PART_B
    assert "a sender's own header counts for nothing" in PART_B


def test_uat_part_b_holds_the_golden_set_whole():
    for row in range(1, 17):
        assert f"| G{row} |" in PART_B, row


@pytest.mark.parametrize("job", ["inbox-check", "inbox-watch", "inbox-reply"])
def test_uat_part_b_reads_for_a_canary_from_each_clean_folder(job):
    """No double can prove what Claude Code does with those rules."""
    assert f"*-{job}.jsonl" in PART_B and f"data/growth/work/{job}.cwd/" in PART_B


def test_uat_part_b_reads_the_activity_log_because_the_audit_cant_judge_a_click():
    assert "activity log" in PART_B
