"""The social content agent (jurasolutions/prd/pending/prd-jura-social-content-2026-10-24.md).

Every morning at 07:00 SGT a headless Claude run (`prompts/social.md`) writes
one post for the day's theme, adapted for each platform switched on in
`config/social.yaml` (the Facebook Page and Instagram; LinkedIn was switched off
on 2026-10-29), and hands it to `jura-growth social submit`. The submit command
enforces the rules in code: the 14-day no-repeat rule, working source links,
the brand checker with each platform's own rules, image cards rendered from
the design system, the output folder, the `social_posts` log and delivery to
#social-drafts.

Blocks 1 and 2 are built. Block 3 became browser publishing
(prd-jura-browser-publishing-2026-10-25.md): a platform in `browser` mode gets
a publish item and an approval card for each draft, and the publish plug-in
posts it once Ting Yu approves. In `draft` mode Ting Yu posts by hand.

See docs/social.md.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

NAME = "social"
MIGRATIONS = Path(__file__).parent / "migrations"


def register(cli) -> None:
    from jura_growth.agents.social import commands

    commands.register(cli)


def channels() -> dict:
    from jura_growth.agents.social import checks

    return checks.channels()


def digest(conn: sqlite3.Connection, day: str) -> dict:
    from jura_growth import db

    from jura_growth.agents.social.settings import load

    # Only the platforms switched on count: a draft left for one switched off since (LinkedIn,
    # 2026-10-29) is never going out, so it isn't waiting.
    on = {p.name for p in load().enabled_platforms()}
    rows = [r for r in db.rows(conn, "SELECT platform, status, published_at FROM social_posts WHERE date = ?", (day,))
            if r["platform"] in on]
    waiting = sorted(r["platform"] for r in rows if r["status"] == "draft")
    skipped_rows = {r["platform"] for r in rows if r["status"] == "skipped"}
    skips = {
        r["platform"] for r in db.rows(conn, "SELECT platform FROM social_skips WHERE date = ?", (day,))
    } & on
    skipped = len(skipped_rows | skips)
    published = sum(
        1 for r in db.rows(
            conn, "SELECT platform FROM social_posts WHERE status = 'published' AND substr(published_at, 1, 10) = ?",
            (day,),
        ) if r["platform"] in on
    )
    no_draft = db.one(
        conn,
        "SELECT reason FROM social_submissions WHERE date = ? AND status IN ('no-draft', 'dropped') ORDER BY id DESC LIMIT 1",
        (day,),
    )

    figures = {
        "social_drafts_waiting": len(waiting),
        "social_skipped": skipped,
        "social_published": published,
    }
    lines, brief = [], []
    if waiting:
        lines.append(f"Social: {_where_they_wait(conn, day, waiting)}, {skipped} skipped, {published} published")
        brief.append(f"{len(waiting)} social draft{'s' if len(waiting) != 1 else ''} waiting")
    elif rows or skipped or published:
        lines.append(f"Social: no drafts waiting, {skipped} skipped, {published} published")
    if no_draft and not rows:
        figures["social_no_draft"] = no_draft["reason"]
        lines.append(f"Social: no draft ({no_draft['reason']})")  # no day: see MC X15
        brief.append("no social draft today")
    return {"figures": figures, "lines": lines, "brief": brief}


def _where_they_wait(conn: sqlite3.Connection, day: str, waiting: list[str]) -> str:
    """Where each draft really is: on a pending card in #approvals, in #social-drafts for a platform
    in draft mode, or nowhere, for a browser draft that got no card or whose card has closed."""
    from jura_growth import db

    from jura_growth.agents.social.settings import load

    carded = {r["platform"] for r in db.rows(
        conn, "SELECT i.platform FROM publish_items i JOIN approvals a ON a.subject = 'publish_item:' || i.id "
              "WHERE i.day = ? AND i.kind = 'social_post' AND a.kind = 'social-post' AND a.status = 'pending'", (day,))}
    platforms = load().platforms
    places = {"waiting in #approvals": [n for n in waiting if n in carded],
              "waiting in #social-drafts": [n for n in waiting if n not in carded and not platforms[n].browser],
              "with no card": [n for n in waiting if n not in carded and platforms[n].browser]}
    return ", ".join(f"{len(names)} draft{'s' if len(names) != 1 else ''} {where} ({', '.join(names)})"
                     for where, names in places.items() if names)


RUN_UPDATE_DISCORD_CHANNEL = "social-drafts"


def run_update(conn: sqlite3.Connection, run) -> list[str]:
    """The "Produced:" items of a social run: its drafts and their images."""
    from jura_growth import db
    from jura_growth.run_update import count

    rows = db.rows(conn, "SELECT image_paths FROM social_posts WHERE run_id = ?", (run.id,))
    images = sum(len(json.loads(r["image_paths"] or "[]")) for r in rows)
    produced = [count(len(rows), "draft")] if rows else []
    if images:
        produced.append(count(images, "image"))
    return produced


def permissions(job: str):
    """The `jura-growth` commands `prompts/social.md` uses. Skipping and
    marking drafts published are Ting Yu's steps."""
    if job != "social":
        return None
    from jura_growth.headless import Permissions

    return Permissions(commands=("social today", "social submit", "social no-draft", "social history", "check"))


def precheck(job: str, conn: sqlite3.Connection) -> str | None:
    if job != "social":
        return None
    from jura_growth import timeutil
    from jura_growth.agents.social import history, rhythm, submit
    from jura_growth.agents.social.settings import load

    settings = load()
    day = timeutil.today()
    reason = rhythm.posting_allowed(day, settings)
    if reason:
        return reason
    active, _ = submit.active_platforms(conn, day, settings)
    if not active:
        return "today's drafts are already in, or every platform is skipped"
    if all(settings.platforms[name].browser for name in active):
        from jura_growth.agents.publish import limits

        decide_by = limits.decide_by_on(day)
        if timeutil.now_sgt() >= decide_by:
            return f"today's posts had to be decided by {decide_by:%H:%M} SGT, so a draft written now couldn't be approved and posted"
    done = [s for s in history.submissions(conn, day) if s["status"] in ("no-draft", "dropped")]
    if done:
        return "“No draft today” was already posted today"
    return None
