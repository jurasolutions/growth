"""Run updates: one Discord message per run of the jobs that ask for one.

The runner calls `after_run` once on every path a run can take except the
PAUSE file: a pause-flag, schedule or precheck skip; a quiet run with nothing
to do; a finished run, after its row, the alert and auto-pause; and the lock
skip, with `conn=None`, so the database is never opened. The runner wraps the
call, so an error here is logged and never changes the run.

Ticket MC-03 fills this in (`prd-jura-mission-control-2026-10-25.md` §5.5).
Until then it does nothing.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jura_growth.runner import Outcome


def after_run(conn: sqlite3.Connection | None, job: str, spec: dict, run_id: int | None, outcome: Outcome) -> None:
    """Post the run update for this run, if its job asks for one."""
    return None
