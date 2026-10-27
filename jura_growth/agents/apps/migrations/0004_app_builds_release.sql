-- A build's way from preview to production (prd-jura-mission-control-2026-10-25.md §5.9 steps 3
-- and 4, ticket MC-10b). `apps built` records the task, its branch, the head commit and the
-- preview, and the row becomes `built`; `apps release-plan` stamps when it handed out the merge;
-- `apps released` stamps the release once main holds the commit, and the row becomes
-- `released`. The release request's own state lives only in `approvals` (MC §4.6 A2).
-- Every column is new and empty, so no existing row changes.

ALTER TABLE app_builds ADD COLUMN task_id TEXT;             -- T-0031
ALTER TABLE app_builds ADD COLUMN branch TEXT;              -- claude/T-0031-paynow-qr, based on main
ALTER TABLE app_builds ADD COLUMN head_sha TEXT;            -- the full commit the release request covers
ALTER TABLE app_builds ADD COLUMN preview_url TEXT;         -- the branch's Cloudflare Pages preview
ALTER TABLE app_builds ADD COLUMN built_at TEXT;
ALTER TABLE app_builds ADD COLUMN release_planned_at TEXT;  -- when release-plan printed the merge
ALTER TABLE app_builds ADD COLUMN released_at TEXT;

-- One unreleased build per app: handed off, or built and waiting for its release.
DROP INDEX app_builds_open;
CREATE UNIQUE INDEX app_builds_open ON app_builds (app_id) WHERE status IN ('handed_off', 'built');
