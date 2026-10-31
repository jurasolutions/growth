"""What an `inbox-reply` run may do, and what its reports come to (PRD D4, F9, F15, S4; N12, N13).

A reply run types into a real conversation on a signed-in account, just after reading text anyone can
write. So its model decides nothing, and what it says is believed only as far as what Chrome returned to
it bears it out (code review 06). In order:

1. **`reply-due`** hands this run one approved reply's target and whose words to look for, and not the reply.
   A run gets one, and nothing else it does can touch any other reply.
2. **The read (F9).** It opens the target and reports what it found in a file. Nothing has been claimed yet,
   and until the claim the run may only read.
3. **`reply-next`** decides from that report, for that one reply:
   - the session isn't acting as Jura: a stop signal. A page that doesn't show who it is acting as: a hand
     reply, with no stop;
   - the person on the thread isn't the item's author, or the read doesn't make sense: a hand reply (N12);
   - the target has gone, the Page has already answered, or the box is closed: only a report, so far. A page's
     words can't close an item. The run's checks do it, from what Chrome returned at the target's address,
     and without that evidence the item goes to a hand reply, with a line saying why (`settle_reported`);
   - they have written since: that message is recorded and the draft is superseded, so triage drafts
     again over the whole conversation;
   - only a clean read is claimed, in one transaction, and only then is the reply's text handed out.
4. **`reply-done`** takes the read-back. It says what the run saw and proves nothing, so the item stays
   `sending`. Words that don't match mean something else went out: `unknown`, and the agent pauses.
5. **The run's checks** (`inbox_browser/job.py`) make it `sent`, and nothing else does: an audit with no
   failures, the whole text typed and one send, and the words on the claimed thread in a read after that send.

**No claim left open survives (N13).** A claim with no proved outcome when its run ends, or found by a later
job, is `unknown` and pauses `inbox-browser`. It is listed for 7 days and never sent again, so there is nothing
to resolve and no command that resolves it.

What a run sends comes back as a fixed reason. Every path handed out is absolute, because the job starts
in an empty folder of its own (`caps.CLEAN_CWD_JOBS`). The reply itself is one approved text and no file.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jura_growth import approvals, caps, cards, db, log, paths, pause, timeutil
from jura_growth.agents.inbox import kinds as email_kinds
from jura_growth.agents.inbox import settings, social, store, watch
from jura_growth.agents.publish import text as text_mod

AGENT = social.AGENT
JOB = "inbox-reply"
TARGET_WORDS = ("found", "gone", "closed")
GONE, BOX_CLOSED, ANSWERED = "the target has gone", "the reply box is closed", "the Page has answered"
_RUN = "reply.run."  # + run: what this run was handed, and what it reported
_UNCLEAN = "The reply run couldn't get a clean read of this thread, so nothing was typed. Answer by hand if it still matters."
_NOT_THEIRS = "The reply run didn't find this person on that thread, so nothing was typed. Answer by hand if it needs one."
_NO_IDENTITY = "The reply run couldn't see who the session was acting as on that thread, so nothing was typed. Answer by hand if it needs one."
_GONE_NOTE = "The reply run found the comment or thread gone, and its page didn't show their words, so nothing was typed. No reply is needed unless they write again."
_BOX_NOTE = "The reply run reported the reply box on that thread is closed, so nothing was typed. Answer another way if it matters."
_ANSWERED_NOTE = "The reply run found the Page had already answered this by hand, so the draft was dropped and nothing was typed."
_NOT_BORNE_OUT = ("The reply run reported that {what}, but what its pages showed doesn't bear that out, so nothing was typed and "
                  "this isn't closed. Check the thread, and answer by hand if it needs one.")
_NOT_SENT = "The run says it couldn't post this, and nothing was sent. It won't be tried again. Answer by hand if it still matters."
_OPEN_CLAIM = "A reply run claimed this and recorded no outcome, so it may have posted. It won't be sent again."
_DIFFERENT = "What the page shows isn't what was approved, so check it. It won't be sent again."
_NOT_PROVED = "A reply run says this posted, but what its browser did and read doesn't prove it went in the right place. Check it. It won't be sent again."
_TYPED_ANYWAY = "The run says this didn't go, but it typed, so it may have. It won't be sent again."


# --- what is due ----------------------------------------------------------------------------------


def due(conn: sqlite3.Connection) -> list[dict]:
    """Replies Ting Yu approved and nobody has claimed, high priority first, then the oldest."""
    return db.rows(
        conn,
        "SELECT i.* FROM inbox_items i JOIN approvals a ON a.kind = ? AND a.subject = 'inbox_item:' || i.id AND a.status = 'approved' "
        "AND a.used_at IS NULL WHERE i.state = ? ORDER BY COALESCE(i.priority, '') = 'high' DESC, i.id",
        (social.KIND, store.WAITING),
    )


def claimed_by(conn: sqlite3.Connection, run_id: int) -> dict | None:
    """The item this run claimed, whatever became of it."""
    return db.one(
        conn,
        "SELECT i.* FROM inbox_items i JOIN approvals a ON a.kind = ? AND a.subject = 'inbox_item:' || i.id "
        "WHERE a.used_by_run = ? ORDER BY a.id DESC LIMIT 1",
        (social.KIND, run_id),
    )


def _claims_by(conn: sqlite3.Connection, run_id: int) -> int:
    return db.scalar(conn, "SELECT count(*) FROM approvals WHERE kind = ? AND used_by_run = ?", (social.KIND, run_id)) or 0


def _run_state(conn: sqlite3.Connection, run_id: int) -> dict:
    raw = store.get_state(conn, f"{_RUN}{run_id}")
    return json.loads(raw) if raw else {}


def _set_run_state(conn: sqlite3.Connection, run_id: int, **fields: Any) -> None:
    store.set_state(conn, f"{_RUN}{run_id}", json.dumps({**_run_state(conn, run_id), **fields}))


def handed_to(conn: sqlite3.Connection, run_id: int) -> dict | None:
    """The item this run was told to read, claimed or not."""
    found = _run_state(conn, run_id).get("item")
    return store.get(conn, found) if found else None


def _claims_on(conn: sqlite3.Connection, day: str) -> int:
    return db.scalar(conn, "SELECT count(*) FROM approvals WHERE kind = ? AND substr(used_at, 1, 10) = ?", (social.KIND, day)) or 0


def _to_the_minute(moment: datetime) -> datetime:
    return moment.astimezone(timeutil.SGT).replace(second=0, microsecond=0)


def _gap_problem(conn: sqlite3.Connection, start: datetime) -> str | None:
    """Between the start of the runs that claimed two replies, in whole minutes: the slots are 20 minutes
    apart, and launchd doesn't fire to the second."""
    last = db.one(conn, "SELECT a.used_at, r.started_at FROM approvals a LEFT JOIN runs r ON r.id = a.used_by_run "
                        "WHERE a.kind = ? AND a.used_at IS NOT NULL ORDER BY a.used_at DESC, a.id DESC LIMIT 1", (social.KIND,))
    if last is None:
        return None
    previous = timeutil.parse(last["started_at"] or last["used_at"])
    gap = timedelta(minutes=settings.minutes_between_social_replies())
    return None if _to_the_minute(start) - _to_the_minute(previous) >= gap else "the last reply went too recently"


