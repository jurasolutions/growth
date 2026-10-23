"""The weekly rhythm (PRD §5.2): which theme a day gets, and what comes next
when nothing good fits."""

from __future__ import annotations

from datetime import date, timedelta

from jura_growth.agents.social.settings import WEEKDAYS, Settings, Theme


def weekday(day: date) -> str:
    return WEEKDAYS[day.weekday()]


def is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def theme_for(day: date, settings: Settings) -> Theme:
    return settings.theme(settings.rhythm[weekday(day)])


def fallbacks(day: date, settings: Settings) -> list[Theme]:
    """The themes to try, in order, when today's doesn't fit: the next day's,
    then the one after, each once."""
    seen = {settings.rhythm[weekday(day)]}
    order = []
    for offset in range(1, 8):
        theme_id = settings.rhythm[weekday(day + timedelta(days=offset))]
        if theme_id not in seen:
            seen.add(theme_id)
            order.append(settings.theme(theme_id))
    return order


def posting_allowed(day: date, settings: Settings) -> str | None:
    """A reason not to post on `day`, or None."""
    if is_weekend(day) and not settings.weekends:
        return "weekend posts are off (config/social.yaml: weekends: false)"
    return None
