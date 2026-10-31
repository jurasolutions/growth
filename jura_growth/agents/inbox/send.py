"""`jura-growth inbox send-due`, job `inbox-send`: sending the email replies Ting Yu approved (D2, D3).

Every 10 minutes, 08:00 to 22:00 SGT, with no model. In order, for each approved reply:

1. **A fresh read (F9).** The mail intake runs first, outside any transaction, so a message they wrote a
   minute ago supersedes the draft rather than being answered over. A read that failed or didn't finish
   isn't clean, and nothing is claimed on it: the next slot tries again. D1's suppression list is synced
   once a run first, so someone who clicked unsubscribe gets no email (E2).
2. **The claim (ADR 0003).** One `BEGIN IMMEDIATE` transaction re-reads the item, builds the reply from
   that row, claims the approval (which checks its hash against what the kind computes now), counts the
   attempt and keeps the outgoing `Message-ID`. It commits before Resend is called, and only the reply
   built here is sent.
3. **Resend**, under `Idempotency-Key: jura-inbox-reply-<id>`.

A claimed reply Resend errored on, or that the process lost before the mark, is retried under the same
key with no second claim, while it still hashes to what was approved and inside whichever comes first:
`caps.OUTREACH_RETRY_WINDOW_HOURS` from the claim, or the use-by. Past either it may already have gone out,
so it is marked `unknown` and never sent again (N13).

A failed send never counts toward auto-pause: this job shares the `inbox` flag with the mail watch, and
three Resend errors must not stop anyone being seen (technical review B5). So nothing here raises. A
crash is logged and alerts once a day, the way a failed mail check does, and because a good slot leaves no
run row, failures weeks apart would otherwise read as "in a row" (code review 01, P-5).

Ting Yu hears each outcome once (F15, S7): `told_at` stays empty until Discord takes the line. These lines
hold no words anyone wrote, and the only name is on `sent`, under the conversation class.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import httpx

from jura_growth import approvals, caps, cards, db, discord, locks, log, pause, timeutil
from jura_growth.agents.inbox import kinds, mail, report, settings, store
from jura_growth.agents.outreach import send as outreach_send
from jura_growth.agents.outreach import sync
from jura_growth.agents.scout import settings as scout_settings

AGENT = "inbox"
LOCK = "inbox-send-due"  # the job's own lock is the runner's; this one holds for a run by hand too
RETRIES = 3  # attempts at one claim, as outreach has it
_FAILURE = "send"  # the label a crash goes under on the health strip
_REFUSED = "resend"  # and one where Resend refuses the account
_MAY_HAVE_GONE = "It may have gone out: check the copy in Levi's mailbox before answering by hand. It won't be sent again."


def in_window() -> bool:
    """PRD §4: launchd can fire early until the Mac restarts, so the hours are checked here too."""
    start, end = caps.INBOX_SEND_WINDOW
    return start <= timeutil.now_sgt().strftime("%H:%M") <= end


def due(conn: sqlite3.Connection) -> list[dict]:
    """Replies Ting Yu approved: unclaimed, or claimed and not finished. High priority first."""
    return db.rows(
        conn,
        "SELECT i.* FROM inbox_items i JOIN approvals a ON a.kind = ? AND a.subject = 'inbox_item:' || i.id AND a.status = 'approved' "
        "WHERE (i.state = ? AND a.used_at IS NULL) OR (i.state = ? AND a.used_at IS NOT NULL) "
        "ORDER BY COALESCE(i.priority, '') = 'high' DESC, i.id",
        (kinds.KIND, store.WAITING, store.SENDING),
    )


# --- the run -------------------------------------------------------------------------------------


def send_due(conn: sqlite3.Connection, *, client: httpx.Client | None = None) -> str:
    """One send run. Returns a summary of counts, empty when nothing happened. Never raises."""
    with locks.held(LOCK) as acquired:
        if not acquired:
            return ""
        try:
            summary = _send_due(conn, client)
            mail.cleared(conn, _FAILURE)
        except Exception as error:  # noqa: BLE001 - see the module's docstring
            log.event(None, "inbox.send_error", {"error": type(error).__name__}, level="error", agent=AGENT)
            mail.failed(conn, _FAILURE, error)
            summary = f"the send run stopped on {type(error).__name__}"
        _tell_safely(conn)
    cards.sweep_safely(conn)
    return summary


def _clean_read(conn: sqlite3.Connection) -> bool:
    """F9. Only here, with no transaction open: the network is never inside a claim."""
    if not mail.mailboxes():
        return False
    found = mail.intake(conn)
    return not found.failed and not found.unfinished


def _send_due(conn: sqlite3.Connection, client: httpx.Client | None) -> str:
    if pause.is_paused(conn, AGENT):
        return ""
    kinds.refresh_open(conn)
    kinds.settle_waiting(conn)
    kinds.raise_due(conn)
    if not in_window() or kinds.switched_off():
        return ""
    waiting = due(conn)
    if not waiting:
        return ""
    d1 = sync.sync_suppression(conn)
    if d1.configured and not d1.ok:
        return "not sending: the suppression list couldn't be synced"
    done = {"sent": 0, "failed": 0, "uncertain": 0, "will retry": 0}
    for item in waiting:
        if item["state"] == store.WAITING and store.sent_on(conn, timeutil.today_str()) >= settings.limit("email_replies_per_day"):
            log.event(conn, "inbox.daily_cap", {"item": item["id"]}, agent=AGENT)
            continue
        if not _clean_read(conn):
            log.event(conn, "inbox.not_a_clean_read", {"item": item["id"]}, level="warning", agent=AGENT)
            break
        word = _send_one(conn, item["id"], client)
        if word:
            done[word] += 1
    kinds.settle_waiting(conn)
    return ", ".join(f"{count} {word}" for word, count in done.items() if count)


@dataclass
class _Claimed:
    """What the claim checked, and so exactly what goes out."""

    reply: kinds.Reply
    message_id: str
    attempts: int
    promised: bool


def _outgoing_id(subject: str, claim: approvals.Approval) -> str:
    return store.outgoing_id(f"{subject}|{claim.content_hash}|{claim.used_at}", outreach_send.sending_domain())


def _claim(conn: sqlite3.Connection, item_id: int) -> _Claimed | None:
    """The claim, or None with nothing claimed. A lapse or supersede `use()` finds is kept. A refusal
    raised after it rolls the claim back with everything else."""
    subject = kinds.subject_of(item_id)
    try:
        with db.transaction(conn):
            item = store.get(conn, item_id)
            if item is None:
                return None
            if item["state"] == store.SENDING:
                return _retry(conn, item, subject)
            if item["state"] != store.WAITING:
                return None
            reply = kinds.reply_of(item)
            try:
                used = approvals.use(conn, kinds.KIND, subject, run_id=log.current_run_id())
            except approvals.NotApproved as refused:
                log.event(conn, "inbox.not_claimed", {"item": item_id, "why": refused.reason}, level="warning", agent=AGENT)
                return None
            if reply is None or reply.content_hash() != used.content_hash:
                raise approvals.NotApproved(approvals.NotApproved.MISMATCH, f"what would go out isn't what {used.id} approved", used)
            return _in_flight(conn, item, reply, subject, used)
    except approvals.NotApproved as refused:
        log.event(conn, "inbox.not_claimed", {"item": item_id, "why": refused.reason}, level="warning", agent=AGENT)
        return None


def _in_flight(conn: sqlite3.Connection, item: dict, reply: kinds.Reply, subject: str, claim: approvals.Approval) -> _Claimed:
    now = timeutil.stamp()
    conn.execute("UPDATE inbox_items SET state = ?, send_attempts = send_attempts + 1, updated_at = ? WHERE id = ?",
                 (store.SENDING, now, item["id"]))
    message_id = _outgoing_id(subject, claim)
    store.remember_outgoing(conn, message_id, lead_id=item["lead_id"])
    return _Claimed(reply, message_id, item["send_attempts"] + 1, bool(item["promised"]))


def _retry(conn: sqlite3.Connection, item: dict, subject: str) -> _Claimed | None:
    """The same action instance, with no second claim, unless it may no longer go: they wrote again,
    it changed, or the retry's time is up. Then whether it went is unknowable, and it never goes again."""
    earlier = approvals.latest(conn, kinds.KIND, subject)
    reply = kinds.reply_of(item)
    now_says = kinds.EmailReply().content(conn, subject)
    if earlier is None or not earlier.used_at:
        closed = "its claim can't be found"
    elif now_says is None or reply is None or approvals.content_hash(now_says) != earlier.content_hash:
        closed = "what would go out changed after it was claimed"
    else:
        closed = outreach_send.retry_closed(earlier, timeutil.now_sgt())
    if closed or reply is None or earlier is None:
        store.set_item_state(conn, item["id"], store.UNKNOWN, note="It may have gone out, and it won't be sent again.")
        log.event(conn, "inbox.send_unknown", {"item": item["id"]}, level="warning", agent=AGENT)
        return None
    return _in_flight(conn, item, reply, subject, earlier)


