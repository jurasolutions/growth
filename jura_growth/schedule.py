"""launchd jobs, one per entry in `settings.yaml` → `jobs`.

`jura-growth schedule render` writes the plists to `launchd/generated/` to
read; `install` copies them to `~/Library/LaunchAgents/` and loads them;
`uninstall` unloads and removes them.

launchd runs a calendar job missed while the Mac slept as soon as it wakes.
Send windows still hold, because `outreach send-due` checks the window itself.
A Mac that is switched off misses those runs; the next scheduled one carries on.

Schedule shapes (all SGT):
    {daily: "HH:MM"}
    {business_days: "HH:MM"}                    Mon–Fri; holidays skipped in code
    {business_days_every: {start, end, minutes}}
    {daily_every: {start, end, minutes}}        every day, weekends included
    {weekly: {day: mon, time: "HH:MM"}}
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from jura_growth import config, paths, timeutil

LABEL_PREFIX = "sg.jurasolutions.growth."
WEEKDAYS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
# Schedule shapes whose job skips weekends and public holidays in code.
BUSINESS_DAY_KINDS = ("business_days", "business_days_every")


def business_days_only(schedule: dict) -> bool:
    """True when the job skips a whole day that isn't a business day, as the
    runner does if any of its schedule shapes is a business-day one."""
    return bool(set(schedule) & set(BUSINESS_DAY_KINDS))


def launchd_weekday(day: date) -> int:
    """launchd's weekday numbering: 0 is Sunday."""
    return (day.weekday() + 1) % 7


def label(job: str) -> str:
    return LABEL_PREFIX + job


def launch_agents_dir() -> Path:
    return Path(os.environ.get("JURA_GROWTH_LAUNCH_AGENTS", Path.home() / "Library" / "LaunchAgents"))


def generated_dir() -> Path:
    """Where `render` writes plists. Tests point it at a temp folder with `JURA_GROWTH_PLIST_DIR`."""
    return Path(os.environ.get("JURA_GROWTH_PLIST_DIR", paths.REPO_ROOT / "launchd" / "generated"))


def _hm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def sgt_slots(schedule: dict) -> list[tuple[int | None, int, int]]:
    """(launchd weekday or None, hour, minute) in SGT."""
    slots: list[tuple[int | None, int, int]] = []
    if "daily" in schedule:
        slots.append((None, *_hm(schedule["daily"])))
    if "business_days" in schedule:
        h, m = _hm(schedule["business_days"])
        slots += [(day, h, m) for day in range(1, 6)]
    if "business_days_every" in schedule:
        for hour, minute in _every(schedule["business_days_every"]):
            slots += [(day, hour, minute) for day in range(1, 6)]
    if "daily_every" in schedule:
        slots += [(None, hour, minute) for hour, minute in _every(schedule["daily_every"])]
    if "weekly" in schedule:
        weekly = schedule["weekly"]
        slots.append((WEEKDAYS[weekly["day"][:3].lower()], *_hm(weekly["time"])))
    return slots


