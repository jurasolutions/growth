"""The mail intake (W1, W5 to W8, R2, F2 to F4, F12, S11, S16; technical review B5).

Each mailbox is read through `outreach/replies.py`'s read-only pieces: EXAMINE and BODY.PEEK, so
nothing is marked read, moved or deleted. A message is fetched first and committed on its own, so
no transaction is ever open across the network and a decision in Discord never waits on IMAP.

What happens to a message, in order:

1. Jura's own mail is dropped, with no item and no count (F4), except the website form's.
2. Anything in the Junk folder only lists under noise (S16).
3. A signed website enquiry is the person in its `Reply-To` (W8). One that isn't signed is an
   ordinary stranger.
4. A lead's reply does what the 16:45 check would (W6), and counts there as already done.
5. Mail with evidence in its headers is noise (F3). Nothing else may be: a person writing from their
   own address is always reported, whatever they wrote.

A network fault never raises: a raising precheck is a failed run, and three flaps would pause the
mail for good. It is logged, and a refused login or two hours without a good check alerts once a
day. The last-good-check stamp moves only for a check that finished.
"""

from __future__ import annotations

import imaplib
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta
from email.header import Header, decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr

from jura_growth import config, db, discord, log, privacy, suppression, timeutil
from jura_growth.agents.inbox import settings, store
from jura_growth.agents.outreach import replies
from jura_growth.agents.scout import contact as scout_contact
from jura_growth.agents.scout import settings as scout_settings

AGENT = "inbox"
# Fetch only this much of a message. Its words come first, and it leaves a large attachment behind.
PARTIAL_BODY = f"(BODY.PEEK[]<0.{replies.MAX_BODY_BYTES}>)"
HEADER_BATCH = 200
OVERDUE_HOURS = 2
REFERENCES_KEPT = 20
ATTACHMENTS_KEPT = 5
SECOND_MAILBOX = ("ENQUIRY_IMAP_HOST", "ENQUIRY_IMAP_USER", "ENQUIRY_IMAP_PASSWORD")

_MESSAGE_ID = re.compile(r"<[!-;=?-~]{1,250}>")
_NO_REPLY = re.compile(r"(?:no|do[-_.]?not)[-_.]?reply|mailer[-_.]?daemon|postmaster|bounces?", re.I)
_SUBJECT_PREFIX = re.compile(r"^(?:\s*(?:re|fwd?|aw|wg)\s*(?:\[\d+\])?\s*:\s*)+", re.I)
_LIST_LINE = re.compile(rb'^\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.+)$')
_JUNK_NAMES = ("junk", "spam", "junk e-mail", "junk email", "bulk mail", "[gmail]/spam")
_ENQUIRY_NAME = re.compile(r"^Name: (.+)$", re.M)


@dataclass
class Intake:
    """How one check went: counts only, so it can go in a run record."""

    recorded: int = 0
    noise: int = 0
    dropped: int = 0
    replies: int = 0
    failed: int = 0


class _Spent(Exception):
    """The check's budget ran out. The rest waits for the next check."""


class _Budget:
    """B5 rule 3: wall clock and body fetches for one check, across its mailboxes."""

    def __init__(self) -> None:
        self.deadline = time.monotonic() + settings.limit("check_seconds")
        self.bodies = settings.limit("bodies_per_check")

    def check_time(self) -> None:
        if time.monotonic() >= self.deadline:
            raise _Spent

    def spend_body(self) -> None:
        if self.bodies <= 0:
            raise _Spent
        self.bodies -= 1


# --- the mailboxes -----------------------------------------------------------------


def _second_account() -> replies.Account | None:
    if not all(config.secret(name) for name in SECOND_MAILBOX):
        return None
    return replies.Account(
        "enquiry",
        config.require("ENQUIRY_IMAP_HOST"),
        int(config.secret("ENQUIRY_IMAP_PORT") or 993),
        config.require("ENQUIRY_IMAP_USER"),
        config.require("ENQUIRY_IMAP_PASSWORD"),
    )


