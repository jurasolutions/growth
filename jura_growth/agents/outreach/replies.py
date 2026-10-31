"""Optional, read-only reply detection on levi@jurasolutions.sg, the Reply-To
and List-Unsubscribe mailbox (PRD §5.5, §5.6a).

On only when `OUTREACH_IMAP_HOST`, `OUTREACH_IMAP_USER` and
`OUTREACH_IMAP_PASSWORD` are set (`OUTREACH_IMAP_PORT` defaults to 993).

- The mailbox is opened with EXAMINE (read-only) and every fetch uses
  BODY.PEEK, so nothing is marked read, moved or deleted.
- Headers are read for every recent message; a message is looked at further
  only if its sender is an address we have emailed, or a colleague on that
  lead's own domain.
- Stored here: which lead replied and when, plus a hash of the Message-ID so a
  reply is counted once. No bodies and no subjects are stored here. A reply's
  own text (quoted text removed) is read in memory only to look for an opt-out
  (`opt_out_reason`), which suppresses the address.
- Auto-replies (Auto-Submitted, "out of office", "automatic reply") are
  ignored.

The module has three parts, which `inbox-check` (agents/inbox) shares with the
16:45 `check` below: reading a mailbox (`mailbox`, `open_folder`,
`numbers_since`, `headers_of`, `body_of`), the rules for what a message means
(`Contacts`, `opt_out_reason`, `own_text`), and recording a reply
(`apply_reply`). A reply `inbox-check` has already counted is skipped here by
its `message_key`, so this check posts only what that one missed.
"""

from __future__ import annotations

import email
import hashlib
import html
import imaplib
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterator

from jura_growth import config, db, log, privacy, suppression, timeutil
from jura_growth.agents.outreach import store
from jura_growth.agents.scout import contact as scout_contact

MAX_BODY_BYTES = 512_000
OPT_OUT_WORD_RE = re.compile(r"\b(remove|stop)\b", re.I)
UNSUBSCRIBE_RE = re.compile(r"\bunsubscribe\b", re.I)
# A question is an opt-out only when it names the person or the mail. "How do we stop retyping
# invoices?" is a customer asking something, however short (inbox watch PRD, F1).
ASKED_OUT_RE = re.compile(
    r"\b(?:remove\s+(?:me|us|my|our)\b|stop\s+(?:e-?mailing|contacting|sending|mailing|messaging|writing|these|this|your))",
    re.I,
)
OPT_OUT_MAX_WORDS = 12
AUTO_SUBJECT_RE = re.compile(r"\b(?:out of (?:the )?office|automatic reply|auto(?:matic)?[- ]?reply|autoreply|on leave|away from)\b", re.I)
QUOTE_START_RE = re.compile(
    r"^(?:On .{4,200}wrote:\s*$|-{2,}\s*Original Message\s*-{2,}|From:\s|Sent from my |_{5,}|>)", re.I | re.M
)
HEADER_FIELDS = (
    "(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM DATE MESSAGE-ID AUTO-SUBMITTED SUBJECT REPLY-TO TO CC IN-REPLY-TO "
    "REFERENCES LIST-ID LIST-UNSUBSCRIBE PRECEDENCE AUTHENTICATION-RESULTS)])"
)
WHOLE_BODY = "(BODY.PEEK[])"


class RepliesError(RuntimeError):
    pass


class RepliesAuthError(RepliesError):
    """The mailbox refused the login, which waiting won't fix."""


@dataclass
class Result:
    checked: int = 0
    replies: list[dict] = field(default_factory=list)
    unsubscribes: int = 0


@dataclass(frozen=True)
class Account:
    """One mailbox's login. Never printed: the password stays out of its repr."""

    label: str
    host: str
    port: int
    user: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class Headers:
    """One message's headers from a FETCH: its number in the folder, its size, the headers."""

    number: bytes
    size: int
    message: Message


