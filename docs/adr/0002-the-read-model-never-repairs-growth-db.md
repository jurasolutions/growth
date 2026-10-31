# The one-pager's read model opens growth.db read-only and never repairs it

Status: accepted (2026-10-26, ticket MC-08 of `prd-jura-mission-control-2026-10-25.md`).

Every other reader uses `db.connect()`, which creates folders, sets `journal_mode`, runs migrations
and, on its first open, rolls back a stale journal. The one-pager's read model instead opens
`file:…?mode=ro` with `PRAGMA query_only = ON`. A hot journal makes that open fail with
`SQLITE_READONLY_ROLLBACK`, and the one-pager tells Ting Yu to send `/growth status` rather than
recovering itself. A reporting path must never be the process that decides what happens to an
unfinished write. Lapsed approvals are shown as lapsed by comparing their deadlines with the clock,
not by writing; the one-pager job writes those transitions on its own connection before the
read model runs, and skips that write when growth.db is locked, leaving it to the next writer. Don't "fix" this by switching the read model to `db.connect()` or `immutable=1`.

In code: `jura_growth/mission.py` probes the connection with one query before anything else uses
it, so a hot journal or a lock (`database is locked` after two seconds) becomes the "unfinished
write" state, and a missing `growth.db` or migration a line, before any plug-in hook sees the
connection. The plug-ins' `health(conn)` hooks get that read-only connection, so a write in one
raises. The suite proves it on dataset D4, a journal copied mid-transaction that a throwaway copy
shows to be hot (`tests/mission_world.py`).
