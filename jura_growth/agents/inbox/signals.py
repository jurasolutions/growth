"""Reactions with no person writing: what the apps saw (W4, S14), and a spam complaint (S12).

Each is one message at most, through the same report as everything else, so it is retried until Discord
takes it. Both run in the precheck, with no model.

**App usage.** The first check after 08:00 asks the website's D1 once for every day not yet reported, at
most 7, up to yesterday in Singapore. One attempt a day: D1 down or not set up is one logged warning, never
a failure and never an alert, and the days it missed come with the next report. A slug and a count come
from a website anyone can open, so only what looks like one is shown.

**Complaints.** The 16:45 sync acts on each D1 event and logs it as `outreach.suppressed`, even for an
address already suppressed, which is why this reads that event and not the suppression list. A click and
a bounce are only counted, in R4.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta

from jura_growth import caps, cloudflare, db, health, log, timeutil
from jura_growth.agents.inbox import store

AGENT = "inbox"
USAGE_FROM = "08:00"
APPS_SHOWN_PER_DAY = 5
SLUG_CHARS = 24
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
_TRIED_ON = "usage.tried_on"
_REPORTED_THROUGH = "usage.reported_through"
_COMPLAINTS_AFTER = "signals.complaints_after"


def _warn(conn: sqlite3.Connection, why: str) -> None:
    log.event(conn, "inbox.usage_unavailable", {"why": why}, level="warning", agent=AGENT)


def _count(value) -> int:
    """A sane count, or 0: a row with a bad one is dropped."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= caps.INBOX_USAGE_COUNT_MAX else 0


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _lines(rows: list[dict], first: date, last: date) -> list[str]:
    """One line per day with an open, oldest first, its busiest apps first."""
    days: dict[date, list[tuple[str, int, int]]] = {}
    for row in rows:
        day, slug, opens = _day(row.get("day")), str(row.get("app_slug") or ""), _count(row.get("opens"))
        if day is None or not first <= day <= last or not opens or not _SLUG.fullmatch(slug):
            continue
        days.setdefault(day, []).append((slug[:SLUG_CHARS], opens, _count(row.get("completions"))))
    lines = []
    for day, apps in sorted(days.items()):
        ranked = sorted(apps, key=lambda app: (-app[1], app[0]))
        parts = [f"{slug} {health.plural(opens, 'open')}" + (f", {health.plural(done, 'completion')}" if done else "")
                 for slug, opens, done in ranked[:APPS_SHOWN_PER_DAY]]
        if len(ranked) > APPS_SHOWN_PER_DAY:
            parts.append(f"and {len(ranked) - APPS_SHOWN_PER_DAY} more")
        lines.append(f"{day:%a} {day.day} {day:%b}: " + "; ".join(parts))
    return lines


def report_usage(conn: sqlite3.Connection) -> None:
    """W4 and S14. Network first, with no transaction open (B5 rule 2)."""
    now = timeutil.now_sgt()
    today = now.date()
    if now.strftime("%H:%M") < USAGE_FROM or store.get_state(conn, _TRIED_ON) == today.isoformat():
        return
    store.set_state(conn, _TRIED_ON, today.isoformat())
    if not cloudflare.configured():
        _warn(conn, "not configured")
        return
    last = today - timedelta(days=1)
    through = _day(store.get_state(conn, _REPORTED_THROUGH))
    first = max(through + timedelta(days=1), today - timedelta(days=caps.INBOX_USAGE_DAYS)) if through else today - timedelta(days=caps.INBOX_USAGE_DAYS)
    if first > last:
        return
    try:
        rows = cloudflare.query("SELECT app_slug, day, SUM(opens) AS opens, SUM(completions) AS completions FROM app_usage "
                                "WHERE day >= ? AND day <= ? GROUP BY app_slug, day", [first.isoformat(), last.isoformat()])
    except Exception as error:  # noqa: BLE001 - any failure is one warning, and the days wait for the next report
        _warn(conn, type(error).__name__)
        return
    lines = _lines(rows, first, last)
    with db.transaction(conn):
        if lines:
            key = store.text_key("app-usage", last.isoformat())
            store.record(conn, store.Reaction(source=store.APP_USAGE, key=key, conversation=key, state=store.REPORTED, note="\n".join(lines)))
        store.set_state(conn, _REPORTED_THROUGH, last.isoformat())


def report_complaints(conn: sqlite3.Connection) -> None:
    """S12: a spam complaint gets a high report and no draft. Each event once, by its id. The first check
    starts from now: an old complaint isn't news, and its "outreach is paused" may no longer be so."""
    cursor = store.get_state(conn, _COMPLAINTS_AFTER)
    if cursor is None:
        newest = db.scalar(conn, "SELECT max(id) FROM events WHERE kind = 'outreach.suppressed'") or 0
        store.set_state(conn, _COMPLAINTS_AFTER, str(newest))
        return
    after = int(cursor)
    rows = db.rows(conn, "SELECT id, payload_json FROM events WHERE kind = 'outreach.suppressed' AND id > ? AND "
                         "json_extract(payload_json, '$.reason') = 'complaint' ORDER BY id", (after,))
    for row in rows:
        domains = json.loads(row["payload_json"]).get("domains") or []
        where = ", ".join(str(domain) for domain in domains) or "an address not in the scout's leads"
        key = store.text_key("complaint", str(row["id"]))
        with db.transaction(conn):
            store.record(conn, store.Reaction(source=store.EMAIL_SIGNAL, key=key, conversation=key, state=store.REPORTED, priority="high",
                                              sender_domain=domains[0] if domains else "",
                                              note=f"A spam complaint came in from {where}. The address is suppressed and outreach is paused. "
                                                   "Look at what was sent before you resume it."))
            store.set_state(conn, _COMPLAINTS_AFTER, str(row["id"]))
