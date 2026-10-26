"""Where a decision comes from (MC §4.6 A8 as amended 2026-10-26, ADR 0004).

A decision counts only when it comes from Dispatch over SSH: `jura-growth
remote`, reached through the forced command on the growth Mac, carrying Ting
Yu's Discord user id. `approvals.decide()` takes an `Origin` and refuses
anything but `Origin.ssh()`.

Terminal decisions are off (Ting Yu, 2026-10-26). A crew review showed that a
process started from an interactive Claude session can leave the session's
process tree, give itself a terminal and type a code that isn't secret. So
`jura-growth approve` and `skip` typed in Terminal refuse, and point to
#approvals. A Touch ID ticket may bring them back.

`detect_ssh()` is the check `remote` (ticket 11) runs before it builds
`Origin.ssh()`:

- the forced command's `SSH_ORIGINAL_COMMAND` is set;
- an `sshd` process running as root is an ancestor, from `/bin/ps -o
  ppid=,comm=` walked up to launchd, by its full path so a `ps` earlier on PATH
  can't answer; a walk that can't be finished refuses. Root matters: a name
  is only a file name, and any process can run a symlink called `sshd` (code
  review 11). The real daemon's privileged monitor runs as root above every
  session, and no process running as Ting Yu's user can start a root one;
- no ancestor is `claude`;
- none of Claude Code's environment markers (`CLAUDE_MARKERS`) is set. They
  survive a process leaving the session's tree, so they catch every casual
  route out; only deliberate stripping gets past them, and that still needs
  an `sshd` ancestor.

An origin is never granted from a flag or an environment variable, which an
agent could set: the variables read here can only refuse. Tests pass an
`Origin` in process (to `decide()`, or as `ctx.obj["origin"]`, which only
`remote` sets).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

SSH = "ssh"
NOT_HUMAN = "refused"

# Set by Claude Code in every process it starts, and kept by their children.
CLAUDE_MARKERS = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID")

TERMINAL_OFF = "decisions aren't taken in Terminal: approve or skip it in #approvals"
NOT_DISPATCH = "decisions come only from Dispatch, through the SSH forced command"
IN_CLAUDE = "a decision can't come from inside a Claude session"
UNCHECKED = "the process ancestry couldn't be checked"


@dataclass(frozen=True)
class Origin:
    """Built through `ssh()` or `refused()`. Built directly, it is checked
    just the same, so no `Origin` skips the rules."""

    kind: str
    reason: str | None = None  # why it was refused

    def __post_init__(self) -> None:
        if self.kind == SSH:
            if self.reason:
                raise ValueError("an SSH origin carries nothing: the actor comes with the command")
        elif self.kind == NOT_HUMAN:
            if not self.reason:
                raise ValueError("a refused origin needs the reason")
        else:
            raise ValueError(f"an origin is ssh or refused, not {self.kind!r}")

    @classmethod
    def ssh(cls) -> "Origin":
        """`jura-growth remote` under the forced command. The Discord actor
        comes with the command (`--actor`), as attribution."""
        return cls(SSH)

    @classmethod
    def refused(cls, reason: str) -> "Origin":
        return cls(NOT_HUMAN, reason=reason or "not a human origin")

    @property
    def human(self) -> bool:
        return self.kind == SSH


# --- the process ancestry -----------------------------------------------------------

PS = "/bin/ps"
MAX_DEPTH = 64
# Interpreters that may be running Claude Code from a script (an npm install).
_HOSTS = {"node", "bun", "deno"}


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    comm: str
    args: str | None = None  # only for an interpreter, to see what it runs
    uid: int | None = None  # only for an `sshd`, to see that it is the real, root one


def _ps(pid: int, field: str) -> str | None:
    """One `ps -o <field> -p <pid>` line, or None if ps can't say."""
    try:
        result = subprocess.run([PS, "-o", field, "-p", str(pid)], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = result.stdout.strip()
    return line if result.returncode == 0 and line else None


def parse(line: str) -> tuple[int, str]:
    """`(ppid, comm)` from a `ps -o ppid=,comm=` line; comm may hold spaces."""
    parts = line.strip().split(None, 1)
    if len(parts) != 2 or not parts[0].isdigit():
        raise ValueError(f"not a ps line: {line!r}")
    return int(parts[0]), parts[1].strip()


def _base(name: str) -> str:
    return os.path.basename(name.strip()).lower()


def ancestry(pid: int, *, ps=None) -> list[Process] | None:
    """`pid` and every ancestor up to launchd (pid 1), nearest first, or None
    when the walk can't be finished (ps fails, loops or runs too deep)."""
    ps = ps or _ps
    found: list[Process] = []
    seen: set[int] = set()
    while pid > 1:
        if pid in seen or len(found) >= MAX_DEPTH:
            return None
        seen.add(pid)
        line = ps(pid, "ppid=,comm=")
        if line is None:
            return None
        try:
            ppid, comm = parse(line)
        except ValueError:
            return None
        args = ps(pid, "args=") if _base(comm) in _HOSTS else None
        uid = _uid(ps(pid, "uid=")) if _is_sshd_named(comm) else None
        found.append(Process(pid, ppid, comm, args, uid))
        pid = ppid
    return found


def _is_claude(process: Process) -> bool:
    if _base(process.comm) == "claude":
        return True
    if process.args:
        words = process.args.split()[:3]
        return any(_base(word) == "claude" or "claude-code" in word for word in words)
    return False


def claude_among(processes: list[Process] | None) -> bool:
    return any(_is_claude(p) for p in processes or [])


def _is_sshd_named(comm: str) -> bool:
    return _base(comm).startswith("sshd")


def _uid(line: str | None) -> int | None:
    text = (line or "").strip()
    return int(text) if text.isdigit() else None


def sshd_among(processes: list[Process] | None) -> bool:
    """An `sshd` ancestor running as root. A user-owned one is only a name."""
    return any(_is_sshd_named(p.comm) and p.uid == 0 for p in processes or [])


# --- the check ----------------------------------------------------------------------


def _start() -> int:
    return os.getpid()


def claude_marker() -> str | None:
    """The first of Claude Code's environment markers that is set, or None.
    Reading it can only refuse an origin, never grant one."""
    return next((name for name in CLAUDE_MARKERS if os.environ.get(name)), None)


def detect_ssh() -> Origin:
    """The SSH origin for `jura-growth remote`, or why it is refused."""
    if claude_marker():
        return Origin.refused(IN_CLAUDE)
    if not os.environ.get("SSH_ORIGINAL_COMMAND"):
        return Origin.refused(NOT_DISPATCH)
    processes = ancestry(_start())
    if processes is None:
        return Origin.refused(UNCHECKED)
    if claude_among(processes):
        return Origin.refused(IN_CLAUDE)
    if not sshd_among(processes):
        return Origin.refused(NOT_DISPATCH)
    return Origin.ssh()
