"""The UAT harness for `.scratch/mission-control/uat.md` (tickets 04b and 17; X13).

Seeds the UAT data into a temporary folder, for Ting Yu to run the script against a test Discord
server. From the repo root, in the window `uat.md` sets up ("The window for Parts A and C"):

    uv run python -m tests.uat.seed "$UAT" [--scenario base] [--today YYYY-MM-DD] [--lead <id>] [--group <id>] [--page <page>]

It refuses unless `$UAT` is a temporary folder (made with `mktemp -d`) outside `jurasolutions/`, and
`JURA_GROWTH_DATA_DIR`, `JURA_GROWTH_OUTPUTS_DIR` and `JURA_PRD_DIR` all sit inside it, as does
`JURA_GROWTH_CONFIG_DIR` when it is set. So it can never write to the live `data/growth/`,
`outputs/growth/`, PRD or `config/` folders. It also refuses a folder it has already seeded. A
config folder inside `$UAT` starts as a copy of the repo's `config/`.

Every row is dated from `--today` (default: today in SGT), which must be a business day: Dispatch
stamps decisions with the real clock, so deadlines must line up with the day the UAT runs.

- `base` holds S1 (eight days of run history, with the previous business day's scout-send
  traces missing slots and a quiet run six minutes late), S2 (today's app-factory and social
  runs), S4 (the queued emails for leads 233, 240 to 254 and 260), S5 and S6 (the planted reply,
  phone number and Resend key), S7 (APP-014's PRD) and S8 (groups G4 and G7).
- `outreach-live` (S3) puts live mode in `$UAT/config` with every pre-condition met but the
  buttons switch. It needs `JURA_GROWTH_RESEND_BASE_URL` and `JURA_GROWTH_D1_BASE_URL` pointed at
  the stub (`uv run python -m tests.resend_stub`, ticket 18), and writes `do-not-contact.csv` when `JURA_INPUTS_DIR`
  is inside `$UAT`. It prints any pre-condition the window must still supply.
- `edit-draft --lead <id>` (S9) changes that lead's queued draft by hand.
- `shadow-trial` (S10) holds 40 shadow-sent emails for `requeue-shadow`.
- `note-rules --group <id>` (S13, ticket 05) records that group's rules as seen inside the group
  and raises its `group-rules` request, as `publish note-rules` will: `--group 4` is G4.

A scenario never inserts approval rows. The outreach requests come from the outreach commands
themselves, as they would live; `note-rules` raises its request through the kind's own code. Any
card a scenario raised is posted once its transaction commits. The other kinds' tickets add their
own scenarios to `SCENARIOS`.

Part C's publish scenarios (BP-02a) put Facebook in `browser` mode in `$UAT/config` and seed the
day's Facebook draft through the same code `social submit` uses, which raises its card:

- `social-post` (C1): one pending `social-post` card, decide by 18:00 on the seeded day.
- `social-approved` (C2): that card approved through the Dispatch origin, not yet claimed.
- `claimed-not-closed` (C2): claimed by a publish run that recorded neither done nor stopped, so
  it is `unknown`, publish is paused and #alerts says how to settle it. Seed it between 09:00 and
  18:00.

Part C's community scenario (BP-02b), after `base`:

- `community-plan` (C3): `community.browser` on in `$UAT/config`, G4 recorded as joined as the
  Jura Page, and a G4 post planned for the seeded day that mentions Jura, with its pending
  `community-post` card raised through the code `community publish-plan` uses. G4's rules aren't
  confirmed yet, so `publish next` refuses it once approved.

Part R's rehearsal scenarios (BP-07) need the fixture platform on (`JURA_GROWTH_PUBLISH_FIXTURE_URL`,
`jura_growth/agents/publish/fixture.py`), and refuse without it. Each seeds one approved item whose
target is a page of the fixture site, named with `--page`:

- `fixture-post` (R1 to R4, R6): a Facebook item, approved, on `page.html` (the composer) unless
  `--page` names a stop page, `link-out.html`, `injection.html` or `other-identity.html`.
- `fixture-join` (R5): a join for G9, a good-fit group whose address is `join.html` (membership
  questions) unless `--page profile-only-join.html`, approved.
- `fixture-reply`: an approved `social-reply` to a direct message at the site's own thread address,
  `direct/t/1234567/`, for `inbox-reply`'s rehearsal.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import yaml

from jura_growth import cards, cloudflare, config, db, holidays, paths, schedule, suppression, timeutil, uat_stub
from jura_growth.agents.outreach import send, store

FOLDERS = ("JURA_GROWTH_DATA_DIR", "JURA_GROWTH_OUTPUTS_DIR", "JURA_PRD_DIR")
# Folders the seed writes to only when they are set, and then only inside the UAT folder.
OPTIONAL_FOLDERS = ("JURA_GROWTH_CONFIG_DIR",)
HISTORY_DAYS = 8  # S1: run history from eight days before the seeded day

# Datasets D2 and D3 (test strategy v3 §3), as uat.md S5 and S6 plant them.
RESEND_KEY = "re_uat_9Xq7Lm2Pz"
REPLY = "Please take us off your list"
PHONE = "+65 9123 4567"
NAMED_ADDRESS = "jane.tan@example.com.sg"


class Refused(RuntimeError):
    pass


# --- the seeded day (`--today`) -------------------------------------------------------------
#
# Dispatch stamps every decision with the real clock (ADR 0004 as amended 2026-10-26), so the
# seed dates its rows from the day the UAT runs: `--today`, by default today in SGT. Scenarios
# read it through `today()` and `previous_business_day()`, never a fixed date.

_day: date | None = None
_folder: Path | None = None  # the UAT folder being seeded
_options: dict = {}  # the scenario's own options, such as `--lead`


def option(name: str, flag: str | None = None):
    """A scenario's option, or Refused naming the flag that sets it."""
    if name not in _options:
        raise Refused(f"this scenario needs {flag or '--' + name}")
    return _options[name]


