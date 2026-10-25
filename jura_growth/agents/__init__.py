"""Agent plug-ins.

Each agent (scout, social, community, app factory) is a subpackage here. The
foundation finds them at start-up, so adding an agent never means editing the
core. A plug-in module may define any of:

    NAME: str
        The agent name used for pause flags, runs and Discord usernames.

    MIGRATIONS: pathlib.Path
        A folder of `NNNN_name.sql` files, applied in order after the core
        schema and recorded as `<NAME>/<file>` in `schema_migrations`.

    register(cli: click.Group) -> None
        Add the agent's commands to `jura-growth`.

    channels() -> dict[str, brand_check.Channel]
        Brand-check channels with the agent's own required parts (rule 10).

    digest(conn, day: str) -> dict
        Figures for the daily digest: {"figures": {...}, "lines": [...],
        "brief": [...]}. Lines go to #daily-digest; brief fragments go into the
        one-line morning brief summary.

    precheck(job: str, conn) -> str | None
        Called before a scheduled job starts. Return a reason to skip the run
        (for example "7 app PRDs already waiting"), or None to go ahead.
        Return a `NothingToDo` (for example `NothingToDo("nothing due")`)
        when the run simply has nothing to do: the runner then writes a
        `run.quiet` event with that reason and no run row, whatever the job's
        `quiet` flag (ADR 0001). A plain string is a skip Ting Yu should see.

    permissions(job: str) -> headless.Permissions | None
        For a `claude` job this agent runs: the `jura-growth` commands its
        prompt (`prompts/<job>.md`) uses, and any extra Claude Code deny rules.
        The run may use those commands and no others, in Claude Code's own
        rules and again in code (see `jura_growth/headless.py`). Return None
        for jobs the agent doesn't run.

    after_run(conn, job: str, run_id: int | None, outcome) -> runner.Outcome | None
        Called after the job body of a run that actually started, before its
        run row is finished. Return an `Outcome` to replace the run's final
        outcome (the run row, the #alerts post and auto-pause all see it), or
        None to keep it. An exception is logged as `run.after_run_error` and
        the original outcome stands. `run_id` is None for a quiet command job
        that has no row yet.

    run_update(conn, run) -> list[str] | None
        The "Produced:" lines of this agent's run update (ticket MC-03); None
        posts nothing.

    approval_kinds() -> dict[str, approvals.ApprovalKind]
        The approval kinds this agent owns, by name (MC §4.6, ADR 0003). A
        gated action of one of them claims its approval with
        `approvals.use()`; the agent's pause flag stops the claim. A kind
        two plug-ins declare, or one whose plug-in failed to load, fails
        closed.

The optional hooks are found with `getattr`, like `digest()`, so a plug-in
that defines none of them still loads.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from functools import lru_cache
from types import ModuleType


class NothingToDo(str):
    """What a precheck returns for a run that found nothing to do. The
    runner records it as a quiet run; any other string is a skip."""


BROKEN: dict[str, str] = {}


@lru_cache(maxsize=None)
def plugins() -> tuple[ModuleType, ...]:
    """Every agent plug-in that imports cleanly.

    A plug-in that fails to import is skipped and reported on stderr (and in
    `BROKEN`), so one broken agent never stops the others, the digest or the
    kill switches.
    """
    found = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            found.append(importlib.import_module(f"{__name__}.{info.name}"))
        except Exception as error:  # noqa: BLE001
            BROKEN[info.name] = f"{type(error).__name__}: {error}"
            print(f"warning: agent plug-in {info.name!r} failed to load: {BROKEN[info.name]}", file=sys.stderr)
    return tuple(found)


def by_name(name: str) -> ModuleType | None:
    for module in plugins():
        if getattr(module, "NAME", None) == name:
            return module
    return None
