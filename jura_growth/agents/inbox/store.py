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
STATES = ("new", "triaged", "reported", "waiting", "sending", "sent", "skipped", "lapsed", "superseded", "unknown", "failed",
          "needs-you", "noise", "unverified", "answered-by-hand", "closed", "done")
NOISE = "noise"
REPORTED = "reported"
NEEDS_HAND_REPLY = "needs-you"  # the state's name in the PRD; in words, "needs a hand reply"
NEW = "new"
TRIAGED = "triaged"  # classed, with a draft ready for its card
WAITING = "waiting"  # its card is up
SENDING = "sending"  # its approval is claimed: it may be on its way, and the claim is never made twice
SENT = "sent"
SKIPPED = "skipped"
LAPSED = "lapsed"
FAILED = "failed"
UNKNOWN = "unknown"  # it may have gone out, so it is never sent again
SUPERSEDED = "superseded"
# The sources a person writes through, and so what triage reads. `MAIL_SOURCES` answer by email.
MAIL_SOURCES = ("email", "enquiry")
PEOPLE_SOURCES = (*MAIL_SOURCES, "facebook-comment", "facebook-dm", "instagram-comment", "instagram-dm")

NAME_CHARS = 120
SUBJECT_CHARS = 300
ADDRESS_CHARS = 254
TARGET_CHARS = 1000

_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_])")
LINE_BREAKS = re.compile(r"\r\n|[\r\x0b\x0c\x85\u2028\u2029]")
# C0 and C1 controls but tab and newline, bidi marks and overrides, zero-width characters.
# A soft hyphen and the tag block too: they render as nothing, so `evil<U+00AD>.com` reads `evil.com`.
_INVISIBLE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x9f\xad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff\U000e0000-\U000e007f]")


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


def thread_of(item: dict) -> dict:
    """What its source kept for answering it. `record` doesn't read it, and an empty one is fine."""
    return json.loads(item["thread_json"] or "{}")


def label(item_id: int) -> str:
    """An inbox item's id, which Ting Yu sees on its report and types to act on it."""
    return f"I-{item_id:04d}"


def set_item_state(conn: sqlite3.Connection, item_id: int, state: str, *, note: str | None = None) -> None:
    """Move an inbox item on. A `note` joins what it already says, and the intake's warning stays."""
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    found = get(conn, item_id) if note else None
    said = " ".join(part for part in (found["note"], note) if part) if found else None
    conn.execute("UPDATE inbox_items SET state = ?, note = COALESCE(?, note), updated_at = ? WHERE id = ?",
                 (state, said, timeutil.stamp(), item_id))


# --- reports ------------------------------------------------------------------


# Owed a report now. Noise never is (R2), and a message waiting for triage isn't yet: its report says
# what triage made of it (R1).
_OWED = "reported_at IS NULL AND state NOT IN ('noise', 'new')"


def unreported(conn: sqlite3.Connection) -> list[dict]:
    """Every inbox item owed a report now, oldest first."""
    return db.rows(conn, f"SELECT * FROM inbox_items WHERE {_OWED} ORDER BY id")


def by_conversation(items: list[dict]) -> dict[str, list[dict]]:
    """`items` by conversation, in the order each first appears, keeping their order within it."""
    found: dict[str, list[dict]] = {}
    for item in items:
        found.setdefault(item["conversation"], []).append(item)
    return found


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
        "unreported": db.scalar(conn, f"SELECT count(*) FROM inbox_items WHERE {_OWED}") or 0,
        "hand_replies": db.scalar(conn, "SELECT count(*) FROM inbox_items WHERE state = ?", (NEEDS_HAND_REPLY,)) or 0,
    }


# --- triage -------------------------------------------------------------------


def waiting_for_triage(conn: sqlite3.Connection) -> list[dict]:
    """Every message a person wrote that triage hasn't dealt with, oldest first."""
    places = ", ".join("?" for _ in PEOPLE_SOURCES)
    return db.rows(conn, f"SELECT * FROM inbox_items WHERE state = ? AND source IN ({places}) ORDER BY id", (NEW, *PEOPLE_SOURCES))


def in_conversation(conn: sqlite3.Connection, conversation: str) -> list[dict]:
    """Every message in one conversation, oldest first."""
    return db.rows(conn, "SELECT * FROM inbox_items WHERE conversation = ? ORDER BY id", (conversation,))