def today() -> date:
    """The day being seeded."""
    return _day if _day is not None else timeutil.today()


def previous_business_day(day: date | None = None) -> date:
    candidate = (day or today()) - timedelta(days=1)
    while not holidays.is_business_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def day_refusal(day: date) -> str | None:
    """Why `day` can't be the seeded day, or None."""
    if holidays.is_business_day(day):
        return None
    why = holidays.holiday(day) or "weekend"
    return f"{day.isoformat()} is not a business day ({why}): run the UAT on a business day"


# --- the refusal ----------------------------------------------------------------------------


def _temporary(folder: Path) -> bool:
    roots = {Path(tempfile.gettempdir()), Path("/tmp"), Path("/private/var/folders")}
    return any(root.exists() and paths.is_within(folder, root) for root in roots)


def refusal(folder: str | os.PathLike[str]) -> str | None:
    """Why seeding `folder` is refused, or None."""
    folder = Path(folder).resolve()
    if paths.is_within(folder, paths.JURA_ROOT) or not _temporary(folder):
        return f"{folder} is not a temporary folder: make one with `mktemp -d`, outside jurasolutions/"
    for variable in FOLDERS:
        value = os.environ.get(variable)
        if not value:
            return f"{variable} isn't set: point it inside {folder}"
        if not paths.is_within(value, folder):
            return f"{variable} ({value}) is outside {folder}"
    for variable in OPTIONAL_FOLDERS:
        value = os.environ.get(variable)
        if value and not paths.is_within(value, folder):
            return f"{variable} ({value}) is outside {folder}"
    return None


def _prepare_config() -> None:
    """A `JURA_GROWTH_CONFIG_DIR` inside the UAT folder starts as a copy of the repo's `config/`,
    which is only read, so every command in the window has its settings. The copy's outreach
    starts in shadow mode, with no legal review and no sending domain, whatever `config/scout.yaml`
    ships (live since 2026-10-31): only `outreach-live` (S3) turns live mode on, and then only
    towards the stub."""
    value = os.environ.get("JURA_GROWTH_CONFIG_DIR")
    if value and not (Path(value) / "settings.yaml").exists():
        shutil.copytree(paths.REPO_ROOT / "config", value, dirs_exist_ok=True)

        def shadow(scout: dict) -> None:
            scout.update(mode="shadow", legal_review_done=False, sending_domain=None)

        _rewrite_yaml(Path(value) / "scout.yaml", shadow)


# --- building blocks ------------------------------------------------------------------------


def at(day: date, clock: str) -> str:
    hour, minute = (int(part) for part in clock.split(":")[:2])
    second = int(clock.split(":")[2]) if clock.count(":") == 2 else 0
    return timeutil.stamp(datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=timeutil.SGT))


def run_row(conn, agent: str, job: str, started: str, *, minutes: float = 2, status: str = "ok", summary: str | None = None,
            error: str | None = None, cost: float | None = None) -> int:
    finished = timeutil.stamp(timeutil.parse(started) + timedelta(minutes=minutes))
    cursor = conn.execute(
        "INSERT INTO runs (agent, job, started_at, finished_at, status, summary, error, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (agent, job, started, finished, status, summary, error, cost),
    )
    return int(cursor.lastrowid or 0)


def event_row(conn, kind: str, ts: str, payload: dict, *, agent: str | None = None, run_id: int | None = None) -> None:
    conn.execute(
        "INSERT INTO events (run_id, ts, agent, level, kind, payload_json) VALUES (?, ?, ?, 'info', ?, ?)",
        (run_id, ts, agent, kind, json.dumps(payload)),
    )


