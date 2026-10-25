# 05 — BP-05 community posts as the Jura Page, on confirmed open days only

Status: ready-for-agent
Blocked by: 03, 06, mission-control#05
PRD ticket: BP-05 in `prd-jura-browser-publishing-2026-10-25.md` §5.12 (06 added as an edge by the ticket review; this ticket now follows 06, so its number no longer sorts before its blocker, and the numbers are kept so the BP-05 and BP-06 ids stay stable)
Covers: SC4 (the composer branch of AC-P4.3), SC5 (lines 8 to 10, end to end), SC6 (AC-P6.2), SC11 (the Page in groups)

## What to build

An approved community post goes out in a Facebook group as the Jura Facebook Page, only in a group joined as the Page (which 06 makes possible), with its rules and open days confirmed by Ting Yu through a `group-rules` decision, and only on a day those rules leave open. A composer that offers no way to act as the Page records `pages-not-allowed` through 06's handler. A removal notice or admin warning stops the run and also marks the group removed.

## What to change

- The community-post section of `prompts/publish.md`: open the group, check the Page is the posting identity at the composer, post, read back, `publish done`; at a composer with no way to act as the Page, call `publish done <id> --outcome pages-not-allowed` (06 owns that handler).
- A removal or admin warning in a group runs `community removed` for that group as well as `publish stopped`.
- `config/community.yaml`: `post_as` becomes "the Jura Solutions Facebook Page"; the community plan prompt writes drafts in the Jura voice ("we"), per `design-system/README.md` §3. `docs/community.md` follows BP §3.3.
- The group's hosts in the domain rules, if 01's U18 showed they differ from the Page's.

## Acceptance criteria

- [ ] **AC-P6.2** Given a removal notice or an admin warning in a group, then `community removed` also
  runs for that group, so it stays skipped.
- [ ] **AC-P4.3 (owned by 06), the composer branch.** A post composer that offers no way to act as the Jura Page leads the run to record `--outcome pages-not-allowed`, with the group effects 06's handler applies.
- [ ] **AC-P11.1 (owned by 03), the Page in groups.** The run checks the Jura Page is the group identity before any typing.
- [ ] **AC-P5.1 lines 8, 9 and 10 (owned by 02) end to end**, through a fake-`claude` run, with the group's days confirmed through mission control's `group-rules` decision.
- [ ] AC-M15.1 (owned by mission-control#01) still holds.

## Done when

The agent's part is done when every criterion above passes, `uv run pytest` passes, and the report is in. The ticket closes after Ting Yu's live step U14 (an approved post in a test group on an open day; the same item on a closed day refused by `publish next`), recorded in `reviews/qa-05.md`. Then wait for go-ahead.

## Pointers

- PRD: BP §3.3 (community rows), §4.3, §4.5, §4.6, §5.5 (`community-post` row); MC §5.7 (`group-rules`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T8
- `.scratch/mission-control/reviews/functional.md`: B5
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.2 (AC-P4.3, AC-P5.1, AC-P6.2, AC-P11.1), §7 (U14), §3 (D10 community), §11.2 row BP-05
- `jurasolutions/prd/pending/prd-jura-community-scout-2026-10-24.md` (superseded in part)
- Code: `jura_growth/agents/community/`, `rules.py` (`day_problem`), `config/community.yaml`, `prompts/`
