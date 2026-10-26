-- Browser publishing (prd-jura-browser-publishing-2026-10-25.md §4.3, §5.6; BP-02b).
--
-- Joins and group posts go out as the Jura Facebook Page, and only in groups
-- that allow Pages. This migration only adds columns: it changes no existing
-- row (X7).
--
-- `joined_as` is read, never written: it is `joined_as_set` when that is
-- recorded, and otherwise what the legacy `joined` flag means. A group joined
-- before this build (`joined = 1`) was joined by Ting Yu as himself, so it
-- reads as `profile`; one never joined reads as `none`.
-- `pages_allowed`: `unknown` until a run sees the join or post screen; `no`
-- means only personal profiles can join or post there, so the group is skipped.
-- `join_status`: what a join item's run recorded (`requested`, `member`,
-- `declined`); NULL until then.

ALTER TABLE community_groups ADD COLUMN joined_as_set TEXT
  CHECK (joined_as_set IN ('none', 'profile', 'page'));
ALTER TABLE community_groups ADD COLUMN joined_as TEXT GENERATED ALWAYS AS
  (coalesce(joined_as_set, CASE WHEN joined = 1 THEN 'profile' ELSE 'none' END)) VIRTUAL;
ALTER TABLE community_groups ADD COLUMN pages_allowed TEXT NOT NULL DEFAULT 'unknown'
  CHECK (pages_allowed IN ('unknown', 'yes', 'no'));
ALTER TABLE community_groups ADD COLUMN join_status TEXT
  CHECK (join_status IN ('requested', 'member', 'declined'));
