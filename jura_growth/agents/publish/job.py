"""The publish job's hooks (browser publishing PRD §5.8).

BP-02a fills in `after_run`'s first duty: a claim the run left open, with neither `publish done`
nor `publish stopped`, is settled as `unknown` (AC-P10.1), and so is one an earlier run left when
its process died before its own `after_run`. Publishing never retries, so an
unknown item is never claimed again; `publish` pauses, and the run fails with the two commands
that settle it, which the runner posts to #alerts. BP-03 adds the precheck, the transcript audit
and the run update here. Its precheck must first run `items.sync()` in a committed transaction
and post the cards it raised (`cards.sweep_safely()`), then ask `claim.claimable()`: otherwise a
change the heartbeat superseded waits for its new card until something is claimable (code review
02, B1).
"""

from __future__ import annotations

import sqlite3

from jura_growth import db, log, pause, timeutil
from jura_growth.agents.publish import items


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
