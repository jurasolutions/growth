"""QA 01's failing regression tests, the red step of the defect tickets (`issues/03` to `issues/08`).

Each test fails at 33fb30d for the reason its ticket gives. The developer who fixes a ticket moves
its test to the file that owns the behaviour, or keeps it here, and deletes this file once it is empty.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from click.testing import CliRunner

import picture_chrome as oracle
import picture_world as world
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import agents, db, discord, health, images, mission, one_pager, paths, picture, runner
from jura_growth.cli import cli
from test_scout_support import buttons, configure, fake_d1, live_ready, scout_env  # noqa: F401

NINE = "2026-11-10T09:00:00+08:00"
CHROME = images.Chrome(images.DEFAULT_CHROME)
needs_chrome = pytest.mark.skipif(images.chrome_path(images.DEFAULT_CHROME) is None, reason="Google Chrome is not installed")


# --- issues/03: a lock past db.connect's 30 seconds stops the morning post --------------------------


def locked(*args, **kwargs):
    """What `db.connect` raises once a writer has held growth.db past its 30-second wait. The ticket
    has the same failure with a real lock; a test can't spend the 30 seconds."""
    raise sqlite3.OperationalError("database is locked")


@pytest.fixture
def post_path(conn, discord_double, monkeypatch):  # noqa: F811
    monkeypatch.setenv("JURA_GROWTH_NOW", NINE)
    monkeypatch.setattr(one_pager, "OFFLINE", True)
    monkeypatch.setattr(mission, "read_patiently", lambda source: mission.read(source))  # no real waiting
    return discord_double


def test_the_command_gets_the_morning_post_out_past_the_write_connections_wait(post_path, monkeypatch):
    monkeypatch.setattr(db, "connect", locked)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert result.exception is None, repr(result.exception)
    assert len(post_path.posts("mission-control")) == 1


def test_the_job_gets_the_morning_post_out_past_the_write_connections_wait(post_path, monkeypatch):
    monkeypatch.setattr(db, "connect", locked)
    runner.run("one-pager", ignore_schedule=True)
    assert len(post_path.posts("mission-control")) == 1


def test_a_lock_after_delivery_doesnt_report_a_post_that_went_out_as_failed(post_path, monkeypatch):
    monkeypatch.setattr(discord, "_record", locked)
    result = CliRunner().invoke(cli, ["one-pager"])
    assert len(post_path.posts("mission-control")) == 1
    assert result.exception is None, repr(result.exception)


# --- issues/04: real Fix wordings lose what to do to the three-line clamp ---------------------------


def problem(kind: str, monkeypatch) -> None:
    """Make one real `send.live_problems()` wording the first problem."""
    live = dict(mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg")
    if kind == "buttons":
        buttons(monkeypatch, False)
    elif kind == "legal":
        configure(monkeypatch, **{**live, "legal_review_done": False})
    elif kind == "domain unset":
        configure(monkeypatch, **{**live, "sending_domain": ""})
    elif kind == "domain wrong":
        configure(monkeypatch, **{**live, "sending_domain": "example.com"})
    elif kind == "resend":
        monkeypatch.delenv("RESEND_API_KEY_OUTREACH")
    elif kind == "unsubscribe":
        monkeypatch.delenv("UNSUBSCRIBE_SECRET")
    elif kind == "do-not-contact":
        (paths.inputs_dir() / "do-not-contact.csv").unlink()
    elif kind == "d1":
        monkeypatch.delenv("D1_DATABASE_ID")


def outreach_health(conn) -> list[str]:
    module = next(m for m in agents.plugins() if getattr(m, "NAME", "") == "outreach")
    return module.health(conn)


def fix_rows(**fields) -> list[dict]:
    base = dict(slots=world.morning(), morning=world.figures(), yesterday=world.figures(), approvals=())
    return oracle.inspect(picture.html(world.snap(**{**base, **fields})), chrome=CHROME)["fixRows"]


@needs_chrome
@pytest.mark.parametrize("kind", ["buttons", "legal", "domain unset", "domain wrong", "resend", "unsubscribe", "do-not-contact", "d1"])
def test_each_real_line_about_live_outreach_fits_its_fix_row_whole(conn, scout_env, monkeypatch, kind):  # noqa: F811
    live_ready(monkeypatch)
    problem(kind, monkeypatch)
    lines = outreach_health(conn)
    assert len(lines) == 1, lines
    (row,) = fix_rows(plugin_lines=tuple(lines))
    assert not row["cut"], f"the picture cuts {lines[0]!r}"


@needs_chrome
def test_every_unset_setting_is_named_on_its_fix_row(conn):
    gaps = tuple(gap for gap in health.setup_gaps() if gap.of is None)
    assert len(gaps) >= 6
    (row,) = fix_rows(gaps=gaps)
    assert not row["cut"], f"the picture cuts {row['text']!r}"


# --- issues/05: the Dispatch contract still describes the grid in the post --------------------------


def test_the_dispatch_contract_no_longer_says_the_one_pager_carries_the_grid():
    contract = (paths.REPO_ROOT / "docs" / "dispatch-contract.md").read_text(encoding="utf-8")
    assert "with the 14-day grid" not in contract


# --- issues/06: a draft whose card was answered reads as "to post by hand" ---------------------------


@pytest.mark.parametrize("reading", [mission.Reading.APPROVED, mission.Reading.SKIPPED])
def test_an_answered_social_card_is_not_a_draft_to_post_by_hand(reading):
    snapshot = world.snap(
        slots=world.morning(),
        morning=world.figures(social_drafts_waiting=1),
        yesterday=world.figures(),
        approvals=(world.request(1, "social-post", reading=reading),),
    )
    assert "to post by hand" not in picture.verdict(snapshot)


# --- issues/07: a job silent two mornings gets two Fix lines -----------------------------------------


def test_a_job_silent_two_mornings_is_one_fix_line():
    today, yesterday = world.NOW.date(), (world.NOW - timedelta(days=1)).date()
    snapshot = world.snap(
        slots={
            ("social", yesterday): [world.slot("social", "missed", at=world.NOW.replace(hour=7, minute=30) - timedelta(days=1))],
            ("social", today): [world.slot("social", "due", at=world.NOW.replace(hour=7, minute=30))],
        },
        morning=world.figures(),
        yesterday=world.figures(),
        approvals=(),
        installs={"social": health.INSTALLED},
    )
    assert len([line for line in picture.fixes(snapshot) if "`social`" in line]) == 1


# --- issues/08: on install day, a job that is installed and has run reads "Not installed" ------------


def test_an_installed_job_with_a_run_on_record_never_reads_not_installed():
    """Install at 10:00; the job ran at its old time that morning; asked at 10:10."""
    now = world.NOW.replace(hour=10, minute=10)
    snapshot = world.snap(
        now,
        slots=world.morning(now=now, social="not installed"),
        morning=world.figures(),
        yesterday=world.figures(),
        approvals=(),
        installs={"social": health.INSTALLED},
        installed_at={"social": world.NOW.replace(hour=10, minute=0)},
    )
    row = next(r for r in picture.agent_rows(snapshot) if r.label == "Social")
    assert row.word != "Not installed", (row.word, row.detail)
