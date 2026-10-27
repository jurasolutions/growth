"""Builders for the publish queue (test strategy v3 §1: `tests/publish_world.py` holds the publish
builders). Dataset D11: social drafts for 2026-11-10, Facebook in `browser` mode, LinkedIn and
Instagram in `draft`.

The clock is BP's default, Tue 2026-11-10 (ISO week 46). A draft row can be written straight into
`social_posts` (`draft()`), or through `social submit` with the fixture drafts from
`test_social.py` (`submit()`), which needs that file's `env` fixture.
"""

from __future__ import annotations

import json
import struct
import zlib
from datetime import date
from pathlib import Path

from click.testing import CliRunner

from jura_growth import approvals, config, db, log, paths, timeutil
from jura_growth.agents.publish import claim, items
from jura_growth.cli import cli
from jura_growth.origin import Origin

DAY = date(2026, 11, 10)
MORNING = "2026-11-10T07:05:00+08:00"  # the social run
TEN = "2026-11-10T10:00:00+08:00"
PAGE_URL = "https://www.facebook.com/jura-test-page"
LINKEDIN_URL = "https://www.linkedin.com/company/jura-test-page"
INSTAGRAM_URL = "https://www.instagram.com/jura-test-page"
CONTROL_ID = "111"
TEXT = (
    "Chasing late invoices by hand? Your accounting software can send the first reminder for you.\n\n"
    "More small automations like this: https://jurasolutions.sg\n\n#SmallBusiness #Automation\n"
)


