"""The social content agent (jurasolutions/prd/pending/prd-jura-social-content-2026-10-24.md).

Every morning at 07:00 SGT a headless Claude run (`prompts/social.md`) writes
one post for the day's theme, adapted for the LinkedIn page, the Facebook Page
and Instagram, and hands it to `jura-growth social submit`. The submit command
enforces the rules in code: the 14-day no-repeat rule, working source links,
the brand checker with each platform's own rules, image cards rendered from
the design system, the output folder, the `social_posts` log and delivery to
#social-drafts.

Blocks 1 and 2 are built. Block 3 (auto-publishing) is not: `publish_mode`
stays `draft`, and Ting Yu posts by hand. `social skip` already records skips
so block 3 can honour them.

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

    rows = db.rows(conn, "SELECT platform, status, published_at FROM social_posts WHERE date = ?", (day,))
    waiting = sorted(r["platform"] for r in rows if r["status"] == "draft")
    skipped_rows = {r["platform"] for r in rows if r["status"] == "skipped"}
    skips = {
        r["platform"] for r in db.rows(conn, "SELECT platform FROM social_skips WHERE date = ?", (day,))
    }
    skipped = len(skipped_rows | skips)
    published = db.scalar(
        conn, "SELECT count(*) FROM social_posts WHERE status = 'published' AND substr(published_at, 1, 10) = ?", (day,)
    ) or 0
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
        lines.append(
            f"Social: {len(waiting)} draft{'s' if len(waiting) != 1 else ''} waiting in #social-drafts "
            f"({', '.join(waiting)}), {skipped} skipped, {published} published"
        )
        brief.append(f"{len(waiting)} social draft{'s' if len(waiting) != 1 else ''} waiting")
    elif rows or skipped or published:
        lines.append(f"Social: no drafts waiting, {skipped} skipped, {published} published")
    if no_draft and not rows:
        figures["social_no_draft"] = no_draft["reason"]
        lines.append(f"Social: no draft today ({no_draft['reason']})")
        brief.append("no social draft today")
    return {"figures": figures, "lines": lines, "brief": brief}


RUN_UPDATE_CHANNEL = "social-drafts"


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
        return "today's drafts are already in #social-drafts, or every platform is skipped"
    done = [s for s in history.submissions(conn, day) if s["status"] in ("no-draft", "dropped")]
    if done:
        return "“No draft today” was already posted today"
    return None
