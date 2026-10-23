"""Singapore business days, from `config/sg-public-holidays.yaml`."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import yaml

from jura_growth import paths, timeutil


@lru_cache(maxsize=None)
def _holidays() -> dict[date, str]:
    path = paths.config_dir() / "sg-public-holidays.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = {}
    for item in data.get("holidays", []):
        day = item["date"] if isinstance(item["date"], date) else date.fromisoformat(str(item["date"]))
        found[day] = item["name"] + (" (observed)" if item.get("observed") else "")
    return found


def holiday(day: date) -> str | None:
    return _holidays().get(day)


def is_business_day(day: date | None = None) -> bool:
    day = day or timeutil.today()
    return day.weekday() < 5 and day not in _holidays()


def next_business_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    while not is_business_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def business_days_between(start: date, end: date) -> int:
    """Business days after `start` up to and including `end`."""
    count, day = 0, start
    while day < end:
        day += timedelta(days=1)
        if is_business_day(day):
            count += 1
    return count


def coverage_warning(today: date | None = None) -> str | None:
    """A reminder when next year's holidays are missing (checked from December)."""
    today = today or timeutil.today()
    years = {d.year for d in _holidays()}
    if today.year not in years:
        return f"No {today.year} public holidays in config/sg-public-holidays.yaml"
    if today.month == 12 and today.year + 1 not in years:
        return f"Add {today.year + 1} public holidays from the MOM website to config/sg-public-holidays.yaml"
    return None
