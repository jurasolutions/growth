"""The `community-post` and `group-join` approval kinds (browser publishing PRD §4.3, §5.5; BP-02b).

Both go out as the Jura Facebook Page (the posting identity of the `facebook` platform in
`config/social.yaml`), in a group from the community register.

- **`community-post`**, subject `publish_item:<id>`: one planned post (`community_posts`) in a group
  joined as the Page. Content: the group and its URL, the posting identity, the day, the exact
  text and the image's bytes, read live from the plan and the register. It is gone once the post
  is posted or skipped (by hand, or because `community removed` skipped the group's posts), the
  group is removed, isn't joined as the Page any more, or turned out to take only personal
  profiles (`pages_allowed = no`), or the image is missing. Decide by and use by the end of the posting window on the post's day.
- **`group-join`**, two steps, each its own item and request:
  - the join, subject `publish_item:<id>` of a `community_join` item: the group, its URL and the
    posting identity. Gone once the group is removed or takes only personal profiles. Decide by
    and use by 18:00 (the end of the posting window) on the Sunday of the ISO week it was
    proposed in (AC-P3.4).
  - the membership answers, a `community_join_answers` item whose parent is the join: the same,
    plus the questions and the answers exactly as they will be submitted, which live in the item.
    Decide by and use by the end of the posting window on the third day after the request is
    raised: a fresh request over changed answers or a changed group gets three days of its own
    (the item's day records when). Raising them never touches the join's used approval.

Which groups an item may act in is decided here, in one place (`gone`, `problem`,
`rules_problem`); the claim, item creation and the cards all ask these.

A content change supersedes the request and raises a fresh one over the new content on the same
item (MC §4.6 A3, the publish queue's `sync()`); see `items.py`. The hash covers the exact bytes,
with no Unicode normalisation (ADR 0003). Skip, expiry and lapse withdraw the item; the plan and
the register are left as they are. The switch for both kinds is `browser` in
`config/community.yaml`: while it is off, a valid approval is refused and not claimed (AC-P5.3).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from jura_growth import approvals, brand_check, db, timeutil
from jura_growth.agents.publish import hosts, items, limits

ANSWERS_DAYS = 3  # BP §5.5: answers are decided by 18:00 on the third day after they are raised


def browser_on() -> bool:
    """`browser` in `config/community.yaml`: off by default (BP §5.10)."""
    from jura_growth.agents.community import groups as groups_mod

    return (groups_mod.settings() or {}).get("browser") is True


def identity() -> str:
    """The posting identity in groups: the Jura Facebook Page (BP §4.3, TY1)."""
    from jura_growth.agents.social.settings import load

    return load().platforms["facebook"].identity


def _group(conn: sqlite3.Connection, group_id) -> dict | None:
    from jura_growth.agents.community import groups as groups_mod

    return groups_mod.get(conn, group_id)


def week_of(day: date) -> tuple[str, date, date]:
    """(label, Monday, Sunday) of `day`'s ISO week in SGT, as the community plan reads weeks."""
    from jura_growth.agents.community import plan as plan_mod

    label = timeutil.iso_week(day)
    days = plan_mod.week_days(label)
    return label, days[0], days[-1]


# --- which groups an item may act in (BP §4.3, §4.5): one place for every check -------------------

POST, JOIN, ANSWERS = "post", "join", "answers"
STEP = {items.COMMUNITY_POST_ITEM: POST, items.JOIN_ITEM: JOIN, items.ANSWERS_ITEM: ANSWERS}


