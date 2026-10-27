# 02b — BP-02b community posts and group joins in the publish queue

Status: ready-for-agent
Blocked by: 02
PRD ticket: BP-02 in `prd-jura-browser-publishing-2026-10-25.md` §5.12, second half: community items (split by the ticket review)
Covers: SC1 and SC3 (community), SC5 (the community caps and checks)

## What to build

Every planned community post in a group joined as the Jura Page, and every proposed join for a good-fit group, becomes a publish item with frozen content and its own approval request, through the queue 02 built. `publish next` refuses a community item unless every group check in BP §4.5 passes: joined as the Page, good fit, not removed, `pages_allowed` not `no`, rules and open days confirmed by Ting Yu, the day open, and every cap with room. It runs beside 03, which needs only 02.

## What to change

- The community plug-in's next migration: `community_groups` gains `joined_as` (`none`, `profile`, `page`), `pages_allowed` (`unknown`, `yes`, `no`) and `join_status`. Groups joined before this build (`joined = yes`) read as `joined_as = profile`.
- The `community-post` and `group-join` kinds (including the membership-answers step), declared by the publish plug-in, with the content, deadlines and actions in BP §5.5.
- Item creation from `community publish-plan` (each planned post in a group joined as the Page) and `community propose-join <group-id>` (good-fit groups not joined as the Page, `pages_allowed` not `no`, up to the weekly join cap). Adding `propose-join` to the Monday run is 06.
- The community checks in `agents/publish/claim.py`, and `config/community.yaml` gaining `browser: false` and `joins_per_week` (may only lower the cap).
- `tests/gate_adapter_community_post.py` and `tests/gate_adapter_group_join.py`. Call mission-control#02's `assert_clean` over community and join cards.

## Acceptance criteria

- [ ] **AC-P3.4** Given a join proposed Mon 2026-11-09, then its decide-by is Sun 2026-11-15 18:00.
- [ ] **AC-P5.1 lines 2 to 5 and 8 to 10 (owned by 02).** A fourth group posted to in ISO week 46 is refused; a second community post on the same day is refused; a fourth join in the week is refused; a group posted to 13 days ago is refused and 14 days ago allowed; a community post on a day the confirmed rules close, in a group with `rules_confirmed = 1` but its days unconfirmed ("open days not confirmed"), or in a group not joined as the Jura Page is refused.
- [ ] **The community switch in AC-P5.3 (owned by 02).** With `community.browser: false`, nothing is claimed and the approval is not consumed.
- [ ] AC-P1.3's supersede rule (owned by 02) holds for a community post's text or group, and for a join's answers.
- [ ] AC-M4.1 to AC-M4.7 (owned by mission-control#04) hold for `community-post` and `group-join`, including the answers step, through their adapter files.
- [ ] **X7.** The `community_groups` migration changes no existing row, and legacy `joined = yes` groups read as `joined_as = profile`.
- [ ] The sweep in `tests/sweep.py` passes over this ticket's messages (the `community-post` and `group-join` cards, including the answers step): no planted secret or personal data reaches the Discord double or the outbox (AC-M11.1 and AC-M12.1, owned by mission-control#02).
- [ ] AC-M15.1 (owned by mission-control#01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Ting Yu can then run the community part of `uat.md` Part C. Then wait for go-ahead.

## Pointers

- PRD: BP §4.3, §4.4, §4.5, §5.4, §5.5 (`community-post`, `group-join` rows), §5.6, §5.10
- `.scratch/mission-control/reviews/tickets-technical.md`: T7, T8, N9
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.2 (AC-P3.4, AC-P5.1), §4.3 (X7), §5, §3 (D10 community), §11.2 row BP-02
- Code: `jura_growth/agents/community/` (`__init__.py`, `groups.py`, `plan.py`, migrations), `agents/publish/claim.py` (from 02), `config/community.yaml`

## Comments

### 2026-10-27T02:22+0800 conductor: UAT seed

Add this ticket's uat.md seed scenario to tests/uat/seed.py SCENARIOS.
