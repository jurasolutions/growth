"""The mail intake (W1, W5 to W8, R2, F2 to F4, F12, S11, S16; technical review B5).

Each mailbox is read through `outreach/replies.py`'s read-only pieces: EXAMINE and BODY.PEEK, so
nothing is marked read, moved or deleted. A message is fetched first and committed on its own, so
no transaction is ever open across the network and a decision in Discord never waits on IMAP.

What happens to a message, in order:

1. Jura's own mail is dropped, with no inbox item and no count (F4), except the website form's.
2. Anything in the Junk folder only lists under noise (S16).
3. A signed website enquiry is the person in its `Reply-To` (W8). One that isn't signed is an
   ordinary stranger.
4. A lead's reply does what the 16:45 check would (W6), and counts there as already done. If that
   check counted it first the person is still recorded and reported, because its post doesn't say
   what they wrote, unless it was too long ago to matter.
5. Mail with evidence in its headers is noise (F3). Nothing else may be: a person writing from their
   own address is always reported, whatever they wrote.

A fault here never raises: a raising precheck is a failed run, and failures add up to an auto-pause
even across weeks of good checks, because a good check leaves no run row. So a mailbox that fails is
logged, and a refused login or two hours without a good check alerts once a day. The last-good-check
stamp moves only for a check that finished.
"""

from __future__ import annotations

import imaplib
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.message import Message
from email.utils import getaddresses, parseaddr

from jura_growth import config, db, discord, log, suppression, timeutil
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
_MAILBOX_SETTINGS = (("levi", replies.SETTINGS), ("enquiry", SECOND_MAILBOX))

_MESSAGE_ID = re.compile(r"<[!-;=?-~]{1,250}>")
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


class _Later(Exception):
    """This message can't be read properly now. It waits for the next check."""


class _Check:
    """What reading one mailbox needs: the connection, who Jura has emailed, what is left of the
    check's budget (B5 rule 3: wall clock and body fetches, across its mailboxes), and the tally."""

    def __init__(self, conn: sqlite3.Connection, known: replies.Contacts, result: Intake) -> None:
        self.conn = conn
        self.known = known
        self.result = result
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
    return replies.account_from("enquiry", "ENQUIRY_IMAP")


def mailboxes() -> list[replies.Account]:
    """The Reply-To mailbox, and `info@` as a second one if it isn't delivered there (W8)."""
    return [login for login in (replies.account(), _second_account()) if login is not None]


def setup_gaps() -> list[str]:
    """The settings that are missing. The first mailbox is what makes the watch work at all; the
    second is optional, so it is a gap only when it is half set."""
    missing = [name for name in replies.SETTINGS if not config.is_set(name)]
    if any(config.is_set(name) for name in SECOND_MAILBOX):
        missing += [name for name in SECOND_MAILBOX if not config.is_set(name)]
    return missing


def _unreadable_settings() -> list[str]:
    """Mailboxes whose settings are all set and still can't be read, such as a `keychain:` value
    the Keychain doesn't have. `is_set` never asks the Keychain, so nothing else would notice."""
    return [label for label, names in _MAILBOX_SETTINGS
            if all(config.is_set(name) for name in names) and not all(config.secret(name) for name in names)]


# --- the check ---------------------------------------------------------------------


def intake(conn: sqlite3.Connection) -> Intake:
    """Read every mailbox and record what is new. A fault in one mailbox, whatever it is, is logged
    and leaves the other to run."""
    result = Intake()
    check = _Check(conn, replies.sent_contacts(conn), result)
    for label in _unreadable_settings():
        result.failed += 1
        problem(conn, label, f"The {label} mailbox's settings can't be read, so new mail isn't being read. Check the Keychain.",
                 "unreadable settings", at_once=True)
    for login in mailboxes():
        started = timeutil.stamp()
        try:
            finished = _read_mailbox(check, login)
        except replies.RepliesAuthError as error:
            result.failed += 1
            problem(conn, login.label, f"The {login.label} mailbox refused the login, so new mail isn't being read. Check its password.",
                     type(error).__name__, at_once=True)
            continue
        except Exception as error:  # noqa: BLE001 - a network fault, a locked database or a bug
            result.failed += 1
            failed(conn, login.label, error)
            continue
        cleared(conn, login.label)
        if finished:
            store.set_state(conn, _last_success(login), started)
    log.event(conn, "inbox.checked", {"recorded": result.recorded, "noise": result.noise, "dropped": result.dropped,
                                      "replies": result.replies, "failed": result.failed}, agent=AGENT)
    return result


