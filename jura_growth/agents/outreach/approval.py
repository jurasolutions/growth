"""The `outreach-email` approval kind (MC §4.6, §5.7, §5.8; ticket 06).

Every live email, first or follow-up, goes out only on an approval claimed
first. The subject is one queued message, `outreach_message:<id>`.

- **Content** is the recipient address of the contact row the send will use
  (`queue.recipient()`), the subject and `draft_body`: never the footer, which
  is recomposed at send time with the current unsubscribe token. A message that
  won't go out any more (cancelled, skipped, dropped, sent) is gone, so its
  request is superseded at the next read or claim; no cancellation call site
  needs to know about approvals. A shadow-sent message keeps its content, so an
  approval for an email shadow-sent after a switch back to shadow lapses at its
  use-by rather than being superseded (AC-M8.10).
- **Deadlines:** decide by 16:30 on the next business day; use by 16:30 on the
  third business day after approval. `config/settings.yaml` may shorten either
  (`approvals.deadlines.outreach-email`), never lengthen one.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, time

from jura_growth import approval_settings, approvals, caps, db, log, pause, timeutil
from jura_growth.agents.outreach import store

KIND = "outreach-email"
_SUBJECT = re.compile(r"outreach_message:([0-9]+)")
# Messages whose email may still go out: queued, or recorded in shadow mode (see above).
_HELD = ("queued", "shadow")


def subject_of(message_id: int) -> str:
    return f"outreach_message:{int(message_id)}"


def message_id(subject: str) -> int | None:
    match = _SUBJECT.fullmatch(subject or "")
    return int(match.group(1)) if match else None


def _message(conn: sqlite3.Connection, subject: str) -> dict | None:
    number = message_id(subject)
    if number is None:
        return None
    return db.one(conn, "SELECT * FROM outreach_messages WHERE id = ?", (number,))


def _canonical(value: dict) -> bytes:
    normalised = {k: unicodedata.normalize("NFC", str(v)) for k, v in value.items()}
    return json.dumps(normalised, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _at_cutoff(day: date) -> datetime:
    hour, minute = (int(part) for part in caps.OUTREACH_DEADLINE_TIME.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=timeutil.SGT)


class OutreachEmail:
    """The kind `approvals` asks about every `outreach_message:<id>`."""

    name = KIND

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        from jura_growth.agents.outreach import queue

        message = _message(conn, subject)
        if message is None or message["status"] not in _HELD:
            return None
        try:
            _, row = queue.recipient(conn, message["lead_id"])
        except queue.QueueError:
            return None
        return _canonical({"to": row["email"], "subject": message["subject"], "body": message["draft_body"]})

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """The card (MC §5.6): who it goes to, why, and the draft as it will go
        out. Emails greet the company, never a person (the `email` brand
        channel drops one that names someone), so the draft is shown exactly.
        A named-person address is masked beside its source page; the hash
        still covers the full address."""
        from jura_growth import privacy
        from jura_growth.agents.outreach import queue

        message = _message(conn, subject)
        if message is None:
            raise LookupError(f"no message for {subject}")
        lead, row = queue.recipient(conn, message["lead_id"])
        found_by = db.one(conn, "SELECT id, job FROM runs WHERE id = ?", (lead["run_id"],)) if lead["run_id"] else None
        origin = f" from {found_by['job']} run {found_by['id']}" if found_by else ""
        draft = "\n".join(f"> {line}" if line else ">" for line in message["draft_body"].split("\n"))
        return approvals.Preview(
            title=f"To: {privacy.masked_address(row['email'])} ({lead['company']}, {lead['industry']}, score {lead['score']})",
            reason=f"lead {lead['id']}{origin}; address listed on {row['source_url']}",
            text=f"Subject: {message['subject']}\n{draft}",
        )

    def deadlines(self, conn: sqlite3.Connection | None, subject: str, now: datetime) -> approvals.Deadlines:
        today = now.astimezone(timeutil.SGT).date()
        decide = approval_settings.deadline(KIND, "decide_by_business_days")
        use = approval_settings.deadline(KIND, "use_by_business_days")
        return approvals.Deadlines(
            decide_by=_at_cutoff(store.add_business_days(today, decide)),
            use_by=_at_cutoff(store.add_business_days(today, use)),
        )

    # The kind's own switch: `use()` refuses without claiming while it shows.
    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        from jura_growth.agents.outreach import send
        from jura_growth.agents.scout import settings

        mode = settings.mode()
        if mode != "live":
            return f"outreach is in {mode} mode, which sends nothing"
        problems = send.live_problems()
        return f"live sending isn't ready: {problems[0]}" if problems else None

    # What each answer, or silence, does (MC §5.7). Each runs inside the
    # transaction that writes the transition, at most once per request.
    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        self._close(conn, subject, "skipped by Ting Yu")
        message = _message(conn, subject)
        if message is not None:
            lead = db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (message["lead_id"],))
            if lead not in store.FINAL_LEAD_STATUSES:
                store.set_lead_status(conn, [message["lead_id"]], store.DECLINED)

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        self._reopen(conn, self._close(conn, subject, "not approved in time"))

    def on_lapse(self, conn: sqlite3.Connection, subject: str) -> None:
        self._reopen(conn, self._close(conn, subject, "approved but the limits didn't reach it"))

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str | None:
        """Why the email changed or went away, for the card's first line."""
        message = _message(conn, subject)
        if message is None:
            return None
        lead = db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (message["lead_id"],))
        if lead in _LEAD_NOTES:
            return _LEAD_NOTES[lead]
        if message["status"] == "dropped":
            return "dropped by the brand check at send time"
        if message["status"] == "queued":
            return "the email changed"
        return None

    def _close(self, conn: sqlite3.Connection, subject: str, why: str) -> dict | None:
        """Cancel the email if it is still queued; log the hook either way.
        Returns the message, or None when there is none."""
        message = _message(conn, subject)
        if message is None:
            return None
        cancelled = conn.execute(
            "UPDATE outreach_messages SET status = 'cancelled', error = ? WHERE id = ? AND status = 'queued'",
            (why, message["id"]),
        ).rowcount
        log.event(conn, "outreach.approval_closed", {"message": message["id"], "why": why, "cancelled": bool(cancelled)},
                  agent=store.AGENT)
        return message if cancelled else None

    def _reopen(self, conn: sqlite3.Connection, message: dict | None) -> None:
        """The lead stays new: a first email that never went out leaves its
        lead as it was before it was queued."""
        if message is not None and message["kind"] == "first":
            conn.execute("UPDATE leads SET status = 'new', updated_at = ? WHERE id = ? AND status = 'queued'",
                         (timeutil.stamp(), message["lead_id"]))

    # What a card's answer says about a used request (AC-M8.7).
    used_word = "sent"


