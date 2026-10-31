-- Inbox watch (prd-jura-inbox-watch-2026-10-31 §5). `state` and `source` have no CHECK on purpose:
-- SQLite can't alter one, later tickets add states, and `inbox/store.py` validates both in code.

-- One recorded reaction. `key` counts it once (W5). `thread_json` holds what its source needs to
-- answer it, which the store doesn't read. Approval state lives only in `approvals`.
CREATE TABLE inbox_items (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  conversation TEXT NOT NULL,
  sender_name TEXT NOT NULL DEFAULT '',
  sender_address TEXT NOT NULL DEFAULT '',
  sender_domain TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '',
  text_cut INTEGER NOT NULL DEFAULT 0,
  target TEXT NOT NULL DEFAULT '',
  thread_json TEXT NOT NULL DEFAULT '{}',
  attachments_json TEXT NOT NULL DEFAULT '[]',
  lead_id INTEGER,
  class TEXT,
  priority TEXT,
  draft TEXT,
  guidance TEXT,
  promised INTEGER NOT NULL DEFAULT 0,
  triage_attempts INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'new',
  note TEXT NOT NULL DEFAULT '',
  stale INTEGER NOT NULL DEFAULT 0,
  received_at TEXT,
  recorded_at TEXT NOT NULL,
  reported_at TEXT,
  closed_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX inbox_items_state ON inbox_items (state);
CREATE INDEX inbox_items_conversation ON inbox_items (conversation);
CREATE INDEX inbox_items_unreported ON inbox_items (reported_at) WHERE reported_at IS NULL;

-- The mailboxes' last good check, and what the mail health check remembers between runs.
CREATE TABLE inbox_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Each outgoing Message-ID, hashed, so a copy of Jura's own mail is recognised even if a header
-- was rewritten, and an answer naming one finds its lead (F2, F4). Written from ticket 03 on, for
-- inbox replies. Outreach sends carry no kept id: see `store.remember_outgoing`.
CREATE TABLE inbox_outgoing (
  message_key TEXT PRIMARY KEY,
  lead_id INTEGER,
  recorded_at TEXT NOT NULL
);
