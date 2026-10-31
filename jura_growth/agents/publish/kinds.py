"""The `social-post` approval kind, and what every publish kind shares (browser publishing PRD §5.5;
MC §4.6). The `community-post` and `group-join` kinds are in `group_kinds.py`; `read()`,
`closes()`, `opens()` and `kind_of()` answer for an item of any kind.

The subject is one publish item, `publish_item:<id>`: one platform's post for one draft.

- **Content** is what the browser would post now: the platform, the posting identity, the page
  it posts to, the day, the exact text and the image bytes in order (each image's SHA-256). It is
  read live from the `social_posts` draft, its image files and `config/social.yaml`, so a change
  to any one field supersedes the request and raises one over the new content (A3, AC-P1.3). The
  hash covers the exact bytes, with no Unicode normalisation (MC §4.6 A3 and ADR 0003, amended
  2026-10-27). The item is gone (`None`) once its draft is skipped or posted by hand, a skip is
  recorded for its day and platform, its page URL is unset, its platform is switched off
  (`enabled: false`), or an image is missing.
- **Deadlines:** decide by an hour before the end of the posting window, and use by its end, on
  the day of the content being asked about (17:00 and 18:00 SGT, or earlier when
  `config/publish.yaml` narrows the window), so an approval always has a publish slot left. A
  request raised because the day changed therefore lapses at the new day's end, not the old one's.
  A claim that finds the post changed after the decide-by raises the replacement straight away
  (`approvals.use`), and that one has until the window's end.
- **Switch:** the platform's `enabled` and its `publish_mode`. While the platform is turned off
  (LinkedIn since 2026-10-29) or in `draft` mode, a valid approval is refused and not claimed
  (A13, AC-P5.3), and no card is raised.
- **Skip** withdraws the item and records `social skip <date> <platform>`. Expiry and lapse
  withdraw it and leave the draft as it is.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from jura_growth import approvals, db, discord, privacy, timeutil
from jura_growth.agents.publish import items, limits

KIND = items.SOCIAL_KIND
_LINK = re.compile(r"https?://[^\s<>()\"']+")


@dataclass(frozen=True)
class Read:
    """One read of a draft: its content, and each image's bytes exactly as hashed."""

    content: dict
    blobs: tuple[bytes, ...]


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")


def read_social(conn: sqlite3.Connection, post_id: int) -> Read | None:
    """What a browser run would post for this draft now, read once, or None when it can't be
    posted. Each image's hash is of the bytes in `blobs`, so a caller can hand out exactly what
    it checked."""
    from jura_growth.agents.social.settings import load

    post = db.one(conn, "SELECT * FROM social_posts WHERE id = ?", (post_id,))
    if post is None or post["status"] != "draft":
        return None
    skipped = db.scalar(conn, "SELECT 1 FROM social_skips WHERE date = ? AND platform = ?", (post["date"], post["platform"]))
    if skipped:
        return None
    platform = load().platforms.get(post["platform"])
    # A switched-off platform's post is gone, so the next sync supersedes its waiting card and
    # withdraws the item ("the item is gone"). Draft mode isn't gone: A13 keeps that card live.
    if platform is None or not platform.enabled or not platform.page_url:
        return None
    images, blobs = [], []
    for name in json.loads(post["image_paths"] or "[]"):
        try:
            blob = Path(name).read_bytes()
        except OSError:
            return None
        images.append({"path": name, "sha256": hashlib.sha256(blob).hexdigest()})
        blobs.append(blob)
    content = {
        "platform": platform.name,
        "posting_identity": platform.identity,
        "target_url": platform.page_url,
        "day": post["date"],
        "text": post["text"],
        "images": images,
    }
    return Read(content, tuple(blobs))


def social_content(conn: sqlite3.Connection, post_id: int) -> dict | None:
    found = read_social(conn, post_id)
    return found.content if found else None


def hashed(content: dict) -> bytes:
    """The bytes a request's hash covers: everything but where the images sit on disk."""
    if "images" not in content:
        return _canonical(content)
    return _canonical({**content, "images": [image["sha256"] for image in content["images"]]})


def read(conn: sqlite3.Connection, item: items.Item) -> Read | None:
    """What a browser run would act on for `item` now, read once, whatever its kind; None when
    it can't go out (MC §4.6 A3)."""
    from jura_growth.agents.publish import group_kinds

    if item.kind == items.SOCIAL_ITEM:
        return read_social(conn, item.ref_id)
    if item.kind == items.COMMUNITY_POST_ITEM:
        return group_kinds.read_post(conn, item.ref_id)
    return group_kinds.read_join(conn, item)


def switched_off(conn: sqlite3.Connection, item: items.Item) -> str | None:
    """The item's kind's own switch (`switched_off`), as `use()` reads it: why nothing goes out."""
    registered = approvals.kinds().get(kind_of(item))
    hook = getattr(registered.kind, "switched_off", None) if registered else None
    return hook(conn, item.subject) if hook is not None else None


