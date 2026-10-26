"""Publish items: creating them and writing their lifecycle (browser publishing PRD §5.4).

An item's lifecycle is its own and never a copy of the decision (MC §4.6 A2): `ready`, `claimed`,
`done`, `stopped`, `unknown` or `withdrawn`. Whether its request is pending, approved, skipped or
expired is read from `approvals`. The subject of an item's requests is `publish_item:<id>`;
Ting Yu only ever sees and types the request's `A-nnnn`, with `P-nnnn` as a label beside it.

A social item is raised by `social submit` for each platform in `browser` mode whose variant
passed the brand gate (`create_social`), and only while its decide-by, the end of the posting
window on its day, is still ahead. Drafts written before a platform moved to `browser` never get
one: items are made only at submit.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, fields
from datetime import date

from jura_growth import approvals, db, log, timeutil
from jura_growth.agents.publish import hosts, limits

AGENT = "publish"
SOCIAL_ITEM = "social_post"  # publish_items.kind; its approval kind is SOCIAL_KIND
SOCIAL_KIND = "social-post"
_SUBJECT = re.compile(r"publish_item:([0-9]+)")
OPEN = ("ready", "claimed")


@dataclass(frozen=True)
class Item:
    id: int
    label: str
    kind: str
    platform: str
    ref: str
    parent_item: int | None
    target_url: str
    posting_identity: str
    content_json: str
    day: str
    state: str
    outcome: str | None
    stop_reason: str | None
    post_url: str | None
    live_text_hash: str | None
    live_text_matches: int | None
    run_id: int | None
    created_at: str
    claimed_at: str | None
    finished_at: str | None

    @property
    def subject(self) -> str:
        return subject_of(self.id)

    @property
    def ref_id(self) -> int:
        return int(self.ref)

    @property
    def content(self) -> dict:
        return json.loads(self.content_json)

    @classmethod
    def from_row(cls, row) -> "Item":
        row = dict(row)
        return cls(**{f.name: row[f.name] for f in fields(cls)})


@dataclass(frozen=True)
class Made:
    """What `create_social` did: the item and its request, or why there is none."""

    item: Item | None = None
    approval: approvals.Approval | None = None
    why: str = ""


def subject_of(item_id: int) -> str:
    return f"publish_item:{int(item_id)}"


def item_id(subject: str) -> int | None:
    match = _SUBJECT.fullmatch(subject or "")
    return int(match.group(1)) if match else None


def get(conn: sqlite3.Connection, number: int) -> Item | None:
    row = conn.execute("SELECT * FROM publish_items WHERE id = ?", (number,)).fetchone()
    return Item.from_row(row) if row else None


def of(conn: sqlite3.Connection, subject: str) -> Item | None:
    number = item_id(subject)
    return get(conn, number) if number is not None else None


def latest_request(conn: sqlite3.Connection, item: Item) -> approvals.Approval | None:
    """The newest request over `item` (a plain read of `approvals`)."""
    row = conn.execute(
        "SELECT * FROM approvals WHERE subject = ? ORDER BY id DESC LIMIT 1", (item.subject,)
    ).fetchone()
    return approvals.Approval.from_row(row) if row else None


def claimed_request(conn: sqlite3.Connection, item: Item) -> approvals.Approval | None:
    row = conn.execute(
        "SELECT * FROM approvals WHERE subject = ? AND used_at IS NOT NULL ORDER BY id DESC LIMIT 1", (item.subject,)
    ).fetchone()
    return approvals.Approval.from_row(row) if row else None


# --- creating -------------------------------------------------------------------------------


def create_social(conn: sqlite3.Connection, post_id: int, *, run_id: int | None, request: bool = True) -> Made:
    """The item and its `social-post` request for one `social_posts` draft, or why not.

    Runs in its own transaction, or inside the caller's. Post the card with
    `cards.sweep_safely()` once that has committed (MC §4.6 A12). With `request=False` the
    item is made without its request, which `raise_request()` raises later."""
    from jura_growth.agents.publish import kinds
    from jura_growth.agents.social.settings import load

    post = db.one(conn, "SELECT * FROM social_posts WHERE id = ?", (post_id,))
    if post is None:
        return Made(why=f"there is no social draft {post_id}")
    platform = load().platforms[post["platform"]]
    if not platform.browser:
        return Made(why=f"{platform.name} is in draft mode")
    if not platform.page_url:
        return Made(why=f"{platform.name} is in browser mode but its page_url isn't set in config/social.yaml")
    wrong = hosts.problem(platform.name, platform.page_url)
    if wrong:
        return Made(why=f"{platform.name}'s page_url won't do: {wrong}")
    day = date.fromisoformat(post["date"])
    _, closes = limits.window_on(day)
    if timeutil.now_sgt() >= closes:
        return Made(why=f"the posting window for {day} has closed ({closes:%H:%M} SGT)")
    content = kinds.social_content(conn, post_id)
    if content is None:
        return Made(why=f"the {platform.name} draft for {day} can't be posted now (skipped, posted or missing an image)")
    with db.atomic(conn):
        cursor = conn.execute(
            "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, created_at)"
            " VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?)",
            (SOCIAL_ITEM, platform.name, str(post_id), content["target_url"], content["posting_identity"],
             json.dumps(content, ensure_ascii=False, sort_keys=True), post["date"], timeutil.stamp()),
        )
        number = int(cursor.lastrowid or 0)
        conn.execute("UPDATE publish_items SET label = ? WHERE id = ?", (label_of(number), number))
        log.event(conn, "publish.item_created", {"item": label_of(number), "kind": SOCIAL_ITEM, "platform": platform.name,
                                                  "day": post["date"]}, agent=AGENT, run_id=run_id)
        item = get(conn, number)
        assert item is not None  # inserted above, in this transaction
        approval = raise_request(conn, item, run_id=run_id) if request else None
    return Made(item, approval)


def raise_request(conn: sqlite3.Connection, item: Item, *, run_id: int | None) -> approvals.Approval | None:
    """The item's request (A11: raised only by the commands that make items)."""
    from jura_growth.agents.social.settings import load

    label = load().platforms[item.platform].label
    return approvals.request(conn, SOCIAL_KIND, item.subject, reason=f"the {label} post for {item.day}", run_id=run_id)


