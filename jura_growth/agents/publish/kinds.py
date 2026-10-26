"""The `social-post` approval kind (browser publishing PRD §5.5; MC §4.6).

The subject is one publish item, `publish_item:<id>`.

- **Content** is what the browser would post now: the platform, the posting identity, the page
  it posts to, the day, the exact text and the image bytes in order (each image's SHA-256). It is
  read live from the `social_posts` draft, its image files and `config/social.yaml`, so a change
  to any one field supersedes the request and raises one over the new content (A3, AC-P1.3).
  The text is hashed byte for byte, with no Unicode normalisation, so two drafts that differ at
  all never hash alike (as for `outreach-email`, code review 06). The item is gone (`None`) once
  its draft is skipped or posted by hand, a skip is recorded for its day and platform, its page
  URL is unset, or an image is missing.
- **Deadlines:** decide by and use by the end of the posting window on the item's day (18:00
  SGT, or earlier when `config/publish.yaml` narrows the window).
- **Switch:** the platform's `publish_mode`. In `draft` mode a valid approval is refused and not
  claimed (A13, AC-P5.3).
- **Skip** withdraws the item and records `social skip <date> <platform>`. Expiry and lapse
  withdraw it and leave the draft as it is.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from jura_growth import approvals, db
from jura_growth.agents.publish import items, limits

KIND = items.SOCIAL_KIND
_LINK = re.compile(r"https?://[^\s<>()\"']+")


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def social_content(conn: sqlite3.Connection, post_id: int) -> dict | None:
    """What a browser run would post for this draft now, or None when it can't be posted."""
    from jura_growth.agents.social.settings import load

    post = db.one(conn, "SELECT * FROM social_posts WHERE id = ?", (post_id,))
    if post is None or post["status"] != "draft":
        return None
    skipped = db.scalar(conn, "SELECT 1 FROM social_skips WHERE date = ? AND platform = ?", (post["date"], post["platform"]))
    if skipped:
        return None
    platform = load().platforms.get(post["platform"])
    if platform is None or not platform.page_url:
        return None
    images = []
    for name in json.loads(post["image_paths"] or "[]"):
        digest = _sha256(Path(name))
        if digest is None:
            return None
        images.append({"path": name, "sha256": digest})
    return {
        "platform": platform.name,
        "posting_identity": platform.identity,
        "target_url": platform.page_url,
        "day": post["date"],
        "text": post["text"],
        "images": images,
    }


def hashed(content: dict) -> bytes:
    """The bytes a request's hash covers: everything but where the images sit on disk."""
    return _canonical({**content, "images": [image["sha256"] for image in content["images"]]})


def _day(item: items.Item) -> date:
    return date.fromisoformat(item.day)


def _item(conn: sqlite3.Connection, subject: str) -> items.Item:
    found = items.of(conn, subject)
    if found is None:
        raise LookupError(f"no publish item for {subject}")
    return found


class SocialPost:
    """The kind `approvals` asks about every `publish_item:<id>` that is a social post."""

    name = KIND
    used_word = "claimed by a publish run"

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None:
        item = items.of(conn, subject)
        if item is None or item.kind != items.SOCIAL or item.state not in items.OPEN:
            return None
        content = social_content(conn, item.ref_id)
        return hashed(content) if content is not None else None

    def preview(self, conn: sqlite3.Connection, subject: str) -> approvals.Preview:
        """The card (AC-P1.1): the page and its URL, the day, the exact text, the image, the
        links in the text and the brand-gate result."""
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
        lines = [f"```\n{content['text'].strip()}\n```"]
        links = list(dict.fromkeys(_LINK.findall(content["text"])))
        lines.append("Links in the text: " + (", ".join(links) if links else "none"))
        if qa.get("passed"):
            lines.append(f"Brand check: passed on attempt {qa.get('attempt', 1)} of 2")
        images = [Path(image["path"]) for image in content["images"]]
        lines.append(f"{len(images)} image{'s' if len(images) != 1 else ''} attached, posted in this order." if images
                     else "No image.")
        return approvals.Preview(
            title=f"{platform.label} as {content['posting_identity']}: {content['target_url']} · "
                  f"{day:%a} {day.day} {day:%b %Y} · {item.label}",
            reason=f"the {platform.label} post for {day:%a} {day.day} {day:%b}"
                   + (f" ({theme.label})" if theme else "") + run,
            text="\n".join(lines),
            files=tuple(images),
        )

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> approvals.Deadlines:
        _, closes = limits.window_on(_day(_item(conn, subject)))
        return approvals.Deadlines(decide_by=closes, use_by=closes)

    def switched_off(self, conn: sqlite3.Connection, subject: str) -> str | None:
        from jura_growth.agents.social.settings import load

        item = _item(conn, subject)
        if not load().platforms[item.platform].browser:
            return f"{item.platform} is in draft mode, so nothing is posted through the browser"
        return None

    def on_skip(self, conn: sqlite3.Connection, subject: str) -> None:
        from jura_growth.agents.social import history

        item = _item(conn, subject)
        items.withdraw(conn, item, "skipped")
        try:
            history.skip(conn, _day(item), item.platform, "skipped by Ting Yu in #approvals")
        except ValueError:
            pass  # already published by hand: nothing left to skip

    def on_expire(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject), "expired")

    def on_lapse(self, conn: sqlite3.Connection, subject: str) -> None:
        items.withdraw(conn, _item(conn, subject), "lapsed")

    def superseded_note(self, conn: sqlite3.Connection, subject: str) -> str | None:
        item = items.of(conn, subject)
        if item is None:
            return None
        post = db.one(conn, "SELECT status FROM social_posts WHERE id = ?", (item.ref_id,))
        skipped = db.scalar(conn, "SELECT 1 FROM social_skips WHERE date = ? AND platform = ?", (item.day, item.platform))
        if post and post["status"] == "published":
            return "posted by hand"
        if skipped or (post and post["status"] == "skipped"):
            return "skipped by hand"
        if social_content(conn, item.ref_id) is not None:
            return "the post changed"
        return None


def kinds() -> dict[str, SocialPost]:
    return {KIND: SocialPost()}
