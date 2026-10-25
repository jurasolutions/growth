"""The slot classifier (MC-07): literal records in, slot statuses out.

Dataset D1 (the fortnight) from the test strategy: the clock is frozen at
Tue 2026-11-10 11:05 SGT. Sun 2026-11-08 is Deepavali and Mon 2026-11-09 its
observed holiday. Every test runs with the Mac's zone set to Singapore, UTC
and New York, because slots are SGT whatever the Mac says.
"""

import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

import pytest

from jura_growth import config, slots
from jura_growth.timeutil import SGT

NOW = datetime(2026, 11, 10, 11, 5, tzinfo=SGT)
TODAY = date(2026, 11, 10)

JOBS = {
    "app-factory": {"schedule": {"daily": "06:30"}},
    "scout-research": {"schedule": {"business_days": "09:00"}},
    "scout-send": {"schedule": {"business_days_every": {"start": "09:30", "end": "16:30", "minutes": 10}}, "quiet": True},
    "publish": {"schedule": {"business_days_every": {"start": "09:00", "end": "17:40", "minutes": 20}}, "quiet": True},
    "community": {"schedule": {"weekly": {"day": "mon", "time": "07:30"}}},
    "backup": {"schedule": {"daily": "23:30"}},
}


@pytest.fixture(autouse=True, params=["Asia/Singapore", "UTC", "America/New_York"])
def mac_zone(request, monkeypatch):
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    monkeypatch.undo()
    time.tzset()


def quiet(job, ts, reason=None):
    payload = {"job": job, "started_at": ts}
    if reason:
        payload["reason"] = reason
    return slots.Record.from_event({"ts": ts, "kind": "run.quiet", "payload": payload})


def run(job, started_at, status="ok", summary=None):
    return slots.Record.from_run({"job": job, "started_at": started_at, "status": status, "summary": summary})


def skipped(job, ts, reason):
    return slots.Record.from_event({"ts": ts, "kind": "run.skipped", "payload": {"job": job, "reason": reason}})


def every(job, day, start, end, minutes, second=2, reason=None):
    """A quiet run a few seconds after each slot from `start` to `end`."""
    found = []
    hour, minute = map(int, start.split(":"))
    last = tuple(map(int, end.split(":")))
    while (hour, minute) <= last:
        found.append(quiet(job, f"{day}T{hour:02d}:{minute:02d}:{second:02d}+08:00", reason))
        minute += minutes
        hour, minute = hour + minute // 60, minute % 60
    return found


# D1, the fortnight from Wed 2026-10-28 to Tue 2026-11-10.
FORTNIGHT = [date(2026, 10, 28) + timedelta(days=n) for n in range(14)]
D1 = [
    # scout-send, installed before the fortnight began.
    quiet("scout-send", "2026-10-28T09:30:02+08:00"),
    *every("scout-send", "2026-11-06", "09:30", "09:50", 10),
    quiet("scout-send", "2026-11-06T10:00:03+08:00"),
    *every("scout-send", "2026-11-06", "10:10", "16:30", 10),  # 16:30's window runs to Tuesday
    *every("scout-send", "2026-11-10", "09:30", "09:50", 10),
    quiet("scout-send", "2026-11-10T10:26:00+08:00"),  # slept through 10:00, 10:10 and 10:20
    *every("scout-send", "2026-11-10", "10:30", "11:00", 10),
    # app-factory: today's 06:30 slot ran late, after the Mac woke.
    run("app-factory", "2026-10-28T06:30:05+08:00"),
    run("app-factory", "2026-11-10T08:42:00+08:00"),
    # scout-research: Friday's run, then the holiday skips on the observed Monday.
    run("scout-research", "2026-10-28T09:00:04+08:00"),
    run("scout-research", "2026-11-06T09:00:04+08:00"),
    run("scout-research", "2026-11-09T09:00:02+08:00", "skipped", "not a business day (Deepavali)"),
    # backup: first record on 2026-11-02, finishing after midnight.
    run("backup", "2026-11-02T23:30:04+08:00"),
    # publish: every slot so far today found nothing due (agents.NothingToDo).
    *every("publish", "2026-11-10", "09:00", "11:00", 20, second=5, reason="nothing due"),
]


def statuses(result, job, day=TODAY, *, hours=None):
    found = [(s.at.strftime("%H:%M"), s.status) for s in result[(job, day)]]
    return found if hours is None else [pair for pair in found if pair[0] in hours]


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


