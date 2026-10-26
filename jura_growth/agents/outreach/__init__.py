"""Outreach: queues, checks and sends the scout's emails (scout PRD §5.3–5.8).

Jobs `scout-send` (every 10 minutes, quiet) and `scout-sync` (16:45) run as
agent `outreach`, so `jura-growth pause outreach` / `resume outreach` stop and
start sending without touching research. Settings: `config/scout.yaml`
(`mode: shadow` by default). Hard limits: `caps.py`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jura_growth import db

NAME = "outreach"
# Setup gaps (health.setup_gaps): what live sending and the suppression sync need.
# The OUTREACH_IMAP_* settings are left out on purpose: reply detection is opt-in (replies.py).
REQUIRED_SETTINGS = (
    "RESEND_API_KEY_OUTREACH",
    "UNSUBSCRIBE_SECRET",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "D1_DATABASE_ID",
)
MIGRATIONS = Path(__file__).parent / "migrations"


def register(cli) -> None:
    from jura_growth.agents.outreach.cli import outreach_group

    cli.add_command(outreach_group)


def channels() -> dict:
    from jura_growth.agents.outreach import compose

    return {"email": compose.channel()}


def precheck(job: str, conn: sqlite3.Connection) -> str | None:
    # send-due and sync check everything themselves, so a manual run behaves
    # the same as a scheduled one.
    return None


def digest(conn: sqlite3.Connection, day: str) -> dict:
    from jura_growth.agents.scout import settings

    def count(sql: str) -> int:
        return db.scalar(conn, sql, (day,)) or 0

    sent = count("SELECT count(*) FROM outreach_messages WHERE mode = 'live' AND substr(sent_at, 1, 10) = ?")
    shadow = count("SELECT count(*) FROM outreach_messages WHERE mode = 'shadow' AND substr(sent_at, 1, 10) = ?")
    replies = count("SELECT count(*) FROM outreach_replies WHERE substr(detected_at, 1, 10) = ?")
    unsubscribes = count("SELECT count(*) FROM suppression WHERE reason = 'unsubscribe' AND substr(added_at, 1, 10) = ?")
    bounces = count("SELECT count(*) FROM suppression WHERE reason = 'bounce' AND substr(added_at, 1, 10) = ?")
    complaints = count("SELECT count(*) FROM suppression WHERE reason = 'complaint' AND substr(added_at, 1, 10) = ?")
    queued = db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'queued'") or 0
    mode = settings.mode()

    lines, brief = [], []
    if sent or shadow or replies or unsubscribes or bounces or complaints:
        parts = []
        if sent:
            parts.append(f"{sent} email{'s' if sent != 1 else ''} sent")
        if shadow:
            parts.append(f"{shadow} shadow email{'s' if shadow != 1 else ''} (not sent)")
        parts.append(f"{replies} repl{'ies' if replies != 1 else 'y'}")
        parts.append(f"{unsubscribes} unsubscribe{'s' if unsubscribes != 1 else ''}")
        parts.append(f"{bounces} bounce{'s' if bounces != 1 else ''}")
        if complaints:
            parts.append(f"{complaints} complaint{'s' if complaints != 1 else ''}")
        lines.append(f"Outreach ({mode}): " + ", ".join(parts) + f"; {queued} queued")
        if sent:
            brief.append(f"{sent} email{'s' if sent != 1 else ''} sent")
        if shadow:
            brief.append(f"{shadow} shadow email{'s' if shadow != 1 else ''}")
        if replies:
            brief.append(f"{replies} repl{'ies' if replies != 1 else 'y'}")
        if unsubscribes:
            brief.append(f"{unsubscribes} unsubscribe{'s' if unsubscribes != 1 else ''}")
    elif queued:
        lines.append(f"Outreach ({mode}): nothing sent today; {queued} queued")
    return {
        "figures": {
            "outreach_mode": mode,
            "emails_sent": sent,
            "emails_shadow": shadow,
            "replies": replies,
            "unsubscribes": unsubscribes,
            "bounces": bounces,
            "complaints": complaints,
            "emails_queued": queued,
        },
        "lines": lines,
        "brief": brief,
    }


def privacy_terms(conn) -> dict:
    """For `privacy`: Ting Yu's sender address, kept only in previews of Jura's own
    email, and his name, which signs them and is never read as a prospect's."""
    from jura_growth.agents.scout import settings

    local = str(settings.get().get("from_local_part") or "tingyu").strip().lower()
    domains = {"jurasolutions.sg", str(settings.get().get("sending_domain") or "").strip().lower()}
    return {
        "owner_addresses": sorted(f"{local}@{d}" for d in domains if d),
        "kept_names": [settings.SIGNATURE_NAME],
    }
