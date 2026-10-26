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

    def deadlines(self, conn: sqlite3.Connection | None, subject: str, now: datetime) -> approvals.Deadlines:
        today = now.astimezone(timeutil.SGT).date()
        decide = approval_settings.deadline(KIND, "decide_by_business_days")
        use = approval_settings.deadline(KIND, "use_by_business_days")
        return approvals.Deadlines(
            decide_by=_at_cutoff(store.add_business_days(today, decide)),
            use_by=_at_cutoff(store.add_business_days(today, use)),
        )


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
