"""The `inbox-check` job's hooks. Its precheck does all the mail work with no model, under the job
lock and after the pause checks, and ends as a quiet run: there is nothing to triage yet."""

from __future__ import annotations

import sqlite3

from jura_growth import agents, caps, timeutil
from jura_growth.agents.inbox import mail, report


def in_window() -> bool:
    """PRD §4: launchd can fire early until the Mac restarts, so the hours are checked here too."""
    start, end = caps.INBOX_CHECK_WINDOW
    return start <= timeutil.now_sgt().strftime("%H:%M") <= end


def precheck(conn: sqlite3.Connection) -> agents.NothingToDo:
    if not in_window():
        return agents.NothingToDo("outside the mail check's hours")
    found = mail.intake(conn)
    reported = report.report_due(conn)
    return agents.NothingToDo(f"{found.recorded} new, {found.noise} noise, {reported} reported")
