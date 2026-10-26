"""Browser publishing: the publish queue (prd/pending/prd-jura-browser-publishing-2026-10-25.md).

A **publish item** is one action the browser may take, with frozen content: a social post for
one platform and day (BP-02a), a community post for one group and day, a join for one group, or a
join's membership answers (BP-02b). Every item is the
subject of an approval request (`publish_item:<id>`), and nothing is handed to a browser run
until `publish next` claims that approval (MC §4.6 A6). Approval state lives only in `approvals`;
`publish_items` holds the item's own lifecycle: ready, claimed, done, stopped, unknown or
withdrawn.

Modules:

- `items`: creating items and their lifecycle writes.
- `kinds`: the `social-post` approval kind, and reading any item's content.
- `group_kinds`: the `community-post` and `group-join` approval kinds.
- `claim`: every claim-time check and the claim itself; `claimable(conn, now)` is the read-only
  form the publish job's precheck uses (BP-03).
- `job`: the job hooks: the precheck, `after_run` (unknown claims, the audit, the no-browser
  alert, the summary) and the run update.
- `scope`: the publish run's commands and Chrome tools, scoped by domain (ADR 0005).
- `audit`: the transcript audit for hosts, tabs and typed text.
- `hosts`: each platform's hosts, for post URLs and for the browser.
- `limits`: the caps in `caps.py`, tightened by `config/publish.yaml`.
- `commands`: `jura-growth publish next | done | stopped | queue | resolve`.

The scheduled `publish` job (BP-03, `prompts/publish.md`) drives Chrome through Claude in Chrome,
every 20 minutes from 09:00 to 17:40 SGT, posting to the Facebook Page in this build.
See docs/social.md.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

NAME = "publish"
MIGRATIONS = Path(__file__).parent / "migrations"
# Social posts are the only kind this build publishes; BP-05's community posts report to #community.
RUN_UPDATE_DISCORD_CHANNEL = "social-drafts"


def register(cli) -> None:
    from jura_growth.agents.publish import commands

    commands.register(cli)


def digest(conn: sqlite3.Connection, day: str) -> dict:
    """The day's posted, skipped, expired and stopped items (AC-P8.3), by the items' own day."""
    from jura_growth.agents.publish import items, kinds

    found = [items.Item.from_row(r) for r in conn.execute("SELECT * FROM publish_items WHERE day = ?", (day,))]
    if not found:
        return {"figures": {}, "lines": [], "brief": []}
    counts = {"posted": 0, "skipped": 0, "expired": 0, "stopped": 0}
    for item in found:
        if item.state == "done" and item.outcome == "posted":
            counts["posted"] += 1
        elif item.state == "stopped":
            counts["stopped"] += 1
        elif item.state in ("ready", "withdrawn") and item.outcome is None:  # ready: not yet synced
            latest = items.latest_request(conn, item)
            if (latest is not None and latest.status == "skipped") or kinds.skipped_by_hand(conn, item):
                counts["skipped"] += 1  # in #approvals, or by hand with `social skip`
            elif latest is not None and latest.status == "expired":
                counts["expired"] += 1
    line = ", ".join(f"{number} {word}" for word, number in counts.items())
    return {"figures": {f"publish_{word}": number for word, number in counts.items()},
            "lines": [f"Publishing: {line}"], "brief": []}


def precheck(job: str, conn: sqlite3.Connection):
    """The publish job's precheck (`job.precheck`); the plug-in's other jobs have none."""
    if job != "publish":
        return None
    from jura_growth.agents.publish import job as publish_job

    return publish_job.precheck(job, conn)


def setup_gaps() -> list:
    """`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` in the environment (AC-P9.5)."""
    from jura_growth.agents.publish import job as publish_job

    return publish_job.setup_gaps()


def permissions(job: str):
    """The publish run's commands and Chrome tools (`scope.py`, AC-P9.2)."""
    if job != "publish":
        return None
    from jura_growth.agents.publish import scope

    return scope.permissions()


def run_update(conn: sqlite3.Connection, run) -> list[str] | None:
    """Only a run that claimed an item posts an update (`run_update: claimed-only`, AC-P8.1)."""
    from jura_growth.agents.publish import job as publish_job

    return publish_job.run_update(conn, run)


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    from jura_growth.agents.publish import job as publish_job

    return publish_job.after_run(conn, job, run_id, outcome)


def approval_kinds() -> dict:
    from jura_growth.agents.publish import kinds

    return kinds.kinds()
