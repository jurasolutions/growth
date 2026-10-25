"""Optional, read-only reply detection on info@jurasolutions.sg (PRD §5.5).

On only when `OUTREACH_IMAP_HOST`, `OUTREACH_IMAP_USER` and
`OUTREACH_IMAP_PASSWORD` are set (`OUTREACH_IMAP_PORT` defaults to 993).

- The mailbox is opened with EXAMINE (read-only) and every fetch uses
  BODY.PEEK, so nothing is marked read, moved or deleted.
- Headers are read for every recent message; a message is looked at further
  only if its sender is an address we have emailed.
- Stored: which lead replied and when, plus a hash of the Message-ID so a
  reply is counted once. No bodies and no subjects are stored. A reply's own
  text (quoted text removed) is read in memory only to look for
  "unsubscribe", "remove" or "stop", which suppresses the address.
- Auto-replies (Auto-Submitted, "out of office", "automatic reply") are
  ignored.
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import timedelta
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from jura_growth import config, db, log, privacy, suppression, timeutil
from jura_growth.agents.outreach import store

MAX_BODY_BYTES = 512_000
UNSUBSCRIBE_RE = re.compile(r"\b(?:unsubscribe|remove|stop)\b", re.I)
AUTO_SUBJECT_RE = re.compile(r"\b(?:out of (?:the )?office|automatic reply|auto(?:matic)?[- ]?reply|autoreply|on leave|away from)\b", re.I)
QUOTE_START_RE = re.compile(
    r"^(?:On .{4,200}wrote:\s*$|-{2,}\s*Original Message\s*-{2,}|From:\s|Sent from my |_{5,}|>)", re.I | re.M
)


class RepliesError(RuntimeError):
    pass


@dataclass
class Result:
    checked: int = 0
    replies: list[dict] = field(default_factory=list)
    unsubscribes: int = 0


def enabled() -> bool:
    return all(config.secret(n) for n in ("OUTREACH_IMAP_HOST", "OUTREACH_IMAP_USER", "OUTREACH_IMAP_PASSWORD"))


def imap_factory(host: str, port: int):
    """The IMAP connection (tests replace it)."""
    return imaplib.IMAP4_SSL(host, port, timeout=30)


def _own_text(message: Message) -> str:
    """The reply's own words, without the quoted original."""
    part = None
    if message.is_multipart():
        for candidate in message.walk():
            if candidate.get_content_type() == "text/plain" and not candidate.get_filename():
                part = candidate
                break
        if part is None:
            for candidate in message.walk():
                if candidate.get_content_type() == "text/html":
                    part = candidate
                    break
    else:
        part = message
    if part is None:
        return ""
    payload = part.get_payload(decode=True) or b""
    text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<blockquote.*", "", text)
        text = re.sub(r"<[^>]+>", " ", text)
    match = QUOTE_START_RE.search(text)
    return text[: match.start()] if match else text