def png(width: int = 1200, height: int = 630, extra: bytes = b"") -> bytes:
    """A well-formed PNG header (and an IEND), enough for the attachment check. `extra` makes
    the bytes differ while the picture's size stays the same."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"tEXt", b"c\x00" + extra) + chunk(b"IEND", b"")


PNG = png()

# Instagram and LinkedIn (BP-04): a carousel day, each platform's own post address.
THURSDAY = date(2026, 11, 12)  # an Instagram carousel day in ISO week 46
INSTAGRAM_POST = "https://www.instagram.com/p/C0deAbc123/"
LINKEDIN_POST = "https://www.linkedin.com/feed/update/urn:li:activity:7254000000000000000/"


def slides(day: date = THURSDAY) -> list[Path]:
    """Three Instagram carousel slides for `day`, each with its own bytes, in order."""
    return [image(f"instagram-{n}-of-3-1080x1350.png", png(1080, 1350, extra=bytes([n])), day=day) for n in (1, 2, 3)]


def at(monkeypatch, moment: str):
    monkeypatch.setenv("JURA_GROWTH_NOW", moment)
    return timeutil.parse(moment)


def social_config(monkeypatch, *, browser=("facebook",), urls=None, **overrides) -> None:
    """`config/social.yaml` with the given platforms in `browser` mode and every page URL set."""
    real = config.agent_config
    urls = {"facebook": PAGE_URL, "linkedin": LINKEDIN_URL, "instagram": INSTAGRAM_URL, **(urls or {})}

    def patched(agent):
        base = dict(real(agent))
        if agent == "social":
            platforms = {name: dict(spec) for name, spec in (base.get("platforms") or {}).items()}
            for name, spec in platforms.items():
                spec["publish_mode"] = "browser" if name in browser else "draft"
                spec["page_url"] = urls.get(name)
            base["platforms"] = platforms
            base.update(overrides)
        return base

    monkeypatch.setattr(config, "agent_config", patched)


def image(name: str = "facebook-1200x630.png", data: bytes = PNG, day: date = DAY) -> Path:
    path = paths.outputs_dir() / "social" / day.isoformat() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def draft(conn, platform: str = "facebook", *, day: date = DAY, text: str = TEXT, images=None, attempt: int = 1) -> int:
    """A `social_posts` draft as `social submit` writes it (past the brand gate)."""
    files = [image(f"{platform}-1.png", day=day)] if images is None else list(images)
    qa = {"passed": True, "attempt": attempt, "issues": [], "words": 30, "hashtags": 2}
    cursor = conn.execute(
        "INSERT INTO social_posts (date, theme, platform, text, image_paths, source_urls, qa_json, status, run_id, created_at)"
        " VALUES (?, 'automation-tip', ?, ?, ?, '[]', ?, 'draft', NULL, ?)",
        (day.isoformat(), platform, text, json.dumps([str(f) for f in files]), json.dumps(qa), timeutil.stamp()),
    )
    return int(cursor.lastrowid or 0)


def item(conn, platform: str = "facebook", **given) -> tuple[items.Item, approvals.Approval]:
    """A draft, its publish item and its pending request."""
    post = draft(conn, platform, **given)
    made = items.create_social(conn, post, run_id=None)
    assert made.item is not None and made.approval is not None, made.why
    return made.item, made.approval


def decide(conn, approval, decision: str = "approve", monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv("CONTROL_DISCORD_USER_ID", CONTROL_ID)
    return approvals.decide(conn, approval.id, decision, actor=f"discord:{CONTROL_ID}", origin=Origin.ssh(),
                            source_ref=None, args={})


def approved(conn, monkeypatch, platform: str = "facebook", **given):
    found, approval = item(conn, platform, **given)
    assert decide(conn, approval, monkeypatch=monkeypatch).answer == "recorded"
    return found, approvals.get(conn, approval.id)


def run(conn, started: str | None = None, monkeypatch=None) -> int:
    """A publish run row, started at `started` (default now). Sets `JURA_GROWTH_RUN_ID`."""
    run_id = log.start_run(conn, "publish", "publish", started_at=started)
    if monkeypatch is not None:
        monkeypatch.setenv("JURA_GROWTH_RUN_ID", str(run_id))
    return run_id


def next_item(conn, run_id: int | None = None):
    return claim.next_item(conn, run_id=run_id)


def invoke(*args):
    return CliRunner().invoke(cli, list(args), catch_exceptions=False)


def fresh_state(approval_id: str) -> dict:
    """The approval and its item as a second connection sees them (committed only)."""
    conn = db.connect(migrate_now=False)
    try:
        record = approvals.get(conn, approval_id)
        found = items.of(conn, record.subject) if record else None
        return {"used_at": record.used_at if record else None, "used_by_run": record.used_by_run if record else None,
                "state": found.state if found else None}
    finally:
        conn.close()


def item_row(conn, item_id: int) -> dict:
    return db.one(conn, "SELECT * FROM publish_items WHERE id = ?", (item_id,))


def limits_window(day: date):
    from jura_growth.agents.publish import limits

    return limits.window_on(day)


# --- community items (BP-02b; dataset D10) ------------------------------------------------------
#
# Groups and planned posts are written straight into `community_groups` and `community_posts`, as
# the community run and `plan-add` leave them. `community.browser` is on (`community_config`).

GROUP_TEXT = (
    "Most invoice chasing follows the same three steps: a polite reminder, a firmer one, then a call. "
    "If your accounting software can send the first two on a schedule, you only make the call. "
    "What does your team do when an invoice is a week late?"
)
PROMO_TEXT = GROUP_TEXT + "\n\nWe write about this at Jura Solutions: https://jurasolutions.sg?utm_source=facebook_group"


def community_config(monkeypatch, *, browser: bool = True, **overrides) -> None:
    """`config/community.yaml` with `browser` set, over whatever `agent_config` already returns."""
    real = config.agent_config

    def patched(agent):
        base = dict(real(agent))
        if agent == "community":
            base["browser"] = browser
            base.update(overrides)
        return base

    monkeypatch.setattr(config, "agent_config", patched)


_groups = {"n": 0}


def group(conn, *, joined_as: str | None = "page", pages_allowed: str = "unknown", fit: str = "good fit",
          rules: str | None = "Promotion is welcome.", rules_confirmed: int = 1, promo_days: str | None = "any",
          post_days: str | None = "any", removed: int = 0, joined: int = 1, last_posted_at: str | None = None,
          join_status: str | None = None) -> int:
    """One Facebook group in the register, joined as the Jura Page with its rules and days
    confirmed (any day open) unless told otherwise. `joined_as=None` leaves it unrecorded, so it
    reads from the legacy `joined` flag."""
    _groups["n"] += 1
    number = _groups["n"]
    url = f"https://www.facebook.com/groups/sg-owners-{number}"
    cursor = conn.execute(
        "INSERT INTO community_groups (channel, name, slug, url, url_key, promo_rules, fit, fit_reason, joined, "
        "rules_confirmed, removed, promo_days_confirmed, post_days_confirmed, last_posted_at, joined_as_set, "
        "pages_allowed, join_status, created_at, updated_at) "
        "VALUES ('facebook', ?, ?, ?, ?, ?, ?, 'owners asking about admin', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (f"SG owners {number}", f"sg-owners-{number}", url, url.removeprefix("https://www."), rules, fit, joined,
         rules_confirmed, removed, promo_days, post_days, last_posted_at, joined_as, pages_allowed, join_status,
         timeutil.stamp(), timeutil.stamp()),
    )
    return int(cursor.lastrowid or 0)


def not_joined(conn, **given) -> int:
    """A good-fit group nobody has joined, its rules unconfirmed: one a join could be proposed for."""
    return group(conn, **{"joined_as": None, "joined": 0, "rules_confirmed": 0, "promo_days": None,
                          "post_days": None, **given})


def planned(conn, group_id: int, *, day: date = DAY, text: str = GROUP_TEXT, image: Path | None = None,
            status: str = "planned") -> int:
    """A planned community post, past `plan-add`'s checks and the brand gate."""
    week = f"{day.isocalendar().year}-W{day.isocalendar().week:02d}"
    qa = {"brand": "pass", "attempt": 1, "rules": "any day", "rules_ok": None, "sources": []}
    cursor = conn.execute(
        "INSERT INTO community_posts (group_id, week, planned_day, kind, text, image_path, qa_json, status, created_at)"
        " VALUES (?, ?, ?, 'post', ?, ?, ?, ?, ?)",
        (group_id, week, day.isoformat(), text, str(image) if image else None, json.dumps(qa), status, timeutil.stamp()),
    )
    return int(cursor.lastrowid or 0)


