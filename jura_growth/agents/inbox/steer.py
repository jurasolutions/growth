"""What Ting Yu can do about an inbox item from his phone (PRD D6, S1, S2; code review 02, SEC-2).

Each comes from `/growth inbox …` through `remote` and no other way: `headless.NEVER` refuses them to
every run, and `commands.py` refuses them without an origin, so typed in Terminal they do nothing, and a
person's words can't reach them through a model.

- **reword A-nnnn <his words>:** his words become the draft after the brand check, and in one transaction
  the old card closes and a new one is raised. A refusal answers with the reasons and leaves the card
  open. D8's two strikes aren't for his words.
- **redraft A-nnnn <guidance>:** the next triage redrafts it. The old card stays open until the new one
  exists, because triage may fail, and approving it meanwhile sends what it says and drops the redraft.
- **draft I-nnnn [guidance]:** the way back when the model said no reply was needed. It answers the
  conversation's newest message, since a reply to an older one would be gone at once (D5).
- **done I-nnnn:** clears a conversation's hand replies and lapsed or uncertain lines from R4. It doesn't
  erase what they were, so what may have gone out is still never sent again.
- **unsuppress I-nnnn:** lifts a suppression its own message caused, on the address its own sender wrote
  from, and restores the lead. An unsubscribe click, a bounce, a complaint, a manual entry or a whole
  domain stays, and so does anything a stranger's `Reply-To` names.

Reword and redraft work only on a card still waiting for him. A decided, lapsed, superseded or claimed
card refuses and says why. While `inbox` is paused nothing here raises a card or asks for one, since a
card that can't be answered helps nobody.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from jura_growth import approvals, caps, cards, db, log, pause, suppression, timeutil
from jura_growth.agents.inbox import checks, kinds, mail, social, store, triage
from jura_growth.agents.outreach import replies

AGENT = "inbox"
_TYPED_BREAK = "\\n\\n"
PARAGRAPH_BREAKS = ("//", _TYPED_BREAK)  # Dispatch splits on whitespace, so a line break must be typed as a word (N9, S1)
_REPLY_SENT = (store.SENDING, store.SENT, store.UNKNOWN)
_NEVER_DRAFTED = {store.BASELINE: "A baseline message is never drafted for.", store.OWN: "That is the Page's own message, so it gets no draft.",
                  store.OBSERVED: "The watch's checks haven't read that yet. Try again after the run."}


@dataclass(frozen=True)
class Answer:
    """What goes back to Discord. Exit 1 is the contract's "ran and reported a problem"."""

    exit_code: int
    text: str


def _refused(text: str) -> Answer:
    return Answer(1, f"refused: {text}")


def _paused(conn: sqlite3.Connection) -> Answer | None:
    why = pause.is_paused(conn, AGENT)
    if not why:
        return None
    return _refused(f"inbox is paused ({why}), so nothing would come of this. `/growth resume inbox` first.")


def _browser_paused(conn: sqlite3.Connection, item: dict) -> Answer | None:
    """A social card that couldn't be posted helps nobody either."""
    why = pause.is_paused(conn, social.AGENT) if item["source"] in store.SOCIAL_SOURCES else None
    if not why:
        return None
    return _refused(f"inbox-browser is paused ({why}), so nothing would come of this. `/growth resume inbox-browser` first.")


def paragraphs(words: tuple[str, ...]) -> str:
    """His words as he meant them: one paragraph, with a break wherever he typed one as a word (N9)."""
    found: list[list[str]] = [[]]
    for word in words:
        if word in PARAGRAPH_BREAKS:
            found.append([])
            continue
        first, *rest = word.split(_TYPED_BREAK)  # a natural slip on a phone: it can come glued to a word
        if first:
            found[-1].append(first)
        for part in rest:
            found.append([part] if part else [])
    return "\n\n".join(" ".join(part) for part in found if part)


def _guidance(words: tuple[str, ...]) -> str:
    return store.clean_line(" ".join(words))[: caps.INBOX_GUIDANCE_CHARS]


# --- the card he named --------------------------------------------------------------------------------


def _why_closed(conn: sqlite3.Connection, record: approvals.Approval, item: dict) -> str | None:
    """Why this card can't be changed, in words for him, or None. Judged by growth's own clock."""
    label = store.label(item["id"])
    if record.used_at:
        return f"{record.id} was already claimed, so it can't be changed."
    if record.status == approvals.APPROVED:
        return f"{record.id} is already approved, so it goes as it reads. `/growth skip {record.id}` first if you want it changed."
    if record.status == approvals.SKIPPED:
        return f"{record.id} was skipped. `/growth inbox draft {label}` asks for a new draft."
    if record.status == approvals.EXPIRED or (record.status == approvals.PENDING and timeutil.now_sgt() >= timeutil.parse(record.decide_by)):
        return f"{record.id} lapsed. `/growth inbox draft {label}` asks for a new draft."
    if kinds.wrote_again(conn, item):
        return f"They wrote again, so {record.id} is being replaced. Its new card comes after the next check."
    if record.status == approvals.SUPERSEDED:
        newer = approvals.successor(conn, record)
        return f"{record.id} was superseded" + (f" by {newer.id}: change that one." if newer else ".")
    if item["state"] != store.WAITING:
        return f"{record.id} isn't waiting any more ({item['state']})."
    reason = kinds.suppressed_because(conn, item)
    if reason:
        return f"The address is suppressed ({reason}), so no reply can go."
    return None