def _every(every: dict) -> list[tuple[int, int]]:
    """(hour, minute) from `start` to `end` inclusive, every `minutes`."""
    start, end = _hm(every["start"]), _hm(every["end"])
    step = int(every["minutes"])
    return [(m // 60, m % 60) for m in range(start[0] * 60 + start[1], end[0] * 60 + end[1] + 1, step)]


def local_offset() -> timedelta:
    return datetime.now().astimezone().utcoffset() or timedelta(0)


def to_local(slot: tuple[int | None, int, int]) -> dict:
    """A StartCalendarInterval entry in the Mac's own zone."""
    weekday, hour, minute = slot
    shift = local_offset() - timedelta(hours=8)
    # 2026-10-25 is a Sunday; launchd weekday 0 = Sunday.
    base = datetime(2026, 10, 25 + (weekday or 0), hour, minute) + shift
    entry = {"Hour": base.hour, "Minute": base.minute}
    if weekday is not None:
        entry["Weekday"] = launchd_weekday(base)
    return entry


def plist(job: str, spec: dict) -> dict:
    program = paths.REPO_ROOT / ".venv" / "bin" / "jura-growth"
    logs = paths.data_dir() / "launchd"
    home = Path.home()
    env_path = os.pathsep.join(
        [
            str(paths.REPO_ROOT / ".venv" / "bin"),
            str(home / ".local" / "bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )
    return {
        "Label": label(job),
        "ProgramArguments": [str(program), "run", job],
        "WorkingDirectory": str(paths.REPO_ROOT),
        "EnvironmentVariables": {"PATH": env_path, "PYTHONUNBUFFERED": "1"},
        "StartCalendarInterval": [to_local(s) for s in sgt_slots(spec["schedule"])],
        "StandardOutPath": str(logs / f"{job}.log"),
        "StandardErrorPath": str(logs / f"{job}.log"),
        "RunAtLoad": False,
        "ProcessType": "Background",
    }


def render(jobs: list[str] | None = None) -> list[Path]:
    specs = config.settings()["jobs"]
    out = []
    for job in jobs or list(specs):
        path = paths.writable(generated_dir() / f"{label(job)}.plist")
        with open(path, "wb") as handle:
            plistlib.dump(plist(job, specs[job]), handle)
        out.append(path)
    return out


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install(jobs: list[str] | None = None) -> list[str]:
    if not (paths.REPO_ROOT / ".venv" / "bin" / "jura-growth").exists():
        raise RuntimeError("Run `uv sync` in repos/growth first: launchd calls .venv/bin/jura-growth")
    (paths.data_dir() / "launchd").mkdir(parents=True, exist_ok=True)
    done = []
    for rendered in render(jobs):
        target = launch_agents_dir() / rendered.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(rendered.read_bytes())
        name = rendered.stem
        _launchctl("bootout", f"{_domain()}/{name}")
        result = _launchctl("bootstrap", _domain(), str(target))
        if result.returncode != 0:
            raise RuntimeError(f"launchctl bootstrap {name} failed: {result.stderr.strip()}")
        done.append(name)
    return done


def uninstall(jobs: list[str] | None = None) -> list[str]:
    specs = config.settings()["jobs"]
    done = []
    for job in jobs or list(specs):
        name = label(job)
        _launchctl("bootout", f"{_domain()}/{name}")
        target = launch_agents_dir() / f"{name}.plist"
        if target.exists():
            target.unlink()
            done.append(name)
    return done


def installed(job: str) -> bool:
    return _launchctl("print", f"{_domain()}/{label(job)}").returncode == 0


def installed_at(job: str) -> datetime | None:
    """When `install` last wrote the job's plist, or None with no plist."""
    try:
        modified = (launch_agents_dir() / f"{label(job)}.plist").stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(modified, timeutil.SGT)


def describe(spec: dict) -> str:
    schedule = spec["schedule"]
    if "daily" in schedule:
        return f"daily {schedule['daily']}"
    if "business_days" in schedule:
        return f"business days {schedule['business_days']}"
    if "business_days_every" in schedule:
        e = schedule["business_days_every"]
        return f"business days {e['start']}–{e['end']}, every {e['minutes']} min"
    if "daily_every" in schedule:
        e = schedule["daily_every"]
        return f"daily {e['start']}–{e['end']}, every {e['minutes']} min"
    if "weekly" in schedule:
        w = schedule["weekly"]
        return f"{w['day'].capitalize()} {w['time']}"
    return str(schedule)


def tz_note() -> str | None:
    if local_offset() != timedelta(hours=8):
        hours = local_offset().total_seconds() / 3600
        return f"This Mac is on UTC{hours:+g}; times are converted from SGT when installed. Reinstall after travel."
    return None


def now_label() -> str:
    return timeutil.stamp()
