"""Built snapshots for the morning picture's tests (test strategy: Q, T, B, H and W).

Everything here is plain data: a `mission.Snapshot` built by hand, with no database. The clock is
Tue 2026-11-10 09:00 SGT unless a fixture says otherwise.

- `quiet()` (Q): every agent ran, nothing waits, nothing is broken.
- `typical()` (T): two requests, one thing to fix, a draft to post by hand, a reply to read.
- `database_missing()` and `database_locked()` (B): the bad day.
- `health_pages()` (H): one page per real wording in the health strip.
- `worst()` (W): as much as a page can ever hold, with the hardest text to lay out.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from jura_growth import health, mission, slots
from jura_growth.agents import outreach
from jura_growth.agents.apps import builds, releases
from jura_growth.timeutil import SGT
from test_one_pager import HEALTH_ITEMS

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=SGT)
LATE = "2026-11-10T09:06:00+08:00"
JOBS = {"Scout": "scout-research", "Outreach": "outreach-requests", "Social": "social",
        "Community": "community", "App factory": "app-factory"}
TIMES = {"scout-research": (6, 30), "outreach-requests": (8, 30), "social": (7, 30), "community": (8, 0), "app-factory": (7, 0)}
RECORDED = {  # what the plug-ins' digests record on a quiet day: real zeros
    "leads_added": 0, "outreach_mode": "live", "emails_queued": 0, "emails_sent": 0, "replies": 0, "reply_detection": True,
    "unsubscribes": 0, "bounces": 0, "complaints": 0, "social_drafts_waiting": 0, "social_drafts_by_hand": 0, "social_published": 0,
    "community_posts_planned": 0, "app_prd_today": None,
}


def snap(now: datetime = NOW, **fields) -> mission.Snapshot:
    fields.setdefault("last_one_pager", now - timedelta(days=1))
    fields.setdefault("next_one_pager", now + timedelta(days=1))
    return mission.Snapshot(now, fields.pop("db_state", mission.OK), **fields)


def figures(**changed) -> mission.Yesterday:
    return mission.Yesterday("2026-11-10", (), 0.0, {**RECORDED, **changed})


def request(number: int, kind: str = "outreach-email", reading: str = mission.Reading.WAITING, **fields) -> mission.Request:
    values = dict(
        id=f"A-{number:04d}",
        kind=kind,
        reading=reading,
        requested_at=NOW - timedelta(hours=2),
        decide_by=NOW + timedelta(hours=7),
        use_by=None,
        posted=True,
        close_reason=None,
        reason="Send to Acme Pte Ltd",
    )
    return mission.Request(**{**values, **fields})


def slot(job: str, status: str, *, reason: str | None = None, at: datetime | None = None) -> slots.SlotStatus:
    hour, minute = TIMES.get(job, (9, 0))
    return slots.SlotStatus(job, at or NOW.replace(hour=hour, minute=minute), status, reason)


def morning(status: str = "ok", now: datetime = NOW, **statuses) -> dict:
    """Today's slots for the five agents, each `status` unless named. A value of None is no slot."""
    found = {}
    for job, (hour, minute) in TIMES.items():
        wanted = statuses.get(job.replace("-", "_"), status)
        found[(job, now.date())] = [] if wanted is None else [slot(job, wanted, at=now.replace(hour=hour, minute=minute))]
    return found


def quiet() -> mission.Snapshot:
    return snap(slots=morning(), morning=figures(), yesterday=figures(), approvals=())


def typical() -> mission.Snapshot:
    later = {
        ("publish", NOW.date()): [slot("publish", "upcoming", at=NOW.replace(hour=hour)) for hour in (10, 16)],
        ("scout-send", NOW.date()): [slot("scout-send", "upcoming", at=NOW.replace(hour=9, minute=30))],
        ("digest", NOW.date()): [slot("digest", "upcoming", at=NOW.replace(hour=17, minute=30))],
    }
    return snap(
        slots={**morning(community=None, social="skipped"), **later},
        morning=figures(leads_added=3, emails_queued=2, social_drafts_waiting=2, social_drafts_by_hand=1, app_prd_today="APP-014 Invoice chaser"),
        yesterday=mission.Yesterday("2026-11-09", (), 0.41, {**RECORDED, "emails_sent": 4, "replies": 1, "social_published": 1}),
        approvals=(request(412), request(413, "social-post", decide_by=NOW + timedelta(hours=3))),
        paused=(("social", "3 failed runs in a row"),),
    )


def database_missing() -> mission.Snapshot:
    return snap(db_state=mission.MISSING)