def mailboxes() -> list[replies.Account]:
    """The Reply-To mailbox, and `info@` as a second one if it isn't delivered there (W8)."""
    return [login for login in (replies.account(), _second_account()) if login is not None]


def setup_gaps() -> list[str]:
    """The settings that are missing. The first mailbox is what makes the watch work at all; the
    second is optional, so it is a gap only when it is half set."""
    missing = [n for n in ("OUTREACH_IMAP_HOST", "OUTREACH_IMAP_USER", "OUTREACH_IMAP_PASSWORD") if not config.is_set(n)]
    if any(config.is_set(n) for n in SECOND_MAILBOX):
        missing += [n for n in SECOND_MAILBOX if not config.is_set(n)]
    return missing


# --- the check ---------------------------------------------------------------------


def intake(conn: sqlite3.Connection) -> Intake:
    """Read every mailbox and record what is new. Never raises for a network fault."""
    result = Intake()
    known = replies.sent_contacts(conn)
    budget = _Budget()
    for login in mailboxes():
        started = timeutil.stamp()
        try:
            finished = _read_mailbox(conn, login, known, budget, result)
        except replies.RepliesError as error:
            result.failed += 1
            _failed(conn, login, error)
            continue
        _reached(conn, login)
        if finished:
            store.set_state(conn, _last_success(login), started)
    log.event(conn, "inbox.checked", {"recorded": result.recorded, "noise": result.noise, "dropped": result.dropped,
                                      "replies": result.replies, "failed": result.failed}, agent=AGENT)
    return result


def _last_success(login: replies.Account) -> str:
    return f"mail.last_success.{login.label}"


def _since(conn: sqlite3.Connection, login: replies.Account) -> date:
    """W7: the first run's window, then the last good check less a day, and a long absence bounded."""
    today = timeutil.today()
    last = store.get_state(conn, _last_success(login))
    if last is None:
        return today - timedelta(days=settings.limit("first_run_days"))
    floor = today - timedelta(days=settings.limit("look_back_days"))
    return max(timeutil.parse(last).date() - timedelta(days=1), floor)


def _read_mailbox(conn, login: replies.Account, known: replies.Contacts, budget: _Budget, result: Intake) -> bool:
    """True when every message from the look-back was handled."""
    since = _since(conn, login)
    with replies.mailbox(login) as imap:
        replies.open_folder(imap)
        if not _read_folder(conn, imap, since, known, budget, result, junk=False):
            return False
        folder = _junk_folder(imap)
        if folder is None:
            return True
        try:
            replies.open_folder(imap, folder)
        except replies.RepliesError:
            log.event(conn, "inbox.no_junk_folder", {"mailbox": login.label}, agent=AGENT)
            return True
        return _read_folder(conn, imap, since, known, budget, result, junk=True)


def _junk_folder(imap) -> str | None:
    """The folder flagged `\\Junk`, or one with a usual name, quoted as the server wrote it."""
    status, lines = imap.list()
    if status != "OK":
        return None
    named = None
    for line in lines or ():
        match = _LIST_LINE.match(line) if isinstance(line, bytes) else None
        if not match:
            continue
        name = match.group("name").decode("utf-8", "replace").strip()
        if "\\junk" in match.group("flags").decode("utf-8", "replace").lower():
            return name
        if name.strip('"').lower() in _JUNK_NAMES:
            named = named or name
    return named


def _read_folder(conn, imap, since: date, known: replies.Contacts, budget: _Budget, result: Intake, *, junk: bool) -> bool:
    numbers = replies.numbers_since(imap, since)
    for start in range(0, len(numbers), HEADER_BATCH):
        for found in replies.headers_of(imap, numbers[start : start + HEADER_BATCH]):
            try:
                budget.check_time()
                _read_one(conn, imap, found, known, budget, result, junk=junk)
            except _Spent:
                return False
    return True


