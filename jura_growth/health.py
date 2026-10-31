"""The health strip: what "Needs you" says on the one-pager (MC §5.4).

- `setup_gaps()` is the one list of settings the engine needs and doesn't
  have. `jura-growth status` and the health strip both read it, so they never
  disagree. A gap is a name and a boolean: never a value, a prefix, a length or
  a `keychain:` service name (MC §4.3).
- `install_states()` says whether each job is loaded in launchd, through an
  injected `installed` callable, and whether its plist is out of date.
- `strip()` turns the read model (`mission.Snapshot`) into the lines under
  "Needs you".

Plug-ins add their own gaps and lines through two optional hooks, documented in
`agents/__init__.py`: `setup_gaps()` (or the `REQUIRED_SETTINGS` shorthand) and
`health(conn)`. The core never imports an agent by name.
"""

from __future__ import annotations

import plistlib
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from itertools import combinations
from typing import Any, Callable, Mapping

from jura_growth import agents, config, discord, holidays, schedule, timeutil

_SETTING = re.compile(r"[A-Z][A-Z0-9_]*")
DISCORD = "Discord"
# Core settings: approvals.py refuses every Dispatch decision without this one.
CORE_SETTINGS = ("CONTROL_DISCORD_USER_ID",)


@dataclass(frozen=True)
class Gap:
    """One setting the engine checks. `ok` says whether it is as it should be:
    set, or, for a `must_be_unset` setting (one that breaks a job when it is
    there, such as an API key that hides the publish job's Chrome tools), not
    set. The core's Discord check also carries how many webhooks are set
    (`have` of `of`)."""

    name: str
    ok: bool = False
    have: int | None = None
    of: int | None = None
    must_be_unset: bool = False

    def __post_init__(self) -> None:
        """Names, booleans and counts only (MC §4.3): anything else would let a
        value into a line that `status` prints as it is."""
        if not isinstance(self.ok, bool) or not isinstance(self.must_be_unset, bool):
            raise ValueError("a setup gap's ok and must_be_unset are True or False")
        counted = self.of is not None
        if counted and self.name != DISCORD:
            raise ValueError("only the Discord check counts webhooks")
        if counted and not all(isinstance(n, int) and not isinstance(n, bool) for n in (self.have, self.of)):
            raise ValueError("the Discord check counts whole webhooks")
        if not counted and not (isinstance(self.name, str) and _SETTING.fullmatch(self.name)):
            raise ValueError(f"a setup gap names a setting, such as RESEND_API_KEY_OUTREACH, not {self.name!r}")

    @property
    def line(self) -> str:
        if self.of is not None:
            return f"{DISCORD}: {self.have} of {self.of} webhooks"
        if self.must_be_unset:
            return f"`{self.name}`: {'not set' if self.ok else 'set, and must not be'}"
        return f"`{self.name}`: {'set' if self.ok else 'not set'}"


def _discord() -> Gap:
    channels = discord.channels()
    have = sum(1 for channel in channels if discord.webhook_set(channel))
    return Gap(DISCORD, ok=have == len(channels), have=have, of=len(channels))


def _plugin_checks(module) -> list[Gap]:
    """A plug-in's gaps, from its `setup_gaps()` or its `REQUIRED_SETTINGS`.
    Only the core counts Discord webhooks. A check that raises, or names
    something that isn't a setting, is one gap, `<NAME>_SETUP_CHECK`."""
    hook = getattr(module, "setup_gaps", None)
    try:
        if hook is None:
            return [Gap(name, ok=config.is_set(name)) for name in getattr(module, "REQUIRED_SETTINGS", ())]
        return [gap for gap in hook() if isinstance(gap, Gap) and gap.name != DISCORD]
    except Exception:  # noqa: BLE001 - a broken check is a gap, never a crash or a leaked error
        name = re.sub(r"[^A-Z0-9]+", "_", str(getattr(module, "NAME", "plugin")).upper()).strip("_") or "PLUGIN"
        return [Gap(f"{name}_SETUP_CHECK")]


INSTALLED, OUT_OF_DATE, NOT_INSTALLED = "installed", "out of date", "not installed"


