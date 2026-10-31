"""What the watch run's tests share: a clock inside the window, a page's worth of Chrome calls, and
observation files as a model would write them. Dataset W of the test strategy.

The transcripts use the fake `claude` (`publish_fake.py`) with real `jura-growth` children, so the
job's allowlist and the path guard run for real.
"""

from __future__ import annotations

import json
from datetime import timedelta

import publish_transcripts as t
import publish_world as pw
from jura_growth import db, timeutil
from jura_growth.agents.inbox import watch

TEN = "2026-11-10T10:05:00+08:00"
ELEVEN = "2026-11-10T11:05:00+08:00"
IG_INBOX = "https://www.instagram.com/direct/inbox/"
FB_INBOX = "https://business.facebook.com/latest/inbox/all"
THREAD = "https://www.instagram.com/direct/t/1234567/"
FB_POST = "https://www.facebook.com/jurasolutionssg/posts/1234567"
COMMENT = FB_POST + "?comment_id=998877"
SAID = "Do you work with clinics in Tampines?"


def chrome(step: dict) -> dict:
    """A `publish_transcripts` step as a fake scenario step."""
    return {"chrome": step["name"].removeprefix(t.CHROME), "input": step["input"], "result": step["result"],
            "error": step["error"], "denied": step["denied"]}


def browser(*steps: dict) -> list[dict]:
    return [chrome(s) for s in steps]


def opening() -> list[dict]:
    return browser(*t.browser_check(), t.created())


def page_says(text: str, url: str = IG_INBOX) -> list[dict]:
    """A real read of a page that says `text`: navigate, then `get_page_text`."""
    return browser(t.opened(url), t.page("get_page_text", {}, text, url=url))


def surface(name: str, *, ok: bool = True, items: int = 0) -> dict:
    return {"type": "surface", "surface": name, "ok": ok, "items": items}


def all_surfaces(*, except_for: tuple[str, ...] = ()) -> list[dict]:
    return [surface(name) for name in watch.SURFACES if name not in except_for]


def dm(text: str = SAID, *, author: str = "Priya Nair", url: str = THREAD, surface_name: str = "instagram-primary",
       source: str = "instagram-dm", age_hours: float | None = 2, **given) -> dict:
    return {"type": "reaction", "source": source, "surface": surface_name, "url": url, "author": author, "text": text,
            "age_hours": age_hours, **given}


def comment(text: str = "Nice work, how much is it?", *, author: str = "Mei Ling", url: str = COMMENT,
            source: str = "facebook-comment", surface_name: str = "posts", age_hours: float | None = 2, **given) -> dict:
    return {"type": "reaction", "source": source, "surface": surface_name, "url": url, "author": author, "text": text,
            "age_hours": age_hours, **given}


def post_read(item: str, *, reactions: int = 0, shares: int = 0, comments: int = 0, **given) -> dict:
    return {"type": "post", "item": item, "reactions": reactions, "shares": shares, "comments": comments, **given}


def file_steps(observations, name: str = "seen.json") -> list[dict]:
    """Write `observations` to a scratch file and hand it to `inbox observe`, as a run does."""
    return [{"write": name, "text": json.dumps(observations)}, {"cli": ["inbox", "observe", "--file", "{WORK}/" + name]}]


def good_watch(observations: list[dict] = (), said: str = SAID) -> list[dict]:
    """A whole clean run: reads both platforms, records `observations` and every surface."""
    return [
        *opening(),
        *page_says(said, IG_INBOX),
        *page_says("The Page's inbox", FB_INBOX),
        *file_steps([*observations, *all_surfaces()]),
        *browser(t.closed()),
    ]


def baseline(conn) -> None:
    """As if an earlier run (number 0, which no real run has) had read every surface, so nothing here
    reads as a first run."""
    watch.observe(conn, 0, all_surfaces())
    watch.finish_surfaces(conn, 0, watch.PageReads(platforms=frozenset(watch.PLATFORMS)))


def published(conn, n: int = 1, *, platform: str = "facebook", days_ago: int = 1, url: str | None = None,
              kind: str = "social_post") -> list[str]:
    """`n` posts Jura published `days_ago` days before the clock, with their labels."""
    labels = []
    finished = timeutil.stamp(timeutil.now_sgt() - timedelta(days=days_ago))
    for _ in range(n):
        row = db.one(conn, "SELECT count(*) AS n FROM publish_items")
        number = row["n"] + 1
        label = f"P-{number:04d}"
        conn.execute(
            "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, "
            "state, outcome, post_url, created_at, claimed_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, 'Jura Solutions', '{}', ?, 'done', 'posted', ?, ?, ?, ?)",
            (label, kind, platform, str(number), pw.PAGE_URL, finished[:10], url or f"{FB_POST}{number}", finished, finished, finished),
        )
        labels.append(label)
    return labels
