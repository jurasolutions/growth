"""The hooks of the `inbox-watch` and `inbox-reply` jobs (inbox watch PRD D4, S2, S3, S4; N13; ADR 0006).

- `precheck`: the hours, once an hour, a publish pause, the auth variables, then what an earlier run
  left behind. Launchd can fire early until the Mac restarts, so the hours are checked here too.
- `after_run`: audits the transcript, settles what the run recorded and what it read, posts what is
  due, and replaces the summary and error with words of our own. A model's words, and anything it
  quoted from a page, never reach the run row, #alerts or a run update. Failing closed is the
  plug-in's job (`failed_closed`).
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from jura_growth import agents, approvals, caps, cards, db, log, pause, timeutil, transcripts
from jura_growth.agents.inbox import reply_run, report, send, settings, social, store, watch
from jura_growth.agents.inbox_browser import scope
from jura_growth.agents.publish import audit, fixture
from jura_growth.agents.publish import job as publish_job

RESUME = "`jura-growth resume inbox-browser` or /growth resume inbox-browser"


def in_window() -> bool:
    return settings.in_hours(caps.INBOX_WATCH_WINDOW)


def _too_soon(conn: sqlite3.Connection) -> bool:
    """W2: at most one read an hour, however launchd fires. Each read is more activity on the account."""
    last = db.scalar(conn, "SELECT started_at FROM runs WHERE job = 'inbox-watch' AND status != 'skipped' ORDER BY id DESC LIMIT 1")
    if not last:
        return False
    return timeutil.now_sgt() - timeutil.parse(last) < timedelta(minutes=caps.INBOX_WATCH_MINUTES_BETWEEN_RUNS)


def _tried(conn: sqlite3.Connection, step: str, work) -> None:
    """Housekeeping that the next run tries again, so it may never stop the watch or fail a run."""
    try:
        work()
    except Exception as error:  # noqa: BLE001
        log.event(conn, "inbox.watch_step_failed", {"step": step, "error": type(error).__name__}, level="error", agent=watch.AGENT)


def precheck(conn: sqlite3.Connection):
    """A skip reason, `NothingToDo`, or None to start the run. A fixture its guard refuses raises."""
    fixture.active()
    if not in_window():
        return agents.NothingToDo("outside the watch's hours")
    if _too_soon(conn):
        return agents.NothingToDo(f"the watch read the platforms less than {caps.INBOX_WATCH_MINUTES_BETWEEN_RUNS} minutes ago")
    held = pause.is_paused(conn, watch.PUBLISH)
    if held:
        return f"publish is paused, and the two share the accounts: {held}"
    problem = publish_job.auth_problem("the watch needs the claude.ai login")
    if problem:
        return problem
    problems = watch.page_problems()
    if problems:
        return "; ".join(problems)
    _tried(conn, "settle", lambda: watch.settle_orphans(conn))  # a killed run's held items
    _tried(conn, "report", lambda: report.report_due(conn))
    return None


def _audit(transcript: transcripts.Transcript | None, outcome) -> audit.Audit:
    if transcript is None:
        # With no transcript a good run can't be cleared. A run that broke first says so itself.
        failures = ["no transcript was kept, so the run can't be cleared"] if outcome.status == "ok" else []
        return audit.Audit(failures=failures)
    return audit.audit(transcript, hosts=scope.hosts(), approved=[], images=[], site=fixture.active(), rules=scope.WATCH_RULES)


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """The run's last word, before its row, the alert and auto-pause see the outcome."""
    if run_id is None:
        return None
    from jura_growth import runner

    path = transcripts.find(run_id)
    transcript = transcripts.read(path) if path else None
    found = _audit(transcript, outcome)
    if found.failures:
        with db.transaction(conn):
            log.event(conn, "inbox.audit_failed", {"failures": found.failures}, level="error", agent=watch.AGENT, run_id=run_id)
            pause.pause(conn, watch.AGENT, f"the audit of run {run_id} failed", notify=False)

    reads = watch.page_reads(transcript)
    settled = watch.settle(conn, run_id, reads.results, trusted=not found.failures)
    # A steered run's numbers aren't told, and stay unremembered until a clean run reads them again.
    # Before the surfaces settle, because the first good read of `posts` is what tells nothing (F12).
    lines = watch.post_lines(conn, run_id) if not found.failures else []
    failed_surfaces = watch.finish_surfaces(conn, run_id, watch.PageReads() if found.failures else reads)
    watch.record_run_message(conn, run_id, [*lines, *watch.over_cap_lines(conn, run_id), *watch.own_lines(conn, run_id)])
    if found.no_browser:
        publish_job.no_browser_once(conn, run_id, watch.AGENT, "inbox.no_browser",
                                    f"No browser was connected when the inbox watch ran (run {run_id}), so nothing on "
                                    "Facebook or Instagram was read.")
    _tried(conn, "report", lambda: report.report_due(conn))
    _tried(conn, "cards", lambda: _cards_read_again(conn))  # the Page may have answered something with a card

    stop = watch.stopped_reason(conn, run_id)
    errors = []
    if found.failures:
        # Fixed words and a count. A finding can quote what a model asked for, and #alerts renders links:
        # the detail stays in the event and the transcript (code review 05, B1).
        count = len(found.failures)
        errors.append(f"The audit of run {run_id} failed with {count} finding{'s' if count != 1 else ''}, in that run's "
                      f"inbox.audit_failed event. Watching and social replies are paused until you resume them: {RESUME}.")
    if stop:
        errors.append(f"Run {run_id} stopped: {stop} ({watch.STOP_REASONS.get(stop, 'a stop signal')}).")
    if outcome.status == "failed" and not errors:
        errors.append(publish_job.ending(outcome.error, run_id))
    read = len(watch.SURFACES) - len(failed_surfaces)
    summary = f"read {read} of {len(watch.SURFACES)} surfaces; " + ", ".join(
        f"{count} {state}" for state, count in sorted(settled.states.items())) if settled.states else \
        f"read {read} of {len(watch.SURFACES)} surfaces; nothing new"
    if failed_surfaces:
        summary += "; failed: " + ", ".join(failed_surfaces)
    if found.no_browser:
        summary += "; no browser was connected"
    summary += "".join(f"; {warning}" for warning in found.warnings)
    return runner.Outcome("failed" if errors else "ok", summary=summary, error=" ".join(errors), cost_usd=outcome.cost_usd,
                          alerted=bool(stop) and not found.failures)


