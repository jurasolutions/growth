"""Publish items: creating them and writing their lifecycle (browser publishing PRD §5.4).

An item's lifecycle is its own and never a copy of the decision (MC §4.6 A2): `ready`, `claimed`,
`done`, `stopped`, `unknown` or `withdrawn`. Whether its request is pending, approved, skipped or
expired is read from `approvals`. The subject of an item's requests is `publish_item:<id>`;
Ting Yu only ever sees and types the request's `A-nnnn`, with `P-nnnn` as a label beside it.

A social item is raised by `social submit` for each platform in `browser` mode whose variant
passed the brand gate (`create_social`), and only while its decide-by, the end of the posting
window on its day, is still ahead. Drafts written before a platform moved to `browser` never get
one: items are made only at submit.

Community items (BP-02b), each only while `browser` is on in `config/community.yaml`:

- a community post, by `community publish-plan` for each planned post in a group joined as the
  Jura Page (`create_community_post`, `raise_for_plan`); one item per planned post;
- a join, by `community propose-join <group-id>` for a good-fit group not joined as the Page
  and not Page-less, up to the weekly join cap counted over the joins proposed in the ISO week
  (`create_join`);
- a join's membership answers, by `publish done <id> --outcome questions` once they pass the
  brand gate (browser publishing#06 calls `create_join_answers`).

When a queued item's content changes, `sync()` raises a fresh request on the same item for the
new content and supersedes the old one (MC §4.6 A3 and A11). That holds for every kind; for the
answers step, answers reported again for the same join replace those still waiting.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, fields
from datetime import date, timedelta

from jura_growth import approvals, db, log, timeutil
from jura_growth.agents.publish import hosts, limits

AGENT = "publish"
SOCIAL_ITEM = "social_post"  # publish_items.kind; its approval kind is SOCIAL_KIND
SOCIAL_KIND = "social-post"
COMMUNITY_POST_ITEM = "community_post"  # its approval kind is COMMUNITY_POST_KIND
COMMUNITY_POST_KIND = "community-post"
JOIN_ITEM = "community_join"  # the join; its approval kind is JOIN_KIND
ANSWERS_ITEM = "community_join_answers"  # a join's membership answers; also JOIN_KIND
JOIN_KIND = "group-join"
APPROVAL_KINDS = {SOCIAL_ITEM: SOCIAL_KIND, COMMUNITY_POST_ITEM: COMMUNITY_POST_KIND, JOIN_ITEM: JOIN_KIND,
                  ANSWERS_ITEM: JOIN_KIND}
COMMUNITY_PLATFORM = "facebook"  # every group in the register that can be acted on is a Facebook group
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
    wrong = hosts.page_problem(platform.name, platform.page_url)
    if wrong:
        return Made(why=f"{platform.name}'s page_url won't do: {wrong}")
    day = date.fromisoformat(post["date"])
    _, closes = limits.window_on(day)
    if timeutil.now_sgt() >= closes:
        return Made(why=f"the posting window for {day} has closed ({closes:%H:%M} SGT)")
    content = kinds.social_content(conn, post_id)
    if content is None:
        return Made(why=f"the {platform.name} draft for {day} can't be posted now (skipped, posted or missing an image)")
    return _make(conn, SOCIAL_ITEM, platform.name, post_id, content, post["date"], run_id=run_id, request=request)


def _make(conn: sqlite3.Connection, kind: str, platform: str, ref, content: dict, day: str, *, run_id: int | None,
          request: bool = True, parent: int | None = None) -> Made:
    """Insert one item with `content` frozen into it, and raise its request."""
    with db.atomic(conn):
        cursor = conn.execute(
            "INSERT INTO publish_items (label, kind, platform, ref, parent_item, target_url, posting_identity, content_json,"
            " day, created_at) VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, platform, str(ref), parent, content["target_url"], content["posting_identity"],
             json.dumps(content, ensure_ascii=False, sort_keys=True), day, timeutil.stamp()),
        )
        number = int(cursor.lastrowid or 0)
        conn.execute("UPDATE publish_items SET label = ? WHERE id = ?", (label_of(number), number))
        log.event(conn, "publish.item_created", {"item": label_of(number), "kind": kind, "platform": platform, "day": day},
                  agent=AGENT, run_id=run_id)
        item = get(conn, number)
        assert item is not None  # inserted above, in this transaction
        approval = raise_request(conn, item, run_id=run_id) if request else None
    return Made(item, approval)


def _existing(conn: sqlite3.Connection, kind: str, ref, *, states: tuple[str, ...] | None = None,
              parent: int | None = None) -> Item | None:
    """The newest item of `kind` over `ref`, optionally in `states` and under the `parent` item."""
    sql = "SELECT * FROM publish_items WHERE kind = ? AND ref = ?"
    params: tuple = (kind, str(ref))
    if parent is not None:
        sql += " AND parent_item = ?"
        params += (parent,)
    if states:
        sql += f" AND state IN ({', '.join('?' for _ in states)})"
        params += states
    row = conn.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone()
    return Item.from_row(row) if row else None


def _too_late(item_kind: str, day: str, content: dict) -> str | None:
    """Why an item made now couldn't be decided in time, or None."""
    from jura_growth.agents.publish import kinds

    closes = kinds.closes(_probe(item_kind, 0, day=day), content)
    if timeutil.now_sgt() >= closes:
        return f"its time to be decided has passed ({closes.astimezone(timeutil.SGT):%a %d %b %H:%M} SGT)"
    return None


