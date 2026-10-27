"""Runs and events.

Every event goes to the `events` table and, as one JSON line, to
`data/growth/runs/YYYY-MM-DD.jsonl` (the SGT day). The JSONL file is a plain
mirror that survives a broken database.

Outside a transaction both are written at once. Inside `db.transaction()` the
row is part of the transaction and the mirror line is written after the
commit, never after a rollback, because the mirror is append-only and must not
record work that didn't happen. The cost is a gap: a crash between the commit
and the mirror write loses that transaction's lines while `events` keeps its
rows. That is the right way round, since `growth.db` is the log of record, and
readers that need every record (the slot classifier, `slots.py`) take them from
both stores and count a record found in both once. A mirror write that fails
after the commit is reported on stderr and never raised. Lines can land out of
order, or in the next day's file for a commit after midnight, so a reader of
the mirror sorts by `ts`.

A command started inside a scheduled run picks the run up from
`JURA_GROWTH_RUN_ID`, so what a headless Claude session does through
`jura-growth` is filed under that run.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from jura_growth import config, db, paths, timeutil


def current_run_id() -> int | None:
    value = os.environ.get("JURA_GROWTH_RUN_ID")
    return int(value) if value and value.isdigit() else None


def current_agent() -> str | None:
    return os.environ.get("JURA_GROWTH_AGENT")


def current_job() -> str | None:
    """The scheduled job this process runs under (the runner sets it), or None
    outside a run. A label, not a credential: it can only restrict."""
    return os.environ.get("JURA_GROWTH_JOB") or None


def event(
    conn: sqlite3.Connection | None,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    level: str = "info",
    agent: str | None = None,
    run_id: int | None = None,
) -> None:
    ts = timeutil.stamp()
    run_id = run_id if run_id is not None else current_run_id()
    agent = agent or current_agent()
    clean = config.redact(payload or {})
    body = json.dumps(clean, ensure_ascii=False, default=str)
    if conn is not None:
        conn.execute(
            "INSERT INTO events (run_id, ts, agent, level, kind, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, ts, agent, level, kind, body),
        )
    record = {"ts": ts, "run_id": run_id, "agent": agent, "level": level, "kind": kind, "payload": clean}
    # Inside db.transaction() the mirror line waits for the commit: the
    # mirror is append-only, so it must never hold an event that rolled back.
    if conn is None or not db.after_commit(conn, lambda: mirror(record)):
        mirror(record)


def mirror(record: dict[str, Any]) -> None:
    path = paths.writable(paths.data_dir() / "runs" / f"{timeutil.today_str()}.jsonl")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def start_run(conn: sqlite3.Connection, agent: str, job: str, *, started_at: str | None = None) -> int:
    """Open a run row. `started_at` is the run's real start when the row is
    written after the work (a quiet run that turned out to do something)."""
    cursor = conn.execute(
        "INSERT INTO runs (agent, job, started_at, status) VALUES (?, ?, ?, 'running')",
        (agent, job, started_at or timeutil.stamp()),
    )
    run_id = cursor.lastrowid
    event(conn, "run.start", {"job": job}, agent=agent, run_id=run_id)
    return run_id


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    *,
    summary: str | None = None,
    error: str | None = None,
    cost_usd: float | None = None,
) -> None:
    error = config.redact(error) if error else None
    summary = config.redact(summary) if summary else None
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, summary = ?, error = ?, cost_usd = ? WHERE id = ?",
        (timeutil.stamp(), status, summary, error, cost_usd, run_id),
    )
    row = conn.execute("SELECT agent, job FROM runs WHERE id = ?", (run_id,)).fetchone()
    event(
        conn,
        "run.finish",
        {"job": row["job"], "status": status, "summary": summary, "error": error, "cost_usd": cost_usd},
        level="error" if status == "failed" else "info",
        agent=row["agent"],
        run_id=run_id,
    )


def skip_run(conn: sqlite3.Connection, agent: str, job: str, reason: str) -> int:
    run_id = start_run(conn, agent, job)
    finish_run(conn, run_id, "skipped", summary=reason)
    return run_id