def failed_closed(conn: sqlite3.Connection, run_id: int | None, outcome, error: Exception):
    """The outcome when the checks themselves broke. A run nobody could check keeps no benefit of doubt,
    and its held items reach him through the next mail check."""
    return publish_job.checks_failed(conn, run_id, outcome, error, agent=watch.AGENT, event="inbox.checks_failed",
                                     paused=f"Watching and social replies are paused until you resume them: {RESUME}.")


def _cards_read_again(conn: sqlite3.Connection) -> None:
    approvals.expire_due(conn)
    cards.sweep_safely(conn)


# --- inbox-reply ------------------------------------------------------------------------------------


def reply_precheck(conn: sqlite3.Connection):
    """A skip reason, `NothingToDo`, or None to start the run. A quiet run starts no Claude (ADR 0001).
    A claim an earlier run left open settles first (N13). That pauses this agent, so the run is skipped."""
    fixture.active()
    reply_run.forget_killed_runs(conn)
    settled = reply_run.settle_open(conn)
    _tried(conn, "tell", lambda: send.tell_outcomes(conn))
    if settled:
        return pause.is_paused(conn, watch.AGENT)
    if not settings.in_hours(caps.INBOX_REPLY_WINDOW):
        return agents.NothingToDo("outside the reply hours")
    held = pause.is_paused(conn, watch.PUBLISH)
    if held:
        return f"publish is paused, and the two share the accounts: {held}"
    problem = publish_job.auth_problem("the reply job needs the claude.ai login")
    if problem:
        return problem
    problems = watch.page_problems()
    if problems:
        return "; ".join(problems)
    _tried(conn, "settle", lambda: watch.settle_orphans(conn))  # a killed run's held items
    _tried(conn, "cards", lambda: _cards_read_again(conn))
    off = social.switched_off(conn)
    if off:
        return agents.NothingToDo(off)
    blocked = reply_run.why_not_now(conn, run_id=None)
    if blocked:
        return agents.NothingToDo(blocked)
    return None if reply_run.due(conn) else agents.NothingToDo("no reply is waiting")


def _reply_audit(transcript: transcripts.Transcript | None, outcome, handed: dict | None, claimed: dict | None) -> audit.Audit:
    if transcript is None:
        failures = ["no transcript was kept, so the run can't be cleared"] if outcome.status == "ok" else []
        return audit.Audit(failures=failures)
    platforms = (social.platform_of(handed),) if handed else watch.PLATFORMS
    approved = [claimed["draft"]] if claimed and claimed["draft"] else []
    places = [handed["target"]] if handed and social.is_dm(handed) else []  # a comment's target is held to its host and its read-back (N12)
    return audit.audit(transcript, hosts=scope.hosts(platforms), approved=approved, images=[], site=fixture.active(), places=places,
                       rules=scope.REPLY_RULES)


