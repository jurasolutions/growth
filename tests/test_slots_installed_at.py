"""A slot from before a job's plist was last installed isn't judged (morning brief T-B5).

Moving a job later leaves its change day's slot with no trace: the old run landed before the new
time, so it counts for the slot before. These are the technical review's probe: the old times run
until Saturday 31 October, `schedule install` runs that day, and the new times run from the next.
"""

from __future__ import annotations

import dataclasses
import os
from datetime import date, datetime, timedelta

import pytest

import mission_world as world
from jura_growth import db, health, log, mission, schedule, slots
from jura_growth.timeutil import SGT

NEW = {
    "one-pager": {"schedule": {"daily": "09:00"}},
    "app-factory": {"schedule": {"daily": "07:00"}},
    "social": {"schedule": {"daily": "07:30"}},
    "scout-research": {"schedule": {"business_days": "06:30"}},
    "community": {"schedule": {"weekly": {"day": "mon", "time": "08:00"}}},
}
OLD = {"one-pager": "08:00", "app-factory": "06:30", "social": "07:00", "scout-research": "09:00", "community": "07:30"}
INSTALL_DAY = date(2026, 10, 31)  # a Saturday
INSTALLED = datetime(2026, 10, 31, 12, 0, tzinfo=SGT)
TIMES = [
    datetime(2026, 11, 1, 9, 1, tzinfo=SGT),  # Sunday
    datetime(2026, 11, 2, 9, 1, tzinfo=SGT),  # Monday
    datetime(2026, 11, 3, 9, 1, tzinfo=SGT),  # Tuesday
]
# What the probe found with no rule: the false lines the first pictures would carry.
FALSE_MISSES = {
    TIMES[0]: {("one-pager", "Sat 31 Oct"), ("app-factory", "Sat 31 Oct"), ("social", "Sat 31 Oct")},
    TIMES[1]: {("one-pager", "Sat 31 Oct"), ("app-factory", "Sat 31 Oct"), ("social", "Sat 31 Oct"), ("community", "Mon 26 Oct")},
    TIMES[2]: {("one-pager", "Sat 31 Oct"), ("app-factory", "Sat 31 Oct"), ("social", "Sat 31 Oct"), ("community", "Mon 26 Oct")},
}


def weekday(day: date) -> bool:
    return day.weekday() < 5


def run(job: str, moment: datetime) -> slots.Record:
    return slots.Record(kind=slots.RUN, job=job, ts=moment.isoformat(), status="ok")


def the_move() -> list[slots.Record]:
    """Old times every morning to the install day, then the new times."""
    records = []
    for offset in range(27):
        day = date(2026, 10, 5) + timedelta(days=offset)
        for job, hhmm in OLD.items():
            if (job == "community" and day.weekday() != 0) or (job == "scout-research" and not weekday(day)):
                continue
            hour, minute = map(int, hhmm.split(":"))
            records.append(run(job, datetime(day.year, day.month, day.day, hour, minute, 5, tzinfo=SGT)))
    for day in (date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)):
        for job, spec in NEW.items():
            records += [run(job, at) for at in slots.slot_times(spec["schedule"], day, weekday)]
    return records


def classify(now: datetime, records: list[slots.Record], **rule) -> dict:
    usable = [record for record in records if record.at <= now]
    days = [now.date() - timedelta(days=n) for n in reversed(range(14))]
    return slots.classify(NEW, usable, now, days, business_day=weekday, **rule)


def missed(found: dict) -> set[tuple[str, str]]:
    return {
        (job, health.day_label(slot.at))
        for (job, _), statuses in found.items()
        for slot in statuses
        if slot.status == "missed"
    }


@pytest.mark.parametrize("now", TIMES, ids=["Sunday", "Monday", "Tuesday"])
def test_without_the_rule_moving_a_job_later_reads_as_missed(now):
    """The world below is the one that goes wrong, so the next test proves something."""
    assert missed(classify(now, the_move())) == FALSE_MISSES[now]


@pytest.mark.parametrize("now", TIMES, ids=["Sunday", "Monday", "Tuesday"])
def test_with_the_rule_the_move_leaves_no_false_miss(now):
    assert missed(classify(now, the_move(), installed_at=lambda job: INSTALLED)) == set()