def count_attempt(conn: sqlite3.Connection, item_ids: list[int]) -> None:
    for item_id in item_ids:
        conn.execute("UPDATE inbox_items SET triage_attempts = triage_attempts + 1, updated_at = ? WHERE id = ?", (timeutil.stamp(), item_id))


def set_attempts(conn: sqlite3.Connection, item_ids: list[int], attempts: int) -> None:
    for item_id in item_ids:
        conn.execute("UPDATE inbox_items SET triage_attempts = ?, updated_at = ? WHERE id = ?", (attempts, timeutil.stamp(), item_id))


def set_brand_failures(conn: sqlite3.Connection, item_ids: list[int], failures: int) -> None:
    for item_id in item_ids:
        conn.execute("UPDATE inbox_items SET brand_failures = ?, updated_at = ? WHERE id = ?", (failures, timeutil.stamp(), item_id))


def update_triage(conn: sqlite3.Connection, item_id: int, *, state: str, note: str, kind: str | None, priority: str | None,
                  language: str | None, draft: str | None, promised: bool) -> None:
    """What triage decided about one message. Its text and everything else read at intake stay."""
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}")
    conn.execute(
        "UPDATE inbox_items SET state = ?, note = ?, class = ?, priority = ?, language = ?, draft = ?, promised = ?, updated_at = ? WHERE id = ?",
        (state, note, kind, priority, language, draft, int(promised), timeutil.stamp(), item_id),
    )


# --- replies going out --------------------------------------------------------


def drafts_without_a_card(conn: sqlite3.Connection) -> list[dict]:
    """Email drafts triage has finished with that haven't been asked about yet, oldest first."""
    places = ", ".join("?" for _ in MAIL_SOURCES)
    return db.rows(conn, f"SELECT * FROM inbox_items WHERE state = ? AND source IN ({places}) ORDER BY id", (TRIAGED, *MAIL_SOURCES))


def with_state(conn: sqlite3.Connection, state: str) -> list[dict]:
    return db.rows(conn, "SELECT * FROM inbox_items WHERE state = ? ORDER BY id", (state,))


def sent_on(conn: sqlite3.Connection, day: str) -> int:
    return db.scalar(conn, "SELECT count(*) FROM inbox_items WHERE substr(sent_at, 1, 10) = ?", (day,)) or 0


def outcomes_owed(conn: sqlite3.Connection) -> list[dict]:
    """Replies whose outcome Ting Yu hasn't heard yet (F15, S7), oldest first."""
    return db.rows(
        conn,
        "SELECT * FROM inbox_items WHERE told_at IS NULL AND (sent_at IS NOT NULL OR state IN (?, ?, ?)) ORDER BY id",
        (FAILED, UNKNOWN, LAPSED),
    )


def mark_told(conn: sqlite3.Connection, item_id: int) -> None:
    now = timeutil.stamp()
    conn.execute("UPDATE inbox_items SET told_at = ?, updated_at = ? WHERE id = ?", (now, now, item_id))


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


def outgoing_id(seed: str, domain: str) -> str:
    """The `Message-ID` for one message Jura sends. The same `seed` gives the same id, so a retry under
    one claim carries it again. `seed` holds the approval's content hash, which leaves nothing to guess:
    an answer that names this id came from someone who was shown it."""
    return f"<{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:32]}@{domain}>"


def remember_outgoing(conn: sqlite3.Connection, message_id: str, *, lead_id: int | None = None) -> None:
    """Keep the `Message-ID` of a message Jura sent, so its copy is recognised (F4) and an answer
    naming it finds its lead (F2). Inbox replies write it in their claim, before Resend is called, so a
    copy that lands first is still known.

    Outreach sends set no `Message-ID`, by decision in ticket 03's code review: Resend may override the
    header, and a refusal would fail live outreach. So answers to outreach have nothing to look up, and
    F2's domain match is what covers them (`replies.Contacts.match`): a colleague on the lead's domain
    counts, and someone elsewhere is reported as a stranger. Copies are dropped by sender domain, so F4
    holds whether or not Resend keeps an id. UAT Part B checks that it takes the header on an inbox reply.
    """
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
