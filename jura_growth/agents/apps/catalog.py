"""What apps exist: PRDs waiting in `prd/pending/apps/`, built ones in
`prd/done/apps/`, live tools in the site's registry, and the factory's own
record of what it wrote (`app_prds`).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from jura_growth import caps, config, db, paths, timeutil
from jura_growth.agents.apps import prd as prd_mod

NAME = "app-factory"


@dataclass
class PrdFile:
    path: Path
    state: str  # pending or done
    app_id: str
    number: int
    slug: str
    day: str
    name: str
    tier: str
    category: str
    author: str

    def as_dict(self) -> dict:
        return {
            "id": self.app_id,
            "name": self.name,
            "slug": self.slug,
            "tier": self.tier,
            "category": self.category,
            "state": self.state,
            "date": self.day,
            "author": self.author,
            "path": rel(self.path),
        }


def settings() -> dict:
    return config.agent_config("apps")


def pending_dir() -> Path:
    return paths.prd_dir() / "pending" / "apps"


def done_dir() -> Path:
    return paths.prd_dir() / "done" / "apps"


def template_path() -> Path:
    return paths.prd_dir() / "templates" / "prd-app-template.md"


def registry_path() -> Path:
    return paths.site_repo() / "src" / "apps" / "registry.json"


def rel(path: Path) -> str:
    """A path relative to jurasolutions/ when it sits inside it."""
    try:
        return str(Path(path).resolve().relative_to(paths.JURA_ROOT.resolve()))
    except ValueError:
        try:
            return "prd/" + str(Path(path).resolve().relative_to(paths.prd_dir().resolve()))
        except ValueError:
            return str(path)


def prd_files() -> list[PrdFile]:
    found = []
    for state, folder in (("pending", pending_dir()), ("done", done_dir())):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("prd-app-*.md")):
            m = prd_mod.FILENAME_RE.match(path.name)
            if not m:
                continue
            try:
                parsed = prd_mod.parse(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            found.append(
                PrdFile(
                    path=path,
                    state=state,
                    app_id=f"APP-{int(m['num']):03d}",
                    number=int(m["num"]),
                    slug=m["slug"],
                    day=m["day"],
                    name=parsed.name or m["slug"].replace("-", " ").capitalize(),
                    tier=parsed.tier,
                    category=parsed.category,
                    author=parsed.author,
                )
            )
    return found


def waiting() -> list[PrdFile]:
    return [f for f in prd_files() if f.state == "pending"]


def waiting_max() -> int:
    return caps.effective(caps.APP_PRDS_WAITING_MAX, settings().get("waiting_max"))


def per_day() -> int:
    return caps.effective(caps.APP_PRDS_PER_DAY, settings().get("prds_per_day"))


def registry() -> tuple[list[dict], str]:
    """(entries, status). Status is "ok", or why the registry can't be read."""
    path = registry_path()
    if not path.exists():
        return [], f"not found at {path} (the toolbox shell isn't on this branch yet)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [], f"unreadable ({type(error).__name__})"
    if isinstance(data, dict):
        data = data.get("apps", [])
    if not isinstance(data, list):
        return [], "unexpected shape (expected a list of entries)"
    return [e for e in data if isinstance(e, dict)], "ok"


def live_apps() -> list[dict]:
    entries, _ = registry()
    return [e for e in entries if e.get("status") == "live"]


def numbers_in_use(conn: sqlite3.Connection | None = None) -> set[int]:
    used = {f.number for f in prd_files()}
    entries, _ = registry()
    for entry in entries:
        m = re.match(r"^APP-(\d+)$", str(entry.get("prd", "")))
        if m:
            used.add(int(m.group(1)))
    from jura_growth.agents.apps import backlog

    for row in backlog.load():
        m = re.match(r"^APP-(\d+)$", str(row.get("app_id") or ""))
        if m:
            used.add(int(m.group(1)))
    if conn is not None:
        for row in db.rows(conn, "SELECT app_id FROM app_prds"):
            m = re.match(r"^APP-(\d+)$", row["app_id"])
            if m:
                used.add(int(m.group(1)))
    return used


def next_number(conn: sqlite3.Connection | None = None) -> int:
    used = numbers_in_use(conn)
    return (max(used) + 1) if used else 1


def taken(conn: sqlite3.Connection | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """Slugs and names already used by a live, pending or built app, or by a
    backlog row that already has a PRD."""
    slugs: dict[str, str] = {}
    names: dict[str, str] = {}
    for entry in registry()[0]:
        where = f"{entry.get('status', 'listed')} in the site registry"
        if entry.get("slug"):
            slugs.setdefault(str(entry["slug"]), where)
        if entry.get("name"):
            names.setdefault(prd_mod.normalise_name(str(entry["name"])), where)
    for f in prd_files():
        where = f"{f.app_id}, {f.state}"
        slugs.setdefault(f.slug, where)
        names.setdefault(prd_mod.normalise_name(f.name), where)
    from jura_growth.agents.apps import backlog

    for row in backlog.load():
        if row.get("status") in (None, "idea"):
            continue
        where = f"backlog: {row.get('app_id') or row.get('status')}"
        slugs.setdefault(str(row.get("slug") or prd_mod.slugify(row["name"])), where)
        names.setdefault(prd_mod.normalise_name(row["name"]), where)
    if conn is not None:
        for row in db.rows(conn, "SELECT app_id, slug, name FROM app_prds"):
            slugs.setdefault(row["slug"], f"{row['app_id']}, written by the factory")
            names.setdefault(prd_mod.normalise_name(row["name"]), f"{row['app_id']}, written by the factory")
    return slugs, names


def factory_prd_on(conn: sqlite3.Connection, day: str) -> list[dict]:
    """PRDs the factory wrote on `day`, from its table and, if the database was
    reset, from the files themselves (author line and date)."""
    rows = db.rows(conn, "SELECT app_id, name, slug, path FROM app_prds WHERE day = ? ORDER BY id", (day,))
    seen = {r["app_id"] for r in rows}
    for f in prd_files():
        if f.day == day and f.author == prd_mod.FACTORY_AUTHOR and f.app_id not in seen:
            rows.append({"app_id": f.app_id, "name": f.name, "slug": f.slug, "path": rel(f.path)})
    return rows


def limit_reason(conn: sqlite3.Connection, day: str | None = None) -> str | None:
    """Why the factory must not write a PRD today, or None."""
    day = day or timeutil.today_str()
    written = factory_prd_on(conn, day)
    if len(written) >= per_day():
        first = written[0]
        return f"app PRD already written today ({first['app_id']} {first['name']}); one a day"
    count = len(waiting())
    if count >= waiting_max():
        return f"{count} app PRDs waiting in prd/pending/apps (limit {waiting_max()}); skipping until some are built"
    dropped = db.one(conn, "SELECT attempts FROM qa_attempts WHERE item_key = ?", (gate_key(day),))
    from jura_growth import gate

    if dropped and dropped["attempts"] >= gate.MAX_ATTEMPTS:
        return "today's app PRD failed the brand check twice and was dropped"
    return None


def gate_key(day: str) -> str:
    return f"app-prd:{day}"