def _runs_on(spec: dict, day: date) -> list[str]:
    """The SGT times `spec` has a slot on `day` (repeating slots excluded)."""
    shape = spec["schedule"]
    if "business_days_every" in shape:
        return []
    if schedule.business_days_only(shape) and not holidays.is_business_day(day):
        return []
    weekday = schedule.launchd_weekday(day)
    return [f"{h:02d}:{m:02d}" for when, h, m in schedule.sgt_slots(shape) if when is None or when == weekday]


# --- the base scenario ---------------------------------------------------------------------


def s1_history(conn) -> None:
    jobs = config.settings()["jobs"]
    day = today() - timedelta(days=HISTORY_DAYS)
    while day < today():
        for name, spec in jobs.items():
            for clock in _runs_on(spec, day):
                cost = 0.50 if spec["kind"] == "claude" else None
                run_row(conn, spec["agent"], name, at(day, clock), cost=cost, summary=f"OK: {name} on {day.isoformat()}")
        day += timedelta(days=1)
    # The previous business day: scout-send's quiet traces, with 10:00, 10:10 and 10:20 slept
    # through and a quiet run at 10:26.
    friday = previous_business_day()
    minute = 9 * 60 + 30
    while minute <= 16 * 60 + 30:
        clock = f"{minute // 60:02d}:{minute % 60:02d}"
        if clock not in ("10:00", "10:10", "10:20"):
            started = at(friday, clock + ":03")
            event_row(conn, "run.quiet", started, {"job": "scout-send", "started_at": started}, agent="outreach")
        minute += 10
    late = at(friday, "10:26:00")
    event_row(conn, "run.quiet", late, {"job": "scout-send", "started_at": late}, agent="outreach")


def s2_today(conn) -> None:
    run_row(conn, "app-factory", "app-factory", at(today(), "06:31"), minutes=6, cost=1.20,
            summary="OK: filed APP-014 PayNow QR for small shops")
    run_row(conn, "social", "social", at(today(), "07:00"), minutes=4.2, cost=0.41,
            summary="OK: drafted Facebook and Instagram for \"PayNow QR for small shops\"")


def _lead(conn, lead_id: int, company: str, domain: str, *, industry: str = "logistics", score: int = 70) -> None:
    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel, status,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, '[\"runs dispatch by hand\"]', 'email', 'queued', ?, ?)",
        (lead_id, company, company.removesuffix(" Pte Ltd"), domain, f"https://{domain}", industry, score,
         _found(), _found()),
    )


def _found() -> str:
    """When the seeded leads were found: the day before the previous business day, 09:00."""
    return at(previous_business_day() - timedelta(days=1), "09:00")


def _contact(conn, lead_id: int, email: str, kind: str, source: str) -> int:
    cursor = conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (lead_id, email, suppression.email_hash(email), source, kind, _found(), _found()),
    )
    return int(cursor.lastrowid or 0)


NAMES = ("Alder", "Birch", "Cedar", "Dove", "Elm", "Fern", "Grove", "Hazel", "Iris", "Juniper", "Kestrel", "Linden",
         "Maple", "Nutmeg", "Olive", "Pine", "Quill", "Rowan", "Sage", "Teak")
SUBJECT = "Quotes that write themselves"
TOOL = "quote-builder"  # live in the site registry, so a draft linking it passes the send-time brand gate


def draft(company: str) -> str:
    """A first email that passes the `email` brand channel as it stands, so an approved one sends."""
    return (
        f"I saw on the {company} site that each quote is still typed up by hand. We've made a free quote "
        f"builder that turns a job into a clean PDF quote: jurasolutions.sg/apps/{TOOL}\n\n"
        "It sits with our other small tools at jurasolutions.sg/apps. There's nothing to install, and what you "
        "enter stays in your browser.\n\n"
        "We're Jura Solutions, a small automation consultancy (jurasolutions.sg). If quotes eat into your "
        "evenings, I'd be glad to hear how they work today on a 30-minute call."
    )


def _queued(conn, lead_id: int, contact_id: int, queued_at: str, send_after: date, body: str) -> int:
    cursor = conn.execute(
        "INSERT INTO outreach_messages (lead_id, contact_id, kind, tool_slug, subject, draft_body, body_text, body_html,"
        " send_after, queued_at, status) VALUES (?, ?, 'first', ?, ?, ?, ?, ?, ?, ?, 'queued')",
        (lead_id, contact_id, TOOL, SUBJECT, body, body, f"<p>{body}</p>", send_after.isoformat(), queued_at),
    )
    return int(cursor.lastrowid or 0)


