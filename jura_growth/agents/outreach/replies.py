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
(`Contacts`, `opt_out_reason`, `own_text`, `bulk_evidence`, `verdicts`), and
recording a reply (`apply_reply`). A reply `inbox-check` has already counted is
skipped here by its `message_key`, so this check posts only what that one
missed.
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
from email.header import Header, decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterator

from jura_growth import caps, config, db, log, privacy, suppression, timeutil
from jura_growth.agents.outreach import store
from jura_growth.agents.scout import contact as scout_contact

SETTINGS = ("OUTREACH_IMAP_HOST", "OUTREACH_IMAP_USER", "OUTREACH_IMAP_PASSWORD")
MAX_BODY_BYTES = 512_000
OPT_OUT_MAX_WORDS = 12
OPT_OUT_WORD_RE = re.compile(r"\b(remove|stop)\b", re.I)
# Words that ask to be left alone wherever they are, however long the message (P-9). Each is about
# the person or the mail, so "stop these duplicate invoices" and "remove my old invoices" aren't.
_MAIL = r"(?:e-?mails?|mails?|messages?|newsletters?|marketing|spam)"
EXPLICIT_OPT_OUT_RE = re.compile(
    rf"""
    \b(?P<unsubscribe>unsubscribe)\b
    | \b(?P<stop>stop)\s+(?:spamming|bothering|harassing)\b
    | \b(?P<stop2>stop)\s+(?:e-?mailing|contacting|messaging|mailing|writing\s+to)\s*(?:me\b|us\b|[.!?]|$)
    | \b(?P<stop3>stop)\s+sending\s+(?:me|us)\b
    | \b(?P<stop4>stop)\s+(?:sending\s+)?(?:the\s+|these\s+|this\s+|those\s+|your\s+|all\s+|any\s+)?(?:\w+\s+)?{_MAIL}\b
    | \b(?P<remove>remove)\s+(?:me|us)\b
    | \b(?P<remove2>remove)\s+(?:my|our)\s+(?:e-?mail(?:\s+address)?|address|contact(?:\s+details)?|details|name)\b
    | \b(?P<remove3>remove)\s+(?:this|that)\s+(?:e-?mail\s+)?address\b
    | \b(?P<remove4>remove)\s+\S+@\S+
    | \b(?P<remove5>remove)\b[^.?!\n]{{0,40}}\bfrom\s+(?:your|the)\s+(?:\w+\s+)?list\b
    | \b(?P<take>take)\s+(?:me|us|(?:my|our)\s+\S+)\s+off\b
    | \b(?P<opt>opt)(?:ing)?\s+(?:me\s+|us\s+)?out\b
    | \b(?P<dont>do\s+not|don'?t)\s+(?:e-?mail|contact|message|write\s+to)\s+(?:me|us)\b
    | \b(?P<nomore>no\s+more)\s+{_MAIL}\b
    """,
    re.I | re.X | re.M,
)
_OPT_OUT_NAMES = {"stop": "stop", "remove": "remove", "take": "take off", "opt": "opt out", "dont": "do not contact",
                  "nomore": "no more", "unsubscribe": "unsubscribe"}
