-- Social content agent (social PRD §5.4).

-- One row per platform variant delivered to #social-drafts.
CREATE TABLE social_posts (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,                     -- the SGT day the post is for
  theme TEXT NOT NULL,
  platform TEXT NOT NULL,                 -- linkedin, facebook, instagram
  text TEXT NOT NULL,
  image_paths TEXT NOT NULL DEFAULT '[]', -- JSON list
  source_urls TEXT NOT NULL DEFAULT '[]', -- JSON list, as written in sources.md
  qa_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'skipped')),
  published_url TEXT,
  published_at TEXT,
  tool_slug TEXT,                         -- the toolbox tool featured, if any
  run_id INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT
);
-- caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY = 1
CREATE UNIQUE INDEX social_posts_date_platform ON social_posts (date, platform);
CREATE INDEX social_posts_tool ON social_posts (tool_slug, date);

-- `jura-growth social skip <date> <platform>`. Recorded even before the draft
-- exists, so a skip set the night before holds.
CREATE TABLE social_skips (
  date TEXT NOT NULL,
  platform TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (date, platform)
);

-- Each `social submit` that reached the brand gate, and each "No draft today".
-- The second gated submission of a day is final (one regeneration).
CREATE TABLE social_submissions (
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  status TEXT NOT NULL, -- retry, delivered, partial, dropped, no-draft
  theme TEXT,
  reason TEXT,
  issues_json TEXT NOT NULL DEFAULT '{}',
  run_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX social_submissions_date ON social_submissions (date);
