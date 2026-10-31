-- Seeing and steering from Discord (inbox watch ticket 04). `asked_at` is when Ting Yu asked for a draft
-- or a redraft, until triage answers. `alerted_at` and `alert_repeated_at` are the #alerts lines for a
-- high item (S7), empty until Discord takes them. `text_removed_at` is when retention took what a person
-- wrote (PRD §4; `inbox/text_retention.py`). `suppressed_by_this` is set when this item's own message is
-- what suppressed its sender, and only such a message can lift it (code review 04, SEC-2).
ALTER TABLE inbox_items ADD COLUMN asked_at TEXT;
ALTER TABLE inbox_items ADD COLUMN alerted_at TEXT;
ALTER TABLE inbox_items ADD COLUMN alert_repeated_at TEXT;
ALTER TABLE inbox_items ADD COLUMN text_removed_at TEXT;
ALTER TABLE inbox_items ADD COLUMN suppressed_by_this INTEGER NOT NULL DEFAULT 0;
