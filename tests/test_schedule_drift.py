"""SC1: the one-pager says when scheduled jobs fire at the wrong SGT time by a steady amount.

The first half is a table on the pure check, `health.schedule_drift(starts, jobs, now)`. The clock
is Tue 2026-11-10 08:00 SGT. `last_two("22:00", "22:01")` is a job's last two runs, newest first:
the newest at the last 22:00 before now, the other at 22:01 the day before.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime, timedelta

import pytest

import mission_world as world
from jura_growth import config, db, health, mission, one_pager, paths, slots
from jura_growth.timeutil import SGT

NOW = datetime(2026, 11, 10, 8, 0, tzinfo=SGT)
JOBS = {
    "app-factory": {"schedule": {"daily": "06:30"}},
    "social": {"schedule": {"daily": "07:00"}},
    "one-pager": {"schedule": {"daily": "08:00"}},
    "heartbeat": {"schedule": {"daily": "12:00"}},
    "digest": {"schedule": {"daily": "17:30"}},
    "backup": {"schedule": {"daily": "23:30"}},
}


def on_clock(day: datetime, clock: str) -> datetime:
    hour, minute = clock.split(":")
    return day.replace(hour=int(hour), minute=int(minute))


def days_ago(days: int, clock: str) -> datetime:
    return on_clock(NOW - timedelta(days=days), clock)


def last_two(newest: str, older: str | None = None) -> list[datetime]:
    first = on_clock(NOW, newest)
    if first > NOW:
        first -= timedelta(days=1)
    return [first, on_clock(first, older or newest) - timedelta(days=1)]


def drift(**starts):
    return health.schedule_drift({job.replace("_", "-"): runs for job, runs in starts.items()}, JOBS, NOW)


def two_jobs(first: str, second: str) -> dict:
    return {"first": {"schedule": {"daily": first}}, "second": {"schedule": {"daily": second}}}


# --- steady drift -----------------------------------------------------------------


def test_two_jobs_steadily_nine_hours_early_are_flagged():
    found = drift(social=last_two("22:00", "22:01"), one_pager=last_two("23:00"))
    assert found is not None
    assert (found.job, found.due, found.ran, found.hours) == ("social", "07:00", "22:00", -9)


def test_every_daily_job_nine_hours_early_is_flagged():
    found = drift(
        app_factory=last_two("21:30"),
        social=last_two("22:00"),
        one_pager=last_two("23:00"),
        heartbeat=last_two("03:00"),
        digest=last_two("08:30"),
        backup=last_two("14:30"),
    )
    assert found is not None and found.hours == -9


def test_the_line_says_how_far_off_and_what_to_do_without_stating_the_cause_as_fact():
    line = health.Drift("social", "07:00", "22:00", -9).line
    assert "about 9 hours off" in line
    assert "`social` is due at 07:00 SGT and ran at 22:00 SGT" in line
    assert "Most likely launchd kept an old time zone. Restart the Mac once." in line
    assert "If it's still off tomorrow, run `jura-growth schedule install`." in line


@pytest.mark.parametrize(
    ("hours", "words"),
    [(-9.0, "about 9 hours off"), (1.0, "about 1 hour off"), (-1.0, "about 1 hour off"), (0.5, "about 0.5 hours off"), (2.5, "about 2.5 hours off")],
)
def test_the_hours_read_as_a_person_would_say_them(hours, words):
    assert words in health.Drift("social", "07:00", "08:00", hours).line


# --- a Mac that woke late, and jobs that don't agree ----------------------------------


def test_one_job_steadily_off_is_not_drift():
    assert drift(social=last_two("22:00")) is None


def test_two_jobs_steadily_off_by_different_amounts_are_not_drift():
    assert drift(social=last_two("22:00"), heartbeat=last_two("15:00")) is None


def test_a_mac_waking_at_a_different_time_each_day_is_not_drift():
    assert drift(social=last_two("09:30", "08:10"), app_factory=last_two("09:30", "08:10")) is None


def test_a_mac_waking_at_the_same_time_every_day_is_not_drift():
    """Each job is steadily off, but by a different amount, because their slots differ."""
    assert drift(social=last_two("09:30"), app_factory=last_two("09:30")) is None


def test_two_jobs_due_within_the_tolerance_of_each_other_could_be_one_wake():
    starts = {"first": last_two("09:30"), "second": last_two("09:30")}
    assert health.schedule_drift(starts, two_jobs("07:00", "07:05"), NOW) is None


def test_slots_either_side_of_midnight_count_as_close_together():
    starts = {"first": last_two("02:58"), "second": last_two("03:01")}
    assert health.schedule_drift(starts, two_jobs("23:58", "00:01"), NOW) is None


def test_jobs_due_just_past_the_tolerance_can_agree():
    starts = {"first": last_two("09:30"), "second": last_two("09:36")}
    assert health.schedule_drift(starts, two_jobs("07:00", "07:06"), NOW) is not None


# --- once the clock is right again ------------------------------------------------------


def test_a_run_off_with_the_latest_on_time_is_not_drift():
    assert drift(social=last_two("07:01", "22:00"), one_pager=last_two("08:00", "23:00")) is None


def test_the_morning_after_a_restart_is_not_drift():
    """Restarted on Monday at 20:00. Heartbeat and digest haven't run since, so their last two runs
    still agree, but the jobs that have run since are on time."""
    found = drift(
        heartbeat=last_two("03:00"),
        digest=last_two("08:30"),
        backup=[days_ago(1, "23:30"), days_ago(1, "14:30")],
        social=[days_ago(0, "07:00"), days_ago(1, "22:00")],
        one_pager=[days_ago(0, "08:00"), days_ago(1, "23:00")],
    )
    assert found is None


def test_an_on_time_run_before_the_drifted_runs_does_not_clear_them():
    found = drift(social=last_two("22:00"), one_pager=last_two("23:00"), heartbeat=[days_ago(2, "12:00")])
    assert found is not None and found.hours == -9


@pytest.mark.parametrize(
    ("woke", "still_flagged"),
    [
        ("06:15", True),  # the Mac's repeating 06:15 wake, 15 minutes before app-factory's slot
        ("06:24", True),
        ("06:25", False),  # the limit left on record: a wake this close reads as a fixed clock
        ("06:30", False),
        ("06:35", False),
        ("06:36", True),
        ("06:59", True),
    ],
)
def test_a_wake_near_a_slot_during_real_drift_only_clears_it_within_the_tolerance(woke, still_flagged):
    """Being on time is a stricter bar than not being off: launchd fires within seconds of a slot."""
    found = drift(social=last_two("22:00"), one_pager=last_two("23:00"), app_factory=[days_ago(0, woke)])
    assert (found is not None) == still_flagged

# --- one outlier ---------------------------------------------------------------------


def test_one_job_off_by_another_amount_does_not_hide_a_steady_drift():
    """The Mac sleeps through heartbeat's drifted 03:00 slot, so heartbeat always fires at wake."""
    found = drift(social=last_two("22:00"), one_pager=last_two("23:00"), heartbeat=last_two("07:00"))
    assert found is not None and found.hours == -9


