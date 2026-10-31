"""The record of every reaction (`inbox_items`), and the one way in: `record(conn, Reaction)`.

Mail intake and the browser watch both come through here, so everything that must hold for any
reaction holds at this seam: counted once by its key, stored text capped and free of control
characters, source and state from the model. It knows nothing about mail: a `Reaction` arrives
with its key and conversation already worked out, and `thread` is opaque to it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Mapping

from jura_growth import db, timeutil
from jura_growth.agents.inbox import settings

SOURCES = ("email", "enquiry", "facebook-comment", "facebook-dm", "instagram-comment", "instagram-dm", "post-stats",
           "app-usage")
STATES = ("new", "triaged", "reported", "waiting", "sent", "skipped", "lapsed", "superseded", "unknown", "failed",
          "needs-you", "noise", "unverified", "answered-by-hand", "closed", "done")
NOISE = "noise"
REPORTED = "reported"
NEEDS_YOU = "needs-you"
NEW = "new"

NAME_CHARS = 120
SUBJECT_CHARS = 300
ADDRESS_CHARS = 254
TARGET_CHARS = 1000

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
_LINE_BREAKS = re.compile(r"\r\n|[\r\x0b\x0c\x85  ]")
# C0 and C1 controls but tab and newline, bidi marks and overrides, zero-width characters.
_INVISIBLE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x9f؜᠎​-‏‪-‮⁠-⁩﻿]")


def clean_text(value: str) -> str:
    """Text as it may be stored and shown: valid Unicode, no control characters, plain newlines."""
    value = value.encode("utf-8", "replace").decode("utf-8")
    value = _LINE_BREAKS.sub("\n", _ANSI.sub("", value))
    return _INVISIBLE.sub("", value)


def clean_line(value: str) -> str:
    """One line, for anything that may become a header or sit in a frame."""
    return " ".join(clean_text(value).split())


def text_key(*parts: str) -> str:
    """A key or conversation made of plain parts, hashed so it stores nothing readable."""
    return hashlib.sha256("|".join(parts).encode("utf-8", "replace")).hexdigest()


@dataclass(frozen=True)
class Reaction:
    """Anything a person or platform did in response to Jura, as its source read it."""

    source: str
    key: str
    conversation: str
    sender_name: str = ""
    sender_address: str = ""
    sender_domain: str = ""
    subject: str = ""
    text: str = ""
    target: str = ""
    thread: Mapping[str, Any] = field(default_factory=dict)
    attachments: tuple[str, ...] = ()
    lead_id: int | None = None
    state: str = NEW
    note: str = ""
    stale: bool = False  # too old at intake for a draft (F12)
    received_at: str | None = None
    reported: bool = False  # already told, so no report is due


@dataclass(frozen=True)
class Recorded:
    item_id: int


@dataclass(frozen=True)
class Duplicate:
    item_id: int


def record(conn: sqlite3.Connection, reaction: Reaction) -> Recorded | Duplicate:
    """Record a reaction, or say which item already holds it. Safe inside a transaction, and
    holds none open itself: the caller keeps it short, and never across the network."""
    if reaction.source not in SOURCES:
        raise ValueError(f"unknown source {reaction.source!r}")
    if reaction.state not in STATES:
        raise ValueError(f"unknown state {reaction.state!r}")
    limit = settings.limit("text_chars")
    text = clean_text(reaction.text).strip()
    now = timeutil.stamp()
    inserted = conn.execute(
        "INSERT OR IGNORE INTO inbox_items (key, source, conversation, sender_name, sender_address, sender_domain, "
        "subject, text, text_cut, target, thread_json, attachments_json, lead_id, state, note, stale, received_at, "
        "recorded_at, reported_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (
            reaction.key, reaction.source, reaction.conversation,
            clean_line(reaction.sender_name)[:NAME_CHARS],
            clean_line(reaction.sender_address)[:ADDRESS_CHARS],
            clean_line(reaction.sender_domain)[:ADDRESS_CHARS],
            clean_line(reaction.subject)[:SUBJECT_CHARS],
            text[:limit], int(len(text) > limit),
            clean_line(reaction.target)[:TARGET_CHARS],
            json.dumps(dict(reaction.thread), ensure_ascii=False),
            json.dumps([clean_line(name) for name in reaction.attachments], ensure_ascii=False),
            reaction.lead_id, reaction.state, reaction.note, int(reaction.stale), reaction.received_at,
            now, now if reaction.reported else None, now,
        ),
    ).fetchall()
    if inserted:
        return Recorded(inserted[0][0])
    return Duplicate(conn.execute("SELECT id FROM inbox_items WHERE key = ?", (reaction.key,)).fetchone()[0])


def known(conn: sqlite3.Connection, key: str) -> bool:
    return db.one(conn, "SELECT 1 FROM inbox_items WHERE key = ?", (key,)) is not None


def item(conn: sqlite3.Connection, item_id: int) -> dict | None:
    return db.one(conn, "SELECT * FROM inbox_items WHERE id = ?", (item_id,))


def label(item_id: int) -> str:
    """The id Ting Yu sees on a report, and types to act on it."""
    return f"I-{item_id:04d}"


def set_item_state(conn: sqlite3.Connection, item_id: int, state: str) -> None:
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    conn.execute("UPDATE inbox_items SET state = ?, updated_at = ? WHERE id = ?", (state, timeutil.stamp(), item_id))


# --- reports ------------------------------------------------------------------


def unreported(conn: sqlite3.Connection) -> list[dict]:
    """Every item still owed a report, oldest first. Noise never is (R2)."""
    return db.rows(conn, "SELECT * FROM inbox_items WHERE reported_at IS NULL AND state != ? ORDER BY id", (NOISE,))


def mark_reported(conn: sqlite3.Connection, item_ids: list[int]) -> None:
    now = timeutil.stamp()
    with db.atomic(conn):
        for item_id in item_ids:
            conn.execute("UPDATE inbox_items SET reported_at = ?, updated_at = ? WHERE id = ?", (now, now, item_id))


def noise_since(conn: sqlite3.Connection, since: str) -> list[dict]:
    """What R2 lists under the count: each filtered message's sender domain and subject."""
    return db.rows(
        conn,
        "SELECT sender_domain, subject, note, recorded_at FROM inbox_items WHERE state = ? AND recorded_at >= ? ORDER BY id",
        (NOISE, since),
    )


