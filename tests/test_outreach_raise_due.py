"""`outreach raise-due` and its quiet 08:30 job (morning brief SC2, PRD amendment to MC A11).

Live mode: queued emails from an earlier day get their requests and cards before the 09:00 picture,
up to today's room. It sends nothing. In shadow mode, or paused, it does nothing, and the slot still
shows the job ran or was skipped.
"""

from __future__ import annotations

from datetime import date

import pytest

import mission_world as world
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import config, db, headless, mission, pause, paths, runner
from jura_growth.agents.outreach import approval

from test_scout_support import at, configure, fake_resend, live_ready, outreach_requests, scout_env, seed  # noqa: F401

FRIDAY = "2026-11-06T15:00:00+08:00"
TUESDAY_0830 = "2026-11-10T08:30:00+08:00"
TUESDAY = date(2026, 11, 10)
JOB = "outreach-requests"


@pytest.fixture
def sent(monkeypatch):
    return fake_resend(monkeypatch)


def leftovers(conn, monkeypatch, n: int = 3) -> None:
    """Emails queued on Friday in shadow mode, so none has a request."""
    at(monkeypatch, FRIDAY)
    for lead in range(1, n + 1):
        seed(conn, lead)
    assert outreach_requests(conn) == []


def live_with_room(monkeypatch, room: int) -> None:
    live_ready(monkeypatch)
    configure(monkeypatch, mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg", send={"per_day": room})
    at(monkeypatch, TUESDAY_0830)


def cards(double) -> list:
    return [r for r in double.requests if r.channel == "approvals" and r.method == "POST"]


def slot_status(job: str = JOB) -> str:
    source = world.source(TUESDAY_0830, jobs=config.settings()["jobs"])
    [slot] = mission.read(source).slots[(job, TUESDAY)]
    return slot.status


def test_live_with_three_queued_and_room_for_two_raises_two_requests_and_two_cards(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    outcome = runner.run(JOB)
    assert outcome.status == "ok"
    assert outcome.summary == "raised 2 approval requests"
    assert len(outreach_requests(conn, "pending")) == 2
    assert len(cards(discord_double)) == 2
    assert sent == []


def test_a_rerun_adds_nothing(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    runner.run(JOB)
    outcome = runner.run(JOB)
    assert outcome.status == "ok" and not outcome.summary
    assert len(outreach_requests(conn, "pending")) == 2
    assert len(cards(discord_double)) == 2
    assert sent == []


def test_it_raises_for_the_oldest_email_first(conn, monkeypatch, discord_double):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 1)
    runner.run(JOB)
    first = db.scalar(conn, "SELECT min(id) FROM outreach_messages WHERE status = 'queued'")
    [request] = outreach_requests(conn, "pending")
    assert request.subject == approval.subject_of(first)


def test_no_room_raises_nothing_and_stays_quiet(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 1)
    runner.run(JOB)  # takes the only room
    before = len(cards(discord_double))
    outcome = runner.run(JOB)
    assert not outcome.summary
    assert len(outreach_requests(conn, "pending")) == 1 and len(cards(discord_double)) == before
    assert sent == []


def test_shadow_mode_does_nothing_and_the_slot_reads_as_run(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    at(monkeypatch, TUESDAY_0830)
    outcome = runner.run(JOB)
    assert outcome.status == "ok" and not outcome.summary
    assert outreach_requests(conn) == [] and cards(discord_double) == [] and sent == []
    assert slot_status() == "ok"


def test_a_paused_outreach_does_nothing_and_the_slot_reads_as_skipped(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    pause.pause(conn, "outreach", "by hand", notify=False)
    assert runner.run(JOB).status == "skipped"
    assert outreach_requests(conn) == [] and cards(discord_double) == [] and sent == []
    assert slot_status() == "skipped"


def test_the_pause_file_does_nothing(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    paths.pause_file().write_text("holiday")
    assert runner.run(JOB).status == "skipped"
    assert outreach_requests(conn) == [] and cards(discord_double) == [] and sent == []


def test_a_live_problem_raises_nothing(conn, monkeypatch, discord_double, sent):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    monkeypatch.delenv("UNSUBSCRIBE_SECRET")
    assert approval.raising_problem(conn)
    runner.run(JOB)
    assert outreach_requests(conn) == [] and cards(discord_double) == [] and sent == []


def test_nothing_to_raise_leaves_one_quiet_trace_and_no_run_row(conn, monkeypatch, discord_double):
    live_with_room(monkeypatch, 2)
    outcome = runner.run(JOB)
    assert outcome.status == "ok" and not outcome.summary
    assert db.scalar(conn, "SELECT count(*) FROM runs WHERE job = ?", (JOB,)) == 0
    quiet = conn.execute("SELECT payload_json FROM events WHERE kind = 'run.quiet'").fetchall()
    assert len(quiet) == 1 and JOB in quiet[0][0]
    assert slot_status() == "ok"


def test_it_posts_only_cards_and_no_run_update(conn, monkeypatch, discord_double):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    before = len(discord_double.requests)  # adding the leads posted to #scout-leads
    runner.run(JOB)
    assert {r.channel for r in discord_double.requests[before:]} == {"approvals"}
    assert db.scalar(conn, "SELECT agent FROM runs WHERE job = ?", (JOB,)) == "outreach"


def test_a_weekend_is_not_its_day(conn, monkeypatch, discord_double):
    leftovers(conn, monkeypatch)
    live_with_room(monkeypatch, 2)
    at(monkeypatch, "2026-11-07T08:30:00+08:00")  # Saturday
    assert runner.run(JOB).status == "skipped"
    assert outreach_requests(conn) == []


def test_only_its_own_job_may_use_the_command():
    assert headless.permissions(JOB).commands == ("outreach raise-due",)
    for job, spec in config.settings()["jobs"].items():
        if spec["kind"] == "claude":
            assert not headless.may_use(job, "outreach raise-due"), job