def s4_queued_emails(conn) -> None:
    _lead(conn, 233, "Example Pte Ltd", "example.com.sg", score=78)
    contact = _contact(conn, 233, "info@example.com.sg", "role", "https://example.com.sg/contact")
    previous = previous_business_day()
    _queued(conn, 233, contact, at(previous, "09:12"), previous, draft("Example"))
    for lead_id, name in zip(range(240, 255), NAMES):
        domain = f"lead{lead_id}.example.sg"
        # Word names: a figure in a company name fails the numbers rule at send time.
        _lead(conn, lead_id, f"{name} Freight Pte Ltd", domain)
        contact = _contact(conn, lead_id, f"hello@{domain}", "role", f"https://{domain}/contact")
        planted = f" (draft notes: key {RESEND_KEY})" if lead_id == 254 else ""  # S6
        _queued(conn, lead_id, contact, at(today(), "09:05"), today(), draft(f"{name} Freight") + planted)
    # Not "Tan Logistics": a company name holding the named recipient's surname reads as greeting
    # the person, and the `email` brand channel drops it (AC-M12.2).
    _lead(conn, 260, "Harbourline Logistics Pte Ltd", "harbourline.example.sg")
    contact = _contact(conn, 260, NAMED_ADDRESS, "named", "https://harbourline.example.sg/enquiries")
    _queued(conn, 260, contact, at(today(), "09:05"), today(), draft("Harbourline Logistics"))


def s5_s6_planted(conn) -> None:
    previous = previous_business_day()
    run_row(conn, "scout", "scout-research", at(previous, "09:00:30"), summary=f"OK: 3 leads (token {RESEND_KEY})")
    failed = run_row(conn, "outreach", "scout-sync", at(previous, "16:45:30"), status="failed",
                     error=f"ResendError: 401 for key {RESEND_KEY}")
    folder = paths.data_dir() / "transcripts" / today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "assistant", "text": f"Reply from lead 233: {REPLY}. Call {PHONE}."},
        {"type": "assistant", "text": f"Using RESEND_API_KEY_OUTREACH={RESEND_KEY}"},
    ]
    (folder / f"{failed}-scout-sync.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))


def s7_factory_prd(conn) -> None:
    folder = paths.prd_dir() / "pending" / "apps"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"prd-app-014-paynow-qr-{today().isoformat()}.md").write_text(
        "# APP-014 PayNow QR for small shops\n\n"
        "Pitch: a shop prints one PayNow QR per invoice, so payments match themselves.\n"
        "Tier: free tool. Lead types: retail, food and beverage.\n"
    )


def _group(conn, group_id: int, name: str, slug: str, *, joined: int, rules: str | None) -> None:
    now = at(today() - timedelta(days=HISTORY_DAYS), "07:30")
    url = f"https://www.facebook.com/groups/{slug}"
    conn.execute(
        "INSERT INTO community_groups (id, name, slug, url, url_key, promo_rules, fit, fit_reason, joined, rules_confirmed,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'good fit', 'owners asking about admin', ?, 0, ?, ?)",
        (group_id, name, slug, url, url.removeprefix("https://www."), rules, joined, now, now),
    )


def s8_groups(conn) -> None:
    """G4 and G7 under ids 4 and 7, so `community set 4` and `--group 4` mean G4."""
    _group(conn, 4, "G4 Singapore SME owners", "g4-sg-sme-owners", joined=1, rules="promo Saturdays only")
    _group(conn, 7, "G7 Logistics operators SG", "g7-logistics-sg", joined=0, rules=None)


def base(conn) -> None:
    for step in (s1_history, s2_today, s4_queued_emails, s5_s6_planted, s7_factory_prd, s8_groups):
        step(conn)


# --- the outreach scenarios (ticket 17) ----------------------------------------------------
#
# A4 and B6 run against these. None of them raises an approval request: requests come only from
# the outreach commands themselves (`send-due`, `requeue-shadow`), as they would live.

LIVE_SENDING_DOMAIN = "hello.jurasolutions.sg"  # only ever reaches the stub
WARM_UP_DAY = 3  # cap 5 (caps.OUTREACH_WARMUP)


