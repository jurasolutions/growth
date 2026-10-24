"""What a scheduled run may do through `jura-growth`.

**Files.** Every path a command takes (any `click.Path` option or argument, in
the core or a plug-in) goes through `paths.guard()`, so no command can read,
print or upload a secret file, and a run can only use its own folders.
"""

from __future__ import annotations

from typing import Iterator

import click

from jura_growth import paths


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


def leaves(group: click.Group, prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, click.Command]]:
    """Every runnable command under `group`, as ("outreach send-due", command)."""
    for name, command in sorted(group.commands.items()):
        path = (*prefix, name)
        if isinstance(command, click.Group):
            yield from leaves(command, path)
        else:
            yield " ".join(path), command


def install(cli: click.Group) -> None:
    """Guard every path parameter of every command. Called once, after the
    plug-ins have registered their commands."""
    for _, command in leaves(cli):
        for param in command.params:
            if isinstance(param.type, click.Path) and not isinstance(param.type, GuardedPath):
                param.type = _guarded(param.type)