def _read_shown(claimed: dict | None, reads: watch.PageReads) -> list[str]:
    """Why the read it claimed on doesn't stand: a run may not claim on words its pages never returned."""
    if claimed is None:
        return []
    said = store.thread_of(claimed).get("claim_read") or {}
    if said.get("newest") and not watch.words_on_page(said["newest"], reads.results):
        return ["the run claimed on a message its pages never showed"]
    if said.get("author") and not watch.words_on_page(said["author"], reads.results):
        return ["the run claimed on an author its pages never showed"]
    return []


def _typed_anything(transcript: transcripts.Transcript | None) -> bool:
    if transcript is None:
        return True
    return any(call.name == audit.CHROME + "computer" and call.input.get("action") == "type" for call in transcript.calls)


def _said_not_sent_but_typed(conn: sqlite3.Connection, item_id: int, transcript: transcripts.Transcript | None) -> bool:
    item = store.get(conn, item_id)
    return bool(item) and item["state"] == store.FAILED and _typed_anything(transcript)


def reply_after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """The reply run's last word: the audit, what it read, any claim it left open, and what he hears. A
    model's words reach neither the run's row nor #alerts: these are fixed words and record fields."""
    if run_id is None:
        return None
    from jura_growth import runner

    path = transcripts.find(run_id)
    transcript = transcripts.read(path) if path else None
    handed, claimed = reply_run.handed_to(conn, run_id), reply_run.claimed_by(conn, run_id)
    found = _reply_audit(transcript, outcome, handed, claimed)
    reads = watch.page_reads(transcript)
    failures = [*found.failures, *_read_shown(claimed, reads)]
    if failures:
        with db.transaction(conn):
            log.event(conn, "inbox.audit_failed", {"failures": failures}, level="error", agent=watch.AGENT, run_id=run_id)
            pause.pause(conn, watch.AGENT, f"the audit of run {run_id} failed", notify=False)
    settled = watch.settle(conn, run_id, reads.results, trusted=not failures)
    if claimed and _said_not_sent_but_typed(conn, claimed["id"], transcript):
        with db.transaction(conn):
            store.set_item_state(conn, claimed["id"], store.UNKNOWN, note="The run says this didn't go, but it typed, so it may have. It won't be sent again.")
            pause.pause(conn, watch.AGENT, f"run {run_id} typed a reply it says didn't go", notify=False)
    left_open = reply_run.settle_open(conn)
    if found.no_browser:
        publish_job.no_browser_once(conn, run_id, watch.AGENT, "inbox.no_browser",
                                    f"No browser was connected when a reply run ran (run {run_id}), so nothing was typed. "
                                    "An approved reply stays approved until its use-by.")
    reply_run.forget_handed(conn, run_id)
    _tried(conn, "report", lambda: report.report_due(conn))
    _tried(conn, "cards", lambda: _cards_read_again(conn))
    _tried(conn, "tell", lambda: send.tell_outcomes(conn))

    now = store.get(conn, claimed["id"]) if claimed else None
    unconfirmed = bool(left_open) or bool(now and now["state"] == store.UNKNOWN)
    stop = watch.stopped_reason(conn, run_id)
    errors = []
    if failures:
        count = len(failures)
        errors.append(f"The audit of run {run_id} failed with {count} finding{'s' if count != 1 else ''}, in that run's inbox.audit_failed "
                      f"event. Watching and social replies are paused until you resume them: {RESUME}.")
    if stop:
        errors.append(f"Run {run_id} stopped: {stop} ({watch.STOP_REASONS.get(stop, 'a stop signal')}).")
    if unconfirmed:
        errors.append(f"Run {run_id} left a reply unconfirmed. Watching and social replies are paused until you resume them: {RESUME}.")
    if outcome.status == "failed" and not errors:
        errors.append(publish_job.ending(outcome.error, run_id))
    summary = f"reply: {store.label(claimed['id'])} is {now['state']}" if claimed and now else "reply: nothing claimed"
    if settled.states:
        summary += "; " + ", ".join(f"{count} {state}" for state, count in sorted(settled.states.items()))
    if found.no_browser:
        summary += "; no browser was connected"
    summary += "".join(f"; {warning}" for warning in found.warnings)
    return runner.Outcome("failed" if errors else "ok", summary=summary, error=" ".join(errors), cost_usd=outcome.cost_usd,
                          alerted=(bool(stop) or unconfirmed) and not failures)
