# 06 — BP-06 group joins as the Jura Page, with approved membership answers

Status: ready-for-agent
Blocked by: 03, 02b, mission-control#05
PRD ticket: BP-06 in `prd-jura-browser-publishing-2026-10-25.md` §5.12 (02b from the ticket review's split)
Covers: SC4

## What to build

The Monday community run proposes joins for good-fit groups, up to three a week, and each approved join goes in as the Jura Facebook Page. If the group asks membership questions, the run submits nothing, records the questions, and the drafted answers become a second item with their own approval; only after that is approved does a later run submit exactly those answers. A group that only lets personal profiles join or post is skipped for good, through one handler for every item kind. Rules seen inside a group are recorded and raise a `group-rules` request, so Ting Yu can confirm them and the open days.

## What to change

- `community propose-join` (from 02b) added to the Monday community run's prompt and permissions; the research job still never fetches Facebook (ticket 02 stands).
- The join section of `prompts/publish.md`: join as the Page; on a questions form, close it without submitting and call `publish done <id> --outcome questions --file q.json`; for an answers item, submit exactly the approved answers.
- `publish done --outcome questions`: brand-gate the answers and raise the answers item and its request; it neither alerts nor pauses.
- `publish done --outcome requested|member|declined` on a join: `join_status`, and on `member`, `joined_as = page`.
- **`publish done --outcome pages-not-allowed` for every item kind** (this ticket owns the handler; 05 adds only the composer branch of the prompt): `pages_allowed = no`, `fit = skip` ("only personal profiles can join or post"), every pending item for the group superseded, never proposed again.
- `publish note-rules <group-id> --file <f>`: records rules seen inside the group and raises a `group-rules` request (mission-control#05's kind).
- `docs/community.md` for joins.

## Acceptance criteria

- [ ] **AC-P4.1** Given an approved join and a group with no questions that offers the Jura Page as the
  joining identity, when the run joins, then `publish done <id> --outcome requested` (or `member`)
  is recorded, `join_status` is set, and no second request is raised.
- [ ] **AC-P4.2** Given a group that asks questions, when the run reaches the form, then it submits
  nothing, closes the form, and records `publish done <id> --outcome questions --file q.json`,
  which does not alert or pause. The answers are brand-gated, a second `group-join` item and request
  post with the questions and answers, and only after that is approved does a later run submit
  exactly those answers.
- [ ] **AC-P4.3** Given a group whose join or post screen offers no way to act as the Jura Page, when
  the run sees it, then it records `--outcome pages-not-allowed`; the group gets `pages_allowed =
  no` and `fit = skip` ("only personal profiles can join or post"); every pending item for that
  group is superseded; and it is never proposed again.
  *Owned here: the handler for every item kind, and the join-screen branch. 05 adds the composer branch.*
- [ ] **AC-P4.4** Given `join_status = member` from a join item, then `joined_as = page` is set. The
  group's rules and open days still need a `group-rules` decision.
- [ ] **X10.** `publish note-rules` raises one `group-rules` request for the rules text seen, and never for researched rules.
- [ ] **AC-P5.1 line 4 (owned by 02) end to end.** A fourth join in the ISO week (SGT) is refused, and the Monday run proposes no more than the weekly cap allows.
- [ ] **AC-P9.1 (owned by 03) still holds.** `community` keeps its Facebook `WebFetch` denies and gains no browser tools.
- [ ] AC-M15.1 (owned by mission-control#01) still holds.

## Done when

The agent's part is done when every criterion above passes, `uv run pytest` passes, and the report is in. The ticket closes after Ting Yu's rehearsal R5 (the membership questions page) and live step U15 (an approved join with questions submits only the approved answers; a group without questions is requested on its single approval), recorded in `reviews/qa-06.md`. Then wait for go-ahead.

## Pointers

- PRD: BP §4.3, §4.5, §5.4, §5.5 (`group-join` row), §5.7; MC §5.7 (`group-rules`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T8, Q5
- `.scratch/mission-control/reviews/functional.md`: S16
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.2 (AC-P4.1 to AC-P4.4), §4.3 (X10), §7 (R5, U15), §3 (D10), §11.2 row BP-06
- Code: `jura_growth/agents/community/`, `agents/publish/`, `prompts/`, `tests/test_community_fetch_block.py`
