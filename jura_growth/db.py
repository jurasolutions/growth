"""SQLite access and migrations. `data/growth/growth.db` is the log of record.

The database lives in OneDrive, which does not get on with SQLite's WAL files
(the AI OS PRD records the same problem for Discord Dispatch). So the journal
stays in rollback mode and every connection is short-lived.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from jura_growth import agents, paths, timeutil

CORE_MIGRATIONS = Path(__file__).parent / "migrations"


def connect(path: Path | None = None, *, migrate_now: bool = True) -> sqlite3.Connection:
    target = paths.writable(path or paths.db_path())
    conn = sqlite3.connect(target, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if migrate_now:
        migrate(conn)
    return conn


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migration_sets() -> list[tuple[str, Path]]:
    sets = [("core", CORE_MIGRATIONS)]
    for module in agents.plugins():
        folder = getattr(module, "MIGRATIONS", None)
        if folder and Path(folder).is_dir():
            sets.append((module.NAME, Path(folder)))
    return sets


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    done = {row[0] for row in conn.execute("SELECT id FROM schema_migrations")}
    applied = []
    for owner, folder in migration_sets():
        for file in sorted(folder.glob("*.sql")):
            migration_id = f"{owner}/{file.name}"
            if migration_id in done:
                continue
            sql = file.read_text(encoding="utf-8")
            # executescript commits on its own, so wrap the file and the record
            # in one script to keep them atomic.
            conn.executescript(
                "BEGIN;\n"
                + sql
                + "\nINSERT INTO schema_migrations (id, applied_at) VALUES "
                + f"('{migration_id}', '{timeutil.stamp()}');\nCOMMIT;"
            )
            applied.append(migration_id)
    return applied


def rows(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params)]


def one(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def scalar(conn: sqlite3.Connection, sql: str, params: tuple | dict = ()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None
