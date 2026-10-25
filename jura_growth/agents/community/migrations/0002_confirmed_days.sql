-- Day rules are Ting Yu's to confirm (code review 07): rules text that names a
-- day opens no day until he sets them with
-- `jura-growth community set <id> promo_days=... post_days=...`.
-- NULL = not confirmed; 'any' = no day limit; 'none' = no day; else 'mon,tue,...'.

ALTER TABLE community_groups ADD COLUMN promo_days_confirmed TEXT;
ALTER TABLE community_groups ADD COLUMN post_days_confirmed TEXT;