def _open_card(conn: sqlite3.Connection, approval_id: str) -> tuple[approvals.Approval, dict] | Answer:
    """The card he named and its item, or why not."""
    record = approvals.get(conn, approval_id)
    if record is None:
        return _refused(f"there is no approval request {approval_id}.")
    item_id = kinds.item_id_of(record.subject)
    item = store.get(conn, item_id) if item_id is not None else None
    if item is None:
        return _refused(f"{record.id} isn't an inbox reply.")
    why = _why_closed(conn, record, item)
    return _refused(why) if why else (record, item)


# --- reword and redraft -------------------------------------------------------------------------------


def _problems(conn: sqlite3.Connection, item: dict, draft: str) -> list[str]:
    issues = [str(issue) for issue in triage.draft_problems(conn, item, draft, high=item["priority"] == "high")]
    if issues:
        return issues
    problem = social.card_problem(conn, {**item, "draft": draft})
    return [problem] if problem else []


def reword(conn: sqlite3.Connection, approval_id: str, words: tuple[str, ...]) -> Answer:
    paused = _paused(conn)
    if paused:
        return paused
    found = _open_card(conn, approval_id)
    if isinstance(found, Answer):
        return found
    record, item = found
    browser = _browser_paused(conn, item)
    if browser:
        return browser
    draft = store.clean_text(paragraphs(words)).strip()
    if draft == item["draft"]:
        return _refused(f"that is already the draft on {record.id}.")
    problems = _problems(conn, item, draft)
    if problems:
        log.event(conn, "inbox.reword_refused", {"item": item["id"], "reasons": len(problems)}, agent=AGENT)
        listed = "\n".join(f"- {problem}" for problem in problems)
        return Answer(1, f"refused: the brand check refused those words, so {record.id} stays open as it was:\n{listed}")
    with db.transaction(conn):
        again = _open_card(conn, approval_id)  # under the lock: a decision may have landed since
        if isinstance(again, Answer):
            return again
        store.update_draft(conn, item["id"], draft, promised=item["priority"] == "high" or checks.promises_a_reply(draft))
        new = social.raise_for(conn, item, reason=record.reason)
        log.event(conn, "inbox.reworded", {"item": item["id"], "was": record.id, "now": new.id if new else None}, agent=AGENT)
    cards.sweep_safely(conn)
    if new is None or new.status != approvals.PENDING:
        return _refused(f"{record.id} went away as it was being changed. `/growth inbox list` shows what waits.")
    return Answer(0, f"{record.id} is closed. {new.id} has your words, in #approvals.")


def redraft(conn: sqlite3.Connection, approval_id: str, words: tuple[str, ...]) -> Answer:
    paused = _paused(conn)
    if paused:
        return paused
    with db.transaction(conn):
        found = _open_card(conn, approval_id)
        if isinstance(found, Answer):
            return found
        record, item = found
        store.ask_for_draft(conn, item["id"], _guidance(words))
        log.event(conn, "inbox.redraft_asked", {"item": item["id"], "card": record.id}, agent=AGENT)
    return Answer(0, f"{record.id} goes to triage at the next check, within about 15 minutes. It stays open until the new card is up, "
                     "and approving it before then sends it as it reads.")


# --- draft ---------------------------------------------------------------------------------------------


def _why_no_draft(conn: sqlite3.Connection, item: dict) -> str | None:
    state = item["state"]
    if state in _NEVER_DRAFTED:
        return _NEVER_DRAFTED[state]
    if state == store.UNVERIFIED:
        return "It's unverified, so its words aren't proved to be anyone's. Read the thread and answer by hand."
    if state == store.FAILED and item["source"] in store.SOCIAL_SOURCES:
        return "The last reply on this one didn't post, and it isn't tried again. Answer by hand."
    if state == store.FAILED:  # a new draft would go under the one idempotency key this item has used
        return "Resend refused the last reply on this one. Answer by hand."
    if state in _REPLY_SENT or item["sent_at"] or item["send_attempts"] or approvals.claimed(conn, store.approval_subject(item["id"])):
        return "A reply already went, or may have. Answer by hand if there is more to say."
    if state == store.WAITING:
        record = social.latest_for(conn, item)
        number = record.id if record else "its card"
        return f"It already has a card, {number}. `/growth inbox redraft {number} <guidance>` changes it."
    if state == store.TRIAGED:
        return "A draft is ready and its card follows."
    if item["source"] not in store.PEOPLE_SOURCES or not item["text"]:
        return "There are no words kept to draft from. Answer by hand if it needs one."
    reason = kinds.suppressed_because(conn, item)
    if reason:
        # Offered only on the message that caused it: a stranger can name anyone in a `Reply-To` (SEC-2).
        lift = f" `/growth inbox unsuppress {store.label(item['id'])}` lifts it if that's wrong." if item["suppressed_by_this"] else ""
        return f"The address is suppressed ({reason}), so no reply can go.{lift}"
    if item["source"] in store.MAIL_SOURCES and mail.valid_recipient(store.thread_of(item).get("reply_to")) is None:
        return "It has no single address to answer. Answer by hand."
    if item["source"] in store.SOCIAL_SOURCES and not item["target"]:
        return "The watch kept no safe address for it. Answer by hand."
    return None