def test_the_largest_group_wins_and_names_one_of_its_own_jobs():
    found = drift(heartbeat=last_two("15:00"), social=last_two("22:00"), one_pager=last_two("23:00"), backup=last_two("14:30"))
    assert found is not None and found.hours == -9 and found.job in ("social", "one-pager", "backup")


# --- stale runs ------------------------------------------------------------------------


def test_jobs_that_have_not_run_for_over_three_days_hold_no_alarm():
    found = drift(
        social=[days_ago(4, "22:00"), days_ago(5, "22:00")],
        one_pager=[days_ago(4, "23:00"), days_ago(5, "23:00")],
    )
    assert found is None


def test_a_run_past_three_days_does_not_count_as_one_of_the_two():
    found = drift(
        social=[days_ago(1, "22:00"), days_ago(4, "22:00")],
        one_pager=[days_ago(1, "23:00"), days_ago(4, "23:00")],
    )
    assert found is None


def test_a_run_exactly_three_days_old_still_counts():
    starts = {"first": [days_ago(2, "08:00"), days_ago(3, "08:00")], "second": [days_ago(2, "08:30"), days_ago(3, "08:30")]}
    found = health.schedule_drift(starts, two_jobs("17:00", "17:30"), NOW)
    assert found is not None and found.hours == -9


