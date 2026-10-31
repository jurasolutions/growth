"""The inbox limits as they apply now: `caps.py`, tightened by `config/inbox.yaml`, which may lower
a count and never raise one. Sender rules the code holds as constants are here too, and config may
only add to the platform domains that count as noise."""

from __future__ import annotations

from jura_growth import caps, config, timeutil

_HARD = {
    "email_replies_per_day": caps.INBOX_EMAIL_REPLIES_PER_DAY,
    "social_replies_per_day": caps.INBOX_SOCIAL_REPLIES_PER_DAY,
    "watch_posts_per_run": caps.INBOX_WATCH_POSTS_PER_RUN,
    "decide_by_days": caps.INBOX_DECIDE_BY_DAYS,
    "use_by_days": caps.INBOX_USE_BY_DAYS,
    "text_chars": caps.INBOX_TEXT_CHARS,
    "text_retention_days": caps.INBOX_TEXT_RETENTION_DAYS,
    "bodies_per_check": caps.INBOX_BODIES_PER_CHECK,
    "check_seconds": caps.INBOX_CHECK_SECONDS,
    "first_run_days": caps.INBOX_FIRST_RUN_DAYS,
    "look_back_days": caps.INBOX_LOOK_BACK_DAYS,
    "old_after_hours": caps.INBOX_OLD_AFTER_HOURS,
    "observations_per_run": caps.INBOX_OBSERVATIONS_PER_RUN,
    "triage_per_run": caps.INBOX_TRIAGE_PER_RUN,
}

# The website form's sender (`landing-page/functions/submit.js`, W8).
ENQUIRY_SENDER = "no_reply@jurasolutions.sg"
JURA_DOMAIN = "jurasolutions.sg"
# Senders whose mail is a platform telling Jura something, not a person writing (R2, F3).
PLATFORM_DOMAINS = (
    "facebookmail.com", "facebook.com", "instagram.com", "mail.instagram.com", "linkedin.com", "carousell.com",
    "accounts.google.com", "resend.com", "cloudflare.com", "github.com",
)


def _configured() -> dict:
    return config.agent_config("inbox") or {}


def limit(name: str) -> int:
    """A limit as it applies now, never above its hard value."""
    return caps.effective(_HARD[name], _configured().get(name))


def minutes_between_social_replies() -> int:
    """A floor: config may lengthen the gap and never shorten it."""
    return caps.at_least(caps.INBOX_MINUTES_BETWEEN_SOCIAL_REPLIES, _configured().get("minutes_between_social_replies"))


def in_hours(window: tuple[str, str]) -> bool:
    """PRD §4: launchd can fire early until the Mac restarts, so a job's hours are checked in code too."""
    start, end = window
    return start <= timeutil.now_sgt().strftime("%H:%M") <= end


def platform_domains() -> tuple[str, ...]:
    extra = _configured().get("extra_platform_domains") or ()
    return (*PLATFORM_DOMAINS, *(str(domain).strip().lower() for domain in extra))
