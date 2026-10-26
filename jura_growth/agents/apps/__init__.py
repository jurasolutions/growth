"""The daily app PRD factory (prd-jura-app-factory-2026-10-24.md §5.6, §5.7,
block 4).

At 06:30 SGT a headless run reads `jura-growth apps context --json`, picks the
next tool idea, checks any rule it depends on against the official source,
writes a PRD to `prd/templates/prd-app-template.md` in its scratch folder and
files it with `jura-growth apps submit-prd`. The code enforces one PRD a day,
the waiting-pile limit, the template's shape, numbering, duplicates, the
guardrails and the brand gate.

Each filed PRD waits for an `app-build` decision in #approvals; approving it
writes a build handoff (`builds.py`, MC §5.9). The finished build waits for a
second, `app-release` decision bound to its commit (`releases.py`).

Commands: `jura-growth apps status | context | backlog | submit-prd | handoffs
| built | release-plan | released`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import click

from jura_growth import approval_settings, brand_check, cards, db, log, timeutil
from jura_growth.agents.apps import backlog, builds, catalog, factory, inputs, releases

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


def permissions(job: str):
    """The `jura-growth` commands `prompts/app-factory.md` uses, plus
    `scout insights`, which `apps context` reads in-process."""
    if job != JOB:
        return None
    from jura_growth.headless import Permissions

    return Permissions(commands=("apps context", "apps submit-prd", "check", "scout insights"))


def precheck(job: str, conn: sqlite3.Connection) -> str | None:
    """Before the 06:30 run: the catch-up pass first, so PRDs filed before requests existed count
    toward the waiting pile and get their cards, then the limits."""
    if job != JOB:
        return None
    if not catalog.template_path().exists():
        return f"the app PRD template is missing ({catalog.template_path()})"
    if builds.raise_waiting(conn):
        cards.sweep_safely(conn)
    return catalog.limit_reason(conn)


def approval_kinds() -> dict:
    return {builds.KIND: builds.AppBuild(), releases.KIND: releases.AppRelease()}


def health(conn: sqlite3.Connection) -> list[str]:
    """Build handoffs waiting for a builder (MC §5.4), on the read model's read-only connection."""
    return builds.health_lines(conn)


def digest(conn: sqlite3.Connection, day: str) -> dict:
    written = catalog.factory_prd_on(conn, day)
    waiting = len(catalog.waiting(conn))
    figures = {"app_prd_today": None, "app_prds_waiting": waiting, "app_factory_note": None}
    if written:
        first = written[0]
        label = f"{first['app_id']} {first['name']}"
        figures["app_prd_today"] = label
        return {
            "figures": figures,
            "lines": [f"App factory: {label} written ({first['path']}); {waiting} app PRDs waiting for a decision."],
            "brief": [f"app PRD: {label}"],
        }
    runs = db.rows(
        conn,
        "SELECT status, summary, error FROM runs WHERE job = ? AND substr(started_at, 1, 10) = ? ORDER BY id DESC",
        (JOB, day),
    )
    # The digest's lines name no day: the digest is headed with its date, and
    # the one-pager repeats them under "Yesterday" (MC X15).
    if not runs:
        note, brief = "no run", "no app PRD today"
    elif runs[0]["status"] == "skipped":
        note = f"skipped: {runs[0]['summary']}"
        brief = f"app PRD skipped ({runs[0]['summary']})"
    elif runs[0]["status"] == "failed":
        note = f"no PRD; the run failed ({(runs[0]['error'] or '')[:160]})"
        brief = "no app PRD today (run failed)"
    else:
        note = f"no PRD: {(runs[0]['summary'] or '').strip()[:200]}"
        brief = "no app PRD today"
    figures["app_factory_note"] = note
    return {"figures": figures, "lines": [f"App factory: {note}; {waiting} app PRDs waiting."], "brief": [brief]}


RUN_UPDATE_DISCORD_CHANNEL = "app-factory"


