-- Seeing and steering from Discord (inbox watch ticket 04). `asked_at` is when Ting Yu asked for a draft
-- or a redraft, until triage answers. `alerted_at` and `alert_repeated_at` are the #alerts lines for a
-- high item (S7), empty until Discord takes them. `text_removed_at` is when retention took what a person
-- wrote (PRD §4; `inbox/text_retention.py`).
ALTER TABLE inbox_items ADD COLUMN asked_at TEXT;
ALTER TABLE inbox_items ADD COLUMN alerted_at TEXT;
ALTER TABLE inbox_items ADD COLUMN alert_repeated_at TEXT;
ALTER TABLE inbox_items ADD COLUMN text_removed_at TEXT;
