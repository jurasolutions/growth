"""Approval cards in #approvals (MC §4.6 A12, §5.6; ticket 04b).

One message per request, posted after the request's transaction commits.
`sweep()` is A12's `post_unposted`: the heartbeat runs it, and so does every
raising command when it ends (tickets 05, 06, 10 and browser publishing call
`sweep_safely()` there). A request is never lost between its commit and its
post: until a card is posted, `approvals.posted_at` stays empty and the
one-pager lists it.

    **A-0412 · outreach email** · decide by Tue 10 Nov, 16:30 SGT
    <the preview's title>
    Why: <the preview's reason, or the request's>
    <the preview's text, as it will go out>
    Answer: Approve / Skip, or /growth approve A-0412

When a request is decided, lapses, is superseded or is claimed, the sweep
edits the card's first line in place (edits don't notify). If the edit fails,
one follow-up line posts instead. Each change is edited once. Decisions come
only from #approvals through Dispatch, so a card carries no code to type.

The rules:

- Only pending requests are posted (`approvals.unposted()`); a request
  decided before its card went out never gets one.
- No `DISCORD_WEBHOOK_APPROVALS` means nothing is posted or saved to the
  outbox: the record waits, and the one-pager lists it as unposted.
- A preview with more than ten files is refused before anything is posted,
  rather than dropping one (AC-M5.5).
- Cards mention nobody and go through `discord.post()`'s masking, with the
  Keychain values loaded first (`privacy.load_for_masking`), because a
  preview carries text another process wrote.
- One sweep at a time, through the `approval-cards` lock; a second sweep that
  finds it held does nothing, and the next one catches up.

Approval state is read from and written to `approvals` through its own
functions (`unposted`, `mark_posted`, `successor`); this module keeps only
`approval_cards`, what each card shows now. The sweep judges no content.
"""

from __future__ import annotations

import sqlite3

from jura_growth import approvals, db, discord, locks, log, privacy, timeutil

CHANNEL = "approvals"
USERNAME = "Jura growth · approvals"
LOCK = "approval-cards"
APPROVER = "Ting Yu"  # the one approver: CONTROL_DISCORD_USER_ID
# What a card can show: a record's status, or CLAIMED once it is used.
CLAIMED = "used"
_OPEN = (approvals.PENDING, approvals.APPROVED)  # cards that can still change


class CardRefused(ValueError):
    """The card can't be built as the kind gave it (more than ten files)."""


# --- the text -------------------------------------------------------------------


def when(stamp: str) -> str:
    """`Tue 10 Nov, 16:30 SGT`."""
    return when_at(timeutil.parse(stamp))


def when_at(moment) -> str:
    moment = moment.astimezone(timeutil.SGT)
    return f"{moment:%a} {moment.day} {moment:%b}, {moment:%H:%M} SGT"


def _clock(stamp: str | None) -> str:
    return timeutil.parse(stamp).astimezone(timeutil.SGT).strftime("%H:%M") if stamp else "?"


def label(kind: str) -> str:
    return kind.replace("-", " ")


def state(approval: approvals.Approval) -> str:
    """What the card should show: the status, or `CLAIMED` once used."""
    return CLAIMED if approval.used_at else approval.status


def status_line(conn: sqlite3.Connection, approval: approvals.Approval) -> str:
    shown = state(approval)
    if shown == approvals.PENDING:
        return f"decide by {when(approval.decide_by)}"
    if shown in (approvals.APPROVED, CLAIMED):
        line = f"Approved by {APPROVER}, {_clock(approval.decided_at)} SGT"
        return line + (f" · claimed at {_clock(approval.used_at)} SGT" if shown == CLAIMED else "")
    if shown == approvals.SKIPPED:
        return f"Skipped by {APPROVER}, {_clock(approval.decided_at)} SGT"
    if shown == approvals.EXPIRED:
        return f"Expired: {approval.close_reason}"
    newer = approvals.successor(conn, approval)
    return f"Superseded: {_superseded_note(conn, approval)}" + (f"; see {newer.id}" if newer else "")


def _superseded_note(conn: sqlite3.Connection, approval: approvals.Approval) -> str:
    """The kind's own words for why its item changed (`superseded_note`), or
    the core's reason. A failing hook falls back to the core's reason."""
    registered = approvals.kinds().get(approval.kind)
    hook = getattr(registered.kind, "superseded_note", None) if registered else None
    if hook is not None:
        try:
            note = hook(conn, approval.subject)
        except Exception as error:  # noqa: BLE001 - a card edit never fails on a kind's wording
            log.event(conn, "approval.card_note_error", {"approval": approval.id, "error": f"{type(error).__name__}: {error}"},
                      level="warning", agent=registered.agent if registered else None)
            note = None
        if note:
            return note
    return approval.close_reason or "the item changed"