def _sent_contacts(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = db.rows(
        conn,
        "SELECT c.email, c.id AS contact_id, c.lead_id, min(m.sent_at) AS first_sent, l.company, l.domain "
        "FROM contacts c JOIN outreach_messages m ON m.contact_id = c.id JOIN leads l ON l.id = c.lead_id "
        "WHERE m.mode = 'live' AND m.sent_at IS NOT NULL GROUP BY c.id",
    )
    return {r["email"].lower(): r for r in rows}


def _fetch_parts(data) -> list[tuple[bytes, bytes]]:
    """(meta line, literal) pairs from an IMAP FETCH response."""
    return [(item[0], item[1]) for item in data or [] if isinstance(item, tuple) and len(item) >= 2]


def check(conn: sqlite3.Connection, *, days: int = 45) -> Result | None:
    """Look for replies from emailed addresses. None when not set up."""
    if not enabled():
        return None
    result = Result()
    known = _sent_contacts(conn)
    if not known:
        return result

    host = config.secret("OUTREACH_IMAP_HOST")
    port = int(config.secret("OUTREACH_IMAP_PORT") or 993)
    try:
        imap = imap_factory(host, port)
    except (OSError, imaplib.IMAP4.error) as error:
        raise RepliesError(f"IMAP connection to {host} failed ({type(error).__name__})") from None
    try:
        try:
            imap.login(config.secret("OUTREACH_IMAP_USER"), config.secret("OUTREACH_IMAP_PASSWORD"))
            status, _ = imap.select("INBOX", readonly=True)
            if status != "OK":
                raise RepliesError("could not open INBOX read-only")
            since = (timeutil.today() - timedelta(days=days)).strftime("%d-%b-%Y")
            status, data = imap.search(None, "SINCE", since)
            if status != "OK":
                raise RepliesError("IMAP search failed")
            numbers = (data[0] or b"").split() if data else []
            for start in range(0, len(numbers), 200):
                _batch(conn, imap, numbers[start : start + 200], known, result)
        except (imaplib.IMAP4.error, OSError) as error:
            raise RepliesError(f"IMAP error: {type(error).__name__}: {str(error)[:120]}") from None
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001 - logging out is best effort
            pass
    log.event(conn, "outreach.replies", {"checked": result.checked, "replies": len(result.replies), "unsubscribes": result.unsubscribes}, agent=store.AGENT)
    return result


HEADER_FIELDS = "(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM DATE MESSAGE-ID AUTO-SUBMITTED SUBJECT)])"


def _batch(conn, imap, numbers: list[bytes], known: dict, result: Result) -> None:
    """Headers for a batch of messages in one FETCH; bodies only for replies."""
    status, data = imap.fetch(b",".join(numbers).decode(), HEADER_FIELDS)
    if status != "OK":
        return
    for meta, literal in _fetch_parts(data):
        result.checked += 1
        number = (meta or b"").split(b" ", 1)[0]
        headers = email.message_from_bytes(literal)
        sender = parseaddr(headers.get("From", ""))[1].strip().lower()
        if sender not in known:
            continue
        contact = known[sender]
        try:
            received = parsedate_to_datetime(headers.get("Date", ""))
        except (TypeError, ValueError):
            continue
        if received.tzinfo is None:
            received = received.replace(tzinfo=timeutil.SGT)
        if received < timeutil.parse(contact["first_sent"]):
            continue
        if headers.get("Auto-Submitted", "no").strip().lower() not in ("", "no"):
            continue
        subject = str(headers.get("Subject", ""))
        privacy.never_show(subject)  # read in memory only; never posted (MC §4.4)
        if AUTO_SUBJECT_RE.search(subject):
            continue
        message_id = (headers.get("Message-ID") or f"{sender}|{received.isoformat()}").strip()
        key = hashlib.sha256(message_id.encode("utf-8")).hexdigest()
        if db.one(conn, "SELECT 1 FROM outreach_replies WHERE message_key = ?", (key,)):
            continue

        size_match = re.search(rb"RFC822\.SIZE (\d+)", meta or b"")
        size = int(size_match.group(1)) if size_match else 0
        wants_out = bool(UNSUBSCRIBE_RE.search(subject))
        if not wants_out and number.isdigit() and size <= MAX_BODY_BYTES:
            body_status, body_data = imap.fetch(number.decode(), "(BODY.PEEK[])")
            if body_status == "OK":
                for _, raw in _fetch_parts(body_data):
                    own = _own_text(email.message_from_bytes(raw))
                    # Lines of four words or more: a sign-off ("Best regards") would blank later posts.
                    privacy.never_show(*(line for line in own.splitlines() if len(line.split()) >= 4))
                    wants_out = bool(UNSUBSCRIBE_RE.search(own))
        _record(conn, contact, sender, received, key, wants_out, result)


def _record(conn, contact: dict, sender: str, received, key: str, wants_out: bool, result: Result) -> None:
    lead_id = contact["lead_id"]
    conn.execute(
        "INSERT INTO outreach_replies (lead_id, contact_id, message_key, received_at, unsubscribe, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (lead_id, contact["contact_id"], key, timeutil.stamp(received), int(wants_out), timeutil.stamp()),
    )
    conn.execute(
        "UPDATE outreach_messages SET status = 'replied' WHERE lead_id = ? AND mode = 'live' AND status = 'sent'",
        (lead_id,),
    )
    store.cancel_queued(conn, [lead_id], "the company replied")
    store.set_lead_status(conn, [lead_id], "replied")
    note = ""
    if wants_out:
        suppression.add(conn, email=sender, reason="unsubscribe", source="reply")
        store.set_lead_status(conn, [lead_id], "unsubscribed")
        result.unsubscribes += 1
        note = " They asked to be removed: the address is suppressed."
    result.replies.append({"lead_id": lead_id, "domain": contact["domain"], "unsubscribe": wants_out})
    log.event(conn, "outreach.reply", {"lead": lead_id, "domain": contact["domain"], "unsubscribe": wants_out}, agent=store.AGENT)
    store.post(
        conn,
        "outreach-replies",
        f"**Reply** from {contact['domain']} ({contact['company']}, lead {lead_id}) at "
        f"{timeutil.stamp(received)[:16].replace('T', ' ')} SGT. It's in info@jurasolutions.sg.{note}",
    )
