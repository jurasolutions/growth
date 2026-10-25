# Quiet runs leave an event, not a run row

Status: proposed (2026-10-25). Accepted in ticket MC-01 of `prd-jura-mission-control-2026-10-25.md`.

scout-send runs about 43 times a business day and usually finds nothing to send, and publish runs
27 times a day with the same pattern. To tell those quiet runs apart from slots the Mac slept
through, the runner writes an append-only `run.quiet` event (`{"job", "started_at"}`) instead of a
`runs` row. Run rows would bury every other job in `runs`, in `jura-growth status` and in the
digest counts, and would reset the failure streak `check_auto_pause` reads. Events are append-only
by trigger, so these rows are permanent; changing the shape later means reading both.
