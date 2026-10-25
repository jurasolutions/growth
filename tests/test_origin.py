"""Where a decision comes from: `origin.detect()` and `origin.detect_ssh()` (MC §4.6 A8, ADR 0004).

Seam S13. Unit tests here walk canned `ps -o ppid=,comm=` tables (dataset D12) and drive
`detect()`'s branches in process. `test_origin_processes.py` runs the real checks in real
processes: no TTY, a pseudo-terminal, and a `claude` ancestor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from jura_growth import origin
from jura_growth.origin import NOT_HUMAN, SSH, TERMINAL, Process


def table(rows: dict[int, str], args: dict[int, str] | None = None):
    """A fake `ps`: `rows[pid]` is the `ppid comm` line, `args[pid]` the `args` line."""

    def ps(pid: int, field: str) -> str | None:
        if field == "args=":
            return (args or {}).get(pid)
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


def test_sshd_and_its_session_process_are_both_found():
    for name in ("/usr/sbin/sshd", "sshd-session", "sshd: tingy [priv]"):
        rows = {500: f"  400 {name}", 400: "    1 /sbin/launchd"}
        assert origin.sshd_among(origin.ancestry(500, ps=table(rows))), name


# --- detect(): Terminal (AC-M7.2 to AC-M7.4) ------------------------------------------


@pytest.fixture
def terminal(monkeypatch):
    """A real terminal, a clean ancestry and Ting Yu typing `typed`."""
    state = {"ttys": True, "rows": SHELL, "typed": "3f9a1c\n", "prompts": []}
    monkeypatch.setattr(origin, "_both_ttys", lambda: state["ttys"])
    monkeypatch.setattr(origin, "_ps", lambda pid, field: table(state["rows"])(pid, field))
    monkeypatch.setattr(origin, "_start", lambda: 500)

    def read(prompt):
        state["prompts"].append(prompt)
        return state["typed"]

    monkeypatch.setattr(origin, "_read_line", read)
    return state


def test_a_terminal_with_the_code_typed_is_a_terminal_origin(terminal):
    found = origin.detect("Type A-0412's code: ")
    assert found.kind == TERMINAL and found.code == "3f9a1c" and found.user
    assert terminal["prompts"] == ["Type A-0412's code: "]


def test_no_tty_is_refused_before_anything_is_asked(terminal):
    terminal["ttys"] = False
    found = origin.detect("Type A-0412's code: ")
    assert found.kind == NOT_HUMAN
    assert found.reason == "decisions need a terminal or the Dispatch link"
    assert terminal["prompts"] == []


def test_a_claude_ancestor_is_refused_before_anything_is_asked(terminal):
    terminal["rows"] = {500: "  400 /bin/zsh", 400: "  300 claude", 300: "    1 /sbin/launchd"}
    found = origin.detect("Type A-0412's code: ")
    assert found.kind == NOT_HUMAN and "Claude" in found.reason
    assert terminal["prompts"] == []


def test_an_ancestry_that_cant_be_checked_is_refused(terminal):
    terminal["rows"] = {500: "  400 /bin/zsh"}
    found = origin.detect("Type A-0412's code: ")
    assert found.kind == NOT_HUMAN and "couldn't be checked" in found.reason


def test_no_code_typed_is_refused(terminal):
    terminal["typed"] = "\n"
    assert origin.detect("Type A-0412's code: ").kind == NOT_HUMAN


def test_the_user_is_the_macos_account_not_an_environment_variable(terminal, monkeypatch):
    import pwd, os

    monkeypatch.setenv("USER", "someone-else")
    monkeypatch.setenv("LOGNAME", "someone-else")
    assert origin.detect("code: ").user == pwd.getpwuid(os.getuid()).pw_name


# --- detect_ssh(): the remote origin (for ticket 11) ---------------------------------


@pytest.fixture
def remote(monkeypatch):
    state = {"rows": {500: "  400 /bin/sh", 400: "  300 sshd-session", 300: "    1 /sbin/launchd"}}
    monkeypatch.setattr(origin, "_ps", lambda pid, field: table(state["rows"])(pid, field))
    monkeypatch.setattr(origin, "_start", lambda: 500)
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "approve A-0412")
    return state


def test_an_sshd_ancestor_with_the_forced_command_is_an_ssh_origin(remote):
    assert origin.detect_ssh().kind == SSH


def test_no_forced_command_is_refused(remote, monkeypatch):
    monkeypatch.delenv("SSH_ORIGINAL_COMMAND")
    assert origin.detect_ssh().kind == NOT_HUMAN


def test_no_sshd_ancestor_is_refused(remote):
    remote["rows"] = SHELL
    assert origin.detect_ssh().kind == NOT_HUMAN


def test_a_claude_ancestor_under_sshd_is_refused(remote):
    remote["rows"] = {500: "  400 claude", 400: "  300 sshd-session", 300: "    1 /sbin/launchd"}
    assert origin.detect_ssh().kind == NOT_HUMAN


# --- structure (test strategy v3 E6) ----------------------------------------------------


def test_origin_reads_no_environment_variable_but_the_forced_command_and_no_flag():
    source = Path(origin.__file__).read_text(encoding="utf-8")
    reads = re.findall(r"os\.environ[^\n]*|getenv[^\n]*", source)
    assert reads and all("SSH_ORIGINAL_COMMAND" in line for line in reads), reads
    assert "import click" not in source and "click." not in source


def test_ps_is_called_by_its_full_path_so_path_cant_swap_it():
    assert origin.PS == "/bin/ps"