def _rewrite_yaml(path: Path, change: Callable[[dict], None]) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    change(data)
    path.write_text("# Written by tests/uat/seed.py for the UAT folder only.\n"
                    + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def outreach_live(conn) -> list[str]:
    """S3: `outreach.mode: live` in `$UAT/config` with every live pre-condition met except the
    buttons switch (`approvals.discord_buttons: false`, which A4 turns on), warm-up day 3, and
    Resend and D1 pointed at the stub. Returns any pre-condition the window still has to supply."""
    folder = os.environ.get("JURA_GROWTH_CONFIG_DIR")
    if not folder:
        raise Refused("JURA_GROWTH_CONFIG_DIR isn't set: outreach-live writes live mode into $UAT/config, never config/")
    for variable, service in ((send.RESEND_BASE_ENV, "no email can reach Resend"),
                              (cloudflare.BASE_ENV, "no query can reach Cloudflare")):
        if not os.environ.get(variable):
            raise Refused(f"{variable} isn't set: start the stub (`uv run python -m tests.resend_stub`) and "
                          f"export {variable}=http://127.0.0.1:{8025}, so {service}")
        problem = uat_stub.url_problem(variable)
        if problem:
            raise Refused(problem)

    def live(scout: dict) -> None:
        scout.update(mode="live", legal_review_done=True, sending_domain=LIVE_SENDING_DOMAIN)

    def buttons_off(settings: dict) -> None:
        settings.setdefault("approvals", {})["discord_buttons"] = False

    _rewrite_yaml(Path(folder) / "scout.yaml", live)
    _rewrite_yaml(Path(folder) / "settings.yaml", buttons_off)
    inputs = os.environ.get("JURA_INPUTS_DIR")
    if inputs and _folder is not None and paths.is_within(inputs, _folder):  # never the real inputs/
        dnc = Path(inputs) / "do-not-contact.csv"
        dnc.parent.mkdir(parents=True, exist_ok=True)
        if not dnc.exists():
            dnc.write_text("company,domain,reason\n", encoding="utf-8")
    first_live_send = today() - timedelta(days=WARM_UP_DAY - 1)
    store.set_state(conn, "first_live_send_at", at(first_live_send, "10:00"))
    config.reset_caches()
    return [p for p in send.live_problems() if not p.startswith("approval buttons not set up")]


EDITED = "\n\nP.S. A short note added by hand after the first read."


def edit_draft(conn) -> None:
    """S9: change one lead's queued `draft_body`, as a hand edit would, so the next read or claim
    supersedes its request and raises one for the new text."""
    lead = option("lead")
    message = db.one(conn, "SELECT id, draft_body FROM outreach_messages WHERE lead_id = ? AND status = 'queued'", (lead,))
    if message is None:
        raise Refused(f"lead {lead} has no queued email to edit")
    conn.execute("UPDATE outreach_messages SET draft_body = ? WHERE id = ?", (message["draft_body"] + EDITED, message["id"]))


SHADOW_LEADS = range(300, 340)  # S10: 40 shadow-trial emails
SHADOW_TRADES = ("Aircon", "Renovation")


def shadow_trial(conn) -> None:
    """S10: 40 first emails shadow-sent over the business days before today, five a day, in the
    shape `requeue-shadow` reads: the message `shadow`, its lead `shadow_sent`."""
    if db.scalar(conn, "SELECT 1 FROM leads WHERE id = ?", (SHADOW_LEADS[0],)):
        raise Refused("shadow-trial is already seeded in this folder")
    day = today()
    for index, lead_id in enumerate(SHADOW_LEADS):
        if index % 5 == 0:
            day = previous_business_day(day)
        name = f"{NAMES[index % len(NAMES)]} {SHADOW_TRADES[index // len(NAMES)]}"
        domain = f"shadow{lead_id}.example.sg"
        _lead(conn, lead_id, f"{name} Pte Ltd", domain)
        contact = _contact(conn, lead_id, f"hello@{domain}", "role", f"https://{domain}/contact")
        message = _queued(conn, lead_id, contact, at(day, "09:05"), day, draft(name))
        sent = at(day, f"{10 + index % 5}:00")
        conn.execute("UPDATE outreach_messages SET status = 'shadow', mode = 'shadow', sent_at = ?, qa_json = '{}' WHERE id = ?",
                     (sent, message))
        conn.execute("UPDATE leads SET status = 'shadow_sent' WHERE id = ?", (lead_id,))


# --- the group-rules scenario (ticket 05) ---------------------------------------------------


def note_rules(conn) -> None:
    """S13: the group's rules as seen inside the group, with its `group-rules` request raised over
    them through the kind's own code (the same request again if one is already waiting)."""
    from jura_growth.agents.community import group_rules
    from jura_growth.agents.community import groups as groups_mod

    group = option("group", "--group <id>, such as --group 4 for G4")
    found = groups_mod.get(conn, group)
    if found is None:
        raise Refused(f"no group {group}: seed `base` first")
    if not (found["promo_rules"] or "").strip():
        raise Refused(f"group {group} has no rules recorded to confirm")
    group_rules.request(conn, group, reason="the rules as seen inside the group (UAT seed, as publish note-rules will record them)")


# --- the publish scenarios (BP-02a; uat.md Part C) -------------------------------------------
#
# They manage their own transactions (`own_transactions`): raising, deciding and claiming each
# commit on their own, as they do live.

UAT_PAGE_URL = "https://www.facebook.com/jura-uat-test-page"
SOCIAL_DRAFT = (
    "Chasing late invoices by hand? Your accounting software can send the first reminder for you.\n\n"
    "More small automations like this: https://jurasolutions.sg\n\n#SmallBusiness #Automation\n"
)


INSTAGRAM_DRAFT = (
    "Chasing late invoices by hand? Your accounting software can send the first reminder for you.\n\n"
    "Link in bio.\n\n#SmallBusiness #Automation\n"
)


def _browser_facebook(page_url: str = UAT_PAGE_URL, platform: str = "facebook") -> None:
    folder = os.environ.get("JURA_GROWTH_CONFIG_DIR")
    if not folder:
        raise Refused("JURA_GROWTH_CONFIG_DIR isn't set: the publish scenarios write browser mode into $UAT/config, never config/")

    def browser(social: dict) -> None:
        social["platforms"][platform].update(publish_mode="browser", page_url=page_url)

    _rewrite_yaml(Path(folder) / "social.yaml", browser)
    config.reset_caches()


def _png(width: int = 1200, height: int = 630) -> bytes:
    import struct
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")


def _facebook_item(conn, page_url: str = UAT_PAGE_URL, platform: str = "facebook"):
    """The seeded day's Facebook (or `platform`'s) draft, past the brand gate, with its item, request and card."""
    from jura_growth import cards
    from jura_growth.agents.publish import items

    _browser_facebook(page_url, platform)
    day = today()
    width, height = (1080, 1350) if platform == "instagram" else (1200, 630)
    image = paths.outputs_dir() / "social" / day.isoformat() / f"{platform}-{width}x{height}.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(_png(width, height))
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO social_posts (date, theme, platform, text, image_paths, qa_json, status, created_at)"
            " VALUES (?, 'automation-tip', ?, ?, ?, ?, 'draft', ?)",
            (day.isoformat(), platform, INSTAGRAM_DRAFT if platform == "instagram" else SOCIAL_DRAFT, json.dumps([str(image)]), json.dumps({"passed": True, "attempt": 1}),
             timeutil.stamp()),
        )
        made = items.create_social(conn, int(cursor.lastrowid or 0), run_id=None)
    if made.approval is None:
        raise Refused(f"no {platform} card could be raised: {made.why}")
    cards.sweep_safely(conn)
    return made