def why_not_now(conn: sqlite3.Connection, *, run_id: int | None) -> str | None:
    """Why no reply may be claimed now, whichever it is. Launchd can fire early, so the hours are here too."""
    if not settings.in_hours(caps.INBOX_REPLY_WINDOW):
        return "outside the reply hours"
    if _claims_on(conn, timeutil.today_str()) >= settings.limit("social_replies_per_day"):
        return "today's social replies are used up"
    started = db.scalar(conn, "SELECT started_at FROM runs WHERE id = ?", (run_id,)) if run_id else None
    return _gap_problem(conn, timeutil.parse(started) if started else timeutil.now_sgt())


# --- hand-out ------------------------------------------------------------------------------------


def _nothing(*reasons: str) -> dict:
    return {"due": False, "reasons": list(reasons)}


def _blocked(conn: sqlite3.Connection, run_id: int | None) -> str | None:
    paused = pause.is_paused(conn, AGENT)
    if paused:
        return f"inbox-browser is paused ({paused})"
    return social.switched_off(conn) or why_not_now(conn, run_id=run_id)


def _read_file() -> str:
    return str(paths.work_dir(JOB) / "read.json")


def _still_due(conn: sqlite3.Connection, item_id: int) -> dict | None:
    return next((item for item in due(conn) if item["id"] == item_id), None)


