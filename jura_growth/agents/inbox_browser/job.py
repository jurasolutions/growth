"""The `inbox-watch` job's hooks (inbox watch PRD S2, S3, S4; ADR 0006).

- `precheck`: the hours, once an hour, a publish pause, the auth variables, then what an earlier run
  left behind. Launchd can fire early until the Mac restarts, so the hours are checked here too.
- `after_run`: audits the transcript, settles what the run recorded and what it read, posts what is
  due, and replaces the summary and error with words of our own. A model's words, and anything it
  quoted from a page, never reach the run row, #alerts or a run update. Failing closed is the
  plug-in's job (`failed_closed`).
"""

from __future__ import annotations

import os
import sqlite3
from datetime import timedelta

from jura_growth import agents, caps, db, discord, log, pause, timeutil, transcripts
from jura_growth.agents.inbox import report, watch
from jura_growth.agents.inbox_browser import scope
from jura_growth.agents.publish import audit, fixture
from jura_growth.agents.publish.job import AUTH_VARIABLES, ENDINGS, MODEL_FAILED

RESUME = "`jura-growth resume inbox-browser` or /growth resume inbox-browser"


def in_window() -> bool:
    start, end = caps.INBOX_WATCH_WINDOW
    return start <= timeutil.now_sgt().strftime("%H:%M") <= end


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
        return agents.NothingToDo("the watch read the platforms less than an hour ago")
    held = pause.is_paused(conn, watch.PUBLISH)
    if held:
        return f"publish is paused, and the two share the accounts: {held}"
    for name in AUTH_VARIABLES:
        if os.environ.get(name):
            return (f"{name} is set, so Claude Code would start without the Chrome tools; remove it from the "
                    f"environment scheduled runs get (the watch needs the claude.ai login)")
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


def _ending(error: str, run_id: int) -> str:
    phrase = next((words for prefix, words in ENDINGS if (error or "").startswith(prefix)), MODEL_FAILED)
    return f"Run {run_id} {phrase}; its words are withheld (run {run_id}'s transcript keeps them)."


def _no_browser(conn: sqlite3.Connection, run_id: int) -> None:
    """Once a day: the text is the same each hour, and the health strip keeps saying it after that."""
    today = timeutil.today_str()
    earlier = db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'inbox.no_browser' AND ts LIKE ?", (f"{today}%",))
    log.event(conn, "inbox.no_browser", {"run": run_id}, level="warning", agent=watch.AGENT, run_id=run_id)
    if earlier:
        return
    discord.alert(conn, f"No browser was connected when the inbox watch ran (run {run_id}), so nothing on Facebook or "
                        "Instagram was read. On the Mac, open Chrome with the Claude extension signed in to the same "
                        "account as Claude Code. This is the only alert about it today.", agent=watch.AGENT)


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
    settled = watch.settle(conn, run_id, reads.text, trusted=not found.failures)
    failed_surfaces = watch.finish_surfaces(conn, run_id, reads)
    # A steered run's numbers aren't told, and stay unremembered until a clean run reads them again.
    lines = (watch.post_lines(conn, run_id) if not found.failures else []) + watch.over_cap_lines(conn, run_id)
    watch.record_run_message(conn, run_id, lines)
    if found.no_browser:
        _no_browser(conn, run_id)
    _tried(conn, "report", lambda: report.report_due(conn))

    stop = watch.stopped_reason(conn, run_id)
    errors = []
    if found.failures:
        errors.append(f"The audit of run {run_id} failed: {'; '.join(found.failures)}. Watching and social replies are "
                      f"paused until you resume them: {RESUME}.")
    if stop:
        errors.append(f"Run {run_id} stopped: {stop} ({watch.STOP_REASONS.get(stop, 'a stop signal')}).")
    if outcome.status == "failed" and not errors:
        errors.append(_ending(outcome.error, run_id))
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
    """The outcome when the checks themselves broke: failed, with a fixed reason naming the run and
    the error's type only, and the watch paused. A run nobody could check keeps no benefit of doubt."""
    from jura_growth import runner

    name = type(error).__name__
    for step in (
        lambda: log.event(conn, "inbox.checks_failed", {"error": name}, level="error", agent=watch.AGENT, run_id=run_id),
        lambda: pause.pause(conn, watch.AGENT, f"the checks after run {run_id} couldn't run", notify=False),
    ):
        try:
            step()
        except Exception:  # noqa: BLE001 - the failed outcome stands whatever happens here
            pass
    return runner.Outcome(
        "failed",
        summary=f"the checks after run {run_id} couldn't run",
        error=(f"The checks after run {run_id} couldn't run ({name}), so the run is treated as failed. Watching and "
               f"social replies are paused until you resume them: {RESUME}."),
        cost_usd=getattr(outcome, "cost_usd", None),
    )
