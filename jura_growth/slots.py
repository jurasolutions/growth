"""Slot statuses: what happened at each scheduled time of each job (MC §4.5).

Pure. The schedule, the records and the clock come in; slot statuses come out.
Nothing here opens growth.db or the JSONL mirror: the read model (`mission.py`)
gathers the records and this module only judges them. The one thing read from
disk is the holiday list, through `holidays.is_business_day` (cached once per
process), and a caller may pass its own `business_day` instead.

The rules:

- A slot owns the window from its own time up to the next slot of the same
  job, so a run launchd started late after the Mac woke still counts for it.
- Within one window the latest run wins over any skipped run; a skipped run
  counts only when nothing ran.
- A skipped run whose reason starts "not a business day", or that was recorded
  on a day with no slot for its job, counts for no slot.
- With nothing recorded, a slot is upcoming before its time, due while its
  window is open, and missed once the next slot has passed. If that next slot
  found the lock taken ("previous run still going"), the slot is running: a
  quiet job writes nothing until it finishes.
- Slots before a job's first record are not installed, and so are the upcoming
  slots of a job that isn't loaded in launchd.
- A slot with no trace from before the job's plist was last installed is not
  installed either. A job moved to a later time would otherwise read as missed
  on the day it moved: its old run landed before the new slot, so it counts for
  the slot before. The cost: any `schedule install` also clears true misses from
  before it. Installs are rare and deliberate, so that is accepted.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache
from typing import Any, Callable, Container, Iterable, Mapping

from jura_growth import holidays, locks, schedule, timeutil
from jura_growth.timeutil import SGT

RUN, SKIPPED, QUIET = "run", "run.skipped", "run.quiet"
# Slot statuses, the one that most needs attention first (MC SC2, AC-M2.3).
WORST_FIRST = ("failed", "missed", "running", "ok", "skipped", "due", "upcoming", "not installed")
RUN_STATUSES = ("ok", "failed", "running")  # what a finished or open `runs` row can say
LOOKAHEAD_DAYS = 31  # how far to look for the next slot that closes a window

BusinessDay = Callable[[date], bool]


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
        `payload`) or an `events` row (with `payload_json`), as a dict or a
        `sqlite3.Row`."""
        payload = event["payload"] if "payload" in event.keys() else json.loads(event["payload_json"] or "{}")
        return cls(
            kind=event["kind"],
            job=payload["job"],
            ts=event["ts"],
            reason=payload.get("reason"),
            started_at=payload.get("started_at"),
        )

    @classmethod
    def from_run(cls, row: Mapping[str, Any]) -> Record:
        """A `runs` row, as a dict or a `sqlite3.Row`. A skipped run's reason
        is its summary."""
        status = row["status"]
        return cls(
            kind=RUN,
            job=row["job"],
            ts=row["started_at"],
            status=status,
            reason=row["summary"] if status == "skipped" and "summary" in row.keys() else None,
        )

    @property
    def key(self) -> tuple[str, str, str, str | None]:
        """The same record read from `events` and from the mirror (MC §4.5)."""
        return (self.kind, self.ts, self.job, self.reason)

    @property
    def at(self) -> datetime:
        return timeutil.parse(self.started_at or self.ts).astimezone(SGT)

    @property
    def is_skipped_run(self) -> bool:
        return self.kind == SKIPPED or (self.kind == RUN and self.status == "skipped")

    @property
    def run_status(self) -> str:
        """The slot status a run gives its slot. A status no slot status
        matches, which an `after_run` hook could return, reads as failed."""
        if self.kind == QUIET:
            return "ok"
        return self.status if self.status in RUN_STATUSES else "failed"


@dataclass(frozen=True)
class SlotStatus:
    """One slot of a job and what happened at it."""

    job: str
    at: datetime
    status: str
    reason: str | None = None  # a skipped run's reason
    records: tuple[Record, ...] = ()  # what landed in the slot's window, oldest first


@dataclass(frozen=True)
class DayCell:
    """One job's day in the grid: the worst slot status, and how many slots
    had each status (in `WORST_FIRST` order)."""

    status: str | None
    counts: dict[str, int]


def day_cell(statuses: Iterable[SlotStatus]) -> DayCell:
    counts = {status: 0 for status in WORST_FIRST}
    for slot in statuses:
        counts[slot.status] += 1
    counts = {status: n for status, n in counts.items() if n}
    return DayCell(next(iter(counts), None), counts)


