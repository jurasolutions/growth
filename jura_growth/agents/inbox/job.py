"""The `inbox-check` job's hooks. Its precheck does all the mail work with no model, under the job
lock and after the pause checks. It ends as a quiet run unless something waits for triage, and only
then does Claude start (ADR 0001). Raising an approval is never done here (technical review, N10).

The precheck never raises, for anything. A raising precheck is a failed run, and `check_auto_pause`
reads only run rows, while a good check leaves none. So three failures weeks apart would still read
as "in a row" and stop the mail for good (technical review B5; code review 01, P-5). A fault is
logged, and shows on the health strip and in #alerts through `mail.failed`.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, TypeVar

from jura_growth import agents, caps, locks, log
from jura_growth.agents.inbox import mail, reply_run, report, settings, signals, store, triage, watch

T = TypeVar("T")


def in_window() -> bool:
    return settings.in_hours(caps.INBOX_CHECK_WINDOW)


def _settle_held(conn: sqlite3.Connection) -> None:
    """A browser run's held items and open claims, when no browser job is running. A browser pause stops
    those jobs' own prechecks and never this one, so nobody stays hidden behind it (N3), and no claim stays
    open (N13). `inbox-send` tells him what that claim came to."""
    if not store.has_state(conn, store.OBSERVED) and not reply_run.open_claims(conn):
        return
    with locks.held(locks.BROWSER) as free:
        if free:
            watch.settle_orphans(conn)
            reply_run.settle_open(conn)


def _guarded(conn: sqlite3.Connection, step: str, work: Callable[[], T], otherwise: T) -> T:
    try:
        found = work()
    except Exception as error:  # noqa: BLE001 - see the module's docstring
        try:
            log.event(None, "inbox.check_error", {"step": step, "error": type(error).__name__}, level="error", agent=mail.AGENT)
            mail.failed(conn, step, error)
        except Exception:  # noqa: BLE001 - the same database may be what failed: the next check tries again
            pass
        return otherwise
    try:
        mail.cleared(conn, step)
    except Exception:  # noqa: BLE001
        pass
    return found


def precheck(conn: sqlite3.Connection) -> agents.NothingToDo | None:
    if not in_window():
        return agents.NothingToDo("outside the mail check's hours")
    found = _guarded(conn, "intake", lambda: mail.intake(conn), mail.Intake(failed=1))
    _guarded(conn, "settle-held", lambda: _settle_held(conn), None)
    _guarded(conn, "settle", lambda: triage.settle(conn), 0)
    _guarded(conn, "usage", lambda: signals.report_usage(conn), None)
    _guarded(conn, "complaints", lambda: signals.report_complaints(conn), None)
    reported = _guarded(conn, "report", lambda: report.report_due(conn), 0)
    _guarded(conn, "high", lambda: report.alert_high(conn), 0)
    if _guarded(conn, "waiting", lambda: triage.waiting(conn), False):
        return None
    return agents.NothingToDo(f"{found.recorded} new, {found.noise} noise, {reported} reported")