def community_item(conn, group_id: int | None = None, **given) -> tuple[items.Item, approvals.Approval]:
    """A planned post in a group joined as the Page, its item and its pending request."""
    group_id = group_id if group_id is not None else group(conn)
    made = items.create_community_post(conn, planned(conn, group_id, **given), run_id=None)
    assert made.item is not None and made.approval is not None, made.why
    return made.item, made.approval


def join_item(conn, group_id: int | None = None) -> tuple[items.Item, approvals.Approval]:
    """A good-fit group not joined as the Page, its join item and its pending request."""
    made = items.create_join(conn, group_id if group_id is not None else not_joined(conn), run_id=None)
    assert made.item is not None and made.approval is not None, made.why
    return made.item, made.approval


def asked(conn, join: items.Item) -> items.Item:
    """`join`, as BP-06's `publish done --outcome questions` leaves it, whether or not a run claimed
    it first: a claim left open would be an orphan to the next run (final review Sp1)."""
    conn.execute("UPDATE publish_items SET state = 'done', outcome = 'questions' WHERE id = ? "
                 "AND state IN ('ready', 'claimed')",
                 (join.id,))
    found = items.get(conn, join.id)
    assert found is not None
    return found


QUESTIONS = [
    {"question": "Why do you want to join?", "answer": "We help small teams automate admin, and we share what we learn."},
    {"question": "Do you agree to the group rules?", "answer": "Yes."},
]


def answers_item(conn, join: items.Item | None = None, answers=None) -> tuple[items.Item, approvals.Approval]:
    """The membership answers for a join, as `publish done --outcome questions` will raise them:
    a join still `ready` is first recorded as done by a run that met the questions."""
    join = asked(conn, join if join is not None else join_item(conn)[0])
    made = items.create_join_answers(conn, join, QUESTIONS if answers is None else answers, run_id=None)
    assert made.item is not None and made.approval is not None, made.why
    return made.item, made.approval
