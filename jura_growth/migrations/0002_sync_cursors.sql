-- How far an append-only feed from outside has been read. `d1:suppression`
-- holds the id of the last event processed from the website's D1 suppression
-- table: the next sync asks only for later ids, so every event is acted on
-- once, whether or not the address was already suppressed here. `marker`
-- identifies the event at `position`, so a table that was recreated or
-- rewritten behind the cursor fails the sync instead of hiding new events.

CREATE TABLE sync_cursors (
  name TEXT PRIMARY KEY,
  position INTEGER NOT NULL,
  marker TEXT,
  updated_at TEXT NOT NULL
);