def _payload(claimed: _Claimed) -> dict:
    reply = claimed.reply
    headers = {"Message-ID": claimed.message_id}
    if reply.in_reply_to:
        headers |= {"In-Reply-To": reply.in_reply_to, "References": " ".join(reply.references)}
    return {
        "from": outreach_send.from_address(),
        "to": [reply.to],
        "bcc": [reply.bcc],
        "reply_to": scout_settings.REPLY_TO,
        "subject": reply.subject,
        "text": reply.text,
        "headers": headers,
        "tags": [{"name": "agent", "value": AGENT}, {"name": "item", "value": str(reply.item_id)}],
    }


def _send_one(conn: sqlite3.Connection, item_id: int, client: httpx.Client | None) -> str | None:
    claimed = _claim(conn, item_id)
    if claimed is None:
        return "uncertain" if (store.get(conn, item_id) or {}).get("state") == store.UNKNOWN else None
    outcome, detail = outreach_send.post_email(_payload(claimed), f"jura-inbox-reply-{item_id}", client)
    if outcome == "sent":
        _mark_sent(conn, item_id, claimed, detail)
        return "sent"
    # Resend's words can name the address, so only its status code is kept.
    code = next(iter(re.findall(r"^\d{3}", detail)), None)
    log.event(conn, "inbox.send_failed", {"item": item_id, "outcome": outcome, "status": code}, level="warning", agent=AGENT)
    if outcome == "pause":
        mail.problem(conn, _REFUSED, "Resend refused the account, so approved replies aren't going out. Check its key, quota and domain.",
                     code or outcome)
    if outcome != "fail" and claimed.attempts < RETRIES:
        return "will retry"
    store.set_item_state(conn, item_id, store.FAILED, note="The send failed. It may have gone out, and it won't be sent again.")
    return "failed"