def install_states(jobs: Mapping[str, Mapping[str, Any]], installed: Callable[[str], bool]) -> dict[str, str]:
    """Each job's install state. `installed(job)` says whether launchd has it
    loaded (`schedule.installed`, or a test's fake). A loaded job whose plist in
    `~/Library/LaunchAgents` differs from what the schedule would generate now
    is out of date. Nothing is rendered or written (round 2 decisions §2)."""
    found = {}
    for job, spec in jobs.items():
        try:
            loaded = bool(installed(job))
        except Exception:  # noqa: BLE001 - launchctl missing or refusing: say not installed
            loaded = False
        if not loaded:
            found[job] = NOT_INSTALLED
            continue
        try:
            with open(schedule.launch_agents_dir() / f"{schedule.label(job)}.plist", "rb") as handle:
                current = plistlib.load(handle) == schedule.plist(job, dict(spec))
        except Exception:  # noqa: BLE001 - missing or unreadable: it can't be the current one
            current = False
        found[job] = INSTALLED if current else OUT_OF_DATE
    return found


def setup_gaps() -> list[Gap]:
    """Every setting the engine needs that isn't set: the core's (the Discord
    webhooks, and the Discord user id every Dispatch decision is checked
    against), then each plug-in's, in plug-in order."""
    checks = [_discord(), *(Gap(name, ok=config.is_set(name)) for name in CORE_SETTINGS)]
    for module in agents.plugins():
        checks += _plugin_checks(module)
    return [gap for gap in checks if not gap.ok]


# --- the strip ------------------------------------------------------------------------

MISSED_SHOWN = 4  # slot times listed per job before "and N more"


def day_label(moment: datetime) -> str:
    return f"{moment:%a} {moment.day} {moment:%b}"


def _plural(n: float, word: str, many: str | None = None) -> str:
    return f"{n:g} {word if n == 1 else many or word + 's'}"


def previous_business_day_start(now: datetime) -> datetime:
    """Midnight SGT at the start of the business day before `now`'s day."""
    day = now.date() - timedelta(days=1)
    for _ in range(14):
        if holidays.is_business_day(day):
            break
        day -= timedelta(days=1)
    return timeutil.midnight(day)


def strip(snapshot, *, short: bool = False) -> list[str]:
    """The "Needs you" items, in the order of MC §5.4. Empty means nothing
    needs Ting Yu. `snapshot` is a `mission.Snapshot`; its strings are
    already masked. `short` is the morning picture's Fix wording: each item
    with the action first, on one line apart from a failed run's own words in
    a quote, and a job's missed slots as a count without the times."""
    from jura_growth import mission  # mission imports this module
    from jura_growth.run_update import untrusted_line

    def worded(long: str, brief: str) -> str:
        return brief if short else long

    items: list[str] = []
    if snapshot.pause_file:
        items.append(worded(f"The PAUSE file is in place, so every job is paused ({snapshot.pause_file}). Delete it on the Mac to resume.",
                            f"Delete the PAUSE file on the Mac to resume. Every job is paused: {snapshot.pause_file}."))
    for agent, reason in snapshot.paused:
        items.append(worded(f"`{agent}` is paused: {reason}. Send `/growth resume {agent}`.",
                            f"Send `/growth resume {agent}` to resume. Paused: {reason}."))
    for failure in snapshot.failures:
        # A claude job's error is the model's own `FAIL:` line: untrusted (MC §4.3, final review Sp2).
        error = untrusted_line(failure.error) if failure.error else ""
        item = f"`{failure.job}` failed on {timeutil.when(failure.at)}." + (f"\n> {error}" if error else "")
        items.append(worded(item, f"Check `{failure.job}`: it failed on {timeutil.when(failure.at)}." + (f"\n> {error}" if error else "")))
    if snapshot.drift is not None:
        items.append(snapshot.drift.line)
    items += _missed_counts(snapshot) if short else _missed(snapshot)
    waiting_in_outbox = max(snapshot.undelivered, snapshot.outbox)
    if waiting_in_outbox:
        verb = "waits" if waiting_in_outbox == 1 else "wait"
        count = _plural(waiting_in_outbox, "Discord message")
        items.append(worded(f"{count} since the last one-pager {verb} in the outbox. Check the webhooks with `jura-growth discord test`.",
                            f"Run `jura-growth discord test`: {count} {verb} in the outbox."))
    requests = snapshot.approvals or ()
    waiting = [r for r in requests if not r.posted and r.reading in (mission.Reading.WAITING, mission.Reading.APPROVED)]
    items += [f"{r.id} ({r.kind}) has no card: {r.refused}. Nothing goes out, and it lapses {timeutil.when(r.decide_by)}."
              for r in waiting if r.refused]
    unposted = [r.id for r in waiting if not r.refused]
    if unposted:
        items.append(f"Not posted to #approvals yet: {', '.join(unposted)}. The heartbeat posts {'it' if len(unposted) == 1 else 'them'}.")
    for r in requests:
        if r.reading == mission.Reading.LAPSED_UNUSED:
            items.append(f"{r.id} ({r.kind}) was approved but not used before its use-by" + (f", {timeutil.when(r.use_by)}." if r.use_by else "."))
    for state, text, brief in (
        (NOT_INSTALLED, "Jobs not installed: {}. Run `jura-growth schedule install` on the Mac.",
         "Run `jura-growth schedule install` on the Mac. Not installed: {}."),
        (OUT_OF_DATE, "Jobs installed but out of date: {}. Run `jura-growth schedule install` again.",
         "Run `jura-growth schedule install` again. Out of date: {}."),
    ):
        jobs = [job for job, found in snapshot.installs.items() if found == state]
        if jobs:
            items.append((brief if short else text).format(", ".join(jobs)))
    items += _gap_lines(snapshot.gaps) if short else [gap.line for gap in snapshot.gaps]
    items += _database_action_first(snapshot, mission) if short else _database(snapshot, mission)
    items += list(snapshot.plugin_lines)
    items += [f"A plug-in failed to load: {broken}" for broken in snapshot.broken]
    return items


