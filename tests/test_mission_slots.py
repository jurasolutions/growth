"""The slot classifier (MC-07): literal records in, slot statuses out.

Dataset D1 (the fortnight, `tests/fortnight.py`) from the test strategy: the
clock is frozen at Tue 2026-11-10 11:05 SGT. Sun 2026-11-08 is Deepavali and
Mon 2026-11-09 its observed holiday. Every test runs with the Mac's zone set
to Singapore, UTC and New York, because slots are SGT whatever the Mac says.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime

import pytest

import fortnight
from fortnight import DAYS as FORTNIGHT, JOBS, NOW, TODAY
from jura_growth import config, locks, runner, slots
from jura_growth.timeutil import SGT

D1 = fortnight.records()


@pytest.fixture(autouse=True, params=["Asia/Singapore", "UTC", "America/New_York"])
def mac_zone(request):
    """Set `TZ` alone and put back only `TZ`, so conftest's `isolated`
    fixture keeps its own environment until its teardown has run."""
    before = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    yield request.param
    if before is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = before
    time.tzset()


def quiet(job, ts, reason=None):
    payload = {"job": job, "started_at": ts}
    if reason:
        payload["reason"] = reason
    return slots.Record.from_event({"ts": ts, "kind": slots.QUIET, "payload": payload})


def run(job, started_at, status="ok", summary=None):
    return slots.Record.from_run({"job": job, "started_at": started_at, "status": status, "summary": summary})


def skipped(job, ts, reason):
    return slots.Record.from_event({"ts": ts, "kind": slots.SKIPPED, "payload": {"job": job, "reason": reason}})


def statuses(result, job, day=TODAY, *, hours=None):
    found = [(s.at.strftime("%H:%M"), s.status) for s in result[(job, day)]]
    return found if hours is None else [pair for pair in found if pair[0] in hours]


def at(day, hm):
    hour, minute = map(int, hm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=SGT)


PUBLISH_SO_FAR = ["09:00", "09:20", "09:40", "10:00", "10:20", "10:40", "11:00"]


@pytest.mark.parametrize(
    "job, day, hours, expected",
    [
        pytest.param("scout-send", date(2026, 11, 6), {"10:00"}, [("10:00", "ok")], id="quiet run at 10:00:03"),
        pytest.param(
            "scout-send",
            TODAY,
            {"10:00", "10:10", "10:20"},
            [("10:00", "missed"), ("10:10", "missed"), ("10:20", "ok")],
            id="slept through three slots",
        ),
        pytest.param("app-factory", TODAY, None, [("06:30", "ok")], id="late run at 08:42"),
        pytest.param("scout-research", TODAY, None, [("09:00", "due")], id="not yet run"),
        pytest.param("scout-research", date(2026, 11, 9), None, [], id="holiday skip is no slot"),
        pytest.param("backup", date(2026, 10, 30), None, [("23:30", "not installed")], id="before first record"),
        pytest.param(
            "publish",
            TODAY,
            set(PUBLISH_SO_FAR),
            [(hm, "ok") for hm in PUBLISH_SO_FAR],
            id="nothing due is ok",
        ),
    ],
)
def test_ac_m2_1_the_fortnight_table(job, day, hours, expected):
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    assert statuses(result, job, day, hours=hours) == expected


def test_ac_m2_1_publish_collapses_to_one_cell_with_counts():
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    cell = slots.day_cell(result[("publish", TODAY)])

    assert cell.status == "ok"
    assert cell.counts == {"ok": 7, "upcoming": 20}


@pytest.mark.parametrize(
    "job, day, hours, expected",
    [
        pytest.param("app-factory", date(2026, 11, 5), None, [("06:30", "failed")], id="failed run"),
        pytest.param("social", TODAY, None, [("07:00", "running")], id="running run"),
        pytest.param("scout-sync", date(2026, 11, 5), None, [("16:45", "skipped")], id="skip row"),
        pytest.param(
            "scout-send",
            date(2026, 11, 5),
            {"10:00", "10:10", "10:20"},
            [("10:00", "ok"), ("10:10", "skipped"), ("10:20", "skipped")],
            id="long run, then the lock and PAUSE-file skips from the mirror",
        ),
        pytest.param("scout-send", TODAY, {"10:30"}, [("10:30", "skipped")], id="quiet skip in events and mirror"),
        pytest.param("community", date(2026, 11, 9), None, [("07:30", "failed")], id="weekly slot on a holiday Monday"),
        pytest.param("community", date(2026, 11, 3), None, [], id="weekly job, not its day"),
        pytest.param("backup", date(2026, 11, 9), None, [("23:30", "ok")], id="backup past midnight"),
        pytest.param("backup", TODAY, None, [("23:30", "upcoming")], id="tonight's backup"),
        pytest.param("scout-send", date(2026, 11, 6), {"16:30"}, [("16:30", "ok")], id="friday's last slot"),
    ],
)
def test_the_rest_of_the_fortnight(job, day, hours, expected):
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    assert statuses(result, job, day, hours=hours) == expected


def test_the_fortnight_skip_reasons_come_through():
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    thursday = {s.at.strftime("%H:%M"): s.reason for s in result[("scout-send", date(2026, 11, 5))]}
    assert thursday["10:10"] == locks.STILL_GOING
    assert thursday["10:20"] == "PAUSE file: holiday"
    assert [s.reason for s in result[("scout-sync", date(2026, 11, 5))]] == ["paused: outreach"]


def test_ac_m2_2_the_same_quiet_skip_from_events_and_the_mirror_counts_once():
    line = {
        "ts": "2026-11-10T10:30:01+08:00",
        "run_id": None,
        "agent": "outreach",
        "level": "info",
        "kind": "run.skipped",
        "payload": {"job": "scout-send", "reason": "outside the send window"},
    }
    row = {**{k: line[k] for k in ("ts", "run_id", "agent", "level", "kind")}, "payload_json": json.dumps(line["payload"])}
    records = [quiet("scout-send", "2026-11-10T09:30:02+08:00"), slots.Record.from_event(row), slots.Record.from_event(line)]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    [slot] = [s for s in result[("scout-send", TODAY)] if s.at.strftime("%H:%M") == "10:30"]
    assert slot.status == "skipped"
    assert len(slot.records) == 1


def test_ac_m2_2_the_fortnight_read_from_both_sources_counts_each_record_once():
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    [slot] = [s for s in result[("scout-send", TODAY)] if s.at.strftime("%H:%M") == "10:30"]
    assert [r.reason for r in slot.records] == ["outside the send window"]


def test_records_come_from_sqlite_rows():
    """`db.connect()` and the read model hand out `sqlite3.Row`s, which have
    no `.get` and whose `in` searches values, not column names."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE runs (id INTEGER PRIMARY KEY, agent TEXT, job TEXT, started_at TEXT, finished_at TEXT, status TEXT, summary TEXT)"
    )
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, run_id INTEGER, ts TEXT, agent TEXT, level TEXT, kind TEXT, payload_json TEXT)")
    conn.executemany(
        "INSERT INTO runs VALUES (:id, :agent, :job, :started_at, :finished_at, :status, :summary)", fortnight.RUNS
    )
    conn.executemany(
        "INSERT INTO events (run_id, ts, agent, level, kind, payload_json) VALUES (:run_id, :ts, :agent, :level, :kind, :payload_json)",
        fortnight.EVENTS,
    )
    rows = conn.execute("SELECT * FROM runs").fetchall()
    events = conn.execute("SELECT * FROM events").fetchall()
    conn.close()

    records = [slots.Record.from_run(row) for row in rows] + [slots.Record.from_event(row) for row in events]

    assert sorted(records, key=lambda r: r.key) == sorted(
        [slots.Record.from_run(row) for row in fortnight.RUNS] + [slots.Record.from_event(row) for row in fortnight.EVENTS],
        key=lambda r: r.key,
    )
    skip = next(r for r in records if r.job == "scout-sync" and r.status == "skipped")
    assert skip.reason == "paused: outreach"


