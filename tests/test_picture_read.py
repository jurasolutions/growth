"""The morning picture from growth.db (seam S2; MB6, MB7, MB13, S4, N3, N5).

`mission.read()` on temp data, and what the picture makes of it. Built snapshots are
`test_picture.py`; this file proves the road from the database and the plug-ins to the page.
"""

from __future__ import annotations

import plistlib
import sqlite3

import pytest

import mission_world as world
import picture_world
from jura_growth import agents, approvals, mission, paths, picture, schedule, slots
from jura_growth.agents.outreach import replies, send
from jura_growth.agents.scout import settings as scout_settings

NINE = "2026-11-10T09:00:00+08:00"
DASH = "–"
JOBS = {"social": {"agent": "social", "kind": "claude", "schedule": {"daily": "07:30"}},
        "app-factory": {"agent": "apps", "kind": "claude", "schedule": {"daily": "07:00"}}}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", NINE)


def read(jobs=None) -> mission.Snapshot:
    return mission.read(world.source(NINE, jobs=JOBS if jobs is None else jobs))


def plugin(name: str):
    return next(module for module in agents.plugins() if getattr(module, "NAME", "") == name)


def tiles(snapshot) -> dict[str, str]:
    return {caption: figure for figure, caption in picture.yesterday_tiles(snapshot)}


def row(snapshot, label: str) -> picture.AgentRow:
    return next(r for r in picture.agent_rows(snapshot) if r.label == label)


# --- what the read model now carries -----------------------------------------------------------


def test_the_snapshot_holds_todays_figures_and_each_requests_reason(conn):
    world.approval(conn, 7, "outreach-email")
    snapshot = read()
    assert snapshot.morning.day == "2026-11-10" and snapshot.morning.figures["leads_added"] == 0
    assert snapshot.yesterday.day == "2026-11-09" and snapshot.yesterday.figures["emails_sent"] == 0
    (request,) = snapshot.approvals
    assert request.reason == "a test asked"


def test_a_requests_reason_is_masked(conn):
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by)"
        " VALUES (7, 'outreach-email', 's', 'h', 'pending', 'Write to jane.tan@example.com.sg today',"
        " '2026-11-09T09:12:00+08:00', '2026-11-10T16:30:00+08:00')"
    )
    (request,) = read().approvals
    assert "jane.tan@" not in request.reason and "j***@example.com.sg" in request.reason


def test_a_figure_is_masked_however_deep_it_sits(conn, monkeypatch):
    """N3: a nested value passed unmasked, and the pixels can't be re-masked after the snapshot."""
    nested = {"figures": {"deep": {"list": [{"who": "jane.tan@example.com.sg"}], "kept": 3}, "top": "jane.tan@example.com.sg"}, "lines": []}
    monkeypatch.setattr(plugin("social"), "digest", lambda conn, day: nested)
    figures = read().morning.figures
    assert figures["deep"]["list"][0]["who"] == "j***@example.com.sg"
    assert figures["deep"]["kept"] == 3
    assert figures["top"] == "j***@example.com.sg"


# --- MB7: every route that used to print a guessed zero -------------------------------------------


def test_a_plugin_whose_digest_raises_shows_dashes_not_zeros(conn, monkeypatch):
    def broken(conn, day):
        raise RuntimeError("boom")

    monkeypatch.setattr(plugin("social"), "digest", broken)
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-10T07:30:30+08:00', 'ok')")
    snapshot = read()
    assert row(snapshot, "Social").detail == DASH
    assert tiles(snapshot)["social posts"] == DASH
    assert tiles(snapshot)["emails sent"] == "0"
    assert "Nothing needs you" not in picture.verdict(snapshot)


def test_a_recorded_zero_from_the_database_stays_zero(conn):
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-10T07:30:30+08:00', 'ok')")
    snapshot = read()
    assert row(snapshot, "Social").detail == "0 drafts waiting"
    assert tiles(snapshot)["social posts"] == "0"


def test_reply_detection_off_shows_a_dash_and_on_shows_the_count(conn, monkeypatch):
    monkeypatch.setattr(replies, "enabled", lambda: False)
    off = read()
    assert off.yesterday.figures["reply_detection"] is False
    assert tiles(off)["replies"] == DASH
    monkeypatch.setattr(replies, "enabled", lambda: True)
    assert tiles(read())["replies"] == "0"