# --- the edges of the table -------------------------------------------------------------


def test_29_minutes_off_does_not_count_as_off_and_30_minutes_does():
    assert drift(social=last_two("07:29"), one_pager=[days_ago(1, "08:29"), days_ago(2, "08:29")]) is None
    found = drift(social=last_two("07:30"), one_pager=[days_ago(1, "08:30"), days_ago(2, "08:30")])
    assert found is not None and found.hours == 0.5


def test_a_second_run_5_minutes_away_is_steady_and_6_minutes_away_is_not():
    assert drift(social=last_two("22:00", "22:05"), one_pager=last_two("23:00")) is not None
    assert drift(social=last_two("22:00", "22:06"), one_pager=last_two("23:00")) is None


def test_runs_across_midnight_keep_their_sign_and_hours():
    late = drift(backup=[days_ago(0, "00:30"), days_ago(1, "00:30")], digest=last_two("18:30"))
    assert late is not None and (late.hours, late.job, late.due, late.ran) == (1, "digest", "17:30", "18:30")
    early = drift(app_factory=last_two("21:30"), social=last_two("22:00"))
    assert early is not None and early.hours == -9


def test_twelve_hours_off_agrees_across_the_wrap():
    """A run at 19:00 for a 07:00 slot and one at 18:59 sit either side of the ±12h wrap."""
    found = drift(social=last_two("19:00", "18:59"), one_pager=last_two("20:00"))
    assert found is not None and abs(found.hours) == 12


def test_a_job_with_one_run_or_none_is_ignored():
    assert drift(social=last_two("22:00")[:1], one_pager=last_two("23:00")) is None
    assert drift(social=[], one_pager=last_two("23:00")) is None


def test_schedules_that_are_not_one_daily_slot_are_ignored():
    jobs = {
        "publish": {"schedule": {"daily_every": {"start": "09:00", "end": "17:40", "minutes": 20}}},
        "scout-research": {"schedule": {"business_days": "09:00"}},
    }
    starts = {"publish": last_two("00:00"), "scout-research": last_two("00:00")}
    assert health.schedule_drift(starts, jobs, NOW) is None


def test_a_malformed_daily_is_skipped_and_the_other_jobs_still_count():
    jobs = {
        "nonsense": {"schedule": {"daily": "soon"}},
        "seconds": {"schedule": {"daily": "07:00:00"}},
        "hour": {"schedule": {"daily": "25:00"}},
        "minutes": {"schedule": {"daily": 420}},
        **JOBS,
    }
    starts = {name: last_two("22:00") for name in ("nonsense", "seconds", "hour", "minutes")}
    assert health.schedule_drift(starts, jobs, NOW) is None
    starts.update({"social": last_two("22:00"), "one-pager": last_two("23:00")})
    found = health.schedule_drift(starts, jobs, NOW)
    assert found is not None and found.job == "social"


# --- through the read model and the one-pager, with the shipped job list -----------------


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", NOW.isoformat())


def shipped_jobs() -> dict:
    return config.settings()["jobs"]


def growth_db_with(rows: dict[str, list[datetime]], *, status: str = "ok") -> None:
    """`rows` is each job's start times, newest first, as `last_two` gives them."""
    conn = db.connect()
    with conn:
        for job, runs in rows.items():
            for run in reversed(runs):
                conn.execute(
                    "INSERT INTO runs (agent, job, started_at, finished_at, status) VALUES (?, ?, ?, ?, ?)",
                    (job, job, run.isoformat(timespec="seconds"), run.isoformat(timespec="seconds"), status),
                )
    conn.close()


def read(now: datetime = NOW) -> mission.Snapshot:
    return mission.read(world.source(now.isoformat(), jobs=shipped_jobs()))