def test_a_holiday_skip_does_not_hide_the_miss_before_it():
    """Friday's slot owns the window to Tuesday; the holiday skip on the
    observed Monday falls inside it and must not turn the miss into a skipped run."""
    records = [
        run("scout-research", "2026-11-05T09:00:04+08:00"),
        run("scout-research", "2026-11-09T09:00:02+08:00", "skipped", "not a business day (Deepavali)"),
    ]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 6)])

    assert statuses(result, "scout-research", date(2026, 11, 6)) == [("09:00", "missed")]


@pytest.mark.parametrize("reason", ["paused: scout", "PAUSE file: away", "all paused: travel"])
def test_a_paused_skip_on_a_holiday_does_not_hide_the_miss_before_it(reason):
    """The runner checks pause before the schedule, so on a holiday a paused
    agent records a pause reason. A skipped run on a day with no slot for the
    job counts for no slot, whatever its reason (review S-1)."""
    records = [
        run("scout-research", "2026-11-05T09:00:04+08:00"),
        run("scout-research", "2026-11-09T09:00:02+08:00", "skipped", reason),
    ]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 6)])

    assert statuses(result, "scout-research", date(2026, 11, 6)) == [("09:00", "missed")]


@pytest.mark.parametrize("reason", ["not a business day (weekend)", "PAUSE file: away"])
def test_a_weekend_skip_after_a_wake_does_not_fill_fridays_last_slot(reason):
    """Asleep across Friday 16:30; launchd fires the coalesced run on Saturday
    and it records a skipped run. Friday 16:30 is missed once Tuesday 09:30 passes."""
    friday = date(2026, 11, 6)
    records = [quiet("scout-send", "2026-11-06T16:20:02+08:00"), skipped("scout-send", "2026-11-07T08:15:00+08:00", reason)]

    result = slots.classify(JOBS, records, datetime(2026, 11, 10, 9, 31, tzinfo=SGT), [friday])

    assert statuses(result, "scout-send", friday, hours={"16:30"}) == [("16:30", "missed")]