def _approve(conn, approval) -> None:
    """Approve through the only origin that decides, as Dispatch delivers it."""
    from jura_growth import approvals, cards
    from jura_growth.origin import Origin

    control = config.secret("CONTROL_DISCORD_USER_ID")
    answer = approvals.decide(conn, approval.id, "approve", actor=f"discord:{control}", origin=Origin.ssh(),
                              source_ref=None, args={})
    if answer.answer != "recorded":
        raise Refused(f"{approval.id} couldn't be approved: {answer.text}")
    cards.sweep_safely(conn)


def social_post(conn) -> None:
    """C1: one pending social-post card for Facebook."""
    _facebook_item(conn)


def social_approved(conn) -> None:
    """C2: the Facebook card, approved and not yet claimed."""
    _approve(conn, _facebook_item(conn).approval)


def claimed_not_closed(conn) -> None:
    """C2: a publish run claimed the Facebook item and ended without done or stopped, so
    `after_run` settled it as unknown, paused publish, and the run's alert says how to settle it."""
    from jura_growth import discord, log, runner
    from jura_growth.agents.publish import claim, job

    _approve(conn, _facebook_item(conn).approval)
    run_id = log.start_run(conn, "publish", "publish")
    handed = claim.next_item(conn, run_id=run_id)
    if handed.item is None:
        raise Refused("nothing could be claimed: " + "; ".join(handed.why) + " (seed this between 09:00 and 18:00)")
    outcome = job.after_run(conn, "publish", run_id, runner.Outcome("ok"))
    log.finish_run(conn, run_id, outcome.status, summary=outcome.summary, error=outcome.error)
    discord.alert(conn, f"`publish` failed: {outcome.error[:500]}", agent="publish")


# --- the community scenario (BP-02b; uat.md Part C, C3) ---------------------------------------

G4_POST = (
    "Most invoice chasing follows the same three steps: a polite reminder, a firmer one, then a call. "
    "If your accounting software sends the first two on a schedule, you only make the call. "
    "What does your team do when an invoice is a week late?\n\n"
    "We write about small automations like this at Jura Solutions."
)


