-- An idea whose PRD expired unanswered may be proposed again after 30 days, under the same slug
-- and a new APP number (prd-jura-mission-control-2026-10-25.md §5.9 step 5, ticket MC-10). The
-- slug stops being unique in `app_prds`; `apps submit-prd` already refuses a slug that a live,
-- pending, built or resting app holds. SQLite can't drop a UNIQUE constraint in place, so the
-- table is rebuilt with every row copied as it is.

CREATE TABLE app_prds_rebuilt (
  id INTEGER PRIMARY KEY,
  app_id TEXT NOT NULL UNIQUE,   -- APP-003
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,            -- browser, ai
  category TEXT NOT NULL,
  path TEXT NOT NULL,            -- relative to jurasolutions/
  day TEXT NOT NULL,             -- SGT day it was written
  run_id INTEGER,
  created_at TEXT NOT NULL
);
INSERT INTO app_prds_rebuilt (id, app_id, slug, name, tier, category, path, day, run_id, created_at)
  SELECT id, app_id, slug, name, tier, category, path, day, run_id, created_at FROM app_prds;
DROP TABLE app_prds;
ALTER TABLE app_prds_rebuilt RENAME TO app_prds;
CREATE INDEX app_prds_day ON app_prds (day);
CREATE INDEX app_prds_slug ON app_prds (slug);
