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