@pytest.mark.parametrize("job,day", [
    ("one-pager", date(2026, 10, 31)),
    ("app-factory", date(2026, 10, 31)),
    ("social", date(2026, 10, 31)),
    ("community", date(2026, 10, 26)),
])
def test_the_slot_with_no_trace_on_the_change_day_reads_not_installed(job, day):
    found = classify(TIMES[1], the_move(), installed_at=lambda name: INSTALLED)
    assert [slot.status for slot in found[(job, day)]] == ["not installed"]


def test_community_mondays_slot_is_no_longer_due_for_a_week():
    now = TIMES[0]  # the probe read Mon 26 Oct as "due" until the next Monday's slot
    assert [s.status for s in classify(now, the_move())[("community", date(2026, 10, 26))]] == ["due"]
    assert [s.status for s in classify(now, the_move(), installed_at=lambda job: INSTALLED)[("community", date(2026, 10, 26))]] == ["not installed"]


def test_a_slot_after_the_install_with_no_trace_is_a_true_miss():
    records = [r for r in the_move() if not (r.job == "one-pager" and r.at.date() == date(2026, 11, 2))]
    found = classify(TIMES[2], records, installed_at=lambda job: INSTALLED)
    assert missed(found) == {("one-pager", "Mon 2 Nov")}


def test_a_slot_from_before_the_install_keeps_the_run_it_has():
    found = classify(TIMES[1], the_move(), installed_at=lambda job: INSTALLED)
    assert [slot.status for slot in found[("one-pager", date(2026, 10, 28))]] == ["ok"]


def test_a_late_run_after_the_install_still_counts_for_the_slot_before_it():
    """The Mac woke late: the install's moment doesn't take the run away from its window."""
    late = run("one-pager", datetime(2026, 10, 31, 12, 30, tzinfo=SGT))
    found = classify(TIMES[0], [*the_move(), late], installed_at=lambda job: INSTALLED)
    assert [slot.status for slot in found[("one-pager", date(2026, 10, 31))]] == ["ok"]


def test_the_rule_is_per_job():
    """Only the job that was installed then loses its old slots."""
    rule = {"one-pager": INSTALLED}.get
    assert missed(classify(TIMES[0], the_move(), installed_at=rule)) == FALSE_MISSES[TIMES[0]] - {("one-pager", "Sat 31 Oct")}


def test_a_plist_time_in_the_future_doesnt_hide_an_upcoming_slot():
    """A wrong clock at install can't make today's later slots read as not installed."""
    now = datetime(2026, 11, 3, 6, 0, tzinfo=SGT)
    found = classify(now, the_move(), installed_at=lambda job: now + timedelta(days=2))
    assert [slot.status for slot in found[("one-pager", now.date())]] == ["upcoming"]


def test_a_job_with_no_plist_is_judged_as_before():
    now = TIMES[1]
    assert missed(classify(now, the_move(), installed_at=lambda job: None)) == FALSE_MISSES[now]


# --- schedule.installed_at: the plist `install` writes ----------------------------------------------


def test_installed_at_is_the_plists_modified_time():
    folder = schedule.launch_agents_dir()
    folder.mkdir(parents=True, exist_ok=True)
    plist = folder / f"{schedule.label('social')}.plist"
    plist.write_bytes(b"<plist/>")
    stamp = datetime(2026, 10, 31, 12, 0, tzinfo=SGT).timestamp()
    os.utime(plist, (stamp, stamp))
    assert schedule.installed_at("social") == INSTALLED


def test_installed_at_is_none_with_no_plist():
    assert schedule.installed_at("social") is None


# --- it reaches Fix, through the read model -----------------------------------------------------------


@pytest.fixture
def conn():
    with db.session() as connection:
        yield connection


def history(conn) -> None:
    for record in the_move():
        if record.at <= TIMES[1]:
            run_id = log.start_run(conn, record.job, record.job, started_at=record.ts)
            log.finish_run(conn, run_id, "ok")


def read(**rule) -> mission.Snapshot:
    source = world.source(TIMES[1].isoformat(), jobs=NEW)
    return mission.read(dataclasses.replace(source, **rule))


def missed_lines(snapshot: mission.Snapshot) -> list[str]:
    return [line for line in health.strip(snapshot) if " missed " in line]


def test_the_read_model_passes_the_install_time_and_fix_says_nothing_false(conn):
    history(conn)
    assert len(missed_lines(read())) == 3  # one-pager, app-factory and social, since Friday
    assert missed_lines(read(installed_at=lambda job: INSTALLED)) == []


def test_only_the_engines_own_source_reads_the_real_plists():
    assert world.source().installed_at("social") is None
    assert mission.Source.here().installed_at is schedule.installed_at
