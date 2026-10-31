-- The watch (prd-jura-inbox-watch-2026-10-31, F6, F13, W3). Text a person wrote stays in inbox_items.

-- One row per surface: what the latest run said about it, whether that read stood, and the last good
-- read. A surface with no good read has failed, which is different from a quiet day (F13).
CREATE TABLE inbox_surfaces (
  surface TEXT PRIMARY KEY,
  first_tried_at TEXT NOT NULL,
  last_run_id INTEGER,
  said_ok INTEGER NOT NULL DEFAULT 0,
  said_items INTEGER NOT NULL DEFAULT 0,
  read_ok INTEGER NOT NULL DEFAULT 0,
  last_good_at TEXT,
  last_good_items INTEGER,
  updated_at TEXT NOT NULL
);

-- One row per published post the watch has read: the counts as last read and as last told, so only a
-- rise is reported, and when it was read, so the least recently read go first.
CREATE TABLE inbox_watch_posts (
  publish_item INTEGER PRIMARY KEY REFERENCES publish_items (id),
  reactions INTEGER NOT NULL DEFAULT 0,
  shares INTEGER NOT NULL DEFAULT 0,
  comments INTEGER NOT NULL DEFAULT 0,
  page_comments INTEGER NOT NULL DEFAULT 0,
  told_reactions INTEGER,
  told_shares INTEGER,
  told_unread INTEGER NOT NULL DEFAULT 0,
  gone_at TEXT,
  gone_told INTEGER NOT NULL DEFAULT 0,
  last_read_at TEXT,
  last_run_id INTEGER
);
CREATE INDEX inbox_watch_posts_run ON inbox_watch_posts (last_run_id);