def test_a_holiday_the_classifier_does_not_know_still_drops_its_skip():
    """The holiday list changed after the runner skipped: the skipped run says
    "not a business day", the day still has a slot here, and it reads missed."""
    records = [
        run("scout-research", "2026-11-06T09:00:04+08:00"),
        run("scout-research", "2026-11-09T09:00:02+08:00", "skipped", "not a business day (Deepavali)"),
    ]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 9)], business_day=lambda day: day.weekday() < 5)

    assert statuses(result, "scout-research", date(2026, 11, 9)) == [("09:00", "missed")]


def test_the_latest_run_in_a_window_wins_over_any_skipped_run():
    records = [
        run("scout-research", "2026-11-05T09:00:04+08:00"),
        # Thursday: paused at 09:00, then run by hand at 10:15, then the lock skip.
        skipped("scout-research", "2026-11-05T09:00:01+08:00", "paused: PAUSE file"),
        run("scout-research", "2026-11-05T10:15:00+08:00", "failed"),
        skipped("scout-research", "2026-11-05T10:20:00+08:00", locks.STILL_GOING),
        # Friday: only skipped runs, so the latest one's reason stands.
        run("scout-research", "2026-11-06T09:00:01+08:00", "skipped", "paused: outreach"),
        skipped("scout-research", "2026-11-06T09:30:00+08:00", locks.STILL_GOING),
    ]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 5), date(2026, 11, 6)])

    thursday, friday = result[("scout-research", date(2026, 11, 5))], result[("scout-research", date(2026, 11, 6))]
    assert [(s.status, s.reason) for s in thursday] == [("failed", None)]
    assert [(s.status, s.reason) for s in friday] == [("skipped", locks.STILL_GOING)]


def test_a_run_still_going_shows_running():
    records = [run("app-factory", "2026-11-09T06:30:02+08:00"), run("app-factory", "2026-11-10T06:30:03+08:00", "running")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "app-factory") == [("06:30", "running")]


def test_a_quiet_run_still_going_reads_running_from_the_lock_skip_after_it():
    """A quiet job writes nothing until it finishes. Its next slot finding the
    lock taken shows it is still going, so the slot is running, not missed (S-2)."""
    records = [quiet("scout-send", "2026-11-10T09:50:02+08:00"), skipped("scout-send", "2026-11-10T10:10:01+08:00", locks.STILL_GOING)]

    result = slots.classify(JOBS, records, at(TODAY, "10:12"), [TODAY])

    assert statuses(result, "scout-send", hours={"09:50", "10:00", "10:10"}) == [
        ("09:50", "ok"),
        ("10:00", "running"),
        ("10:10", "skipped"),
    ]


