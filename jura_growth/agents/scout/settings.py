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
from jura_growth.agents.scout import contact

# Scout PRD §5.6a (amended 2026-10-31): emails go out as Levi, and replies
# reach his mailbox. The From local part comes from config (`from_local_part`).
SENDER_NAME = "Levi Ting, Jura Solutions"
SIGNATURE_NAME = "Levi Ting"
SIGNATURE_TITLE = "Principal Consultant"
SIGNATURE_EMAIL = "levi@jurasolutions.sg"
REPLY_TO = SIGNATURE_EMAIL
SITE = "jurasolutions.sg"
# The enquiry form on the home page; `from` labels where the visitor came from.
CALL_URL = "https://jurasolutions.sg/?from=outreach#contact"
# The Jura mark as a PNG (email clients block SVG), served by the website from
# `public/email/`. 96 px, shown at 48 px for sharp retina screens.
MARK_URL = "https://jurasolutions.sg/email/jura-mark-96.png"
UNSUBSCRIBE_URL = "https://jurasolutions.sg/unsubscribe"
# Opt-outs by mail reach the same mailbox as "or reply 'unsubscribe'" (Reply-To).
UNSUBSCRIBE_MAILTO = f"mailto:{SIGNATURE_EMAIL}?subject=unsubscribe"

# The PRD's floor and the window's outer bounds. Config may tighten them.
SCORE_THRESHOLD_MIN = 60
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
        "candidates": 20,
        "shortlist": 10,
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
    "free_mail_contacts": list(contact.FREE_MAIL_CONTACTS),
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


def candidates() -> int:
    """Candidates a research run gathers and compares (§5.2a point 1), 1 to the code's ceiling."""
    configured = get()["research"].get("candidates")
    return max(1, caps.effective(caps.SCOUT_CANDIDATES_PER_RUN, 20 if configured is None else configured))


def shortlist() -> int:
    """Leads kept a day, the best by score (§5.2a point 4). Config may lower it, never raise it."""
    configured = get()["research"].get("shortlist")
    return caps.effective(caps.SCOUT_SHORTLIST_PER_DAY, 10 if configured is None else configured)


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


def free_mail_contacts() -> tuple[str, ...]:
    """The free-mail providers a contact address may use. Config may drop some
    of `contact.FREE_MAIL_CONTACTS`; a provider it adds is ignored."""
    configured = get().get("free_mail_contacts")
    if configured is None:
        return contact.FREE_MAIL_CONTACTS
    if not isinstance(configured, (list, tuple)):
        configured = [configured]
    wanted = {str(item).strip().lower() for item in configured}
    return tuple(d for d in contact.FREE_MAIL_CONTACTS if d in wanted)


def utm() -> dict[str, str]:
    return {str(k): str(v) for k, v in (get().get("utm") or {}).items() if v}