def _holding_the_lock(monkeypatch):
    world.fresh_db()
    holder = sqlite3.connect(paths.db_path(), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(mission, "BUSY_TIMEOUT", 0.01)
    return holder


def test_a_locked_database_gives_the_bad_day_page(monkeypatch):
    holder = _holding_the_lock(monkeypatch)
    try:
        snapshot = read()
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert [(r.word, r.detail) for r in picture.agent_rows(snapshot)] == [("Not available", "")] * 5
    assert picture.later_today(snapshot) == ["Not available"]
    assert list(tiles(snapshot).values()) == [DASH] * 4
    assert any("unfinished write" in line for line in picture.fixes(snapshot))
    assert "to fix" in picture.verdict(snapshot) and "to decide" not in picture.verdict(snapshot)
    assert "Not available: growth.db has an unfinished write" in picture.html(snapshot)


def test_a_missing_database_gives_the_bad_day_page():
    snapshot = read()
    assert snapshot.db_state == mission.MISSING
    assert [r.word for r in picture.agent_rows(snapshot)] == ["Not available"] * 5
    assert list(tiles(snapshot).values()) == [DASH] * 4


# --- MB6, through the classifier ---------------------------------------------------------------


def _ran_yesterday_only(conn) -> None:
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-09T07:30:30+08:00', 'ok')")


def _current_plist(job: str) -> None:
    folder = schedule.launch_agents_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{schedule.label(job)}.plist", "wb") as handle:
        plistlib.dump(schedule.plist(job, dict(JOBS[job])), handle)


def test_a_job_with_no_trace_this_morning_reads_didnt_run_and_reaches_fix(conn):
    _ran_yesterday_only(conn)
    _current_plist("social")
    snapshot = read({"social": JOBS["social"]})
    assert snapshot.installs["social"] == "installed"
    assert slots.day_cell(snapshot.slots[("social", snapshot.now.date())]).status == "due"  # the classifier's word stands
    assert (row(snapshot, "Social").word, row(snapshot, "Social").detail) == ("Didn't run", "No trace of its 07:30 run")
    assert "Check `social`: no trace of its run today." in picture.fixes(snapshot)


def test_a_job_whose_plist_is_out_of_date_gets_no_didnt_run_line(conn):
    """Between the pull and `schedule install`, old-time runs land in yesterday's slot."""
    _ran_yesterday_only(conn)
    snapshot = read({"social": JOBS["social"]})
    assert snapshot.installs["social"] == "out of date"
    assert row(snapshot, "Social").word == "Out of date"
    assert not [line for line in picture.fixes(snapshot) if "no trace" in line]
    assert [line for line in picture.fixes(snapshot) if line.startswith("Run `jura-growth schedule install` again")]


# --- MB13: read-only ------------------------------------------------------------------------------


def test_the_read_calls_no_kinds_content_or_preview(conn, monkeypatch):
    world.load_fortnight(conn)
    world.approval(conn, 7, "outreach-email")
    registered = approvals.kinds()
    assert registered
    calls = []
    for name, entry in registered.items():
        for method in ("content", "preview"):
            monkeypatch.setattr(type(entry.kind), method, lambda *args, _n=name, _m=method, **kwargs: calls.append((_n, _m)), raising=False)
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    snapshot = mission.read(world.source(NINE))
    picture.html(snapshot)
    assert calls == []
    assert snapshot.morning is not None
    assert world.stat_snapshot(*folders) == before


# --- S4: a held lock at 09:00, beside publish's first slot --------------------------------------


def test_the_post_path_retries_a_held_lock_and_reads_once_it_clears(monkeypatch):
    holder = _holding_the_lock(monkeypatch)
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 2:
            holder.execute("ROLLBACK")

    try:
        snapshot = mission.read_patiently(world.source(NINE), sleep=sleep)
    finally:
        holder.close()
    assert snapshot.db_state == mission.OK
    assert len(slept) == 2


def test_past_sixty_seconds_the_post_path_gives_the_bad_day_snapshot(monkeypatch):
    holder = _holding_the_lock(monkeypatch)
    slept = []
    monkeypatch.setattr(mission, "BUSY_TIMEOUT", 2)
    real = mission.open_read_only

    def quick(path):  # the fake clock counts the wait; the real one needn't spend it
        conn = real(path)
        conn.execute("PRAGMA busy_timeout = 0")
        return conn

    monkeypatch.setattr(mission, "open_read_only", quick)
    try:
        snapshot = mission.read_patiently(world.source(NINE), sleep=slept.append)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert snapshot.db_state == mission.UNFINISHED_WRITE
    assert slept, "it never waited"
    assert sum(slept) + 2 * (len(slept) + 1) <= mission.LOCK_PATIENCE + mission.LOCK_RETRY + mission.BUSY_TIMEOUT
    assert sum(slept) + mission.BUSY_TIMEOUT * len(slept) >= mission.LOCK_PATIENCE - mission.LOCK_RETRY - mission.BUSY_TIMEOUT


def test_an_ordinary_read_never_waits(monkeypatch):
    holder = _holding_the_lock(monkeypatch)
    monkeypatch.setattr(mission.time, "sleep", lambda seconds: pytest.fail("the plain read slept"))
    try:
        assert mission.read(world.source(NINE)).db_state == mission.UNFINISHED_WRITE
    finally:
        holder.execute("ROLLBACK")
        holder.close()


def test_a_healthy_database_is_read_once(conn, monkeypatch):
    calls = []
    real = mission.read
    monkeypatch.setattr(mission, "read", lambda source: calls.append(1) or real(source))
    mission.read_patiently(world.source(NINE), sleep=lambda seconds: pytest.fail("it slept"))
    assert calls == [1]


# --- N5: live mode with something stopping it -----------------------------------------------------


def test_live_mode_with_a_problem_is_a_fix_line(conn, monkeypatch):
    monkeypatch.setattr(scout_settings, "mode", lambda: "live")
    monkeypatch.setattr(send, "live_problems", lambda: ["sending_domain is not set in config/scout.yaml", "another"])
    lines = [line for line in read().plugin_lines if "live outreach" in line]
    assert lines == ["Clear what stops live outreach, or no email is asked for: sending_domain is not set in config/scout.yaml."]


def test_live_mode_with_nothing_wrong_and_shadow_mode_say_nothing(conn, monkeypatch):
    monkeypatch.setattr(send, "live_problems", lambda: ["a problem"])
    monkeypatch.setattr(scout_settings, "mode", lambda: "shadow")
    assert not [line for line in read().plugin_lines if "live outreach" in line]
    monkeypatch.setattr(scout_settings, "mode", lambda: "live")
    monkeypatch.setattr(send, "live_problems", lambda: [])
    assert not [line for line in read().plugin_lines if "live outreach" in line]


def test_fixtures_and_the_real_read_agree_on_the_figures_the_page_needs(conn):
    """The built fixtures must carry the keys the plug-ins really record, or they prove nothing."""
    snapshot = read()
    recorded = {**snapshot.morning.figures, **snapshot.yesterday.figures}
    assert set(picture_world.RECORDED) <= set(recorded), set(picture_world.RECORDED) - set(recorded)
