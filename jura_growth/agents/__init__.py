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
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from functools import lru_cache
from types import ModuleType


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
