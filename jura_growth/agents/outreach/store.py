"""Small shared helpers for the outreach tables."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date

from jura_growth import db, discord, holidays, log, pause, timeutil

AGENT = "outreach"
USERNAME = "Jura growth · outreach"
# Message statuses that count as "went out" (or would have, in shadow).
SENT_STATUSES = ("shadow", "sent", "bounced", "complained", "replied")
# Lead statuses after which nothing more is sent to the company.
FINAL_LEAD_STATUSES = ("replied", "unsubscribed", "bounced", "complained", "suppressed", "do_not_contact")


def mask(text: str) -> str:
    """Hide the local part of any address before it goes into the append-only
    event log (addresses live only in `contacts`, which retention prunes)."""
    return re.sub(r"[\w.+%-]+@(?=[\w-]+\.)", "…@", text or "")


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    return db.scalar(conn, "SELECT value FROM outreach_state WHERE key = ?", (key,))


def set_state(conn: sqlite3.Connection, key: str, value: str, *, overwrite: bool = True) -> None:
    verb = "DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at" if overwrite else "DO NOTHING"
    conn.execute(
        f"INSERT INTO outreach_state (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT (key) {verb}",
        (key, value, timeutil.stamp()),
    )


def set_lead_status(conn: sqlite3.Connection, lead_ids, status: str) -> None:
    for lead_id in set(lead_ids):
        conn.execute("UPDATE leads SET status = ?, updated_at = ? WHERE id = ?", (status, timeutil.stamp(), lead_id))


def cancel_queued(conn: sqlite3.Connection, lead_ids, reason: str) -> int:
    count = 0
    for lead_id in set(lead_ids):
        cursor = conn.execute(
            "UPDATE outreach_messages SET status = 'cancelled', error = ? WHERE lead_id = ? AND status = 'queued'",
            (reason, lead_id),
        )
        count += cursor.rowcount
    return count


def add_business_days(start: date, days: int) -> date:
    day = start
    for _ in range(days):
        day = holidays.next_business_day(day)
    return day


def contacted(conn: sqlite3.Connection, domain: str) -> bool:
    return db.one(conn, "SELECT 1 FROM contacted_domains WHERE domain = ?", (domain,)) is not None


def record_contacted(conn: sqlite3.Connection, domain: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO contacted_domains (domain, first_contacted_at) VALUES (?, ?)",
        (domain, timeutil.stamp()),
    )


# --- auto-pause (PRD §5.7) -------------------------------------------------


def auto_pause(conn: sqlite3.Connection, reason: str, *, notify: bool = True) -> None:
    """Pause outreach and post to #alerts (pause.pause does both). Inside a
    transaction pass notify=False and call pause.announce after the commit."""
    pause.pause(conn, AGENT, reason, notify=notify)


def _last_resume_id(conn: sqlite3.Connection) -> int:
    rows = db.rows(conn, "SELECT id, payload_json FROM events WHERE kind = 'resume' ORDER BY id DESC LIMIT 50")
    for row in rows:
        try:
            agent = json.loads(row["payload_json"]).get("agent")
        except ValueError:
            continue
        if agent in (AGENT, "all"):
            return row["id"]
    return 0


def record_qa(conn: sqlite3.Connection, item: str, passed: bool, reasons: list[str]) -> bool:
    """Log a brand-gate verdict for an outreach email. Two failures in a row
    (since the last resume) pause outreach. True if it paused."""
    log.event(conn, "outreach.qa", {"item": item, "passed": passed, "issues": reasons[:8]}, agent=AGENT)
    if passed:
        return False
    since = _last_resume_id(conn)
    last_two = db.rows(
        conn,
        "SELECT payload_json FROM events WHERE kind = 'outreach.qa' AND id > ? ORDER BY id DESC LIMIT 2",
        (since,),
    )
    failures = [r for r in last_two if not json.loads(r["payload_json"]).get("passed")]
    if len(failures) == 2:
        auto_pause(conn, "two outreach emails failed the brand check in a row")
        return True
    return False


def bounce_rate_pause(conn: sqlite3.Connection, *, notify: bool = True) -> str | None:
    """Bounce rate above 3% over the last 50 live sends pauses outreach. With
    fewer than 50 sends the denominator stays 50, so two bounces pause.
    Returns the pause reason, or None."""
    recent = db.rows(
        conn,
        "SELECT status FROM outreach_messages WHERE mode = 'live' AND sent_at IS NOT NULL "
        "ORDER BY sent_at DESC, id DESC LIMIT 50",
    )
    bounced = sum(1 for r in recent if r["status"] == "bounced")
    rate = bounced / 50
    if rate > 0.03:
        reason = f"bounce rate {rate:.0%} over the last 50 sends ({bounced} bounced of {len(recent)} sent)"
        auto_pause(conn, reason, notify=notify)
        return reason
    return None


def post(conn: sqlite3.Connection, channel: str, text: str, *, own_copy: tuple[str, ...] = ()) -> None:
    """`own_copy`: the parts of `text` that are Jura's own email, shown as written (privacy.py)."""
    discord.post(conn, channel, text, username=USERNAME, own_copy=own_copy)
