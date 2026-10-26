"""Sending (`jura-growth outreach send-due`, every 10 minutes, PRD §5.3).

Every rule is code. In order:

 1. Pause flags (outreach, all, the PAUSE file).
 2. The window: 09:30–16:30 SGT on business days. Outside it nothing
    happens; whatever is still queued rolls to the next business day.
 3. Mode. `shadow` (the default) records and posts to #outreach-sent marked
    SHADOW, and never calls Resend. `live` refuses to start unless every
    pre-condition in `live_problems()` holds.
 4. Caps from caps.py (config may lower them): per day, rolling 30 and 365
    days, the warm-up (5 a day in week 1, 10 in week 2, then 20), at most one
    email per run, and in live mode no send within 10 minutes of the last
    live send, however often `send-due` is called.
 5. Random spacing: this slot sends with probability remaining quota ÷
    remaining slots, so the day's emails spread across the window.
 6. Suppression synced from D1 at the start of the send. A failed sync pauses
    outreach; no D1 is a logged warning in shadow mode and a refusal in live.
 7. Per message: suppression (address and domain), the do-not-contact list,
    `contacted_domains`, the per-company rule, and the brand gate again on the
    exact text being sent.
 8. Live only: the claim (mission control §5.8, ADR 0003). Live mode considers
    only emails Ting Yu approved in #approvals (`due(approved_only=True)`,
    which also feeds the spacing in step 5). After every check above, one
    `BEGIN IMMEDIATE` transaction claims the email's `outreach-email`
    approval and counts the attempt; then Resend is called under
    `Idempotency-Key: jura-outreach-<id>`; then the email is marked sent. A
    claimed email that Resend errored on, or that the process lost before the
    mark, is retried under the same key with no second claim.

In live mode each run also tops up the approval requests (`approval.raise_due`)
and posts or edits their cards when it ends. Live mode waits for
`approvals.discord_buttons: true` (`approval_gate_problem`). Before rolling back
past the mission-control outreach gate, set `mode: shadow` in config/scout.yaml: an older
`send.py` has no gate.
"""

from __future__ import annotations

import os
import random
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import formataddr
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from jura_growth import approval_settings, approvals, caps, cloudflare, config, db, discord, holidays, locks, log, pause, paths, timeutil
from jura_growth.agents.outreach import approval, compose, queue, replies, store, sync
from jura_growth.agents.scout import contact as contact_rules
from jura_growth.agents.scout import dnc, registry, settings

RESEND_URL = "https://api.resend.com/emails"
# The UAT harness only (uat.md Part A): point Resend at the local stub,
# `uv run python -m tests.resend_stub`. Refused unless it is a loopback http
# URL and the data folder is a temporary one, so a real run can never send
# through it or be fooled into thinking it sent.
RESEND_BASE_ENV = "JURA_GROWTH_RESEND_BASE_URL"
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


class ResendStubRefused(RuntimeError):
    pass


@dataclass
class SendResult:
    summary: str | None  # for the run log; None when nothing happened
    note: str  # what to print


def resend_client() -> httpx.Client:
    """The client used for Resend (tests replace it)."""
    return httpx.Client(timeout=30)


def chance() -> float:
    """A number in [0, 1) for random spacing (tests replace it)."""
    return random.random()


# --- live mode pre-conditions ----------------------------------------------


def sending_domain() -> str:
    return str(settings.get().get("sending_domain") or "").strip().lower()


def from_address() -> str:
    local = str(settings.get().get("from_local_part") or "tingyu").strip()
    return formataddr((settings.SENDER_NAME, f"{local}@{sending_domain()}"))


