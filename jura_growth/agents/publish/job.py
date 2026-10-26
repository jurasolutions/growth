"""The publish job's hooks (browser publishing PRD §5.8).

- `precheck` (before Claude starts): an auth variable that would hide the Chrome tools is a plain
  skip Ting Yu should see (AC-P9.5). Otherwise it runs `items.sync()` in a committed transaction
  and posts the cards that raised (`cards.sweep_safely()`), so a changed post gets its new card
  whether or not anything is due (code review 02, B1), then asks `claim.claimable()`, read-only:
  nothing claimable is `NothingToDo("nothing due")`, a quiet run with no Claude (AC-P8.2).
- `setup_gaps`: the same auth variables, by name, for `jura-growth status`.
- `after_run`: see its docstring.
"""

from __future__ import annotations

import os
import sqlite3

from jura_growth import agents, cards, db, log, pause, timeutil
from jura_growth.agents.publish import claim, items

# With either set, Claude Code keeps Chrome integration off, even with --chrome (spike §1).
AUTH_VARIABLES = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def precheck(job: str, conn: sqlite3.Connection):
    """A skip reason, `NothingToDo`, or None to start the run."""
    if job != "publish":
        return None
    for name in AUTH_VARIABLES:
        if os.environ.get(name):
            return (f"{name} is set, so Claude Code would start without the Chrome tools; remove it from the "
                    f"environment scheduled runs get (the publish job needs the claude.ai login)")
    with db.transaction(conn):
        items.sync(conn)
    cards.sweep_safely(conn)
    if not claim.claimable(conn):
        return agents.NothingToDo(claim.NOTHING_DUE)
    return None


def setup_gaps() -> list:
    from jura_growth.health import Gap

    return [Gap(name, ok=not os.environ.get(name), must_be_unset=True) for name in AUTH_VARIABLES]


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """Settle as `unknown` this run's open claims, and any left by an earlier run that ended
    without its own `after_run` (the process was killed), and fail the run; None when there are
    none. A Terminal claim (no run) is left to Ting Yu, who can `publish resolve` it."""
    if run_id is None:
        return None
    rows = conn.execute(
        "SELECT p.* FROM publish_items p LEFT JOIN runs r ON r.id = p.run_id WHERE p.state = 'claimed' "
        "AND p.run_id IS NOT NULL AND (p.run_id = ? OR r.id IS NULL OR r.status != 'running') ORDER BY p.id",
        (run_id,),
    ).fetchall()
    open_items = [items.Item.from_row(r) for r in rows]
    if not open_items:
        return None
    settled = []
    with db.transaction(conn):
        for found in open_items:
            conn.execute("UPDATE publish_items SET state = 'unknown', finished_at = ? WHERE id = ? AND state = 'claimed'",
                         (timeutil.stamp(), found.id))
            record = items.claimed_request(conn, found)
            shown = record.id if record else found.label
            log.event(conn, "publish.unknown", {"item": found.label, "approval": shown}, level="error",
                      agent=items.AGENT, run_id=run_id)
            settled.append(shown)
        pause.pause(conn, items.AGENT, f"{', '.join(settled)} may or may not have been posted", notify=False)
    from jura_growth import runner

    lines = [f"{shown} was claimed, but the run recorded neither done nor stopped, so it may or may not have "
             f"been posted. It won't be tried again, and publish is paused. Check the page, then settle it: "
             f"/growth publish resolve {shown} posted --url <url>, or /growth publish resolve {shown} not-posted."
             for shown in settled]
    return runner.Outcome("failed", summary=outcome.summary, error=" ".join(lines), cost_usd=outcome.cost_usd)