def kind_of(item: items.Item) -> str:
    """The approval kind of an item's requests."""
    return items.APPROVAL_KINDS[item.kind]


def closes(item: items.Item, content: dict | None = None) -> datetime:
    """When the item's chance to go out ends (its use-by), for `content` as it reads now (the
    item's own frozen copy when None). A social post's decide-by comes earlier (`decide_closes`)."""
    from jura_growth.agents.publish import group_kinds

    if item.kind == items.SOCIAL_ITEM:
        return limits.window_on(date.fromisoformat((content or item.content)["day"]))[1]
    return group_kinds.closes(item, content)


def decide_closes(item: items.Item, content: dict | None = None) -> datetime:
    """When a new request over the item can no longer be raised: its decide-by."""
    if item.kind == items.SOCIAL_ITEM:
        return limits.decide_by_on(date.fromisoformat((content or item.content)["day"]))
    return closes(item, content)


def opens(item: items.Item, content: dict | None = None) -> str:
    """The first day (YYYY-MM-DD) the item may be claimed."""
    from jura_growth.agents.publish import group_kinds

    if item.kind == items.SOCIAL_ITEM:
        return (content or item.content)["day"]
    return group_kinds.opens(item, content)


def _item(conn: sqlite3.Connection, subject: str) -> items.Item:
    found = items.of(conn, subject)
    if found is None:
        raise LookupError(f"no publish item for {subject}")
    return found


class SocialPost:
    """The kind `approvals` asks about every `publish_item:<id>` that is a social post."""

    name = KIND
    used_word = "claimed by a publish run"

    def feed_approved(self, conn: sqlite3.Connection, subject: str) -> str:
        """What happens next, kept true: the decide-by leaves a slot, and a pause holds it back. A
        platform moved back to draft mode with its card open posts nothing (A13). A claim's
        replacement can be approved after the last run has started (`deadlines`), and then nothing
        is left to post it."""
        item = _item(conn, subject)
        day = date.fromisoformat(item.day)
        _, end = limits.window_on(day)
        off = self.switched_off(conn, subject)
        if off:
            return f"{off[:1].upper()}{off[1:]}, and this lapses at {end:%H:%M} SGT."
        latest = items.latest_request(conn, item)
        decided = timeutil.parse(latest.decided_at) if latest and latest.decided_at else timeutil.now_sgt()
        if decided >= limits.last_run_on(day):
            return f"No publish run is left today, so this lapses at {end:%H:%M} SGT."
        return items.unless_paused(conn, f"It goes out on a publish run today, by {end:%H:%M} SGT. "
                                         "The run's update here gives the post's address.")

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        item = items.of(conn, subject)
        if item is None or item.kind != items.SOCIAL_ITEM or item.state not in items.OPEN:
            return None
        content = social_content(conn, item.ref_id)
        return hashed(content) if content is not None else None

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """The card (AC-P1.1): the page and its URL, the day, the headline, the exact text, the
        images, the links in the text, the sources and the brand-gate result."""
        from jura_growth.agents.social.settings import load

        item = _item(conn, subject)
        content = social_content(conn, item.ref_id) or item.content
        post = db.one(conn, "SELECT * FROM social_posts WHERE id = ?", (item.ref_id,)) or {}
        settings = load()
        platform = settings.platforms[item.platform]
        day = date.fromisoformat(content["day"])
        qa = json.loads(post.get("qa_json") or "{}")
        theme = settings.themes.get(post.get("theme") or "")
        run = f", drafted by social run {post['run_id']}" if post.get("run_id") else ""
        lines = [f"```\n{discord.no_fence(content['text'].strip())}\n```"]
        links = list(dict.fromkeys(_LINK.findall(content["text"])))
        lines.append("Links in the text: " + (", ".join(f"<{link}>" for link in links) if links else "none"))
        sources = [url for url in json.loads(post.get("source_urls") or "[]") if url not in links]
        if sources:  # Instagram carries no links, so this is how the card shows what the post relies on
            lines.append("Sources: " + ", ".join(f"<{url}>" for url in sources))
        if qa.get("passed"):
            lines.append(f"Brand check: passed on attempt {qa.get('attempt', 1)} of 2")
        images = [Path(image["path"]) for image in content["images"]]
        lines.append(f"{len(images)} image{'s' if len(images) != 1 else ''} attached, posted in this order." if images
                     else "No image.")
        headline = qa.get("headline")  # beside the content, not in it: the title isn't hashed
        return approvals.Preview(
            title=f"{platform.label} as {content['posting_identity']}: {content['target_url']} · "
                  f"{day:%a} {day.day} {day:%b %Y} · {item.label}" + (f" · {headline}" if headline else ""),
            reason=f"the {platform.label} post for {day:%a} {day.day} {day:%b}"
                   + (f" ({theme.label})" if theme else "") + run,
            text="\n".join(lines),
            files=tuple(images),
        )

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        """Decide by an hour before the window ends, and use by its end, on the content's day. A
        request raised past that decide-by is a claim's replacement for a post that changed
        (`approvals.use`): it has until the window's end."""
        item = _item(conn, subject)
        content = social_content(conn, item.ref_id)
        day = date.fromisoformat(content["day"] if content else item.day)
        decide_by = limits.decide_by_on(day)
        _, end = limits.window_on(day)
        return approvals.Deadlines(decide_by=decide_by if now < decide_by else end, use_by=end)

    def card_problem(self, conn: sqlite3.Connection, subject: str) -> str | None:
        """Why the card can't go out: Discord would mask part of the post, and Ting Yu must never
        approve words he couldn't read. The brand gate refuses these; this holds for a name
        learned since the gate, or a draft changed past it. It learns the names first: a new
        process, as each SSH call is, knows none, and would call the post fine."""
        privacy.learn(conn)
        content = social_content(conn, _item(conn, subject).ref_id)
        if content is not None and privacy.own_copy_as_shown(content["text"]) != content["text"]:
            return "Discord would mask part of the post, so its card can't show the exact text"
        return None

    def on_approve(self, conn: sqlite3.Connection, subject: str, args: dict) -> None:
        """No card, no approval: a typed approval of a request whose card hasn't gone out would be
        a yes to words he hasn't read, and #social-drafts no longer holds them. A card Discord hasn't
        taken yet can wait, since the heartbeat posts it, and it stays open for a skip. A post whose
        card went out whole stands, whatever is learned since. The answer says why: the sweep's own
        refusal, then what this process can read, then the plain case. The refusal rolls the
        decision back."""
        from jura_growth import cards  # cards reaches the kinds through the approvals registry

        latest = items.latest_request(conn, _item(conn, subject))
        if latest is None or latest.posted_at is not None:
            return
        problem = cards.refusal(conn, latest.id) or self.card_problem(conn, subject)
        if problem:
            raise approvals.BadArgs(f"{problem}. It can't be approved")
        raise approvals.BadArgs("Its card hasn't gone out yet, so it can't be approved. The heartbeat posts it, and you can decide then")

    def own_copy(self, conn: sqlite3.Connection, subject: str) -> tuple[str, ...]:
        """The post's text, as Jura's own copy on its card (`privacy`). A draft past the brand gate only."""
        item = _item(conn, subject)
        post = db.one(conn, "SELECT text, qa_json FROM social_posts WHERE id = ?", (item.ref_id,))
        if post is None or not json.loads(post["qa_json"] or "{}").get("passed"):
            return ()
        return (post["text"].strip(),)

    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        from jura_growth.agents.social.settings import load

        why = load().platforms[_item(conn, subject).platform].not_browser
        return f"{why}, so nothing is posted through the browser" if why else None

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        from jura_growth.agents.social import history

        item = _item(conn, subject)
        items.withdraw(conn, item, "skipped")
        try:
            history.skip(conn, date.fromisoformat(item.day), item.platform, "skipped by Ting Yu in #approvals")
        except ValueError:
            pass  # already published by hand: nothing left to skip

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject), "expired")

    def on_lapse(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject), "lapsed")

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str | None:
        item = items.of(conn, subject)
        return note(conn, item) if item else None