def gone(group: dict | None, step: str) -> str | None:
    """Why no item of `step` can ever go out in `group`, or None. A reason here makes the item's
    content gone (`None`), so its request is superseded with no new card (A3): the group isn't in
    the register, was removed, takes only personal profiles, or, for a post, isn't joined as the
    Jura Page (BP §5.4: posts are made only in groups joined as the Page)."""
    if group is None:
        return "the group isn't in the register"
    if group["removed"]:
        return "the group was removed"
    if group["pages_allowed"] == "no":
        return "only personal profiles can join or post in the group"
    if hosts.group_url_problem(group["url"]):
        # Recorded before the register checked it (code review 06, S7): fail closed.
        return "the group's address isn't one group's own address"
    if step == POST and group["joined_as"] != "page":
        return "the group isn't joined as the Jura Page"
    return None


def problem(group: dict | None, step: str) -> str | None:
    """Why an item of `step` can't go out in `group` now, or None: `gone()`, then the checks that
    may clear again (BP §4.5). A post needs a good-fit group joined as the Page; a join or its
    answers a good-fit Facebook group not joined as the Page, with no join made yet, and the join
    itself no join requested yet."""
    reason = gone(group, step)
    if reason or group is None:
        return reason
    if group["channel"] != "facebook":
        return "the group isn't a Facebook group"
    if group["fit"] != "good fit":
        return f"the group isn't a good fit (fit: {group['fit']})"
    if step == POST:
        return None
    if group["joined_as"] == "page":
        return "the group is already joined as the Jura Page"
    if group["join_status"] == "member" or (step == JOIN and group["join_status"] == "requested"):
        return f"the group's join is already {group['join_status']}"
    if group["join_status"] == "declined":
        # The conductor's decision (code review 06, S4): never proposed again on its own, so it
        # never takes one of a week's joins.
        return "the group declined the Jura Page's join, so it isn't proposed again"
    return None


def rules_problem(group: dict, text: str, day: date) -> str | None:
    """Why a post with `text` breaks the group's confirmed rules on `day`, or None (BP §4.5,
    AC-P5.1 lines 8 and 9). The rules must be confirmed by Ting Yu, with their open days; the day
    must be open (`rules.day_problem`); a promotional post (a link, or Jura named) needs promotion
    allowed, and confirmed promotion days of `none` allow none; a post with a link needs rules
    that are known and don't forbid links. The plan checks the same at `plan-add`, but rules are
    often confirmed after the plan, so the claim checks them again."""
    from jura_growth.agents.community import groups as groups_mod
    from jura_growth.agents.community import plan as plan_mod
    from jura_growth.agents.community import rules as rules_mod

    if not group["rules_confirmed"]:
        return "the group's rules aren't confirmed by Ting Yu"
    rules = groups_mod.rules_for(group)
    if not rules.days_confirmed:
        return "open days not confirmed"
    promotional = plan_mod.is_promotional(text)
    if promotional and rules.no_promo:
        return "the group's confirmed rules allow no promotion"
    if brand_check.find_links(text) and (not rules.known or rules.no_links):
        return "the group's rules forbid links" if rules.known else "the group's rules are unknown, so no link"
    closed = rules_mod.day_problem(rules, day.weekday(), promotional=promotional)
    if closed:
        return f"{day:%a %d %b} breaks the group's rules: {closed}"
    return None


# --- reading the content ------------------------------------------------------------------------


def read_post(conn: sqlite3.Connection, post_id: int):
    """What a browser run would post for this planned post now, read once, or None when it can't
    be posted. Returns a `kinds.Read`."""
    from jura_growth.agents.publish.kinds import Read

    post = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (int(post_id),))
    if post is None or post["kind"] != "post" or post["status"] != "planned" or not post["group_id"]:
        return None
    group = _group(conn, post["group_id"])
    if group is None or gone(group, POST):
        return None
    images, blobs = [], []
    for name in [post["image_path"]] if post["image_path"] else []:
        try:
            blob = Path(name).read_bytes()
        except OSError:
            return None
        images.append({"path": name, "sha256": hashlib.sha256(blob).hexdigest()})
        blobs.append(blob)
    content = {
        "group": group["id"],
        "target_url": group["url"],
        "posting_identity": identity(),
        "day": post["planned_day"],
        "text": post["text"],
        "images": images,
    }
    return Read(content, tuple(blobs))