def day_counts(conn: sqlite3.Connection, day: str) -> dict[str, int]:
    """One day's figures: counts only, for the digest and the morning brief (R5)."""
    row = db.one(
        conn,
        "SELECT sum(state != ?) AS reactions, sum(state = ?) AS noise FROM inbox_items WHERE substr(recorded_at, 1, 10) = ?",
        (NOISE, NOISE, day),
    ) or {}
    return {"reactions": row.get("reactions") or 0, "noise": row.get("noise") or 0}


def open_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """What is still open, whatever day it arrived."""
    return {
        "unreported": db.scalar(conn, "SELECT count(*) FROM inbox_items WHERE reported_at IS NULL AND state != ?", (NOISE,)) or 0,
        "needs_you": db.scalar(conn, "SELECT count(*) FROM inbox_items WHERE state = ?", (NEEDS_YOU,)) or 0,
    }


# --- what the mail check remembers --------------------------------------------


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    return db.scalar(conn, "SELECT value FROM inbox_state WHERE key = ?", (key,))


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO inbox_state (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, timeutil.stamp()),
    )


def clear_state(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM inbox_state WHERE key = ?", (key,))


# --- Jura's own outgoing mail -------------------------------------------------


def remember_outgoing(conn: sqlite3.Connection, message_id: str, *, lead_id: int | None = None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO inbox_outgoing (message_key, lead_id, recorded_at) VALUES (?, ?, ?)",
        (text_key(message_id.strip()), lead_id, timeutil.stamp()),
    )


def is_outgoing(conn: sqlite3.Connection, message_id: str) -> bool:
    return bool(message_id) and db.one(
        conn, "SELECT 1 FROM inbox_outgoing WHERE message_key = ?", (text_key(message_id.strip()),)
    ) is not None


def lead_of_outgoing(conn: sqlite3.Connection, message_ids: list[str]) -> int | None:
    """The lead that any of `message_ids` went to, when one of them is a message Jura sent a lead."""
    for message_id in message_ids:
        row = db.one(conn, "SELECT lead_id FROM inbox_outgoing WHERE message_key = ?", (text_key(message_id.strip()),))
        if row and row["lead_id"] is not None:
            return row["lead_id"]
    return None
