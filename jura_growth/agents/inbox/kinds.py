"""The `email-reply` approval kind (PRD D1, D2, D5, D7, E2; ADR 0003). Agent `inbox`, subject
`inbox_item:<id>`: the newest message in a conversation, which holds the draft.

- **Content** is every byte the code hands Resend or chooses for it: the recipient, the subject, the
  draft, the thread headers, the BCC and the frame (`frame_fingerprint`: the sender, Reply-To and
  signature). So a change to any of them after approval supersedes the request. The `Message-ID` isn't
  in it: it is derived from the subject and the claim, and says nothing to the person.
- **Gone** (`content` is None) means a reply mustn't go: they wrote again with words in it (a sticker
  isn't an answer to anything, so it leaves the draft standing), the address is suppressed, or the
  stored recipient doesn't hold up. Suppression is by address, so that holds across conversations.
- **Held** (`held_by_newer`) is for a newer message from the same address under another subject, which
  triage hasn't read yet. It might be an opt-out or a change of mind, so no claim is made until triage
  has settled it. An opt-out or a "not now" then closes the draft (`close_drafts_to`). Anything else
  lets it go at the next slot (code review 03, P-1).
- **The subject** is on the card whole, because the card shows exactly what goes out. A subject the card
  couldn't show byte for byte, or that the draft's link rule would refuse, is sent as a safe one instead
  (code review 03, SEC-1, SEC-2).
- **Deadlines:** decide by 3 days after asking, use by 2 days after approval. Either passing lapses the
  item, which then reads "answer by hand".

Raised by `raise_due`, from `inbox submit` and `inbox send-due`, never in the precheck (technical
review N10). A draft waits as `triaged` while the kind's switch is off, or the agent is paused, because
a card that can't be answered helps nobody.

Approval state lives only in `approvals`: `inbox_items.state` holds the item's own life.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from jura_growth import approval_settings, approvals, caps, config, db, discord, log, pause, privacy, suppression, timeutil
from jura_growth.agents.inbox import checks, mail, report, settings, store
from jura_growth.agents.outreach import replies
from jura_growth.agents.outreach import send as outreach_send
from jura_growth.agents.scout import settings as scout_settings

KIND = "email-reply"
AGENT = "inbox"
FRAME_VERSION = "inbox-reply-1"
SIGNATURE = (
    f"{scout_settings.SIGNATURE_NAME}\n{scout_settings.SIGNATURE_TITLE}\nJura Solutions\n"
    f"{scout_settings.SIGNATURE_EMAIL}\n{scout_settings.SITE}"
)
ENQUIRY_SUBJECT = "Your enquiry to Jura Solutions"  # S3: the form's own subject is one she never saw
NO_SUBJECT = "Your message to Jura Solutions"
REFERENCES_SENT = 20
# What `cards.build` puts around a preview, past its title and reason: the header and the answer line,
# as an edited card's header is longest. A card never splits, so this is counted before the quote is.
CARD_FRAME = 150
_SUBJECT = store.SUBJECT_PREFIX
_WROTE_AGAIN = "they wrote again"
_TOO_LONG = "The draft and its card won't fit one Discord message, so there is no card. Answer by hand if it needs one."
_NO_ADDRESS = "It has no single address to answer: reply by hand if it matters."
_LAPSED = "Lapsed: answer by hand if it still matters."


def subject_of(item_id: int) -> str:
    return store.approval_subject(item_id)


def item_id_of(subject: str) -> int | None:
    number = (subject or "").removeprefix(_SUBJECT)
    return int(number) if (subject or "").startswith(_SUBJECT) and number.isdigit() else None


def _item(conn: sqlite3.Connection, subject: str) -> dict | None:
    item_id = item_id_of(subject)
    return store.get(conn, item_id) if item_id is not None else None


def opted_out_earlier(reason: str) -> str:
    return f"They opted out earlier ({reason}) and wrote again. The engine won't send. Answer by hand if it's right."


def language_line(language: str | None) -> str:
    if not language or language == "English":
        return ""
    if language == "Other":
        return "They wrote in another language. This draft is English."
    return f"They wrote in {language}. This draft is English."


def addresses_of(item: dict) -> list[str]:
    """Each address this person is known by here: the one they wrote from, and the one to answer."""
    found = (item["sender_address"], store.thread_of(item).get("reply_to"))
    return [address for address in dict.fromkeys(found) if address]


def suppressed_because(conn: sqlite3.Connection, item: dict) -> str | None:
    """Why this person gets no email, whichever of their addresses it is: From, or the one to answer."""
    for address in addresses_of(item):
        reason = suppression.is_suppressed(conn, address)
        if reason:
            return reason
    return None


def wrote_again(conn: sqlite3.Connection, item: dict) -> bool:
    """A newer message in the conversation with words in it (D5). One with none doesn't count: the
    sticker must not cancel the answer (code review 02, P-2)."""
    return any(other["id"] > item["id"] and other["text"] and other["state"] != store.NOISE
               for other in store.in_conversation(conn, item["conversation"]))


def held_by_newer(conn: sqlite3.Connection, item: dict) -> bool:
    """A newer message with words in it from the same address, in another conversation, that triage
    hasn't settled. People don't keep to a thread, and this may be the one that says not to answer (P-1).
    One in the same conversation doesn't hold: `wrote_again` has already made the draft gone."""
    theirs = set(addresses_of(item))
    return any(other["id"] > item["id"] and other["conversation"] != item["conversation"] and other["text"]
               and theirs & set(addresses_of(other))
               for other in store.waiting_for_triage(conn))


