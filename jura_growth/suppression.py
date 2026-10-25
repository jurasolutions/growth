"""The shared suppression list. Nothing is ever sent to a suppressed address or
domain, by any agent.

Rows come from four places: an unsubscribe link or one-click POST on the
website, a Resend bounce or complaint webhook (both land in the website's D1
first and are synced here), a reply saying "unsubscribe", and manual entries.
Entries are kept indefinitely.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable

from jura_growth import cloudflare, db, log, timeutil


def email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def domain_of(email_or_domain: str) -> str:
    value = email_or_domain.strip().lower()
    return value.rsplit("@", 1)[-1].removeprefix("www.")


def is_suppressed(conn: sqlite3.Connection, email: str) -> str | None:
    """The suppression reason for `email` (or its domain), or None."""
    row = conn.execute(
        "SELECT reason FROM suppression WHERE email_hash = ?", (email_hash(email),)
    ).fetchone()
    if row:
        return row["reason"]
    row = conn.execute(
        "SELECT reason FROM suppression WHERE domain = ? AND email_hash IS NULL", (domain_of(email),)
    ).fetchone()
    return f"{row['reason']} (domain)" if row else None


def is_domain_suppressed(conn: sqlite3.Connection, domain: str) -> str | None:
    row = conn.execute(
        "SELECT reason FROM suppression WHERE domain = ? AND email_hash IS NULL", (domain_of(domain),)
    ).fetchone()
    return row["reason"] if row else None


def add(
    conn: sqlite3.Connection,
    *,
    email: str | None = None,
    domain: str | None = None,
    reason: str,
    source: str,
    email_hash_value: str | None = None,
) -> bool:
    """Suppress an address (or hash) or a whole domain. True if it was new."""
    if reason not in ("unsubscribe", "bounce", "complaint", "manual"):
        raise ValueError(f"unknown suppression reason {reason!r}")
    if email:
        email = email.strip().lower()
        hashed = email_hash(email)
    else:
        hashed = email_hash_value
    if not hashed and not domain:
        raise ValueError("suppress an email, an email hash or a domain")
    cursor = conn.execute(
        "INSERT OR IGNORE INTO suppression (email, email_hash, domain, reason, source, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (email, hashed, None if hashed else domain_of(domain), reason, source, timeutil.stamp()),
    )
    if not cursor.rowcount and email:
        # A hash-only row from an unsubscribe link learns its address later.
        conn.execute("UPDATE suppression SET email = ? WHERE email_hash = ? AND email IS NULL", (email, hashed))
    if cursor.rowcount:
        log.event(conn, "suppression.add", {"reason": reason, "source": source, "domain": domain_of(email or domain or "") or None})
    return bool(cursor.rowcount)


D1_CURSOR = "d1:suppression"


class D1ContractError(ValueError):
    """D1's suppression table doesn't look like the append-only log the sync
    relies on (docs/scout.md, D1 contract)."""


def sync_from_d1(conn: sqlite3.Connection, apply: Callable[[list[dict]], None]) -> list[dict]:
    """Copy the website's D1 suppression events not yet processed here and
    return them, oldest first (id, email_hash, email, reason, source,
    resend_email_id, created_at).

    D1 keeps one row per event with its own id, so an address that is already
    suppressed here still brings in its later complaint or bounce. `apply` (the
    caller acting on bounces and complaints, database writes only) runs in the
    same transaction as the local copy and the cursor move. A failure anywhere
    rolls all three back, so the batch is tried again on the next sync, and an
    event that was processed is never processed again.

    The event the cursor points at must come back unchanged. If it is missing
    or different, the table was recreated or rewritten behind the cursor, and
    new events could be hiding under old ids, so this raises D1ContractError
    instead of skipping them.
    """
    after, marker = _cursor(conn, D1_CURSOR)
    rows = cloudflare.query(
        "SELECT id, email_hash, email, reason, source, resend_email_id, created_at FROM suppression "
        "WHERE id >= ? ORDER BY id",
        [after],
    )
    if after:
        _check_cursor_row(rows, after, marker)
    # Filter again here as well as in the query: the sync must never re-apply
    # an event, whatever D1 returns.
    events = sorted((row for row in rows if _event_id(row) > after), key=_event_id)
    if events:
        with db.transaction(conn):
            for row in events:
                add(
                    conn,
                    email=row.get("email"),
                    email_hash_value=row["email_hash"],
                    reason=row["reason"],
                    source=f"d1:{row['source']}",
                )
            apply(events)
            _move_cursor(conn, D1_CURSOR, _event_id(events[-1]), _marker(events[-1]))
    log.event(conn, "suppression.sync", {"fetched": len(rows), "new": len(events), "after_id": after})
    return events


def _marker(row: dict) -> str:
    return "|".join(str(row.get(key) or "") for key in ("email_hash", "reason", "source", "created_at"))


def _check_cursor_row(rows: list[dict], after: int, marker: str | None) -> None:
    found = [row for row in rows if _event_id(row) == after]
    if not found or (marker is not None and _marker(found[0]) != marker):
        state = "is missing" if not found else "has changed"
        raise D1ContractError(
            f"D1 suppression event {after}, the last one processed here, {state}: the site's table was "
            "recreated or rewritten, so newer events may be hidden under old ids. Check the table against "
            "the D1 contract in docs/scout.md before resuming outreach"
        )


def _event_id(row: dict) -> int:
    try:
        return int(row["id"])
    except (KeyError, TypeError, ValueError):
        raise D1ContractError(
            "a D1 suppression row has no numeric id: the site's table must be append-only, one row per "
            "event with its own id (docs/scout.md, D1 contract)"
        ) from None


def _cursor(conn: sqlite3.Connection, name: str) -> tuple[int, str | None]:
    row = db.one(conn, "SELECT position, marker FROM sync_cursors WHERE name = ?", (name,))
    return (row["position"], row["marker"]) if row else (0, None)


def _move_cursor(conn: sqlite3.Connection, name: str, position: int, marker: str) -> None:
    conn.execute(
        "INSERT INTO sync_cursors (name, position, marker, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET position = excluded.position, marker = excluded.marker, "
        "updated_at = excluded.updated_at",
        (name, position, marker, timeutil.stamp()),
    )
