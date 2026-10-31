-- Sending an approved email reply (inbox watch ticket 03). `send_attempts` is the claim's in-flight
-- marker, `resend_id` and `sent_at` what came back, and `told_at` when Ting Yu heard the outcome: empty
-- until Discord takes the line, so a line it refused goes again on the next send slot (F15).
ALTER TABLE inbox_items ADD COLUMN send_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inbox_items ADD COLUMN resend_id TEXT;
ALTER TABLE inbox_items ADD COLUMN sent_at TEXT;
ALTER TABLE inbox_items ADD COLUMN told_at TEXT;