def _temporary(folder: Path) -> bool:
    roots = {Path(tempfile.gettempdir()), Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders")}
    return any(root.exists() and paths.is_within(folder, root.resolve()) for root in roots)


def temporary_data_problem() -> str | None:
    """Why the data folder isn't a temporary one the UAT stub may serve, or None."""
    value = os.environ.get("JURA_GROWTH_DATA_DIR")
    if not value:
        return "JURA_GROWTH_DATA_DIR isn't set: point it at a folder made with `mktemp -d`"
    folder = Path(value).resolve()
    if paths.is_within(folder, paths.JURA_ROOT) or not _temporary(folder):
        return f"the data folder {folder} is not a temporary folder: make one with `mktemp -d`, outside jurasolutions/"
    return None


def resend_stub_problem() -> str | None:
    """Why `JURA_GROWTH_RESEND_BASE_URL` may not be used, or None (also None when unset)."""
    base = os.environ.get(RESEND_BASE_ENV)
    if not base:
        return None
    parts = urlsplit(base)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK:
        return f"{RESEND_BASE_ENV} must point at the local UAT stub (http://127.0.0.1:<port>), not {base}"
    problem = temporary_data_problem()
    return f"{RESEND_BASE_ENV} is for the UAT stub only, and {problem}" if problem else None


def resend_url() -> str:
    """Where emails are sent: Resend, or the UAT stub when that is allowed."""
    base = os.environ.get(RESEND_BASE_ENV)
    if not base:
        return RESEND_URL
    problem = resend_stub_problem()
    if problem:
        raise ResendStubRefused(problem)
    return base.rstrip("/") + "/emails"


def approval_gate_problem() -> str | None:
    """Why the approval gate stops live sending, or None (MC §5.8, AC-M8.11).

    Every live email needs an `outreach-email` approval claimed first, and
    approvals come only from the Approve and Skip buttons in #approvals,
    through Dispatch. So live sending waits until Ting Yu has checked the
    buttons work and set `approvals.discord_buttons: true` (ticket 15). The
    switch is read here only; nothing in the engine sets it.
    """
    if approval_settings.switch("discord_buttons"):
        return None
    return (
        "approval buttons not set up: every live email needs Ting Yu's approval from #approvals first. "
        "Set approvals.discord_buttons: true in config/settings.yaml only after checking the Approve and "
        "Skip buttons work (mission-control ticket 15)"
    )


def live_problems() -> list[str]:
    """Every reason live sending may not start. Empty means ready."""
    cfg = settings.get()
    problems = []
    gate = approval_gate_problem()
    if gate:
        problems.append(gate)
    mode = settings.mode()
    if mode != "live":
        problems.append(f"mode is {mode!r} in config/scout.yaml (live sending needs `mode: live`)")
    if cfg.get("legal_review_done") is not True:
        problems.append(
            "legal_review_done is not true in config/scout.yaml: get a Singapore lawyer's view on the Spam "
            "Control Act's address-harvesting provision first (PRD open question 1)"
        )
    domain = sending_domain()
    if not domain:
        problems.append(
            "sending_domain is not set in config/scout.yaml: choose jurasolutions.sg or a subdomain such as "
            "hello.jurasolutions.sg and verify it in Resend (PRD open question 2)"
        )
    elif not (domain == settings.SITE or domain.endswith("." + settings.SITE)):
        problems.append(f"sending_domain {domain!r} is not jurasolutions.sg or a subdomain of it")
    if not config.secret("RESEND_API_KEY_OUTREACH"):
        problems.append("RESEND_API_KEY_OUTREACH is not set in .env (a sending-only Resend key)")
    if not config.secret("UNSUBSCRIBE_SECRET"):
        problems.append("UNSUBSCRIBE_SECRET is not set in .env (the same value as the website's, so unsubscribe links verify)")
    if not dnc.exists():
        problems.append(f"{dnc.path()} does not exist (create it, even with only a header row)")
    if not cloudflare.configured():
        problems.append("D1 is not configured (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, D1_DATABASE_ID), so suppression can't sync")
    stub = resend_stub_problem()
    if stub:
        problems.append(stub)
    return problems


def _once_today(conn: sqlite3.Connection, kind: str, payload: dict, alert_text: str | None = None) -> bool:
    """Log `kind` and optionally alert, at most once per SGT day. True the first time."""
    already = db.one(
        conn, "SELECT 1 FROM events WHERE kind = ? AND substr(ts, 1, 10) = ?", (kind, timeutil.today_str())
    )
    if already:
        return False
    log.event(conn, kind, payload, level="warning", agent=store.AGENT)
    if alert_text:
        discord.alert(conn, alert_text, agent=store.AGENT)
    return True


def _refuse(conn: sqlite3.Connection, problems: list[str]) -> SendResult:
    text = "live sending refused:\n- " + "\n- ".join(problems)
    first = _once_today(conn, "outreach.live_refused", {"problems": problems}, text.capitalize())
    return SendResult("live sending refused: " + "; ".join(problems) if first else None, text)


# --- window, caps, spacing -------------------------------------------------


def outside_window(moment: datetime) -> str | None:
    day = moment.date()
    if not holidays.is_business_day(day):
        name = holidays.holiday(day)
        return f"not a business day ({name or 'weekend'})"
    (start_h, start_m), (end_h, end_m) = settings.window()
    minute = moment.hour * 60 + moment.minute
    if minute < start_h * 60 + start_m:
        return f"before the send window ({start_h:02d}:{start_m:02d})"
    if minute > end_h * 60 + end_m:
        return f"after the send window ({end_h:02d}:{end_m:02d}); queued email rolls to the next business day"
    return None


def slot_minutes() -> int:
    try:
        spec = config.settings()["jobs"]["scout-send"]["schedule"]["business_days_every"]
        return max(1, int(spec.get("minutes", 10)))
    except (KeyError, TypeError):
        return 10


def slots_left(moment: datetime) -> int:
    """Send slots from now to the end of the window, this one included."""
    (_, _), (end_h, end_m) = settings.window()
    minute = moment.hour * 60 + moment.minute
    return max(1, (end_h * 60 + end_m - minute) // slot_minutes() + 1)


def _count(conn: sqlite3.Connection, mode: str, since: datetime | None = None, day: str | None = None) -> int:
    sql = "SELECT count(*) FROM outreach_messages WHERE mode = ? AND sent_at IS NOT NULL"
    params: list = [mode]
    if since is not None:
        sql += " AND sent_at >= ?"
        params.append(timeutil.stamp(since))
    if day is not None:
        sql += " AND substr(sent_at, 1, 10) = ?"
        params.append(day)
    return db.scalar(conn, sql, tuple(params)) or 0


def counts(conn: sqlite3.Connection, mode: str) -> dict[str, int]:
    now = timeutil.now_sgt()
    return {
        "today": _count(conn, mode, day=timeutil.today_str()),
        "last_30_days": _count(conn, mode, since=now - timedelta(days=30)),
        "last_365_days": _count(conn, mode, since=now - timedelta(days=365)),
    }


def minutes_since_last_live_send(conn: sqlite3.Connection, moment: datetime) -> int | None:
    """Whole clock minutes from the last live send to `moment`, or None if
    nothing has gone out live yet."""
    last = db.scalar(conn, "SELECT max(sent_at) FROM outreach_messages WHERE mode = 'live' AND sent_at IS NOT NULL")
    if not last:
        return None
    then = timeutil.parse(last).astimezone(timeutil.SGT).replace(second=0, microsecond=0)
    now = moment.astimezone(timeutil.SGT).replace(second=0, microsecond=0)
    return int((now - then).total_seconds() // 60)


def first_send_day(conn: sqlite3.Connection, mode: str) -> date | None:
    """The day the warm-up counts from. In live mode `send.warmup_start` may
    only delay it: the later of that date and the first live send wins, and a
    first live send that hasn't happened yet counts as today."""
    value = store.get_state(conn, f"first_{mode}_send_at")
    recorded = timeutil.parse(value).date() if value else None
    configured = settings.get()["send"].get("warmup_start")
    if mode != "live" or not configured:
        return recorded
    start = configured if isinstance(configured, date) else date.fromisoformat(str(configured))
    return max(start, recorded or timeutil.today())


def daily_cap(conn: sqlite3.Connection, mode: str) -> tuple[int, str]:
    first = first_send_day(conn, mode)
    days = (timeutil.today() - first).days if first else None
    if days is not None and days < 0:
        days = None
    warm = caps.warmup_cap(days)
    cap = min(settings.per_day(), warm)
    return cap, f"warm-up day {1 if days is None else days + 1}, {warm} a day; daily cap {cap}"


def quota(conn: sqlite3.Connection, mode: str) -> tuple[int, str]:
    """Emails still allowed today, and which limit binds."""
    sent = counts(conn, mode)
    cap, note = daily_cap(conn, mode)
    limits = [
        (cap - sent["today"], f"daily cap ({note})"),
        (settings.rolling_30() - sent["last_30_days"], f"rolling 30-day cap of {settings.rolling_30()}"),
        (settings.rolling_365() - sent["last_365_days"], f"rolling 365-day cap of {settings.rolling_365()}"),
    ]
    left, why = min(limits, key=lambda item: item[0])
    return max(0, left), why


def due(conn: sqlite3.Connection, *, approved_only: bool = False) -> list[dict]:
    """Queued emails due today. With `approved_only` (live mode), only those
    Ting Yu approved: unclaimed, or claimed by an attempt that is retried
    under the same idempotency key. That list also feeds the spacing
    probability, so spacing spreads only what can actually go out."""
    sql = "SELECT * FROM outreach_messages WHERE status = 'queued' AND send_after <= ?"
    if approved_only:
        sql += (
            " AND EXISTS (SELECT 1 FROM approvals a WHERE a.kind = ? AND a.status = 'approved'"
            " AND a.subject = 'outreach_message:' || outreach_messages.id)"
        )
    params = (timeutil.today_str(), approval.KIND) if approved_only else (timeutil.today_str(),)
    return db.rows(conn, sql + " ORDER BY send_after, id", params)


# --- the run ---------------------------------------------------------------


SEND_LOCK = "outreach-send"


def send_due(conn: sqlite3.Connection, *, client: httpx.Client | None = None) -> SendResult:
    """One send run. The whole run, from the cap and gap checks to the Resend
    call and the record of the send, holds an exclusive lock, so a second
    `send-due` started meanwhile (by hand, or by another process) skips instead
    of sending past the gap or the daily cap."""
    with locks.held(SEND_LOCK) as acquired:
        if not acquired:
            return SendResult(None, "skipped: another send-due run is still going")
        result = _send_due(conn, client)
        if outside_window(timeutil.now_sgt()) is None:
            # Live mode tops the requests up to today's room (A14): after a
            # send, a skip, or a decision since the last slot.
            approval.raise_due(conn)
    approval.post_cards(conn)
    return result


def _send_due(conn: sqlite3.Connection, client: httpx.Client | None) -> SendResult:
    moment = timeutil.now_sgt()
    reason = pause.is_paused(conn, store.AGENT)
    if reason:
        return SendResult(None, f"outreach is paused: {reason}")
    reason = outside_window(moment)
    if reason:
        return SendResult(None, f"nothing to do: {reason}")

    mode = settings.mode()
    if mode not in ("shadow", "live"):
        return _refuse(conn, [f"mode must be shadow or live, not {mode!r}"])
    if mode == "live":
        problems = live_problems()
        if problems:
            return _refuse(conn, problems)

    waiting = due(conn, approved_only=mode == "live")
    if not waiting:
        return SendResult(None, _nothing_waiting(conn, mode))
    left, binding = quota(conn, mode)
    if left <= 0:
        return SendResult(None, f"nothing more today: {binding} reached")
    if settings.per_run() <= 0:
        return SendResult(None, "per_run is 0 in config/scout.yaml")
    if mode == "live":
        gap = minutes_since_last_live_send(conn, moment)
        floor = caps.OUTREACH_MINUTES_BETWEEN_LIVE_SENDS
        if gap is not None and gap < floor:
            return SendResult(
                None,
                f"spacing: the last live send was {gap} minute{'s' if gap != 1 else ''} ago; live sends are at "
                f"least {floor} minutes apart",
            )

    probability = min(1.0, min(left, len(waiting)) / slots_left(moment))
    if chance() >= probability:
        return SendResult(None, f"spacing: not this slot ({probability:.0%} chance; {left} left today, {slots_left(moment)} slots)")

    tools, problem = registry.load()
    if not tools:
        _once_today(conn, "outreach.no_registry", {"problem": problem}, f"Outreach can't send: {problem}.")
        return SendResult(None, f"not sending: {problem}")

    notes = []
    d1 = sync.sync_suppression(conn)
    if not d1.configured:
        if mode == "live":
            return _refuse(conn, ["D1 is not configured, so suppression can't sync"])
        notes.append("suppression not synced from D1 (not configured; shadow mode carries on)")
        _once_today(conn, "outreach.d1_missing", {"mode": mode})
    elif not d1.ok:
        return SendResult(f"suppression sync failed; outreach paused ({d1.error})", "suppression sync failed; outreach paused")
    if pause.is_paused(conn, store.AGENT):
        text = "outreach paused after the suppression sync: " + "; ".join(d1.paused)
        return SendResult(text, text)

    skipped = []
    for message in due(conn, approved_only=mode == "live"):
        try:
            lead, row = queue.recipient(conn, message["lead_id"])
        except queue.QueueError as error:
            conn.execute("UPDATE outreach_messages SET status = 'skipped', error = ? WHERE id = ?", (str(error)[:500], message["id"]))
            skipped.append(f"message {message['id']}: {error}")
            continue
        found = queue.blockers(conn, lead, row, message["kind"])
        if message["kind"] == "follow_up":
            found += _follow_up_send_problems(conn, lead["id"])
        if found:
            _skip(conn, message, lead, found)
            skipped.append(f"message {message['id']} ({lead['domain']}): {store.mask(found[0])}")
            continue
        if db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message["id"],)) != "queued":
            continue  # cancelled meanwhile (a reply or an unsubscribe)
        try:
            result = _send_one(conn, message, lead, row, mode, client)
        except _NotClaimed as refused:
            skipped.append(store.mask(str(refused)))
            continue  # the next approved email may still go
        summary = "; ".join([result] + notes + (["skipped " + "; ".join(skipped)] if skipped else []))
        return SendResult(summary, summary)
    if skipped:
        text = "skipped " + "; ".join(skipped)
        return SendResult(text, text)
    return SendResult(None, "nothing sendable")


def _nothing_waiting(conn: sqlite3.Connection, mode: str) -> str:
    if mode != "live":
        return "nothing queued"
    pending = approval.pending_requests(conn)
    unasked = len(approval.without_request(conn))
    if not pending and not unasked:
        return "nothing queued"
    return (f"nothing approved to send: {pending} waiting for a decision, "
            f"{unasked} waiting for a request slot")


def _follow_up_send_problems(conn: sqlite3.Connection, lead_id: int) -> list[str]:
    if not sync.follow_ups_on():
        return ["follow-ups need reply detection and follow_ups.enabled"]
    try:
        replies.check(conn)
    except replies.RepliesError as error:
        return [f"reply check before the follow-up failed ({error}); trying again next slot"]
    lead = db.one(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,))
    if lead["status"] in store.FINAL_LEAD_STATUSES:
        return [f"lead {lead_id} is {lead['status']}"]
    first = db.one(
        conn, "SELECT status FROM outreach_messages WHERE lead_id = ? AND kind = 'first' AND mode = 'live' AND sent_at IS NOT NULL", (lead_id,)
    )
    if not first or first["status"] != "sent":
        return [f"lead {lead_id}'s first email was not delivered live"]
    return []