def _read_one(conn, imap, found: replies.Headers, known: replies.Contacts, budget: _Budget, result: Intake, *, junk: bool) -> None:
    key = _safe_key(found.message)
    if store.known(conn, key):
        return
    try:
        _take(conn, imap, found, key, known, budget, result, junk=junk)
    except (_Spent, replies.RepliesError, imaplib.IMAP4.error, OSError, sqlite3.Error):
        raise
    except Exception as error:  # noqa: BLE001 - one malformed message never stops the rest (A12)
        _unreadable(conn, found.message, key, error, result)


def _safe_key(headers: Message) -> str:
    try:
        sender = _one_address(str(headers.get("From", ""))) or ""
        return replies.message_key(headers, sender, replies.received_at(headers))
    except Exception:  # noqa: BLE001 - a header so broken it can't even be read
        return store.text_key("unreadable", repr(headers.items())[:4000])


def _take(conn, imap, found: replies.Headers, key: str, known: replies.Contacts, budget: _Budget, result: Intake,
          *, junk: bool) -> None:
    headers = found.message
    raw_from = str(headers.get("From", ""))
    sender = _one_address(raw_from) or ""
    message_ids = _ids(headers.get("Message-ID"))
    if message_ids and store.is_outgoing(conn, message_ids[0]):
        result.dropped += 1
        return

    subject = _decoded(headers.get("Subject", ""))
    from_form = sender == settings.ENQUIRY_SENDER
    if _is_jura(sender) and not from_form:
        result.dropped += 1
        return
    if junk:
        _record_noise(conn, key, sender, subject, "it was in the junk folder", result)
        return

    signed = from_form and _signed_by_jura(headers)
    received = replies.received_at(headers)
    contact = None if from_form else _contact_of(conn, known, sender, headers, received, subject)
    if contact is None and not from_form:
        evidence = _noise_evidence(headers, sender)
        if evidence:
            _record_noise(conn, key, sender, subject, evidence, result)
            return

    budget.spend_body()
    body = replies.body_of(imap, found.number, PARTIAL_BODY)
    own = ""
    attachments: tuple[str, ...] = ()
    if body is not None:
        own = replies.plain_text(body) if signed else replies.own_text(body)
        attachments = _attachment_names(body)

    reply_to = _recipient(headers, sender)
    wants_out = replies.opt_out_reason(subject, own) if contact else None
    stale = received is not None and timeutil.now() - received > timedelta(hours=settings.limit("old_after_hours"))
    counted_already = contact is not None and replies.counted(conn, key)
    who = reply_to if from_form else (sender or reply_to or "")
    # The form's own display name is Jura's, so the person's name comes from what the form wrote.
    typed = _ENQUIRY_NAME.search(own) if signed else None
    name = typed.group(1) if typed else ("" if from_form else _decoded(parseaddr(raw_from)[0]))

    state, notes = store.NEW, []
    if from_form and not signed:
        notes.append("It says it came from the website form, but it isn't signed by Jura.")
    if wants_out:
        state = store.REPORTED
        notes.append(f"They asked to be removed ({wants_out}): the address is suppressed and no reply will be drafted.")
    if stale:
        state = store.REPORTED
        notes.append("It's older than 48 hours: answer by hand if it still matters.")
    if reply_to is None:
        state = store.NEEDS_YOU
        notes.append("It has no single address to answer: reply by hand if it matters.")

    reaction = store.Reaction(
        source="enquiry" if signed else "email",
        key=key,
        conversation=store.text_key("mail", who or key, _topic(subject)),
        sender_name=name,
        sender_address=who or "",
        sender_domain=suppression.domain_of(who) if who else "",
        subject=subject,
        text=own,
        thread={
            "message_id": message_ids[0] if message_ids else None,
            "in_reply_to": next(iter(_ids(headers.get("In-Reply-To"))), None),
            "references": _ids(headers.get("References"))[-REFERENCES_KEPT:],
            "reply_to": reply_to,
            "copied": _copied(headers),
        },
        attachments=attachments,
        lead_id=contact["lead_id"] if contact else None,
        state=state,
        note=" ".join(notes),
        stale=stale,
        received_at=timeutil.stamp(received) if received else None,
        reported=counted_already and stale,  # told at the time by the 16:45 check, before this change
    )
    # What they wrote stays out of everything that isn't an inbox report (`privacy.py`).
    privacy.never_show(subject, name, *(line for line in own.splitlines() if len(line.split()) >= 4))
    if who:
        privacy.remember_address(who)

    with db.transaction(conn):
        outcome = store.record(conn, reaction)
        if isinstance(outcome, store.Recorded):
            if contact is not None and received is not None and not counted_already:
                replies.apply_reply(conn, contact, sender, received, key, bool(wants_out), post=False)
                result.replies += 1
            log.event(conn, "inbox.recorded", {"item": outcome.item_id, "source": reaction.source,
                                               "domain": reaction.sender_domain, "state": state}, agent=AGENT)
    result.recorded += 1


