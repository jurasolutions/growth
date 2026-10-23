"""The website's toolbox registry (`src/apps/registry.json` in the landing-page
repo), read-only.

Each entry: {slug, name, description, category, tier: browser|ai,
status: live|draft, added: YYYY-MM-DD, prd: APP-NNN}. Only live tools are
offered. The file may not exist yet (it arrives with the toolbox branch);
that is a note, not an error.

"Most used" needs usage counts. They live in the website's D1 database
(`app_usage`); if a copy has been synced into growth.db as a table of the
same name, it is used, otherwise tools are ranked by newest only.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from jura_growth import paths

REGISTRY = Path("src") / "apps" / "registry.json"


@dataclass(frozen=True)
class Tool:
    slug: str
    name: str
    description: str
    category: str = ""
    tier: str = "browser"
    status: str = "live"
    added: str = ""
    prd: str = ""

    def url(self, site: str) -> str:
        return f"{site.rstrip('/')}/apps/{self.slug}"

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def registry_path() -> Path:
    return paths.site_repo() / REGISTRY


def load() -> tuple[list[Tool], str | None]:
    """(tools, note). The note says why the list is empty when it is."""
    path = registry_path()
    if not path.exists():
        return [], f"no toolbox registry at {path} yet"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [], f"toolbox registry unreadable ({type(error).__name__}: {error})"
    if not isinstance(data, list):
        return [], "toolbox registry is not a list"
    tools = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("slug") or not entry.get("name"):
            continue
        tools.append(
            Tool(
                slug=str(entry["slug"]),
                name=str(entry["name"]),
                description=str(entry.get("description", "")),
                category=str(entry.get("category", "")),
                tier=str(entry.get("tier", "browser")),
                status=str(entry.get("status", "draft")),
                added=str(entry.get("added", "")),
                prd=str(entry.get("prd", "")),
            )
        )
    live = [t for t in tools if t.status == "live"]
    if not live:
        return [], "no live tools in the toolbox registry yet"
    return live, None


def find(slug: str) -> Tool | None:
    tools, _ = load()
    return next((t for t in tools if t.slug == slug), None)


def usage(conn: sqlite3.Connection | None, day: date, days: int = 30) -> dict[str, int]:
    """{slug: opens + completions over the last `days`}, if usage is available."""
    if conn is None:
        return {}
    table = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'app_usage'").fetchone()
    if not table:
        return {}
    columns = {row[1] for row in conn.execute("PRAGMA table_info(app_usage)")}
    if not {"day", "app_slug"} <= columns:
        return {}
    measures = [c for c in ("opens", "completions") if c in columns] or ["1"]
    start = (day - timedelta(days=days)).isoformat()
    try:
        rows = conn.execute(
            f"SELECT app_slug, sum({' + '.join(measures)}) FROM app_usage WHERE day >= ? GROUP BY app_slug",
            (start,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {row[0]: int(row[1] or 0) for row in rows}


def plan(conn: sqlite3.Connection | None, day: date, used: dict[str, str]) -> dict:
    """Newest and most-used live tools, and which are free to feature today."""
    tools, note = load()
    counts = usage(conn, day)
    newest = sorted(tools, key=lambda t: (t.added, t.name), reverse=True)
    most_used = sorted((t for t in tools if counts.get(t.slug)), key=lambda t: counts[t.slug], reverse=True)
    eligible = [t for t in newest if t.slug not in used]
    return {
        "registry": str(registry_path()),
        "note": note,
        "live": [t.as_dict() for t in newest],
        "newest": newest[0].as_dict() if newest else None,
        "most_used": [dict(t.as_dict(), uses_30_days=counts[t.slug]) for t in most_used[:3]],
        "usage_available": bool(counts),
        "eligible": [t.as_dict() for t in eligible],
        "used_recently": used,
    }
