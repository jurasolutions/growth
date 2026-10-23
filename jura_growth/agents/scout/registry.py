"""The website's toolbox registry, `<JURA_SITE_REPO>/src/apps/registry.json`.

Each email links to one live tool. The registry is the single source of truth
for which tools exist (app factory PRD), so the scout reads it rather than
keeping its own list. Entries: slug, name, description, category, tier,
status ("live" | "draft"), added, prd. Only `live` entries count.

Usage counts (for "industry fit, then usage counts") come from the site's D1
`app_usage` table when Cloudflare is configured; without it they are simply
absent.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from jura_growth import cloudflare, paths, timeutil


def path() -> Path:
    return paths.site_repo() / "src" / "apps" / "registry.json"


def load() -> tuple[list[dict], str | None]:
    """(live tools, problem). `problem` explains an empty list."""
    file = path()
    if not file.exists():
        return [], f"the site registry is missing ({file})"
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except ValueError as error:
        return [], f"the site registry is not valid JSON ({error})"
    if isinstance(data, dict):
        data = data.get("apps") or data.get("entries") or []
    if not isinstance(data, list):
        return [], "the site registry is not a list"
    live = [
        entry
        for entry in data
        if isinstance(entry, dict) and entry.get("status") == "live" and entry.get("slug")
    ]
    if not live:
        return [], f"the site registry has no live tools yet ({file})"
    return live, None


def live_slugs() -> set[str]:
    tools, _ = load()
    return {t["slug"] for t in tools}


def get(slug: str) -> dict | None:
    for tool in load()[0]:
        if tool["slug"] == slug:
            return tool
    return None


def usage(days: int = 30) -> dict[str, dict]:
    """{slug: {"opens": n, "completions": n}} over `days`, or {} if unavailable."""
    if not cloudflare.configured():
        return {}
    since = (timeutil.today() - timedelta(days=days)).isoformat()
    try:
        rows = cloudflare.query(
            "SELECT app_slug, sum(opens) AS opens, sum(completions) AS completions FROM app_usage "
            "WHERE day >= ? GROUP BY app_slug",
            [since],
        )
    except cloudflare.D1Error:
        return {}
    return {
        r["app_slug"]: {"opens": int(r.get("opens") or 0), "completions": int(r.get("completions") or 0)}
        for r in rows
        if r.get("app_slug")
    }