def _skip(conn: sqlite3.Connection, message: dict, lead: dict, found: list[str]) -> None:
    temporary = any("trying again" in f for f in found)
    if temporary:
        return
    conn.execute(
        "UPDATE outreach_messages SET status = 'skipped', error = ? WHERE id = ? AND status = 'queued'",
        ("; ".join(found)[:500], message["id"]),
    )
    joined = " ".join(found)
    if "suppressed" in joined:
        store.set_lead_status(conn, [lead["id"]], "suppressed")
    elif "do-not-contact" in joined:
        store.set_lead_status(conn, [lead["id"]], "do_not_contact")
    log.event(conn, "outreach.skipped", {"message": message["id"], "domain": lead["domain"], "reasons": [store.mask(f) for f in found]}, agent=store.AGENT)


class _NotClaimed(Exception):
    """Live: the email's approval couldn't be claimed, so it isn't sent."""


def _claim(conn: sqlite3.Connection, message: dict) -> str | None:
    """The claim (MC §4.6 A6, §5.8): in one `BEGIN IMMEDIATE` transaction,
    claim the email's approval and count the attempt (the in-flight marker),
    so the claim is committed before Resend is called. Returns why it was
    refused, or None.

    An email whose approval an earlier attempt already claimed (Resend
    errored, or the process died before the mark) is the same action
    instance: it is retried under its `Idempotency-Key` without a second
    claim, as long as what goes out is still what was approved."""
    refusal = None
    with db.transaction(conn):
        claimed = approval.claimed(conn, message["id"])
        if claimed is None:
            try:
                approvals.use(conn, approval.KIND, approval.subject_of(message["id"]), run_id=log.current_run_id())
            except approvals.NotApproved as error:
                refusal = error.text  # a lapse or supersede it wrote commits with the block
        elif not approval.still_matches(conn, claimed):
            refusal = f"changed after {claimed.id} was used, so it isn't sent again"
            conn.execute("UPDATE outreach_messages SET status = 'failed', error = ? WHERE id = ? AND status = 'queued'",
                         (refusal, message["id"]))
        if refusal is None:
            conn.execute("UPDATE outreach_messages SET attempts = attempts + 1 WHERE id = ?", (message["id"],))
        else:
            log.event(conn, "outreach.not_claimed", {"message": message["id"], "why": store.mask(refusal)},
                      level="warning", agent=store.AGENT)
    return refusal


