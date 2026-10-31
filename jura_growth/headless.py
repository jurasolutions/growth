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

The same allowlist becomes the claude job's `--allowedTools` and
`--disallowedTools` (`claude_rules`), so Claude Code refuses a command before
it starts and the code refuses it again if it does start. Those rules also
refuse reading any secret file under `JURA_ROOT` (`paths.SECRET_FILE_PATTERNS`).

**Files.** Every path a command takes (any `click.Path` option or argument, in
the core or a plug-in) goes through `paths.guard()`, so no command can read,
print or upload a secret file, and a run can only use its own folders.

The core never imports an agent by name: it asks the job's agent plug-in.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Callable, Iterator

import click

from jura_growth import agents, config, log, paths, timeutil

# Commands no run may use, whatever a plug-in declares: starting, resuming or
# scheduling jobs, posting or uploading to Discord directly, deciding an
# approval or sending a control command, which only a human may do, and
# settling a publish item whose outcome is unknown (browser publishing §5.7).
# Not `one-pager`: that is a scheduled job's own command. An entry of several
# words matches a command that starts with those words. The `inbox` ones are
# how Ting Yu steers a reply (inbox watch D6, S2): a person's words reach a
# model, so no run may read that list or change a draft, a suppression or an
# item's state.
NEVER = ("run", "resume", "schedule", "discord", "approve", "skip", "approvals", "remote", "publish resolve",
         "inbox done", "inbox draft", "inbox list", "inbox redraft", "inbox reword", "inbox unsuppress")


def never(command: str) -> bool:
    """Whether `command` ("publish resolve A-0001 posted") starts with an entry of `NEVER`,
    matched word by word, so "publish resolve" refuses it and "publish next" doesn't."""
    words = command.split()
    return any(words[: len(entry.split())] == entry.split() for entry in NEVER)


@dataclass(frozen=True)
class Permissions:
    """What a claude job may do, declared by its agent's plug-in.

    commands: `jura-growth` commands as their full names, "scout add-lead" or
        "check"; each one allows its options and arguments.
    disallowed_tools: extra Claude Code deny rules for the job, for example
        "WebFetch(domain:example.com)".
    allowed_tools: extra Claude Code allow rules for the job, for example the publish job's
        Chrome tab tools and `ClaudeInChromeDomain(<host>)` rules (ADR 0005). Never a Bash rule:
        commands are declared in `commands`, so code enforces them too.
    """

    commands: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()


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
    if never(command):
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


# --- Claude Code's own rules for a claude job -----------------------------------


def secret_read_rules() -> list[str]:
    """Read denials for every secret file under jurasolutions/
    (`paths.SECRET_FILE_PATTERNS`) and the configured env file. Read rules
    also cover Grep and Glob."""
    root = paths.JURA_ROOT
    return [f"Read(/{paths.env_file()})", *(f"Read(/{root}/**/{pattern})" for pattern in paths.SECRET_FILE_PATTERNS)]


def claude_rules(job: str) -> tuple[list[str], list[str]]:
    """(allowed, disallowed) Claude Code rules for a claude job: its own
    `jura-growth` commands and help, the plug-in's own extra allow rules, and a
    denial for every other command, for `NEVER`, for secret files, and for the
    plug-in's own extra deny rules.

    Each command is written both bare and with `:*`, so it matches with or
    without arguments.
    """
    from jura_growth.cli import cli

    declared = permissions(job)
    commands = [c for c in declared.commands if not never(c)]
    allowed = ["Bash(jura-growth --help)"]
    allowed += [f"Bash(jura-growth {group} --help)" for group in sorted({c.split()[0] for c in commands if " " in c})]
    for command in commands:
        allowed += [f"Bash(jura-growth {command})", f"Bash(jura-growth {command}:*)"]
    allowed += [rule for rule in declared.allowed_tools if not rule.startswith("Bash")]

    disallowed = secret_read_rules()
    for name in NEVER:  # bare too, for the ones not written yet
        disallowed += [f"Bash(jura-growth {name})", f"Bash(jura-growth {name}:*)"]
    for name, _ in leaves(cli):
        if name in commands:
            continue
        disallowed.append(f"Bash(jura-growth {name})")
        # A prefix rule would also catch an allowed command that starts with
        # this name ("check" and "check-copy"); the bare rule still applies.
        if not any(c.startswith(name) for c in commands):
            disallowed.append(f"Bash(jura-growth {name}:*)")
    disallowed += list(declared.disallowed_tools)
    return allowed, list(dict.fromkeys(disallowed))


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
    return GuardedPath(
        exists=kind.exists,
        file_okay=kind.file_okay,
        dir_okay=kind.dir_okay,
        writable=kind.writable,
        readable=kind.readable,
        resolve_path=kind.resolve_path,
        allow_dash=kind.allow_dash,
        path_type=kind.type,
        executable=kind.executable,
    )


def _enforced(name: str, callback: Callable) -> Callable:
    @functools.wraps(callback)
    def run(*args, **kwargs):
        job = log.current_job()
        if job and not may_use(job, name):
            try:
                log.mirror({
                    "ts": timeutil.stamp(), "agent": log.current_agent(), "level": "warning",
                    "kind": "command.refused", "payload": {"job": job, "command": name},
                })
            except OSError:
                pass  # the refusal stands even if the log can't be written
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