def _newest_with_words(conn: sqlite3.Connection, item: dict) -> dict:
    """A reply answers the whole conversation and goes under its newest message (D5, F8)."""
    theirs = [other for other in store.in_conversation(conn, item["conversation"]) if other["text"] and other["state"] not in store.NOT_HISTORY]
    return theirs[-1] if theirs and theirs[-1]["id"] >= item["id"] else item


def draft(conn: sqlite3.Connection, label: str, words: tuple[str, ...]) -> Answer:
    item = store.get(conn, store.number_of(label))
    if item is None:
        return _refused(f"there is no inbox item {label}.")
    paused = _paused(conn)
    if paused:
        return paused
    with db.transaction(conn):
        newest = _newest_with_words(conn, item)
        why = _why_no_draft(conn, newest)
        if why:
            return _refused(why)
        store.reopen_for_draft(conn, newest["id"], _guidance(words), note=triage.note_without_its_verdict(newest["note"]))
        log.event(conn, "inbox.draft_asked", {"item": newest["id"]}, agent=AGENT)
    shown = store.label(newest["id"])
    also = f" It answers their newest message, {shown}." if newest["id"] != item["id"] else ""
    return Answer(0, f"{shown} goes to triage at the next check, within about 15 minutes, and a card follows.{also}")


# --- done ----------------------------------------------------------------------------------------------


def done(conn: sqlite3.Connection, label: str) -> Answer:
    item = store.get(conn, store.number_of(label))
    if item is None:
        return _refused(f"there is no inbox item {label}.")
    conversation = store.in_conversation(conn, item["conversation"])
    clearable = [other for other in conversation if other["state"] in store.LISTED_STATES and not other["closed_at"]]
    carded = next((other for other in conversation if other["state"] == store.WAITING), None)
    record = social.latest_for(conn, carded) if carded else None
    if not clearable:
        if record:
            return _refused(f"it has a card waiting. `/growth skip {record.id}` if you've answered by hand.")
        return Answer(0, f"{label} has nothing open.")
    with db.transaction(conn):
        store.mark_done(conn, clearable)
        log.event(conn, "inbox.done", {"items": [other["id"] for other in clearable]}, agent=AGENT)
    still = f" {record.id} still waits in #approvals." if record else ""
    return Answer(0, f"{label} is cleared.{still}")


# --- unsuppress ----------------------------------------------------------------------------------------


def _why_it_stays(conn: sqlite3.Connection, item: dict, address: str) -> str | None:
    """Why this item can't lift this address, or None. In order: only a suppression a reply caused, with
    nothing stronger on top of it, and only the message that caused it (code review 04, SEC-1, SEC-2, SEC-3)."""
    label = store.label(item["id"])
    domain = suppression.is_domain_suppressed(conn, suppression.domain_of(address))
    if domain:
        return f"a whole domain is suppressed ({domain}), and that can't be lifted here, so it stays."
    source = suppression.source_of(conn, address)
    if source is None:
        return f"{label}'s address isn't suppressed."
    if source != suppression.FROM_A_REPLY:
        return f"that suppression didn't come from a reply, so it stays: {suppression.is_suppressed(conn, address)}, from {source}."
    if not item["suppressed_by_this"]:
        earlier = store.what_suppressed(conn, address) if store.thread_of(item).get("own_sender") else None
        where = f" {store.label(earlier['id'])} is the one that did." if earlier else ""
        return f"{label}'s message isn't what suppressed that address, so it stays.{where}"
    return None


def unsuppress(conn: sqlite3.Connection, label: str) -> Answer:
    """Only the address the item's own sender wrote from, never one a `Reply-To` names, which anyone can write."""
    item = store.get(conn, store.number_of(label))
    if item is None:
        return _refused(f"there is no inbox item {label}.")
    address = item["sender_address"]
    if not address:
        return _refused(f"{label} has no address to lift.")
    why = _why_it_stays(conn, item, address)
    if why:
        return _refused(why)
    problem = suppression.website_holds([address])
    if problem:
        return _refused(problem)
    with db.transaction(conn):
        restored = replies.undo_opt_out(conn, address, item["lead_id"], item["key"])
        store.lifted(conn, address)
        store.set_item_state(conn, item["id"], item["state"], note="You lifted the suppression.")
        log.event(conn, "inbox.unsuppressed", {"item": item["id"], "lead_restored": restored}, agent=AGENT)
    lead = " Their lead is back to having replied. Queued follow-ups stay cancelled." if restored else ""
    return Answer(0, f"{label}'s suppression on {suppression.domain_of(address)} is lifted.{lead} `/growth inbox draft {label}` asks for a draft.")