def close_drafts_to(conn: sqlite3.Connection, newest: dict) -> None:
    """They opted out or said not now, under whatever subject: no other draft to that address goes (E2).
    Call it inside the caller's transaction. Its approval supersedes at the next read."""
    theirs = set(addresses_of(newest))
    for state in (store.TRIAGED, store.WAITING):
        for item in store.with_state(conn, state):
            if item["id"] < newest["id"] and item["source"] in store.MAIL_SOURCES and theirs & set(addresses_of(item)):
                store.set_item_state(conn, item["id"], store.SUPERSEDED, note="They wrote again, so this draft is closed.")


# --- what goes out ------------------------------------------------------------------------------


def frame_fingerprint() -> str:
    """Everything the code puts around a draft (ADR 0003). Computed fresh from what would send now."""
    parts = {"version": FRAME_VERSION, "from": outreach_send.from_address(), "reply_to": scout_settings.REPLY_TO,
             "signature": SIGNATURE}
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reply:
    """One email reply, exactly as it would go out now."""

    item_id: int
    to: str
    subject: str
    draft: str
    in_reply_to: str | None
    references: tuple[str, ...]
    bcc: str

    @property
    def text(self) -> str:
        return f"{self.draft}\n\n{SIGNATURE}\n"

    def content_bytes(self) -> bytes:
        """No Unicode normalisation: two drafts with different bytes never hash alike (ADR 0003)."""
        value = {"to": self.to, "subject": self.subject, "body": self.draft, "in_reply_to": self.in_reply_to,
                 "references": list(self.references), "bcc": self.bcc, "frame": frame_fingerprint()}
        return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def content_hash(self) -> str:
        return approvals.content_hash(self.content_bytes())


def _reply_subject(item: dict) -> str:
    if item["source"] == "enquiry":
        return ENQUIRY_SUBJECT
    bare = store.clean_line(replies.SUBJECT_PREFIX_RE.sub("", item["subject"] or ""))
    if not bare or len(bare) > caps.INBOX_REPLY_SUBJECT_CHARS or checks.holds_a_link(bare) or not report.shows_as_written(bare):
        return NO_SUBJECT
    return f"Re: {bare}"


def reply_of(item: dict) -> Reply | None:
    """The reply this inbox item would send, read again from the row: None when its recipient doesn't
    hold up, whatever put it there (A8). An enquiry starts its own thread, because the form's message
    is one she never saw (S3)."""
    thread = store.thread_of(item)
    to = mail.valid_recipient(thread.get("reply_to"))
    if to is None or not item["draft"]:
        return None
    theirs = next(iter(replies.message_ids(thread.get("message_id"))), None)
    if item["source"] == "enquiry" or theirs is None:
        in_reply_to, references = None, ()
    else:
        earlier = [found for value in thread.get("references") or () for found in replies.message_ids(value)]
        in_reply_to, references = theirs, tuple(dict.fromkeys([*earlier, theirs]))[-REFERENCES_SENT:]
    return Reply(item["id"], to, _reply_subject(item), item["draft"], in_reply_to, references, scout_settings.REPLY_TO)


# --- the card ------------------------------------------------------------------------------------


def _title(item: dict) -> str:
    """Names no person: it is the line an agent feed repeats through plain masking."""
    if item["source"] == "enquiry":
        return "Email reply · enquiry"
    return "Email reply · answer to our email" if item["lead_id"] else "Email reply"


def _unanswered(conn: sqlite3.Connection, item: dict) -> list[dict]:
    """What this reply answers: their messages up to it, since the last reply that went out."""
    found: list[dict] = []
    for other in store.in_conversation(conn, item["conversation"]):
        if other["sent_at"]:
            found = []
        elif other["id"] <= item["id"] and other["state"] != store.NOISE:
            found.append(other)
    return found or [item]


