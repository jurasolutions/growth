"""Suppression sync, bounces and complaints, follow-ups and retention.

The website's D1 `suppression` table collects unsubscribes (link and one-click
POST) and Resend's bounce and complaint webhooks. `suppression.sync_from_d1`
copies new rows here; this module acts on them:

- a bounce marks the message (matched by `resend_email_id`) and the lead
  `bounced`; a bounce rate above 3% over the last 50 sends pauses outreach;
- a complaint marks them `complained` and pauses outreach;
- an unsubscribe marks the lead `unsubscribed`;
- every one cancels anything still queued for that company.

A failed sync pauses outreach when D1 is configured (PRD §5.7).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date

from jura_growth import cloudflare, db, holidays, log, suppression, timeutil
from jura_growth.agents.outreach import replies, store
from jura_growth.agents.scout import registry, settings


@dataclass
class D1Result:
    configured: bool = True
    ok: bool = True
    error: str = ""
    new: int = 0
    bounces: int = 0
    complaints: int = 0
    unsubscribes: int = 0
    paused: list[str] = field(default_factory=list)


def sync_suppression(conn: sqlite3.Connection) -> D1Result:
    if not cloudflare.configured():
        return D1Result(configured=False)
    result = D1Result()
    try:
        rows = suppression.sync_from_d1(conn)
    except Exception as error:  # noqa: BLE001 - any failure means the list may be stale
        result.ok = False
        result.error = f"{type(error).__name__}: {str(error)[:200]}"
        reason = f"suppression sync from D1 failed ({result.error})"
        store.auto_pause(conn, reason)
        result.paused.append(reason)
        return result
    result.new = len(rows)
    apply_rows(conn, rows, result)
    return result


def _matching(conn: sqlite3.Connection, row: dict) -> tuple[dict | None, set[int]]:
    message = None
    if row.get("resend_email_id"):
        message = db.one(conn, "SELECT * FROM outreach_messages WHERE resend_id = ?", (row["resend_email_id"],))
    lead_ids = {message["lead_id"]} if message else set()
    if row.get("email_hash"):
        lead_ids |= {r["lead_id"] for r in db.rows(conn, "SELECT lead_id FROM contacts WHERE email_hash = ?", (row["email_hash"],))}
    if message is None and lead_ids:
        marks = ",".join("?" * len(lead_ids))
        message = db.one(
            conn,
            f"SELECT * FROM outreach_messages WHERE lead_id IN ({marks}) AND mode = 'live' AND sent_at IS NOT NULL "
            "ORDER BY sent_at DESC LIMIT 1",
            tuple(lead_ids),
        )
    return message, lead_ids


def apply_rows(conn: sqlite3.Connection, rows: list[dict], result: D1Result) -> None:
    for row in rows:
        reason = row.get("reason")
        message, lead_ids = _matching(conn, row)
        domains = sorted({r["domain"] for r in db.rows(conn, f"SELECT domain FROM leads WHERE id IN ({','.join('?' * len(lead_ids))})", tuple(lead_ids))}) if lead_ids else []
        where = ", ".join(domains) or "an address not in the scout's leads"
        if reason == "bounce":
            result.bounces += 1
            if message:
                conn.execute("UPDATE outreach_messages SET status = 'bounced' WHERE id = ?", (message["id"],))
            store.set_lead_status(conn, lead_ids, "bounced")
            store.post(conn, "outreach-replies", f"**Bounce** from {where} ({row.get('source')}). The address is suppressed.")
        elif reason == "complaint":
            result.complaints += 1
            if message:
                conn.execute("UPDATE outreach_messages SET status = 'complained' WHERE id = ?", (message["id"],))
            store.set_lead_status(conn, lead_ids, "complained")
        elif reason == "unsubscribe":
            result.unsubscribes += 1
            store.set_lead_status(conn, lead_ids, "unsubscribed")
            store.post(conn, "outreach-replies", f"**Unsubscribe** from {where} ({row.get('source')}). The address is suppressed.")
        else:
            store.set_lead_status(conn, lead_ids, "suppressed")
        store.cancel_queued(conn, lead_ids, f"suppressed ({reason})")
        log.event(
            conn,
            "outreach.suppressed",
            {"reason": reason, "source": row.get("source"), "domains": domains, "message": message["id"] if message else None},
            agent=store.AGENT,
        )
    if result.complaints:
        reason = f"{result.complaints} spam complaint{'s' if result.complaints != 1 else ''} received"
        store.auto_pause(conn, reason)
        result.paused.append(reason)
    if result.bounces and store.bounce_rate_pause(conn):
        result.paused.append("bounce rate")


# --- follow-ups ------------------------------------------------------------


def follow_ups_on() -> bool:
    return settings.follow_ups_enabled() and replies.enabled()


def follow_up_problem(conn: sqlite3.Connection, lead_id: int, today: date | None = None) -> str | None:
    """Why lead `lead_id` can't have a follow-up now, or None."""
    if not settings.follow_ups_enabled():
        return "follow-ups are switched off in config/scout.yaml"
    if not replies.enabled():
        return "follow-ups need reply detection (the OUTREACH_IMAP_* secrets), so a reply can stop them"
    lead = db.one(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,))
    if not lead:
        return f"no lead {lead_id}"
    if lead["status"] in store.FINAL_LEAD_STATUSES:
        return f"lead {lead_id} is {lead['status']}"
    first = db.one(
        conn,
        "SELECT sent_at, status FROM outreach_messages WHERE lead_id = ? AND kind = 'first' AND mode = 'live' "
        "AND sent_at IS NOT NULL",
        (lead_id,),
    )
    if not first:
        return f"lead {lead_id} has no live first email"
    if first["status"] != "sent":
        return f"the first email was {first['status']}"
    if db.one(conn, "SELECT 1 FROM outreach_replies WHERE lead_id = ?", (lead_id,)):
        return f"lead {lead_id} replied"
    existing = db.one(
        conn,
        "SELECT id, status FROM outreach_messages WHERE lead_id = ? AND kind = 'follow_up' "
        "AND status NOT IN ('dropped', 'cancelled', 'skipped', 'failed')",
        (lead_id,),
    )
    if existing:
        return f"lead {lead_id} already has a follow-up (message {existing['id']}, {existing['status']})"
    today = today or timeutil.today()
    sent_day = timeutil.parse(first["sent_at"]).date()
    waited = holidays.business_days_between(sent_day, today)
    if waited < settings.follow_up_days():
        return f"only {waited} business days since the first email; follow-ups wait {settings.follow_up_days()}"
    return None


