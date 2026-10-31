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
- **done I-nnnn:** clears a conversation's hand replies and lapsed or uncertain lines from R4.
- **unsuppress I-nnnn:** lifts a suppression that came from a reply, and nothing else, and restores the
  lead. An unsubscribe click, a bounce, a complaint or a manual entry stays.

Reword and redraft work only on a card still waiting for him. A decided, lapsed, superseded or claimed
card refuses and says why. While `inbox` is paused nothing here raises a card or asks for one, since a
card that can't be answered helps nobody.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from jura_growth import approvals, caps, cards, cloudflare, db, log, pause, privacy, suppression, timeutil
from jura_growth.agents.inbox import checks, kinds, store, triage
from jura_growth.agents.outreach import store as outreach_store

AGENT = "inbox"
PARAGRAPH_BREAKS = ("//", "\\n\\n")  # Dispatch splits on whitespace, so a line break must be typed as a word (N9, S1)
_REPLY_SENT = (store.SENDING, store.SENT, store.UNKNOWN)
_NEVER_DRAFTED = {store.BASELINE: "A baseline message is never drafted for.", store.OWN: "That is the Page's own message, so it gets no draft.",
                  store.OBSERVED: "The watch's checks haven't read that yet. Try again after the run."}
_CLEARED_BY_DONE = (store.NEEDS_HAND_REPLY, store.LAPSED, store.FAILED, store.UNKNOWN, store.UNVERIFIED)


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


def paragraphs(words: tuple[str, ...]) -> str:
    """His words as he meant them: one paragraph, with a break wherever he typed one as a word (N9)."""
    found: list[list[str]] = [[]]
    for word in words:
        if word in PARAGRAPH_BREAKS:
            found.append([])
        else:
            found[-1].append(word)
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
    candidate = {**item, "draft": draft}
    reply = kinds.reply_of(candidate)
    if reply is None:
        return ["It has no single address to answer."]
    return [] if kinds.card_fits(conn, candidate, reply) else ["It won't fit on one card with what they said. Shorten it."]


def reword(conn: sqlite3.Connection, approval_id: str, words: tuple[str, ...]) -> Answer:
    paused = _paused(conn)
    if paused:
        return paused
    found = _open_card(conn, approval_id)
    if isinstance(found, Answer):
        return found
    record, item = found
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
        new = kinds.raise_request(conn, kinds.subject_of(item["id"]), reason=record.reason)
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
    if state in _REPLY_SENT or item["sent_at"]:
        return "A reply already went, or may have. Answer by hand if there is more to say."
    if state == store.FAILED:  # a new draft would go under the one idempotency key this item has used
        return "Resend refused the last reply on this one. Answer by hand."
    if state == store.WAITING:
        record = approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"]))
        number = record.id if record else "its card"
        return f"It already has a card, {number}. `/growth inbox redraft {number} <guidance>` changes it."
    if state == store.TRIAGED:
        return "A draft is ready and its card follows."
    if item["source"] not in store.PEOPLE_SOURCES or not item["text"]:
        return "There are no words kept to draft from. Answer by hand if it needs one."
    reason = kinds.suppressed_because(conn, item)
    if reason:
        return f"The address is suppressed ({reason}), so no reply can go. `/growth inbox unsuppress {store.label(item['id'])}` lifts one that came from a reply."
    if item["source"] in store.MAIL_SOURCES and kinds.reply_of({**item, "draft": "x"}) is None:
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
    clearable = [other["id"] for other in conversation if other["state"] in _CLEARED_BY_DONE]
    if not clearable:
        carded = next((other for other in conversation if other["state"] == store.WAITING), None)
        record = approvals.latest(conn, kinds.KIND, kinds.subject_of(carded["id"])) if carded else None
        if record:
            return _refused(f"it has a card waiting. `/growth skip {record.id}` if you've answered by hand.")
        return Answer(0, f"{label} has nothing open.")
    with db.transaction(conn):
        store.mark_done(conn, clearable)
        log.event(conn, "inbox.done", {"items": clearable}, agent=AGENT)
    return Answer(0, f"{label} is cleared.")


# --- unsuppress ----------------------------------------------------------------------------------------


def _also_on_the_website(addresses: list[str]) -> str | None:
    """The website's D1 may hold a click, bounce or complaint for this address, past the sync's cursor, so
    lifting the local row alone would mail someone who said stop there. It fails closed."""
    if not cloudflare.configured():
        return None
    hashes = [suppression.email_hash(address) for address in addresses]
    try:
        rows = cloudflare.query(f"SELECT reason FROM suppression WHERE email_hash IN ({', '.join('?' for _ in hashes)})", hashes)
    except Exception as error:  # noqa: BLE001 - any failure means this can't be checked
        return f"the website's list can't be read just now ({type(error).__name__}), so it stays. Try again later."
    return f"the website's list holds them as well ({rows[0].get('reason')}), so it stays." if rows else None


def _restore_lead(conn: sqlite3.Connection, item: dict, addresses: list[str]) -> list[int]:
    """Their lead goes back to having replied. A bounce or a complaint on it is stronger, and stays."""
    hashes = [suppression.email_hash(address) for address in addresses]
    found = {row["lead_id"] for row in db.rows(conn, f"SELECT lead_id FROM contacts WHERE email_hash IN ({', '.join('?' for _ in hashes)})", tuple(hashes))}
    lead_ids = sorted(found | ({item["lead_id"]} if item["lead_id"] else set()))
    restored = []
    for lead_id in lead_ids:
        conn.execute("UPDATE outreach_replies SET unsubscribe = 0 WHERE lead_id = ?", (lead_id,))
        if db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,)) == "unsubscribed":
            outreach_store.set_lead_status(conn, [lead_id], "replied")
            restored.append(lead_id)
    return restored


def unsuppress(conn: sqlite3.Connection, label: str) -> Answer:
    item = store.get(conn, store.number_of(label))
    if item is None:
        return _refused(f"there is no inbox item {label}.")
    addresses = kinds.addresses_of(item)
    if not addresses:
        return _refused(f"{label} has no address to lift.")
    held = [(address, suppression.is_suppressed(conn, address)) for address in addresses]
    held = [(address, reason) for address, reason in held if reason]
    if not held:
        return _refused(f"{label}'s address isn't suppressed.")
    if any(suppression.source_of(conn, address) != suppression.FROM_A_REPLY for address, _ in held):
        return _refused(f"that suppression didn't come from a reply ({held[0][1]}), so it stays.")
    found = [address for address, _ in held]
    problem = _also_on_the_website(found)
    if problem:
        return _refused(problem)
    with db.transaction(conn):
        for address in found:
            suppression.lift_reply(conn, address)
        restored = _restore_lead(conn, item, found)
        store.set_item_state(conn, item["id"], item["state"], note="You lifted the suppression.")
        log.event(conn, "inbox.unsuppressed", {"item": item["id"], "leads": restored}, agent=AGENT)
    privacy.load_for_masking(conn)
    lead = " Their lead is back to having replied. Queued follow-ups stay cancelled." if restored else ""
    return Answer(0, f"{label}'s suppression is lifted.{lead} `/growth inbox draft {label}` asks for a draft.")