_LEAD_NOTES = {
    "unsubscribed": "lead unsubscribed",
    "bounced": "lead bounced",
    "complained": "lead complained",
    "replied": "lead replied",
    "suppressed": "address suppressed",
    "do_not_contact": "company on the do-not-contact list",
    store.DECLINED: "lead declined by Ting Yu",
}


def kinds() -> dict[str, OutreachEmail]:
    return {KIND: OutreachEmail()}


# --- requests track capacity (A14) ----------------------------------------------------
#
# These read `approvals` with their own SELECTs, as the one-pager's read model
# does; every write to it goes through the `approvals` module.

_SUBJECT_SQL = "'outreach_message:' || m.id"
# A request that still holds a slot: pending, or approved and not yet claimed.
_LIVE = "a.status IN ('pending', 'approved') AND a.used_at IS NULL"


def live_request(conn: sqlite3.Connection, message: int) -> approvals.Approval | None:
    row = conn.execute(
        f"SELECT a.* FROM approvals a WHERE a.kind = ? AND a.subject = ? AND {_LIVE}", (KIND, subject_of(message))
    ).fetchone()
    return approvals.Approval.from_row(row) if row else None


def open_requests(conn: sqlite3.Connection) -> int:
    """Requests holding a slot today: live, over a message still queued."""
    return db.scalar(
        conn,
        f"SELECT count(*) FROM approvals a JOIN outreach_messages m ON a.subject = {_SUBJECT_SQL} "
        f"WHERE a.kind = ? AND {_LIVE} AND m.status = 'queued'",
        (KIND,),
    ) or 0


