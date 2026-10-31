"""The morning picture from growth.db (seam S2; MB6, MB7, MB13, S4, N3, N5).

`mission.read()` on temp data, and what the picture makes of it. Built snapshots are
`test_picture.py`; this file proves the road from the database and the plug-ins to the page.
"""

from __future__ import annotations

import dataclasses
import plistlib
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import mission_world as world
import picture_world
import sweep
from jura_growth import agents, approvals, mission, paths, picture, privacy, schedule, slots
from jura_growth.agents.outreach import replies, send
from jura_growth.agents.scout import settings as scout_settings
from jura_growth.timeutil import SGT
from test_discord_sweep import contact_lead

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


def _spend_tile(conn) -> str:
    return tiles(read())["Claude spend"]


def test_a_claude_job_that_ran_with_no_recorded_cost_shows_a_dash_for_spend(conn):
    """S4: abandoned runs leave `cost_usd` empty, and US$0.00 would be a guessed zero."""
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-09T07:30:30+08:00', 'failed')")
    conn.execute("INSERT INTO runs (agent, job, started_at, status, cost_usd) VALUES ('apps', 'app-factory', '2026-11-09T07:00:30+08:00', 'ok', 0.4)")
    assert _spend_tile(conn) == DASH


def test_recorded_spend_shows_and_nothing_else_leaves_a_dash(conn):
    jobs = {**JOBS, "backup": {"agent": "backup", "kind": "command", "schedule": {"daily": "23:30"}}}
    conn.execute("INSERT INTO runs (agent, job, started_at, status, cost_usd) VALUES ('social', 'social', '2026-11-09T07:30:30+08:00', 'ok', 0.41)")
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('apps', 'app-factory', '2026-11-09T07:00:30+08:00', 'skipped')")  # a skip costs nothing
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('backup', 'backup', '2026-11-09T23:30:00+08:00', 'ok')")  # a command job has no cost
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-08T07:30:30+08:00', 'failed')")  # another day
    assert tiles(read(jobs))["Claude spend"] == "US$0.41"


def test_a_day_with_no_claude_run_shows_a_real_zero(conn):
    assert _spend_tile(conn) == "US$0.00"


def test_the_long_form_spend_stays_a_number(conn):
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-09T07:30:30+08:00', 'failed')")
    assert read().yesterday.spend == 0.0 and read().yesterday.spend_recorded is False


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
    assert '<span class="n">–</span>' in picture.html(snapshot)


def test_a_missing_database_gives_the_bad_day_page():
    snapshot = read()
    assert snapshot.db_state == mission.MISSING
    assert [r.word for r in picture.agent_rows(snapshot)] == ["Not available"] * 5
    assert list(tiles(snapshot).values()) == [DASH] * 4
    assert '<span class="n">–</span>' in picture.html(snapshot)


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


def test_an_installed_job_with_no_record_at_all_reaches_fix(conn):
    """B1: `outreach-requests` on its first mornings, if launchd never fires it."""
    _current_plist("social")
    source = dataclasses.replace(world.source(NINE, jobs={"social": JOBS["social"]}), installed_at=lambda job: None)
    snapshot = mission.read(source)
    assert snapshot.installs["social"] == "installed"
    assert row(snapshot, "Social").word == "Didn't run"
    assert "Check `social`: no trace of its run today." in picture.fixes(snapshot)


def test_install_day_stays_clean_through_the_read(conn):
    """B1, with ticket 02's rule: the plist went in after the slot, so the slot isn't judged."""
    _current_plist("social")
    after_the_slot = datetime(2026, 11, 10, 8, 0, tzinfo=SGT)
    source = dataclasses.replace(world.source(NINE, jobs={"social": JOBS["social"]}), installed_at=lambda job: after_the_slot)
    snapshot = mission.read(source)
    assert snapshot.installed_at["social"] == after_the_slot
    assert (row(snapshot, "Social").word, row(snapshot, "Social").detail) == ("Not judged", "Installed today 08:00")
    assert not [line for line in picture.fixes(snapshot) if "no trace" in line]
    before_the_slot = dataclasses.replace(source, installed_at=lambda job: after_the_slot - timedelta(hours=1))
    assert row(mission.read(before_the_slot), "Social").word == "Didn't run"


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


@pytest.mark.parametrize("day", ["2026-11-09", "2026-11-10"], ids=["yesterday", "this morning"])
def test_a_lock_inside_a_plugins_digest_is_retried(day, conn, monkeypatch):
    """S2: both hook routes used to catch it, so `db_state` stayed ok and the figures went quietly."""
    real = plugin("social").digest
    calls = []

    def digest(conn, asked):
        calls.append(asked)
        if asked == day and calls.count(day) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real(conn, asked)

    monkeypatch.setattr(plugin("social"), "digest", digest)
    slept = []
    snapshot = mission.read_patiently(world.source(NINE, jobs=JOBS), sleep=slept.append)
    assert slept == [mission.LOCK_RETRY] and snapshot.db_state == mission.OK
    assert "social_drafts_waiting" in snapshot.morning.figures