def hand_out(conn: sqlite3.Connection, *, run_id: int | None) -> dict:
    """`inbox reply-due`: what to read before any claim. It holds their words, and neither the reply nor who
    the session should be acting as, because the run reports that from the page (code review 06, SEC-2). A
    run gets one reply: asking again gives the same one, or nothing."""
    email_kinds.refresh_open(conn, social.KIND)
    social.settle_waiting(conn)
    cards.sweep_safely(conn)
    blocked = _blocked(conn, run_id)
    if blocked:
        return _nothing(blocked)
    given = _run_state(conn, run_id).get("item") if run_id is not None else None
    item = _still_due(conn, given) if given else next(iter(due(conn)), None)
    record = social.latest_for(conn, item) if item else None
    if item is None or record is None:
        return _nothing("no reply is waiting")
    if run_id is not None:
        _set_run_state(conn, run_id, item=item["id"])
    Path(_read_file()).unlink(missing_ok=True)  # a claim goes on what this run reads, never on what an earlier one left
    return {
        "reply_is_due": True,  # not "due": the audit reads that as the claim, and this claims nothing
        "approval": record.id,
        "item": store.label(item["id"]),
        "platform": store.platform_of(item),
        "kind": "dm" if store.is_dm(item) else "comment",
        "target_url": item["target"],
        "author": item["sender_name"],
        "their_words": [other["text"] for other in email_kinds.unanswered(conn, item) if other["text"]],
        "read_file": _read_file(),
        "accept_request": store.thread_of(item).get("surface") == social.REQUESTS,
    }


# --- the read --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Read:
    """What a run says it found on the target, before any claim. All of it is a model's word: the code
    decides from it, the run's checks hold it to what Chrome returned, and it never reaches a line he reads."""

    approval: str
    target: str
    acting_as: str
    author: str
    newest: str
    occurrence: int
    attachment: str | None
    answered: bool
    newest_url: str


def read_of(given: Any) -> Read | None:
    """A run's report, or None when it isn't one. Never raises."""
    if not isinstance(given, dict):
        return None
    approval, target = given.get("approval"), given.get("target")
    acting_as, author, newest, url = (given.get(name, "") for name in ("acting_as", "author", "newest_from_them", "newest_url"))
    occurrence = given.get("occurrence", 1)
    if not isinstance(approval, str) or not isinstance(target, str) or target not in TARGET_WORDS:
        return None
    if not all(isinstance(word, str) for word in (acting_as, author, newest, url)):
        return None
    if isinstance(occurrence, bool) or not isinstance(occurrence, int) or not 1 <= occurrence <= watch.MAX_OCCURRENCE:
        return None
    answered, attachment = given.get("page_answered", False), given.get("newest_attachment")
    if not isinstance(answered, bool):
        return None
    return Read(approval, target, acting_as, author, store.clean_text(newest).strip(), occurrence,
                attachment if isinstance(attachment, str) and attachment in watch.ATTACHMENTS else None, answered, url)