def classify(
    jobs: Mapping[str, Mapping[str, Any]],
    records: Iterable[Record],
    now: datetime,
    days: Iterable[date],
    *,
    installed: Container[str] | None = None,
    installed_at: Callable[[str], datetime | None] | None = None,
    business_day: BusinessDay = holidays.is_business_day,
) -> dict[tuple[str, date], list[SlotStatus]]:
    """Every slot of every job on each of `days`, with its slot status.

    - `jobs` maps a job name to its `settings.yaml` spec; only `schedule` is read.
    - `records` are `Record`s from the `runs` table (runs and the skip rows of
      jobs that aren't quiet) and the JSONL mirror (`run.skipped`, `run.quiet`).
      A record read from both `events` and the mirror counts once. Pass one
      record from before the first day for each job, so the classifier knows
      the job was installed by then.
    - `now` is the clock; a time with no zone is SGT, as `timeutil.parse` reads it.
    - `installed` names the jobs loaded in launchd; a job missing from it shows
      its upcoming slots as not installed. None counts every job as installed.
    - `installed_at` says when a job's plist was last installed, or None for no
      such moment (`schedule.installed_at`, or a test's fake).

    Every `(job, day)` pair gets a list, empty on a day with no slots.
    """
    now = (now if now.tzinfo else now.replace(tzinfo=SGT)).astimezone(SGT)
    days = sorted(set(days))
    by_job: dict[str, dict[tuple, Record]] = {}
    for record in records:
        by_job.setdefault(record.job, {}).setdefault(record.key, record)

    result: dict[tuple[str, date], list[SlotStatus]] = {}
    for job, spec in jobs.items():
        since = installed_at(job) if installed_at else None
        since = min(since, now) if since else None  # a wrong clock at install can't hide an upcoming slot
        judge = _Job(job, spec["schedule"], by_job.get(job, {}).values(), now, installed is None or job in installed, business_day, since)
        for day in days:
            result[(job, day)] = judge.day(day)
    return result


def slot_times(shape: Mapping[str, Any], day: date, business_day: BusinessDay = holidays.is_business_day) -> list[datetime]:
    """A schedule's slots on one SGT day. A job with any business-day shape
    has none on a weekend or public holiday, as the runner skips it."""
    if schedule.business_days_only(dict(shape)) and not business_day(day):
        return []
    weekday = schedule.launchd_weekday(day)
    return sorted(
        datetime(day.year, day.month, day.day, hour, minute, tzinfo=SGT)
        for launchd_day, hour, minute in schedule.sgt_slots(dict(shape))
        if launchd_day is None or launchd_day == weekday
    )


class _Job:
    """One job's records, sorted and set against its schedule."""

    def __init__(
        self, job: str, shape: Mapping[str, Any], records: Iterable[Record], now: datetime, loaded: bool, business_day: BusinessDay,
        since: datetime | None = None,
    ) -> None:
        self.job, self.shape, self.now, self.loaded, self.business_day, self.since = job, shape, now, loaded, business_day, since
        self.slot_times = cache(self._slot_times)
        mine = sorted(records, key=lambda record: record.at)
        self.first = mine[0].at if mine else None
        self.counted = [record for record in mine if self._counts(record)]
        self.times = [record.at for record in self.counted]
        self.lock_skips = [record.at for record in self.counted if record.is_skipped_run and record.reason == locks.STILL_GOING]

    def day(self, day: date) -> list[SlotStatus]:
        return [self._status(at) for at in self.slot_times(day)]

    def _slot_times(self, day: date) -> list[datetime]:
        return slot_times(self.shape, day, self.business_day)

    def _next_slot(self, after: datetime) -> datetime | None:
        """The first slot of the job later than `after`: where its window ends."""
        day = after.date()
        for _ in range(LOOKAHEAD_DAYS):
            later = [at for at in self.slot_times(day) if at > after]
            if later:
                return later[0]
            day += timedelta(days=1)
        return None

    def _counts(self, record: Record) -> bool:
        """A skipped run on a holiday, a weekend or any day with no slot for
        the job counts for no slot (MC §4.5), whatever its reason: the runner
        checks pause before the schedule."""
        if not record.is_skipped_run:
            return True
        if (record.reason or "").startswith("not a business day"):
            return False
        return bool(self.slot_times(record.at.date()))

    def _between(self, start: datetime, end: datetime | None) -> list[Record]:
        low = bisect_left(self.times, start)
        high = len(self.times) if end is None else bisect_left(self.times, end)
        return self.counted[low:high]

    def _status(self, at: datetime) -> SlotStatus:
        end = self._next_slot(at)
        window = self._between(at, end)
        runs = [record for record in window if not record.is_skipped_run]
        if runs:
            return SlotStatus(self.job, at, runs[-1].run_status, records=tuple(window))
        if window:
            return SlotStatus(self.job, at, "skipped", window[-1].reason, records=tuple(window))
        if self.first is None or at < self.first or (self.since is not None and at < self.since):
            return SlotStatus(self.job, at, "not installed")
        if at > self.now:
            return SlotStatus(self.job, at, "upcoming" if self.loaded else "not installed")
        if end is None or end >= self.now:
            return SlotStatus(self.job, at, "due")
        if self._still_going(end):
            return SlotStatus(self.job, at, "running")
        return SlotStatus(self.job, at, "missed")

    def _still_going(self, end: datetime) -> bool:
        """The next slot's window holds a "previous run still going" skip."""
        after = self._next_slot(end)
        low = bisect_left(self.lock_skips, end)
        return low < len(self.lock_skips) and (after is None or self.lock_skips[low] < after)