def _recipient_lines(item: dict, reply: Reply) -> list[str]:
    """A9, SEC-6: a forged sender can bring its own `Reply-To`, so the card names who really gets it, and
    says when the mail's own claim to be from there doesn't hold up (code review 03, SEC-3)."""
    thread = store.thread_of(item)
    goes_to = suppression.domain_of(reply.to)
    claimed = thread.get("from_domain")
    lines = [f"Goes to {privacy.masked_address(reply.to)}."]
    if item["source"] == "enquiry":
        return lines
    if not claimed:
        lines.append(f"Its From couldn't be read as one address, so nothing shows who wrote it. The reply goes to {goes_to}: check that is right before you approve.")
    elif claimed != goes_to:
        lines.append(f"It says it is from {claimed}, but the reply goes to {goes_to}: check that is right before you approve.")
    if thread.get("forged"):
        lines.append("The receiving server says this may not be from that address, so approving may answer someone who never wrote.")
    return lines


def _has_a_number(items: list[dict]) -> bool:
    return any(privacy.PHONE in privacy.for_discord(i["text"], conversation=[i["text"]]) for i in items if i["text"])


def _card_lines(conn: sqlite3.Connection, item: dict, reply: Reply, record: approvals.Approval | None) -> tuple[list[str], list[str]]:
    """The card's text around what they said: what comes before the quote, and after."""
    number = record.id if record else "A-nnnn"
    before = _recipient_lines(item, reply)
    if item["priority"] == "high":
        by = f": answer it by {timeutil.when(record.decide_by)}" if record else ""
        before.insert(0, f"**High priority**{by}.")
    language = language_line(item["language"])
    if language:
        before.append(language)
    if _has_a_number(_unanswered(conn, item)):
        before.append("They left a number. It's in the mailbox.")
    draft = "\n".join(f"> {line}" if line else ">" for line in reply.draft.split("\n"))
    # No address on these lines: the signature's is Levi's own.
    after = [
        f"Subject: {reply.subject}",
        "Draft, exactly as it goes out, with Levi's signature under it:",
        draft,
        f"Template: {FRAME_VERSION}, frame {frame_fingerprint()[:8]}: sent as {scout_settings.SENDER_NAME}, BCC to his mailbox.",
        "Approve: sends as Levi within 10 minutes, or at 08:00 if it's after 22:00.",
        "Skip: nothing goes out. Use this too if you've answered by hand.",
        f"Change: `/growth inbox redraft {number} <guidance>` or `/growth inbox reword {number} <your words>`.",
    ]
    return before, after


def reason_of(item: dict) -> str:
    return f"{store.label(item['id'])}, {item['class'] or 'a message'}"


def _room_for_quote(item: dict, before: list[str], after: list[str]) -> int:
    """What a quote may take: a card is always one message, and the draft is never what gives way (B8).
    Measured masked, because masking can lengthen text."""
    return discord.MAX_CONTENT - CARD_FRAME - report.masked_length("\n".join([_title(item), f"Why: {reason_of(item)}", *before, *after]))


def card_fits(conn: sqlite3.Connection, item: dict, reply: Reply) -> bool:
    before, after = _card_lines(conn, item, reply, None)
    return _room_for_quote(item, before, after) >= report.masked_length(report.quoted(report.CUT_NOTE))


# --- the kind ------------------------------------------------------------------------------------


