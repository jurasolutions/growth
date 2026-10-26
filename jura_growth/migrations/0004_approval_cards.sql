-- Approval cards in #approvals (MC §4.6 A12, §5.6; ticket 04b).
--
-- `approvals.posted_at` and `approvals.message_id` record that a card went out.
-- This table keeps what an in-place edit needs: the card's first message as it
-- was posted (already masked), so an edit replaces only its first line, and
-- what that line shows now, so each change is edited once. It holds no
-- decision: the record's state is read from `approvals` every time.

CREATE TABLE approval_cards (
  approval_id INTEGER PRIMARY KEY REFERENCES approvals (id),
  message_id TEXT,              -- the first message's id; NULL if Discord gave none (edits become follow-ups)
  first_piece TEXT NOT NULL,    -- that message's text as posted
  shows TEXT NOT NULL           -- what its first line shows: pending, approved, used, skipped, expired, superseded
    CHECK (shows IN ('pending', 'approved', 'used', 'skipped', 'expired', 'superseded')),
  posted_at TEXT NOT NULL,
  updated_at TEXT
);

-- The cards that can still change; the rest are final.
CREATE INDEX approval_cards_open ON approval_cards (shows) WHERE shows IN ('pending', 'approved');