def create_community_post(conn: sqlite3.Connection, post_id: int, *, run_id: int | None, request: bool = True) -> Made:
    """The item and its `community-post` request for one planned post in a group joined as the
    Jura Page (`community publish-plan`), or why not. A post that already has an item gets no
    second one. Transactions and cards as `create_social`."""
    from jura_growth.agents.publish import group_kinds

    if not group_kinds.browser_on():
        return Made(why="community.browser is off in config/community.yaml")
    post = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (int(post_id),))
    if post is None or post["kind"] != "post":
        return Made(why=f"there is no planned post {post_id}")
    gone = group_kinds.gone(_group(conn, post["group_id"]), group_kinds.POST)
    if gone:
        return Made(why=f"item {post_id} is posted by hand: {gone}")
    existing = _existing(conn, COMMUNITY_POST_ITEM, post_id)
    if existing is not None:
        return Made(existing, latest_request(conn, existing), why=f"item {post_id} already has {existing.label}")
    found = group_kinds.read_post(conn, post_id)
    if found is None:
        return Made(why=f"item {post_id} can't be posted now (posted, skipped, or its image missing)")
    late = _too_late(COMMUNITY_POST_ITEM, post["planned_day"], found.content)
    if late:
        return Made(why=f"item {post_id}: {late}")
    return _make(conn, COMMUNITY_POST_ITEM, COMMUNITY_PLATFORM, post_id, found.content, post["planned_day"],
                 run_id=run_id, request=request)


def raise_for_plan(conn: sqlite3.Connection, week: str, *, run_id: int | None) -> list[Made]:
    """`community publish-plan`: an item and a request for each planned post of `week` in a group
    joined as the Jura Page. Posts in other groups stay on the checklist for Ting Yu."""
    rows = db.rows(
        conn,
        "SELECT p.id FROM community_posts p JOIN community_groups g ON g.id = p.group_id WHERE p.week = ? "
        "AND p.kind = 'post' AND p.status = 'planned' AND g.joined_as = 'page' ORDER BY p.planned_day, p.id",
        (week,),
    )
    with db.transaction(conn):
        return [create_community_post(conn, row["id"], run_id=run_id) for row in rows]


def proposals_in_week(conn: sqlite3.Connection, day: date) -> int:
    """Joins proposed in `day`'s ISO week (SGT), whatever became of them: a proposal Ting Yu
    skipped, or left to expire, still uses one of the week's three (the conductor's decision,
    code review 02b). It fails closed and keeps the weekly pace."""
    from jura_growth.agents.publish import group_kinds

    _, monday, sunday = group_kinds.week_of(day)
    return db.scalar(
        conn, "SELECT count(*) FROM publish_items WHERE kind = ? AND day BETWEEN ? AND ?",
        (JOIN_ITEM, monday.isoformat(), sunday.isoformat()),
    ) or 0


def _group(conn: sqlite3.Connection, group_id) -> dict | None:
    from jura_growth.agents.community import groups as groups_mod

    return groups_mod.get(conn, group_id) if group_id else None


def create_join(conn: sqlite3.Connection, group_id: int, *, run_id: int | None, request: bool = True) -> Made:
    """`community propose-join <group-id>`: the join item and its `group-join` request for a
    good-fit group not joined as the Page, up to the weekly join cap, or why not."""
    from jura_growth.agents.publish import group_kinds

    if not group_kinds.browser_on():
        return Made(why="community.browser is off in config/community.yaml, so no join is proposed")
    problem = group_kinds.problem(_group(conn, group_id), group_kinds.JOIN)
    if problem:
        return Made(why=f"group {group_id}: {problem}")
    waiting = _existing(conn, JOIN_ITEM, group_id, states=OPEN)
    if waiting is not None:
        return Made(waiting, latest_request(conn, waiting), why=f"group {group_id} already has a join waiting ({waiting.label})")
    today = timeutil.today()
    if _too_late(JOIN_ITEM, today.isoformat(), {}):
        # Past this week's last window (Sunday 18:00): the proposal belongs to the next ISO week.
        today += timedelta(days=7 - today.weekday())
    cap = limits.community_joins_per_week()
    if proposals_in_week(conn, today) >= cap:
        return Made(why=f"{cap} joins proposed in {timeutil.iso_week(today)} already; the cap is {cap} a week")
    found = group_kinds.read_join(conn, _probe(JOIN_ITEM, group_id))
    if found is None:
        return Made(why=f"group {group_id} can't be joined now")
    return _make(conn, JOIN_ITEM, COMMUNITY_PLATFORM, group_id, found.content, today.isoformat(), run_id=run_id,
                 request=request)