def test_a_lock_inside_a_plugins_health_hook_is_retried_not_reported_as_broken(conn, monkeypatch):
    calls = []

    def health(conn):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return []

    monkeypatch.setattr(plugin("social"), "health", health, raising=False)
    slept = []
    snapshot = mission.read_patiently(world.source(NINE, jobs=JOBS), sleep=slept.append)
    assert slept == [mission.LOCK_RETRY] and snapshot.db_state == mission.OK
    assert not [line for line in snapshot.plugin_lines if "health check failed" in line]


def test_any_other_hook_failure_still_stays_inside_that_plugin(conn, monkeypatch):
    def broken(conn, *rest):
        raise sqlite3.OperationalError("no such table: social_posts")

    monkeypatch.setattr(plugin("social"), "digest", broken)
    monkeypatch.setattr(plugin("social"), "health", broken, raising=False)
    snapshot = read()
    assert snapshot.db_state == mission.OK
    assert [line for line in snapshot.plugin_lines if "health check failed" in line]


def _lock_during_learning(monkeypatch):
    """A real `BEGIN EXCLUSIVE` held only while the first read learns what to mask, then gone."""
    holder = sqlite3.connect(paths.db_path(), isolation_level=None)
    monkeypatch.setattr(mission, "BUSY_TIMEOUT", 0.01)
    real, calls = privacy.learn, []

    def learn(conn, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            return real(conn, **kwargs)
        holder.execute("BEGIN EXCLUSIVE")
        try:
            return real(conn, **kwargs)
        finally:
            holder.execute("ROLLBACK")

    monkeypatch.setattr(privacy, "learn", learn)
    return holder


def _named_request(conn) -> None:
    contact_lead(conn)
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by)"
        " VALUES (7, 'outreach-email', 's', 'h', 'pending', ?, '2026-11-10T08:00:00+08:00', '2026-11-10T16:30:00+08:00')",
        (f"Asked for {sweep.PERSON}",),
    )
    privacy.reset()


def test_a_lock_during_mask_learning_is_an_unfinished_write_and_never_an_unmasked_page(conn, monkeypatch):
    """B6: with `db_state` ok and the names unlearned, the page read "Asked for Jane Tan"."""
    _named_request(conn)
    holder = _lock_during_learning(monkeypatch)
    try:
        snapshot = read()
    finally:
        holder.close()
    assert snapshot.db_state == mission.UNFINISHED_WRITE
    assert sweep.PERSON not in picture.html(snapshot)


def test_the_post_path_retries_a_lock_during_learning_and_then_masks(conn, monkeypatch):
    _named_request(conn)
    holder = _lock_during_learning(monkeypatch)
    slept = []
    try:
        snapshot = mission.read_patiently(world.source(NINE, jobs=JOBS), sleep=slept.append)
    finally:
        holder.close()
    assert slept == [mission.LOCK_RETRY] and snapshot.db_state == mission.OK
    (request,) = snapshot.approvals
    assert request.reason.startswith("Asked for") and sweep.PERSON not in picture.html(snapshot)


def test_learning_without_a_lock_masks_the_name(conn):
    """The control for the two above: the plant is one the masking knows."""
    _named_request(conn)
    assert sweep.PERSON not in picture.html(read())


def test_other_callers_of_learn_still_swallow_a_plugin_error(conn, monkeypatch):
    def broken(conn):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(plugin("social"), "privacy_terms", broken, raising=False)
    privacy.learn(conn)  # a message still goes: "one plug-in never stops a message"


def test_past_its_patience_the_post_path_gives_the_bad_day_snapshot(monkeypatch):
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


# --- B2: drafts on draft-mode platforms --------------------------------------------------------------


def _draft_today(conn, platform: str) -> None:
    conn.execute(
        "INSERT INTO social_posts (date, theme, platform, text, status, created_at) VALUES ('2026-11-10', 't', ?, 'b', 'draft', ?)",
        (platform, NINE),
    )


@pytest.mark.parametrize("mode, by_hand", [("draft", 1), ("browser", 0)])
def test_only_a_draft_on_a_draft_mode_platform_is_to_post_by_hand(mode, by_hand, conn, monkeypatch):
    """Final B2: a `browser` platform's draft goes out through its card, answered or not. With no
    card it waits for nothing (approvals first, ticket 05), so only the hand post counts as waiting."""
    from jura_growth.agents.social import settings as social_settings

    real = social_settings.load()
    platforms = [dataclasses.replace(p, publish_mode=mode) for p in real.enabled_platforms()]
    monkeypatch.setattr(social_settings, "load", lambda: SimpleNamespace(enabled_platforms=lambda: platforms))
    _draft_today(conn, platforms[0].name)
    figures = plugin("social").digest(conn, "2026-11-10")["figures"]
    assert figures["social_drafts_waiting"] == by_hand
    assert figures["social_drafts_by_hand"] == by_hand
    assert read().morning.figures["social_drafts_by_hand"] == by_hand


# --- N5: live mode with something stopping it -----------------------------------------------------


def test_live_mode_with_a_problem_is_a_fix_line(conn, monkeypatch):
    monkeypatch.setattr(scout_settings, "mode", lambda: "live")
    monkeypatch.setattr(send, "live_problems", lambda: ["sending_domain is not set in config/scout.yaml", "another"])
    lines = [line for line in read().plugin_lines if "live outreach" in line]
    assert lines == ["Run `jura-growth outreach status`: 2 things stop live outreach, so no email is asked for.\n"
                     "sending_domain is not set in config/scout.yaml."]


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