def _community_browser() -> None:
    folder = os.environ.get("JURA_GROWTH_CONFIG_DIR")
    if not folder:
        raise Refused("JURA_GROWTH_CONFIG_DIR isn't set: the community scenario writes browser: true into $UAT/config, "
                      "never config/")

    def browser(community: dict) -> None:
        community["browser"] = True

    _rewrite_yaml(Path(folder) / "community.yaml", browser)
    config.reset_caches()


def community_plan(conn) -> None:
    """C3: G4 joined as the Jura Page, and a promotional post planned there for the seeded day,
    with its card. G4's rules ("promo Saturdays only") aren't confirmed yet."""
    from jura_growth.agents.publish import items

    if db.one(conn, "SELECT id FROM community_groups WHERE id = 4") is None:
        raise Refused("no group 4: seed `base` first")
    _community_browser()
    day = today()
    with db.transaction(conn):
        conn.execute("UPDATE community_groups SET joined_as_set = 'page', joined = 1 WHERE id = 4")
        conn.execute(
            "INSERT INTO community_posts (group_id, week, planned_day, kind, text, qa_json, status, created_at)"
            " VALUES (4, ?, ?, 'post', ?, ?, 'planned', ?)",
            (timeutil.iso_week(day), day.isoformat(), G4_POST, json.dumps({"brand": "pass", "attempt": 1}), timeutil.stamp()),
        )
    made = items.raise_for_plan(conn, timeutil.iso_week(day), run_id=None)
    if not made or made[0].approval is None:
        raise Refused("no community-post card could be raised: " + "; ".join(m.why for m in made))
    cards.sweep_safely(conn)


# --- the rehearsal scenarios (BP-07; uat.md Part R, R1 to R6) -------------------------------------
#
# They need the fixture platform on: `JURA_GROWTH_PUBLISH_FIXTURE_URL` set to the local fixture
# site, which its guard accepts (`jura_growth/agents/publish/fixture.py`). The item's target is the
# fixture page `--page` names, so each step starts from its own page.

FIXTURE_SITE = paths.REPO_ROOT / "tests" / "fixtures" / "publish-site"
FIXTURE_GROUP = 9  # G9, the rehearsal's group; the base scenario's groups are 4 and 7


def _fixture_page(default: str) -> str:
    """The fixture site's address for `--page`, or Refused."""
    from jura_growth.agents.publish import fixture

    try:
        site = fixture.active()
    except fixture.FixtureRefused as refused:
        raise Refused(str(refused)) from None
    if site is None:
        raise Refused(f"{fixture.ENV} isn't set: serve tests/fixtures/publish-site on loopback and export "
                      f"{fixture.ENV}=http://publish-fixture.localhost:8765")
    page = _options.get("page") or default
    pages = sorted(p.name for p in FIXTURE_SITE.glob("*.html") if p.name != "index.html")
    if page not in pages:
        raise Refused(f"--page must name a fixture page ({', '.join(pages)}), not {page!r}")
    return f"{site.base}/{page}"


def fixture_post(conn) -> None:
    """R1 to R4 and R6: an approved Facebook item whose target is the fixture page `--page` names
    (default `page.html`, the composer)."""
    _approve(conn, _facebook_item(conn, _fixture_page("page.html")).approval)


def fixture_post_instagram(conn) -> None:
    """R1, R2 and R6 for Instagram (BP-04): the same as `fixture-post`, for an Instagram item."""
    _approve(conn, _facebook_item(conn, _fixture_page("instagram.html"), "instagram").approval)


def fixture_join(conn) -> None:
    """R5: an approved join for G9, a good-fit group not yet joined, whose address is the fixture
    group the join page `--page` names is served at (default `join.html`, the membership
    questions, at `/groups/join/`)."""
    from jura_growth.agents.publish import items

    page = _fixture_page("join.html")
    # A group's address is one group's own address, /groups/<one segment>/ (code review 06, S7): the
    # fixture site serves each join page there as well.
    stem = page.rsplit("/", 1)[1].removesuffix(".html")
    if not (FIXTURE_SITE / "groups" / stem / "index.html").is_file():
        raise Refused(f"--page {stem}.html isn't a join page: use join.html or profile-only-join.html")
    url = f"{page.rsplit('/', 1)[0]}/groups/{stem}/"
    if db.one(conn, "SELECT id FROM community_groups WHERE id = ?", (FIXTURE_GROUP,)) is not None:
        raise Refused(f"group {FIXTURE_GROUP} is already seeded: start again from a fresh `mktemp -d`")
    _community_browser()
    now = timeutil.stamp()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO community_groups (id, channel, name, slug, url, url_key, fit, fit_reason, joined, rules_confirmed,"
            " created_at, updated_at) VALUES (?, 'facebook', 'G9 Rehearsal group', 'g9-rehearsal', ?, ?, 'good fit',"
            " 'the rehearsal group', 0, 0, ?, ?)",
            (FIXTURE_GROUP, url, url.split("://", 1)[1], now, now),
        )
        made = items.create_join(conn, FIXTURE_GROUP, run_id=None)
    if made.approval is None:
        raise Refused(f"no join card could be raised: {made.why}")
    cards.sweep_safely(conn)
    _approve(conn, made.approval)