def _send_one(conn, message: dict, lead: dict, row: dict, mode: str, client) -> str:
    # Recomposed from the draft so the footer carries the current token, then
    # gated again on exactly the text that goes out.
    email = queue.build(conn, lead, row, subject=message["subject"], body=message["draft_body"])
    verdict = queue.gate_email(conn, f"outreach-send:{message['id']}", lead, email, kind=message["kind"], tool=message["tool_slug"], alert=False)
    store.record_qa(conn, f"outreach-send:{message['id']}", verdict.passed, verdict.result.reasons())
    if not verdict.passed:
        conn.execute(
            "UPDATE outreach_messages SET status = 'dropped', error = ? WHERE id = ?",
            ("failed the brand check at send time: " + "; ".join(verdict.result.reasons())[:400], message["id"]),
        )
        reasons = "\n".join(f"- {r}" for r in verdict.result.reasons()[:8])
        discord.alert(conn, f"Message {message['id']} failed the brand check at send time and was dropped:\n{reasons}", agent=store.AGENT)
        return f"message {message['id']} dropped at send time (brand check)"

    first_line = compose.first_line(email.draft)
    domain = contact_rules.mail_domain(row["email"])
    if mode == "shadow":
        _mark_sent(conn, message, lead, row, email, mode="shadow", resend_id=None)
        store.post(
            conn,
            "outreach-sent",
            f"**SHADOW** (not sent) message {message['id']} to {domain} for {lead['company']} (lead {lead['id']})\n"
            f"Subject: {email.subject}\n\n{email.draft}",
            own_copy=(email.subject, email.draft),
        )
        return f"SHADOW message {message['id']} to {domain}"

    refusal = _claim(conn, message)
    if refusal:
        raise _NotClaimed(f"message {message['id']} ({lead['domain']}): {refusal}")
    outcome, detail = _resend(conn, message, row, email, client)
    if outcome == "sent":
        with db.transaction(conn):
            _mark_sent(conn, message, lead, row, email, mode="live", resend_id=detail)
        store.post(
            conn,
            "outreach-sent",
            f"**Sent** message {message['id']} to {domain} ({lead['company']}, lead {lead['id']})\n"
            f"Subject: {email.subject}\nFirst line: {first_line}",
            own_copy=(email.subject, first_line),
        )
        return f"sent message {message['id']} to {domain}"
    if outcome == "pause":
        conn.execute("UPDATE outreach_messages SET error = ? WHERE id = ?", (detail[:500], message["id"]))
        store.auto_pause(conn, f"Resend refused the send: {detail}")
        return f"Resend error, outreach paused: {detail}"
    attempts = message["attempts"] + 1  # counted by the claim, before the call
    if outcome == "retry" and attempts < 3:
        conn.execute("UPDATE outreach_messages SET attempts = ?, error = ? WHERE id = ?", (attempts, detail[:500], message["id"]))
        log.event(conn, "outreach.retry", {"message": message["id"], "error": detail}, level="warning", agent=store.AGENT)
        return f"Resend error on message {message['id']}, will retry: {detail}"
    conn.execute(
        "UPDATE outreach_messages SET status = 'failed', attempts = ?, error = ? WHERE id = ?", (attempts, detail[:500], message["id"])
    )
    discord.alert(conn, f"Message {message['id']} to {domain} failed: {detail}", agent=store.AGENT)
    return f"message {message['id']} failed: {detail}"


