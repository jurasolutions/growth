"""Where a decision comes from (MC §4.6 A8, ADR 0004).

A decision counts only from a human origin: a real terminal with the
request's six-character code typed, or `jura-growth remote` reached through
the SSH forced command from Dispatch. `approvals.decide()` takes an `Origin`
and refuses anything else.

`detect()` is the Terminal check behind `approve` and `skip`: stdin and stdout
are TTYs, no ancestor process is `claude`, and then Ting Yu types the code.
Claude Code's Bash tool has no TTY, and a `! jura-growth approve` typed inside
a Claude session has a `claude` ancestor, so no agent session can decide.
`detect_ssh()` is the check behind `jura-growth remote` (ticket 11): the
forced command's `SSH_ORIGINAL_COMMAND` is set, an `sshd` process is an
ancestor, and no ancestor is `claude`.

The ancestry comes from `/bin/ps -o ppid=,comm=`, walked up to launchd, by
its full path so a `ps` earlier on PATH can't answer. A walk that can't be
finished refuses. Tests pass an `Origin` in process (to `decide()`, or as
`ctx.obj["origin"]`, which only `remote` sets). It is never read from a flag
or an environment variable, which an agent could set; the only variable read
here is `SSH_ORIGINAL_COMMAND`, which sshd sets for the forced command.
"""

from __future__ import annotations

import os
import pwd
import subprocess
import sys
from dataclasses import dataclass

TERMINAL = "terminal"
SSH = "ssh"
NOT_HUMAN = "refused"


@dataclass(frozen=True)
class Origin:
    """Built through `terminal()`, `ssh()` or `refused()`. Built directly,
    it is checked just the same, so no `Origin` skips the rules."""

    kind: str
    user: str | None = None    # the macOS user, for a terminal
    code: str | None = None    # the six hex characters typed, for a terminal
    reason: str | None = None  # why it was refused

    def __post_init__(self) -> None:
        if self.kind == TERMINAL:
            if not self.user or not self.code or self.reason:
                raise ValueError("a terminal origin needs the user and the typed code")
        elif self.kind == SSH:
            if self.user or self.code or self.reason:
                raise ValueError("an SSH origin carries nothing: the actor comes with the command")
        elif self.kind == NOT_HUMAN:
            if not self.reason or self.user or self.code:
                raise ValueError("a refused origin needs the reason, and nothing else")
        else:
            raise ValueError(f"an origin is terminal, ssh or refused, not {self.kind!r}")

    @classmethod
    def terminal(cls, user: str, code: str) -> "Origin":
        return cls(TERMINAL, user=user, code=code)

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
        return self.kind in (TERMINAL, SSH)


NO_TERMINAL = "decisions need a terminal or the Dispatch link"
IN_CLAUDE = "a decision can't come from inside a Claude session"
UNCHECKED = "the process ancestry couldn't be checked"


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
        found.append(Process(pid, ppid, comm, args))
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


def sshd_among(processes: list[Process] | None) -> bool:
    return any(_base(p.comm).startswith("sshd") for p in processes or [])


# --- the checks ---------------------------------------------------------------------


def _start() -> int:
    return os.getpid()


def _both_ttys() -> bool:
    return os.isatty(0) and os.isatty(1)


def _read_line(prompt: str) -> str:
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline()


def _user() -> str:
    """The macOS account running this, from the process's own uid."""
    return pwd.getpwuid(os.getuid()).pw_name


def detect(prompt: str) -> Origin:
    """The Terminal origin for `approve` or `skip`, or why it is refused.
    Asks for the code (with `prompt`) only once the TTYs and the ancestry
    have passed; `decide()` compares it with the request's."""
    if not _both_ttys():
        return Origin.refused(NO_TERMINAL)
    processes = ancestry(_start())
    if processes is None:
        return Origin.refused(UNCHECKED)
    if claude_among(processes):
        return Origin.refused(IN_CLAUDE)
    code = _read_line(prompt).strip()
    if not code:
        return Origin.refused("no code was typed")
    return Origin.terminal(_user(), code)


def detect_ssh() -> Origin:
    """The SSH origin for `jura-growth remote`, or why it is refused."""
    if not os.environ.get("SSH_ORIGINAL_COMMAND"):
        return Origin.refused("control commands come only through the SSH forced command")
    processes = ancestry(_start())
    if processes is None:
        return Origin.refused(UNCHECKED)
    if claude_among(processes):
        return Origin.refused(IN_CLAUDE)
    if not sshd_among(processes):
        return Origin.refused("control commands come only through the SSH forced command")
    return Origin.ssh()
