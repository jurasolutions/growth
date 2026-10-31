"""The script Ting Yu follows names only what exists (ticket 04's acceptance).

`.scratch/approvals-first-social-depth/reviews/uat.md` is prose around commands. These cases read
it the way he will: every `jura-growth` command and option must be real, every seed scenario and
flag must be one the seed has, and what changed after it was written must stay corrected.
"""

from __future__ import annotations

import re
import shlex

import click
import pytest

from jura_growth import paths
from jura_growth.cli import cli
from uat import seed

SCRIPT = paths.REPO_ROOT / ".scratch" / "approvals-first-social-depth" / "reviews" / "uat.md"
TEXT = SCRIPT.read_text(encoding="utf-8")


def commands() -> list[list[str]]:
    """Every `uv run jura-growth …` in the script, as its words, up to the end of the command."""
    found = []
    for match in re.finditer(r"uv run jura-growth ([^`\n]+)", TEXT):
        line = match.group(1).split(";")[0].split(" | ")[0].split(",")[0]
        found.append(shlex.split(line))
    return found


def resolve(words: list[str]) -> tuple[click.Command, list[str]]:
    """The command these words reach, and the path that reached it."""
    command, path = cli, []
    for word in words:
        if not isinstance(command, click.Group) or word not in command.commands:
            break
        command, path = command.commands[word], [*path, word]
    return command, path


def test_the_script_names_commands_to_check():
    assert len(commands()) > 15


@pytest.mark.parametrize("words", commands(), ids=" ".join)
def test_each_jura_growth_command_in_the_script_exists_with_its_options(words):
    command, path = resolve(words)
    assert path and not isinstance(command, click.Group), f"{words} doesn't reach a command"
    known = {option for param in command.params for option in param.opts}
    for word in words[len(path):]:
        if word.startswith("--"):
            assert word in known, f"{word} isn't an option of {' '.join(path)}"


def test_the_slash_command_a_feed_line_names_is_a_real_command():
    command, path = resolve(["apps", "release-plan"])
    assert path == ["apps", "release-plan"] and not isinstance(command, click.Group)
    assert "/growth apps release-plan APP-nnn" in TEXT


def scenarios() -> set[str]:
    named = set(re.findall(r"--scenario ([a-z][a-z-]*)", TEXT))
    named |= set(re.findall(r"`?\bfresh ([a-z][a-z-]*)", TEXT))
    named |= {name for row in re.findall(r"^\| H\d \| (.+?) \| [^|]+ \|$", TEXT, re.M) for name in re.findall(r"Scenarios? `([a-z-]+)", row)}
    named |= set(re.findall(r"and `(late-wake)`", TEXT))
    return named


def test_the_script_names_every_new_scenario():
    assert {"social-day", "decide", "app-prd", "app-built", "drift", "late-wake", "base", "outreach-live"} <= scenarios()


@pytest.mark.parametrize("scenario", sorted(scenarios()))
def test_each_scenario_in_the_script_is_one_the_seed_has(scenario):
    assert scenario in seed.SCENARIOS


def test_each_seed_flag_in_the_script_is_one_the_seed_takes(capsys):
    with pytest.raises(SystemExit):
        seed.main(["--help"])
    usage = capsys.readouterr().out
    lines = [line for line in TEXT.splitlines() if "tests.uat.seed" in line]
    flags = {flag for line in lines for flag in re.findall(r"(--[a-z]+)", line)}
    flags |= set(re.findall(r"`social-day \[(--theme) ID\] \[(--offline)\]", TEXT)[0])
    assert {"--scenario", "--today", "--approval", "--decision", "--theme"} <= flags
    for flag in flags:
        assert flag in usage


@pytest.mark.parametrize("place", ["tests/fixtures/publish-site", "tests/resend_stub.py", "tests/uat/social-day", "tests/uat/app-prd.md"])
def test_what_the_script_serves_and_seeds_from_is_checked_in(place):
    assert (paths.REPO_ROOT / place).exists()
    assert place.removesuffix(".py").replace("tests/resend_stub", "tests.resend_stub") in TEXT


@pytest.mark.parametrize(
    "said",
    [
        "decide by <today>, 17:00 SGT",  # the decide-by moved to 17:00 (functional B2)
        "Run between 09:00 and 17:00",
        "no masked word",  # a post the masking layer changes is refused at the gate
        "Handed to Dispatch",  # dispatch_builds is on
        "It goes out on a publish run today, by 18:00 SGT.",
        "Publishing is paused, so nothing goes out until you resume it.",
        "It goes out on a send run, inside the send window and the day's caps.",
        "Expired: not approved in time",
        'fresh base\nmkdir -p "$UAT/cards"',  # Part P needs $UAT/config, or the banned words aren't read
        'JURA_SITE_REPO="$UAT/site" decide',  # only A3 points at the stand-in: Part E reads the real registry
    ],
)
def test_the_script_says_what_the_code_now_does(said):
    assert said in TEXT


@pytest.mark.parametrize(
    "stale",
    [
        "Build it: open Claude Code",
        "You build it by hand until Dispatch",
        "These go in ticket 2",
        "It goes out on the next publish run",
        "with the address masked",
        "Run between 09:00 and 18:00",
    ],
)
def test_the_script_has_dropped_what_is_no_longer_true(stale):
    assert stale not in TEXT