def _mark_sent(conn, message: dict, lead: dict, row: dict, email: compose.Email, *, mode: str, resend_id: str | None) -> None:
    now = timeutil.stamp()
    conn.execute(
        "UPDATE outreach_messages SET status = ?, mode = ?, sent_at = ?, resend_id = ?, subject = ?, body_text = ?, "
        "body_html = ?, error = NULL WHERE id = ?",
        ("shadow" if mode == "shadow" else "sent", mode, now, resend_id, email.subject, email.text, email.html, message["id"]),
    )
    store.set_state(conn, f"first_{mode}_send_at", now, overwrite=False)
    if mode == "live":
        store.record_contacted(conn, lead["domain"])
        mail_domain = contact_rules.mail_domain(row["email"])
        if not contact_rules.is_free_mail(mail_domain):
            store.record_contacted(conn, mail_domain)
        store.set_lead_status(conn, [lead["id"]], "contacted" if message["kind"] == "first" else "followed_up")
    elif message["kind"] == "first":
        store.set_lead_status(conn, [lead["id"]], "shadow_sent")
    log.event(conn, "outreach.sent", {"message": message["id"], "mode": mode, "domain": lead["domain"], "kind": message["kind"]}, agent=store.AGENT)


def resend_payload(message: dict, row: dict, email: compose.Email) -> dict:
    return {
        "from": from_address(),
        "to": [row["email"]],
        "reply_to": settings.REPLY_TO,
        "subject": email.subject,
        "text": email.text,
        "html": email.html,
        "headers": compose.list_unsubscribe_headers(email.unsubscribe_url),
        "tags": [{"name": "agent", "value": "outreach"}, {"name": "message", "value": str(message["id"])}],
    }


