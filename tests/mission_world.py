"""Builders for the read model's tests (seams S2 and S4, ticket MC-08).

- `fresh_db()` is a temp growth.db built by `db.migrate`, closed again.
- `load_fortnight()` writes dataset D1 (`fortnight.py`) as the engine would: the
  `runs` and `events` rows, and every line of the JSONL mirror in its day's file.
- `approval()` writes one `approvals` row by raw SQL, with the kind name given as
  text: the read model never imports a kind (ticket review T5).
- `stat_snapshot()` is the AC-M13.1 oracle: path, size and mtime of every file
  under the temp data, outputs and PRD folders, opening none of them.
- `hot_journal()` is dataset D4: a growth.db and its journal copied while a
  `BEGIN IMMEDIATE` write had spilled pages, which proves itself hot first.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

import fortnight
from jura_growth import db, mission, paths, timeutil


def fresh_db() -> Path:
    conn = db.connect()
    conn.close()
    return paths.db_path()


def load_fortnight(conn: sqlite3.Connection, *, mirror: bool = True) -> None:
    for row in fortnight.RUNS:
        conn.execute(
            "INSERT INTO runs (id, agent, job, started_at, finished_at, status, summary) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row["id"], row["agent"], row["job"], row["started_at"], row["finished_at"], row["status"], row["summary"]),
        )
    for row in fortnight.EVENTS:
        conn.execute(
            "INSERT INTO events (run_id, ts, agent, level, kind, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (row["run_id"], row["ts"], row["agent"], row["level"], row["kind"], row["payload_json"]),
        )
    if mirror:
        for line in fortnight.MIRROR:
            mirror_line(line)


def mirror_line(record: dict, *, raw: str | None = None) -> None:
    path = paths.data_dir() / "runs" / f"{record['ts'][:10]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write((raw if raw is not None else json.dumps(record)) + "\n")


def approval(
    conn: sqlite3.Connection,
    number: int,
    kind: str,
    *,
    status: str = "pending",
    requested_at: str = "2026-11-09T09:12:00+08:00",
    decide_by: str = "2026-11-10T16:30:00+08:00",
    use_by: str | None = None,
    decided_at: str | None = None,
    decided_origin: str | None = None,
    used_at: str | None = None,
    closed_at: str | None = None,
    close_reason: str | None = None,
    posted_at: str | None = "2026-11-09T09:12:05+08:00",
) -> None:
    decided_by = None
    if decided_at:
        decided_by = "terminal:tingyu" if decided_origin == "terminal" else "discord:111"
        decided_origin = decided_origin or "ssh"
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by, use_by,"
        " decided_at, decided_by, decided_origin, used_at, closed_at, close_reason, posted_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            number, kind, f"{kind}:{number}", f"{number:064x}", status, "a test asked", requested_at, decide_by, use_by,
            decided_at, decided_by, decided_origin, used_at, closed_at, close_reason, posted_at,
        ),
    )


def source(now: str = "2026-11-10T08:00:00+08:00", *, jobs=None, installed=lambda job: True, days: int = 14) -> mission.Source:
    return mission.Source(
        db=paths.db_path(),
        data=paths.data_dir(),
        outputs=paths.outputs_dir(),
        prd=paths.prd_dir(),
        now=timeutil.parse(now),
        jobs=fortnight.JOBS if jobs is None else jobs,
        installed=installed,
        days=days,
    )


def stat_snapshot(*folders: Path) -> dict[str, tuple]:
    """Every entry under the folders, by path: (is a folder, size, mtime in ns)."""
    found = {}
    for folder in folders:
        for root, dirs, files in os.walk(folder):
            for name in dirs + files:
                path = os.path.join(root, name)
                info = os.lstat(path)
                found[path] = (os.path.isdir(path), info.st_size, info.st_mtime_ns)
    return found


def watched() -> tuple[Path, ...]:
    for folder in (paths.data_dir(), paths.outputs_dir(), paths.prd_dir()):
        folder.mkdir(parents=True, exist_ok=True)
    return (paths.data_dir(), paths.outputs_dir(), paths.prd_dir())


def hot_journal(target: Path, scratch: Path) -> None:
    """Give the growth.db at `target` a hot journal (dataset D4).

    A writer opens `BEGIN IMMEDIATE` with a tiny page cache and inserts enough
    that pages spill into the database file before any commit. While it is
    open, the database and its journal are copied aside; the writer then rolls
    back and the copies replace the originals. Nothing holds a lock on them, so
    the journal is hot. The fixture proves it on a throwaway copy, which a
    read-write open rolls back (the journal goes and the one committed row is
    all that is left), or it raises."""
    scratch.mkdir(parents=True, exist_ok=True)
    journal = Path(f"{target}-journal")
    setup = sqlite3.connect(target, isolation_level=None)
    setup.execute("CREATE TABLE filler (id INTEGER PRIMARY KEY, body BLOB)")
    setup.execute("INSERT INTO filler (body) VALUES (x'00')")
    setup.close()

    writer = sqlite3.connect(target, isolation_level=None)
    writer.execute("PRAGMA cache_size = 5")
    writer.execute("BEGIN IMMEDIATE")
    for _ in range(300):
        writer.execute("INSERT INTO filler (body) VALUES (?)", (os.urandom(3000),))
    assert journal.exists() and journal.stat().st_size > 0, "the writer left no journal"
    saved_db, saved_journal = scratch / "growth.db", scratch / "growth.db-journal"
    shutil.copyfile(target, saved_db)
    shutil.copyfile(journal, saved_journal)
    writer.execute("ROLLBACK")
    writer.close()
    shutil.copyfile(saved_db, target)
    shutil.copyfile(saved_journal, journal)

    proof = scratch / "proof.db"
    shutil.copyfile(target, proof)
    shutil.copyfile(journal, Path(f"{proof}-journal"))
    rolled = sqlite3.connect(proof)
    rows = rolled.execute("SELECT count(*) FROM filler").fetchone()[0]
    rolled.close()
    if Path(f"{proof}-journal").exists() or rows != 1:
        raise AssertionError(f"the D4 journal is not hot (rows after the open: {rows})")