def needs_you(snapshot: mission.Snapshot) -> str:
    text = one_pager.text(snapshot)
    return text[text.index("**Needs you**") : text.index("**Approvals waiting**")]


def test_the_shipped_list_has_daily_jobs_far_enough_apart_for_the_check_to_fire():
    jobs = shipped_jobs()
    daily = {job: spec["schedule"]["daily"] for job, spec in jobs.items() if "daily" in spec["schedule"]}
    assert len(daily) >= 2
    starts = {job: [days_ago(1, due) - timedelta(hours=9), days_ago(2, due) - timedelta(hours=9)] for job, due in daily.items()}
    found = health.schedule_drift(starts, jobs, NOW)
    assert found is not None and found.hours == -9


def test_steady_drift_reaches_needs_you(clock):
    growth_db_with({"social": last_two("22:30", "22:31"), "one-pager": last_two("00:00")})
    snapshot = read()
    assert snapshot.db_state == mission.OK
    assert snapshot.drift is not None
    assert "about 9 hours off" in needs_you(snapshot)
    assert "Restart the Mac once" in needs_you(snapshot)
    assert snapshot.drift.line in health.strip(snapshot)


def test_a_late_wake_says_nothing(clock):
    growth_db_with({"social": last_two("09:30", "08:10"), "app-factory": last_two("09:30", "08:10")})
    snapshot = read()
    assert snapshot.drift is None
    assert "hours off" not in needs_you(snapshot)


def test_the_two_day_wake_says_nothing(clock):
    growth_db_with({"social": last_two("09:30"), "app-factory": last_two("09:30")})
    assert read().drift is None


def test_the_one_pagers_own_run_clears_the_line_after_a_restart(clock):
    growth_db_with({"heartbeat": last_two("03:00"), "digest": last_two("09:05"), "one-pager": [days_ago(1, "00:00"), days_ago(2, "00:00")]})
    assert read(days_ago(0, "08:55")).drift is not None  # before today's one-pager, the drift is real
    growth_db_with({"one-pager": [days_ago(0, "09:00")]})
    assert read(days_ago(0, "09:05")).drift is None


def test_a_one_pager_fired_by_a_late_wake_still_says_so(clock):
    """A Mac asleep overnight with a real drift: the one-pager fires at a 09:10 wake, 10 minutes
    past its slot. Its own run must not silence the one place the line appears."""
    growth_db_with(
        {
            "digest": last_two("09:05"),
            "backup": last_two("14:30"),
            "social": last_two("22:30"),
            "one-pager": [days_ago(0, "09:10")],
        }
    )
    snapshot = read(days_ago(0, "09:10"))
    assert "about 9 hours off" in needs_you(snapshot)


def test_a_skipped_run_counts_as_a_start(clock):
    growth_db_with({"social": last_two("22:30"), "one-pager": last_two("00:00")}, status="skipped")
    assert read().drift is not None


def test_the_line_comes_after_failures_and_before_missed_slots():
    missed = slots.SlotStatus("scout-send", datetime(2026, 11, 9, 10, 0, tzinfo=SGT), "missed")
    snapshot = mission.Snapshot(
        NOW,
        mission.OK,
        last_one_pager=datetime(2026, 11, 9, 8, 0, tzinfo=SGT),
        next_one_pager=datetime(2026, 11, 11, 8, 0, tzinfo=SGT),
        failures=(mission.Failure("community", datetime(2026, 11, 9, 7, 30, tzinfo=SGT), None),),
        drift=health.Drift("social", "07:00", "22:00", -9),
        slots={("scout-send", missed.at.date()): [missed]},
    )
    items = health.strip(snapshot)
    assert "failed on" in items[0]
    assert "hours off" in items[1]
    assert "missed 1 slot" in items[2]


def test_reading_drift_changes_no_file_and_never_opens_a_writable_connection(clock, monkeypatch):
    growth_db_with({"social": last_two("22:30"), "one-pager": last_two("00:00")})
    folders = world.watched()
    before = world.stat_snapshot(*folders)

    def refuse(*args, **kwargs):
        raise AssertionError("the read model opened a writable connection")

    monkeypatch.setattr(db, "connect", refuse)
    monkeypatch.setattr(db, "session", refuse)
    assert read().drift is not None
    assert world.stat_snapshot(*folders) == before