def read_join(conn: sqlite3.Connection, item: items.Item):
    """The join, or its membership answers, as a browser run would act on them now."""
    from jura_growth.agents.publish.kinds import Read

    group = _group(conn, item.ref_id)
    if group is None or gone(group, STEP[item.kind]):
        return None
    content = {"group": group["id"], "target_url": group["url"], "posting_identity": identity()}
    if item.kind == items.ANSWERS_ITEM:
        content["answers"] = item.content.get("answers") or []
    return Read(content, ())


# --- deadlines ------------------------------------------------------------------------------------


def closes(item: items.Item, content: dict | None = None) -> datetime:
    """When the item's chance to go out ends: its decide-by and use-by."""
    if item.kind == items.COMMUNITY_POST_ITEM:
        day = date.fromisoformat((content or {}).get("day") or item.day)
    elif item.kind == items.JOIN_ITEM:
        day = week_of(date.fromisoformat(item.day))[2]  # the Sunday of the ISO week it was proposed in
    else:
        day = date.fromisoformat(item.day) + timedelta(days=ANSWERS_DAYS)
    return limits.window_on(day)[1]


def opens(item: items.Item, content: dict | None = None) -> str:
    """The first day the item may be claimed: a post's own day; a join or answers from the day
    they were raised."""
    if item.kind == items.COMMUNITY_POST_ITEM:
        return (content or {}).get("day") or item.day
    return item.day


# --- the kinds ------------------------------------------------------------------------------------


def _has_live(conn: sqlite3.Connection, kind: str, subject: str) -> bool:
    """A request over `subject` is pending, or approved and unclaimed: `deadlines()` is asked for
    its use-by. With none, it is asked for a new request's decide-by."""
    return bool(db.scalar(
        conn, "SELECT 1 FROM approvals WHERE kind = ? AND subject = ? AND status IN ('pending', 'approved') "
              "AND used_at IS NULL", (kind, subject)))


def _item(conn: sqlite3.Connection, subject: str, kinds: tuple[str, ...]) -> items.Item:
    found = items.of(conn, subject)
    if found is None or found.kind not in kinds:
        raise LookupError(f"no publish item of kind {', '.join(kinds)} for {subject}")
    return found


class _GroupKind:
    name = ""
    item_kinds: tuple[str, ...] = ()
    used_word = "claimed by a publish run"

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        from jura_growth.agents.publish import kinds

        item = items.of(conn, subject)
        if item is None or item.kind not in self.item_kinds or item.state not in items.OPEN:
            return None
        found = kinds.read(conn, item)
        return kinds.hashed(found.content) if found is not None else None

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        from jura_growth.agents.publish import kinds

        item = _item(conn, subject, self.item_kinds)
        if item.kind == items.ANSWERS_ITEM and approvals.latest(conn, self.name, subject) is not None \
                and not _has_live(conn, self.name, subject):
            # A fresh request over changed answers or a changed group: its three days start now,
            # whichever path raised it (SC3; code review 02b, B2). The item's day records it.
            item = items.restart_clock(conn, item, now.astimezone(timeutil.SGT).date())
        found = kinds.read(conn, item)
        end = closes(item, found.content if found else None)
        return approvals.Deadlines(decide_by=end, use_by=end)

    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        if not browser_on():
            return "community.browser is off in config/community.yaml, so nothing is posted or joined through the browser"
        return None

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject, self.item_kinds), "skipped")

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject, self.item_kinds), "expired")

    def on_lapse(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject, self.item_kinds), "lapsed")

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str | None:
        item = items.of(conn, subject)
        return note(conn, item) if item else None


