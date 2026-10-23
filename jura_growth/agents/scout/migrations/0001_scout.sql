-- Scout research tables (scout PRD §5.8). The outreach plug-in adds
-- outreach_messages, contacted_domains and its own state.

CREATE TABLE leads (
  id INTEGER PRIMARY KEY,
  company TEXT NOT NULL,
  display_name TEXT NOT NULL,          -- the name used in the email, without "Pte Ltd"
  domain TEXT NOT NULL,                -- the company's own website domain, no www.
  website TEXT NOT NULL,
  industry TEXT NOT NULL,
  size_signal TEXT,
  summary TEXT,                        -- what they do
  observations_json TEXT NOT NULL DEFAULT '[]',
  source_urls_json TEXT NOT NULL DEFAULT '[]',
  score INTEGER NOT NULL,
  score_reasons TEXT NOT NULL,         -- JSON list of written reasons
  channel TEXT NOT NULL,               -- email, form, none
  form_url TEXT,                       -- when channel = form
  tool_slug TEXT,                      -- the toolbox tool picked for this company
  status TEXT NOT NULL,                -- new, form_only, no_contact, queued, shadow_sent, contacted,
                                       -- followed_up, replied, unsubscribed, bounced, complained,
                                       -- suppressed, qa_dropped
  run_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (channel IN ('email', 'form', 'none')),
  CHECK (score BETWEEN 0 AND 100)
);
CREATE UNIQUE INDEX leads_domain ON leads (domain);
CREATE INDEX leads_created ON leads (created_at);
CREATE INDEX leads_status ON leads (status);

CREATE TABLE contacts (
  id INTEGER PRIMARY KEY,
  lead_id INTEGER NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
  email TEXT NOT NULL,                 -- lower-cased
  email_hash TEXT NOT NULL,            -- suppression.email_hash(email)
  source_url TEXT NOT NULL,            -- the page on the company's own site that publishes it
  kind TEXT NOT NULL,                  -- role, named
  mx_ok INTEGER NOT NULL,
  verified_at TEXT NOT NULL,           -- when the code fetched the page and found the address
  created_at TEXT NOT NULL,
  CHECK (kind IN ('role', 'named'))
);
CREATE UNIQUE INDEX contacts_email_hash ON contacts (email_hash);
CREATE INDEX contacts_lead ON contacts (lead_id);

-- Companies looked at and turned down, so a re-run doesn't research them
-- again. Business names and domains only. Pruned after 12 months.
CREATE TABLE scout_rejections (
  domain TEXT PRIMARY KEY,
  company TEXT,
  reason TEXT NOT NULL,
  rejected_at TEXT NOT NULL
);
