"""The claim: every check before an item goes to a browser run (browser publishing PRD §4.4, §4.5).

`next_item()` is what `publish next` runs. Inside one `BEGIN IMMEDIATE` transaction it
re-checks everything and claims at most one item: the approval is claimed with
`approvals.use()` (`used_at` and `used_by_run` set, MC §4.6 A6) and the item becomes `claimed`
in the same transaction, which commits before the command prints anything. Its images are
copied into the run's scratch folder and checked against the approved bytes inside that
transaction too, so a copy that doesn't match leaves nothing claimed.

The checks, in order:

1. Kill switches: the PAUSE file, `pause publish` or `pause all` (which auto-pause sets too).
2. Items whose day has passed, or whose posting window has closed, are judged by `use()`, which
   writes their expiry; none is claimed.
3. The posting window (09:00 to 18:00 SGT, `limits.window()`).
4. One item per run (`caps.PUBLISH_ITEMS_PER_RUN`).
5. The gap: 20 minutes between the start times of the runs that claimed two items
   (`caps.PUBLISH_MINUTES_BETWEEN_ACTIONS`).
6. Per item: its day is today, its platform has no claimed item yet today
   (`caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY`), and `use()` agrees: approved, before its use-by,
   unused, its content unchanged, and its platform in `browser` mode.

A cap counts an item from its claim, whatever happens next, so a stopped or unknown item still
uses its platform's day (AC-P5.2).

`claimable(conn, now)` answers the same question read-only, for the publish job's precheck
(BP-03): it never writes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from jura_growth import approvals, caps, db, log, paths, pause, timeutil
from jura_growth.agents.publish import items, kinds, limits

NOTHING_DUE = "nothing due"


@dataclass
class Claim:
    """What `next_item()` handed out, or why nothing (`why`, one line per reason)."""

    item: items.Item | None = None
    approval: approvals.Approval | None = None
    images: list[Path] = field(default_factory=list)
    why: list[str] = field(default_factory=list)


class CopyFailed(RuntimeError):
    """An image copied to the scratch folder doesn't match the approved bytes."""


# --- reading ----------------------------------------------------------------------------------


def _ready(conn: sqlite3.Connection, today: str) -> list[items.Item]:
    rows = conn.execute(
        "SELECT * FROM publish_items WHERE state = 'ready' AND day <= ? ORDER BY day, id", (today,)
    ).fetchall()
    return [items.Item.from_row(r) for r in rows]


def _run_start(conn: sqlite3.Connection, run_id: int | None, now: datetime) -> datetime:
    started = db.scalar(conn, "SELECT started_at FROM runs WHERE id = ?", (run_id,)) if run_id else None
    return timeutil.parse(started) if started else now


def _gap_problem(conn: sqlite3.Connection, start: datetime) -> str | None:
    last = db.one(
        conn,
        "SELECT p.claimed_at, r.started_at FROM publish_items p LEFT JOIN runs r ON r.id = p.run_id "
        "WHERE p.claimed_at IS NOT NULL ORDER BY p.claimed_at DESC, p.id DESC LIMIT 1",
    )
    if last is None:
        return None
    previous = timeutil.parse(last["started_at"] or last["claimed_at"])
    gap = timedelta(minutes=limits.minutes_between_actions())
    if start - previous < gap:
        return (f"the last item was claimed by a run that started at {previous.astimezone(timeutil.SGT):%H:%M} SGT; "
                f"the next may start from {(previous + gap).astimezone(timeutil.SGT):%H:%M}")
    return None


def _per_run_problem(conn: sqlite3.Connection, run_id: int | None) -> str | None:
    if run_id is None:
        return None
    claimed = db.scalar(conn, "SELECT count(*) FROM publish_items WHERE run_id = ? AND claimed_at IS NOT NULL", (run_id,)) or 0
    if claimed >= limits.items_per_run():
        return f"this run has already claimed its {limits.items_per_run()} item"
    return None


def _item_problem(conn: sqlite3.Connection, item: items.Item, today: str) -> str | None:
    if item.day != today:
        return f"{item.label} is for {item.day}"
    if item.kind == items.SOCIAL:
        used = db.scalar(
            conn,
            "SELECT count(*) FROM publish_items WHERE kind = ? AND platform = ? AND day = ? AND claimed_at IS NOT NULL",
            (items.SOCIAL, item.platform, item.day),
        ) or 0
        if used >= caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY:
            return f"{item.platform} already had its post claimed for {item.day}"
    return None


def _past(item: items.Item, now: datetime) -> bool:
    _, closes = limits.window_on(datetime.fromisoformat(item.day).date())
    return now >= closes


def _name(item: items.Item) -> str:
    return f"{item.label} ({item.platform}, {item.day})"


