"""What has been posted: the 14-day no-repeat rule, skips, and the
`social_posts` log.

No story URL and no toolbox tool may come back within `caps.NO_REPEAT_DAYS`
(14) days. A story counts as used on the day of any draft that cited it,
whatever happened to the draft afterwards (published, skipped or left
waiting), so a story Ting Yu passed over doesn't return the next morning.
"Within 14 days" is inclusive: a story used on the 10th is free again on the
25th.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit

from jura_growth import caps, db, log, timeutil

TRACKING_PARAMS = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|cmpid|ocid|igshid|si)$", re.I)


def normalise_url(url: str) -> str:
    """A comparable key for a story URL: no scheme, no www, no tracking
    parameters, no fragment, no trailing slash, lower-case host."""
    candidate = url.strip()
    if not re.match(r"^https?://", candidate, re.I):
        candidate = "https://" + candidate
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parts.path) or ""
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    key = host + path
    if query:
        key += "?" + urlencode(sorted(query))
    return key


def window_start(day: date) -> date:
    return day - timedelta(days=caps.NO_REPEAT_DAYS)


def recent(conn: sqlite3.Connection, day: date, days: int | None = None) -> list[dict]:
    """Rows from the last `days` days (default the no-repeat window), up to and
    including `day`, oldest first."""
    start = day - timedelta(days=days if days is not None else caps.NO_REPEAT_DAYS)
    rows = db.rows(
        conn,
        "SELECT * FROM social_posts WHERE date >= ? AND date <= ? ORDER BY date, platform",
        (start.isoformat(), day.isoformat()),
    )
    for row in rows:
        row["image_paths"] = json.loads(row["image_paths"] or "[]")
        row["source_urls"] = json.loads(row["source_urls"] or "[]")
    return rows


def used_stories(conn: sqlite3.Connection, day: date) -> dict[str, tuple[str, str]]:
    """{normalised URL: (date, URL as written)} for stories in the window."""
    used: dict[str, tuple[str, str]] = {}
    for row in recent(conn, day):
        for url in row["source_urls"]:
            used.setdefault(normalise_url(url), (row["date"], url))
    return used


def used_tools(conn: sqlite3.Connection, day: date) -> dict[str, str]:
    """{tool slug: last date used} in the window."""
    used: dict[str, str] = {}
    for row in recent(conn, day):
        if row["tool_slug"]:
            used[row["tool_slug"]] = max(used.get(row["tool_slug"], ""), row["date"])
    return used


def used_themes(conn: sqlite3.Connection, day: date) -> dict[str, str]:
    """{date: theme} in the window."""
    return {row["date"]: row["theme"] for row in recent(conn, day)}


def repeats(conn: sqlite3.Connection, day: date, urls: list[str], tool: str | None) -> list[str]:
    """Reasons the no-repeat rule refuses these stories or this tool."""
    problems = []
    stories = used_stories(conn, day)
    for url in urls:
        hit = stories.get(normalise_url(url))
        if hit:
            problems.append(
                f"story already used on {hit[0]} ({url}); no story repeats within {caps.NO_REPEAT_DAYS} days"
            )
    if tool:
        last = used_tools(conn, day).get(tool)
        if last:
            problems.append(f"tool {tool!r} already featured on {last}; no tool repeats within {caps.NO_REPEAT_DAYS} days")
    return problems


# --- today's state -----------------------------------------------------------


def drafted_platforms(conn: sqlite3.Connection, day: date) -> set[str]:
    return {
        row["platform"]
        for row in db.rows(conn, "SELECT platform FROM social_posts WHERE date = ?", (day.isoformat(),))
    }


def skipped_platforms(conn: sqlite3.Connection, day: date) -> dict[str, str]:
    return {
        row["platform"]: row["reason"] or ""
        for row in db.rows(conn, "SELECT platform, reason FROM social_skips WHERE date = ?", (day.isoformat(),))
    }


def submissions(conn: sqlite3.Connection, day: date) -> list[dict]:
    return db.rows(conn, "SELECT * FROM social_submissions WHERE date = ? ORDER BY id", (day.isoformat(),))


def gated_attempts(conn: sqlite3.Connection, day: date) -> int:
    return sum(1 for s in submissions(conn, day) if s["status"] != "no-draft")


def record_submission(
    conn: sqlite3.Connection,
    day: date,
    *,
    attempt: int,
    status: str,
    theme: str | None = None,
    reason: str | None = None,
    issues: dict | None = None,
) -> None:
    conn.execute(
        "INSERT INTO social_submissions (date, attempt, status, theme, reason, issues_json, run_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            day.isoformat(), attempt, status, theme, reason,
            json.dumps(issues or {}, ensure_ascii=False), log.current_run_id(), timeutil.stamp(),
        ),
    )


# --- skip and publish --------------------------------------------------------


def skip(conn: sqlite3.Connection, day: date, platform: str, reason: str) -> str:
    """Skip one platform's post for `day`. Returns what happened."""
    row = db.one(conn, "SELECT id, status FROM social_posts WHERE date = ? AND platform = ?", (day.isoformat(), platform))
    if row and row["status"] == "published":
        raise ValueError(f"the {platform} post for {day} is already published; it can't be skipped")
    conn.execute(
        "INSERT INTO social_skips (date, platform, reason, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (date, platform) DO UPDATE SET reason = excluded.reason",
        (day.isoformat(), platform, reason, timeutil.stamp()),
    )
    if row:
        conn.execute(
            "UPDATE social_posts SET status = 'skipped', updated_at = ? WHERE id = ?", (timeutil.stamp(), row["id"])
        )
        outcome = "draft marked skipped" if row["status"] == "draft" else "already skipped"
    else:
        outcome = "no draft yet; it won't be drafted"
    log.event(conn, "social.skip", {"date": day.isoformat(), "platform": platform, "reason": reason, "outcome": outcome}, agent="social")
    return outcome


def mark_published(conn: sqlite3.Connection, day: date, platform: str, url: str | None) -> None:
    row = db.one(conn, "SELECT id, status FROM social_posts WHERE date = ? AND platform = ?", (day.isoformat(), platform))
    if not row:
        raise ValueError(f"no {platform} draft for {day}")
    if row["status"] == "skipped":
        raise ValueError(f"the {platform} post for {day} was skipped")
    now = timeutil.stamp()
    conn.execute(
        "UPDATE social_posts SET status = 'published', published_url = coalesce(?, published_url), "
        "published_at = coalesce(published_at, ?), updated_at = ? WHERE id = ?",
        (url, now, now, row["id"]),
    )
    log.event(conn, "social.published", {"date": day.isoformat(), "platform": platform, "url": url, "how": "by hand"}, agent="social")
