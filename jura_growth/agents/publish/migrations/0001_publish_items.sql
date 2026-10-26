-- Browser publishing: the publish queue (browser publishing PRD §5.4, §5.6; BP-02a).
--
-- One row per publish item: one action the browser may take, with frozen
-- content. Each item is the subject of approval requests (`publish_item:<id>`)
-- in the core `approvals` table, which alone holds the decision (MC §4.6 A2):
-- this table keeps only the item's own lifecycle.

CREATE TABLE publish_items (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,                    -- P-nnnn, shown beside the A-id; never typed
  kind TEXT NOT NULL CHECK (kind IN ('social_post', 'community_post', 'community_join', 'community_join_answers')),
  platform TEXT NOT NULL,                 -- facebook, linkedin, instagram (community items: facebook)
  ref TEXT NOT NULL,                      -- the social_posts or community_posts row, or the group id
  parent_item INTEGER REFERENCES publish_items (id),  -- the join an answers item belongs to
  target_url TEXT NOT NULL,
  posting_identity TEXT NOT NULL,
  content_json TEXT NOT NULL,             -- text, image paths and hashes, answers: as raised, then as handed out
  day TEXT NOT NULL,                      -- the SGT day the item is for
  state TEXT NOT NULL DEFAULT 'ready'
    CHECK (state IN ('ready', 'claimed', 'done', 'stopped', 'unknown', 'withdrawn')),
  outcome TEXT CHECK (outcome IN ('posted', 'not-posted', 'requested', 'member', 'declined', 'questions', 'pages-not-allowed')),
  stop_reason TEXT,
  post_url TEXT,
  live_text_hash TEXT,
  live_text_matches INTEGER CHECK (live_text_matches IN (0, 1)),
  run_id INTEGER,                         -- the run that claimed it
  created_at TEXT NOT NULL,
  claimed_at TEXT,
  finished_at TEXT
);

-- The claim-time caps count claimed items by platform and day, and by run.
CREATE INDEX publish_items_day ON publish_items (day, kind, platform);
CREATE INDEX publish_items_state ON publish_items (state);
CREATE INDEX publish_items_run ON publish_items (run_id);
CREATE INDEX publish_items_ref ON publish_items (kind, ref);