def _blocked(conn: sqlite3.Connection) -> str | None:
    paused = pause.is_paused(conn, items.AGENT)
    return f"publish is paused ({paused})" if paused else None


# --- the claim -------------------------------------------------------------------------------


def next_item(conn: sqlite3.Connection, *, run_id: int | None = None, now: datetime | None = None) -> Claim:
    """Claim at most one item, or say why nothing is due. See the module docstring."""
    now = now or timeutil.now_sgt()
    blocked = _blocked(conn)
    if blocked:
        return Claim(why=[blocked])
    today = now.astimezone(timeutil.SGT).date().isoformat()
    why: list[str] = []
    with db.transaction(conn):
        candidates = []
        for item in _ready(conn, today):
            if item.day < today or _past(item, now):
                # Past its deadline: `use()` refuses it and writes the expiry (A5, A17).
                try:
                    approvals.use(conn, kinds.KIND, item.subject, run_id=run_id)
                except approvals.NotApproved as refusal:
                    why.append(f"{_name(item)}: {refusal.text}")
                    continue
                raise RuntimeError(f"{item.label} was claimed after its deadline")  # rolls back
            candidates.append(item)
        items.sync(conn)
        general = None
        if not limits.in_window(now):
            start, end = limits.window()
            general = f"outside the posting window ({start:%H:%M} to {end:%H:%M} SGT)"
        general = general or _per_run_problem(conn, run_id) or _gap_problem(conn, _run_start(conn, run_id, now))
        if general:
            return Claim(why=[general, *why])
        for item in candidates:
            problem = _item_problem(conn, item, today)
            if problem:
                why.append(f"{_name(item)}: {problem}")
                continue
            try:
                approval = approvals.use(conn, kinds.KIND, item.subject, run_id=run_id)
            except approvals.NotApproved as refusal:
                why.append(f"{_name(item)}: {refusal.text}")
                continue
            content = kinds.social_content(conn, item.ref_id)
            if content is None:  # use() matched the content a moment ago in this transaction
                raise RuntimeError(f"{item.label}'s content vanished inside its claim")
            copies = _copy_images(content, approval)
            stamp = timeutil.stamp(now)
            conn.execute(
                "UPDATE publish_items SET state = 'claimed', run_id = ?, claimed_at = ?, content_json = ? WHERE id = ? "
                "AND state = 'ready'",
                (run_id, stamp, json.dumps({**content, "copies": [str(c) for c in copies]}, ensure_ascii=False,
                                           sort_keys=True), item.id),
            )
            log.event(conn, "publish.claimed", {"item": item.label, "approval": approval.id, "platform": item.platform,
                                                 "day": item.day}, agent=items.AGENT, run_id=run_id)
            return Claim(items.get(conn, item.id), approval, copies)
    return Claim(why=why or ["no item is waiting"])


def _copy_images(content: dict, approval: approvals.Approval) -> list[Path]:
    """Copy the approved images, in order, into the run's scratch folder, and check each copy's
    bytes against the approved hash. A mismatch raises, which rolls the claim back."""
    folder = paths.work_dir("publish") / approval.id
    copies = []
    for number, image in enumerate(content["images"], start=1):
        source = Path(image["path"])
        target = paths.writable(folder / f"{number}-{source.name}")
        shutil.copyfile(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != image["sha256"]:
            raise CopyFailed(f"{target.name} doesn't match the approved image")
        copies.append(target)
    return copies


# --- read-only ------------------------------------------------------------------------------


def claimable(conn: sqlite3.Connection, now: datetime | None = None, *, run_start: datetime | None = None) -> list[items.Item]:
    """The items `next_item()` could claim now, judged without writing anything: the precheck
    for the publish job (BP-03). Approval states are read as they stand, deadlines by growth's
    clock, and the content compared through the kind."""
    now = now or timeutil.now_sgt()
    if _blocked(conn) or not limits.in_window(now):
        return []
    if _gap_problem(conn, run_start or now):
        return []
    today = now.astimezone(timeutil.SGT).date().isoformat()
    kind = kinds.SocialPost()
    found = []
    for item in _ready(conn, today):
        if _past(item, now) or _item_problem(conn, item, today) or kind.switched_off(conn, item.subject):
            continue
        record = conn.execute(
            "SELECT * FROM approvals WHERE kind = ? AND subject = ? AND status = 'approved' AND used_at IS NULL",
            (kinds.KIND, item.subject),
        ).fetchone()
        if record is None:
            continue
        approval = approvals.Approval.from_row(record)
        content = kind.content(conn, item.subject)
        if approval.use_by and now >= timeutil.parse(approval.use_by):
            continue
        if content is None or approvals.content_hash(content) != approval.content_hash:
            continue
        found.append(item)
    return found
