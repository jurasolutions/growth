"""Where a decision comes from: `origin.detect_ssh()` (MC §4.6 A8 as amended 2026-10-26, ADR 0004).

Seam S13. Decisions come only from Dispatch over SSH; Terminal decisions are off. Unit tests here
walk canned `ps -o ppid=,comm=` tables (dataset D12) and drive `detect_ssh()`'s branches in
process. `test_origin_processes.py` runs the real refusals in real processes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from jura_growth import origin
from jura_growth.origin import NOT_HUMAN, SSH, Process


def table(rows: dict[int, str], args: dict[int, str] | None = None, uids: dict[int, int] | None = None):
    """A fake `ps`: `rows[pid]` is the `ppid comm` line, `args[pid]` the `args` line and
    `uids[pid]` the `uid` line."""

    def ps(pid: int, field: str) -> str | None:
        if field == "args=":
            return (args or {}).get(pid)
        if field == "uid=":
            uid = (uids or {}).get(pid)
            return None if uid is None else f"  {uid}"
        return rows.get(pid)

    return ps


SHELL = {500: "  400 /bin/zsh", 400: "  300 /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal", 300: "    1 /sbin/launchd"}


# --- the ps parser -------------------------------------------------------------------


def test_a_ps_line_keeps_a_command_name_with_spaces():
    assert origin.parse("  3866 /Applications/Visual Studio Code.app/Contents/MacOS/Code Helper") == (
        3866,
        "/Applications/Visual Studio Code.app/Contents/MacOS/Code Helper",
    )


def test_a_ps_line_that_isnt_a_parent_and_a_name_is_refused():
    with pytest.raises(ValueError):
        origin.parse("garbage")


def test_the_walk_goes_up_to_launchd():
    found = origin.ancestry(500, ps=table(SHELL))
    assert [p.pid for p in found] == [500, 400, 300]
    assert found[0] == Process(500, 400, "/bin/zsh")


def test_a_walk_that_ps_cant_finish_is_none():
    rows = dict(SHELL)
    del rows[400]
    assert origin.ancestry(500, ps=table(rows)) is None


def test_a_walk_that_loops_is_none():
    assert origin.ancestry(10, ps=table({10: "11 a", 11: "10 b"})) is None


# --- claude among the ancestors (AC-M7.4, D12) -----------------------------------------


@pytest.mark.parametrize(
    "rows",
    [
        {500: "  400 claude", 400: "    1 /sbin/launchd"},
        {500: "  400 /bin/zsh", 400: "  300 /Users/tingy/.local/bin/claude", 300: "    1 /sbin/launchd"},
        {500: "  400 /bin/zsh", 400: "  300 /bin/bash", 300: "  200 /bin/zsh", 200: "  100 claude", 100: "    1 /sbin/launchd"},
        {500: "  400 /bin/zsh", 400: "  300 /Applications/Claude.app/Contents/MacOS/Claude", 300: "    1 /sbin/launchd"},
    ],
    ids=["parent", "path-prefix", "great-grandparent", "desktop-app"],
)
def test_claude_at_any_depth_or_with_a_path_prefix_is_found(rows):
    assert origin.claude_among(origin.ancestry(500, ps=table(rows)))


def test_claude_running_under_node_is_found_through_its_arguments():
    rows = {500: "  400 /bin/zsh", 400: "  300 node", 300: "    1 /sbin/launchd"}
    found = origin.ancestry(500, ps=table(rows, {400: "node /usr/local/bin/claude --resume"}))
    assert origin.claude_among(found)


def test_a_plain_shell_has_no_claude_ancestor():
    assert not origin.claude_among(origin.ancestry(500, ps=table(SHELL)))


def test_a_name_that_only_contains_claude_is_not_claude():
    rows = {500: "  400 /usr/local/bin/claudette", 400: "    1 /sbin/launchd"}
    assert not origin.claude_among(origin.ancestry(500, ps=table(rows)))


def test_sshd_and_its_session_process_are_both_found_when_they_run_as_root():
    for name in ("/usr/sbin/sshd", "sshd-session", "sshd: tingy [priv]"):
        rows = {500: f"  400 {name}", 400: "    1 /sbin/launchd"}
        assert origin.sshd_among(origin.ancestry(500, ps=table(rows, uids={500: 0}))), name


@pytest.mark.parametrize("uid", [501, None], ids=["ting-yus-user", "uid-unknown"])
def test_an_sshd_that_isnt_root_is_not_sshd(uid):
    """Code review 11: a symlink named `sshd`, run by any process as Ting Yu's user, showed
    in `ps` as `sshd`. Only the real daemon's monitor runs as root, and no user process
    can start a root one."""
    rows = {500: "  400 /tmp/x/sshd", 400: "    1 /sbin/launchd"}
    found = origin.ancestry(500, ps=table(rows, uids={} if uid is None else {500: uid}))
    assert found is not None and not origin.sshd_among(found)


def test_a_root_process_that_isnt_sshd_is_not_sshd():
    """Terminal's `login` runs as root above every Terminal shell."""
    rows = {500: "  400 /bin/zsh", 400: "  300 login", 300: "    1 /sbin/launchd"}
    assert not origin.sshd_among(origin.ancestry(500, ps=table(rows, uids={400: 0})))