def follow_ups_due(conn: sqlite3.Connection) -> list[dict]:
    if not follow_ups_on():
        return []
    candidates = db.rows(
        conn,
        "SELECT m.lead_id, m.subject, m.sent_at, m.tool_slug, l.company, l.display_name, l.domain, l.industry, "
        "l.observations_json FROM outreach_messages m JOIN leads l ON l.id = m.lead_id "
        "WHERE m.kind = 'first' AND m.mode = 'live' AND m.status = 'sent' ORDER BY m.sent_at",
    )
    tools, _ = registry.load()
    due = []
    for row in candidates:
        if follow_up_problem(conn, row["lead_id"]):
            continue
        sent_day = row["sent_at"][:10]
        newer = [t["slug"] for t in tools if str(t.get("added") or "") > sent_day and t["slug"] != row["tool_slug"]]
        due.append(
            {
                "lead_id": row["lead_id"],
                "company": row["display_name"],
                "domain": row["domain"],
                "industry": row["industry"],
                "first_subject": row["subject"],
                "first_sent": sent_day,
                "first_tool": row["tool_slug"],
                "newer_tools": newer,
                "observations": json.loads(row["observations_json"] or "[]"),
            }
        )
    return due


# --- retention -------------------------------------------------------------


def _months_ago(months: int) -> str:
    today = timeutil.today()
    year, month = today.year, today.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, min(today.day, 28)).isoformat()


def retention(conn: sqlite3.Connection) -> dict:
    """Delete leads that never replied after 24 months (their contacts and
    messages go with them); keep each contacted domain. Prune old rejections."""
    cutoff = _months_ago(settings.retention_months())
    conn.execute(
        "INSERT OR IGNORE INTO contacted_domains (domain, first_contacted_at) "
        "SELECT l.domain, min(m.sent_at) FROM leads l JOIN outreach_messages m ON m.lead_id = l.id "
        "WHERE m.mode = 'live' AND m.sent_at IS NOT NULL GROUP BY l.domain"
    )
    old = db.rows(
        conn,
        "SELECT id FROM leads WHERE created_at < ? AND status != 'replied' "
        "AND id NOT IN (SELECT lead_id FROM outreach_replies WHERE lead_id IS NOT NULL)",
        (cutoff,),
    )
    for row in old:
        conn.execute("DELETE FROM leads WHERE id = ?", (row["id"],))
    rejections = conn.execute(
        "DELETE FROM scout_rejections WHERE rejected_at < ?", (_months_ago(settings.rejection_months()),)
    ).rowcount
    if old or rejections:
        log.event(conn, "outreach.retention", {"leads_deleted": len(old), "rejections_deleted": rejections}, agent=store.AGENT)
    return {"leads_deleted": len(old), "rejections_deleted": rejections}


# --- the 16:45 sync --------------------------------------------------------


def run(conn: sqlite3.Connection) -> str:
    parts = []
    d1 = sync_suppression(conn)
    if not d1.configured:
        mode = settings.mode()
        parts.append(
            "D1 not configured: suppression not synced"
            + (" (live sending stays refused until it is)" if mode == "live" else " (fine in shadow mode)")
        )
        log.event(conn, "outreach.d1_missing", {"mode": mode}, level="warning", agent=store.AGENT)
    elif not d1.ok:
        parts.append(f"suppression sync failed; outreach paused ({d1.error})")
    else:
        parts.append(
            f"{d1.new} new suppression{'s' if d1.new != 1 else ''}"
            + (f" ({d1.unsubscribes} unsubscribe, {d1.bounces} bounce, {d1.complaints} complaint)" if d1.new else "")
        )
    if d1.paused:
        parts.append("paused: " + "; ".join(d1.paused))

    if replies.enabled():
        try:
            found = replies.check(conn)
            parts.append(f"{len(found.replies)} repl{'ies' if len(found.replies) != 1 else 'y'} detected" + (f", {found.unsubscribes} asking to be removed" if found.unsubscribes else ""))
        except replies.RepliesError as error:
            parts.append(f"reply check failed: {error}")
            log.event(conn, "outreach.replies_failed", {"error": str(error)}, level="warning", agent=store.AGENT)
    else:
        parts.append("reply detection off (no follow-ups)")

    due = follow_ups_due(conn)
    if due:
        parts.append(f"{len(due)} follow-up{'s' if len(due) != 1 else ''} due for the next research run")

    rolled = db.scalar(
        conn, "SELECT count(*) FROM outreach_messages WHERE status = 'queued' AND send_after <= ?", (timeutil.today_str(),)
    ) or 0
    if rolled:
        parts.append(f"{rolled} queued email{'s' if rolled != 1 else ''} roll to the next business day")

    kept = retention(conn)
    if kept["leads_deleted"]:
        parts.append(f"{kept['leads_deleted']} leads past retention deleted")
    return "sync: " + "; ".join(parts)
