-- Shortlist research with job boards (scout PRD §5.2a, amended 2026-10-31).
-- Adds columns only, so an older checkout still runs against this database.

-- Every posting that showed the company hiring for manual work:
-- [{url, title, seen (YYYY-MM-DD), duties: [...]}]. Evidence only, never a contact source.
ALTER TABLE leads ADD COLUMN hiring_evidence_json TEXT NOT NULL DEFAULT '[]';
-- One line on why this lead beat the day's other candidates.
ALTER TABLE leads ADD COLUMN comparison TEXT;
-- The score by §5.2a factor: {industry_fit, size_fit, hiring_signals,
-- paperwork_signals, specific_observations, enquiry_address}.
ALTER TABLE leads ADD COLUMN score_breakdown_json TEXT;

-- A candidate researched and not kept keeps its score, so a re-run can say
-- how it compared. NULL for rejections recorded before this migration.
ALTER TABLE scout_rejections ADD COLUMN score INTEGER;

-- One ranking a day (SGT): kept leads can't be taken back, so the day's
-- candidates are compared together, once, and the best kept.
CREATE TABLE scout_rankings (
  day TEXT PRIMARY KEY,                -- YYYY-MM-DD, SGT
  ranked_at TEXT NOT NULL,
  run_id INTEGER,
  candidates INTEGER NOT NULL,         -- submitted in the batch
  kept INTEGER NOT NULL
);
