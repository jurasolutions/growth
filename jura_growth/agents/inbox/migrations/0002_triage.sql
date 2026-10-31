-- Triage (inbox watch ticket 02). What language they wrote in, from a closed list, so the card can say
-- the draft is English (S13), and how many drafts the brand gate has refused for this message (D8).
ALTER TABLE inbox_items ADD COLUMN language TEXT;
ALTER TABLE inbox_items ADD COLUMN brand_failures INTEGER NOT NULL DEFAULT 0;
