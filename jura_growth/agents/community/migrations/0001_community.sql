-- Community scout (prd-jura-community-scout-2026-10-24.md §5.5).

CREATE TABLE community_groups (
  id INTEGER PRIMARY KEY,
  channel TEXT NOT NULL DEFAULT 'facebook', -- facebook, linkedin, telegram, whatsapp, sbf, asme, event, forum, other
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,                -- utm_campaign value for this group
  url TEXT NOT NULL,                        -- the group's own link; recorded, never fetched
  url_key TEXT NOT NULL UNIQUE,             -- normalised url, for dedupe
  audience TEXT,
  size_hint TEXT,
  active_hint TEXT,
  promo_rules TEXT,
  fit TEXT NOT NULL,                        -- good fit, possible, skip
  fit_reason TEXT NOT NULL,
  joined INTEGER NOT NULL DEFAULT 0,
  rules_confirmed INTEGER NOT NULL DEFAULT 0,
  removed INTEGER NOT NULL DEFAULT 0,       -- 1 after an admin removal or warning: skip for good
  notes TEXT,
  source_urls_json TEXT NOT NULL DEFAULT '[]', -- non-Facebook pages the facts came from
  last_posted_at TEXT,
  run_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (fit IN ('good fit', 'possible', 'skip')),
  CHECK (joined IN (0, 1) AND rules_confirmed IN (0, 1) AND removed IN (0, 1))
);
CREATE INDEX community_groups_fit ON community_groups (fit, joined);

CREATE TABLE community_posts (
  id INTEGER PRIMARY KEY,                   -- the checklist's item id
  group_id INTEGER REFERENCES community_groups (id),
  week TEXT NOT NULL,                       -- 2026-W44
  planned_day TEXT,                         -- YYYY-MM-DD; NULL for reply ideas
  kind TEXT NOT NULL,                       -- post, reply_idea
  question TEXT,                            -- reply ideas: the common question it answers
  text TEXT NOT NULL,
  image_path TEXT,
  qa_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'planned',   -- planned, posted, skipped
  posted_url TEXT,
  posted_at TEXT,
  posted_via TEXT,                          -- command, checklist
  run_id INTEGER,
  created_at TEXT NOT NULL,
  CHECK (kind IN ('post', 'reply_idea')),
  CHECK (status IN ('planned', 'posted', 'skipped'))
);
CREATE INDEX community_posts_week ON community_posts (week, kind);
CREATE INDEX community_posts_group ON community_posts (group_id, planned_day);
