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
from typing import Any, Callable, Mapping

from jura_growth import agents, config, discord, schedule

_SETTING = re.compile(r"[A-Z][A-Z0-9_]*")
DISCORD = "Discord"


@dataclass(frozen=True)
class Gap:
    """One setting the engine checks. `ok` says whether it is set. The core's
    Discord check also carries how many webhooks are set (`have` of `of`)."""

    name: str
    ok: bool = False
    have: int | None = None
    of: int | None = None

    def __post_init__(self) -> None:
        counted = self.of is not None
        if counted and self.name != DISCORD:
            raise ValueError("only the Discord check counts webhooks")
        if not counted and not _SETTING.fullmatch(self.name):
            raise ValueError(f"a setup gap names a setting, such as RESEND_API_KEY_OUTREACH, not {self.name!r}")

    @property
    def line(self) -> str:
        if self.of is not None:
            return f"{DISCORD}: {self.have} of {self.of} webhooks"
        return f"`{self.name}`: {'set' if self.ok else 'not set'}"


def _discord() -> Gap:
    channels = discord.channels()
    have = sum(1 for channel in channels if discord.webhook_set(channel))
    return Gap(DISCORD, ok=have == len(channels), have=have, of=len(channels))


def _plugin_checks(module) -> list[Gap]:
    hook = getattr(module, "setup_gaps", None)
    if hook is None:
        return [Gap(name, ok=config.is_set(name)) for name in getattr(module, "REQUIRED_SETTINGS", ())]
    try:
        return [gap for gap in hook() if isinstance(gap, Gap)]
    except Exception:  # noqa: BLE001 - a broken check is a gap, never a crash or a leaked error
        name = re.sub(r"[^A-Z0-9]+", "_", str(getattr(module, "NAME", "plugin")).upper()).strip("_") or "PLUGIN"
        return [Gap(f"{name}_SETUP_CHECK")]


INSTALLED, OUT_OF_DATE, NOT_INSTALLED = "installed", "out of date", "not installed"


def install_states(jobs: Mapping[str, Mapping[str, Any]], installed: Callable[[str], bool]) -> dict[str, str]:
    """Each job's install state. `installed(job)` says whether launchd has it
    loaded (`schedule.installed`, or a test's fake). A loaded job whose plist in
    `~/Library/LaunchAgents` differs from what the schedule would generate now
    is out of date. Nothing is rendered or written (round 2 decisions §2)."""
    states = {}
    for job, spec in jobs.items():
        try:
            loaded = bool(installed(job))
        except Exception:  # noqa: BLE001 - launchctl missing or refusing: say not installed
            loaded = False
        if not loaded:
            states[job] = NOT_INSTALLED
            continue
        try:
            with open(schedule.launch_agents_dir() / f"{schedule.label(job)}.plist", "rb") as handle:
                current = plistlib.load(handle) == schedule.plist(job, dict(spec))
        except Exception:  # noqa: BLE001 - missing or unreadable: it can't be the current one
            current = False
        states[job] = INSTALLED if current else OUT_OF_DATE
    return states


def setup_gaps() -> list[Gap]:
    """Every setting the engine needs that isn't set: the core's Discord
    webhooks, then each plug-in's, in plug-in order."""
    checks = [_discord()]
    for module in agents.plugins():
        checks += _plugin_checks(module)
    return [gap for gap in checks if not gap.ok]
