-- Build handoffs (prd-jura-mission-control-2026-10-25.md §5.9 step 2, ticket MC-10).
-- One row per app-build request Ting Yu said yes to, written in the same transaction as the
-- claim. The request's id and date sit here, never in the PRD file, so the file's SHA-256 stays
-- the one he saw. Status: handed_off until a builder reports the build (ticket 10b), then
-- built, then released. The request's own state lives only in `approvals` (MC §4.6 A2).

CREATE TABLE app_builds (
  id INTEGER PRIMARY KEY,
  app_id TEXT NOT NULL,              -- APP-014
  prd_path TEXT NOT NULL,            -- relative to jurasolutions/
  prd_sha256 TEXT NOT NULL,          -- of the file's bytes at the handoff
  approval_id TEXT NOT NULL UNIQUE,  -- A-nnnn
  approval_at TEXT NOT NULL,         -- when Ting Yu said yes (SGT)
  status TEXT NOT NULL DEFAULT 'handed_off' CHECK (status IN ('handed_off', 'built', 'released')),
  handed_off_at TEXT NOT NULL
);
-- One open handoff per app.
CREATE UNIQUE INDEX app_builds_open ON app_builds (app_id) WHERE status = 'handed_off';