def test_a_holiday_skip_does_not_hide_the_miss_before_it():
    """Friday's slot owns the window to Tuesday; the holiday skip on the
    observed Monday falls inside it and must not turn the miss into a skip."""
    records = [
        run("scout-research", "2026-11-05T09:00:04+08:00"),
        run("scout-research", "2026-11-09T09:00:02+08:00", "skipped", "not a business day (Deepavali)"),
    ]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 6)])

    assert statuses(result, "scout-research", date(2026, 11, 6)) == [("09:00", "missed")]


def test_the_latest_run_in_a_window_wins_over_any_skip():
    records = [
        run("scout-research", "2026-11-05T09:00:04+08:00"),
        # Thursday: paused at 09:00, then run by hand at 10:15, then the lock skip.
        skipped("scout-research", "2026-11-05T09:00:01+08:00", "paused: PAUSE file"),
        run("scout-research", "2026-11-05T10:15:00+08:00", "failed"),
        skipped("scout-research", "2026-11-05T10:20:00+08:00", "previous run still going"),
        # Friday: only skips, so the latest skip's reason stands.
        run("scout-research", "2026-11-06T09:00:01+08:00", "skipped", "paused: outreach"),
        skipped("scout-research", "2026-11-06T09:30:00+08:00", "previous run still going"),
    ]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 5), date(2026, 11, 6)])

    thursday, friday = result[("scout-research", date(2026, 11, 5))], result[("scout-research", date(2026, 11, 6))]
    assert [(s.status, s.reason) for s in thursday] == [("failed", None)]
    assert [(s.status, s.reason) for s in friday] == [("skipped", "previous run still going")]


def test_a_run_still_going_shows_running():
    records = [run("app-factory", "2026-11-09T06:30:02+08:00"), run("app-factory", "2026-11-10T06:30:03+08:00", "running")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "app-factory") == [("06:30", "running")]


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


def test_a_record_from_before_the_days_shown_still_counts_as_the_first():
    """The read model passes one older record per job, so a first shown slot
    the Mac slept through reads as missed, not as not installed."""
    records = [run("scout-research", "2026-10-20T09:00:04+08:00"), run("scout-research", "2026-10-29T09:00:04+08:00")]

    result = slots.classify(JOBS, records, NOW, FORTNIGHT)

    assert statuses(result, "scout-research", date(2026, 10, 28)) == [("09:00", "missed")]
    assert statuses(result, "scout-research", date(2026, 10, 29)) == [("09:00", "ok")]


def test_a_job_with_no_record_at_all_is_not_installed():
    result = slots.classify(JOBS, [], NOW, [TODAY])

    found = [s.status for s in result[("scout-send", TODAY)]]
    assert found == ["not installed"] * 43


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


def state(status):
    return slots.SlotState("scout-send", NOW, status)


@pytest.mark.parametrize("worst", slots.WORST_FIRST)
def test_ac_m2_3_the_worst_status_wins_the_day_cell(worst):
    """Each status, with one of every status that needs less attention."""
    later = slots.WORST_FIRST[slots.WORST_FIRST.index(worst) :]
    states = [state(status) for status in reversed(later) for _ in range(2)] + [state(worst)]

    cell = slots.day_cell(states)

    assert cell.status == worst
    assert cell.counts == {status: 3 if status == worst else 2 for status in later}


def test_ac_m2_3_the_order_is_the_one_in_the_prd():
    assert slots.WORST_FIRST == ("failed", "missed", "running", "ok", "skipped", "due", "upcoming", "not installed")


def test_ac_m2_3_scout_send_on_a_mixed_day():
    records = [
        quiet("scout-send", "2026-11-10T09:30:02+08:00"),
        run("scout-send", "2026-11-10T09:40:01+08:00", "failed"),
        skipped("scout-send", "2026-11-10T09:50:01+08:00", "previous run still going"),
        quiet("scout-send", "2026-11-10T10:26:00+08:00"),
    ]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    cell = slots.day_cell(result[("scout-send", TODAY)])
    assert cell.status == "failed"
    # 10:00, 10:10 slept through; 10:30 to 10:50 closed with nothing; 11:00 still open.
    assert cell.counts == {"failed": 1, "missed": 5, "ok": 2, "skipped": 1, "due": 1, "upcoming": 33}
    assert list(cell.counts) == ["failed", "missed", "ok", "skipped", "due", "upcoming"]


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