def skipped_by_hand(conn: sqlite3.Connection, item: items.Item) -> bool:
    if item.kind == items.COMMUNITY_POST_ITEM:
        return db.scalar(conn, "SELECT status FROM community_posts WHERE id = ?", (item.ref_id,)) == "skipped"
    if item.kind != items.SOCIAL_ITEM:
        return False
    post = db.one(conn, "SELECT status FROM social_posts WHERE id = ?", (item.ref_id,))
    skip = db.scalar(conn, "SELECT 1 FROM social_skips WHERE date = ? AND platform = ?", (item.day, item.platform))
    return bool(skip) or bool(post and post["status"] == "skipped")


def note(conn: sqlite3.Connection, item: items.Item) -> str | None:
    """Why an item's request was superseded, in Ting Yu's words."""
    post = db.one(conn, "SELECT status FROM social_posts WHERE id = ?", (item.ref_id,))
    if post and post["status"] == "published":
        return "posted by hand"
    if skipped_by_hand(conn, item):
        return "skipped by hand"
    if social_content(conn, item.ref_id) is not None:
        return "the post changed"
    if item.kind == items.SOCIAL_ITEM:
        from jura_growth.agents.social.settings import load

        platform = load().platforms.get(item.platform)
        if platform is not None and not platform.enabled:
            return f"{platform.label} is switched off"
    return None


def kinds() -> dict:
    """The three browser-publishing kinds (BP §5.5), all declared by the publish plug-in."""
    from jura_growth.agents.publish import group_kinds

    return {KIND: SocialPost(), group_kinds.CommunityPost.name: group_kinds.CommunityPost(),
            group_kinds.GroupJoin.name: group_kinds.GroupJoin()}
