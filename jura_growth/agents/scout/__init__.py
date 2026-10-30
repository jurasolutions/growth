"""The scout: finds Singapore businesses that fit the ICP and records each
with a published enquiry address (scout PRD §5.1–5.2).

Research runs as a headless Claude session (`prompts/scout.md`, job
`scout-research`); everything it records goes through `jura-growth scout`,
where the contact rules are enforced. Sending lives in the `outreach`
plug-in. Settings: `config/scout.yaml`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jura_growth import db

NAME = "scout"
MIGRATIONS = Path(__file__).parent / "migrations"


def register(cli) -> None:
    from jura_growth.agents.scout.cli import scout_group

    cli.add_command(scout_group)


def permissions(job: str):
    """The `jura-growth` commands `prompts/scout.md` uses. Sending, syncing,
    requeueing and unsubscribe links stay with code and Ting Yu. Leads come in
    only as a ranked batch (`scout shortlist`, PRD §5.2a), so the code picks the
    day's best; `scout add-lead` stays for Ting Yu in Terminal."""
    if job != "scout-research":
        return None
    from jura_growth.headless import Permissions

    return Permissions(commands=(
        "scout today", "scout tools", "scout check", "scout check-contact", "scout shortlist", "scout add-lead",
        "scout leads",
        "outreach status", "outreach follow-ups-due", "outreach queue",
    ))


def precheck(job: str, conn: sqlite3.Connection) -> str | None:
    if job != "scout-research":
        return None
    from jura_growth.agents.scout import icp, leads, settings, shortlist as ranking

    missing = icp.missing_reason()
    if missing:
        return missing
    done = ranking.ranked_today(conn)
    if done:
        return f"today's candidates are already ranked ({done['kept']} kept of {done['candidates']})"
    shortlist = settings.shortlist()
    if leads.added_today(conn) >= shortlist:
        return f"today's shortlist of {shortlist} leads is already kept"
    queued = db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'queued'") or 0
    if queued >= settings.max_queue():
        return f"{queued} emails are already queued (max_queue {settings.max_queue()}); research waits for the queue to drain"
    return None


def digest(conn: sqlite3.Connection, day: str) -> dict:
    rows = db.rows(conn, "SELECT company, domain, channel, form_url FROM leads WHERE substr(created_at, 1, 10) = ?", (day,))
    added = len(rows)
    forms = [r for r in rows if r["channel"] == "form"]
    lines, brief = [], []
    if added:
        lines.append(f"Scout: {_new_leads(rows)}")
        brief.append(f"{added} new lead{'s' if added != 1 else ''}")
    if forms:
        listed = ", ".join(f"{r['company']} ({r['form_url']})" for r in forms[:10])
        lines.append(f"Form-only leads to contact by hand if you want to: {listed}")
    return {"figures": {"leads_added": added, "leads_form_only": len(forms)}, "lines": lines, "brief": brief}


RUN_UPDATE_DISCORD_CHANNEL = "scout-leads"


def run_update(conn: sqlite3.Connection, run) -> list[str]:
    """The "Produced:" items of a research run: the leads it recorded, by
    how they can be reached."""
    rows = db.rows(conn, "SELECT channel FROM leads WHERE run_id = ?", (run.id,))
    return [_new_leads(rows)] if rows else []


def _new_leads(rows: list) -> str:
    """`3 new leads (2 with an address, 1 form only)`, for the digest and the run update."""
    from jura_growth.run_update import count

    by_email = sum(1 for r in rows if r["channel"] == "email")
    forms = sum(1 for r in rows if r["channel"] == "form")
    return f"{count(len(rows), 'new lead')} ({by_email} with an address, {forms} form only)"


def privacy_terms(conn: sqlite3.Connection | None) -> dict:
    """For `privacy`: addresses that name a person, so their names stay out of
    Discord, and company names, so they are never read as a person's name."""
    if conn is None:
        return {}
    named = db.rows(conn, "SELECT email FROM contacts WHERE kind = 'named'")
    companies = db.rows(conn, "SELECT company, display_name FROM leads")
    return {
        "named_addresses": [r["email"] for r in named],
        # A one-word name ("Tan") would also protect a surname, so only longer ones count.
        "companies": sorted({n for r in companies for n in (r["company"], r["display_name"]) if n and " " in n.strip()}),
    }
