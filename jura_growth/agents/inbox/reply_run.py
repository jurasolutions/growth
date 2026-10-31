"""What an `inbox-reply` run may do, and what its reports come to (PRD D4, F9, F15, S4; N12, N13).

A reply run types into a real conversation on a signed-in account, just after reading text anyone can
write. So its model decides nothing. In order:

1. **`reply-due`** hands out one approved reply's target and whose words to look for, and not the reply.
2. **The read (F9).** It opens the target and reports what it found in a file. Nothing has been claimed yet,
   and typing now fails the run's audit.
3. **`reply-next`** decides from that report:
   - the target has gone: closed with a note, and nothing is paused, because a deleted comment isn't a
     warning (S4). A closed reply box needs a hand reply;
   - the session isn't acting as Jura: a stop signal;
   - the person on the thread isn't the item's author, or the read doesn't make sense: a hand reply (N12);
   - the Page has already answered: closed `answered by hand`;
   - they have written since: that message is recorded and the draft is superseded, so triage drafts
     again over the whole conversation;
   - only a clean read is claimed, in one transaction, and only then is the reply's text handed out.
4. **`reply-done`** takes the read-back: the same thread, and the same words, with room for the `@handle`
   a platform puts in front (functional N3). Words that don't match mean something else went out, so the
   item is `unknown`, and the agent pauses.

**No claim left open survives (N13).** A claim with no outcome when its run ends, or found by a later job,
is `unknown` and pauses `inbox-browser`. It is listed for 7 days and never sent again, so there is nothing to
resolve and no command that resolves it.

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

from jura_growth import approvals, caps, cards, db, discord, log, paths, pause, timeutil
from jura_growth.agents.inbox import kinds as email_kinds
from jura_growth.agents.inbox import report, settings, social, store, watch
from jura_growth.agents.publish import text as text_mod

AGENT = social.AGENT
JOB = "inbox-reply"
TARGET_WORDS = ("found", "gone", "closed")
_HANDED = "reply.handed."  # + run: the item this run was told to read
_UNCLEAN = "The reply run couldn't get a clean read of this thread, so nothing was typed. Answer by hand if it still matters."
_NOT_THEIRS = "The person on that thread isn't who wrote this, so nothing was typed. Answer by hand if it needs one."
_GONE = "The comment or thread has gone, so nothing was typed. No reply is needed unless they write again."
_BOX_CLOSED = "The reply box on that thread is closed, so nothing was typed. Answer another way if it matters."
_ANSWERED = "The Page had already answered this by hand, so the draft was dropped and nothing was typed."
_NOT_SENT = "The run says it couldn't post this, and nothing was sent. It won't be tried again. Answer by hand if it still matters."
_OPEN_CLAIM = "A reply run claimed this and recorded no outcome, so it may have posted. It won't be sent again."
_DIFFERENT = "What the page shows isn't what was approved, so check it. It won't be sent again."


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


def handed_to(conn: sqlite3.Connection, run_id: int) -> dict | None:
    """The item this run was told to read, claimed or not."""
    found = store.get_state(conn, f"{_HANDED}{run_id}")
    return store.get(conn, int(found)) if found else None


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


def hand_out(conn: sqlite3.Connection, *, run_id: int | None) -> dict:
    """`inbox reply-due`: what to read before any claim. It holds their words and never the reply."""
    approvals.expire_due(conn)
    cards.sweep_safely(conn)
    blocked = _blocked(conn, run_id)
    if blocked:
        return _nothing(blocked)
    waiting = due(conn)
    if not waiting:
        return _nothing("no reply is waiting")
    item = waiting[0]
    record = social.latest_for(conn, item)
    if run_id is not None:
        store.set_state(conn, f"{_HANDED}{run_id}", str(item["id"]))
    Path(_read_file()).unlink(missing_ok=True)  # a claim goes on what this run reads, never on what an earlier one left
    platform = social.platform_of(item)
    return {
        "reply_is_due": True,
        "approval": record.id,
        "item": store.label(item["id"]),
        "platform": platform,
        "kind": "dm" if social.is_dm(item) else "comment",
        "target_url": item["target"],
        "posting_identity": watch.pages()[platform].name,
        "author": item["sender_name"],
        "their_words": [other["text"] for other in email_kinds.unanswered(conn, item) if other["text"]],
        "read_file": _read_file(),
        "accept_request": store.thread_of(item).get("surface") == social.REQUESTS,
    }


# --- the read --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Read:
    """What a run says it found on the target, before any claim. All of it is a model's word: the code
    decides from it, `after_run` checks it against what Chrome returned, and it never reaches a line he reads."""

    approval: str
    target: str
    acting_as: str
    author: str
    newest: str
    occurrence: int
    attachment: bool
    answered: bool
    newest_url: str


def read_of(given: Any) -> Read | None:
    """A run's report, or None when it isn't one. Never raises."""
    if not isinstance(given, dict):
        return None
    words = (given.get("approval"), given.get("target"), given.get("acting_as", ""), given.get("author", ""), given.get("newest_from_them", ""),
             given.get("newest_url", ""))
    occurrence = given.get("occurrence", 1)
    if not all(isinstance(word, str) for word in words) or given.get("target") not in TARGET_WORDS:
        return None
    if isinstance(occurrence, bool) or not isinstance(occurrence, int) or not 1 <= occurrence <= watch.MAX_OCCURRENCE:
        return None
    if not isinstance(given.get("page_answered", False), bool):
        return None
    attachment = given.get("newest_attachment")
    return Read(words[0], words[1], words[2], words[3], store.clean_text(words[4]).strip(), occurrence,
                isinstance(attachment, str) and attachment in watch.ATTACHMENTS, given.get("page_answered", False), words[5])


def parse_read(raw: bytes) -> Read | None:
    try:
        return read_of(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None


def _close(conn: sqlite3.Connection, item: dict, state: str, note: str, word: str, run_id: int | None) -> dict:
    with db.transaction(conn):
        store.close_and_tell(conn, item["id"], state, note)
        log.event(conn, "inbox.reply_not_claimed", {"item": item["id"], "why": word}, agent=AGENT, run_id=run_id)
    approvals.expire_due(conn)
    cards.sweep_safely(conn)
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
    """`inbox reply-next`: judge the read, and claim at most one reply. See the module's docstring."""
    if run_id is None:
        return _nothing("only a reply run claims a reply")
    if claimed_by(conn, run_id) is not None:
        return _nothing(f"this run has claimed its {caps.INBOX_SOCIAL_REPLIES_PER_RUN} reply")
    if settle_open(conn, keep_run=run_id):  # that run was killed: it may have posted (N13)
        tell_now(conn)
        return _nothing("an earlier run left a claim open")
    blocked = _blocked(conn, run_id)
    if blocked:
        return _nothing(blocked)
    waiting = due(conn)
    if not waiting:
        return _nothing("no reply is waiting")
    item = waiting[0]
    record = social.latest_for(conn, item)
    if read is None or read.approval != record.id:
        return _close(conn, item, store.NEEDS_HAND_REPLY, _UNCLEAN, "the read didn't make sense", run_id)
    if read.target == "gone":
        return _close(conn, item, store.CLOSED, _GONE, "the target has gone", run_id)
    if read.target == "closed":
        return _close(conn, item, store.NEEDS_HAND_REPLY, _BOX_CLOSED, "the reply box is closed", run_id)
    identity = watch.pages()[social.platform_of(item)].name
    if not watch.same_name(read.acting_as, identity):
        watch.stop(conn, run_id, "wrong-identity")
        return _nothing("the session isn't acting as Jura, so the run stops")
    if not watch.same_name(read.author, item["sender_name"]):
        return _close(conn, item, store.NEEDS_HAND_REPLY, _NOT_THEIRS, "the author isn't on the thread", run_id)
    if read.answered:
        return _close(conn, item, store.ANSWERED_BY_HAND, _ANSWERED, "the Page has answered", run_id)
    newer = _is_newer(conn, item, read)
    if newer is None:
        return _close(conn, item, store.NEEDS_HAND_REPLY, _UNCLEAN, "the read didn't make sense", run_id)
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
        return _close(conn, item, store.NEEDS_HAND_REPLY, _UNCLEAN, "the read didn't make sense", run_id)
    approvals.expire_due(conn)
    cards.sweep_safely(conn)
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
                now = timeutil.stamp()
                conn.execute("UPDATE inbox_items SET state = ?, send_attempts = send_attempts + 1, asked_at = NULL, guidance = NULL, updated_at = ? WHERE id = ?",
                             (store.SENDING, now, item["id"]))
                store.update_thread(conn, item["id"], claim_read={"author": read.author, "newest": read.newest})
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
    """`inbox reply-done`: what became of this run's claim. Returns whether it was recorded, and fixed
    words: neither the address nor the text it was given comes back."""
    record, item = _open_for(conn, typed, run_id)
    if record is None or item is None:
        return False, f"refused: {typed} isn't a reply this run claimed and has open"
    label = store.label(item["id"])
    if url is None or live is None:
        with db.transaction(conn):
            store.set_item_state(conn, item["id"], store.FAILED, note=_NOT_SENT)
            log.event(conn, "inbox.reply_failed", {"item": item["id"]}, level="warning", agent=AGENT, run_id=run_id)
        return True, f"{record.id}: {label} recorded as not sent"
    platform = social.platform_of(item)
    if watch.target_problem(platform, url) or watch.thread_of(url) != watch.thread_of(item["target"]):
        return False, f"refused: that address isn't this reply's own thread on {platform}. Read it back from the thread you replied in."
    if not same_live_text(item["draft"], live, item["sender_name"]):
        with db.transaction(conn):
            store.set_item_state(conn, item["id"], store.UNKNOWN, note=_DIFFERENT)
            log.event(conn, "inbox.reply_differs", {"item": item["id"], "approval": record.id}, level="error", agent=AGENT, run_id=run_id)
            pause.pause(conn, AGENT, f"the read-back of {record.id} isn't what was approved", notify=False)
        return True, f"{record.id}: the read-back isn't what was approved, so inbox-browser is paused"
    _mark_sent(conn, item, url, run_id)
    return True, f"{record.id}: {label} posted"