def read_after_install(installed_at, now: datetime = NOW) -> mission.Snapshot:
    source = world.source(now.isoformat(), jobs=shipped_jobs())
    return mission.read(dataclasses.replace(source, installed_at=installed_at))


def test_runs_on_the_old_times_from_before_an_install_are_not_drift(clock):
    """Morning brief final review M2: the times moved half an hour, and the runs before the install
    still sit on the old ones. Those aren't launchd keeping a wrong zone."""
    growth_db_with({"app-factory": [days_ago(1, "06:30"), days_ago(2, "06:30")], "social": [days_ago(1, "07:00"), days_ago(2, "07:00")]})
    assert read().drift is not None  # with no install time, they read as drift
    assert read_after_install(lambda job: days_ago(1, "12:00")).drift is None


def test_a_steady_drift_after_the_install_still_reports(clock):
    growth_db_with({"social": last_two("22:30"), "one-pager": last_two("00:00")})
    found = read_after_install(lambda job: days_ago(5, "12:00"))
    assert found.drift is not None and found.drift.hours == -9


def test_a_job_with_no_install_time_still_counts_beside_jobs_with_one(clock):
    growth_db_with({"backup": last_two("14:30"), "social": last_two("22:30"), "one-pager": last_two("00:00")})
    assert read_after_install(lambda job: None if job == "backup" else days_ago(0, "07:00")).drift is None  # only backup is left
    assert read_after_install(lambda job: None if job in ("backup", "social") else days_ago(0, "07:00")).drift is not None


def test_a_hot_journal_is_still_the_unfinished_write_state(clock, tmp_path):
    target = world.fresh_db()
    world.hot_journal(target, tmp_path / "d4")
    snapshot = read()
    assert snapshot.db_state == mission.UNFINISHED_WRITE
    assert snapshot.drift is None


def test_a_malformed_started_at_costs_the_check_and_nothing_else(clock):
    growth_db_with({"social": last_two("22:00"), "one-pager": last_two("23:00")})
    conn = db.connect()
    with conn:
        conn.execute("UPDATE runs SET started_at = 'not a date' WHERE id = (SELECT max(id) FROM runs WHERE job = 'social')")
    conn.close()
    snapshot = read()
    assert snapshot.db_state == mission.OK
    assert snapshot.drift is None
    assert snapshot.slots != {}


@pytest.mark.parametrize("stamp", ["not a date", "2026-11-09T99:00:00"])  # the second is the newest stamp before now in SQL
@pytest.mark.parametrize("job", ["social", "one-pager"])
@pytest.mark.parametrize("status", ["ok", "failed", "skipped", "running"])
def test_a_malformed_started_at_on_any_run_never_breaks_the_one_pager(clock, status, job, stamp):
    growth_db_with({"social": last_two("22:00"), "one-pager": last_two("23:00")})
    conn = db.connect()
    with conn:
        conn.execute("UPDATE runs SET started_at = ?, status = ? WHERE id = (SELECT max(id) FROM runs WHERE job = ?)", (stamp, status, job))
    conn.close()
    snapshot = read()
    assert snapshot.db_state == mission.OK
    assert one_pager.text(snapshot).startswith("**Tue 10 Nov")


def test_a_failed_run_with_a_malformed_started_at_leaves_the_other_failures_showing(clock):
    growth_db_with({"social": last_two("22:00"), "community": last_two("07:30")}, status="failed")
    conn = db.connect()
    with conn:
        conn.execute("UPDATE runs SET started_at = 'not a date' WHERE id = (SELECT max(id) FROM runs WHERE job = 'social')")
    conn.close()
    assert [failure.job for failure in read().failures] == ["community"]


def test_no_runs_at_all_is_no_line(clock):
    world.fresh_db()
    snapshot = read()
    assert snapshot.db_state == mission.OK
    assert snapshot.drift is None


def test_a_growth_db_without_a_runs_table_is_no_line(clock):
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(paths.db_path())
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()
    assert read().drift is None