def pending_requests(conn: sqlite3.Connection) -> int:
    return db.scalar(
        conn,
        f"SELECT count(*) FROM approvals a JOIN outreach_messages m ON a.subject = {_SUBJECT_SQL} "
        "WHERE a.kind = ? AND a.status = 'pending' AND m.status = 'queued'",
        (KIND,),
    ) or 0


def without_request(conn: sqlite3.Connection) -> list[dict]:
    """Queued emails due today with no request yet: none live, and none
    claimed (a claimed one is retried under its idempotency key, never asked
    about again)."""
    return db.rows(
        conn,
        "SELECT m.* FROM outreach_messages m WHERE m.status = 'queued' AND m.send_after <= ? "
        f"AND NOT EXISTS (SELECT 1 FROM approvals a WHERE a.kind = ? AND a.subject = {_SUBJECT_SQL} "
        f"AND (({_LIVE}) OR a.used_at IS NOT NULL)) ORDER BY m.send_after, m.id",
        (timeutil.today_str(), KIND),
    )


def _open(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every live outreach request: its subject and the reason it was raised for."""
    return conn.execute(f"SELECT a.subject, a.reason FROM approvals a WHERE a.kind = ? AND {_LIVE} ORDER BY a.id", (KIND,)).fetchall()


def raising_problem(conn: sqlite3.Connection) -> str | None:
    """Why no request may be raised now, or None. Shadow mode raises nothing
    (A13), and neither does a live mode that would refuse to send, or a paused
    outreach: a request is raised only for an email that can go out."""
    from jura_growth.agents.outreach import send

    problems = send.live_problems()
    if problems:
        return problems[0]
    paused = pause.is_paused(conn, store.AGENT)
    return f"outreach is paused ({paused})" if paused else None


def raise_due(conn: sqlite3.Connection, *, run_id: int | None = None) -> list[approvals.Approval]:
    """Raise requests for queued emails due today, oldest first, up to today's
    remaining live quota less the requests already open (A14). Safe to call
    from every raising command: it never raises more than there is room for.
    Returns the requests it raised. Post them with `cards.sweep_safely()` once
    the caller's own work has committed."""
    from jura_growth.agents.outreach import send

    if raising_problem(conn):
        return []
    run_id = run_id if run_id is not None else log.current_run_id()
    raised: list[approvals.Approval] = []
    with db.transaction(conn):
        # The next read (A3): an open request whose email was cancelled
        # meanwhile (a reply, an unsubscribe, a skip at send time) is
        # superseded now, so its card says so and its slot frees up; one
        # whose email changed is superseded by a request for the new text.
        for row in _open(conn):
            approvals.request(conn, KIND, row["subject"], reason=row["reason"], run_id=run_id)
        room = send.quota(conn, "live")[0] - open_requests(conn)
        for message in without_request(conn):
            if room <= 0:
                break
            what = "first email" if message["kind"] == "first" else "follow-up"
            request = approvals.request(
                conn, KIND, subject_of(message["id"]), reason=f"{what} to lead {message['lead_id']}, due today", run_id=run_id
            )
            if request is not None and request.status == approvals.PENDING:
                raised.append(request)
                room -= 1
    return raised


def post_cards(conn: sqlite3.Connection) -> int:
    """A12: post new cards and edit changed ones, after the caller's own
    transaction has committed. Shadow mode raises and claims nothing, so
    there is nothing of outreach's to post then; the heartbeat's sweep
    catches every other change."""
    from jura_growth import cards
    from jura_growth.agents.scout import settings

    if settings.mode() != "live":
        return 0
    return cards.sweep_safely(conn)


# --- the claim (A6) ---------------------------------------------------------------------


def claimed(conn: sqlite3.Connection, message: int) -> approvals.Approval | None:
    """The approval an earlier attempt at this email already claimed, if any."""
    row = conn.execute(
        "SELECT * FROM approvals WHERE kind = ? AND subject = ? AND status = 'approved' AND used_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 1",
        (KIND, subject_of(message)),
    ).fetchone()
    return approvals.Approval.from_row(row) if row else None


def still_matches(conn: sqlite3.Connection, record: approvals.Approval) -> bool:
    """A retry sends only what was approved: the content hash is unchanged."""
    content = OutreachEmail().content(conn, record.subject)
    return content is not None and approvals.content_hash(content) == record.content_hash
