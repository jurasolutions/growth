"""Dataset D1, the fortnight (test strategy v3 §3), as the rows the engine writes.

Wed 2026-10-28 to Tue 2026-11-10, with the clock at 11:05 SGT on the last day.
Sun 2026-11-08 is Deepavali and Mon 2026-11-09 its observed holiday.

- `RUNS` are `runs` rows (runs, and the skip rows of jobs that aren't quiet).
- `EVENTS` are the `run.skipped` and `run.quiet` rows `log.event` writes to
  the `events` table; each also has its line, with the same `ts`, in `MIRROR`.
- `MIRROR` adds the two skips that reach only the JSONL mirror: the PAUSE file
  and "previous run still going".

The slot classifier's tests use it through `records()`, and the read model's
tests (MC-08) can load the same rows into a temp growth.db and mirror folder.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from jura_growth.timeutil import SGT

NOW = datetime(2026, 11, 10, 11, 5, tzinfo=SGT)
TODAY = date(2026, 11, 10)
DAYS = [date(2026, 10, 28) + timedelta(days=n) for n in range(14)]

# The jobs as in config/settings.yaml, plus publish (browser publishing:
# 27 slots a business day). Only `schedule` matters to the classifier.
JOBS = {
    "app-factory": {"agent": "app-factory", "schedule": {"daily": "06:30"}},
    "social": {"agent": "social", "schedule": {"daily": "07:00"}},
    "scout-research": {"agent": "scout", "schedule": {"business_days": "09:00"}},
    "scout-send": {
        "agent": "outreach",
        "quiet": True,
        "schedule": {"business_days_every": {"start": "09:30", "end": "16:30", "minutes": 10}},
    },
    "scout-sync": {"agent": "outreach", "schedule": {"business_days": "16:45"}},
    "community": {"agent": "community", "schedule": {"weekly": {"day": "mon", "time": "07:30"}}},
    "backup": {"agent": "backup", "schedule": {"daily": "23:30"}},
    "publish": {
        "agent": "publish",
        "quiet": True,
        "schedule": {"business_days_every": {"start": "09:00", "end": "17:40", "minutes": 20}},
    },
}

RUNS: list[dict] = []
EVENTS: list[dict] = []
MIRROR: list[dict] = []


def run(job, started_at, status="ok", summary=None, finished_at=None):
    RUNS.append(
        {
            "id": len(RUNS) + 1,
            "agent": JOBS[job]["agent"],
            "job": job,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "summary": summary,
        }
    )


def event(kind, job, ts, *, mirror_only=False, **payload):
    payload = {"job": job, **payload}
    line = {"ts": ts, "run_id": None, "agent": JOBS[job]["agent"], "level": "info", "kind": kind, "payload": payload}
    MIRROR.append(line)
    if not mirror_only:
        EVENTS.append({**{k: line[k] for k in ("ts", "run_id", "agent", "level", "kind")}, "payload_json": json.dumps(payload)})


def quiet(job, ts, reason=None):
    extra = {"reason": reason} if reason else {}
    event("run.quiet", job, ts, started_at=ts, **extra)


def every(job, day, start, end, minutes, second=2, reason=None):
    """A quiet run a few seconds after each slot from `start` to `end`."""
    hour, minute = map(int, start.split(":"))
    last = tuple(map(int, end.split(":")))
    while (hour, minute) <= last:
        quiet(job, f"{day}T{hour:02d}:{minute:02d}:{second:02d}+08:00", reason)
        minute += minutes
        hour, minute = hour + minute // 60, minute % 60


# scout-send, installed before the fortnight began.
quiet("scout-send", "2026-10-28T09:30:02+08:00")
# Thu 11-05: a 10:00 run that sent email (a run row with its real start) and
# ran long, so 10:10 found the lock taken; then the PAUSE file at 10:20.
run("scout-send", "2026-11-05T10:00:02+08:00", summary="sent 2 emails", finished_at="2026-11-05T10:13:40+08:00")
event("run.skipped", "scout-send", "2026-11-05T10:10:01+08:00", mirror_only=True, reason="previous run still going")
event("run.skipped", "scout-send", "2026-11-05T10:20:01+08:00", mirror_only=True, reason="PAUSE file: holiday")
# Fri 11-06: every slot quiet, 10:00 at 10:00:03; 16:30's window runs to Tuesday.
every("scout-send", "2026-11-06", "09:30", "09:50", 10)
quiet("scout-send", "2026-11-06T10:00:03+08:00")
every("scout-send", "2026-11-06", "10:10", "16:30", 10)
# Today: slept through 10:00, 10:10 and 10:20; launchd caught up at 10:26.
every("scout-send", "2026-11-10", "09:30", "09:50", 10)
quiet("scout-send", "2026-11-10T10:26:00+08:00")
event("run.skipped", "scout-send", "2026-11-10T10:30:01+08:00", reason="outside the send window")
every("scout-send", "2026-11-10", "10:40", "11:00", 10)

# app-factory: failed on Thursday; today's 06:30 slot ran late, after the Mac woke.
run("app-factory", "2026-10-28T06:30:05+08:00")
run("app-factory", "2026-11-05T06:30:05+08:00", "failed")
run("app-factory", "2026-11-10T08:42:00+08:00")

# social: today's run is still going.
run("social", "2026-10-28T07:00:04+08:00")
run("social", "2026-11-10T07:00:04+08:00", "running")

# scout-research: Friday's run, then the holiday skip on the observed Monday.
run("scout-research", "2026-10-28T09:00:04+08:00")
run("scout-research", "2026-11-06T09:00:04+08:00")
run("scout-research", "2026-11-09T09:00:02+08:00", "skipped", "not a business day (Deepavali)")

# scout-sync: a skip row (the agent paused) on Thursday.
run("scout-sync", "2026-10-28T16:45:03+08:00")
run("scout-sync", "2026-11-05T16:45:03+08:00", "skipped", "paused: outreach")

# community: weekly on Monday, holiday or not.
run("community", "2026-11-02T07:30:05+08:00")
run("community", "2026-11-09T07:30:05+08:00", "failed")

# backup: first record on 2026-11-02, finishing after midnight.
run("backup", "2026-11-02T23:30:04+08:00", finished_at="2026-11-03T00:04:10+08:00")
run("backup", "2026-11-09T23:30:04+08:00", finished_at="2026-11-10T00:03:55+08:00")

# publish: every slot so far today found nothing due (agents.NothingToDo).
every("publish", "2026-11-10", "09:00", "11:00", 20, second=5, reason="nothing due")


def records():
    """Every row as classifier input, reading both `events` and the mirror."""
    from jura_growth.slots import Record

    return (
        [Record.from_run(row) for row in RUNS]
        + [Record.from_event(row) for row in EVENTS]
        + [Record.from_event(line) for line in MIRROR]
    )
