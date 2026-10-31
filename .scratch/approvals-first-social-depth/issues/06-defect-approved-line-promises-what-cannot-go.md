# 06: Defect: an approved line can promise a post nothing will make

Status: done
Severity: minor (a false line; nothing posts that shouldn't, and the lapse line that follows is true)
Owner: developer
Found by: QA at f0db1e5, `reviews/qa-final.md`
Failing test: `.scratch/approvals-first-social-depth/issues/test_qa_final_defects.py`, the two tests under "06"

## Steps

**Case 1: the way back, with a card open.**

1. Seed `social-day` as in ticket 05, so two cards are pending.
2. Set Facebook's `publish_mode: draft` in `$UAT/config/social.yaml`.
3. `JURA_GROWTH_NOW=2026-11-10T10:31:00+08:00 uv run python -m tests.uat.seed "$UAT" --scenario decide --approval A-0001 --decision approve --today 2026-11-10`
4. `JURA_GROWTH_NOW=2026-11-10T10:32:00+08:00 uv run jura-growth publish next --json`
5. `JURA_GROWTH_NOW=2026-11-10T18:05:00+08:00 uv run jura-growth digest`

**Case 2: a community post approved after the last publish slot.** A community post's decide-by is 18:00, and the last slot starts at 17:40.

1. `uv run python -m tests.uat.seed "$UAT" --scenario community-plan --today 2026-11-10`
2. `JURA_GROWTH_NOW=2026-11-10T17:50:00+08:00 uv run python -m tests.uat.seed "$UAT" --scenario decide --approval A-0001 --decision approve --today 2026-11-10`

## Expected

No feed line says "It goes out" when nothing can post it (`reviews/test-strategy.md` R6: "no line says 'it goes out' when no slot is left"). `feed_approved` already does this for a paused publisher and for a social post's late replacement.

## Actual

**Case 1.** The feed line says "It goes out on a publish run today, by 18:00 SGT. The run's update here gives the post's address." `publish next` then answers "facebook is in draft mode, so nothing is posted through the browser", which is correct. At 18:05 the feed says "Approved but not used in time." Nobody is told why in between. The digest also says "1 draft waiting in #social-drafts (facebook)", though no hand-post message for that day exists in #social-drafts.

**Case 2.** The feed line says "It goes out on a publish run, inside the posting window." No run is left that day. The fixture's group also has unconfirmed rules, so `publish next` would refuse it at any hour with "the group's rules aren't confirmed by Ting Yu". `group-join`'s line has the same wording.

## Why

- `SocialPost.feed_approved` (`agents/publish/kinds.py`) checks the last run and the pause, but not `switched_off` for a platform in draft mode.
- `_GroupKind.feed_approved` (`agents/publish/group_kinds.py`) only checks the pause.

## Notes

- Nothing posts in either case: AF5 and MC A6 hold. `test_going_back_to_draft_mode_with_a_card_open_posts_nothing_and_the_next_day_is_by_hand` passes, and it doesn't read the line.
- `community.browser` is off in shipped config, so case 2 can't reach Ting Yu until that is switched on. Case 1 is the one he can hit: it follows the documented rollback.
- Test strategy R3 says the card "closes with one line" on the flip. The shipped behaviour keeps it live until 18:05 by design (`kinds.py`: "Draft mode isn't gone: A13 keeps that card live"). I've treated the design as correct and only the promise as wrong.
