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
from datetime import datetime, timedelta
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


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else many or word + 's'}"


def previous_business_day_start(now: datetime) -> datetime:
    """Midnight SGT at the start of the business day before `now`'s day."""
    day = now.date() - timedelta(days=1)
    for _ in range(14):
        if holidays.is_business_day(day):
            break
        day -= timedelta(days=1)
    return timeutil.midnight(day)


def strip(snapshot) -> list[str]:
    """The "Needs you" items, in the order of MC §5.4. Empty means nothing
    needs Ting Yu. `snapshot` is a `mission.Snapshot`; its strings are
    already masked."""
    from jura_growth import mission  # mission imports this module
    from jura_growth.run_update import untrusted_line

    items: list[str] = []
    if snapshot.pause_file:
        items.append(f"The PAUSE file is in place, so every job is paused ({snapshot.pause_file}). Delete it on the Mac to resume.")
    for agent, reason in snapshot.paused:
        items.append(f"`{agent}` is paused: {reason}. Send `/growth resume {agent}`.")
    for failure in snapshot.failures:
        item = f"`{failure.job}` failed on {timeutil.when(failure.at)}."
        if failure.error:
            # A claude job's error is the model's own `FAIL:` line: untrusted (MC §4.3, final review Sp2).
            item += "\n> " + untrusted_line(failure.error)
        items.append(item)
    if snapshot.drift is not None:
        items.append(snapshot.drift.line)
    items += _missed(snapshot)
    waiting_in_outbox = max(snapshot.undelivered, snapshot.outbox)
    if waiting_in_outbox:
        verb = "waits" if waiting_in_outbox == 1 else "wait"
        items.append(
            f"{_plural(waiting_in_outbox, 'Discord message')} since the last one-pager {verb} in the outbox. "
            "Check the webhooks with `jura-growth discord test`."
        )
    requests = snapshot.approvals or ()
    unposted = [r.id for r in requests if not r.posted and r.reading in (mission.Reading.WAITING, mission.Reading.APPROVED)]
    if unposted:
        items.append(f"Not posted to #approvals yet: {', '.join(unposted)}. The heartbeat posts {'it' if len(unposted) == 1 else 'them'}.")
    for r in requests:
        if r.reading == mission.Reading.LAPSED_UNUSED:
            items.append(f"{r.id} ({r.kind}) was approved but not used before its use-by" + (f", {timeutil.when(r.use_by)}." if r.use_by else "."))
    for state, text in ((NOT_INSTALLED, "Jobs not installed: {}. Run `jura-growth schedule install` on the Mac."),
                        (OUT_OF_DATE, "Jobs installed but out of date: {}. Run `jura-growth schedule install` again.")):
        jobs = [job for job, found in snapshot.installs.items() if found == state]
        if jobs:
            items.append(text.format(", ".join(jobs)))
    items += [gap.line for gap in snapshot.gaps]
    items += _database(snapshot, mission)
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
        return (f"Scheduled jobs are running about {abs(self.hours):g} hours off: `{self.job}` is due at {self.due} SGT and "
                f"ran at {self.ran} SGT. Posting and sending windows are missed while this lasts. launchd's calendar "
                "keeps the time zone it started with, so restart the Mac once.")


DRIFT_MINIMUM = timedelta(minutes=30)
DRIFT_TOLERANCE = timedelta(minutes=5)
DRIFT_JOBS_NEEDED = 2  # one job off by a steady amount could be chance; two can't be a wake-up catching up


def schedule_drift(starts: Mapping[str, list[datetime]], jobs: Mapping[str, Mapping[str, Any]]) -> Drift | None:
    """Whether the daily jobs fire at the wrong SGT time: for each job with one daily slot and two
    runs, both runs off by the same amount, and at least `DRIFT_JOBS_NEEDED` jobs agreeing. A Mac
    waking late moves one slot, by a different amount each day, so it never reads as drift."""
    off: list[tuple[timedelta, str, str, str]] = []
    for job, spec in jobs.items():
        daily = (spec.get("schedule") or {}).get("daily")
        runs = starts.get(job) or []
        if not daily or len(runs) < 2:
            continue
        hour, minute = (int(part) for part in str(daily).split(":"))
        gaps = []
        for run in runs[:2]:
            at = run.astimezone(timeutil.SGT)
            minutes = ((at.hour * 60 + at.minute) - (hour * 60 + minute) + 720) % 1440 - 720
            gaps.append(timedelta(minutes=minutes))
        if abs(gaps[0]) >= DRIFT_MINIMUM and abs(gaps[0] - gaps[1]) <= DRIFT_TOLERANCE:
            off.append((gaps[0], job, str(daily), runs[0].astimezone(timeutil.SGT).strftime("%H:%M")))
    if len(off) < DRIFT_JOBS_NEEDED or max(o[0] for o in off) - min(o[0] for o in off) > DRIFT_TOLERANCE:
        return None
    gap, job, due, ran = off[0]
    return Drift(job, due, ran, round(gap.total_seconds() / 1800) / 2)


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
