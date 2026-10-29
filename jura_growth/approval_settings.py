"""The `approvals:` block of `config/settings.yaml` (MC §5.3, §5.7; ticket review T10).

Ticket 04b creates the block; the kinds and `remote` only read it, through here.

- Three switches, each off until Ting Yu turns it on:
  `discord_buttons` (the buttons are checked, U17; unlocks live outreach),
  `post_buttons` (cards carry Approve and Skip components; needs Dispatch's own
  webhook) and `dispatch_builds` (Dispatch polls build handoffs, D6).
- `deadlines`, per kind, in the units `caps.py` uses. A value may shorten a
  deadline, never lengthen it, and never below one.
"""

from __future__ import annotations

from jura_growth import caps, config

SWITCHES = ("discord_buttons", "post_buttons", "dispatch_builds")

# (kind, key) -> the hard limit in caps.py.
DEADLINE_CAPS = {
    ("outreach-email", "decide_by_business_days"): caps.OUTREACH_DECIDE_BY_BUSINESS_DAYS,
    ("outreach-email", "use_by_business_days"): caps.OUTREACH_USE_BY_BUSINESS_DAYS,
    ("app-build", "decide_by_days"): caps.APP_BUILD_DECIDE_BY_DAYS,
    ("app-release", "decide_by_days"): caps.APP_RELEASE_DECIDE_BY_DAYS,
    ("app-release", "use_by_days"): caps.APP_RELEASE_USE_BY_DAYS,
    ("group-rules", "decide_by_days"): caps.GROUP_RULES_DECIDE_BY_DAYS,
}


def _block() -> dict:
    return config.settings().get("approvals") or {}


def switch(name: str) -> bool:
    """One of `SWITCHES`; off unless the block sets it to true."""
    if name not in SWITCHES:
        raise KeyError(f"no approvals switch {name!r}; expected one of {SWITCHES}")
    return _block().get(name) is True


def deadline(kind: str, key: str) -> int:
    """The configured deadline for `kind`, never above its cap or below one."""
    hard = DEADLINE_CAPS[(kind, key)]
    configured = ((_block().get("deadlines") or {}).get(kind) or {}).get(key)
    return max(1, caps.effective(hard, configured))