def classify(status: int, body: dict) -> tuple[str, str]:
    """('pause' | 'retry' | 'fail', reason) for a Resend error response."""
    name = str(body.get("name") or "")
    text = str(body.get("message") or body.get("error") or "")[:200]
    detail = f"{status} {name}: {text}".strip()
    lowered = f"{name} {text}".lower()
    if status in (401, 403):
        return "pause", f"auth or domain error ({detail})"
    if status == 429 and "quota" in lowered:
        return "pause", f"quota reached ({detail})"
    if status == 429:
        return "retry", f"rate limited ({detail})"
    if status == 422 and ("domain" in lowered or "from" in lowered):
        return "pause", f"sending domain error ({detail})"
    if status >= 500:
        return "retry", f"Resend unavailable ({detail})"
    return "fail", detail


def _resend(conn, message: dict, row: dict, email: compose.Email, client) -> tuple[str, str]:
    key = config.require("RESEND_API_KEY_OUTREACH")
    try:
        url = resend_url()
    except ResendStubRefused as refused:
        return "pause", str(refused)
    owns = client is None
    client = client or resend_client()
    try:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Idempotency-Key": f"jura-outreach-{message['id']}"},
            json=resend_payload(message, row, email),
        )
    except httpx.HTTPError as error:
        return "retry", f"Resend unreachable ({type(error).__name__})"
    finally:
        if owns:
            client.close()
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code < 300 and body.get("id"):
        return "sent", str(body["id"])
    if response.status_code < 300:
        return "fail", f"Resend answered {response.status_code} without an id"
    return classify(response.status_code, body if isinstance(body, dict) else {})


# --- status ----------------------------------------------------------------


def status(conn: sqlite3.Connection) -> dict:
    mode = settings.mode()
    left, binding = quota(conn, mode if mode in ("shadow", "live") else "shadow")
    cap, note = daily_cap(conn, mode if mode in ("shadow", "live") else "shadow")
    tools, problem = registry.load()
    return {
        "mode": mode,
        "paused": pause.is_paused(conn, store.AGENT),
        "live_problems": live_problems(),
        "window": "%02d:%02d–%02d:%02d SGT, business days" % (*settings.window()[0], *settings.window()[1]),
        "in_window_now": outside_window(timeutil.now_sgt()) is None,
        "sent": counts(conn, mode if mode in ("shadow", "live") else "shadow"),
        "daily_cap": cap,
        "warm_up": note,
        "left_today": left,
        "binding_limit": binding,
        "queued": db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'queued'") or 0,
        "d1_configured": cloudflare.configured(),
        "reply_detection": replies.enabled(),
        "follow_ups": sync.follow_ups_on(),
        "do_not_contact_list": dnc.exists(),
        "live_tools": [t["slug"] for t in tools],
        "registry_problem": problem,
    }