# Words beside "stop" or "remove" that give it no other object, so a sentence of only these asks out.
_FILLERS = frozenset("please pls kindly now immediately asap just thanks thank you it them that this at once right away".split())
_NO_OTHER_OBJECT = frozenset("please pls kindly now immediately asap it them that me us".split())
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[\w'@.+-]*\w")
_SIGN_OFF_RE = re.compile(
    r"^[ \t]*(?:--[ \t]*|_{2,}[ \t]*"
    r"|(?:(?:kind|best|warm|warmest)\s+)?regards[,.!]?|best(?:\s+wishes)?[,.!]?|thanks(?:\s*(?:and|&)\s*regards)?[,.!]?"
    r"|thank\s+you[,.!]?|cheers[,.!]?|sincerely[,.!]?|yours\s+(?:sincerely|faithfully|truly)[,.!]?|rgds[,.!]?)[ \t]*$",
    re.I | re.M,
)
SUBJECT_PREFIX_RE = re.compile(r"^(?:\s*(?:re|fwd?|aw|wg)\s*(?:\[\d+\])?\s*:\s*)+", re.I)
AUTO_SUBJECT_RE = re.compile(r"\b(?:out of (?:the )?office|automatic reply|auto(?:matic)?[- ]?reply|autoreply|on leave|away from)\b", re.I)
QUOTE_START_RE = re.compile(
    r"^(?:On .{4,200}wrote:\s*$|-{2,}\s*Original Message\s*-{2,}|From:\s|Sent from my |_{5,}|>)", re.I | re.M
)
NO_REPLY_LOCAL_RE = re.compile(r"(?:no|do[-_.]?not)[-_.]?reply|mailer[-_.]?daemon|postmaster|bounces?", re.I)
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
    return all(config.secret(n) for n in SETTINGS)


def account_from(label: str, prefix: str) -> Account:
    """The login in `<prefix>_HOST`, `_PORT`, `_USER` and `_PASSWORD`, which the caller checked."""
    return Account(
        label,
        config.require(f"{prefix}_HOST"),
        int(config.secret(f"{prefix}_PORT") or 993),
        config.require(f"{prefix}_USER"),
        config.require(f"{prefix}_PASSWORD"),
    )


def account() -> Account | None:
    """The Reply-To mailbox, or None when it isn't set up."""
    return account_from("levi", "OUTREACH_IMAP") if enabled() else None


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
    """Headers for a batch of messages in one FETCH. A refusal raises: a check that didn't see them
    hasn't finished, and must not read as a quiet one."""
    status, data = imap.fetch(b",".join(numbers).decode(), HEADER_FIELDS)
    if status != "OK":
        raise RepliesError("IMAP refused a header fetch")
    found = []
    for meta, literal in _fetch_parts(data):
        size = re.search(rb"RFC822\.SIZE (\d+)", meta or b"")
        found.append(Headers((meta or b"").split(b" ", 1)[0], int(size.group(1)) if size else 0,
                             email.message_from_bytes(literal)))
    return found


def body_of(imap, number: bytes, spec: str = WHOLE_BODY, *, expected: Message | None = None) -> Message | None:
    """One message whole, or as much as `spec` asks for, without marking it read. None when it
    can't be had now: the fetch was refused, or `expected`'s Message-ID says this body is another
    message's, because deleting mail during a check shifts the numbers. The caller leaves that
    message for the next check, so nobody's words land under someone else's name."""
    if not number.isdigit():
        return None
    status, data = imap.fetch(number.decode(), spec)
    if status != "OK":
        return None
    for _, raw in _fetch_parts(data):
        body = email.message_from_bytes(raw)
        wanted = str(expected.get("Message-ID") or "").strip() if expected is not None else ""
        if wanted and str(body.get("Message-ID") or "").strip() not in ("", wanted):
            return None
        return body
    return None


# --- what a message means -----------------------------------------------------


def header_text(value) -> str:
    """A header as text, with any encoded words decoded, however broken they are. Raw UTF-8, which
    the parser holds as surrogates or an unknown-8bit `Header`, reads as the text it is."""
    if isinstance(value, Header):
        pieces = decode_header(value)
        value = "".join(p.decode("utf-8", "replace") if isinstance(p, bytes) else p for p, _ in pieces)
    text = str(value or "").encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    try:
        return str(make_header(decode_header(text)))
    except (LookupError, UnicodeError, ValueError):
        return text


def bare_subject(subject: str) -> str:
    """A subject without its `Re:` and `Fwd:`, for comparing one with another."""
    return " ".join(SUBJECT_PREFIX_RE.sub("", subject).split()).casefold()


def under_domain(domain: str, parent: str) -> bool:
    """Whether `domain` is `parent` or a subdomain of it, and not merely ending in its letters."""
    return domain == parent or domain.endswith(f".{parent}")


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
            if isinstance(part, Message):
                yield from _readable_parts(part)
    elif not message.get_filename():
        yield message


def _from_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?is)<blockquote.*", "", text)
    text = re.sub(r"(?is)<div[^>]*gmail_quote.*", "", text)
    text = re.sub(r"(?i)<br\s*/?>|</p\s*>|</div\s*>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


def plain_text(message: Message) -> str:
    """The message's words as written: its plain part, or its HTML part as text."""
    parts = list(_readable_parts(message))
    part = next((p for p in parts if p.get_content_type() == "text/plain"), None)
    if part is None:
        part = next((p for p in parts if p.get_content_type() == "text/html"), None)
    if part is None:
        return ""
    return _from_html(_decoded(part)) if part.get_content_type() == "text/html" else _decoded(part)


def own_text(message: Message) -> str:
    """The reply's own words, without the quoted original. Someone who writes below the quote
    keeps their words."""
    text = plain_text(message)
    match = QUOTE_START_RE.search(text)
    if not match:
        return text
    head = text[: match.start()]
    if head.strip():
        return head
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def _without_signature(own: str) -> str:
    """Their words up to a sign-off line, so a footer's "unsubscribe" and a long signature don't
    count as what they said. A message that is only a sign-off stays as it is."""
    match = _SIGN_OFF_RE.search(own)
    head = own[: match.start()] if match else own
    return head if head.strip() else own


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _is_only_the_word(sentence: str, word: str) -> bool:
    """"Please stop." or "Remove it please.": nothing else in the sentence for it to be about."""
    return [t for t in _TOKEN.findall(sentence.lower()) if t not in _FILLERS] == [word]


def _word_is_about_them(sentence: str, word: str) -> bool:
    """For a question: whether the word has no other object. "Can you stop?" asks out, and "How do
    we stop this happening?" is about something else. In doubt it counts, because a wrong
    suppression shows in the report and can be undone, and a lost opt-out shows nowhere."""
    tokens = _TOKEN.findall(sentence.lower())
    after = tokens[tokens.index(word) + 1 :] if word in tokens else []
    return not after or after[0] in _NO_OTHER_OBJECT or after == ["this"]


def _short_opt_out(text: str) -> str | None:
    """`remove` or `stop` in a short text, judged by the sentence that holds it."""
    for sentence in _sentences(text):
        match = OPT_OUT_WORD_RE.search(sentence)
        if match:
            word = match.group(1).lower()
            if not sentence.endswith("?") or _word_is_about_them(sentence, word):
                return word
    return None


def _explicit_opt_out(text: str) -> str | None:
    """The fixed name of an explicit ask in `text`, never the text itself: it goes in a report's
    frame, outside the quote."""
    match = EXPLICIT_OPT_OUT_RE.search(text)
    if not match:
        return None
    return _OPT_OUT_NAMES[(match.lastgroup or "").rstrip("0123456789")]


def opt_out_reason(subject: str, own: str, ours: frozenset[str] | set[str] = frozenset()) -> str | None:
    """Why this message asks to be removed, in words for the report, or None. One rule for both
    checks (inbox watch PRD, F1, as decided in code review 01):

    - an explicit ask (`unsubscribe`, `stop emailing`, `remove me`, `take me off` and the like)
      suppresses at any length, in their own words with quote and signature removed;
    - so does a sentence that is only the word: "Please stop.";
    - `remove` or `stop` otherwise counts in the subject, or in a message of 12 words or fewer. A
      question is exempt only when the word plainly has another object.

    `ours` holds the subjects Jura sent them (`sent_subjects`), which aren't their words, so
    "Re: Stop retyping invoices" says nothing about what they want."""
    subject = "" if bare_subject(subject) in ours else subject
    words = _without_signature(own)
    named = _explicit_opt_out(subject) or _explicit_opt_out(words)
    if named:
        return f"an explicit ask, with the word {named}"
    for sentence in _sentences(words):
        match = OPT_OUT_WORD_RE.search(sentence)
        if match and _is_only_the_word(sentence, match.group(1).lower()):
            return f"a sentence that is only the word {match.group(1).lower()}"
    word = _short_opt_out(SUBJECT_PREFIX_RE.sub("", subject))
    if word:
        return f"the subject has the word {word}"
    word = _short_opt_out(words) if len(words.split()) <= OPT_OUT_MAX_WORDS else None
    return f"a short message with the word {word}" if word else None


def bulk_evidence(headers: Message, sender: str) -> str | None:
    """What in the headers says no person wrote this (inbox watch PRD, F3), or None. Both checks
    use it, so a newsletter from a lead's own domain is neither a reply nor an opt-out."""
    if headers.get("List-Id") is not None:
        return "it has a List-Id"
    if headers.get("List-Unsubscribe") is not None:
        return "it has a List-Unsubscribe"
    if str(headers.get("Precedence", "")).strip().lower() in ("bulk", "list", "junk"):
        return "its Precedence says bulk mail"
    if str(headers.get("Auto-Submitted", "no")).strip().lower() not in ("", "no"):
        return "it was sent automatically"
    if sender and NO_REPLY_LOCAL_RE.fullmatch(sender.split("@", 1)[0]):
        return "it came from a no-reply address"
    return None


def verdicts(headers: Message) -> list[str]:
    """The clauses of the receiving server's own `Authentication-Results`, lower-cased, without
    comments or quoted strings, because a sender chooses what those say. It is the top header:
    a sender can add one of their own, but only below it."""
    results = headers.get_all("Authentication-Results") or ()
    if not results:
        return []
    text = re.sub(r'"[^"]*"', '""', str(results[0]))
    while True:
        stripped = re.sub(r"\([^()]*\)", " ", text)
        if stripped == text:
            break
        text = stripped
    return [clause.strip().lower() for clause in text.split(";")[1:]]


def dkim_pass_domains(headers: Message) -> list[str]:
    """Each domain the receiving server says signed this message and passed."""
    domains = []
    for clause in verdicts(headers):
        if clause.startswith("dkim=pass"):
            match = re.search(r"(?:^|\s)header\.(?:d=|i=[^@\s]*@)([a-z0-9.-]+)(?=\s|$)", clause)
            if match:
                domains.append(match.group(1))
    return domains


def failed_verdict(headers: Message, domain: str) -> bool:
    """Whether the server says mail claiming `domain` failed, with nothing aligned passing. Only a
    failure counts, not a missing verdict: plenty of small companies sign nothing, and treating them
    as forged would chase a colleague who has already answered."""
    clauses = verdicts(headers)
    if any(under_domain(d, domain) for d in dkim_pass_domains(headers)):
        return False
    if any(clause.startswith("dmarc=pass") for clause in clauses):
        return False
    return any(clause.startswith(("dmarc=fail", "dkim=fail", "spf=fail", "spf=softfail")) for clause in clauses)


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

    def match(self, sender: str, headers: Message) -> dict | None:
        """The sender's own record, or the lead whose own domain the sender is on (F2). A domain
        match reaches addresses Jura never wrote to, so it has to look like a person there: not
        bulk mail, and not a message the receiving server says failed. Otherwise anyone could
        unsubscribe a lead by forging a colleague."""
        exact = self.by_address.get(sender)
        if exact:
            return exact
        domain = suppression.domain_of(sender)
        colleague = self.by_domain.get(domain)
        if colleague is None or bulk_evidence(headers, sender) or failed_verdict(headers, domain):
            return None
        return colleague


def sent_contacts(conn: sqlite3.Connection) -> Contacts:
    return Contacts(db.rows(
        conn,
        "SELECT c.email, c.id AS contact_id, c.lead_id, min(m.sent_at) AS first_sent, l.company, l.domain "
        "FROM contacts c JOIN outreach_messages m ON m.contact_id = c.id JOIN leads l ON l.id = c.lead_id "
        "WHERE m.mode = 'live' AND m.sent_at IS NOT NULL GROUP BY c.id",
    ))


def sent_subjects(conn: sqlite3.Connection, lead_id: int) -> set[str]:
    """The subjects Jura sent this lead, as `bare_subject` reads them."""
    rows = db.rows(conn, "SELECT DISTINCT subject FROM outreach_messages WHERE lead_id = ? AND sent_at IS NOT NULL", (lead_id,))
    return {bare_subject(r["subject"]) for r in rows}


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
                result: Result | None = None, *, post: bool = True) -> bool:
    """A lead replied: count it, cancel what was queued, and suppress the sender on an opt-out,
    in one step. With `post` it also says so in #outreach-replies, once that has committed; an
    inbox report takes that message's place when `inbox-check` found the reply.

    False, with nothing changed or posted, when it was already counted: `inbox-check` and the
    16:45 check both run at 16:45, and each looks before it fetches the body."""
    lead_id = contact["lead_id"]
    with db.atomic(conn):
        inserted = conn.execute(
            "INSERT OR IGNORE INTO outreach_replies (lead_id, contact_id, message_key, received_at, unsubscribe, detected_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (lead_id, contact["contact_id"], key, timeutil.stamp(received), int(wants_out), timeutil.stamp()),
        ).rowcount
        if not inserted:
            return False
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
    if post:
        note = " They asked to be removed: the address is suppressed." if wants_out else ""
        # "Levi's mailbox", not the address: privacy removes Ting Yu's own
        # addresses from Discord (MC §4.4), so the address would read "[removed]".
        store.post(
            conn,
            "outreach-replies",
            f"**Reply** from {contact['domain']} ({contact['company']}, lead {lead_id}) at "
            f"{timeutil.stamp(received)[:16].replace('T', ' ')} SGT. It's in Levi's mailbox.{note}",
        )
    return True