@dataclass(frozen=True)
class Drift:
    """Scheduled jobs firing at the wrong time of day, all by the same amount."""

    job: str
    due: str  # HH:MM SGT
    ran: str  # HH:MM SGT
    hours: float

    @property
    def line(self) -> str:
        return (f"Scheduled jobs are running about {_plural(abs(self.hours), 'hour')} off: `{self.job}` is due at {self.due} SGT and "
                f"ran at {self.ran} SGT. Posting and sending windows are missed while this lasts. Most likely launchd kept "
                "an old time zone. Restart the Mac once. If it's still off tomorrow, run `jura-growth schedule install`.")


DRIFT_MINIMUM = timedelta(minutes=30)
DRIFT_TOLERANCE = timedelta(minutes=5)
DRIFT_LOOKBACK = timedelta(days=3)  # a paused job's old runs hold no alarm
_DAY = timedelta(days=1)


@dataclass(frozen=True)
class _SteadilyOff:
    """One daily job whose last two runs missed its slot by the same amount."""

    job: str
    slot: time
    gap: timedelta
    newest: datetime


def schedule_drift(starts: Mapping[str, list[datetime]], jobs: Mapping[str, Mapping[str, Any]], now: datetime) -> Drift | None:
    """Whether the daily jobs fire at the wrong SGT time. `starts` holds each job's last runs, newest
    first; a job counts when it has one daily slot and two runs in the last `DRIFT_LOOKBACK`.

    It takes the largest group of jobs steadily off by the same amount, so one job off by something
    else doesn't hide it. The group needs two slots more than `DRIFT_TOLERANCE` apart. That is what
    rules out a late wake, even one at the same time every day: jobs firing together at a wake are
    off by amounts that differ by exactly the distance between their slots. A daily job within
    `DRIFT_TOLERANCE` of its slot since the group's newest run means the clock is right again, so the
    morning after a restart is quiet, though the jobs that haven't run since still hold their last
    two drifted runs. launchd fires within seconds of a slot, so that narrow window is enough, and a
    wake that merely lands near a slot doesn't silence a real drift. A run between that window and
    `DRIFT_MINIMUM` counts as neither off nor on time."""
    off: list[_SteadilyOff] = []
    on_time: list[datetime] = []
    for job, spec in jobs.items():
        slot = _daily_slot(spec)
        recent = (run.astimezone(timeutil.SGT) for run in (starts.get(job) or [])[:2])
        runs = [run for run in recent if now - run <= DRIFT_LOOKBACK]
        if slot is None or not runs:
            continue
        gaps = [_gap(run, slot) for run in runs]
        if abs(gaps[0]) <= DRIFT_TOLERANCE:
            on_time.append(runs[0])
        elif len(gaps) == 2 and min(abs(gaps[0]), abs(gaps[1])) >= DRIFT_MINIMUM and _apart(*gaps) <= DRIFT_TOLERANCE:
            off.append(_SteadilyOff(job, slot, gaps[0], runs[0]))
    group = _largest_group(off)
    if not group or any(run > max(member.newest for member in group) for run in on_time):
        return None
    first = group[0]
    return Drift(first.job, first.slot.strftime("%H:%M"), first.newest.strftime("%H:%M"), round(first.gap.total_seconds() / 1800) / 2)