def _last_success(login: replies.Account) -> str:
    return f"{store.LAST_SUCCESS}{login.label}"


def _since(conn: sqlite3.Connection, login: replies.Account) -> date:
    """W7: the first run's window, then the last good check less a day, and a long absence bounded."""
    today = timeutil.today()
    last = store.get_state(conn, _last_success(login))
    if last is None:
        return today - timedelta(days=settings.limit("first_run_days"))
    floor = today - timedelta(days=settings.limit("look_back_days"))
    return max(timeutil.parse(last).date() - timedelta(days=1), floor)


def _read_mailbox(check: _Check, login: replies.Account) -> bool:
    """True when every message from the look-back was handled."""
    since = _since(check.conn, login)
    with replies.mailbox(login) as imap:
        replies.open_folder(imap)
        finished = _read_folder(check, imap, since, junk=False)
        folder = _junk_folder(imap)
        if folder is None:
            return finished
        try:
            replies.open_folder(imap, folder)
        except replies.RepliesError:
            log.event(check.conn, "inbox.no_junk_folder", {"mailbox": login.label}, agent=AGENT)
            return finished
        return _read_folder(check, imap, since, junk=True) and finished


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


def _read_folder(check: _Check, imap, since: date, *, junk: bool) -> bool:
    numbers = replies.numbers_since(imap, since)
    finished = True
    for start in range(0, len(numbers), HEADER_BATCH):
        for found in replies.headers_of(imap, numbers[start : start + HEADER_BATCH]):
            try:
                check.check_time()
                _read_one(check, imap, found, junk=junk)
            except _Spent:
                return False
            except _Later:
                finished = False
    return finished


def _read_one(check: _Check, imap, found: replies.Headers, *, junk: bool) -> None:
    key = _safe_key(found.message)
    if store.known(check.conn, key):
        return
    try:
        _record_message(check, imap, found, key, junk=junk)
    except (_Spent, _Later, replies.RepliesError, imaplib.IMAP4.error, OSError, sqlite3.Error):
        raise
    except Exception as error:  # noqa: BLE001 - one malformed message never stops the rest (A12)
        _record_unreadable(check, found.message, key, type(error).__name__)


def _safe_key(headers: Message) -> str:
    try:
        sender = _one_address(str(headers.get("From", ""))) or ""
        return replies.message_key(headers, sender, replies.received_at(headers))
    except Exception:  # noqa: BLE001 - a header so broken it can't even be read
        return store.text_key("unreadable", repr(headers.items())[:4000])


def _too_old(received: datetime | None) -> bool:
    return received is not None and timeutil.now() - received > timedelta(hours=settings.limit("old_after_hours"))


