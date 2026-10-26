"""The publish job's hooks (browser publishing PRD §5.8).

BP-02a fills in `after_run`'s first duty: a claim the run left open, with neither `publish done`
nor `publish stopped`, is settled as `unknown` (AC-P10.1). Publishing never retries, so an
unknown item is never claimed again; `publish` pauses, and the run fails with the two commands
that settle it, which the runner posts to #alerts. BP-03 adds the precheck, the transcript audit
and the run update here.
"""

from __future__ import annotations

import sqlite3

from jura_growth import db, log, pause, timeutil
from jura_growth.agents.publish import items


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """Settle this run's open claims as `unknown` and fail the run; None when there are none."""
    if run_id is None:
        return None
    rows = conn.execute("SELECT * FROM publish_items WHERE run_id = ? AND state = 'claimed' ORDER BY id", (run_id,)).fetchall()
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