def _mark_sent(conn: sqlite3.Connection, item: dict, url: str, run_id: int | None) -> None:
    """F10: a reply that promised more stays open as needing Levi, until he says it's done."""
    with db.transaction(conn):
        now = timeutil.stamp()
        conn.execute("UPDATE inbox_items SET sent_at = ?, updated_at = ? WHERE id = ?", (now, now, item["id"]))
        store.update_thread(conn, item["id"], reply_url=url)
        if item["promised"]:
            store.set_item_state(conn, item["id"], store.NEEDS_HAND_REPLY, note="Posted, and it promises a personal reply from Levi.")
        else:
            store.set_item_state(conn, item["id"], store.SENT)
        log.event(conn, "inbox.sent", {"item": item["id"]}, agent=AGENT, run_id=run_id)


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


def forget_handed(conn: sqlite3.Connection, run_id: int) -> None:
    store.clear_state(conn, f"{_HANDED}{run_id}")


def forget_killed_runs(conn: sqlite3.Connection) -> None:
    """What a killed run was told to read. Under the job's lock, so no live run holds one."""
    for run, _ in store.with_prefix(conn, _HANDED):
        store.clear_state(conn, f"{_HANDED}{run}")


# --- what Ting Yu hears (F15) ------------------------------------------------------------------------