def enabled() -> bool:
    return all(config.secret(n) for n in ("OUTREACH_IMAP_HOST", "OUTREACH_IMAP_USER", "OUTREACH_IMAP_PASSWORD"))


def account() -> Account | None:
    """The Reply-To mailbox, or None when it isn't set up."""
    if not enabled():
        return None
    return Account(
        "levi",
        config.secret("OUTREACH_IMAP_HOST"),
        int(config.secret("OUTREACH_IMAP_PORT") or 993),
        config.secret("OUTREACH_IMAP_USER"),
        config.secret("OUTREACH_IMAP_PASSWORD"),
    )


def imap_factory(host: str, port: int):
    """The IMAP connection (tests replace it)."""
    return imaplib.IMAP4_SSL(host, port, timeout=30)


# --- reading a mailbox --------------------------------------------------------


@contextmanager
def mailbox(login: Account) -> Iterator:
    """A logged-in connection, logged out afterwards. Any IMAP or network fault becomes a
    `RepliesError`, and a refused login a `RepliesAuthError`."""
    try:
        imap = imap_factory(login.host, login.port)
    except (OSError, imaplib.IMAP4.error) as error:
        raise RepliesError(f"IMAP connection to {login.host} failed ({type(error).__name__})") from None
    try:
        try:
            imap.login(login.user, login.password)
        except imaplib.IMAP4.error as error:
            raise RepliesAuthError(f"IMAP login refused ({type(error).__name__})") from None
        yield imap
    except (imaplib.IMAP4.error, OSError) as error:
        raise RepliesError(f"IMAP error: {type(error).__name__}: {str(error)[:120]}") from None
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001 - logging out is best effort
            pass


def open_folder(imap, folder: str = "INBOX") -> None:
    """EXAMINE the folder: nothing a read does can change it."""
    status, _ = imap.select(folder, readonly=True)
    if status != "OK":
        raise RepliesError(f"could not open {folder} read-only")


def numbers_since(imap, since: date) -> list[bytes]:
    """The message numbers from `since` on, oldest first."""
    status, data = imap.search(None, "SINCE", since.strftime("%d-%b-%Y"))
    if status != "OK":
        raise RepliesError("IMAP search failed")
    return (data[0] or b"").split() if data else []


def _fetch_parts(data) -> list[tuple[bytes, bytes]]:
    """(meta line, literal) pairs from an IMAP FETCH response."""
    return [(item[0], item[1]) for item in data or [] if isinstance(item, tuple) and len(item) >= 2]


def headers_of(imap, numbers: list[bytes]) -> list[Headers]:
    """Headers for a batch of messages in one FETCH."""
    status, data = imap.fetch(b",".join(numbers).decode(), HEADER_FIELDS)
    if status != "OK":
        return []
    found = []
    for meta, literal in _fetch_parts(data):
        size = re.search(rb"RFC822\.SIZE (\d+)", meta or b"")
        found.append(Headers((meta or b"").split(b" ", 1)[0], int(size.group(1)) if size else 0,
                             email.message_from_bytes(literal)))
    return found


def body_of(imap, number: bytes, spec: str = WHOLE_BODY) -> Message | None:
    """One message whole, or as much as `spec` asks for, without marking it read."""
    if not number.isdigit():
        return None
    status, data = imap.fetch(number.decode(), spec)
    if status != "OK":
        return None
    for _, raw in _fetch_parts(data):
        return email.message_from_bytes(raw)
    return None


# --- what a message means -----------------------------------------------------