def fixture_reply(conn) -> None:
    """An approved reply to the fixture's thread, as triage and Ting Yu would leave it."""
    from jura_growth.agents.inbox import social, store

    target = _fixture_page("inbox-thread.html").rsplit("/", 1)[0] + "/direct/t/1234567/"
    with db.transaction(conn):
        item_id = store.record(conn, store.Reaction(
            source="instagram-dm", key=store.text_key("fixture-reply"), conversation=store.text_key("fixture-reply"), sender_name="Priya Nair",
            sender_domain="instagram.com", text="Do you work with clinics?", target=target, thread={"surface": "instagram-primary", "occurrence": 1},
        )).item_id
        store.update_triage(conn, item_id, state=store.TRIAGED, note="", kind="question", priority="normal", language="English",
                            draft="Thanks for asking. We work with small teams on invoices, and Levi can tell you more.", promised=False)
    raised = social.raise_due(conn)
    if not raised:
        raise Refused(f"no card was raised: {store.get(conn, item_id)['note'] or social.switched_off(conn)}")
    _approve(conn, raised[0])


for _scenario in (social_post, social_approved, claimed_not_closed, community_plan, fixture_post, fixture_post_instagram,
                  fixture_join, fixture_reply):
    _scenario.own_transactions = True  # type: ignore[attr-defined]


SCENARIOS: dict[str, Callable] = {
    "base": base,
    "outreach-live": outreach_live,
    "edit-draft": edit_draft,
    "shadow-trial": shadow_trial,
    "note-rules": note_rules,
    "social-post": social_post,
    "social-approved": social_approved,
    "claimed-not-closed": claimed_not_closed,
    "community-plan": community_plan,
    "fixture-post": fixture_post,
    "fixture-post-instagram": fixture_post_instagram,
    "fixture-join": fixture_join,
    "fixture-reply": fixture_reply,
}


# --- seeding --------------------------------------------------------------------------------


def seed(folder: str | os.PathLike[str], scenario: str = "base", *, today: date | None = None, **options) -> list[str]:
    """Seed `scenario` into `folder`, dating it from `today` (default: today in SGT). A scenario
    reads its own `options` (`--lead`) through `option()`. Returns notes for Ting Yu: anything
    the window must still supply before the scenario's steps."""
    global _day, _folder, _options
    problem = refusal(folder)
    if problem:
        raise Refused(problem)
    build = SCENARIOS.get(scenario)
    if build is None:
        raise Refused(f"no scenario {scenario!r}; known: {', '.join(SCENARIOS)}")
    _prepare_config()
    config.reset_caches()
    day = today or timeutil.today()
    problem = day_refusal(day)
    if problem:
        raise Refused(problem)
    _day, _folder, _options = day, Path(folder).resolve(), {k: v for k, v in options.items() if v is not None}
    try:
        with db.session() as conn:
            if scenario == "base" and db.scalar(conn, "SELECT count(*) FROM runs"):
                raise Refused(f"{folder} is already seeded: start again from a fresh `mktemp -d`")
            if getattr(build, "own_transactions", False):
                return list(build(conn) or [])
            with db.transaction(conn):
                notes = list(build(conn) or [])
            cards.sweep_safely(conn)  # any request a scenario raised posts its card (A12)
            return notes
    finally:
        _day, _folder, _options = None, None, {}


def _day_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a date (YYYY-MM-DD)") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed uat.md's scenarios into a temporary folder.")
    parser.add_argument("folder")
    parser.add_argument("--scenario", default="base")
    parser.add_argument("--today", type=_day_argument, help="the day to date the rows from (default: today in SGT)")
    parser.add_argument("--lead", type=int, help="edit-draft: the lead whose queued draft to change")
    parser.add_argument("--group", type=int, help="note-rules: the group whose rules to raise, such as 4 for G4")
    parser.add_argument("--page", help="fixture-post, fixture-join: the fixture page the item targets, such as login.html")
    options = parser.parse_args(argv)
    try:
        notes = seed(options.folder, options.scenario, today=options.today, lead=options.lead, group=options.group,
                     page=options.page)
    except Refused as refused:
        print(f"refused: {refused}")
        return 2
    print(f"seeded {options.scenario} into {paths.data_dir()}")
    for note in notes:
        print(f"still needed: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
