"""What a scheduled run may do through `jura-growth`.

A scheduled run has `JURA_GROWTH_JOB` set: the runner sets it for a command
job it calls in-process, and passes it to the `claude -p` process of a claude
job, so every `jura-growth` call that session makes carries it.

**Commands.** A run may use only its job's commands:

- a `command` job, the one command it is defined by (`outreach send-due`);
- a `claude` job, the commands its agent's plug-in declares for it through
  `permissions(job) -> Permissions`, which list what `prompts/<job>.md` uses.

Anything else exits with status 2 and a "refused:" line, and the refusal is
logged. No declaration means no commands. `NEVER` is refused to every run,
whatever a plug-in declares. Help (`--help`) is always answered, because it
never runs a command. Outside a run (Ting Yu in Terminal) nothing changes.

**Files.** Every path a command takes (any `click.Path` option or argument, in
the core or a plug-in) goes through `paths.guard()`, so no command can read,
print or upload a secret file, and a run can only use its own folders.

The core never imports an agent by name: it asks the job's agent plug-in.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from typing import Callable, Iterator

import click

from jura_growth import agents, config, log, paths, timeutil

# Commands no run may use, whatever a plug-in declares: starting, resuming or
# scheduling jobs, and posting or uploading to Discord directly.
NEVER = ("run", "resume", "schedule", "discord")


@dataclass(frozen=True)
class Permissions:
    """What a claude job may do, declared by its agent's plug-in.

    commands: `jura-growth` commands as their full names, "scout add-lead" or
        "check"; each one allows its options and arguments.
    disallowed_tools: extra Claude Code deny rules for the job, for example
        "WebFetch(domain:example.com)".
    """

    commands: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()


class Refused(click.ClickException):
    exit_code = 2


def permissions(job: str) -> Permissions:
    """The job's permissions; an unknown job gets none."""
    spec = config.settings()["jobs"].get(job)
    if spec is None:
        return Permissions()
    if spec["kind"] == "command":
        return Permissions(commands=(command_name(spec["command"]),))
    module = agents.by_name(spec["agent"])
    declare = getattr(module, "permissions", None) if module else None
    return (declare(job) if declare else None) or Permissions()


def may_use(job: str, command: str) -> bool:
    if command.split()[0] in NEVER:
        return False
    return command in permissions(job).commands


def command_name(argv: list[str]) -> str:
    """"outreach send-due" for ["outreach", "send-due", "--json"]."""
    from jura_growth.cli import cli

    group: click.Command = cli
    words: list[str] = []
    for word in argv:
        if not isinstance(group, click.Group) or word not in group.commands:
            break
        group = group.commands[word]
        words.append(word)
    return " ".join(words)


# --- enforcement in code -------------------------------------------------------


class GuardedPath(click.Path):
    """A `click.Path` that refuses what `paths.guard()` refuses, before it
    checks whether the file exists."""

    def convert(self, value, param, ctx):
        if not (self.allow_dash and value == "-"):
            try:
                paths.guard(value)
            except paths.PathRefused as error:
                self.fail(str(error), param, ctx)
        return super().convert(value, param, ctx)


def _guarded(kind: click.Path) -> GuardedPath:
    guarded = GuardedPath.__new__(GuardedPath)
    guarded.__dict__.update(kind.__dict__)
    return guarded


def _enforced(name: str, callback: Callable) -> Callable:
    @functools.wraps(callback)
    def run(*args, **kwargs):
        job = os.environ.get("JURA_GROWTH_JOB")
        if job and not may_use(job, name):
            log.mirror({
                "ts": timeutil.stamp(), "agent": log.current_agent(), "level": "warning",
                "kind": "command.refused", "payload": {"job": job, "command": name},
            })
            raise Refused(f"refused: a `{job}` run may not use `jura-growth {name}`")
        return callback(*args, **kwargs)

    run.__jura_enforced__ = True  # type: ignore[attr-defined]
    return run


def leaves(group: click.Group, prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, click.Command]]:
    """Every runnable command under `group`, as ("outreach send-due", command)."""
    for name, command in sorted(group.commands.items()):
        path = (*prefix, name)
        if isinstance(command, click.Group):
            yield from leaves(command, path)
        else:
            yield " ".join(path), command


def install(cli: click.Group) -> None:
    """Enforce the allowlist on every command and guard every path parameter.
    Called once, after the plug-ins have registered their commands."""
    for name, command in leaves(cli):
        if command.callback and not getattr(command.callback, "__jura_enforced__", False):
            command.callback = _enforced(name, command.callback)
        for param in command.params:
            if isinstance(param.type, click.Path) and not isinstance(param.type, GuardedPath):
                param.type = _guarded(param.type)