class EmailReply:
    """The kind `approvals` asks about every `inbox_item:<id>`."""

    name = KIND
    used_word = "sent"
    conversation_card = True  # its card carries a person's words and the answer to them
    # Inert until approvals-first lands (technical review, "Merging"): `feed.py` reads them with getattr.
    feed_channel = "mission-control"
    feed_approved = "It goes out as Levi within 10 minutes, or at 08:00 if it's after 22:00."

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        item = _item(conn, subject)
        if item is None or item["state"] not in (store.WAITING, store.SENDING):
            return None
        reply = reply_of(item)
        if reply is None or wrote_again(conn, item) or suppressed_because(conn, item):
            return None
        return reply.content_bytes()

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """D1: what they said, who and where, the draft exactly as it goes out, and each answer's next step."""
        item = _item(conn, subject)
        reply = reply_of(item) if item else None
        if item is None or reply is None:
            raise LookupError(f"no reply for {subject}")
        before, after = _card_lines(conn, item, reply, approvals.latest(conn, KIND, subject))
        quote = report.card_quote(_unanswered(conn, item), _room_for_quote(item, before, after))
        return approvals.Preview(title=_title(item), reason=reason_of(item), text="\n".join([*before, quote, *after]))

    def deadlines(self, conn: sqlite3.Connection | None, subject: str, now: datetime) -> approvals.Deadlines:
        return approvals.Deadlines(decide_by=now + timedelta(days=settings.limit("decide_by_days")),
                                   use_by=now + timedelta(days=settings.limit("use_by_days")))

    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        return switched_off()

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        self._closed(conn, subject, "on_skip", store.SKIPPED, "Skipped: nothing goes out.")

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        self._closed(conn, subject, "on_expire", store.LAPSED, _LAPSED)

    def on_lapse(self, conn: sqlite3.Connection, subject: str) -> None:
        self._closed(conn, subject, "on_lapse", store.LAPSED, _LAPSED)

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str | None:
        item = _item(conn, subject)
        if item is None:
            return None
        if suppressed_because(conn, item):
            return "address suppressed"
        return _WROTE_AGAIN if wrote_again(conn, item) or item["state"] == store.SUPERSEDED else None

    def _closed(self, conn: sqlite3.Connection, subject: str, hook: str, state: str, note: str) -> None:
        item = _item(conn, subject)
        if item is None:
            return
        store.set_item_state(conn, item["id"], state, note=note)
        log.event(conn, "inbox.approval_closed", {"item": item["id"], "hook": hook}, agent=AGENT)


def kinds() -> dict[str, EmailReply]:
    return {KIND: EmailReply()}


def switched_off() -> str | None:
    """Why no reply can go now. Not outreach's shadow mode or its legal review, which are about mailing
    addresses Jura found: this answers someone who wrote in, through the same sender and key."""
    if not approval_settings.switch("discord_buttons"):
        return "the approval buttons aren't set up, so a reply can't be approved"
    domain = outreach_send.sending_domain()
    if not domain or not replies.under_domain(domain, settings.JURA_DOMAIN):
        return "sending_domain in config/scout.yaml isn't Jura's, so a reply has no sender"
    if not config.secret("RESEND_API_KEY_OUTREACH"):
        return "RESEND_API_KEY_OUTREACH is not set in .env"
    return outreach_send.resend_stub_problem()


# --- raising and settling -----------------------------------------------------------------------


def raise_request(conn: sqlite3.Connection, subject: str, *, reason: str) -> approvals.Approval | None:
    return approvals.request(conn, KIND, subject, reason=reason, run_id=log.current_run_id())


def raise_due(conn: sqlite3.Connection) -> list[approvals.Approval]:
    """A request for each email draft that has none yet. Returns those raised. A draft that can't have
    a card ends needing a hand reply, and one with a newer message waits for triage to replace it."""
    if switched_off() or pause.is_paused(conn, AGENT):
        return []
    raised = []
    for item in store.drafts_without_a_card(conn):
        with db.transaction(conn):
            reply = reply_of(item)
            if reply is None:
                store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note=_NO_ADDRESS)
                continue
            why_not = suppressed_because(conn, item)
            if why_not:
                store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note=opted_out_earlier(why_not))
                continue
            if wrote_again(conn, item):
                continue
            if not card_fits(conn, item, reply):
                store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note=_TOO_LONG)
                continue
            store.set_item_state(conn, item["id"], store.WAITING)
            found = raise_request(conn, subject_of(item["id"]), reason=reason_of(item))
            if found is not None:
                raised.append(found)
    return raised


def refresh_open(conn: sqlite3.Connection) -> None:
    """The next read (A3): every open request judged by the clock and by what would go out now, so a
    lapse is written and an item that went away is superseded, and its card says so."""
    rows = conn.execute(
        "SELECT subject, reason FROM approvals WHERE kind = ? AND status IN ('pending', 'approved') AND used_at IS NULL ORDER BY id",
        (KIND,),
    ).fetchall()
    for row in rows:
        with db.transaction(conn):
            raise_request(conn, row["subject"], reason=row["reason"])


def settle_waiting(conn: sqlite3.Connection) -> None:
    """An inbox item whose request has closed around it, by any path. If what would go out has changed
    it needs asking again. If it is gone it is superseded, unless a message waits for triage, which
    must see this draft to answer all of it (F8) and closes it then."""
    for item in store.with_state(conn, store.WAITING):
        subject = subject_of(item["id"])
        latest = approvals.latest(conn, KIND, subject)
        if latest is None or latest.status != approvals.SUPERSEDED:
            continue
        with db.transaction(conn):
            if EmailReply().content(conn, subject) is not None:
                raise_request(conn, subject, reason=latest.reason)
            elif not any(other["state"] == store.NEW for other in store.in_conversation(conn, item["conversation"])):
                store.set_item_state(conn, item["id"], store.SUPERSEDED)

