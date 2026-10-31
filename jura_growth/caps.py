"""Hard limits. Config may only tighten any of these: lower a count, narrow the
posting window, or lengthen a minimum gap (PUBLISH_MINUTES_BETWEEN_ACTIONS).
Loosening one is a code change.

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
OUTREACH_WORDS_MAX = 150  # scout PRD §5.6a: under 150, without the signature and footer

# Scout research (scout PRD §5.2a). Keeping more leads never means sending
# more: the outreach caps above still decide what goes out.
SCOUT_CANDIDATES_PER_RUN = 40  # candidates one research run may compare
SCOUT_SHORTLIST_PER_DAY = 10  # leads kept a day, the best by score

# Social and community
SOCIAL_POSTS_PER_PLATFORM_PER_DAY = 1
COMMUNITY_GROUPS_PER_WEEK = 3
NO_REPEAT_DAYS = 14

# Browser publishing (browser publishing PRD §4.4). A cap counts an item from
# the moment a run claims it, whatever happens next, so a run that crashes
# mid-post still uses up its slot.
BROWSER_JOBS = frozenset({"publish", "inbox-watch", "inbox-reply"})  # the only jobs that may drive Chrome
# Jobs that hold a stranger's words in the session. Each may read only the repo and its own scratch
# folder, and its transcript goes in BROWSER_TRANSCRIPT_DAYS (inbox watch, technical review B4).
THIRD_PARTY_TEXT_JOBS = BROWSER_JOBS | {"inbox-check"}
# Jobs that start in an empty folder of their own, because Claude Code runs read-only Bash commands
# unasked, and `grep -r KEY .` in the repo would reach `.env` whatever the Read rules say (code review
# 02, SEC-1). A session on hostile pages with the accounts signed in needs this most. `publish` hasn't
# moved yet, because it is a rehearsed live job. Every path a job here is handed must be absolute.
CLEAN_CWD_JOBS = frozenset({"inbox-check", "inbox-watch", "inbox-reply"})
# Days a browser job's transcript is kept: it holds third-party page text (BP §4.7).
BROWSER_TRANSCRIPT_DAYS = 7
COMMUNITY_POSTS_PER_DAY = 1
COMMUNITY_JOINS_PER_WEEK = 3  # ISO week, SGT
PUBLISH_ITEMS_PER_RUN = 1
# Between the start times of the runs that claimed two items. A floor: config
# may lengthen it, never shorten it.
PUBLISH_MINUTES_BETWEEN_ACTIONS = 20
# SGT, start inclusive and end exclusive. A post's decide-by and use-by are the
# end of the window on its day. Config may narrow it, never widen it.
PUBLISH_WINDOW = ("09:00", "18:00")

# Inbox watch (inbox watch PRD §4). Config may lower any of these, and may only lengthen the gap
# between two social replies.
INBOX_EMAIL_REPLIES_PER_DAY = 30
INBOX_SOCIAL_REPLIES_PER_DAY = 20
INBOX_MINUTES_BETWEEN_SOCIAL_REPLIES = 20
INBOX_WATCH_POSTS_PER_RUN = 8
INBOX_DECIDE_BY_DAYS = 3
INBOX_USE_BY_DAYS = 2
INBOX_TEXT_CHARS = 4000  # of a person's message, stored and shown no longer than this
INBOX_TEXT_RETENTION_DAYS = 90  # after an item closes
# One mail check stays small: fetch first and commit per message, so a decision in Discord never
# waits on the network (technical review, B5).
INBOX_BODIES_PER_CHECK = 50
INBOX_CHECK_SECONDS = 120
INBOX_FIRST_RUN_DAYS = 7
INBOX_LOOK_BACK_DAYS = 45  # the limit the 16:45 reply check uses
INBOX_OLD_AFTER_HOURS = 48  # older at intake: reported with no draft (F12)
INBOX_TRIAGE_PER_RUN = 10  # conversations handed to one triage run (technical review, B5 rule 4)
INBOX_TRIAGE_ATTEMPTS = 2  # hand-outs before a conversation is reported for a hand reply
INBOX_SUBMIT_BYTES = 64_000  # one `inbox submit` file: a class and a draft
# Each channel also limits words. A long word is still long, and an inbox card is one message (B8).
INBOX_EMAIL_DRAFT_CHARS = 1200
INBOX_EMAIL_DRAFT_LINES = 30  # each line takes a quote mark on the card
INBOX_REPLY_SUBJECT_CHARS = 120  # longer and a reply goes under a safe subject: the card shows all of what goes out
INBOX_SOCIAL_DRAFT_CHARS = 600
INBOX_GUIDANCE_CHARS = 1000  # what he types to steer a draft: he is on a phone, and triage reads it
INBOX_HIGH_REPEAT_HOURS = 24  # S7: a high item still undecided goes to #alerts once more
INBOX_USAGE_DAYS = 7  # S14: unreported days of app usage on one message
INBOX_USAGE_COUNT_MAX = 100_000_000  # a count past this from the website isn't a count
# SGT, both ends inclusive. Launchd can fire early until the Mac restarts, so the code checks too.
INBOX_CHECK_WINDOW = ("07:00", "23:59")
INBOX_SEND_WINDOW = ("08:00", "22:00")  # D3: an email reply approved outside it goes at 08:00
INBOX_WATCH_WINDOW = ("09:05", "21:05")  # SGT, both ends inclusive
# W2 says hourly. A floor under launchd, which can fire twice: each read is more activity on the account.
INBOX_WATCH_MINUTES_BETWEEN_RUNS = 55
INBOX_OBSERVATIONS_PER_RUN = 40  # new messages one watch run may record: a flood waits for the next run
INBOX_OBSERVE_FILE_BYTES = 1_000_000  # one observation file: over this it is refused whole, to be split
INBOX_WATCH_POST_DAYS = 30  # F6: posts this recent are read in turn, the least recently read first
INBOX_BLIND_SURFACE_HOURS = 3  # F13: of the watch's own hours, then it goes to Needs you

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
APP_BUILD_DECIDE_BY_DAYS = 7  # no use-by: an app build is claimed when it is approved
APP_RELEASE_DECIDE_BY_DAYS = 7
APP_RELEASE_USE_BY_DAYS = 14
GROUP_RULES_DECIDE_BY_DAYS = 14


def effective(hard: int, configured: int | None) -> int:
    """The configured value, never above the hard limit."""
    if configured is None:
        return hard
    return max(0, min(int(configured), hard))


def at_least(floor: int, configured: int | None) -> int:
    """The configured value, never below the floor: for a minimum gap, which config may only lengthen."""
    return floor if configured is None else max(floor, int(configured))


def warmup_cap(days_since_first_live_send: int | None) -> int:
    """Today's daily cap under the warm-up schedule."""
    if days_since_first_live_send is None:
        return OUTREACH_WARMUP[0][1]
    for until_day, cap in OUTREACH_WARMUP:
        if days_since_first_live_send < until_day:
            return cap
    return OUTREACH_PER_DAY
