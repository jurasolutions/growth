"""Seam S2: the one-pager's read model, `mission.read(Source)` (MC-08, ADR 0002).

It opens growth.db with `mode=ro` and `query_only`, fetches into plain data and
closes. A hot journal, a lock, a missing file or a missing table is a value in
the snapshot, never a repair and never a crash. Dataset D1 is the fortnight
(`fortnight.py`) at Tue 2026-11-10 08:00 SGT.
"""

from __future__ import annotations

import fcntl
import sqlite3

import pytest

import fortnight
import mission_world as world
from jura_growth import db, mission, paths, slots


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T08:00:00+08:00")


@pytest.fixture
def no_writes(monkeypatch):
    """AC-M13.2: once armed (after the test has built its data), `db.connect`,
    `db.session` and `paths.writable` fail the test, and a lock is spied on."""
    calls, locked = [], []

    def refuse(name):
        def fail(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"the read model called {name}")

        return fail

    def arm():
        for name in ("connect", "session"):
            monkeypatch.setattr(db, name, refuse(f"db.{name}"))
        monkeypatch.setattr(paths, "writable", refuse("paths.writable"))
        real_flock = fcntl.flock
        monkeypatch.setattr(fcntl, "flock", lambda *a: locked.append(a) or real_flock(*a))

    yield arm
    assert calls == [], calls
    assert locked == [], "the read model took a lock"


def read_unchanged(src=None):
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    snapshot = mission.read(src or world.source())
    assert world.stat_snapshot(*folders) == before, "the read model changed a file"
    return snapshot


# --- growth.db states -------------------------------------------------------------


def test_a_missing_growth_db_is_a_value_and_nothing_is_created(no_writes):
    no_writes()
    snapshot = read_unchanged()
    assert snapshot.db_state == mission.MISSING
    assert not paths.db_path().exists()
    assert snapshot.slots == {}
    assert snapshot.approvals is None


def test_a_hot_journal_is_shown_as_an_unfinished_write_and_never_rolled_back(tmp_path, no_writes):
    target = world.fresh_db()
    world.hot_journal(target, tmp_path / "d4")
    journal = paths.data_dir() / "growth.db-journal"
    before = (target.read_bytes(), journal.read_bytes())
    no_writes()
    with_journal = read_unchanged()
    assert with_journal.db_state == mission.UNFINISHED_WRITE
    assert (target.read_bytes(), journal.read_bytes()) == before


def test_without_a_hot_journal_the_same_database_reads_cleanly(no_writes):
    world.fresh_db()
    no_writes()
    snapshot = read_unchanged()
    assert snapshot.db_state == mission.OK
    assert snapshot.missing_migrations == ()


