"""The social content agent (jurasolutions/prd/pending/prd-jura-social-content-2026-10-24.md).

Every morning at 07:30 SGT a headless Claude run (`prompts/social.md`) writes
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


def pending(conn: sqlite3.Connection) -> list:
    """`jura-growth pending`: drafts for today onward. Only the platforms switched on count, as in
    the digest: a draft for one switched off is never going out."""
    from jura_growth import agents, db, timeutil

    from jura_growth.agents.social.settings import load

    on = {p.name for p in load().enabled_platforms()}
    rows = db.rows(conn, "SELECT platform FROM social_posts WHERE status = 'draft' AND date >= ?", (timeutil.today_str(),))
    drafts = sum(1 for row in rows if row["platform"] in on)
    return [agents.PendingItem(agents.GROWTH, f"{drafts} social draft{'s' if drafts != 1 else ''} for today onward.", order=agents.COUNT)] if drafts else []


def digest(conn: sqlite3.Connection, day: str) -> dict:
    from jura_growth import db

    from jura_growth.agents.social.settings import load

    # Only the platforms switched on count: a draft left for one switched off since (LinkedIn,
    # 2026-10-29) is never going out, so it isn't waiting.
    platforms = load().enabled_platforms()
    on = {p.name for p in platforms}
    rows = [r for r in db.rows(conn, "SELECT platform, status, published_at FROM social_posts WHERE date = ?", (day,))
            if r["platform"] in on]
    drafts = sorted(r["platform"] for r in rows if r["status"] == "draft")
    browser = {p.name for p in platforms if p.browser}  # a `browser` platform's draft goes through its card
    places, waiting = _where_they_are(conn, day, drafts, browser) if drafts else ({}, [])
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
        "social_drafts_by_hand": len(places.get(_BY_HAND, [])),
        "social_skipped": skipped,
        "social_published": published,
    }
    lines, brief = [], []
    if waiting:
        brief.append(f"{len(waiting)} social draft{'s' if len(waiting) != 1 else ''} waiting")
    if places:
        said = ", ".join(f"{len(names)} draft{'s' if len(names) != 1 else ''} {place} ({', '.join(names)})"
                         for place, names in places.items())
        lines.append(f"Social: {said}, {skipped} skipped, {published} published")
    elif rows or skipped or published:
        lines.append(f"Social: no drafts waiting, {skipped} skipped, {published} published")
    if no_draft and not rows:
        figures["social_no_draft"] = no_draft["reason"]
        lines.append(f"Social: no draft ({no_draft['reason']})")  # no day: see MC X15
        brief.append("no social draft today")
    return {"figures": figures, "lines": lines, "brief": brief}


_ON_A_CARD, _BY_HAND, _NO_CARD = "waiting in #approvals", "waiting in #social-drafts", "with no card"
_APPROVED, _HELD, _CLAIMED = "approved, waiting on a publish run", "approved, held by draft mode", "claimed by a publish run"
_EXPIRED, _CLOSED = "expired", "closed"
_PLACES = (_ON_A_CARD, _BY_HAND, _APPROVED, _HELD, _CLAIMED, _NO_CARD, _EXPIRED, _CLOSED)


def _where_they_are(conn: sqlite3.Connection, day: str, drafts: list[str], browser: set[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Each place a draft really is, in `_PLACES` order, and the drafts still waiting."""
    from jura_growth.agents.publish import items

    requests = items.requests_by_platform(conn, day)
    found: dict[str, list[str]] = {}
    waiting = []
    for name in drafts:
        place, waits = _place(conn, requests.get(name), name in browser)
        found.setdefault(place, []).append(name)
        if waits:
            waiting.append(name)
    return {place: found[place] for place in _PLACES if place in found}, waiting


def _place(conn: sqlite3.Connection, request, browser: bool) -> tuple[str, bool]:
    """Where a draft is, from its newest request, and whether anything is still going to happen to
    it. A closed card isn't "no card", and a card the sweep refused will never go out. A card
    Discord hasn't taken yet still waits: the heartbeat posts it."""
    from jura_growth import approvals, cards, timeutil

    if request is None:  # never a card: too late, no image, or from before browser mode
        return (_NO_CARD, False) if browser else (_BY_HAND, True)
    now = timeutil.now_sgt()
    if request.status == approvals.PENDING:
        if timeutil.parse(request.decide_by) <= now:
            return _EXPIRED, False  # closed, whether or not this read may write the lapse
        if request.posted_at:
            return _ON_A_CARD, True
        return _NO_CARD, cards.refusal(conn, request.id) is None
    if request.status != approvals.APPROVED:
        return (_EXPIRED if request.status == approvals.EXPIRED else _CLOSED), False
    if request.used_at:
        return _CLAIMED, False
    if request.use_by and timeutil.parse(request.use_by) <= now:
        return _EXPIRED, False
    return (_APPROVED, True) if browser else (_HELD, False)


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
