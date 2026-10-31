"""The record of every reaction (`inbox_items`), and the one way in: `record(conn, Reaction)`.

Mail intake and the browser watch both come through here, so everything that must hold for any
reaction holds at this seam: counted once by its key, stored text capped and free of control
characters, source and state from the model. `record` knows nothing about mail: a `Reaction`
arrives with its key and conversation already worked out, and `thread` is opaque to it. The small
tables beside it, what the mail check remembers and Jura's outgoing ids, live here too because
they are the same database's, and nothing else writes them.
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
NEEDS_HAND_REPLY = "needs-you"  # the state's name in the PRD; in words, "needs a hand reply"
NEW = "new"

NAME_CHARS = 120
SUBJECT_CHARS = 300
ADDRESS_CHARS = 254
TARGET_CHARS = 1000

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
LINE_BREAKS = re.compile(r"\r\n|[\r\x0b\x0c\x85\u2028\u2029]")
# C0 and C1 controls but tab and newline, bidi marks and overrides, zero-width characters.
_INVISIBLE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x9f\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")


def clean_text(value: str) -> str:
    """Text as it may be stored and shown: valid Unicode, no control characters, plain newlines."""
    value = value.encode("utf-8", "replace").decode("utf-8")
    value = LINE_BREAKS.sub("\n", _ANSI.sub("", value))
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


def get(conn: sqlite3.Connection, item_id: int) -> dict | None:
    """One inbox item, whole."""
    return db.one(conn, "SELECT * FROM inbox_items WHERE id = ?", (item_id,))


def label(item_id: int) -> str:
    """An inbox item's id, which Ting Yu sees on its report and types to act on it."""
    return f"I-{item_id:04d}"


def set_item_state(conn: sqlite3.Connection, item_id: int, state: str) -> None:
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    conn.execute("UPDATE inbox_items SET state = ?, updated_at = ? WHERE id = ?", (state, timeutil.stamp(), item_id))


# --- reports ------------------------------------------------------------------


def unreported(conn: sqlite3.Connection) -> list[dict]:
    """Every inbox item still owed a report, oldest first. Noise never is (R2)."""
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
        "hand_replies": db.scalar(conn, "SELECT count(*) FROM inbox_items WHERE state = ?", (NEEDS_HAND_REPLY,)) or 0,
    }


# --- what the mail check remembers --------------------------------------------

LAST_SUCCESS = "mail.last_success."
FAILING_SINCE = "mail.failing_since."
PROBLEM = "mail.problem."
ALERTED_ON = "mail.alerted_on."


def with_prefix(conn: sqlite3.Connection, prefix: str) -> list[tuple[str, str]]:
    """(what follows `prefix`, value) for each remembered key that starts with it."""
    rows = db.rows(conn, "SELECT key, value FROM inbox_state WHERE key LIKE ? ORDER BY key", (f"{prefix}%",))
    return [(row["key"].removeprefix(prefix), row["value"]) for row in rows]



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
    """Keep the `Message-ID` of a message Jura sent, so its copy is recognised (F4) and an answer
    naming it finds its lead (F2).

    Nothing calls this yet: ticket 03's `inbox-send` sets a `Message-ID` on each inbox reply and
    records it here. Outreach sends carry none (`outreach/send.py` leaves it to Resend, which
    doesn't report the one it sets), so outreach mail has nothing to look up. F2's domain match
    is what covers it (`replies.Contacts.match`): a colleague on the lead's domain still counts, and
    someone elsewhere answering outreach is reported as a stranger. Copies of outreach mail are
    dropped by sender domain, so F4 holds for them too."""
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