def test_a_quiet_run_going_through_several_slots_reads_running_once():
    records = [
        quiet("scout-send", "2026-11-10T09:50:02+08:00"),
        skipped("scout-send", "2026-11-10T10:10:01+08:00", locks.STILL_GOING),
        skipped("scout-send", "2026-11-10T10:20:01+08:00", locks.STILL_GOING),
    ]

    result = slots.classify(JOBS, records, at(TODAY, "10:25"), [TODAY])

    assert statuses(result, "scout-send", hours={"10:00", "10:10", "10:20"}) == [
        ("10:00", "running"),
        ("10:10", "skipped"),
        ("10:20", "skipped"),
    ]


def test_a_skipped_run_for_another_reason_in_the_next_window_leaves_the_miss():
    records = [quiet("scout-send", "2026-11-10T09:50:02+08:00"), skipped("scout-send", "2026-11-10T10:10:01+08:00", "PAUSE file: away")]

    result = slots.classify(JOBS, records, at(TODAY, "10:12"), [TODAY])

    assert statuses(result, "scout-send", hours={"10:00"}) == [("10:00", "missed")]


def test_a_coalesced_run_after_a_long_sleep_fills_only_its_own_slot():
    records = [quiet("scout-send", "2026-11-06T09:30:02+08:00"), quiet("scout-send", "2026-11-10T10:58:00+08:00")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    early = statuses(result, "scout-send", hours={f"{h}:{m}0" for h in ("09", "10") for m in range(6)} | {"11:00"})
    assert early == [(hm, "missed") for hm in ("09:30", "09:40", "09:50", "10:00", "10:10", "10:20", "10:30", "10:40")] + [
        ("10:50", "ok"),
        ("11:00", "due"),
    ]


def test_a_run_a_second_before_its_slot_counts_for_the_slot_before():
    records = [quiet("scout-send", "2026-11-10T09:30:02+08:00"), quiet("scout-send", "2026-11-10T09:59:59+08:00")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"09:50", "10:00"}) == [("09:50", "ok"), ("10:00", "missed")]


def test_a_record_from_before_the_days_shown_still_counts_as_the_first():
    """The read model passes one older record per job, so a first shown slot
    the Mac slept through reads as missed, not as not installed."""
    records = [run("scout-research", "2026-10-20T09:00:04+08:00"), run("scout-research", "2026-10-29T09:00:04+08:00")]

    result = slots.classify(JOBS, records, NOW, FORTNIGHT)

    assert statuses(result, "scout-research", date(2026, 10, 28)) == [("09:00", "missed")]
    assert statuses(result, "scout-research", date(2026, 10, 29)) == [("09:00", "ok")]


def test_a_job_with_no_record_at_all_is_not_installed():
    result = slots.classify(JOBS, [], NOW, [TODAY])

    assert [s.status for s in result[("scout-send", TODAY)]] == ["not installed"] * 43


def test_ac_m2_4_a_job_not_loaded_in_launchd_keeps_its_past_and_loses_its_future():
    records = [quiet("scout-send", "2026-11-06T09:30:02+08:00"), quiet("scout-send", "2026-11-10T09:30:02+08:00")]

    result = slots.classify(JOBS, records, NOW, [TODAY], installed={"app-factory"})

    assert statuses(result, "scout-send", hours={"09:30", "09:40", "11:00", "11:10", "16:30"}) == [
        ("09:30", "ok"),
        ("09:40", "missed"),
        ("11:00", "due"),
        ("11:10", "not installed"),
        ("16:30", "not installed"),
    ]


def test_by_default_every_job_counts_as_installed():
    records = [quiet("scout-send", "2026-11-10T09:30:02+08:00")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"11:10"}) == [("11:10", "upcoming")]


def slot_status(status):
    return slots.SlotStatus("scout-send", NOW, status)


@pytest.mark.parametrize("worst", slots.WORST_FIRST)
def test_ac_m2_3_the_worst_status_wins_the_day_cell(worst):
    """Each status, with one of every status that needs less attention."""
    later = slots.WORST_FIRST[slots.WORST_FIRST.index(worst) :]
    found = [slot_status(status) for status in reversed(later) for _ in range(2)] + [slot_status(worst)]

    cell = slots.day_cell(found)

    assert cell.status == worst
    assert cell.counts == {status: 3 if status == worst else 2 for status in later}


def test_ac_m2_3_the_order_is_the_one_in_the_prd():
    assert slots.WORST_FIRST == ("failed", "missed", "running", "ok", "skipped", "due", "upcoming", "not installed")


