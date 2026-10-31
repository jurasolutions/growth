"""The setup guide and UAT Part B (inbox watch ticket 06). They are what Ting Yu follows on the real
accounts, because no test may touch them. The guide is drafted in the feature folder, and the release
copies it to `outputs/growth/setup/`. Both are `.scratch/`, which ships with the branch."""

from __future__ import annotations

import re
import shlex

import click
import pytest
from click.testing import CliRunner

from jura_growth import db, paths, pause
from jura_growth.cli import cli

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


def test_iw_d4_the_guide_takes_the_code_then_pauses_then_installs_the_schedule():
    _order(GUIDE, "git pull", "uv sync", "jura-growth db migrate", "jura-growth pause inbox\n", "jura-growth pause inbox-browser",
           "jura-growth schedule install", "jura-growth resume inbox\n", "jura-growth resume inbox-browser")


def test_iw_d4_p4_the_guide_points_at_each_canary_where_it_can_be_followed():
    """H1 and H2 with `inbox` paused until they pass, H3 inside the watched run, H4 before any other approval."""
    _order(GUIDE, "jura-growth schedule install", "Canaries H1 and H2", "jura-growth resume inbox\n", "jura-growth run inbox-check", "Canary H3",
           "jura-growth run inbox-watch", "## 6. The first replies", "Canary H4", "**Then one comment.**")


def _commands(text: str) -> list[list[str]]:
    found = []
    for line in text.splitlines():
        for match in re.finditer(r"uv run (jura-growth [^`\n]*)", line):
            found.append(shlex.split(match.group(1).split(" and ")[0].rstrip(".,"))[1:])
    return found


@pytest.mark.parametrize("name, text", [("guide", GUIDE), ("uat", PART_B)])
def test_iw_d4_p3_every_command_they_name_is_one_this_code_has(name, text):
    """Walked as he would, against the real command tree. Nothing is run."""
    commands = _commands(text)
    assert len(commands) >= 6
    for words in commands:
        command, rest = cli, list(words)
        while isinstance(command, click.Group) and rest:
            command = command.commands.get(rest.pop(0))
            assert command is not None, words
        assert not isinstance(command, click.Group), words
        known = {option for param in command.params for option in getattr(param, "opts", ()) if option.startswith("--")}
        for word in rest:
            assert not word.startswith("--") or word in known, words


def test_iw_d4_p3_those_commands_work_in_order_on_a_new_database(tmp_path, monkeypatch):
    """Every one of the guide's commands up to the install, by hand on a fresh database, as he runs them."""
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(tmp_path))
    runner = CliRunner()
    for words in (["db", "migrate"], ["pause", "inbox"], ["pause", "inbox-browser"], ["inbox", "status"], ["status"]):
        result = runner.invoke(cli, words)
        assert result.exit_code == 0, (words, result.output)
    with db.session() as conn:
        assert pause.is_paused(conn, "inbox") and pause.is_paused(conn, "inbox-browser")


def test_iw_d4_the_guide_checks_the_watch_before_any_reply():
    _order(GUIDE, "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.")
    _order(GUIDE, "does the watch see enough without clicking".capitalize(), "## 6. The first replies")


def test_uat_part_b_takes_the_code_then_pauses_before_schedule_install():
    """P-3: `pause` refuses an agent the checkout doesn't know, so the pull comes first."""
    _order(PART_B, "## A. Before you start", "git pull", "uv sync", "jura-growth db migrate", "jura-growth pause inbox\n", "jura-growth pause inbox-browser",
           "jura-growth schedule install", "## B.")
    first_step = PART_B[PART_B.index("## A. Before you start"):PART_B.index("schedule install")]
    assert "resume" not in first_step


def test_uat_part_b_does_the_canaries_where_they_can_be_followed():
    """P-4: H3 and H4 need `inbox-browser` running, and H1 and H2 need `inbox`."""
    start = PART_B[PART_B.index("## A. Before you start"):PART_B.index("## What every check")]
    _order(start, "schedule install", "H1 and H2", "`auth_servers`", "H3 goes with", "jura-growth resume inbox-browser", "H4 with the first approval")
    assert "jura-growth resume inbox`" in PART_B[PART_B.index("| H1 |"):PART_B.index("| H2 |")]


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
