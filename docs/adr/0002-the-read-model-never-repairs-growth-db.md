# The one-pager's read model opens growth.db read-only and never repairs it

Status: proposed (2026-10-25). Accepted in ticket MC-08 of `prd-jura-mission-control-2026-10-25.md`.

Every other reader uses `db.connect()`, which creates folders, sets `journal_mode`, runs migrations
and, on its first open, rolls back a stale journal. The one-pager's read model instead opens
`file:…?mode=ro` with `PRAGMA query_only = ON`. A hot journal makes that open fail with
`SQLITE_READONLY_ROLLBACK`, and the one-pager tells Ting Yu to send `/growth status` rather than
recovering itself. A reporting path must never be the process that decides what happens to an
unfinished write. Lapsed approvals are shown as lapsed by comparing their deadlines with the clock,
not by writing; the one-pager job writes those transitions on the runner's own connection before the
read model runs. Don't "fix" this by switching the read model to `db.connect()` or `immutable=1`.