def test_ac_m2_3_scout_send_on_a_mixed_day():
    records = [
        quiet("scout-send", "2026-11-10T09:30:02+08:00"),
        run("scout-send", "2026-11-10T09:40:01+08:00", "failed"),
        skipped("scout-send", "2026-11-10T09:50:01+08:00", "PAUSE file: away"),
        quiet("scout-send", "2026-11-10T10:26:00+08:00"),
    ]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    cell = slots.day_cell(result[("scout-send", TODAY)])
    assert cell.status == "failed"
    # 10:00, 10:10 slept through; 10:30 to 10:50 closed with nothing; 11:00 still open.
    assert cell.counts == {"failed": 1, "missed": 5, "ok": 2, "skipped": 1, "due": 1, "upcoming": 33}
    assert list(cell.counts) == ["failed", "missed", "ok", "skipped", "due", "upcoming"]


def test_ac_m2_3_publish_on_a_mixed_day():
    records = [
        quiet("publish", "2026-11-10T09:00:05+08:00", "nothing due"),
        run("publish", "2026-11-10T09:20:04+08:00", "failed"),
        run("publish", "2026-11-10T09:40:03+08:00", "skipped", "paused: publish"),
        # 10:00: the Mac slept through it.
        run("publish", "2026-11-10T10:20:03+08:00", "running"),
        skipped("publish", "2026-11-10T10:40:02+08:00", locks.STILL_GOING),
    ]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    cell = slots.day_cell(result[("publish", TODAY)])
    assert cell.status == "failed"
    assert cell.counts == {"failed": 1, "missed": 1, "running": 1, "ok": 1, "skipped": 2, "due": 1, "upcoming": 20}


def test_ac_m2_3_publish_before_it_was_installed():
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    assert slots.day_cell(result[("publish", date(2026, 11, 6))]) == slots.DayCell("not installed", {"not installed": 27})


@pytest.mark.parametrize("status", ["abandoned", "cancelled", ""])
def test_a_run_status_outside_the_slot_statuses_reads_failed(status):
    """A plug-in's `after_run` hook can return any outcome; the cell must not break (S-9)."""
    records = [run("app-factory", "2026-11-09T06:30:02+08:00"), run("app-factory", "2026-11-10T06:30:03+08:00", status)]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "app-factory") == [("06:30", "failed")]
    assert slots.day_cell(result[("app-factory", TODAY)]).status == "failed"


def test_a_day_with_no_slots_has_an_empty_cell():
    result = slots.classify(JOBS, D1, NOW, FORTNIGHT)

    assert slots.day_cell(result[("scout-send", date(2026, 11, 8))]) == slots.DayCell(None, {})


def test_timestamps_in_another_zone_are_read_as_the_same_instant():
    records = [
        slots.Record.from_event({"ts": "2026-11-06T01:30:02+00:00", "kind": "run.quiet", "payload": {"job": "scout-send"}}),
        slots.Record.from_event({"ts": "2026-11-09T21:26:00-05:00", "kind": "run.quiet", "payload": {"job": "scout-send"}}),
    ]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"10:10", "10:20"}) == [("10:10", "missed"), ("10:20", "ok")]


def test_a_naive_clock_is_read_as_sgt_whatever_the_mac_zone(mac_zone):
    """`timeutil.parse`'s rule: a time with no zone is SGT (S-8)."""
    aware = slots.classify(JOBS, D1, NOW, [TODAY])
    naive = slots.classify(JOBS, D1, NOW.replace(tzinfo=None), [TODAY])

    assert naive == aware
    assert slots.day_cell(naive[("scout-send", TODAY)]).counts == {"missed": 2, "ok": 7, "skipped": 1, "upcoming": 33}


def test_the_friday_window_runs_to_the_next_business_day():
    """No record after Friday 16:30 until Tuesday: Friday's last slot stays
    due through the long weekend and while Tuesday 09:30 is the clock, and is
    missed once that slot has passed."""
    records = [quiet("scout-send", "2026-11-06T16:20:02+08:00")]
    friday = date(2026, 11, 6)

    def friday_last(now):
        return statuses(slots.classify(JOBS, records, now, [friday]), "scout-send", friday, hours={"16:30"})

    assert friday_last(datetime(2026, 11, 9, 12, 0, tzinfo=SGT)) == [("16:30", "due")]
    assert friday_last(datetime(2026, 11, 10, 9, 30, tzinfo=SGT)) == [("16:30", "due")]
    assert friday_last(datetime(2026, 11, 10, 9, 30, 1, tzinfo=SGT)) == [("16:30", "missed")]


