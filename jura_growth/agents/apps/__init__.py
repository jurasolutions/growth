"""The daily app PRD factory (prd-jura-app-factory-2026-10-24.md §5.6, §5.7,
block 4).

At 06:30 SGT a headless run reads `jura-growth apps context --json`, picks the
next tool idea, checks any rule it depends on against the official source,
writes a PRD to `prd/templates/prd-app-template.md` in its scratch folder and
files it with `jura-growth apps submit-prd`. The code enforces one PRD a day,
the waiting-pile limit, the template's shape, numbering, duplicates, the
guardrails and the brand gate.

Commands: `jura-growth apps status | context | backlog | submit-prd`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import click

from jura_growth import brand_check, db, timeutil
from jura_growth.agents.apps import backlog, catalog, factory, inputs

NAME = catalog.NAME
MIGRATIONS = Path(__file__).parent / "migrations"
JOB = "app-factory"


# --- plug-in interface -------------------------------------------------------


def channels() -> dict[str, brand_check.Channel]:
    return {
        factory.CHANNEL: brand_check.Channel(
            factory.CHANNEL,
            check=factory.app_copy_check,
            description="Toolbox page copy in an app PRD; no time or money saved claims",
        )
    }


def precheck(job: str, conn: sqlite3.Connection) -> str | None:
    if job != JOB:
        return None
    if not catalog.template_path().exists():
        return f"the app PRD template is missing ({catalog.template_path()})"
    return catalog.limit_reason(conn)


def digest(conn: sqlite3.Connection, day: str) -> dict:
    written = catalog.factory_prd_on(conn, day)
    waiting = len(catalog.waiting())
    figures = {"app_prd_today": None, "app_prds_waiting": waiting, "app_factory_note": None}
    if written:
        first = written[0]
        label = f"{first['app_id']} {first['name']}"
        figures["app_prd_today"] = label
        return {
            "figures": figures,
            "lines": [f"App factory: {label} written ({first['path']}); {waiting} app PRDs waiting to be built."],
            "brief": [f"app PRD: {label}"],
        }
    runs = db.rows(
        conn,
        "SELECT status, summary, error FROM runs WHERE job = ? AND substr(started_at, 1, 10) = ? ORDER BY id DESC",
        (JOB, day),
    )
    if not runs:
        note, brief = "no run today", "no app PRD today"
    elif runs[0]["status"] == "skipped":
        note = f"skipped today: {runs[0]['summary']}"
        brief = f"app PRD skipped ({runs[0]['summary']})"
    elif runs[0]["status"] == "failed":
        note = f"no PRD today; the run failed ({(runs[0]['error'] or '')[:160]})"
        brief = "no app PRD today (run failed)"
    else:
        note = f"no PRD today: {(runs[0]['summary'] or '').strip()[:200]}"
        brief = "no app PRD today"
    figures["app_factory_note"] = note
    return {"figures": figures, "lines": [f"App factory: {note}; {waiting} app PRDs waiting."], "brief": [brief]}


# --- commands ----------------------------------------------------------------


def register(cli: click.Group) -> None:
    cli.add_command(apps)


@click.group("apps")
def apps() -> None:
    """The daily app PRD factory (toolbox tools for jurasolutions.sg/apps)."""


def _overview(conn: sqlite3.Connection) -> dict:
    files = catalog.prd_files()
    entries, registry_status = catalog.registry()
    live = [e for e in entries if e.get("status") == "live"]
    rows = backlog.effective(backlog.load(), prd_files=files, live=live)
    today = timeutil.today_str()
    return {
        "today": today,
        "waiting": {"count": len([f for f in files if f.state == "pending"]), "max": catalog.waiting_max()},
        "next_number": f"APP-{catalog.next_number(conn):03d}",
        "factory_prd_today": catalog.factory_prd_on(conn, today),
        "limit_reason": catalog.limit_reason(conn, today),
        "registry": {"path": str(catalog.registry_path()), "status": registry_status, "entries": len(entries)},
        "live": [{k: e.get(k) for k in ("slug", "name", "description", "category", "tier", "prd", "added")} for e in live],
        "pending": [f.as_dict() for f in files if f.state == "pending"],
        "done": [f.as_dict() for f in files if f.state == "done"],
        "backlog": rows,
    }


@apps.command("status")
def status_cmd() -> str:
    """Waiting PRDs, the next APP number, live tools and the backlog."""
    with db.session() as conn:
        view = _overview(conn)
    click.echo(f"waiting PRDs   {view['waiting']['count']} of {view['waiting']['max']} in prd/pending/apps")
    click.echo(f"next number    {view['next_number']}")
    today = view["factory_prd_today"]
    click.echo("today          " + (", ".join(f"{t['app_id']} {t['name']}" for t in today) if today else "no factory PRD yet"))
    if view["limit_reason"]:
        click.echo(f"limit          {view['limit_reason']}")
    reg = view["registry"]
    if reg["status"] != "ok":
        click.echo(f"live tools     registry {reg['status']}")
    else:
        click.echo(f"live tools     {', '.join(e['name'] for e in view['live']) or 'none yet'} ({reg['entries']} registry entries)")
    for f in view["pending"]:
        click.echo(f"  pending      {f['id']} {f['name']} ({f['tier']}, {f['category']}) {f['path']}")
    for f in view["done"]:
        click.echo(f"  built        {f['id']} {f['name']} {f['path']}")
    click.echo("")
    _print_backlog(view["backlog"])
    return f"{view['waiting']['count']} waiting; next {view['next_number']}"


def _print_backlog(rows: list[dict]) -> None:
    click.echo(f"backlog ({len(rows)})")
    for row in rows:
        click.echo(f"  {(row.get('app_id') or '-'):8} {row['name']:24} {row.get('tier', ''):8} {row.get('category', ''):10} {row['effective_status']}")


@apps.command("backlog")
@click.option("--json", "as_json", is_flag=True)
def backlog_cmd(as_json) -> None:
    """The app backlog (data/growth/app-backlog.yaml), with live status."""
    with db.session() as conn:
        rows = _overview(conn)["backlog"]
    if as_json:
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        _print_backlog(rows)
        click.echo(f"\nfile: {backlog.path()}" + ("" if backlog.path().exists() else " (not written yet; showing the seed)"))


@apps.command("context")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable (what the factory prompt reads).")
def context_cmd(as_json) -> None:
    """Everything the factory run needs, in one call."""
    settings = catalog.settings()
    with db.session() as conn:
        view = _overview(conn)
        view["usage"] = inputs.usage(int(settings.get("usage_days", 7)))
        view["scout_insights"] = inputs.scout_insights(conn, int(settings.get("insights_days", 30)))
    number = view["next_number"].split("-")[1]
    view["files"] = {
        "template": str(catalog.template_path()),
        "examples": [str(catalog.pending_dir() / f["path"].split("/")[-1]) for f in view["pending"][:2]],
        "write_to": f"prd/pending/apps/prd-app-{number}-<slug>-{view['today']}.md (through `jura-growth apps submit-prd`)",
        "backlog": str(backlog.path()),
    }
    view["rules"] = {
        "author_line": "Author: app factory (for Ting Yu)",
        "categories": list(settings.get("categories") or []),
        "official_sources": "any *.gov.sg host (IRAS, MOM, CPF Board, MAS, ACRA)"
        + (", plus " + ", ".join(settings.get("extra_official_domains") or []) if settings.get("extra_official_domains") else ""),
        "source_max_age_days": int(settings.get("official_source_max_age_days", 7)),
        "fetch_required": bool(settings.get("require_fetch_in_run", True)),
    }
    if as_json:
        click.echo(json.dumps(view, indent=2, ensure_ascii=False, default=str))
        return
    for key, value in view.items():
        click.echo(f"{key}: {json.dumps(value, ensure_ascii=False, default=str)[:400]}")


@apps.command("submit-prd")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Run every check, brand check included, without filing, posting or using a brand-gate attempt.")
def submit_prd_cmd(file, dry_run) -> str:
    """Check an app PRD written by the factory and file it in prd/pending/apps/."""
    text = file.read_text(encoding="utf-8")
    with db.session() as conn:
        result = factory.submit(conn, text, dry_run=dry_run)
    for line in result.lines:
        click.echo(line)
    if not result.ok:
        sys.exit(1)
    return result.summary