# --- there is no Terminal origin (MC3 as amended 2026-10-26, ADR 0004) ------------------


def test_terminal_decisions_are_off_so_there_is_no_terminal_check_to_pass():
    assert not hasattr(origin, "detect") and not hasattr(origin.Origin, "terminal")
    with pytest.raises(ValueError):
        origin.Origin("terminal")


# --- detect_ssh(): the remote origin (for ticket 11) ---------------------------------


@pytest.fixture
def remote(monkeypatch):
    """Dispatch's forced command, with an sshd ancestor. Claude Code's markers are
    removed on purpose: this suite may itself run inside a Claude session."""
    state = {
        "rows": {500: "  400 /bin/sh", 400: "  300 sshd-session", 300: "  200 sshd-session", 200: "    1 /sbin/launchd"},
        "uids": {300: 0},  # the privileged monitor; the session process above the shell runs as Ting Yu
    }
    monkeypatch.setattr(origin, "_ps", lambda pid, field: table(state["rows"], uids=state["uids"])(pid, field))
    monkeypatch.setattr(origin, "_start", lambda: 500)
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "approve A-0412")
    for name in origin.CLAUDE_MARKERS:
        monkeypatch.delenv(name, raising=False)
    return state


def test_an_sshd_ancestor_with_the_forced_command_is_an_ssh_origin(remote):
    assert origin.detect_ssh().kind == SSH


@pytest.mark.parametrize("marker", origin.CLAUDE_MARKERS)
def test_any_claude_code_marker_is_refused_even_under_sshd(remote, monkeypatch, marker):
    """Defence in depth (code review 04b, S1): the markers survive a process leaving
    the session's tree, so they refuse even with a clean ancestry."""
    monkeypatch.setenv(marker, "1")
    found = origin.detect_ssh()
    assert found.kind == NOT_HUMAN and found.reason == origin.IN_CLAUDE


def test_an_empty_marker_is_not_a_marker(remote, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "")
    assert origin.detect_ssh().kind == SSH


def test_an_ancestry_that_cant_be_checked_is_refused(remote):
    remote["rows"] = {500: "  400 /bin/sh"}
    found = origin.detect_ssh()
    assert found.kind == NOT_HUMAN and found.reason == origin.UNCHECKED


def test_no_forced_command_is_refused(remote, monkeypatch):
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND")
    assert origin.detect_ssh().kind == NOT_HUMAN


def test_no_sshd_ancestor_is_refused(remote):
    remote["rows"] = SHELL
    assert origin.detect_ssh().kind == NOT_HUMAN


def test_a_claude_ancestor_under_sshd_is_refused(remote):
    remote["rows"] = {500: "  400 claude", 400: "  300 sshd-session", 300: "    1 /sbin/launchd"}
    remote["uids"] = {400: 0}
    assert origin.detect_ssh().kind == NOT_HUMAN


def test_an_sshd_ancestor_running_as_ting_yus_user_only_is_refused(remote):
    """The probe from code review 11: an orphaned shell under a symlink named `sshd`."""
    remote["uids"] = {}
    found = origin.detect_ssh()
    assert found.kind == NOT_HUMAN and found.reason == origin.NOT_DISPATCH


# --- structure (test strategy v3 E6) ----------------------------------------------------


def test_origin_reads_only_the_forced_command_and_the_claude_markers_and_no_flag():
    """E6: an origin is never granted from a variable an agent could set. The forced
    command's variable needs an sshd ancestor too, and the markers can only refuse."""
    source = Path(origin.__file__).read_text(encoding="utf-8")
    reads = [line.strip() for line in source.splitlines() if re.search(r"os\.environ|getenv", line)]
    assert reads == [
        "return next((name for name in CLAUDE_MARKERS if os.environ.get(name)), None)",
        'if not os.environ.get("SSH_ORIGINAL_COMMAND"):',
    ], reads
    assert "import click" not in source and "click." not in source


def test_ps_is_called_by_its_full_path_so_path_cant_swap_it():
    assert origin.PS == "/bin/ps"