def test_a_quiet_run_is_placed_by_its_start_not_its_stamp():
    """A `run.quiet` event carries `started_at` and counts for that slot."""
    record = slots.Record.from_event(
        {"ts": "2026-11-10T10:12:00+08:00", "kind": "run.quiet", "payload": {"job": "scout-send", "started_at": "2026-11-10T10:00:01+08:00"}}
    )
    records = [quiet("scout-send", "2026-11-10T09:30:02+08:00"), record]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"10:00", "10:10"}) == [("10:00", "ok"), ("10:10", "missed")]


def test_a_mixed_schedule_skips_the_whole_holiday_as_the_runner_does(monkeypatch):
    """The runner skips every shape of a job with any business-day shape on a
    holiday (S-10), and the classifier gives that day no slot at all."""
    spec = {"agent": "heartbeat", "kind": "command", "schedule": {"daily": "08:00", "business_days": "09:00"}}
    holiday = date(2026, 11, 9)
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-09T08:00:30+08:00")

    reason = runner._schedule_reason(spec)
    result = slots.classify({"mixed": spec}, [], NOW, [holiday, TODAY])

    assert reason == "not a business day (Deepavali (observed))"
    assert result[("mixed", holiday)] == []
    assert [s.at.strftime("%H:%M") for s in result[("mixed", TODAY)]] == ["08:00", "09:00"]


def test_every_job_in_settings_gets_its_slots():
    jobs = config.settings()["jobs"]

    result = slots.classify(jobs, [], NOW, [TODAY])

    counts = {job: len(result[(job, TODAY)]) for job in jobs}
    assert counts["scout-send"] == 43
    assert counts["scout-research"] == 1
    assert counts["community"] == 0  # weekly on Monday; today is Tuesday
    assert counts["publish"] == 27  # every 20 minutes, 09:00 to 17:40 (BP-03, X4)
    assert counts["inbox-check"] == 68  # every 15 minutes, 07:00 to 23:45 (inbox watch W1)
    assert all(n == 1 for job, n in counts.items() if job not in {"scout-send", "scout-research", "community", "publish", "inbox-check"})


def test_publish_has_its_27_slots_on_a_weekend_and_a_holiday_too():
    """`daily_every` runs every day, unlike `business_days_every` (BP-03, X4)."""
    jobs = {"publish": config.settings()["jobs"]["publish"]}
    saturday, holiday = date(2026, 11, 7), date(2026, 11, 9)

    result = slots.classify(jobs, [], NOW, [saturday, holiday])

    for day in (saturday, holiday):
        times = [s.at.strftime("%H:%M") for s in result[("publish", day)]]
        assert len(times) == 27 and times[0] == "09:00" and times[-1] == "17:40"


def test_a_fortnight_of_every_job_is_quick():
    jobs = config.settings()["jobs"]
    started = time.perf_counter()

    slots.classify(jobs, D1, NOW, FORTNIGHT)

    assert time.perf_counter() - started < 2.0


WATCHING: list[list[str]] = []


def _watch(event, args):
    if WATCHING and event in ("open", "sqlite3.connect", "socket.connect", "subprocess.Popen"):
        WATCHING[-1].append(f"{event} {args[0]!r}")


sys.addaudithook(_watch)


def test_the_classifier_opens_no_file_database_or_socket():
    """Holidays come in as a callable here; by default they're read from
    config/sg-public-holidays.yaml, once per process, by `holidays`."""
    proof: list[str] = []
    WATCHING.append(proof)
    try:
        open(os.devnull).close()  # the watch itself works
    finally:
        WATCHING.pop()
    assert len(proof) == 1

    seen: list[str] = []
    WATCHING.append(seen)
    try:
        result = slots.classify(JOBS, D1, NOW, FORTNIGHT, business_day=lambda day: day.weekday() < 5)
    finally:
        WATCHING.pop()

    assert result[("scout-send", TODAY)]
    assert seen == []


def test_importing_the_classifier_loads_no_database_code():
    code = "import sys, jura_growth.slots; print(sorted(m for m in ('sqlite3', 'jura_growth.db', 'jura_growth.log') if m in sys.modules))"

    found = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert found.stdout.strip() == "[]"