def test_a_locked_database_is_the_same_unfinished_write(monkeypatch):
    world.fresh_db()
    holder = sqlite3.connect(paths.db_path(), isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        monkeypatch.setattr(mission, "BUSY_TIMEOUT", 0.05)
        snapshot = read_unchanged()
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert snapshot.db_state == mission.UNFINISHED_WRITE


def test_a_part_migrated_database_names_what_is_missing_and_reads_the_rest(no_writes):
    path = paths.data_dir() / "growth.db"  # dataset D5: core migrations only
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path, isolation_level=None)
    raw.execute("CREATE TABLE schema_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    raw.executescript((db.CORE_MIGRATIONS / "0001_core.sql").read_text())
    raw.execute("INSERT INTO schema_migrations VALUES ('core/0001_core.sql', '2026-11-01T00:00:00+08:00')")
    raw.close()
    no_writes()
    before = world.stat_snapshot(*world.watched())
    snapshot = mission.read(world.source())
    assert world.stat_snapshot(*world.watched()) == before
    assert snapshot.db_state == mission.OK
    assert "core/0003_approvals.sql" in snapshot.missing_migrations
    assert any(m.startswith("outreach/") for m in snapshot.missing_migrations)
    assert snapshot.approvals is None  # the table isn't there: a line, not a crash
    with sqlite3.connect(path) as check:
        assert [r[0] for r in check.execute("SELECT id FROM schema_migrations")] == ["core/0001_core.sql"]


# --- slots: what the classifier is fed ----------------------------------------------


def statuses(snapshot, job, day=fortnight.TODAY):
    return [(s.at.strftime("%H:%M"), s.status) for s in snapshot.slots[(job, day)]]


@pytest.fixture
def d1(conn):
    world.load_fortnight(conn)
    return conn


EARLY = {"early": {"agent": "early", "schedule": {"daily": "06:30"}}}


def test_the_fortnight_gives_todays_slot_statuses(d1):
    snapshot = mission.read(world.source("2026-11-10T11:05:00+08:00"))
    send = dict(statuses(snapshot, "scout-send"))
    assert [send[t] for t in ("09:30", "10:00", "10:10", "10:20", "11:00", "11:10")] == [
        "ok", "missed", "missed", "ok", "ok", "upcoming"
    ]
    assert statuses(snapshot, "app-factory") == [("06:30", "ok")]
    assert statuses(snapshot, "scout-research") == [("09:00", "due")]
    assert statuses(snapshot, "social") == [("07:00", "running")]
    assert statuses(snapshot, "backup", fortnight.DAYS[2]) == [("23:30", "not installed")]  # 2026-10-30
    assert statuses(snapshot, "scout-research", fortnight.DAYS[12]) == []  # the observed holiday
    assert sorted(day for job, day in snapshot.slots if job == "backup") == fortnight.DAYS


def test_a_record_in_both_events_and_the_mirror_reaches_the_classifier_once(d1, monkeypatch):
    world.mirror_line({"ts": "2026-11-10T10:40:02+08:00"}, raw='{"ts": "2026-11-10T10:40:02+08:00", "kind": "run.qu')
    fed = []
    real = slots.classify

    def spy(jobs, records, *args, **kwargs):
        fed.extend(records)
        return real(jobs, fed, *args, **kwargs)

    monkeypatch.setattr(slots, "classify", spy)
    mission.read(world.source("2026-11-10T11:05:00+08:00"))
    keys = [record.key for record in fed]
    assert len(keys) == len(set(keys))
    assert keys.count(("run.quiet", "2026-11-06T10:00:03+08:00", "scout-send", None)) == 1
    assert ("run.skipped", "2026-11-05T10:20:01+08:00", "scout-send", "PAUSE file: holiday") in keys  # mirror only


def test_a_job_that_ran_before_the_window_shows_its_first_slots_as_missed_not_not_installed(conn):
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('early', 'early', '2026-10-01T06:30:02+08:00', 'ok')")
    snapshot = mission.read(world.source("2026-11-10T11:05:00+08:00", jobs=EARLY))
    assert statuses(snapshot, "early", fortnight.DAYS[0]) == [("06:30", "missed")]


def test_an_earlier_record_only_in_the_mirror_counts_too(conn):
    world.mirror_line({"ts": "2026-10-02T06:30:01+08:00", "kind": "run.skipped", "payload": {"job": "early", "reason": "PAUSE file: away"}})
    snapshot = mission.read(world.source("2026-11-10T11:05:00+08:00", jobs=EARLY))
    assert statuses(snapshot, "early", fortnight.DAYS[0]) == [("06:30", "missed")]


def test_a_job_not_loaded_with_history_keeps_its_past_and_lists_as_not_installed(d1):
    snapshot = mission.read(world.source("2026-11-10T11:05:00+08:00", installed=lambda job: job != "scout-send"))
    send = dict(statuses(snapshot, "scout-send"))
    assert (send["10:00"], send["10:20"], send["11:10"]) == ("missed", "ok", "not installed")
    assert snapshot.installs["scout-send"] == "not installed"
    assert snapshot.installs["app-factory"] != "not installed"


def test_install_state_compares_the_loaded_plist_with_the_schedule(conn):
    import plistlib

    from jura_growth import schedule

    jobs = dict(list(fortnight.JOBS.items())[:2])
    first, second = jobs
    folder = schedule.launch_agents_dir()
    folder.mkdir(parents=True)
    with open(folder / f"{schedule.label(first)}.plist", "wb") as handle:
        plistlib.dump(schedule.plist(first, jobs[first]), handle)
    with open(folder / f"{schedule.label(second)}.plist", "wb") as handle:
        plistlib.dump({**schedule.plist(second, jobs[second]), "StartCalendarInterval": [{"Hour": 3, "Minute": 0}]}, handle)
    snapshot = mission.read(world.source(jobs=jobs))
    assert snapshot.installs == {first: "installed", second: "out of date"}


# --- approval requests, judged by the clock ------------------------------------------


def requests(snapshot):
    return {request.id: request for request in snapshot.approvals}


def test_a_request_past_its_decide_by_is_lapsed_by_the_clock_without_a_write(conn, no_writes):
    world.approval(conn, 7, "social-post", requested_at="2026-11-09T09:00:00+08:00", decide_by="2026-11-09T18:00:00+08:00")
    world.approval(conn, 8, "social-post", decide_by="2026-11-10T18:00:00+08:00")
    no_writes()
    snapshot = read_unchanged()
    assert requests(snapshot)["A-0007"].reading == mission.Reading.LAPSED
    assert requests(snapshot)["A-0008"].reading == mission.Reading.WAITING
    assert conn.execute("SELECT status FROM approvals WHERE id = 7").fetchone()[0] == "pending"


def test_each_stored_status_reads_as_what_it_means_now(conn):
    approved = {"status": "approved", "decided_at": "2026-11-09T10:00:00+08:00", "decided_origin": "ssh"}
    world.approval(conn, 1, "fake", **approved, use_by="2026-11-12T16:30:00+08:00")
    world.approval(conn, 2, "fake", **approved, use_by="2026-11-10T07:59:59+08:00")  # past its use-by, not written yet
    world.approval(conn, 3, "fake", status="expired", decided_at="2026-11-09T10:00:00+08:00", decided_origin="ssh",
                   use_by="2026-11-10T07:00:00+08:00", closed_at="2026-11-10T07:00:01+08:00", close_reason="approved but not used in time")
    world.approval(conn, 4, "fake", status="expired", closed_at="2026-11-10T07:30:00+08:00", close_reason="not approved in time")
    world.approval(conn, 5, "fake", **approved, use_by="2026-11-12T16:30:00+08:00", used_at="2026-11-10T07:40:00+08:00")
    world.approval(conn, 6, "fake", status="skipped", decided_at="2026-11-10T07:41:00+08:00")
    found = requests(mission.read(world.source()))
    assert {id_: r.reading for id_, r in found.items()} == {
        "A-0001": mission.Reading.APPROVED,
        "A-0002": mission.Reading.LAPSED_UNUSED,
        "A-0003": mission.Reading.LAPSED_UNUSED,
        "A-0004": mission.Reading.LAPSED,
        "A-0005": mission.Reading.USED,
        "A-0006": mission.Reading.SKIPPED,
    }


def test_a_request_reading_has_its_own_names_apart_from_the_stored_statuses():
    """Code review 08 ST-2: `mission` no longer rebinds `approvals`' status names, and CONTEXT.md
    defines the reading with each of its values. A slot list is never called `states`."""
    import re

    from jura_growth import approvals

    for name in ("APPROVED", "SKIPPED", "SUPERSEDED", "WAITING", "LAPSED", "LAPSED_UNUSED", "USED"):
        assert not hasattr(mission, name), name
    assert hasattr(approvals, "APPROVED") and "reading" in {f for f in mission.Request.__dataclass_fields__}
    assert "state" not in mission.Request.__dataclass_fields__
    context = (paths.REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    entry = context.split("**Request reading**:", 1)[1].split("\n\n", 1)[0]
    for value in mission.Reading.ALL:
        assert f"**{value}**" in entry, value
    for name in ("mission.py", "health.py", "one_pager.py"):
        source = (paths.REPO_ROOT / "jura_growth" / name).read_text(encoding="utf-8")
        assert not re.search(r"\bstates\b", source), name


def test_only_live_requests_and_those_closed_since_the_last_one_pager_are_read(conn):
    world.approval(conn, 1, "fake", status="expired", closed_at="2026-11-09T08:59:00+08:00", close_reason="not approved in time")
    world.approval(conn, 2, "fake", status="skipped", decided_at="2026-11-09T08:00:00+08:00")
    world.approval(conn, 3, "fake", status="skipped", decided_at="2026-11-09T09:00:01+08:00")
    snapshot = mission.read(world.source("2026-11-10T09:00:00+08:00"))
    assert snapshot.last_one_pager.isoformat() == "2026-11-09T09:00:00+08:00"
    assert snapshot.next_one_pager.isoformat() == "2026-11-11T09:00:00+08:00"
    assert list(requests(snapshot)) == ["A-0003"]


def window_world(conn) -> None:
    """Things that happened on Mon 9 Nov after its 09:00 one-pager."""
    world.approval(conn, 160, "outreach-email", status="expired", decided_at="2026-11-09T10:00:00+08:00", decided_origin="ssh",
                   use_by="2026-11-09T16:30:00+08:00", closed_at="2026-11-09T16:31:00+08:00", close_reason="approved but not used in time")
    conn.execute("INSERT INTO discord_posts (channel, ts, content_hash, delivered) VALUES ('alerts', '2026-11-09T12:00:00+08:00', 'h', 0)")
    outbox = paths.data_dir() / "discord-outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    (outbox / "2026-11-09.jsonl").write_text('{"ts": "2026-11-09T12:00:00+08:00", "content": "x"}\n')


def one_pager_run(conn, started_at: str, status: str = "ok") -> None:
    conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('digest', 'one-pager', ?, ?)", (started_at, status))


@pytest.mark.parametrize("now", ["2026-11-10T09:00:05+08:00", "2026-11-10T09:04:00+08:00"])
def test_the_scheduled_one_pager_running_late_still_reports_since_the_one_before(conn, now):
    window_world(conn)
    one_pager_run(conn, "2026-11-09T09:00:03+08:00")
    one_pager_run(conn, "2026-11-10T09:00:02+08:00", status="running")  # this run itself
    snapshot = mission.read(world.source(now))
    assert snapshot.last_one_pager.isoformat() == "2026-11-09T09:00:03+08:00"
    assert snapshot.next_one_pager.isoformat() == "2026-11-11T09:00:00+08:00"
    assert requests(snapshot)["A-0160"].reading == mission.Reading.LAPSED_UNUSED
    assert (snapshot.undelivered, snapshot.outbox) == (1, 1)


def test_without_a_recorded_one_pager_the_window_starts_at_the_slot_before_this_one(conn):
    window_world(conn)
    snapshot = mission.read(world.source("2026-11-10T09:00:05+08:00"))
    assert snapshot.last_one_pager.isoformat() == "2026-11-09T09:00:00+08:00"
    assert "A-0160" in requests(snapshot)
    assert (snapshot.undelivered, snapshot.outbox) == (1, 1)


def test_an_on_request_one_pager_reports_since_this_mornings(conn):
    assert mission.read(world.source("2026-11-10T11:05:00+08:00")).last_one_pager.isoformat() == "2026-11-10T09:00:00+08:00"
    one_pager_run(conn, "2026-11-10T09:00:02+08:00")
    assert mission.read(world.source("2026-11-10T11:05:00+08:00")).last_one_pager.isoformat() == "2026-11-10T09:00:02+08:00"


def test_after_a_missed_day_the_window_starts_at_the_last_one_pager_that_ran(conn):
    window_world(conn)
    one_pager_run(conn, "2026-11-09T08:00:03+08:00")  # Mon ran; Tue's was slept through
    snapshot = mission.read(world.source("2026-11-11T08:00:05+08:00"))
    assert snapshot.last_one_pager.isoformat() == "2026-11-09T08:00:03+08:00"
    assert "A-0160" in requests(snapshot)
    assert (snapshot.undelivered, snapshot.outbox) == (1, 1)


def test_a_one_pager_run_from_long_ago_does_not_stretch_the_window_past_a_week(conn):
    one_pager_run(conn, "2026-10-01T09:00:03+08:00")
    assert mission.read(world.source("2026-11-10T09:00:05+08:00")).last_one_pager.isoformat() == "2026-11-09T09:00:00+08:00"


def test_an_unposted_card_is_read_as_unposted(conn):
    world.approval(conn, 1, "fake", posted_at=None)
    assert requests(mission.read(world.source()))["A-0001"].posted is False


# --- the other health-strip facts -------------------------------------------------------


def test_the_pause_file_and_paused_agents_are_read(conn):
    paths.pause_file().write_text("holiday\n")
    conn.execute("INSERT INTO pause_flags VALUES ('outreach', 1, '3 failed runs in a row', '2026-11-09T10:00:00+08:00')")
    conn.execute("INSERT INTO pause_flags VALUES ('social', 0, 'resumed', '2026-11-09T10:00:00+08:00')")
    snapshot = mission.read(world.source())
    assert snapshot.pause_file == "holiday"
    assert snapshot.paused == (("outreach", "3 failed runs in a row"),)


def test_an_empty_pause_file_still_pauses(conn):
    paths.pause_file().write_text("")
    assert mission.read(world.source()).pause_file == "PAUSE file present"


def test_failures_are_each_jobs_latest_run_and_any_in_the_last_24_hours(conn):
    rows = [
        ("old-fail", "2026-11-01T06:30:00+08:00", "failed", "boom"),  # still its latest finished run
        ("old-fail", "2026-11-09T09:00:00+08:00", "skipped", None),
        ("recent", "2026-11-10T05:00:00+08:00", "failed", "timed out"),  # 3 hours ago, then fine
        ("recent", "2026-11-10T06:00:00+08:00", "ok", None),
        ("fixed", "2026-11-08T06:00:00+08:00", "failed", "gone"),
        ("fixed", "2026-11-09T06:00:00+08:00", "ok", None),
    ]
    for job, started, status, error in rows:
        conn.execute("INSERT INTO runs (agent, job, started_at, status, error) VALUES (?, ?, ?, ?, ?)", (job, job, started, status, error))
    failures = mission.read(world.source()).failures
    assert [(f.job, f.at.strftime("%d %H:%M"), f.error) for f in failures] == [
        ("old-fail", "01 06:30", "boom"),
        ("recent", "10 05:00", "timed out"),
    ]


def test_undelivered_posts_and_outbox_lines_since_the_last_one_pager_are_counted(conn):
    for ts, delivered in (("2026-11-09T08:00:00+08:00", 0), ("2026-11-09T10:00:00+08:00", 0), ("2026-11-10T08:00:00+08:00", 1)):
        conn.execute("INSERT INTO discord_posts (channel, ts, content_hash, delivered) VALUES ('alerts', ?, 'h', ?)", (ts, delivered))
    outbox = paths.data_dir() / "discord-outbox"
    outbox.mkdir(parents=True)
    (outbox / "2026-11-09.jsonl").write_text(
        '{"ts": "2026-11-09T08:59:00+08:00", "content": "old"}\n{"ts": "2026-11-09T12:00:00+08:00", "content": "x"}\n'
    )
    (outbox / "2026-11-10.jsonl").write_text('{"ts": "2026-11-10T06:00:00+08:00", "content": "y"}\n{"ts": "2026-11')
    snapshot = mission.read(world.source("2026-11-10T09:00:00+08:00"))
    assert (snapshot.undelivered, snapshot.outbox) == (1, 2)


def test_setup_gaps_come_from_the_shared_function(conn):
    from jura_growth import health

    assert mission.read(world.source()).gaps == tuple(health.setup_gaps())


def test_a_plugin_health_line_is_read_and_a_write_inside_the_hook_raises(conn, monkeypatch):
    import types

    from jura_growth import agents

    raised = []

    def writes(read_only):
        try:
            read_only.execute("INSERT INTO pause_flags VALUES ('x', 1, 'x', 'x')")
        except sqlite3.OperationalError as error:
            raised.append(str(error))
            raise
        return ["never"]

    real = agents.plugins()
    monkeypatch.setattr(agents, "plugins", lambda: (
        *real,
        types.SimpleNamespace(NAME="builder", health=lambda read_only: ["Build it: APP-014 (approval A-0153)"]),
        types.SimpleNamespace(NAME="writer", health=writes),
    ))
    lines = mission.read(world.source()).plugin_lines
    assert "Build it: APP-014 (approval A-0153)" in lines
    assert "writer: its health check failed (OperationalError)" in lines
    assert raised and "readonly" in raised[0]
    assert conn.execute("SELECT count(*) FROM pause_flags").fetchone()[0] == 0


# --- yesterday and spend (X15) -------------------------------------------------------


def test_spend_is_recorded_cost_either_side_of_sgt_midnight_and_yesterday_is_the_digest(conn):
    from jura_growth import digest

    costs = [
        ("2026-11-08T23:59:59+08:00", 9.0),  # the day before yesterday
        ("2026-11-09T00:00:00+08:00", 0.25),
        ("2026-11-09T23:59:59+08:00", 0.5),
        ("2026-11-10T00:00:00+08:00", 1.0),
        ("2026-11-10T07:00:00+08:00", None),  # still running: nothing recorded, nothing projected
    ]
    for started, cost in costs:
        conn.execute("INSERT INTO runs (agent, job, started_at, status, cost_usd) VALUES ('social', 'social', ?, 'ok', ?)", (started, cost))
    snapshot = mission.read(world.source())
    assert (snapshot.yesterday.day, snapshot.yesterday.spend, snapshot.spend_today) == ("2026-11-09", 0.75, 1.0)
    assert snapshot.yesterday.lines == tuple(digest.build(conn, "2026-11-09")["lines"])
    assert digest.spend(conn, "2026-11-09") == 0.75


# --- the whole path, with the writers patched to fail (AC-M13.2) ---------------------


def test_the_whole_one_pager_on_the_fortnight_never_reaches_a_writer_or_a_lock(d1, no_writes):
    from jura_growth import one_pager

    world.approval(d1, 101, "outreach-email", posted_at=None)
    d1.execute("INSERT INTO pause_flags VALUES ('outreach', 1, 'paused by hand', '2026-11-09T10:00:00+08:00')")
    migrations = d1.execute("SELECT id, applied_at FROM schema_migrations ORDER BY id").fetchall()
    paths.pause_file().write_text("holiday")
    no_writes()
    folders = world.watched()
    before = world.stat_snapshot(*folders)
    text = one_pager.text(mission.read(world.source("2026-11-10T11:05:00+08:00")))
    assert world.stat_snapshot(*folders) == before
    assert "A-0101" in text and "The PAUSE file is in place" in text
    assert d1.execute("SELECT id, applied_at FROM schema_migrations ORDER BY id").fetchall() == migrations
