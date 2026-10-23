"""`jura-growth scout ...`: what the 09:00 research session calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from jura_growth import db, timeutil
from jura_growth.agents.scout import icp, leads, registry, settings


def _echo_json(value) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise click.UsageError(f"{path} is not valid JSON: {error}") from None


@click.group("scout")
def scout_group() -> None:
    """Lead research and qualification (scout PRD §5.1–5.2)."""


@scout_group.command("today")
@click.option("--json", "as_json", is_flag=True)
def today(as_json) -> None:
    """Today's industries, lead target, threshold, queue room and tools."""
    from jura_growth.agents.outreach import sync

    with db.session() as conn:
        added = leads.added_today(conn)
        queued = db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'queued'") or 0
        unqueued = len(leads.recent(conn, days=14, status="new"))
        follow_ups = len(sync.follow_ups_due(conn))
    tools, problem = registry.load()
    target = settings.daily_target()
    info = {
        "date": timeutil.today_str(),
        "industries": icp.todays_industries(),
        "daily_target": target,
        "added_today": added,
        "remaining": max(0, target - added),
        "score_threshold": settings.score_threshold(),
        "queue": {"queued": queued, "max_queue": settings.max_queue(), "room": max(0, settings.max_queue() - queued)},
        "leads_waiting_for_an_email": unqueued,
        "follow_ups_due": follow_ups,
        "tools": [t["slug"] for t in tools],
        "tools_problem": problem,
        "icp": str(icp.path()),
        "icp_missing": icp.missing_reason(),
        "mode": settings.mode(),
    }
    if as_json:
        _echo_json(info)
        return
    click.echo(f"date              {info['date']}")
    click.echo(f"industries        {', '.join(info['industries']) or 'none (check the ICP)'}")
    click.echo(f"leads             {added} added today, target {target}, {info['remaining']} to go")
    click.echo(f"score threshold   {info['score_threshold']}")
    click.echo(f"queue             {queued} queued, room for {info['queue']['room']}")
    click.echo(f"waiting for email {unqueued} recent leads with an address and no email yet")
    click.echo(f"follow-ups due    {follow_ups}")
    click.echo(f"tools             {', '.join(info['tools']) or problem}")
    if info["icp_missing"]:
        click.echo(f"ICP               {info['icp_missing']}")


@scout_group.command("check")
@click.argument("value")
@click.option("--json", "as_json", is_flag=True)
def check(value, as_json) -> None:
    """Is a domain, website, address or company name already known? Exit 1 if so."""
    with db.session() as conn:
        found = leads.check(conn, value)
    if as_json:
        _echo_json(found)
    elif found["known"]:
        click.echo("known: " + "; ".join(found["reasons"]))
    else:
        click.echo("not known")
        if found["looked_at_before"]:
            before = found["looked_at_before"]
            click.echo(f"looked at on {before['on']} and turned down: {before['reason']}")
    sys.exit(1 if found["known"] else 0)


@scout_group.command("add-lead")
@click.option("--file", "file_", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path), help="The lead as JSON.")
@click.option("--json", "as_json", is_flag=True)
def add_lead(file_, as_json) -> None:
    """Add a qualified lead. The contact rules are checked here, in code.

    \b
    {
      "company": "Acme Aircon Services Pte Ltd",
      "website": "https://acmeaircon.sg",
      "industry": "field service and maintenance",
      "size_signal": "12 technicians listed on the team page",
      "what_they_do": "Aircon servicing for homes and offices",
      "observations": ["Customers request quotes through a form and wait for a reply"],
      "source_urls": ["https://acmeaircon.sg/services"],
      "score": 72,
      "score_reasons": ["Field service is in the ICP", "Quotes requested by form"],
      "tool": "quote-builder",
      "contact": {"email": "info@acmeaircon.sg", "source_url": "https://acmeaircon.sg/contact"}
    }

    For a contact form only: "contact": {"form_url": "https://..."}.
    A named address also needs "enquiry_contact": true in contact.
    Exit 0 when added, 1 when rejected.
    """
    data = _read_json(file_)
    with db.session() as conn:
        try:
            outcome = leads.add_lead(conn, data)
        except leads.LeadError as error:
            raise click.UsageError(str(error)) from None
    if as_json:
        _echo_json(outcome.as_dict())
    elif outcome.status == "added":
        click.echo(f"added lead {outcome.lead_id} (channel {outcome.channel})")
        for note in outcome.notes:
            click.echo(f"  note: {note}")
    else:
        click.echo("rejected: " + "; ".join(outcome.reasons))
    sys.exit(0 if outcome.status == "added" else 1)


@scout_group.command("leads")
@click.option("--days", default=14, show_default=True)
@click.option("--status", help="Only leads with this status (new = has an address, no email queued yet).")
@click.option("--json", "as_json", is_flag=True)
def list_leads(days, status, as_json) -> None:
    """Recent leads."""
    with db.session() as conn:
        found = leads.recent(conn, days=days, status=status)
    if as_json:
        _echo_json(found)
        return
    for row in found:
        reach = row["email"] or (f"form {row['form_url']}" if row["form_url"] else "no contact")
        click.echo(f"{row['id']:>5} {row['created_at'][:10]} {row['score']:>3} {row['status']:12} {row['company'][:36]:36} {row['domain']:28} {reach}")
    if not found:
        click.echo("no leads")


@scout_group.command("insights")
@click.option("--days", default=30, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def insights(days, as_json) -> None:
    """Industries and observations from recent leads: {"industries": {name: count}, "observations": [...]}."""
    with db.session() as conn:
        found = leads.insights(conn, days)
    if as_json:
        _echo_json(found)
        return
    for name, count in found["industries"].items():
        click.echo(f"{count:>4}  {name}")
    for item in found["observations"][:20]:
        click.echo(f"  - {item}")


@scout_group.command("tools")
@click.option("--json", "as_json", is_flag=True)
def tools(as_json) -> None:
    """Live toolbox tools from the site registry, with usage counts when D1 is set up."""
    found, problem = registry.load()
    counts = registry.usage() if found else {}
    rows = [
        {
            "slug": t["slug"],
            "name": t.get("name"),
            "description": t.get("description"),
            "category": t.get("category"),
            "added": t.get("added"),
            "usage_30_days": counts.get(t["slug"]),
        }
        for t in found
    ]
    if as_json:
        _echo_json({"tools": rows, "problem": problem})
        return
    if not rows:
        click.echo(f"no tools: {problem}")
    for row in rows:
        click.echo(f"{row['slug']:28} {row['category'] or '':10} {row['description'] or ''}")
