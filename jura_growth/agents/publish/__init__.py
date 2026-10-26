"""Browser publishing: the publish queue (prd/pending/prd-jura-browser-publishing-2026-10-25.md).

A **publish item** is one action the browser may take, with frozen content: today a social post
for one platform and day (BP-02a; community posts and joins follow in BP-02b). Every item is the
subject of an approval request (`publish_item:<id>`), and nothing is handed to a browser run
until `publish next` claims that approval (MC §4.6 A6). Approval state lives only in `approvals`;
`publish_items` holds the item's own lifecycle: ready, claimed, done, stopped, unknown or
withdrawn.

Modules:

- `items`: creating items and their lifecycle writes.
- `kinds`: the `social-post` approval kind.
- `claim`: every claim-time check and the claim itself; `claimable(conn, now)` is the read-only
  form the publish job's precheck uses (BP-03).
- `job`: the job hooks. `after_run` settles a claim the run left open as `unknown`.
- `limits`: the caps in `caps.py`, tightened by `config/publish.yaml`.
- `commands`: `jura-growth publish next | done | stopped | queue | resolve`.

No browser is involved yet: BP-03 adds the scheduled `publish` job that drives Chrome.
See docs/social.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

NAME = "publish"
MIGRATIONS = Path(__file__).parent / "migrations"


def register(cli) -> None:
    from jura_growth.agents.publish import commands

    commands.register(cli)


def digest(conn: sqlite3.Connection, day: str) -> dict:
    """The day's posted, skipped, expired and stopped items (AC-P8.3), by the items' own day."""
    from jura_growth.agents.publish import items

    found = [items.Item.from_row(r) for r in conn.execute("SELECT * FROM publish_items WHERE day = ?", (day,))]
    if not found:
        return {"figures": {}, "lines": [], "brief": []}
    counts = {"posted": 0, "skipped": 0, "expired": 0, "stopped": 0}
    for item in found:
        if item.state == "done" and item.outcome == "posted":
            counts["posted"] += 1
        elif item.state == "stopped":
            counts["stopped"] += 1
        elif item.state == "withdrawn" and item.outcome is None:
            latest = items.latest_request(conn, item)
            if latest is not None and latest.status in ("skipped", "expired"):
                counts[latest.status] += 1
    line = ", ".join(f"{number} {word}" for word, number in counts.items())
    return {"figures": {f"publish_{word}": number for word, number in counts.items()},
            "lines": [f"Publishing: {line}"], "brief": []}


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    from jura_growth.agents.publish import job as publish_job

    return publish_job.after_run(conn, job, run_id, outcome)


def approval_kinds() -> dict:
    from jura_growth.agents.publish import kinds

    return kinds.kinds()