# --- the 16:45 check ----------------------------------------------------------


def check(conn: sqlite3.Connection, *, days: int = caps.INBOX_LOOK_BACK_DAYS) -> Result | None:
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
        contact = known.match(sender, headers)
        if contact is None:
            continue
        received = received_at(headers)
        if received is None or received < timeutil.parse(contact["first_sent"]):
            continue
        subject = header_text(headers.get("Subject", ""))
        privacy.never_show(subject)  # read in memory only; never posted (MC §4.4)
        if is_automatic(headers, subject):
            continue
        key = message_key(headers, sender, received)
        if counted(conn, key):
            continue

        ours = sent_subjects(conn, contact["lead_id"])
        wants_out = bool(opt_out_reason(subject, "", ours))
        if not wants_out and found.size <= MAX_BODY_BYTES:
            body = body_of(imap, found.number, expected=headers)
            if body is None:
                continue  # refused or shifted: the next check reads it, so an opt-out isn't lost
            own = own_text(body)
            # Lines of four words or more: a sign-off ("Best regards") would blank later posts.
            privacy.never_show(*(line for line in own.splitlines() if len(line.split()) >= 4))
            wants_out = bool(opt_out_reason(subject, own, ours))
        apply_reply(conn, contact, sender, received, key, wants_out, result)