def database_locked() -> mission.Snapshot:
    return snap(db_state=mission.UNFINISHED_WRITE, db_error="SQLITE_BUSY")


LABEL = "APP-014 Delivery order maker"
PRD = "prd/pending/apps/prd-app-014-delivery-order-maker-2026-10-24.md"
PLUGIN_WORDINGS = {  # the plug-ins' real Fix lines, with the longest of what fills them
    **{f"app on its preview, {why}": releases.PREVIEW_LINE.format(
        app_id="APP-014", label=LABEL, request="A-0153", why=why, preview="https://claude-t-0031-app.jura-site.pages.dev")
       for why in ("skipped", "expired unanswered", releases.NEVER_PRINTED)},
    "app release waiting for main": releases.MAIN_LINE.format(sha="abc1234", app_id="APP-014", task="T-0031", label=LABEL, request="A-0153"),
    "app release approved": releases.APPROVED_LINE.format(app_id="APP-014", label=LABEL, request="A-0153"),
    "build handoff by hand": builds.HAND_BUILD_LINE.format(label=LABEL, request="A-0153", build_it=builds.build_it(PRD, "A-0153")),
    "build handoff to Dispatch": builds.DISPATCH_LINE.format(label=LABEL, request="A-0153"),
    "live outreach blocked": outreach.LIVE_BLOCKED_LINE.format(things="3 things stop", problem="RESEND_API_KEY_OUTREACH is not set in .env (a sending-only Resend key)"),
    "six unset settings": health._gap_lines(tuple(health.Gap(name) for name in (
        "RESEND_API_KEY_OUTREACH", "UNSUBSCRIBE_SECRET", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "D1_DATABASE_ID", "OUTREACH_IMAP_PASSWORD")))[0],
    "the ICP": "Put the ICP in inputs/icp.md, from the draft in outputs/growth/setup/. Scout research waits until it's there.",
}


def health_pages() -> dict[str, mission.Snapshot]:
    """One page per real wording in the strip, on an otherwise quiet day."""
    base = dict(slots=morning(), morning=figures(), yesterday=figures(), approvals=())
    pages = {cause: snap(**{**base, **fields}) for cause, fields, _ in HEALTH_ITEMS}
    pages.update({cause: snap(**base, plugin_lines=(line,)) for cause, line in PLUGIN_WORDINGS.items()})
    return pages


LONG_REASON = ("Send to the company with the longest name we could find, which has a good deal to say about itself on its "
               "own website and a very long way of saying it, so that this reason goes on and on past anything the row can "
               "hold, and then a little further still, because a request's reason is written by a person or an agent and "
               "nothing limits how long it may be.")
TOKEN = "x" * 120


def worst() -> mission.Snapshot:
    """W: 50 requests, 20 fixes, long reasons everywhere, wide figures, every warning."""
    now = datetime(2026, 11, 25, 23, 59, tzinfo=SGT)  # a wide weekday, a two-digit day
    kinds = ("outreach-email", "social-post", "community-post", "group-join", "group-rules", "app-build", "app-release")
    reasons = (LONG_REASON, TOKEN, "新加坡贸易有限公司" * 20)
    requests = tuple(
        request(9000 + n, kinds[n % len(kinds)], decide_by=now + timedelta(hours=1, minutes=n), reason=reasons[n % 3])
        for n in range(50)
    )
    fixes = tuple(f"Build handoff waiting for a builder: APP-{n:03d} {TOKEN if n == 0 else LONG_REASON}" for n in range(20))
    skip = f"{LONG_REASON} {TOKEN}"
    day = {(job, now.date()): [slot(job, "skipped", reason=skip, at=now.replace(hour=hour, minute=minute))]
           for job, (hour, minute) in TIMES.items()}
    later = {(job, now.date()): [slot(job, "upcoming", at=now + timedelta(minutes=m)) for m in (1, 2)]
             for job in ("publish", "scout-send", "digest")}
    wide = {**RECORDED, "emails_sent": 12345, "replies": 12345, "social_published": 12345,
            "unsubscribes": 12345, "bounces": 12345, "complaints": 12345}
    return snap(
        now,
        slots={**day, **later},
        morning=figures(social_drafts_waiting=12345, social_drafts_by_hand=12345),
        yesterday=mission.Yesterday("2026-11-24", (), 12345.67, wide),
        approvals=requests + tuple(request(9100 + n, reading=mission.Reading.LAPSED) for n in range(12)),
        plugin_lines=fixes,
    )


FIXTURES = {"quiet": quiet, "typical": typical, "database missing": database_missing,
            "database locked": database_locked, "worst": worst}
