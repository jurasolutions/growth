"""Singapore time. Every day boundary in the growth engine is an SGT day.

`JURA_GROWTH_NOW` (an ISO timestamp) freezes the clock, which is how the tests
and a manual "pretend it's Monday 09:30" run exercise windows and schedules.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")


def now() -> datetime:
    frozen = os.environ.get("JURA_GROWTH_NOW")
    if frozen:
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


def days_ago(days: int) -> datetime:
    return now_sgt() - timedelta(days=days)


def timedelta_days(days: int) -> timedelta:
    return timedelta(days=days)


def iso_week(day: date | None = None) -> str:
    """`2026-W43`, the label community plans use."""
    year, week, _ = (day or today()).isocalendar()
    return f"{year}-W{week:02d}"