def _record_message(check: _Check, imap, found: replies.Headers, key: str, *, junk: bool) -> None:
    conn, result = check.conn, check.result
    headers = found.message
    raw_from = str(headers.get("From", ""))
    sender = _one_address(raw_from) or ""
    message_ids = _ids(headers.get("Message-ID"))
    if message_ids and store.is_outgoing(conn, message_ids[0]):
        result.dropped += 1
        return

    subject = _line(headers.get("Subject", ""))
    from_form = sender == settings.ENQUIRY_SENDER
    if _is_jura(sender) and not from_form:
        result.dropped += 1
        return
    if junk:
        _record_noise(check, key, sender, subject, "it was in the junk folder")
        return

    signed = from_form and _signed_by_jura(headers)
    received = replies.received_at(headers)
    contact = None if from_form else _contact_of(check, sender, headers, received, subject)
    if contact is None and not from_form:
        evidence = _noise_evidence(headers, sender)
        if evidence:
            _record_noise(check, key, sender, subject, evidence)
            return

    check.spend_body()
    stale = _too_old(received)
    body = replies.body_of(imap, found.number, PARTIAL_BODY, expected=headers)
    if body is None:
        # Refused, or the numbers shifted. Recording it now would lose its words and any opt-out
        # for good, so the next check tries again, until waiting would hide the person.
        if received is not None and not stale:
            raise _Later
        _record_unreadable(check, headers, key, "body not available")
        return
    own = replies.plain_text(body) if signed else replies.own_text(body)
    attachments = _attachment_names(body)

    reply_to = _recipient(headers, sender)
    ours = replies.sent_subjects(conn, contact["lead_id"]) if contact else set()
    wants_out = replies.opt_out_reason(subject, own, ours) if contact else None
    counted_already = contact is not None and replies.counted(conn, key)
    who = reply_to if from_form else (sender or reply_to or "")
    # The form's own display name is Jura's, so the person's name comes from what the form wrote.
    typed = _ENQUIRY_NAME.search(own) if signed else None
    name = typed.group(1) if typed else ("" if from_form else _line(parseaddr(raw_from)[0]))

    state, notes = store.NEW, []
    if from_form and not signed:
        notes.append("It says it came from the website form, but it isn't signed by Jura.")
    if wants_out:
        state = store.REPORTED
        notes.append(f"They asked to be removed ({wants_out}): the address is suppressed and no reply will be drafted.")
    if stale:
        state = store.REPORTED
        notes.append(f"It's older than {settings.limit('old_after_hours')} hours: answer by hand if it still matters.")
    if reply_to is None:
        state = store.NEEDS_HAND_REPLY
        notes.append("It has no single address to answer: reply by hand if it matters.")

    reaction = store.Reaction(
        source="enquiry" if signed else "email",
        key=key,
        conversation=store.text_key("mail", who or key, replies.bare_subject(subject)),
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

    with db.transaction(conn):
        outcome = store.record(conn, reaction)
        if isinstance(outcome, store.Recorded):
            if contact is not None and received is not None and not counted_already:
                result.replies += int(replies.apply_reply(conn, contact, sender, received, key, bool(wants_out), post=False))
            log.event(conn, "inbox.recorded", {"item": outcome.item_id, "source": reaction.source,
                                               "domain": reaction.sender_domain, "state": state}, agent=AGENT)
    result.recorded += 1


def _record_noise(check: _Check, key: str, sender: str, subject: str, evidence: str) -> None:
    """R2: nothing is posted, and the domain and subject stay for the one-pager's list."""
    domain = suppression.domain_of(sender) if sender else ""
    with db.transaction(check.conn):
        store.record(check.conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=domain, subject=subject,
                                                state=store.NOISE, note=evidence))
    check.result.noise += 1


def _record_unreadable(check: _Check, headers: Message, key: str, why: str) -> None:
    """A12, P-8: the person isn't lost to a parser bug or a refused fetch. It is reported as
    needing a hand reply."""
    try:
        sender = _one_address(str(headers.get("From", ""))) or ""
    except Exception:  # noqa: BLE001
        sender = ""
    domain = suppression.domain_of(sender) if sender else ""
    with db.transaction(check.conn):
        store.record(check.conn, store.Reaction(source="email", key=key, conversation=key, sender_domain=domain,
                                                state=store.NEEDS_HAND_REPLY, note="This message couldn't be read: see the mailbox."))
        log.event(check.conn, "inbox.unreadable", {"domain": domain, "why": why}, level="warning", agent=AGENT)
    check.result.recorded += 1


# --- what a message says -----------------------------------------------------------


def _line(value) -> str:
    return store.clean_line(replies.header_text(value))


def _one_address(raw: str) -> str | None:
    """The single address `raw` holds, or None when it holds anything else (A8)."""
    found = [address for _, address in getaddresses([raw]) if address]
    if len(found) != 1:
        return None
    address = found[0].strip().lower()
    return address if scout_contact.ADDRESS_RE.fullmatch(address) else None