def link_of(item: dict) -> str:
    return store.thread_of(item).get("reply_url") or item["target"]


def tell(conn: sqlite3.Connection, item: dict) -> bool:
    """One outcome's line, and whether Discord took it. Nothing is attempted with no webhook set."""
    label = store.label(item["id"])
    record = social.latest_for(conn, item)
    number = record.id if record else label
    where = report.SOCIAL_HEADINGS[item["source"]]
    link = f"<{link_of(item)}>" if link_of(item) else "the platform"
    if item["sent_at"] or item["state"] == store.LAPSED:
        if not discord.webhook_set(report.CHANNEL):
            return False
        if item["sent_at"]:
            name = report.shown_name(item["sender_name"])
            text = f"{number} sent to {name or 'them'}, {cards.clock(item['sent_at'])} SGT ({label}): {link}"
            if item["state"] == store.NEEDS_HAND_REPLY:
                text += f" It promises a personal reply, so {label} stays open until `/growth inbox done {label}`."
            own = (name,) if name else ()
        else:
            text, own = f"{number} lapsed: answer {label} by hand if it still matters, at {link}.", ()
        return discord.post(conn, report.CHANNEL, text, username=report.USERNAME, dedupe=False, suppress_embeds=True, conversation=own).delivered
    if not discord.webhook_set("alerts"):
        return False
    if item["state"] == store.FAILED:
        said = f"didn't post, and it won't be tried again. Answer by hand if it still matters: {link}"
    else:
        said = (f"may have posted, check here before answering by hand: {link}. It is never sent again, and "
                "there is nothing to resolve: `/growth inbox list` shows it for 7 days.")
    return discord.alert(conn, f"{number}: the reply to {label} ({where}) {said}", agent=AGENT).delivered


def tell_now(conn: sqlite3.Connection) -> None:
    """Outcomes owed, by the one list `inbox-send` also reads. A line Discord refuses goes again from either."""
    from jura_growth.agents.inbox import send

    send.tell_safely(conn)

