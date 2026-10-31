"""A person's words go 90 days after their item closes (PRD §4; technical N6, functional N7).

**When an item closes**, state by state. An item has closed when nothing asks anything of Ting Yu:

| State | Closes |
|---|---|
| `new`, `triaged`, `waiting`, `sending`, `observed` | Not yet: it is still moving, and a request lapses within days |
| `reported`, `unverified` | When its report went. Untold, it stays open, since he hasn't seen it |
| `noise`, `baseline`, `own` | When it was recorded: it never asked anything |
| `needs-you` | When he sends `done`, or when R4 stops listing it, 7 days on |
| `needs-you`, promised | R4 lists it until `done`, so its words go 90 days after the reply went, and the line stays |
| `sent`, `skipped`, `lapsed`, `superseded`, `unknown`, `failed`, `answered-by-hand`, `closed`, `done` | When it got there |

**What goes:** everything a person wrote or that names them, and the draft that answers them, from the
row and from its cards' `approval_cards.first_piece`. **What stays:** the state, the source, the sender's
domain and the hashes and ids that count a message once, so a read of an old thread doesn't report it as
new (W5).

The nightly backup runs this before it copies the database, through the plug-in's `retention` hook: that
job keeps running when `inbox` is paused. The outbox has its own limit (`backup.prune_outbox`), and
backups and transcripts theirs. `remote.command` events keep no typed words for these commands, because
`events` can't be pruned.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

from jura_growth import db, log, timeutil
from jura_growth.agents.inbox import kinds, settings, store

AGENT = "inbox"
HAND_REPLY_LISTED_DAYS = 7  # R4
_THREAD_KEPT = ("run", "surface", "thread", "comment_id", "words_key", "loose_key", "occurrence", "attachment", "answered")
_STILL_MOVING = (store.NEW, store.TRIAGED, store.WAITING, store.SENDING, store.OBSERVED)
_TOLD = (store.REPORTED, store.UNVERIFIED)
_NEVER_ASKED = (store.NOISE, store.BASELINE, store.OWN)


def closes_at(item: dict) -> str | None:
    """When this item closed, or None while it hasn't. The table in this module's docstring."""
    state = item["state"]
    if state in _STILL_MOVING:
        return None
    if state in _TOLD:
        return item["reported_at"]
    if state in _NEVER_ASKED:
        return item["recorded_at"]
    if state == store.NEEDS_HAND_REPLY:
        if item["promised"] and item["sent_at"]:
            return item["sent_at"]
        return timeutil.stamp(timeutil.parse(item["updated_at"]) + timedelta(days=HAND_REPLY_LISTED_DAYS))
    return item["closed_at"] or item["updated_at"]


def _remove(conn: sqlite3.Connection, item: dict, closed: str) -> int:
    """Returns how many cards it blanked. Inside the caller's transaction."""
    thread = {key: value for key, value in store.thread_of(item).items() if key in _THREAD_KEPT}
    now = timeutil.stamp()
    conn.execute(
        "UPDATE inbox_items SET text = '', text_cut = 0, draft = NULL, guidance = NULL, subject = '', sender_name = '', sender_address = '', "
        "target = '', note = '', attachments_json = '[]', thread_json = ?, closed_at = COALESCE(closed_at, ?), text_removed_at = ? "
        "WHERE id = ?",  # `updated_at` stays: R4 reads it as when the item got here
        (json.dumps(thread, ensure_ascii=False), closed, now, item["id"]),
    )
    return conn.execute(
        "UPDATE approval_cards SET first_piece = '', updated_at = ? WHERE first_piece != '' AND approval_id IN "
        "(SELECT id FROM approvals WHERE subject = ?)",
        (now, kinds.subject_of(item["id"])),
    ).rowcount


def prune(conn: sqlite3.Connection) -> dict[str, int]:
    """Remove what has been closed for long enough. Each item is its own transaction. An item can't
    close later than it was last touched, but for a hand reply's week, which `closes_at` then judges."""
    cutoff = timeutil.stamp(timeutil.now_sgt() - timedelta(days=settings.limit("text_retention_days")))
    found = {"items": 0, "cards": 0}
    rows = db.rows(conn, "SELECT * FROM inbox_items WHERE text_removed_at IS NULL AND updated_at <= ? ORDER BY id", (cutoff,))
    for item in rows:
        closed = closes_at(item)
        if closed is None or closed > cutoff:
            continue
        with db.transaction(conn):
            found["cards"] += _remove(conn, item, closed)
        found["items"] += 1
    if found["items"]:
        log.event(conn, "inbox.text_removed", found, agent=AGENT)
    return found