def _is_jura_domain(domain: str) -> bool:
    own = {settings.JURA_DOMAIN, str(scout_settings.get().get("sending_domain") or "").strip().lower()} - {""}
    return any(replies.under_domain(domain, parent) for parent in own)


def _is_jura(address: str) -> bool:
    return bool(address) and _is_jura_domain(suppression.domain_of(address))


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
    """F3: the receiving server's verdict that DKIM passed for Jura's own domain."""
    return any(_is_jura_domain(domain) for domain in replies.dkim_pass_domains(headers))


def _contact_of(check: _Check, sender: str, headers: Message, received: datetime | None, subject: str) -> dict | None:
    """The lead this message answers (W6, F2), or None. Until ticket 03 outreach mail keeps no
    Message-ID (see `store.remember_outgoing`), so for it the domain match is what finds a colleague."""
    if received is None or replies.is_automatic(headers, subject):
        return None
    contact = check.known.match(sender, headers) if sender else None
    if contact is None:
        lead_id = store.lead_of_outgoing(check.conn, [*_ids(headers.get("In-Reply-To")), *_ids(headers.get("References"))])
        contact = check.known.by_lead.get(lead_id) if lead_id is not None else None
    if contact is None or received < timeutil.parse(contact["first_sent"]):
        return None
    return contact


def _noise_evidence(headers: Message, sender: str) -> str | None:
    """F3: what in the headers says this isn't a person writing, or None."""
    evidence = replies.bulk_evidence(headers, sender)
    if evidence or not sender:
        return evidence
    domain = suppression.domain_of(sender)
    if any(replies.under_domain(domain, parent) for parent in settings.platform_domains()):
        return "it came from a platform's notice address"
    return None


def _attachment_names(message: Message) -> tuple[str, ...]:
    """What is attached, by name only. Attachments are never opened or kept (PRD §3)."""
    names = []
    for part in message.walk():
        if part.get_content_type() == "message/rfc822":
            continue
        name = part.get_filename()
        if name:
            names.append(_line(name)[:80])
    return tuple(names[:ATTACHMENTS_KEPT])


# --- when a check can't do its job -------------------------------------------------


def failed(conn: sqlite3.Connection, label: str, error: Exception) -> None:
    """B5 rule 1, P-5: logged every time, and alerted once a day after two hours of it, so a real
    bug is seen and a flap is not a failed run."""
    what = type(error).__name__
    since_key = f"{store.FAILING_SINCE}{label}"
    since = store.get_state(conn, since_key)
    if since is None:
        since = timeutil.stamp()
        store.set_state(conn, since_key, since)
    log.event(conn, "inbox.mail_failed", {"mailbox": label, "error": what}, level="warning", agent=AGENT)
    if timeutil.now() - timeutil.parse(since) >= timedelta(hours=OVERDUE_HOURS):
        problem(conn, label, f"The {label} mail check hasn't worked for over {OVERDUE_HOURS} hours, so new mail isn't being "
                              f"seen. The last error was {what}.", what)


def problem(conn: sqlite3.Connection, label: str, line: str, what: str, *, at_once: bool = False) -> None:
    """Keep the line for the health strip, and alert at most once a day. `line` is fixed text
    with a type name in it, never a host, an address or a word from a message."""
    if at_once:
        log.event(conn, "inbox.mail_failed", {"mailbox": label, "error": what}, level="warning", agent=AGENT)
    store.set_state(conn, f"{store.PROBLEM}{label}", line)
    today = timeutil.today_str()
    alerted_key = f"{store.ALERTED_ON}{label}"
    if store.get_state(conn, alerted_key) == today:
        return
    store.set_state(conn, alerted_key, today)
    log.event(conn, "inbox.health", {"mailbox": label, "problem": line}, level="warning", agent=AGENT)
    discord.alert(conn, line, agent=AGENT)


def cleared(conn: sqlite3.Connection, label: str) -> None:
    for prefix in (store.FAILING_SINCE, store.PROBLEM, store.ALERTED_ON):
        store.clear_state(conn, f"{prefix}{label}")