def header(conn: sqlite3.Connection, approval: approvals.Approval) -> str:
    return f"**{approval.id} · {label(approval.kind)}** · {status_line(conn, approval)}"


def answer_line(approval: approvals.Approval, kind: approvals.ApprovalKind) -> str:
    wanted: tuple[str, ...] = tuple(getattr(kind, "decision_args", None) or ())
    if wanted:
        typed = " ".join(f"{name}=…" for name in wanted)
        return f"Answer: /growth approve {approval.id} {typed}, or /growth skip {approval.id}"
    return f"Answer: Approve / Skip, or /growth approve {approval.id}"


def build(conn: sqlite3.Connection, approval: approvals.Approval, kind: approvals.ApprovalKind) -> tuple[str, list]:
    """The card's text and files. Raises `CardRefused` for more than ten files."""
    preview = kind.preview(conn, approval.subject)
    files = list(preview.files or ())
    if len(files) > discord.MAX_FILES:
        raise CardRefused(f"the preview has {len(files)} files and a card takes at most {discord.MAX_FILES}")
    lines = [header(conn, approval)]
    if preview.title:
        lines.append(preview.title)
    lines.append(f"Why: {preview.reason or approval.reason}")
    if preview.text:
        lines.append(preview.text)
    lines.append(answer_line(approval, kind))
    return "\n".join(lines), files


# --- the sweep ------------------------------------------------------------------


def sweep(conn: sqlite3.Connection, *, post: bool = True) -> int:
    """Post every unposted pending card (unless `post` is False), then edit
    every card whose record changed since. Run it after the transaction that
    raised or changed the records has committed. Returns the cards posted."""
    with locks.held(LOCK) as acquired:
        if not acquired:
            return 0
        if not discord.webhook(CHANNEL):
            return 0
        privacy.load_for_masking(conn)
        posted = _post_unposted(conn) if post else 0
        _edit_changed(conn)
        return posted


def sweep_safely(conn: sqlite3.Connection, *, post: bool = True) -> int:
    """`sweep()` for a caller whose own work must stand whatever happens to
    the cards: an error is logged as `approval.cards_error`, never raised."""
    try:
        return sweep(conn, post=post)
    except Exception as error:  # noqa: BLE001
        log.event(conn, "approval.cards_error", {"error": f"{type(error).__name__}: {error}"}, level="error")
        return 0


def _post_unposted(conn: sqlite3.Connection) -> int:
    registry = approvals.kinds()
    posted = 0
    for approval in approvals.unposted(conn):
        registered = registry.get(approval.kind)
        if registered is None:
            continue  # its plug-in isn't loaded; the one-pager lists it as unposted
        try:
            content, files = build(conn, approval, registered.kind)
        except Exception as error:  # noqa: BLE001 - one bad preview never holds up the rest
            why = str(error) if isinstance(error, CardRefused) else f"{type(error).__name__}: {error}"
            log.event(conn, "approval.card_refused", {"approval": approval.id, "kind": approval.kind, "why": why},
                      level="warning", agent=registered.agent)
            continue
        result = discord.post(conn, CHANNEL, content, files=files, username=USERNAME, dedupe=False,
                              suppress_embeds=True, wait=True)
        if not result.delivered:
            continue  # saved to the outbox by post(); the next sweep posts it again
        message_id = result.message_ids[0] if result.message_ids else None
        with db.transaction(conn):
            approvals.mark_posted(conn, approval, message_id)
            conn.execute(
                "INSERT OR IGNORE INTO approval_cards (approval_id, message_id, first_piece, shows, posted_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (approval.number, message_id, result.pieces[0] if result.pieces else "", approvals.PENDING, timeutil.stamp()),
            )
        posted += 1
    return posted


def _edit_changed(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT c.approval_id, c.message_id, c.first_piece, c.shows FROM approval_cards c "
        f"WHERE c.shows IN ({', '.join('?' for _ in _OPEN)}) ORDER BY c.approval_id",
        _OPEN,
    ).fetchall()
    edited = 0
    for row in rows:
        approval = approvals.get(conn, approvals.format_id(row["approval_id"]))
        if approval is None:
            continue
        now_shows = state(approval)
        if now_shows == row["shows"]:
            continue
        rest = row["first_piece"].split("\n", 1)
        content = header(conn, approval) + ("\n" + rest[1] if len(rest) > 1 else "")
        done = row["message_id"] and discord.edit(conn, CHANNEL, row["message_id"], content).delivered
        if not done:
            follow_up = f"{approval.id}: {status_line(conn, approval)} (the card couldn't be edited)."
            discord.post(conn, CHANNEL, follow_up, username=USERNAME, dedupe=False, suppress_embeds=True)
        conn.execute(
            "UPDATE approval_cards SET shows = ?, updated_at = ? WHERE approval_id = ?",
            (now_shows, timeutil.stamp(), approval.number),
        )
        edited += 1
    return edited
