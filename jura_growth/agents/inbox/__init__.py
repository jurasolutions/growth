"""Inbox watch: every reaction to Jura reported, every reply approved
(prd/pending/prd-jura-inbox-watch-2026-10-31.md).

So far this agent sees mail and reports it, with no model:

- `store`: the record of every reaction, and `store.record`, the one way in.
- `mail`: the mail intake. Read-only IMAP, the noise filter, a lead's reply recorded as the 16:45
  check would, website enquiries, Jura's own mail dropped.
- `report`: one message per reaction in #mission-control, retried until delivered.
- `watch`: what a watch run may record, and what its records come to. The jobs that drive the browser
  belong to the `inbox_browser` plug-in, which has its own pause flag. Its commands are here, because
  a second `inbox` click group would silently replace this one.
- `job`: the job's precheck.
- `commands`: `jura-growth inbox status`, and a watch run's `watch-targets`, `observe` and `stopped`.
- `settings`: the limits in `caps.py`, tightened by `config/inbox.yaml`.

Job `inbox-check` runs every 15 minutes, 07:00 to 23:45 SGT. Its precheck does all of the above
and starts no Claude.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

NAME = "inbox"
MIGRATIONS = Path(__file__).parent / "migrations"


def register(cli) -> None:
    from jura_growth.agents.inbox.commands import inbox_group

    cli.add_command(inbox_group)


def precheck(job: str, conn: sqlite3.Connection):
    if job != "inbox-check":
        return None
    from jura_growth.agents.inbox import job as inbox_job

    return inbox_job.precheck(conn)


def permissions(job: str):
    """What the prompt uses. There is nothing else for a model to do yet."""
    if job != "inbox-check":
        return None
    from jura_growth import headless

    return headless.Permissions(commands=("inbox status",))


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome) -> None:
    """A report Discord refused goes again here as well as in the precheck (B7)."""
    if job != "inbox-check":
        return None
    from jura_growth.agents.inbox import report

    report.report_due(conn)
    return None


def setup_gaps() -> list:
    from jura_growth import health
    from jura_growth.agents.inbox import mail

    return [health.Gap(name, ok=False) for name in mail.setup_gaps()]


def health(conn: sqlite3.Connection) -> list[str]:
    """Reports waiting on Discord, and a mailbox that can't be read. Reads only."""
    from jura_growth.agents.inbox import store

    try:
        waiting = store.open_counts(conn)["unreported"]
        lines = [f"Inbox: {problem}" for _, problem in store.with_prefix(conn, store.PROBLEM)]
    except sqlite3.OperationalError:  # not migrated yet: nothing has been read
        return []
    if waiting:
        lines.append(f"Inbox: {waiting} reaction{'s' if waiting != 1 else ''} not yet reported in #mission-control")
    return lines


def digest(conn: sqlite3.Connection, day: str) -> dict:
    """R5: counts only, never a name, an address or a word anyone wrote."""
    from jura_growth.agents.inbox import store

    counts = {**store.day_counts(conn, day), **store.open_counts(conn)}
    if not any(counts.values()):
        return {"figures": {}, "lines": [], "brief": []}
    reactions = counts["reactions"]
    parts = [f"{reactions} reaction{'s' if reactions != 1 else ''}", f"{counts['noise']} filtered as noise"]
    if counts["hand_replies"]:
        parts.append(f"{counts['hand_replies']} needing a hand reply")
    if counts["unreported"]:
        parts.append(f"{counts['unreported']} not yet reported")
    return {
        "figures": {f"inbox_{name}": number for name, number in counts.items()},
        "lines": ["Inbox: " + ", ".join(parts)],
        "brief": [f"{reactions} reaction{'s' if reactions != 1 else ''}"] if reactions else [],
    }
