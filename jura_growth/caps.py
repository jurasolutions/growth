"""Hard limits. Config may lower any of these; raising one is a code change.

The outreach caps sit below the Spam Control Act's bulk thresholds (more than
100 similar messages in 24 hours, 1,000 in 30 days, or 10,000 in a year):
see the scout PRD §4 and §5.3.
"""

from __future__ import annotations

# Outreach email
OUTREACH_PER_DAY = 20
OUTREACH_ROLLING_30_DAYS = 600
OUTREACH_ROLLING_365_DAYS = 8000
OUTREACH_FIRST_EMAILS_PER_COMPANY = 1
OUTREACH_FOLLOW_UPS_PER_COMPANY = 1
OUTREACH_PER_SEND_RUN = 1
# No live send within this many minutes of the last one, however often
# `send-due` is called. Counted in whole clock minutes, so the seconds a send
# takes never block the next 10-minute slot. A floor, so not configurable.
OUTREACH_MINUTES_BETWEEN_LIVE_SENDS = 10
# A claimed email whose send didn't complete is retried under the same
# Idempotency-Key only this long after its claim. Resend keeps a key for 24
# hours; past that a retry could be a second email, so the email is marked
# uncertain and needs a fresh approval instead (code review 06, Sp1).
OUTREACH_RETRY_WINDOW_HOURS = 23
# Warm-up by days since the first live send: (until day, daily cap).
OUTREACH_WARMUP = ((7, 5), (14, 10))
OUTREACH_WORDS_MAX = 120

# Social and community
SOCIAL_POSTS_PER_PLATFORM_PER_DAY = 1
COMMUNITY_GROUPS_PER_WEEK = 3
NO_REPEAT_DAYS = 14

# App factory
APP_PRDS_PER_DAY = 1
APP_PRDS_WAITING_MAX = 7

# Run updates (MC §4.3): model-written text in one update, in characters.
RUN_UPDATE_TEXT_CHARS = 300

# Approvals (MC §5.7). Settings may shorten a deadline, never lengthen one.
# No request waits longer than the ceiling, whatever its kind asks for.
APPROVAL_DEADLINE_MAX_DAYS = 14
OUTREACH_DECIDE_BY_BUSINESS_DAYS = 1  # 16:30 on the next business day
OUTREACH_USE_BY_BUSINESS_DAYS = 3     # 16:30 on the third business day after approval
OUTREACH_DEADLINE_TIME = "16:30"
APP_BUILD_DECIDE_BY_DAYS = 7
APP_BUILD_USE_BY_DAYS = 1
APP_RELEASE_DECIDE_BY_DAYS = 7
APP_RELEASE_USE_BY_DAYS = 14
GROUP_RULES_DECIDE_BY_DAYS = 14


def effective(hard: int, configured: int | None) -> int:
    """The configured value, never above the hard limit."""
    if configured is None:
        return hard
    return max(0, min(int(configured), hard))


def warmup_cap(days_since_first_live_send: int | None) -> int:
    """Today's daily cap under the warm-up schedule."""
    if days_since_first_live_send is None:
        return OUTREACH_WARMUP[0][1]
    for until_day, cap in OUTREACH_WARMUP:
        if days_since_first_live_send < until_day:
            return cap
    return OUTREACH_PER_DAY
