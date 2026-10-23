-- Shared tables. Each agent adds its own through its plug-in's migrations.

CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  agent TEXT NOT NULL,
  job TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL DEFAULT 'running', -- running, ok, failed, skipped
  summary TEXT,
  error TEXT,
  cost_usd REAL
);
CREATE INDEX runs_agent_started ON runs (agent, started_at);

-- Append-only. Mirrored line by line to runs/YYYY-MM-DD.jsonl.
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs (id),
  ts TEXT NOT NULL,
  agent TEXT,
  level TEXT NOT NULL, -- info, warning, error
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX events_run ON events (run_id);
CREATE INDEX events_kind_ts ON events (kind, ts);

CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;

CREATE TABLE discord_posts (
  id INTEGER PRIMARY KEY,
  channel TEXT NOT NULL,
  ts TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  delivered INTEGER NOT NULL DEFAULT 1 -- 0 when no webhook was configured
);
CREATE INDEX discord_posts_channel_hash ON discord_posts (channel, content_hash);

-- Shared by every agent: nothing is ever sent to a suppressed address or domain.
CREATE TABLE suppression (
  id INTEGER PRIMARY KEY,
  email TEXT,          -- lower-cased; NULL when only the hash is known
  email_hash TEXT,     -- sha256 of the lower-cased address
  domain TEXT,         -- set to suppress a whole domain
  reason TEXT NOT NULL, -- unsubscribe, bounce, complaint, manual
  source TEXT NOT NULL,
  added_at TEXT NOT NULL,
  CHECK (email IS NOT NULL OR email_hash IS NOT NULL OR domain IS NOT NULL)
);
CREATE UNIQUE INDEX suppression_email_hash ON suppression (email_hash) WHERE email_hash IS NOT NULL;
CREATE UNIQUE INDEX suppression_domain ON suppression (domain) WHERE domain IS NOT NULL AND email_hash IS NULL;

CREATE TABLE pause_flags (
  agent TEXT PRIMARY KEY, -- an agent name, or 'all'
  paused INTEGER NOT NULL,
  reason TEXT,
  set_at TEXT NOT NULL
);

-- Brand-check attempts per outgoing item: one regeneration, then the item drops.
CREATE TABLE qa_attempts (
  item_key TEXT PRIMARY KEY,
  agent TEXT,
  attempts INTEGER NOT NULL,
  last_issues_json TEXT,
  updated_at TEXT NOT NULL
);