def test_the_friday_window_runs_to_the_next_business_day():
    """No record after Friday 16:30 until Tuesday: Friday's last slot stays
    due through the long weekend, and is missed once Tuesday 09:30 passes."""
    records = [quiet("scout-send", "2026-11-06T16:20:02+08:00")]
    friday = date(2026, 11, 6)

    on_monday = slots.classify(JOBS, records, datetime(2026, 11, 9, 12, 0, tzinfo=SGT), [friday])
    on_tuesday = slots.classify(JOBS, records, datetime(2026, 11, 10, 9, 30, tzinfo=SGT), [friday])

    assert statuses(on_monday, "scout-send", friday, hours={"16:30"}) == [("16:30", "due")]
    assert statuses(on_tuesday, "scout-send", friday, hours={"16:30"}) == [("16:30", "missed")]


def test_a_weekly_job_runs_on_a_holiday_monday():
    records = [run("community", "2026-11-02T07:30:05+08:00"), run("community", "2026-11-09T07:30:05+08:00", "failed")]

    result = slots.classify(JOBS, records, NOW, FORTNIGHT)

    assert [(day, statuses(result, "community", day)) for day in FORTNIGHT if result[("community", day)]] == [
        (date(2026, 11, 2), [("07:30", "ok")]),
        (date(2026, 11, 9), [("07:30", "failed")]),
    ]


def test_a_backup_that_finishes_after_midnight_counts_for_the_day_it_started():
    records = [run("backup", "2026-11-02T23:30:04+08:00"), run("backup", "2026-11-09T23:30:04+08:00")]

    result = slots.classify(JOBS, records, NOW, [date(2026, 11, 9), TODAY])

    assert statuses(result, "backup", date(2026, 11, 9)) == [("23:30", "ok")]
    assert statuses(result, "backup") == [("23:30", "upcoming")]


def test_a_quiet_run_is_placed_by_its_start_not_its_stamp():
    """A quiet run that did work and ran long is a run row with its real start;
    a `run.quiet` event carries `started_at` and counts for that slot."""
    record = slots.Record.from_event(
        {"ts": "2026-11-10T10:12:00+08:00", "kind": "run.quiet", "payload": {"job": "scout-send", "started_at": "2026-11-10T10:00:01+08:00"}}
    )
    records = [quiet("scout-send", "2026-11-10T09:30:02+08:00"), record]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"10:00", "10:10"}) == [("10:00", "ok"), ("10:10", "missed")]


def test_every_job_in_settings_gets_its_slots():
    jobs = config.settings()["jobs"]

    result = slots.classify(jobs, [], NOW, [TODAY])

    counts = {job: len(result[(job, TODAY)]) for job in jobs}
    assert counts["scout-send"] == 43
    assert counts["scout-research"] == 1
    assert counts["community"] == 0  # weekly on Monday; today is Tuesday
    assert all(n == 1 for job, n in counts.items() if job not in {"scout-send", "scout-research", "community"})


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


def test_a_quiet_run_seconds_after_its_slot_is_ok():
    records = [
        quiet("scout-send", "2026-11-06T09:30:02+08:00"),  # first trace: installed
        quiet("scout-send", "2026-11-10T10:00:03+08:00"),
    ]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"10:00"}) == [("10:00", "ok")]


def test_slots_the_mac_slept_through_are_missed_and_the_late_run_counts_for_the_last():
    records = [
        quiet("scout-send", "2026-11-10T09:50:01+08:00"),
        quiet("scout-send", "2026-11-10T10:26:00+08:00"),  # launchd caught up after the wake
    ]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"10:00", "10:10", "10:20"}) == [
        ("10:00", "missed"),
        ("10:10", "missed"),
        ("10:20", "ok"),
    ]


def test_a_past_slot_whose_window_is_still_open_is_due():
    records = [slots.Record("run", "scout-research", "2026-11-06T09:00:04+08:00", status="ok")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-research") == [("09:00", "due")]


def test_a_slot_still_to_come_is_upcoming():
    records = [quiet("scout-send", "2026-11-10T09:30:02+08:00")]

    result = slots.classify(JOBS, records, NOW, [TODAY])

    assert statuses(result, "scout-send", hours={"11:00", "11:10", "16:30"}) == [
        ("11:00", "due"),
        ("11:10", "upcoming"),
        ("16:30", "upcoming"),
    ]
