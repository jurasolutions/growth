-- App factory (prd-jura-app-factory-2026-10-24.md §5.6, block 4).
-- One row per app PRD the daily factory filed through `apps submit-prd`.

CREATE TABLE app_prds (
  id INTEGER PRIMARY KEY,
  app_id TEXT NOT NULL UNIQUE,   -- APP-003
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  tier TEXT NOT NULL,            -- browser, ai
  category TEXT NOT NULL,
  path TEXT NOT NULL,            -- relative to jurasolutions/
  day TEXT NOT NULL,             -- SGT day it was written
  run_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX app_prds_day ON app_prds (day);