def _record_noise(conn, key: str, sender: str, subject: str, evidence: str, result: Intake) -> None:
    """R2: nothing is posted, and the domain and subject stay for the one-pager's list."""
    domain = suppression.domain_of(sender) if sender else ""
    with db.transaction(conn):
        store.record(conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=domain, subject=subject,
                                          state=store.NOISE, note=evidence))
    result.noise += 1


def _unreadable(conn, headers: Message, key: str, error: Exception, result: Intake) -> None:
    """A12: the person isn't lost to a parser bug. It is reported as needing a hand reply."""
    try:
        sender = _one_address(str(headers.get("From", ""))) or ""
    except Exception:  # noqa: BLE001
        sender = ""
    domain = suppression.domain_of(sender) if sender else ""
    with db.transaction(conn):
        store.record(conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=domain,
                                          state=store.NEEDS_YOU, note="This message couldn't be read: see the mailbox."))
        log.event(conn, "inbox.unreadable", {"domain": domain, "error": type(error).__name__}, level="warning", agent=AGENT)
    result.recorded += 1


# --- what a message says -----------------------------------------------------------


def _decoded(value) -> str:
    """A header as text, with any encoded words decoded, however broken they are. Raw UTF-8, which
    the parser holds as surrogates or an unknown-8bit `Header`, reads as the text it is."""
    if isinstance(value, Header):
        pieces = decode_header(value)
        value = "".join(p.decode("utf-8", "replace") if isinstance(p, bytes) else p for p, _ in pieces)
    text = str(value or "").encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    try:
        text = str(make_header(decode_header(text)))
    except (LookupError, UnicodeError, ValueError):
        pass
    return store.clean_line(text)


def _one_address(raw: str) -> str | None:
    """The single address `raw` holds, or None when it holds anything else (A8)."""
    found = [address for _, address in getaddresses([raw]) if address]
    if len(found) != 1:
        return None
    address = found[0].strip().lower()
    return address if scout_contact.ADDRESS_RE.fullmatch(address) else None


def _is_jura(address: str) -> bool:
    if not address:
        return False
    domain = suppression.domain_of(address)
    own = {settings.JURA_DOMAIN, str(scout_settings.get().get("sending_domain") or "").strip().lower()} - {""}
    return any(domain == d or domain.endswith(f".{d}") for d in own)


def _recipient(headers: Message, sender: str) -> str | None:
    """S11: `Reply-To` if it is set, otherwise `From`. One address that isn't Jura's, or None."""
    raw = headers.get("Reply-To")
    address = _one_address(str(raw)) if raw is not None else sender
    return address if address and not _is_jura(address) else None


def _copied(headers: Message) -> int:
    """How many other people were copied: named on the card and never included in a reply (S11)."""
    raw = headers.get_all("Cc") or ()
    return sum(1 for _, address in getaddresses([str(value) for value in raw]) if address and not _is_jura(address.lower()))


def _ids(value) -> list[str]:
    """Message ids from a header, and nothing else from it, so none can inject a header (A8)."""
    return _MESSAGE_ID.findall(str(value or ""))


def _signed_by_jura(headers: Message) -> bool:
    """The receiving server's own verdict, which is the top `Authentication-Results`. A sender can
    add one of their own, but only below it."""
    results = headers.get_all("Authentication-Results") or ()
    if not results:
        return False
    match = re.search(r"\bdkim=pass\b[^;]*?\bheader\.[di]=@?([a-z0-9.-]+)", str(results[0]), re.I)
    return bool(match) and _is_jura(f"x@{match.group(1).lower()}")