def _decoded(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    if not isinstance(payload, bytes):
        return ""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:  # a charset Python doesn't know
        return payload.decode("utf-8", errors="replace")


def _readable_parts(message: Message) -> Iterator[Message]:
    """The message's own parts: not attachments, and not a message attached inside it."""
    if message.get_content_type() == "message/rfc822":
        return
    if message.is_multipart():
        for part in message.get_payload():
            yield from _readable_parts(part)
    elif not message.get_filename():
        yield message


def _from_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?is)<blockquote.*", "", text)
    text = re.sub(r"(?is)<div[^>]*gmail_quote.*", "", text)
    text = re.sub(r"(?i)<br\s*/?>|</p\s*>|</div\s*>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


def own_text(message: Message) -> str:
    """The reply's own words, without the quoted original."""
    parts = list(_readable_parts(message))
    part = next((p for p in parts if p.get_content_type() == "text/plain"), None)
    if part is None:
        part = next((p for p in parts if p.get_content_type() == "text/html"), None)
    if part is None:
        return ""
    text = _decoded(part)
    if part.get_content_type() == "text/html":
        text = _from_html(text)
    match = QUOTE_START_RE.search(text)
    return text[: match.start()] if match else text


def _short_opt_out(text: str) -> str | None:
    match = OPT_OUT_WORD_RE.search(text)
    if not match or ("?" in text and not ASKED_OUT_RE.search(text)):
        return None
    return match.group(1).lower()


def opt_out_reason(subject: str, own: str) -> str | None:
    """Why this message asks to be removed, in words for the report, or None. One rule for both
    checks (inbox watch PRD, F1): `unsubscribe` anywhere in a person's own words, `remove` or
    `stop` in the subject or in a message of 12 words or fewer. Anything else is a customer talking,
    and suppressing them would be permanent."""
    if UNSUBSCRIBE_RE.search(subject) or UNSUBSCRIBE_RE.search(own):
        return "they wrote the word unsubscribe"
    word = _short_opt_out(subject)
    if word:
        return f"the subject has the word {word}"
    word = _short_opt_out(own) if len(own.split()) <= OPT_OUT_MAX_WORDS else None
    return f"a short message with the word {word}" if word else None


class Contacts:
    """Who Jura has emailed, for telling a lead's reply from anyone else's mail."""

    def __init__(self, rows: list[dict]):
        self.by_address = {r["email"].lower(): r for r in rows}
        self.by_domain: dict[str, dict] = {}
        self.by_lead: dict[int, dict] = {}
        for row in rows:
            self.by_lead.setdefault(row["lead_id"], row)
            domain = (row["domain"] or "").lower()
            if domain and domain not in scout_contact.FREE_MAIL:
                self.by_domain.setdefault(domain, row)

    def __bool__(self) -> bool:
        return bool(self.by_address)

    def match(self, sender: str) -> dict | None:
        """The sender's own record, or the lead whose own domain the sender is on (F2)."""
        return self.by_address.get(sender) or self.by_domain.get(suppression.domain_of(sender))


def sent_contacts(conn: sqlite3.Connection) -> Contacts:
    return Contacts(db.rows(
        conn,
        "SELECT c.email, c.id AS contact_id, c.lead_id, min(m.sent_at) AS first_sent, l.company, l.domain "
        "FROM contacts c JOIN outreach_messages m ON m.contact_id = c.id JOIN leads l ON l.id = c.lead_id "
        "WHERE m.mode = 'live' AND m.sent_at IS NOT NULL GROUP BY c.id",
    ))


def received_at(headers: Message) -> datetime | None:
    """The message's Date, or None when it has no usable one."""
    try:
        received = parsedate_to_datetime(str(headers.get("Date", "")))
    except (TypeError, ValueError):
        return None
    return received.replace(tzinfo=timeutil.SGT) if received.tzinfo is None else received


def message_key(headers: Message, sender: str, received: datetime | None) -> str:
    """The hash that counts a message once, here and in `inbox-check`."""
    fallback = f"{sender}|{received.isoformat() if received else str(headers.get('Subject', ''))}"
    message_id = (str(headers.get("Message-ID") or "") or fallback).strip()
    return hashlib.sha256(message_id.encode("utf-8", "replace")).hexdigest()


def is_automatic(headers: Message, subject: str) -> bool:
    return (str(headers.get("Auto-Submitted", "no")).strip().lower() not in ("", "no")
            or bool(AUTO_SUBJECT_RE.search(subject)))


def counted(conn: sqlite3.Connection, key: str) -> bool:
    return db.one(conn, "SELECT 1 FROM outreach_replies WHERE message_key = ?", (key,)) is not None


# --- recording a reply --------------------------------------------------------


def apply_reply(conn: sqlite3.Connection, contact: dict, sender: str, received: datetime, key: str, wants_out: bool,
                result: Result | None = None, *, post: bool = True) -> None:
    """A lead replied: count it, cancel what was queued, and suppress the sender on an opt-out,
    in one step. With `post` it also says so in #outreach-replies, once that has committed; an
    inbox report takes that message's place when `inbox-check` found the reply."""
    lead_id = contact["lead_id"]
    with db.atomic(conn):
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
        if wants_out:
            suppression.add(conn, email=sender, reason="unsubscribe", source="reply")
            store.set_lead_status(conn, [lead_id], "unsubscribed")
        log.event(conn, "outreach.reply", {"lead": lead_id, "domain": contact["domain"], "unsubscribe": wants_out}, agent=store.AGENT)
    if result is not None:
        result.unsubscribes += int(wants_out)
        result.replies.append({"lead_id": lead_id, "domain": contact["domain"], "unsubscribe": wants_out})
    if not post:
        return
    note = " They asked to be removed: the address is suppressed." if wants_out else ""
    # "Levi's mailbox", not the address: privacy removes Ting Yu's own
    # addresses from Discord (MC §4.4), so the address would read "[removed]".
    store.post(
        conn,
        "outreach-replies",
        f"**Reply** from {contact['domain']} ({contact['company']}, lead {lead_id}) at "
        f"{timeutil.stamp(received)[:16].replace('T', ' ')} SGT. It's in Levi's mailbox.{note}",
    )


# --- the 16:45 check ----------------------------------------------------------


def check(conn: sqlite3.Connection, *, days: int = 45) -> Result | None:
    """Look for replies from emailed addresses. None when not set up."""
    login = account()
    if login is None:
        return None
    result = Result()
    known = sent_contacts(conn)
    if not known:
        return result

    with mailbox(login) as imap:
        open_folder(imap)
        numbers = numbers_since(imap, timeutil.today() - timedelta(days=days))
        for start in range(0, len(numbers), 200):
            _batch(conn, imap, numbers[start : start + 200], known, result)
    log.event(conn, "outreach.replies", {"checked": result.checked, "replies": len(result.replies), "unsubscribes": result.unsubscribes}, agent=store.AGENT)
    return result


def _batch(conn, imap, numbers: list[bytes], known: Contacts, result: Result) -> None:
    """Headers for a batch of messages in one FETCH; bodies only for replies."""
    for found in headers_of(imap, numbers):
        result.checked += 1
        headers = found.message
        sender = parseaddr(str(headers.get("From", "")))[1].strip().lower()
        contact = known.match(sender)
        if contact is None:
            continue
        received = received_at(headers)
        if received is None or received < timeutil.parse(contact["first_sent"]):
            continue
        subject = str(headers.get("Subject", ""))
        privacy.never_show(subject)  # read in memory only; never posted (MC §4.4)
        if is_automatic(headers, subject):
            continue
        key = message_key(headers, sender, received)
        if counted(conn, key):
            continue

        wants_out = bool(opt_out_reason(subject, ""))
        if not wants_out and found.size <= MAX_BODY_BYTES:
            body = body_of(imap, found.number)
            if body is not None:
                own = own_text(body)
                # Lines of four words or more: a sign-off ("Best regards") would blank later posts.
                privacy.never_show(*(line for line in own.splitlines() if len(line.split()) >= 4))
                wants_out = bool(opt_out_reason(subject, own))
        apply_reply(conn, contact, sender, received, key, wants_out, result)
