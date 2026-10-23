-- Outreach tables (scout PRD §5.8). `leads` and `contacts` come from the
-- scout plug-in's migration; SQLite resolves the references when rows are
-- written, so the order the two plug-ins migrate in doesn't matter.

CREATE TABLE outreach_messages (
  id INTEGER PRIMARY KEY,
  lead_id INTEGER NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
  contact_id INTEGER REFERENCES contacts (id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                  -- first, follow_up
  tool_slug TEXT,
  subject TEXT NOT NULL,
  draft_body TEXT NOT NULL,            -- as written, before the signature and footer
  body_text TEXT NOT NULL,             -- the full plain-text email
  body_html TEXT NOT NULL,
  qa_json TEXT,                        -- the brand gate's verdicts
  resend_id TEXT,
  mode TEXT,                           -- shadow or live, set when sent
  send_after TEXT NOT NULL,            -- SGT date; unsent mail rolls to the next business day
  attempts INTEGER NOT NULL DEFAULT 0, -- send attempts that hit a temporary error
  queued_at TEXT NOT NULL,
  sent_at TEXT,
  status TEXT NOT NULL,                -- queued, shadow, sent, bounced, complained, replied,
                                       -- skipped, dropped, failed, cancelled
  error TEXT,
  CHECK (kind IN ('first', 'follow_up'))
);
CREATE INDEX outreach_messages_due ON outreach_messages (status, send_after);
CREATE INDEX outreach_messages_lead ON outreach_messages (lead_id);
CREATE INDEX outreach_messages_resend ON outreach_messages (resend_id);
CREATE INDEX outreach_messages_sent ON outreach_messages (mode, sent_at);
-- One first email and one follow-up per company, ever (the per-company cap).
CREATE UNIQUE INDEX outreach_messages_one_per_kind ON outreach_messages (lead_id, kind)
  WHERE status NOT IN ('dropped', 'cancelled', 'skipped', 'failed');

-- Every domain that has had a live email. Kept when old leads are deleted.
CREATE TABLE contacted_domains (
  domain TEXT PRIMARY KEY,
  first_contacted_at TEXT NOT NULL
);

-- Small facts the sender needs: first_live_send_at, first_shadow_send_at.
CREATE TABLE outreach_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Replies seen by the optional read-only IMAP check. Sender and date only:
-- no bodies, no subjects. `message_key` is a hash of the Message-ID header.
CREATE TABLE outreach_replies (
  id INTEGER PRIMARY KEY,
  lead_id INTEGER REFERENCES leads (id) ON DELETE CASCADE,
  contact_id INTEGER REFERENCES contacts (id) ON DELETE CASCADE,
  message_key TEXT NOT NULL UNIQUE,
  received_at TEXT NOT NULL,
  unsubscribe INTEGER NOT NULL DEFAULT 0,
  detected_at TEXT NOT NULL
);
CREATE INDEX outreach_replies_lead ON outreach_replies (lead_id);