def label_of(number: int) -> str:
    return f"P-{number:04d}"


def stale_claim(conn: sqlite3.Connection, item: Item) -> bool:
    """A claim no run will close: claimed in Terminal (no run), or by a run that has ended."""
    if item.state != "claimed":
        return False
    if item.run_id is None:
        return True
    status = db.scalar(conn, "SELECT status FROM runs WHERE id = ?", (item.run_id,))
    return status != "running"


# --- the lifecycle ----------------------------------------------------------------------------


def withdraw(conn: sqlite3.Connection, item: Item, why: str) -> bool:
    """`ready` to `withdrawn` (skipped, lapsed or superseded). False if it wasn't ready."""
    changed = conn.execute(
        "UPDATE publish_items SET state = 'withdrawn', finished_at = ? WHERE id = ? AND state = 'ready'",
        (timeutil.stamp(), item.id),
    ).rowcount
    if changed:
        log.event(conn, "publish.item_withdrawn", {"item": item.label, "why": why}, agent=AGENT)
    return bool(changed)


def refreeze(conn: sqlite3.Connection, item: Item, content: dict) -> None:
    """Freeze `content` into the item: the content its live request now covers."""
    conn.execute(
        "UPDATE publish_items SET day = ?, target_url = ?, posting_identity = ?, content_json = ? WHERE id = ?",
        (content["day"], content["target_url"], content["posting_identity"],
         json.dumps(content, ensure_ascii=False, sort_keys=True), item.id),
    )


def sync(conn: sqlite3.Connection, *, run_id: int | None = None) -> list[approvals.Approval]:
    """Bring every ready item in line with its requests, and return the requests it raised.

    - A live request that still matches, over content that differs from the item's frozen copy
      (the core raised it over new content): the new content is frozen into the item.
    - A live request that no longer matches: it is superseded and the new card raised in this
      same sync (`approvals.request` does both), with the new content frozen into the item.
    - A request superseded because the post changed (by `expire_due()`, which raises nothing),
      or because it went and came back: a request is raised over the content as it is now, so
      a change never leaves Ting Yu without a card (A3, AC-P1.3). Only when that content's
      posting window has already closed is the item withdrawn instead.
    - A request skipped or expired, or superseded because the draft is gone (skipped or posted
      by hand): the item is withdrawn.

    Call it inside the caller's transaction; post the raised cards with `cards.sweep_safely()`
    once that has committed."""
    from jura_growth.agents.publish import kinds

    raised: list[approvals.Approval] = []
    for row in conn.execute("SELECT * FROM publish_items WHERE state = 'ready' ORDER BY id").fetchall():
        item = Item.from_row(row)
        latest = latest_request(conn, item)
        if latest is None or latest.used_at:
            continue  # not yet raised, or claimed
        content = kinds.social_content(conn, item.ref_id)
        digest = approvals.content_hash(kinds.hashed(content)) if content is not None else None
        in_time = content is not None and timeutil.now_sgt() < limits.window_on(date.fromisoformat(content["day"]))[1]
        if latest.live:
            if content is not None and digest == latest.content_hash:
                if content != item.content:
                    refreeze(conn, item, content)
                continue
            if content is not None and not in_time:
                continue  # too late for a new card: `use()` and the lapses close the old one
            # The post changed (or went) under a live request: supersede it now and raise the
            # new card in this same sync, not at the next transition (code review 02, R2-S1).
            if content is not None:
                refreeze(conn, item, content)
            fresh = raise_request(conn, item, run_id=run_id)
            if fresh is not None and fresh.live:
                raised.append(fresh)
                continue
            latest = latest_request(conn, item) or latest
        elif latest.status == approvals.SUPERSEDED and content is not None and in_time:
            # Changed, or gone and back again unchanged (R2-N1): either way it needs a live card.
            refreeze(conn, item, content)
            fresh = raise_request(conn, item, run_id=run_id)
            if fresh is not None and fresh.live:
                raised.append(fresh)
                continue
        withdraw(conn, item, latest.status)
    return raised