def run_update(conn: sqlite3.Connection, run) -> list[str]:
    """The "Produced:" items of a factory run: the app PRDs it filed, by id."""
    from jura_growth.run_update import count

    ids = [r["app_id"] for r in db.rows(conn, "SELECT app_id FROM app_prds WHERE run_id = ? ORDER BY id", (run.id,))]
    return [f"{count(len(ids), 'app PRD')} ({', '.join(ids)})"] if ids else []


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
        "waiting": {"count": len(catalog.waiting(conn)), "max": catalog.waiting_max()},
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
    click.echo(f"waiting PRDs   {view['waiting']['count']} of {view['waiting']['max']} waiting for an app-build decision")
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
        if not dry_run:
            builds.raise_waiting(conn, run_id=log.current_run_id())
        result = factory.submit(conn, text, dry_run=dry_run)
        if not dry_run:
            cards.sweep_safely(conn)  # the cards go out once the requests are committed (A12)
    for line in result.lines:
        click.echo(line)
    if not result.ok:
        sys.exit(1)
    return result.summary


@apps.command("handoffs")
@click.option("--json", "as_json", is_flag=True, help="What Dispatch polls: each open handoff with its PRD text and SHA-256.")
def handoffs_cmd(as_json) -> None:
    """Build handoffs waiting for a builder, oldest first."""
    with db.session() as conn:
        if as_json:
            click.echo(json.dumps(builds.handoffs_json(conn), indent=2, ensure_ascii=False))
            return
        waiting = builds.open_handoffs(conn)
    if not waiting:
        click.echo("No build handoffs are waiting.")
        return
    dispatch = approval_settings.switch("dispatch_builds")
    for build in waiting:
        click.echo(f"{build['app_id']} {build['name']} · approval {build['approval_id']} · handed off "
                   f"{build['handed_off_at'][:16].replace('T', ' ')} · {build['prd_path']} · sha256 {build['prd_sha256'][:12]}")
        click.echo("  handed to Dispatch" if dispatch else f"  {builds.build_it(build['prd_path'], build['approval_id'])}")


@apps.command("built")
@click.argument("app_id")
@click.option("--task", required=True, help="The Dispatch task that built it, e.g. T-0031.")
@click.option("--branch", required=True, help="The task branch, based on main.")
@click.option("--sha", required=True, help="The branch's full head commit SHA.")
@click.option("--preview", required=True, help="The branch's Cloudflare Pages preview link.")
def built_cmd(app_id, task, branch, sha, preview) -> str:
    """Report a handed-off build as built, and ask for its release in #approvals."""
    with db.session() as conn:
        outcome = releases.report_built(conn, app_id, task=task, branch=branch, sha=sha, preview=preview,
                                        run_id=log.current_run_id())
        if outcome.ok:
            cards.sweep_safely(conn)  # the card goes out once the request is committed (A12)
    for line in outcome.lines:
        click.echo(line)
    if not outcome.ok:
        sys.exit(1)
    return outcome.lines[0]


@apps.command("release-plan")
@click.argument("app_id")
def release_plan_cmd(app_id) -> str:
    """Claim the approved release and print the merge of exactly its commit into main."""
    with db.session() as conn:
        outcome = releases.plan_release(conn, app_id, run_id=log.current_run_id(), emit=click.echo)
        cards.sweep_safely(conn, post=False)  # the card's first line says it was claimed
    if not outcome.ok:
        for line in outcome.lines:
            click.echo(line)
        sys.exit(1)
    return outcome.lines[0]


@apps.command("released")
@click.argument("app_id")
@click.option("--task", required=True, help="The task whose build was merged, e.g. T-0031.")
def released_cmd(app_id, task) -> str:
    """Record a release once main of the landing-page repository holds the approved commit."""
    with db.session() as conn:
        outcome = releases.record_released(conn, app_id, task=task)
    for line in outcome.lines:
        click.echo(line)
    if not outcome.ok:
        sys.exit(1)
    return outcome.lines[0]