def create_join_answers(conn: sqlite3.Connection, join: Item, answers: list[dict], *, run_id: int | None,
                        request: bool = True) -> Made:
    """The membership answers for `join`, as their own item and `group-join` request (BP §5.4).
    `publish done <id> --outcome questions` calls it once the answers have passed the brand gate
    (browser publishing#06), so `join` is a join a run has claimed and reported on. Answers already
    waiting for that join are replaced in place: their request is superseded and a fresh one raised
    over the new answers (A3), decided by 18:00 on the third day after it is raised."""
    from jura_growth.agents.publish import group_kinds

    if join.kind != JOIN_ITEM:
        return Made(why=f"{join.label} isn't a join")
    if join.state not in ("claimed", "done"):
        return Made(why=f"{join.label} hasn't been claimed by a run, so no membership questions were seen")
    if not group_kinds.browser_on():
        return Made(why="community.browser is off in config/community.yaml")
    clean = [{"question": str(a["question"]), "answer": str(a["answer"])} for a in answers
             if isinstance(a, dict) and str(a.get("question") or "").strip() and str(a.get("answer") or "").strip()]
    if not clean or len(clean) != len(answers):
        return Made(why="every membership question needs its question and its answer")
    today = timeutil.today().isoformat()
    waiting = _existing(conn, ANSWERS_ITEM, join.ref, states=("ready",), parent=join.id)
    if waiting is not None:
        if waiting.content.get("answers") != clean:
            refreeze(conn, waiting, {**waiting.content, "answers": clean})
            waiting = get(conn, waiting.id) or waiting
        return Made(waiting, raise_request(conn, waiting, run_id=run_id) if request else None)
    found = group_kinds.read_join(conn, _probe(ANSWERS_ITEM, join.ref_id, answers=clean))
    if found is None:
        return Made(why=f"group {join.ref} can't be joined now")
    return _make(conn, ANSWERS_ITEM, COMMUNITY_PLATFORM, join.ref, found.content, today, run_id=run_id,
                 request=request, parent=join.id)


def _probe(kind: str, group_id, *, day: str | None = None, **content) -> Item:
    """An unsaved item, to read what a new one would hold."""
    return Item(id=0, label="", kind=kind, platform=COMMUNITY_PLATFORM, ref=str(int(group_id)), parent_item=None,
                target_url="", posting_identity="", content_json=json.dumps(content), day=day or timeutil.today_str(),
                state="ready", outcome=None, stop_reason=None, post_url=None, live_text_hash=None,
                live_text_matches=None, run_id=None, created_at="", claimed_at=None, finished_at=None)


def restart_clock(conn: sqlite3.Connection, item: Item, day: date) -> Item:
    """Record `day` as the day the item's fresh request was raised: a membership-answers request is
    decided by 18:00 on the third day after it is raised (SC3)."""
    conn.execute("UPDATE publish_items SET day = ? WHERE id = ? AND state = 'ready'", (day.isoformat(), item.id))
    return get(conn, item.id) or item


def raise_request(conn: sqlite3.Connection, item: Item, *, run_id: int | None) -> approvals.Approval | None:
    """The item's request (A11: raised only by the commands that make items, and by `sync()`)."""
    if item.kind == SOCIAL_ITEM:
        from jura_growth.agents.social.settings import load

        reason = f"the {load().platforms[item.platform].label} post for {item.day}"
    elif item.kind == COMMUNITY_POST_ITEM:
        reason = f"the community post planned for {item.day}"
    elif item.kind == JOIN_ITEM:
        reason = "a join proposed for a good-fit group"
    else:
        reason = "membership answers for an approved join"
    return approvals.request(conn, APPROVAL_KINDS[item.kind], item.subject, reason=reason, run_id=run_id)


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
        (content.get("day", item.day), content["target_url"], content["posting_identity"],
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
        found = kinds.read(conn, item)
        content = found.content if found is not None else None
        digest = approvals.content_hash(kinds.hashed(content)) if content is not None else None
        # A fresh answers request gets three days from when it is raised (SC3), so it is never late.
        in_time = content is not None and (item.kind == ANSWERS_ITEM or timeutil.now_sgt() < kinds.closes(item, content))
        # While the kind is switched off (a platform in draft, community.browser off) no card is
        # raised: the old request is superseded or lapses as usual (A13; code review 02b, S4).
        switched_off = content is not None and kinds.switched_off(conn, item)
        if latest.live:
            if content is not None and digest == latest.content_hash:
                if content != item.content:
                    refreeze(conn, item, content)
                continue
            if content is not None and (not in_time or switched_off):
                continue  # too late for a new card, or switched off: `use()` and the lapses close the old one
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
            if switched_off:
                continue  # raised once the switch is back on
            # Changed, or gone and back again unchanged (R2-N1): either way it needs a live card.
            refreeze(conn, item, content)
            fresh = raise_request(conn, item, run_id=run_id)
            if fresh is not None and fresh.live:
                raised.append(fresh)
                continue
        withdraw(conn, item, latest.status)
    return raised
