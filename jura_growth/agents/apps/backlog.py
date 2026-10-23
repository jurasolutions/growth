"""The app backlog: `data/growth/app-backlog.yaml`.

Seeded from the app factory PRD §5.7 (`backlog-seed.yaml` beside this file).
`jura-growth apps submit-prd` marks the row it used, or adds one for a new
idea. Ting Yu may edit the file by hand; keep the keys.

Statuses: idea, prd-pending (PRD written, waiting for "approved, build"),
prd-done (built; PRD moved to prd/done/apps), live (in the site registry),
dropped (not to be picked).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from jura_growth import paths, timeutil
from jura_growth.agents.apps import prd as prd_mod

SEED = Path(__file__).with_name("backlog-seed.yaml")
STATUSES = ("idea", "prd-pending", "prd-done", "live", "dropped")
HEADER = """\
# Jura app factory backlog. Seeded from prd/pending/prd-jura-app-factory-2026-10-24.md §5.7.
#
# Machine-maintained: `jura-growth apps submit-prd` marks the row it used, or
# adds a row for a new idea. You can edit it by hand; keep the keys.
#
# status: idea | prd-pending | prd-done | live | dropped
#   (`jura-growth apps backlog` also shows the status worked out from the PRD
#   folders and the site registry, which wins if this file is behind.)
# tier: browser | ai. Category: Sales, Finance, Admin, HR, Marketing, Documents.

"""


def path() -> Path:
    return paths.data_dir() / "app-backlog.yaml"


def load() -> list[dict]:
    source = path() if path().exists() else SEED
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    rows = data.get("apps", []) if isinstance(data, dict) else data
    return [dict(r) for r in rows if isinstance(r, dict) and r.get("name")]


def save(rows: list[dict]) -> Path:
    target = paths.writable(path())
    body = yaml.safe_dump({"apps": rows}, sort_keys=False, allow_unicode=True, width=100)
    target.write_text(HEADER + body, encoding="utf-8")
    return target


def seed_if_missing() -> Path | None:
    if path().exists():
        return None
    return save(load())


def find(rows: list[dict], *, slug: str, name: str) -> dict | None:
    wanted = prd_mod.normalise_name(name)
    for row in rows:
        if (row.get("slug") or prd_mod.slugify(row["name"])) == slug:
            return row
        if prd_mod.normalise_name(row["name"]) == wanted:
            return row
    return None


def mark_written(*, name: str, slug: str, app_id: str, prd_path: str, tier: str, category: str, does: str) -> dict:
    rows = load()
    row = find(rows, slug=slug, name=name)
    if row is None:
        row = {"name": name, "slug": slug, "tier": tier, "category": category, "does": does, "status": "idea",
               "notes": f"New idea from the app factory, {timeutil.today_str()}."}
        rows.append(row)
    row.update(
        name=name,
        slug=slug,
        tier=tier,
        category=category,
        status="prd-pending",
        app_id=app_id,
        prd=prd_path,
        prd_date=timeutil.today_str(),
    )
    save(rows)
    return row


def effective(rows: list[dict], *, prd_files: list, live: list[dict]) -> list[dict]:
    """Rows with `effective_status` worked out from the PRD folders and the
    registry (live beats done beats pending beats the file's own status)."""
    by_slug_live = {str(e.get("slug")) for e in live}
    files = {f.slug: f for f in prd_files}
    out = []
    for row in rows:
        slug = row.get("slug") or prd_mod.slugify(row["name"])
        status = row.get("status") or "idea"
        app_id = row.get("app_id")
        if slug in files:
            f = files[slug]
            app_id = app_id or f.app_id
            status = "prd-done" if f.state == "done" else "prd-pending"
        if slug in by_slug_live:
            status = "live"
        out.append({**row, "slug": slug, "app_id": app_id, "effective_status": status})
    return out
