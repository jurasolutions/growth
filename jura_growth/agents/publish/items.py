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

from jura_growth import approvals, db, log, timeutil
from jura_growth.agents.publish import hosts, limits

AGENT = "publish"
SOCIAL = "social_post"
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
    day = timeutil.parse(post["date"] + "T00:00:00").date()
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
            (SOCIAL, platform.name, str(post_id), content["target_url"], content["posting_identity"],
             json.dumps(content, ensure_ascii=False, sort_keys=True), post["date"], timeutil.stamp()),
        )
        number = int(cursor.lastrowid or 0)
        conn.execute("UPDATE publish_items SET label = ? WHERE id = ?", (label_of(number), number))
        log.event(conn, "publish.item_created", {"item": label_of(number), "kind": SOCIAL, "platform": platform.name,
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


def sync(conn: sqlite3.Connection) -> int:
    """Withdraw every ready item whose request can no longer be claimed: skipped, expired or
    superseded with no newer request (the item is gone). Writes the item's lifecycle only; it
    reads `approvals` and changes nothing there. Returns how many it withdrew."""
    withdrawn = 0
    for row in conn.execute("SELECT * FROM publish_items WHERE state = 'ready' ORDER BY id").fetchall():
        item = Item.from_row(row)
        latest = latest_request(conn, item)
        if latest is None or latest.live or latest.used_at:
            continue
        if withdraw(conn, item, latest.status):
            withdrawn += 1
    return withdrawn
