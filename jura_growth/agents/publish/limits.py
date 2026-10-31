"""The publish limits as they apply now: `caps.py`, tightened by `config/publish.yaml`.

`config/publish.yaml` may tighten a limit and never loosen it (browser publishing PRD §4.4,
§5.10). A count may only go down, the gap between two actions may only grow, and the posting
window may only narrow. A looser value reads as the hard one. A window that makes no sense
(the end before the start, a time that isn't HH:MM) raises `LimitsError`, so a typo stops
publishing instead of widening it.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from jura_growth import caps, config, timeutil


# A social post is decided this long before the window closes, so an approval always has a
# publish slot left: the last run starts at 17:40, and a claim needs 20 minutes since the last one
# (`minutes_between_actions`, which config may lengthen: then fewer of those slots can claim).
DECIDE_BEFORE_CLOSE = timedelta(hours=1)


class LimitsError(ValueError):
    pass


def _settings() -> dict:
    return config.agent_config("publish") or {}


def _clock(value, what: str) -> time:
    try:
        hour, minute = (int(part) for part in str(value).split(":"))
        return time(hour, minute)
    except (TypeError, ValueError):
        raise LimitsError(f"publish.yaml {what} must be HH:MM, not {value!r}") from None


def window() -> tuple[time, time]:
    """(start, end) of today's posting window in SGT: the hard window, narrowed by config."""
    hard_start, hard_end = (_clock(v, "window") for v in caps.PUBLISH_WINDOW)
    configured = _settings().get("window")
    if configured is None:
        return hard_start, hard_end
    if not isinstance(configured, dict):
        raise LimitsError("publish.yaml window must be {start: HH:MM, end: HH:MM}")
    start = max(hard_start, _clock(configured.get("start", caps.PUBLISH_WINDOW[0]), "window.start"))
    end = min(hard_end, _clock(configured.get("end", caps.PUBLISH_WINDOW[1]), "window.end"))
    if start >= end:
        raise LimitsError(f"publish.yaml window starts at {start:%H:%M}, which isn't before its end, {end:%H:%M}")
    return start, end


def window_on(day: date) -> tuple[datetime, datetime]:
    start, end = window()
    return (datetime.combine(day, start, tzinfo=timeutil.SGT), datetime.combine(day, end, tzinfo=timeutil.SGT))


def decide_by_on(day: date) -> datetime:
    """When a social post for `day` must be decided: 17:00 SGT, or earlier when the window narrows."""
    start, end = window_on(day)
    return max(start, end - DECIDE_BEFORE_CLOSE)


def last_run_on(day: date) -> datetime:
    """When the last publish run that can claim on `day` starts: the job's last slot inside the
    window, or the window's end when the schedule names none."""
    from jura_growth import schedule

    start, end = window_on(day)
    planned = (config.settings().get("jobs", {}).get("publish") or {}).get("schedule") or {}
    slots = [datetime.combine(day, time(hour, minute), tzinfo=timeutil.SGT) for _, hour, minute in schedule.sgt_slots(planned)]
    inside = [slot for slot in slots if start <= slot < end]
    return max(inside) if inside else end


def in_window(moment: datetime) -> bool:
    start, end = window_on(moment.astimezone(timeutil.SGT).date())
    return start <= moment < end


def items_per_run() -> int:
    return caps.effective(caps.PUBLISH_ITEMS_PER_RUN, _settings().get("items_per_run"))


def community_posts_per_day() -> int:
    return caps.effective(caps.COMMUNITY_POSTS_PER_DAY, _settings().get("community_posts_per_day"))


def community_joins_per_week() -> int:
    """The weekly join cap: `caps.py`, lowered by `community_joins_per_week` here or by
    `joins_per_week` in `config/community.yaml` (BP §5.10); the lower one wins."""
    from jura_growth.agents.community import groups as groups_mod

    hard = caps.effective(caps.COMMUNITY_JOINS_PER_WEEK, _settings().get("community_joins_per_week"))
    return caps.effective(hard, (groups_mod.settings() or {}).get("joins_per_week"))


def minutes_between_actions() -> int:
    configured = _settings().get("minutes_between_actions")
    hard = caps.PUBLISH_MINUTES_BETWEEN_ACTIONS
    return hard if configured is None else max(hard, int(configured))