class CommunityPost(_GroupKind):
    name = items.COMMUNITY_POST_KIND
    item_kinds = (items.COMMUNITY_POST_ITEM,)

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """The card: the group and its URL, the Page, the day, the exact text, the image, the
        links in the text, the brand-gate result and the group's rules as confirmed."""
        from jura_growth.agents.community import groups as groups_mod
        from jura_growth.agents.publish import kinds

        item = _item(conn, subject, self.item_kinds)
        found = kinds.read(conn, item)
        content = found.content if found else item.content
        post = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (item.ref_id,)) or {}
        group = _group(conn, content["group"]) or {}
        day = date.fromisoformat(content["day"])
        qa = json.loads(post.get("qa_json") or "{}")
        lines = [f"```\n{content['text'].strip()}\n```"]
        links = list(dict.fromkeys(brand_check.find_links(content["text"])))
        lines.append("Links in the text: " + (", ".join(links) if links else "none"))
        if qa.get("brand") == "pass":
            lines.append(f"Brand check: passed on attempt {qa.get('attempt', 1)} of 2")
        if group:
            lines.append(f"Group rules: {groups_mod.rules_for(group).summary()}")
        images = [Path(image["path"]) for image in content["images"]]
        lines.append("1 image attached." if images else "No image.")
        return approvals.Preview(
            title=f"Facebook group {group.get('name', content['group'])} as {content['posting_identity']}: "
                  f"{content['target_url']} · {day:%a} {day.day} {day:%b %Y} · {item.label}",
            reason=f"the post planned for this group on {day:%a} {day.day} {day:%b}"
                   + (f", from community run {post['run_id']}" if post.get("run_id") else ""),
            text="\n".join(lines),
            files=tuple(images),
        )


class GroupJoin(_GroupKind):
    name = items.JOIN_KIND
    item_kinds = (items.JOIN_ITEM, items.ANSWERS_ITEM)

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """A join: the group, its URL, why it fits and its rules. Answers: the questions and the
        answers, exactly as they will be submitted."""
        from jura_growth.agents.publish import kinds

        item = _item(conn, subject, self.item_kinds)
        found = kinds.read(conn, item)
        content = found.content if found else item.content
        group = _group(conn, content["group"]) or {}
        name = group.get("name", f"group {content['group']}")
        if item.kind == items.ANSWERS_ITEM:
            lines = ["The group asks these questions. Nothing is submitted until you approve these answers:"]
            for pair in content.get("answers") or []:
                lines += [f"Q: {pair['question']}", f"A: {pair['answer']}"]
            return approvals.Preview(
                title=f"Membership answers for {name} as {content['posting_identity']}: {content['target_url']} · {item.label}",
                reason="the group asked membership questions when the run went to join it",
                text="\n".join(lines),
            )
        lines = [f"Fit: {group.get('fit_reason') or 'not recorded'}",
                 f"Rules as researched: {group.get('promo_rules') or 'unknown'}",
                 "If the group asks membership questions, the answers come to you as their own card first."]
        return approvals.Preview(
            title=f"Join {name} as {content['posting_identity']}: {content['target_url']} · {item.label}",
            reason="a good-fit group not yet joined as the Jura Page",
            text="\n".join(lines),
        )


def note(conn: sqlite3.Connection, item: items.Item) -> str | None:
    """Why a community item's request was superseded, in Ting Yu's words."""
    from jura_growth.agents.publish import kinds

    post = None
    if item.kind == items.COMMUNITY_POST_ITEM:
        post = db.one(conn, "SELECT status, group_id FROM community_posts WHERE id = ?", (item.ref_id,))
        if post and post["status"] == "posted":
            return "posted by hand"
    group = _group(conn, post["group_id"] if post and post["group_id"] else item.content.get("group", item.ref))
    reason = gone(group, STEP[item.kind])
    if reason:
        return reason
    if post and post["status"] == "skipped":
        return "skipped by hand"
    if kinds.read(conn, item) is not None:
        return {items.COMMUNITY_POST_ITEM: "the post or its group changed",
                items.ANSWERS_ITEM: "the answers or the group changed"}.get(item.kind, "the group changed")
    return None
