# 05 — Every complaint pauses outreach, and config can't loosen the send limits

Status: ready-for-agent
Blocked by: -
Covers: scout B1, B2, and the send-spacing half of B3

## Problem

1. **A complaint for an already-suppressed address is dropped.** `sync_from_d1` passes on only rows that `suppression.add` newly inserted, and `add` is `INSERT OR IGNORE` on the unique `email_hash`. "Report spam and unsubscribe" is the normal pattern, so the complaint that should pause everything never reaches `apply_rows` (`suppression.py:66-103`, `sync.py:76-111`).
2. **`warmup_start` in the past lifts the day-1 cap to 20** (`send.py:172-177`). Caps may only be lowered by config (`caps.py:1`, `settings.yaml:3-4`, scout PRD §5.3).
3. **Back-to-back `send-due` calls both send.** Each call re-rolls the spacing draw. The runner's lock only covers `jura-growth run`, so the day's quota can go out within minutes.

## What to change

- Act on every D1 event whatever the local suppression state: keep a cursor of the last D1 event processed (row id or `created_at`), and run the complaint and bounce handling even when the address is already suppressed.
- Update the D1 contract in `docs/scout.md` to an append-only table (its own id, one row per event) instead of `email_hash` as primary key. The website change itself happens in the landing-page repo; note it as a follow-up in the PR body.
- Count the warm-up from the later of `warmup_start` and the recorded first live send, so config can only delay it.
- Add a hard minimum gap between live sends to `caps.py` (10 minutes), checked in `send-due` against the last recorded live send.

## Acceptance criteria

- Repros `test_f1_complaint_after_unsubscribe_does_not_pause`, `test_f1b_complaint_after_reply_unsubscribe_does_not_pause`, `test_f2_warmup_start_in_the_past_lifts_day_one_cap_to_20` and `test_f3_back_to_back_send_due_calls_both_send_live` (all in `audit/repro/test_review_repro.py`) become passing regression tests with the corrected expectation.
- A D1 event already processed is never applied twice.
- Shadow mode behaves as today.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-02-scout.md` B1, B2, B3 and "Website dependencies"
- `jura_growth/suppression.py:55-112`, `jura_growth/agents/outreach/sync.py:40-126`, `jura_growth/agents/outreach/send.py:160-260`, `jura_growth/caps.py`, `docs/scout.md:170-200`
