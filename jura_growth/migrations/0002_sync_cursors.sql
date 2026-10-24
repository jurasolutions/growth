-- How far an append-only feed from outside has been read. `d1:suppression`
-- holds the id of the last event processed from the website's D1 suppression
-- table: the next sync asks only for later ids, so every event is acted on
-- once, whether or not the address was already suppressed here.

CREATE TABLE sync_cursors (
  name TEXT PRIMARY KEY,
  position INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
