"""Slot statuses: what happened at each scheduled time of each job (MC §4.5).

Pure. The schedule, the records and the clock come in; slot statuses come out.
Nothing here opens growth.db or the JSONL mirror: the read model (`mission.py`)
gathers the records and this module only judges them. The one thing read from
disk is the holiday list, through `holidays.is_business_day` (cached once per
process), and a caller may pass its own `business_day` instead.

A slot owns the window from its own time up to the next slot of the same job,
so a run launchd started late after the Mac woke still counts for its slot.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Container, Iterable, Mapping

from jura_growth import holidays, schedule, timeutil
from jura_growth.timeutil import SGT

RUN, SKIPPED, QUIET = "run", "run.skipped", "run.quiet"
# Slot statuses, the one that most needs attention first (MC SC2, AC-M2.3).
WORST_FIRST = ("failed", "missed", "running", "ok", "skipped", "due", "upcoming", "not installed")
BUSINESS_DAY_KINDS = ("business_days", "business_days_every")  # as `runner` skips them
LOOKAHEAD_DAYS = 31  # how far to look for the next slot that closes a window


@dataclass(frozen=True)
class Record:
    """One trace of a job: a `runs` row (kind "run") or a `run.skipped` or
    `run.quiet` event. `ts` is the record's own stamp, `started_at` when the
    work began (a quiet run's payload carries it)."""

    kind: str
    job: str
    ts: str
    status: str | None = None
    reason: str | None = None
    started_at: str | None = None

    @classmethod
    def from_event(cls, event: Mapping[str, Any]) -> Record:
        """A `run.skipped` or `run.quiet` record: a JSONL mirror line (with
        `payload`) or an `events` row (with `payload_json`)."""
        payload = event["payload"] if "payload" in event else json.loads(event["payload_json"] or "{}")
        return cls(
            kind=event["kind"],
            job=payload["job"],
            ts=event["ts"],
            reason=payload.get("reason"),
            started_at=payload.get("started_at"),
        )

    @classmethod
    def from_run(cls, row: Mapping[str, Any]) -> Record:
        """A `runs` row. A skip row's reason is its summary."""
        status = row["status"]
        return cls(
            kind=RUN,
            job=row["job"],
            ts=row["started_at"],
            status=status,
            reason=row.get("summary") if status == "skipped" else None,
        )

    @property
    def key(self) -> tuple[str, str, str, str | None]:
        """The same record read from `events` and from the mirror (MC §4.5)."""
        return (self.kind, self.ts, self.job, self.reason)

    @property
    def at(self) -> datetime:
        return timeutil.parse(self.started_at or self.ts).astimezone(SGT)

    @property
    def is_skip(self) -> bool:
        return self.kind == SKIPPED or (self.kind == RUN and self.status == "skipped")

    @property
    def outside_schedule(self) -> bool:
        """A business-day job's skip on a holiday or weekend: launchd fired,
        but the day has no slot for it to count against (MC §4.5)."""
        return self.is_skip and (self.reason or "").startswith("not a business day")


@dataclass(frozen=True)
class SlotState:
    job: str
    at: datetime
    status: str
    reason: str | None = None  # a skip's reason
    records: tuple[Record, ...] = ()  # what landed in the slot's window, oldest first


@dataclass(frozen=True)
class DayCell:
    """One job's day in the grid: the worst slot status, and how many slots
    had each status (in `WORST_FIRST` order)."""

    status: str | None
    counts: dict[str, int]


def day_cell(states: Iterable[SlotState]) -> DayCell:
    counts = {status: 0 for status in WORST_FIRST}
    for state in states:
        counts[state.status] += 1
    counts = {status: n for status, n in counts.items() if n}
    return DayCell(next(iter(counts), None), counts)


BusinessDay = Callable[[date], bool]


def _slot_times(spec: Mapping[str, Any], day: date, business_day: BusinessDay) -> list[datetime]:
    """The job's slots on one SGT day. Business-day kinds have none on a
    weekend or public holiday; the other kinds run whatever the day."""
    weekday = (day.weekday() + 1) % 7  # launchd numbering: 0 is Sunday
    found = []
    for kind, value in spec["schedule"].items():
        if kind in BUSINESS_DAY_KINDS and not business_day(day):
            continue
        for launchd_day, hour, minute in schedule.sgt_slots({kind: value}):
            if launchd_day is None or launchd_day == weekday:
                found.append(datetime(day.year, day.month, day.day, hour, minute, tzinfo=SGT))
    return sorted(found)


def _next_slot(spec: Mapping[str, Any], after: datetime, business_day: BusinessDay) -> datetime | None:
    """The first slot of the job later than `after`: where its window ends."""
    day = after.date()
    for _ in range(LOOKAHEAD_DAYS):
        later = [at for at in _slot_times(spec, day, business_day) if at > after]
        if later:
            return later[0]
        day += timedelta(days=1)
    return None


def classify(
    jobs: Mapping[str, Mapping[str, Any]],
    records: Iterable[Record],
    now: datetime,
    days: Iterable[date],
    *,
    installed: Container[str] | None = None,
    business_day: BusinessDay = holidays.is_business_day,
) -> dict[tuple[str, date], list[SlotState]]:
    """Every slot of every job on each of `days`, with its slot status.

    - `jobs` maps a job name to its `settings.yaml` spec; only `schedule` is read.
    - `records` are `Record`s from the `runs` table (runs and the skip rows of
      jobs that aren't quiet) and the JSONL mirror (`run.skipped`, `run.quiet`).
      A record read from both `events` and the mirror counts once. Pass one
      record from before the first day for each job, so the classifier knows
      the job was installed by then.
    - `installed` names the jobs loaded in launchd; a job missing from it shows
      its upcoming slots as not installed. None counts every job as installed.

    Every `(job, day)` pair gets a list, empty on a day with no slots.
    """
    now = now.astimezone(SGT)
    days = sorted(set(days))
    by_job: dict[str, dict[tuple, Record]] = {}
    for record in records:
        by_job.setdefault(record.job, {}).setdefault(record.key, record)

    result: dict[tuple[str, date], list[SlotState]] = {}
    for job, spec in jobs.items():
        mine = sorted(by_job.get(job, {}).values(), key=lambda record: record.at)
        first = mine[0].at if mine else None
        loaded = installed is None or job in installed
        times = [at for day in days for at in _slot_times(spec, day, business_day)]
        ends = [_next_slot(spec, at, business_day) for at in times]
        windows: list[list[Record]] = [[] for _ in times]
        for record in mine:
            if record.outside_schedule:
                continue
            index = bisect_right(times, record.at) - 1
            if index < 0:
                continue  # before the first day shown: it only marks the job as installed
            end = ends[index]
            if end is None or record.at < end:
                windows[index].append(record)
        for day in days:
            result[(job, day)] = []
        for at, end, window in zip(times, ends, windows):
            result[(job, at.date())].append(_state(job, at, end, window, now, first, loaded))
    return result


def _state(
    job: str, at: datetime, end: datetime | None, window: list[Record], now: datetime, first: datetime | None, loaded: bool
) -> SlotState:
    """One slot's status: the latest run in its window wins over any skip;
    a skip counts only when nothing ran; with nothing recorded, the clock, the
    job's first record and its install state decide."""
    found = tuple(window)  # already oldest first
    runs = [record for record in window if not record.is_skip]
    if runs:
        latest = runs[-1]
        return SlotState(job, at, "ok" if latest.kind == QUIET else latest.status or "running", records=found)
    if window:
        return SlotState(job, at, "skipped", window[-1].reason, records=found)
    if first is None or at < first:
        return SlotState(job, at, "not installed")
    if at > now:
        return SlotState(job, at, "upcoming" if loaded else "not installed")
    if end is None or end > now:
        return SlotState(job, at, "due")
    return SlotState(job, at, "missed")
