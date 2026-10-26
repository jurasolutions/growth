"""The app backlog: `data/growth/app-backlog.yaml`.

Seeded from the app factory PRD §5.7 (`backlog-seed.yaml` beside this file).
`jura-growth apps submit-prd` marks the row it used, or adds one for a new
idea. Ting Yu may edit the file by hand; keep the keys.

Statuses: idea, prd-pending (PRD written, waiting for its `app-build`
decision in #approvals, or handed off to be built), prd-done (built; PRD moved
to prd/done/apps), live (in the site registry), dropped (not to be picked;
Ting Yu skipped its PRD). An idea whose PRD expired unanswered keeps status
idea with a `reopens` date, and shows as `resting` until then (MC §5.9 step 5).
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
#   An idea with a `reopens` date had its PRD expire unanswered: it shows as
#   `resting`, and the factory may offer it again from that date.
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


def _row_for(rows: list[dict], *, app_id: str, slug: str | None, name: str | None) -> dict | None:
    for row in rows:
        if row.get("app_id") == app_id:
            return row
    return find(rows, slug=slug, name=name) if slug and name else None


def _note(row: dict, note: str) -> str:
    return f"{(row.get('notes') or '').strip()} {note}".strip()


def drop(*, app_id: str, slug: str | None, name: str | None, note: str) -> dict | None:
    """Ting Yu skipped the app's PRD: the idea closes for good."""
    rows = load()
    row = _row_for(rows, app_id=app_id, slug=slug, name=name)
    if row is None:
        return None
    row.update(status="dropped", notes=_note(row, note))
    save(rows)
    return row


def rest(*, app_id: str, slug: str | None, name: str | None, note: str, reopens: str) -> dict | None:
    """The app's PRD expired unanswered: the idea is an idea again, offered from `reopens`."""
    rows = load()
    row = _row_for(rows, app_id=app_id, slug=slug, name=name)
    if row is None:
        return None
    for key in ("app_id", "prd", "prd_date"):
        row.pop(key, None)
    row.update(status="idea", reopens=reopens, notes=_note(row, f"{note} Offered again from {reopens}."))
    save(rows)
    return row


def release(*, app_id: str, slug: str | None, name: str | None, prd_path: str, note: str) -> dict | None:
    """The app's build is on jurasolutions.sg (`apps released`): live, with its PRD in prd/done/apps."""
    rows = load()
    row = _row_for(rows, app_id=app_id, slug=slug, name=name)
    if row is None:
        return None
    row.update(status="live", prd=prd_path, released=timeutil.today_str(), notes=_note(row, note))
    save(rows)
    return row


def resting(row: dict, today: str | None = None) -> bool:
    """An idea whose PRD expired unanswered, before its `reopens` date."""
    reopens = row.get("reopens")
    return (row.get("status") or "idea") == "idea" and bool(reopens) and str(reopens) > (today or timeutil.today_str())


def effective(rows: list[dict], *, prd_files: list, live: list[dict]) -> list[dict]:
    """Rows with `effective_status` worked out from the PRD folders and the
    registry (live beats done beats pending beats the file's own status)."""
    by_slug_live = {str(e.get("slug")) for e in live}
    files = {f.slug: f for f in prd_files}
    out = []
    for row in rows:
        slug = row.get("slug") or prd_mod.slugify(row["name"])
        status = row.get("status") or "idea"
        if resting(row):
            status = "resting"
        app_id = row.get("app_id")
        if slug in files:
            f = files[slug]
            app_id = app_id or f.app_id
            status = "prd-done" if f.state == "done" else "prd-pending"
        if slug in by_slug_live:
            status = "live"
        out.append({**row, "slug": slug, "app_id": app_id, "effective_status": status})
    return out
