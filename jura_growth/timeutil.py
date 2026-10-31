"""Singapore time. Every day boundary in the growth engine is an SGT day.

`JURA_GROWTH_NOW` (an ISO timestamp) freezes the clock, which is how the tests
and a manual "pretend it's Monday 09:30" run exercise windows and schedules.
A frozen clock refuses the live data and outputs folders: rows and files dated
on the pretend day would make that day's real run skip.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from jura_growth import paths

SGT = ZoneInfo("Asia/Singapore")


class FrozenClockRefused(RuntimeError):
    """`JURA_GROWTH_NOW` is set while the data or outputs folder is the live one."""


def frozen_clock_problem() -> str | None:
    """Why a frozen clock may not run here, or None.

    Live means at or under `jurasolutions/data/` or `jurasolutions/outputs/`.
    """
    frozen = os.environ.get("JURA_GROWTH_NOW")
    if not frozen:
        return None
    live = []
    for variable, folder, current in (
        ("JURA_GROWTH_DATA_DIR", "data", paths.data_dir()),
        ("JURA_GROWTH_OUTPUTS_DIR", "outputs", paths.outputs_dir()),
    ):
        here = current.resolve()
        if paths.is_within(here, paths.JURA_ROOT / folder):
            live.append((variable, here))
    if not live:
        return None
    return (
        f"JURA_GROWTH_NOW={frozen} freezes the clock, so this run would leave test data dated on that day in "
        + " and ".join(str(here) for _, here in live)
        + ". Point "
        + " and ".join(variable for variable, _ in live)
        + " at a temporary folder, or unset JURA_GROWTH_NOW."
    )


def now() -> datetime:
    frozen = os.environ.get("JURA_GROWTH_NOW")
    if frozen:
        problem = frozen_clock_problem()
        if problem:
            raise FrozenClockRefused(problem)
        moment = datetime.fromisoformat(frozen)
        return moment if moment.tzinfo else moment.replace(tzinfo=SGT)
    return datetime.now(SGT)


def now_sgt() -> datetime:
    return now().astimezone(SGT)


def today() -> date:
    return now_sgt().date()


def today_str() -> str:
    return today().isoformat()


def stamp(moment: datetime | None = None) -> str:
    """ISO timestamp in SGT, to the second."""
    return (moment or now_sgt()).astimezone(SGT).isoformat(timespec="seconds")


def parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=SGT)


def when(moment: datetime | str) -> str:
    """A moment as Discord shows it, in cards, the health strip, the
    one-pager and publish items alike: `Tue 10 Nov, 16:30 SGT`. Takes a
    datetime or a stored ISO stamp."""
    moment = (parse(moment) if isinstance(moment, str) else moment).astimezone(SGT)
    return f"{moment:%a} {moment.day} {moment:%b}, {moment:%H:%M} SGT"


def midnight(day: date) -> datetime:
    """The start of an SGT day."""
    return datetime(day.year, day.month, day.day, tzinfo=SGT)


def days_ago(days: int) -> datetime:
    return now_sgt() - timedelta(days=days)


def timedelta_days(days: int) -> timedelta:
    return timedelta(days=days)


def iso_week(day: date | None = None) -> str:
    """`2026-W43`, the label community plans use."""
    year, week, _ = (day or today()).isocalendar()
    return f"{year}-W{week:02d}"