def _contact_of(conn, known: replies.Contacts, sender: str, headers: Message, received, subject: str) -> dict | None:
    """The lead this message answers (W6, F2), or None."""
    if received is None or replies.is_automatic(headers, subject):
        return None
    contact = known.match(sender) if sender else None
    if contact is None:
        lead_id = store.lead_of_outgoing(conn, [*_ids(headers.get("In-Reply-To")), *_ids(headers.get("References"))])
        contact = known.by_lead.get(lead_id) if lead_id is not None else None
    if contact is None or received < timeutil.parse(contact["first_sent"]):
        return None
    return contact


def _noise_evidence(headers: Message, sender: str) -> str | None:
    """F3: what in the headers says this isn't a person writing, or None."""
    if headers.get("List-Id") is not None:
        return "it has a List-Id"
    if headers.get("List-Unsubscribe") is not None:
        return "it has a List-Unsubscribe"
    if str(headers.get("Precedence", "")).strip().lower() in ("bulk", "list", "junk"):
        return "its Precedence says bulk mail"
    if str(headers.get("Auto-Submitted", "no")).strip().lower() not in ("", "no"):
        return "it was sent automatically"
    if not sender:
        return None
    if _NO_REPLY.fullmatch(sender.split("@", 1)[0]):
        return "it came from a no-reply address"
    domain = suppression.domain_of(sender)
    if any(domain == d or domain.endswith(f".{d}") for d in settings.platform_domains()):
        return "it came from a platform's notice address"
    return None


def _topic(subject: str) -> str:
    return " ".join(_SUBJECT_PREFIX.sub("", subject).split()).casefold()


def _attachment_names(message: Message) -> tuple[str, ...]:
    """What is attached, by name only. Attachments are never opened or kept (PRD §3)."""
    names = []
    for part in message.walk():
        if part.get_content_type() == "message/rfc822":
            continue
        name = part.get_filename()
        if name:
            names.append(_decoded(name)[:80])
    return tuple(names[:ATTACHMENTS_KEPT])


# --- when a mailbox can't be read --------------------------------------------------


def _failed(conn, login: replies.Account, error: replies.RepliesError) -> None:
    """B5 rule 1: logged every time, alerted once a day when it won't fix itself."""
    log.event(conn, "inbox.mail_failed", {"mailbox": login.label, "error": type(error).__name__}, level="warning", agent=AGENT)
    since_key, problem_key, alerted_key = (f"mail.{what}.{login.label}" for what in ("failing_since", "problem", "alerted_on"))
    since = store.get_state(conn, since_key)
    if since is None:
        since = timeutil.stamp()
        store.set_state(conn, since_key, since)
    if isinstance(error, replies.RepliesAuthError):
        problem = f"The {login.label} mailbox refused the login, so new mail isn't being read. Check its password."
    elif timeutil.now() - timeutil.parse(since) >= timedelta(hours=OVERDUE_HOURS):
        problem = f"The {login.label} mailbox hasn't been read for over {OVERDUE_HOURS} hours, so new mail isn't being seen."
    else:
        return
    store.set_state(conn, problem_key, problem)
    today = timeutil.today_str()
    if store.get_state(conn, alerted_key) == today:
        return
    store.set_state(conn, alerted_key, today)
    log.event(conn, "inbox.health", {"mailbox": login.label, "problem": problem}, level="warning", agent=AGENT)
    discord.alert(conn, problem, agent=AGENT)


def _reached(conn, login: replies.Account) -> None:
    for what in ("failing_since", "problem", "alerted_on"):
        store.clear_state(conn, f"mail.{what}.{login.label}")


def problems(conn: sqlite3.Connection) -> list[str]:
    """Each mailbox's current problem, for the health strip. Reads only."""
    return [r["value"] for r in db.rows(conn, "SELECT value FROM inbox_state WHERE key LIKE 'mail.problem.%' ORDER BY key")]