def parse_read(raw: bytes) -> Read | None:
    try:
        return read_of(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def _to_hand_reply(conn: sqlite3.Connection, item: dict, note: str, word: str, run_id: int) -> dict:
    with db.transaction(conn):
        store.close_and_tell(conn, item["id"], store.NEEDS_HAND_REPLY, note)
        log.event(conn, "inbox.reply_not_claimed", {"item": item["id"], "why": word}, agent=AGENT, run_id=run_id)
    social.read_again(conn)
    return {"due": False, "outcome": word, "reasons": [f"{store.label(item['id'])}: {word}. Nothing is typed."]}


def _reported(conn: sqlite3.Connection, item: dict, word: str, run_id: int) -> dict:
    """SEC-3: a report the run's checks judge afterwards. Until then the item and its approval stand."""
    _set_run_state(conn, run_id, reported=word)
    log.event(conn, "inbox.reply_not_claimed", {"item": item["id"], "why": word}, agent=AGENT, run_id=run_id)
    return {"due": False, "outcome": word, "reasons": [f"{store.label(item['id'])}: {word}. Nothing is typed."]}


def _is_newer(conn: sqlite3.Connection, item: dict, read: Read) -> bool | None:
    """Whether what they last wrote is newer than this item. None: the read can't be right, because it
    names neither this message nor a new one."""
    if not read.newest:
        return False if read.attachment else None  # a sticker isn't an answer to anything (F8)
    occurrence = store.thread_of(item).get("occurrence") or 1
    if watch.same_words(read.newest, item["text"]):
        return read.occurrence > occurrence
    earlier = [other for other in store.in_conversation(conn, item["conversation"]) if other["id"] < item["id"]]
    return None if any(watch.same_words(read.newest, other["text"]) for other in earlier) else True


def next_reply(conn: sqlite3.Connection, read: Read | None, *, run_id: int | None) -> dict:
    """`inbox reply-next`: judge the read of the one reply this run was handed, and claim it at most. What
    happens to one reply never touches another (code review 06, P-2). See the module's docstring."""
    if run_id is None:
        return _nothing("only a reply run claims a reply")
    state = _run_state(conn, run_id)
    if not state.get("item"):
        return _nothing("this run wasn't handed a reply: `inbox reply-due` comes first")
    if state.get("judged"):
        return _nothing("this run's one reply has been judged")
    if _claims_by(conn, run_id) >= caps.INBOX_SOCIAL_REPLIES_PER_RUN:
        return _nothing("this run has claimed its reply")
    if settle_open(conn, keep_run=run_id):  # that run was killed: it may have posted (N13)
        return _nothing("an earlier run left a claim open")
    blocked = _blocked(conn, run_id)
    if blocked:
        return _nothing(blocked)
    item = _still_due(conn, state["item"])
    record = social.latest_for(conn, item) if item else None
    if item is None or record is None:
        return _nothing("the reply this run was handed isn't waiting any more")
    if read is not None and read.approval != record.id:
        return _nothing("that read is for another approval, so nothing changes")
    _set_run_state(conn, run_id, judged=True)
    return _judged(conn, item, read, run_id)


def _judged(conn: sqlite3.Connection, item: dict, read: Read | None, run_id: int) -> dict:
    if read is None:
        return _to_hand_reply(conn, item, _UNCLEAN, "the read didn't make sense", run_id)
    if read.target == "gone":
        return _reported(conn, item, GONE, run_id)
    if read.target == "closed":
        return _reported(conn, item, BOX_CLOSED, run_id)
    if not read.acting_as:
        return _to_hand_reply(conn, item, _NO_IDENTITY, "the page doesn't show who the session is", run_id)
    identity = watch.pages()[store.platform_of(item)].name
    if not watch.same_name(read.acting_as, identity):
        watch.stop(conn, run_id, "wrong-identity")
        return _nothing("the session isn't acting as Jura, so the run stops")
    if not watch.same_name(read.author, item["sender_name"]):
        return _to_hand_reply(conn, item, _NOT_THEIRS, "the author isn't on the thread", run_id)
    if read.answered:
        return _reported(conn, item, ANSWERED, run_id)
    newer = _is_newer(conn, item, read)
    if newer is None:
        return _to_hand_reply(conn, item, _UNCLEAN, "the read didn't make sense", run_id)
    if newer:
        return _wrote_again(conn, item, read, run_id)
    return _claim(conn, item, read, run_id)


def _wrote_again(conn: sqlite3.Connection, item: dict, read: Read, run_id: int) -> dict:
    """D5, F9: their newer message joins the conversation, held until this run's checks like anything a run
    records. The card closes now, and the old draft stays until triage has read it, to answer all of it (F8)."""
    with db.transaction(conn):
        watch.record_newer(conn, run_id, item, read.newest, read.occurrence, read.newest_url)
        log.event(conn, "inbox.reply_not_claimed", {"item": item["id"], "why": "they wrote again"}, agent=AGENT, run_id=run_id)
    if not social.wrote_again(conn, store.get(conn, item["id"]) or item):
        # Already known and not proved theirs: not a clean read, and asking again would only ask again.
        return _to_hand_reply(conn, item, _UNCLEAN, "the read didn't make sense", run_id)
    social.read_again(conn)
    return {"due": False, "outcome": "they wrote again", "reasons": [f"{store.label(item['id'])}: they wrote again. Nothing is typed."]}


def _claim(conn: sqlite3.Connection, item: dict, read: Read, run_id: int) -> dict:
    """ADR 0003: one transaction re-reads the row, builds the reply, claims the approval, which checks its
    hash against what the kind computes now, and marks it in flight. It commits before the text is handed out."""
    subject = email_kinds.subject_of(item["id"])
    claimed = None
    try:
        with db.transaction(conn):
            fresh = store.get(conn, item["id"])
            reply = social.reply_of(fresh) if fresh else None
            try:
                used = approvals.use(conn, social.KIND, subject, run_id=run_id)
            except approvals.NotApproved as refused:  # a lapse or supersede `use()` finds is kept
                log.event(conn, "inbox.not_claimed", {"item": item["id"], "why": refused.reason}, level="warning", agent=AGENT, run_id=run_id)
                used = None
            if used is not None:
                if reply is None or reply.content_hash() != used.content_hash:  # raised out of the block: it rolls the claim back
                    raise approvals.NotApproved(approvals.NotApproved.MISMATCH, f"what would go out isn't what {used.id} approved", used)
                store.mark_in_flight(conn, item["id"])
                store.update_thread(conn, item["id"], claim_read={"author": read.author, "newest": read.newest, "acting_as": read.acting_as,
                                                                  "attachment": read.attachment})
                log.event(conn, "inbox.reply_claimed", {"item": item["id"], "approval": used.id}, agent=AGENT, run_id=run_id)
                claimed = (used, reply)
    except approvals.NotApproved as refused:
        log.event(conn, "inbox.not_claimed", {"item": item["id"], "why": refused.reason}, level="warning", agent=AGENT, run_id=run_id)
    cards.sweep_safely(conn)
    if claimed is None:
        return _nothing(f"{store.label(item['id'])} can't be claimed as it stands")
    used, reply = claimed
    return {
        "due": True,
        "approval": used.id,
        "item": store.label(item["id"]),
        "platform": reply.platform,
        "kind": reply.kind,
        "target_url": reply.target,
        "posting_identity": reply.identity,
        "author": reply.author,
        "text": reply.text,
        "accept_request": reply.accept_request,
        "live_text_file": str(paths.work_dir(JOB) / f"{used.id}-live.txt"),
    }


def reported_by(conn: sqlite3.Connection, run_id: int) -> str | None:
    """What this run reported finding on its target, for its checks to judge."""
    return _run_state(conn, run_id).get("reported")


def settle_reported(conn: sqlite3.Connection, item: dict, word: str, *, borne_out: bool, run_id: int) -> None:
    """SEC-3. What the run reported finding on the target, now its checks have read what Chrome returned.
    Evidence closes the item, and he hears it. Without it, it needs a hand reply, and the line says why."""
    with db.transaction(conn):
        if not borne_out:
            store.close_and_tell(conn, item["id"], store.NEEDS_HAND_REPLY, _NOT_BORNE_OUT.format(what=word))
        elif word == GONE:
            store.close_and_tell(conn, item["id"], store.CLOSED, _GONE_NOTE)
        elif word == ANSWERED:
            store.close_and_tell(conn, item["id"], store.ANSWERED_BY_HAND, _ANSWERED_NOTE)
        else:
            store.close_and_tell(conn, item["id"], store.NEEDS_HAND_REPLY, _BOX_NOTE)
        log.event(conn, "inbox.reply_settled", {"item": item["id"], "what": word, "borne_out": borne_out}, agent=AGENT, run_id=run_id)


# --- the outcome -----------------------------------------------------------------------------------


def same_live_text(approved: str, live: str, author: str) -> bool:
    """The read-back: the approved words exactly as NFC and collapsed whitespace read, with room in front
    for what a platform prefills on a reply to someone, their `@handle` or their name (functional N3)."""
    want, found = text_mod.normal(approved), text_mod.normal(live)
    if want == found:
        return True
    if not found.endswith(" " + want):
        return False
    prefill = found[: -len(want)].strip()
    return (prefill.startswith("@") and " " not in prefill) or watch.same_name(prefill, author)


def _open_for(conn: sqlite3.Connection, typed: str, run_id: int | None) -> tuple[approvals.Approval | None, dict | None]:
    record = approvals.get(conn, typed)
    if record is None or record.kind != social.KIND or run_id is None or record.used_by_run != run_id:
        return None, None
    item_id = email_kinds.item_id_of(record.subject)
    item = store.get(conn, item_id) if item_id is not None else None
    return (record, item) if item is not None and item["state"] == store.SENDING else (None, None)


def done(conn: sqlite3.Connection, typed: str, *, url: str | None, live: str | None, run_id: int | None) -> tuple[bool, str]:
    """`inbox reply-done`: what this run says became of its claim. Returns whether it was recorded, and fixed
    words: neither the address nor the text it was given comes back. A matching read-back is only a report:
    `sent` is for the run's checks, from what Chrome returned (code review 06, P-1)."""
    record, item = _open_for(conn, typed, run_id)
    if record is None or item is None:
        return False, f"refused: {typed} isn't a reply this run claimed and has open"
    label = store.label(item["id"])
    if url is None or live is None:
        with db.transaction(conn):
            store.set_item_state(conn, item["id"], store.FAILED, note=_NOT_SENT)
            log.event(conn, "inbox.reply_failed", {"item": item["id"]}, level="warning", agent=AGENT, run_id=run_id)
        return True, f"{record.id}: {label} recorded as not sent"
    platform = store.platform_of(item)
    if watch.target_problem(platform, url) or watch.thread_of(url) != watch.thread_of(item["target"]):
        return False, f"refused: that address isn't this reply's own thread on {platform}. Read it back from the thread you replied in."
    if not same_live_text(item["draft"], live, item["sender_name"]):
        with db.transaction(conn):
            store.set_item_state(conn, item["id"], store.UNKNOWN, note=_DIFFERENT)
            log.event(conn, "inbox.reply_differs", {"item": item["id"], "approval": record.id}, level="error", agent=AGENT, run_id=run_id)
            pause.pause(conn, AGENT, f"the read-back of {record.id} isn't what was approved", notify=False)
        return True, f"{record.id}: the read-back isn't what was approved, so inbox-browser is paused"
    with db.transaction(conn):
        store.update_thread(conn, item["id"], reply_reported=True, reply_url=url)  # the run's word: kept here, and shown nowhere
        log.event(conn, "inbox.reply_reported", {"item": item["id"], "approval": record.id}, agent=AGENT, run_id=run_id)
    return True, f"{record.id}: {label} read back. The run's checks confirm it"


def confirm(conn: sqlite3.Connection, item: dict, *, proved: bool, run_id: int | None) -> None:
    """The run's checks on a claim it says went (P-1, SEC-1, SEC-2). With proof it is `sent`, and F10: a reply
    that promised more stays open as needing Levi, until he says it's done. Without, nobody can say it went
    where it should, so it is `unknown`, and that pauses and alerts."""
    with db.transaction(conn):
        if not proved:
            store.set_item_state(conn, item["id"], store.UNKNOWN, note=_NOT_PROVED)
            log.event(conn, "inbox.reply_not_proved", {"item": item["id"]}, level="error", agent=AGENT, run_id=run_id)
            pause.pause(conn, AGENT, f"run {run_id} says a reply went and can't prove it", notify=False)
            return
        now = timeutil.stamp()
        conn.execute("UPDATE inbox_items SET sent_at = ?, updated_at = ? WHERE id = ?", (now, now, item["id"]))
        if item["promised"]:
            store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note="Posted, and it promises a personal reply from Levi.")
        else:
            store.set_item_state(conn, item["id"], store.SENT)
        log.event(conn, "inbox.sent", {"item": item["id"]}, agent=AGENT, run_id=run_id)


