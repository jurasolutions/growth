"""Scout and outreach settings, from `config/scout.yaml` over these defaults.

Both plug-ins (`scout` for research, `outreach` for sending) read the same
file. Brand-critical values (the sender name, Reply-To, the unsubscribe host)
are constants here, not config. Limits that matter sit in `caps.py` or below;
config may make them stricter, never looser.
"""

from __future__ import annotations

import copy
from typing import Any

from jura_growth import caps, config

SENDER_NAME = "Ting Yu, Jura Solutions"
SIGNATURE_NAME = "Ting Yu"
REPLY_TO = "info@jurasolutions.sg"
SITE = "jurasolutions.sg"
UNSUBSCRIBE_URL = "https://jurasolutions.sg/unsubscribe"
UNSUBSCRIBE_MAILTO = "mailto:info@jurasolutions.sg?subject=unsubscribe"

# The PRD's floor and the window's outer bounds. Config may tighten them.
SCORE_THRESHOLD_MIN = 60
DAILY_TARGET_MAX = 30
WINDOW_EARLIEST = (9, 30)
WINDOW_LATEST = (16, 30)
FOLLOW_UP_MIN_BUSINESS_DAYS = 5
RETENTION_MONTHS_MAX = 24

DEFAULTS: dict[str, Any] = {
    "mode": "shadow",
    "legal_review_done": False,
    "sending_domain": None,
    "from_local_part": "tingyu",
    "research": {
        "daily_target": 15,
        "score_threshold": 60,
        "industries_per_day": 2,
        "max_queue": 40,
        "industries": [
            "field service and maintenance",
            "logistics and delivery",
            "F&B groups",
            "renovation and interior design",
            "clinics and allied health (admin side only)",
            "accounting and corporate secretarial firms",
            "events",
            "wholesale and distribution",
            "property agencies",
            "education centres",
        ],
    },
    "send": {
        "window": {"start": "09:30", "end": "16:30"},
        "per_day": caps.OUTREACH_PER_DAY,
        "rolling_30_days": caps.OUTREACH_ROLLING_30_DAYS,
        "rolling_365_days": caps.OUTREACH_ROLLING_365_DAYS,
        "per_run": caps.OUTREACH_PER_SEND_RUN,
        "warmup_start": None,
    },
    "follow_ups": {"enabled": True, "after_business_days": 5},
    "utm": {"utm_source": "outreach", "utm_medium": "email", "utm_campaign": "scout"},
    "retention": {"lead_months": 24, "rejection_months": 12},
    "allow_named_contacts": True,
}


def _merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get() -> dict[str, Any]:
    return _merge(DEFAULTS, config.agent_config("scout") or {})


def mode() -> str:
    return str(get().get("mode") or "shadow").strip().lower()


def score_threshold() -> int:
    return max(SCORE_THRESHOLD_MIN, int(get()["research"].get("score_threshold") or SCORE_THRESHOLD_MIN))


def daily_target() -> int:
    return max(0, min(int(get()["research"].get("daily_target") or 0), DAILY_TARGET_MAX))


def max_queue() -> int:
    return max(0, int(get()["research"].get("max_queue") or 0))


def _hm(value: str) -> tuple[int, int]:
    hour, minute = str(value).split(":")
    return int(hour), int(minute)


def window() -> tuple[tuple[int, int], tuple[int, int]]:
    """The send window in SGT, never wider than 09:30–16:30."""
    configured = get()["send"].get("window") or {}
    start = max(_hm(configured.get("start", "09:30")), WINDOW_EARLIEST)
    end = min(_hm(configured.get("end", "16:30")), WINDOW_LATEST)
    return start, end


def per_day() -> int:
    return caps.effective(caps.OUTREACH_PER_DAY, get()["send"].get("per_day"))


def rolling_30() -> int:
    return caps.effective(caps.OUTREACH_ROLLING_30_DAYS, get()["send"].get("rolling_30_days"))


def rolling_365() -> int:
    return caps.effective(caps.OUTREACH_ROLLING_365_DAYS, get()["send"].get("rolling_365_days"))


def per_run() -> int:
    return caps.effective(caps.OUTREACH_PER_SEND_RUN, get()["send"].get("per_run"))


def follow_up_days() -> int:
    configured = int(get()["follow_ups"].get("after_business_days") or FOLLOW_UP_MIN_BUSINESS_DAYS)
    return max(FOLLOW_UP_MIN_BUSINESS_DAYS, configured)


def follow_ups_enabled() -> bool:
    return bool(get()["follow_ups"].get("enabled"))


def retention_months() -> int:
    return max(1, min(int(get()["retention"].get("lead_months") or RETENTION_MONTHS_MAX), RETENTION_MONTHS_MAX))


def rejection_months() -> int:
    return max(1, int(get()["retention"].get("rejection_months") or 12))


def utm() -> dict[str, str]:
    return {str(k): str(v) for k, v in (get().get("utm") or {}).items() if v}
