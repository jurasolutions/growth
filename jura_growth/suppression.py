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

from jura_growth import cloudflare, log, timeutil


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


def sync_from_d1(conn: sqlite3.Connection) -> list[dict]:
    """Copy new suppression rows from the website's D1. Returns the new rows
    (email_hash, email, reason, source, resend_email_id, created_at) so the
    caller can act on bounces and complaints."""
    since = conn.execute(
        "SELECT max(added_at) FROM suppression WHERE source LIKE 'd1:%'"
    ).fetchone()[0]
    rows = cloudflare.query(
        "SELECT email_hash, email, reason, source, resend_email_id, created_at FROM suppression "
        "WHERE created_at >= ? ORDER BY created_at",
        [_d1_since(since)],
    )
    new = []
    for row in rows:
        added = add(
            conn,
            email=row.get("email"),
            email_hash_value=row["email_hash"],
            reason=row["reason"],
            source=f"d1:{row['source']}",
        )
        if added:
            new.append(row)
    log.event(conn, "suppression.sync", {"fetched": len(rows), "new": len(new)})
    return new


def _d1_since(local_added_at: str | None) -> str:
    # D1 rows carry the site's own created_at, so re-read a day of overlap and
    # let INSERT OR IGNORE drop what is already here.
    if not local_added_at:
        return "1970-01-01"
    moment = timeutil.parse(local_added_at)
    return (moment - timeutil.timedelta_days(1)).date().isoformat()