def _daily_slot(spec: Mapping[str, Any]) -> time | None:
    """The job's one daily slot. None without one, or when it isn't a valid HH:MM."""
    try:
        return datetime.strptime(str((spec.get("schedule") or {}).get("daily")), "%H:%M").time()
    except ValueError:
        return None


def _after_midnight(clock: datetime | time) -> timedelta:
    return timedelta(hours=clock.hour, minutes=clock.minute)


def _gap(run: datetime, slot: time) -> timedelta:
    """How far a run's time of day is from its slot, from -12 hours up to, not including, +12."""
    half = _DAY / 2
    return (_after_midnight(run) - _after_midnight(slot) + half) % _DAY - half


def _apart(one: timedelta, other: timedelta) -> timedelta:
    """The distance between two times of day, the short way round the clock."""
    return min((one - other) % _DAY, (other - one) % _DAY)


def _largest_group(off: list[_SteadilyOff]) -> list[_SteadilyOff]:
    """The most jobs whose gaps all fall within `DRIFT_TOLERANCE`, slots far enough apart. Empty if none."""
    groups = ([member for member in off if (member.gap - start.gap) % _DAY <= DRIFT_TOLERANCE] for start in off)
    return max((group for group in groups if _slots_apart(group)), key=len, default=[])


def _slots_apart(group: list[_SteadilyOff]) -> bool:
    return any(
        _apart(_after_midnight(one.slot), _after_midnight(other.slot)) > DRIFT_TOLERANCE
        for one, other in combinations(group, 2)
    )


def _missed(snapshot) -> list[str]:
    since = previous_business_day_start(snapshot.now)
    by_job: dict[str, list[datetime]] = {}
    for (job, _), statuses in snapshot.slots.items():
        by_job.setdefault(job, []).extend(slot.at for slot in statuses if slot.status == "missed" and slot.at >= since)
    items = []
    for job, times in by_job.items():
        if not times:
            continue
        times.sort()
        # "; " because each time holds a comma of its own.
        shown = "; ".join(timeutil.when(at) for at in times[:MISSED_SHOWN])
        more = f" and {len(times) - MISSED_SHOWN} more" if len(times) > MISSED_SHOWN else ""
        items.append(f"`{job}` missed {_plural(len(times), 'slot')} since {day_label(since)}: {shown}{more}.")
    return items


def _database(snapshot, mission) -> list[str]:
    problem = mission.db_problem(snapshot)
    return [problem.strip] if problem else []


# --- the short wording (the morning picture's Fix) --------------------------------------


def _missed_counts(snapshot) -> list[str]:
    """Each job's missed slots as a count, with no times."""
    since = previous_business_day_start(snapshot.now)
    counts: dict[str, int] = {}
    for (job, _), statuses in snapshot.slots.items():
        counts[job] = counts.get(job, 0) + sum(1 for slot in statuses if slot.status == "missed" and slot.at >= since)
    return [f"Check `{job}`: it missed {_plural(n, 'slot')} since {day_label(since)}." for job, n in counts.items() if n]


def _gap_lines(gaps) -> list[str]:
    """The setup gaps, action first, with every setting that is simply unset on one line. Up to
    three names fit the picture's row; past that its first line says where they are listed."""
    unset, lines = [], []
    for gap in gaps:
        if gap.of is not None:
            lines.append(f"Set the {DISCORD} webhooks: {gap.have} of {gap.of} are set.")
        elif gap.must_be_unset:
            lines.append(f"Unset `{gap.name}`: it must not be set.")
        else:
            unset.append(f"`{gap.name}`")
    if len(unset) > 3:
        return lines + [f"Run `jura-growth status` for the {len(unset)} settings to set.\nNot set: {', '.join(unset)}."]
    return lines + ([f"Set {', '.join(unset)}."] if unset else [])


def _database_action_first(snapshot, mission) -> list[str]:
    """The database line with what to send first, so a long list of migrations can't cut it."""
    problem = mission.db_problem(snapshot)
    if not problem:
        return []
    what, _, action = problem.strip.partition(". ")
    return [f"{action.rstrip('.')}: {what}." if action else problem.strip]
