"""The D1 half of the UAT stub (ticket 18; X13), served by `tests/resend_stub.py`.

An in-memory SQLite database with the two website tables the engine reads, `suppression` and
`app_usage`, answering `POST .../accounts/<account>/d1/database/<database>/query` the way the
Cloudflare API does: `{"success": true, "result": [{"results": [...]}]}`. It runs read queries only,
so nothing the engine sends can change it. Point the engine at it with
`JURA_GROWTH_D1_BASE_URL=http://127.0.0.1:<port>`; the D1 client refuses that variable unless it
is a loopback http URL and the data folder is a temporary one.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from typing import Sequence

QUERY_PATH = re.compile(r"^/accounts/[^/]+/d1/database/[^/]+/query$")

SCHEMA = """
CREATE TABLE suppression (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT NOT NULL,
    email TEXT,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    resend_email_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE app_usage (
    app_slug TEXT NOT NULL,
    day TEXT NOT NULL,
    opens INTEGER NOT NULL DEFAULT 0,
    completions INTEGER NOT NULL DEFAULT 0
);
"""

COLUMNS = {
    "suppression": ("email_hash", "email", "reason", "source", "resend_email_id", "created_at"),
    "app_usage": ("app_slug", "day", "opens", "completions"),
}


class D1:
    """The stub's database. `suppression` and `app_usage` are rows to start with."""

    def __init__(self, *, suppression: Sequence[dict] = (), app_usage: Sequence[dict] = ()):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        for table, rows in (("suppression", suppression), ("app_usage", app_usage)):
            columns = COLUMNS[table]
            marks = ", ".join("?" * len(columns))
            self._conn.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})",
                [tuple(row.get(c) for c in columns) for row in rows],
            )
        self._conn.commit()
        self._conn.execute("PRAGMA query_only = ON")

    @staticmethod
    def handles(path: str) -> bool:
        return bool(QUERY_PATH.match(path))

    def answer(self, body: dict) -> tuple[int, dict]:
        """The HTTP status and JSON body for one query request."""
        sql = str(body.get("sql") or "")
        params = body.get("params") or []
        if not sql.lstrip().upper().startswith("SELECT"):
            return 400, {"success": False, "errors": [{"message": "the UAT stub answers SELECT queries only"}]}
        try:
            with self._lock:
                rows = [dict(row) for row in self._conn.execute(sql, params).fetchall()]
        except sqlite3.Error as error:
            return 400, {"success": False, "errors": [{"message": f"D1 stub: {error}"}]}
        return 200, {"success": True, "errors": [], "result": [{"results": rows, "success": True}]}
