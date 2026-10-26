"""The claim: every check before an item goes to a browser run (browser publishing PRD §4.4, §4.5).

`next_item()` is what `publish next` runs. Inside one `BEGIN IMMEDIATE` transaction it
re-checks everything and claims at most one item: the approval is claimed with
`approvals.use()` (`used_at` and `used_by_run` set, MC §4.6 A6) and the item becomes `claimed`
in the same transaction, which commits before the command prints anything. Inside that
transaction the claim then reads the draft's text and every image once, hashes exactly those
bytes, and refuses (rolling the claim back) unless the hash is the approval's own. The bytes it
hands out, the text printed and the image copies written to the run's scratch folder, are those
same bytes, so nothing Ting Yu didn't approve can be handed out, even if a file changes after
`use()` read it (code review 02, B2).

Before any of that, `items.sync()` brings every ready item in line with its requests: a post that
changed gets its new request and card (AC-P1.3), and one that is gone is withdrawn.

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

`claimable(conn, now)` answers the same question for the publish job's precheck (BP-03) by
running the very same steps, `use()` included, in a transaction it always rolls back: nothing is
written, and the answer can't drift from the real gate.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
    if item.kind == items.SOCIAL_ITEM:
        used = db.scalar(
            conn,
            "SELECT count(*) FROM publish_items WHERE kind = ? AND platform = ? AND day = ? AND claimed_at IS NOT NULL",
            (items.SOCIAL_ITEM, item.platform, item.day),
        ) or 0
        if used >= caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY:
            return f"{item.platform} already had its post claimed for {item.day}"
    return None


def _past(item: items.Item, now: datetime) -> bool:
    _, closes = limits.window_on(date.fromisoformat(item.day))
    return now >= closes


def _name(item: items.Item) -> str:
    return f"{item.label} ({item.platform}, {item.day})"


def _blocked(conn: sqlite3.Connection) -> str | None:
    paused = pause.is_paused(conn, items.AGENT)
    return f"publish is paused ({paused})" if paused else None


# --- the claim -------------------------------------------------------------------------------


class _DryRun(Exception):
    """Rolls `claimable()`'s transaction back, carrying what it found."""

    def __init__(self, found: "Claim"):
        super().__init__("dry run")
        self.found = found


def next_item(conn: sqlite3.Connection, *, run_id: int | None = None, now: datetime | None = None) -> Claim:
    """Claim at most one item, or say why nothing is due. See the module docstring. Post any card
    `items.sync()` raised with `cards.sweep_safely()` afterwards (the command does)."""
    now = now or timeutil.now_sgt()
    blocked = _blocked(conn)
    if blocked:
        return Claim(why=[blocked])
    try:
        with db.transaction(conn):
            return _select(conn, now, run_id, _run_start(conn, run_id, now), hand_out=True)
    except CopyFailed as refusal:  # rolled back: nothing claimed
        log.event(conn, "publish.claim_refused", {"why": str(refusal)}, level="warning", agent=items.AGENT, run_id=run_id)
        return Claim(why=[str(refusal)])


def claimable(conn: sqlite3.Connection, now: datetime | None = None, *, run_id: int | None = None,
              run_start: datetime | None = None) -> list[items.Item]:
    """The item `next_item()` would claim now, if any, found by running its very steps in a
    transaction that is always rolled back: nothing is written or posted."""
    now = now or timeutil.now_sgt()
    if _blocked(conn):
        return []
    try:
        with db.transaction(conn):
            raise _DryRun(_select(conn, now, run_id, run_start or _run_start(conn, run_id, now), hand_out=False))
    except _DryRun as dry:
        return [dry.found.item] if dry.found.item is not None else []
    except CopyFailed:
        return []


def _select(conn: sqlite3.Connection, now: datetime, run_id: int | None, run_start: datetime, *, hand_out: bool) -> Claim:
    """Every check and the claim, inside the caller's transaction."""
    today = now.astimezone(timeutil.SGT).date().isoformat()
    why: list[str] = []
    items.sync(conn, run_id=run_id)
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
    general = None
    if not limits.in_window(now):
        start, end = limits.window()
        general = f"outside the posting window ({start:%H:%M} to {end:%H:%M} SGT)"
    general = general or _per_run_problem(conn, run_id) or _gap_problem(conn, run_start)
    if general:
        items.sync(conn, run_id=run_id)
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
        return _hand_out(conn, item, approval, run_id, now, write_copies=hand_out)
    items.sync(conn, run_id=run_id)  # freeze any request `use()` just raised over new content
    return Claim(why=why or ["no item is waiting"])


def _hand_out(conn: sqlite3.Connection, item: items.Item, approval: approvals.Approval, run_id: int | None,
              now: datetime, *, write_copies: bool) -> Claim:
    """Read the draft once, check exactly those bytes against the approval's hash, and hand
    out those bytes. A mismatch raises `CopyFailed`, which rolls the claim back."""
    found = kinds.read_social(conn, item.ref_id)
    if found is None or approvals.content_hash(kinds.hashed(found.content)) != approval.content_hash:
        raise CopyFailed(f"{item.label}'s post changed while it was being claimed; nothing was handed out")
    copies = _copy_images(found, approval) if write_copies else []
    conn.execute(
        "UPDATE publish_items SET state = 'claimed', run_id = ?, claimed_at = ?, content_json = ? WHERE id = ? "
        "AND state = 'ready'",
        (run_id, timeutil.stamp(now), json.dumps({**found.content, "copies": [str(c) for c in copies]},
                                                 ensure_ascii=False, sort_keys=True), item.id),
    )
    log.event(conn, "publish.claimed", {"item": item.label, "approval": approval.id, "platform": item.platform,
                                         "day": item.day}, agent=items.AGENT, run_id=run_id)
    return Claim(items.get(conn, item.id), approval, copies)


def _copy_images(found: kinds.Read, approval: approvals.Approval) -> list[Path]:
    """Write the checked bytes, in order, into the run's scratch folder, and read each copy back
    to make sure it holds them."""
    folder = paths.work_dir("publish") / approval.id
    copies = []
    for number, (image, blob) in enumerate(zip(found.content["images"], found.blobs), start=1):
        target = paths.writable(folder / f"{number}-{Path(image['path']).name}")
        target.write_bytes(blob)
        if hashlib.sha256(target.read_bytes()).hexdigest() != image["sha256"]:
            raise CopyFailed(f"{target.name} doesn't hold the approved image")
        copies.append(target)
    return copies
