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
from functools import lru_cache
from types import ModuleType


@lru_cache(maxsize=None)
def plugins() -> tuple[ModuleType, ...]:
    found = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        found.append(importlib.import_module(f"{__name__}.{info.name}"))
    return tuple(found)


def by_name(name: str) -> ModuleType | None:
    for module in plugins():
        if getattr(module, "NAME", None) == name:
            return module
    return None