def _mark_sent(conn: sqlite3.Connection, item_id: int, claimed: _Claimed, resend_id: str) -> None:
    """F10: a reply that promised more stays open as needing Levi, until he says it's done."""
    with db.transaction(conn):
        now = timeutil.stamp()
        conn.execute("UPDATE inbox_items SET sent_at = ?, resend_id = ?, updated_at = ? WHERE id = ?", (now, resend_id, now, item_id))
        if claimed.promised:
            store.set_item_state(conn, item_id, store.NEEDS_HAND_REPLY, note="Sent, and it promises a personal reply from Levi.")
        else:
            store.set_item_state(conn, item_id, store.SENT)
        log.event(conn, "inbox.sent", {"item": item_id}, agent=AGENT, run_id=log.current_run_id())
    mail.cleared(conn, _REFUSED)


# --- what Ting Yu hears --------------------------------------------------------------------------


def _clock(stamp: str) -> str:
    return timeutil.parse(stamp).astimezone(timeutil.SGT).strftime("%H:%M")


def _tell(conn: sqlite3.Connection, item: dict) -> bool:
    """One outcome's line, and whether Discord took it. Nothing is attempted with no webhook set."""
    label = store.label(item["id"])
    record = approvals.latest(conn, kinds.KIND, kinds.subject_of(item["id"]))
    number = record.id if record else label
    if item["sent_at"] or item["state"] == store.LAPSED:
        if not discord.webhook_set(report.CHANNEL):
            return False
        if item["sent_at"]:
            name = report.shown_name(item["sender_name"])
            text = f"{number} sent to {name or item['sender_domain']}, {_clock(item['sent_at'])} SGT ({label})."
            if item["state"] == store.NEEDS_HAND_REPLY:
                text += f" It promises a personal reply, so {label} stays open until `/growth inbox done {label}`."
            own = (name,) if name else ()
        else:
            text, own = f"{number} lapsed: answer {label} by hand if it still matters.", ()
        return discord.post(conn, report.CHANNEL, text, username=report.USERNAME, dedupe=False, suppress_embeds=True,
                            conversation=own).delivered
    if not discord.webhook_set("alerts"):
        return False
    what = "failed" if item["state"] == store.FAILED else "can't be confirmed"
    return discord.alert(conn, f"{number}: the reply to {label} ({item['sender_domain']}) {what}. {_MAY_HAVE_GONE}", agent=AGENT).delivered


def tell_outcomes(conn: sqlite3.Connection) -> int:
    """Every outcome still owed, stopping at the first Discord refuses: the rest wait for the next slot."""
    told = 0
    for item in store.outcomes_owed(conn):
        if not _tell(conn, item):
            break
        store.mark_told(conn, item["id"])
        told += 1
    return told


def _tell_safely(conn: sqlite3.Connection) -> None:
    try:
        tell_outcomes(conn)
    except Exception as error:  # noqa: BLE001 - the send stands whatever happens to the line about it
        log.event(None, "inbox.tell_error", {"error": type(error).__name__}, level="warning", agent=AGENT)
