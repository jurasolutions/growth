"""The UAT harness for `.scratch/mission-control/uat.md` Part A (ticket 04b; X13).

Seeds the Part A data into a temporary folder, for Ting Yu to run the script against a test
Discord server. From the repo root, in the Part A window (`uat.md`, "The window for Parts A and C"):

    uv run python -m tests.uat.seed "$UAT" [--scenario base]

It refuses unless `$UAT` is a temporary folder (made with `mktemp -d`) outside `jurasolutions/`, and
`JURA_GROWTH_DATA_DIR`, `JURA_GROWTH_OUTPUTS_DIR` and `JURA_PRD_DIR` all sit inside it. So it can
never write to the live `data/growth/`, `outputs/growth/` or PRD folders. It also refuses a folder
it has already seeded.

The `base` scenario holds what today's schema can: S1 (run history from Mon 2 Nov, Deepavali's
observed Monday without business-day runs, and the 6 Nov scout-send traces), S2 (today's
app-factory and social runs), S4 (the queued emails for leads 233, 240 to 254 and 260), S5 and S6
(the planted reply, phone number and Resend key), S7 (APP-014's PRD) and S8 (groups G4 and G7).
The approval requests over them, and S3's live-mode config, are raised by the kinds' own tickets
(06 for `outreach-email`, 10 for `app-build`, 05 for `group-rules`), each adding to `SCENARIOS`.
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

from jura_growth import config, db, holidays, paths, schedule, suppression, timeutil
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
    which is only read, so every command in the window has its settings."""
    value = os.environ.get("JURA_GROWTH_CONFIG_DIR")
    if value and not (Path(value) / "settings.yaml").exists():
        shutil.copytree(paths.REPO_ROOT / "config", value, dirs_exist_ok=True)


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
            summary="OK: drafted LinkedIn, Facebook and Instagram for \"PayNow QR for small shops\"")


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


SUBJECT = "Quotes that write themselves"
TOOL = "quote-builder"  # live in the site registry, so a draft linking it passes the send-time brand gate


def draft(company: str) -> str:
    """A first email that passes the `email` brand channel as it stands, so an approved one sends."""
    return (
        f"I saw on the {company} site that each quote is still typed up by hand. We've made a free quote "
        f"builder that turns a job into a clean PDF quote: jurasolutions.sg/apps/{TOOL}\n\n"
        "It sits with our other small tools at jurasolutions.sg/apps. There's nothing to install, and what you "
        "enter stays in your browser.\n\n"
        "If quotes eat into your evenings, reply and tell me how they work today. That's the kind of work we "
        "help Singapore teams automate."
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
    for lead_id in range(240, 255):
        domain = f"lead{lead_id}.example.sg"
        _lead(conn, lead_id, f"Lead {lead_id} Pte Ltd", domain)
        contact = _contact(conn, lead_id, f"hello@{domain}", "role", f"https://{domain}/contact")
        planted = f" (draft notes: key {RESEND_KEY})" if lead_id == 254 else ""  # S6
        _queued(conn, lead_id, contact, at(today(), "09:05"), today(), draft(f"Lead {lead_id}") + planted)
    _lead(conn, 260, "Tan Logistics Pte Ltd", "tanlogistics.example.sg")
    contact = _contact(conn, 260, NAMED_ADDRESS, "named", "https://tanlogistics.example.sg/enquiries")
    _queued(conn, 260, contact, at(today(), "09:05"), today(), draft("Tan Logistics"))


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


def _group(conn, name: str, slug: str, *, joined: int, rules: str | None) -> None:
    now = at(today() - timedelta(days=HISTORY_DAYS), "07:30")
    url = f"https://www.facebook.com/groups/{slug}"
    conn.execute(
        "INSERT INTO community_groups (name, slug, url, url_key, promo_rules, fit, fit_reason, joined, rules_confirmed,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'good fit', 'owners asking about admin', ?, 0, ?, ?)",
        (name, slug, url, url.removeprefix("https://www."), rules, joined, now, now),
    )


def s8_groups(conn) -> None:
    _group(conn, "G4 Singapore SME owners", "g4-sg-sme-owners", joined=1, rules="promo Saturdays only")
    _group(conn, "G7 Logistics operators SG", "g7-logistics-sg", joined=0, rules=None)


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
    Resend pointed at the stub. Returns any pre-condition the window still has to supply."""
    folder = os.environ.get("JURA_GROWTH_CONFIG_DIR")
    if not folder:
        raise Refused("JURA_GROWTH_CONFIG_DIR isn't set: outreach-live writes live mode into $UAT/config, never config/")
    if not os.environ.get(send.RESEND_BASE_ENV):
        raise Refused(f"{send.RESEND_BASE_ENV} isn't set: start the stub (`uv run python -m tests.resend_stub`) and "
                      f"export {send.RESEND_BASE_ENV}=http://127.0.0.1:{8025}, so no email can reach Resend")
    problem = send.resend_stub_problem()
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


SCENARIOS: dict[str, Callable] = {"base": base, "outreach-live": outreach_live}


# --- seeding --------------------------------------------------------------------------------


def seed(folder: str | os.PathLike[str], scenario: str = "base", *, today: date | None = None) -> list[str]:
    """Seed `scenario` into `folder`, dating it from `today` (default: today in SGT). Returns
    notes for Ting Yu: anything the window must still supply before the scenario's steps."""
    global _day, _folder
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
    _day, _folder = day, Path(folder).resolve()
    try:
        with db.session() as conn:
            if scenario == "base" and db.scalar(conn, "SELECT count(*) FROM runs"):
                raise Refused(f"{folder} is already seeded: start again from a fresh `mktemp -d`")
            with db.transaction(conn):
                return list(build(conn) or [])
    finally:
        _day, _folder = None, None


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
    options = parser.parse_args(argv)
    try:
        notes = seed(options.folder, options.scenario, today=options.today)
    except Refused as refused:
        print(f"refused: {refused}")
        return 2
    print(f"seeded {options.scenario} into {paths.data_dir()}")
    for note in notes:
        print(f"still needed: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
