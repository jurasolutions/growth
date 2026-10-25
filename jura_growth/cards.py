"""Approval cards in #approvals (MC §4.6 A12, §5.6; ticket 04b).

One message per request, posted after the request's transaction commits by
the sweep (`approvals.post_unposted`), which runs at the end of every raising
command and at the heartbeat. A request is never lost between its commit and
its post: until a card is posted, `approvals.posted_at` stays empty and the
one-pager lists it.

    **A-0412 · outreach email** · decide by Tue 10 Nov, 16:30 SGT · code 3f9a1c
    <the preview's title>
    Why: <the preview's reason, or the request's>
    <the preview's text, as it will go out>
    Answer: Approve / Skip, or /growth approve A-0412

When a request is decided, lapses, is superseded or is used, the same sweep
edits the card's first line in place (edits don't notify). If the edit fails,
one follow-up line posts instead. Each change is edited once.

The rules:

- Only pending requests are posted; a request decided before its card went
  out stays unposted (the one-pager shows its state).
- No `DISCORD_WEBHOOK_APPROVALS` means nothing is posted or saved to the
  outbox: the record waits, and the one-pager lists it as unposted.
- A preview with more than ten files is refused before anything is posted,
  rather than dropping one (AC-M5.5).
- Cards mention nobody and go through `discord.post()`'s masking, with the
  Keychain values loaded first (`privacy.load_for_masking`), because a
  preview carries text another process wrote.
- One sweep at a time, through the `approval-cards` lock; a second sweep that
  finds it held does nothing, and the next one catches up.

The card reads approval state only from `approvals`, never from the kind:
`get()` and `pending()` are plain reads, so the sweep judges no content.
"""

from __future__ import annotations

import sqlite3

from jura_growth import approvals, db, discord, locks, log, privacy, timeutil

CHANNEL = "approvals"
USERNAME = "Jura growth · approvals"
LOCK = "approval-cards"
APPROVER = "Ting Yu"  # the one approver (CONTROL_DISCORD_USER_ID, or his Mac user)
FINAL = ("used", "skipped", "expired", "superseded")


class CardRefused(ValueError):
    """The card can't be built as the kind gave it (more than ten files)."""


# --- the text -------------------------------------------------------------------


def when(stamp: str) -> str:
    """`Tue 10 Nov, 16:30 SGT`."""
    moment = timeutil.parse(stamp).astimezone(timeutil.SGT)
    return f"{moment:%a} {moment.day} {moment:%b}, {moment:%H:%M} SGT"


def _clock(stamp: str | None) -> str:
    return timeutil.parse(stamp).astimezone(timeutil.SGT).strftime("%H:%M") if stamp else "?"


def label(kind: str) -> str:
    return kind.replace("-", " ")


def state(approval: approvals.Approval) -> str:
    """What the card should show: the status, or `used` once claimed."""
    return "used" if approval.used_at else approval.status


def status_line(conn: sqlite3.Connection, approval: approvals.Approval) -> str:
    shown = state(approval)
    if shown == "pending":
        return f"decide by {when(approval.decide_by)} · code {approval.code}"
    if shown in ("approved", "used"):
        line = f"Approved by {APPROVER}, {_clock(approval.decided_at)} SGT"
        return line + (f" · used at {_clock(approval.used_at)} SGT" if shown == "used" else "")
    if shown == "skipped":
        return f"Skipped by {APPROVER}, {_clock(approval.decided_at)} SGT"
    if shown == "expired":
        return f"Expired: {approval.close_reason}"
    successor = db.scalar(conn, "SELECT id FROM approvals WHERE supersedes = ? ORDER BY id DESC LIMIT 1", (approval.number,))
    return f"Superseded: {approval.close_reason}" + (f"; see {approvals.format_id(successor)}" if successor else "")


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


def sweep(conn: sqlite3.Connection) -> int:
    """Post every unposted pending card, then edit every card whose record
    changed since. Returns the number of cards posted."""
    with locks.held(LOCK) as acquired:
        if not acquired:
            return 0
        if not discord.webhook(CHANNEL):
            return 0
        # A preview carries text another process wrote (a draft, a PRD), so
        # every Keychain value is masked too, as for alerts and the digest.
        privacy.load_for_masking(conn)
        posted = _post_unposted(conn)
        _edit_changed(conn)
        return posted


def _post_unposted(conn: sqlite3.Connection) -> int:
    registry = approvals.kinds()
    rows = conn.execute("SELECT * FROM approvals WHERE status = 'pending' AND posted_at IS NULL ORDER BY id").fetchall()
    posted = 0
    for approval in (approvals.Approval.from_row(r) for r in rows):
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
        _mark_posted(conn, approval, registered.agent, result)
        posted += 1
    return posted


def _mark_posted(conn: sqlite3.Connection, approval: approvals.Approval, agent: str, result: discord.PostResult) -> None:
    at = timeutil.stamp()
    message_id = result.message_ids[0] if result.message_ids else None
    first_piece = result.pieces[0] if result.pieces else ""
    with db.transaction(conn):
        conn.execute(
            "UPDATE approvals SET posted_at = ?, message_id = ? WHERE id = ? AND posted_at IS NULL AND used_at IS NULL",
            (at, message_id, approval.number),
        )
        conn.execute(
            "INSERT OR IGNORE INTO approval_cards (approval_id, message_id, first_piece, shows, posted_at) VALUES (?, ?, ?, 'pending', ?)",
            (approval.number, message_id, first_piece, at),
        )
        log.event(conn, "approval.posted", {"approval": approval.id, "kind": approval.kind, "subject": approval.subject,
                                            "hash": approval.content_hash, "message_id": message_id, "at": at}, agent=agent)


def _edit_changed(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT c.message_id AS card_message, c.first_piece, c.shows, a.* FROM approval_cards c "
        "JOIN approvals a ON a.id = c.approval_id WHERE c.shows IN ('pending', 'approved') ORDER BY a.id"
    ).fetchall()
    edited = 0
    for row in rows:
        approval = approvals.Approval.from_row(row)
        now_shows = state(approval)
        if now_shows == row["shows"]:
            continue
        line = header(conn, approval)
        rest = row["first_piece"].split("\n", 1)
        content = line + ("\n" + rest[1] if len(rest) > 1 else "")
        done = row["card_message"] and discord.edit(conn, CHANNEL, row["card_message"], content).delivered
        if not done:
            follow_up = f"{approval.id}: {status_line(conn, approval)} (the card couldn't be edited)."
            discord.post(conn, CHANNEL, follow_up, username=USERNAME, dedupe=False, suppress_embeds=True)
        conn.execute(
            "UPDATE approval_cards SET shows = ?, updated_at = ? WHERE approval_id = ?",
            (now_shows, timeutil.stamp(), approval.number),
        )
        edited += 1
    return edited