def typed_after_saying_not_sent(conn: sqlite3.Connection, item: dict, run_id: int | None) -> None:
    with db.transaction(conn):
        store.set_item_state(conn, item["id"], store.UNKNOWN, note=_TYPED_ANYWAY)
        pause.pause(conn, AGENT, f"run {run_id} typed a reply it says didn't go", notify=False)


def open_claims(conn: sqlite3.Connection) -> list[dict]:
    places = ", ".join("?" for _ in store.SOCIAL_SOURCES)
    return db.rows(conn, f"SELECT * FROM inbox_items WHERE state = ? AND source IN ({places}) ORDER BY id", (store.SENDING, *store.SOCIAL_SOURCES))


def settle_open(conn: sqlite3.Connection, *, keep_run: int | None = None) -> list[dict]:
    """N13: every claim with no outcome, except one the live run `keep_run` holds, is `unknown`, and the
    agent pauses. Call it where no other run can hold a claim: under the browser lock, or in a run."""
    settled = []
    for item in open_claims(conn):
        record = social.latest_for(conn, item)
        if keep_run is not None and record is not None and record.used_by_run == keep_run:
            continue
        settled.append(item)
    if not settled:
        return []
    with db.transaction(conn):
        for item in settled:
            store.set_item_state(conn, item["id"], store.UNKNOWN, note=_OPEN_CLAIM)
            log.event(conn, "inbox.reply_unknown", {"item": item["id"]}, level="error", agent=AGENT)
        pause.pause(conn, AGENT, "a reply run left a claim open, so it may have posted", notify=False)
    return settled


def forget_run(conn: sqlite3.Connection, run_id: int) -> None:
    store.clear_state(conn, f"{_RUN}{run_id}")


def forget_killed_runs(conn: sqlite3.Connection) -> None:
    """What a killed run was handed and reported, which closes nothing. Under the job's lock, so no live run holds one."""
    for run, _ in store.with_prefix(conn, _RUN):
        store.clear_state(conn, f"{_RUN}{run}")


# --- what Ting Yu hears (F15): `send._tell` posts these ------------------------------------------------


def link_of(item: dict) -> str:
    """The item's own target, as the watch cleaned it. Never the address a run reported (code review 06, S-8)."""
    return f"<{watch.clean_link(item['target'])}>" if item["target"] else "the platform"


def alert_words(item: dict) -> str:
    """F15 asks for "may have posted" on `failed` too. A `failed` here is one the run's checks found no typing
    in, so it says what is true (code review 06, S-7)."""
    if item["state"] == store.FAILED:
        return f"didn't post, and it won't be tried again. Answer by hand if it still matters: {link_of(item)}"
    return (f"may have posted, check here before answering by hand: {link_of(item)}. It is never sent again, and "
            "there is nothing to resolve: `/growth inbox list` shows it for 7 days.")
