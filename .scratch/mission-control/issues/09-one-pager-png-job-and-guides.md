# 09 — MC-09 the one-pager PNG, the 08:00 job and the setup guides

Status: ready-for-agent
Blocked by: 08, 11
PRD ticket: MC-09 in `prd-jura-mission-control-2026-10-25.md` §5.12 (11 added as an edge by the ticket review)
Covers: SC1 (the post, the PNG, the job and the remote request), SC14

## What to build

At 08:00 SGT every day `#mission-control` receives the one-pager with a PNG of the 14-day job-by-day grid, and Ting Yu can ask for it again from Discord with `/growth one-pager`. Before it builds, the job writes the day's lapses on its own writable connection. The setup guides tell Ting Yu which two Discord channels to add and that the Cowork morning-brief line can go.

## What to change

- **Move the Chrome render helper into the core.** `design_system()`, `chrome_path()`, `_chrome()`, `screenshot()` and `png_size()` move from `agents/social/render.py` into `jura_growth/images.py`, with the Chrome path passed in explicitly; `agents/social/render.py` then calls the core helper, as an expand and contract inside this ticket. `tests/test_social_render.py` passes unchanged, and `one_pager.py` imports no agent.
- The grid PNG: one cell per job per day, scout-send and publish collapsed, a legend, every status shown as text or a glyph as well as colour. Built from `design-system/` tokens and fonts through the core helper; no second icon or font set.
- `jura-growth one-pager` posts to `#mission-control` with dedupe off; the PNG rides on the last piece.
- `config/settings.yaml`: the `mission-control` channel, and the `one-pager` job (agent `digest`, daily 08:00) directly after `digest`. The job runs `approvals.expire_due()` on the runner's writable connection before the read model runs (MC §4.2, A17). 01's generated `may_use` test now covers it.
- `one-pager` on the remote allowlist from 11, in its sorted place, with its row in `docs/dispatch-contract.md`.
- Setup guides drafted in this ticket as `.scratch/mission-control/setup/discord.md` (names `#mission-control` and `#approvals`, with `#approvals` notifying on all messages) and `.scratch/mission-control/setup/morning-brief.md` (tells Ting Yu to remove the Cowork line). The release persona copies them to `jurasolutions/outputs/growth/setup/` after the merge; this ticket never writes there.

## Acceptance criteria

- [ ] **AC-M1.1** Given 2026-11-10 08:00 and webhooks configured, when the `one-pager` job runs, then
  `#mission-control` receives one message, split only past 2,000 characters, with its sections in
  this order: a header reading "Tue 10 Nov, as of 08:00 SGT", Needs you, Approvals waiting, Today,
  Yesterday, Ask me. One PNG rides on the last piece.
  *Owned here: the full criterion, with the PNG on the last piece. 08 proved the text.*
- [ ] **AC-M1.6** When Ting Yu sends `/growth one-pager` twice in a minute, then two messages post
  (dedupe off) and each call answers "posted to #mission-control".
  *Owned here: through `jura-growth one-pager` and through `jura-growth remote -- one-pager`.*
- [ ] **AC-M14.1** Then `outputs/growth/setup/morning-brief.md` tells Ting Yu to remove the line, the
  17:30 digest still writes `daily-summary.json`, and `outputs/growth/setup/discord.md` names
  `#mission-control` and `#approvals`, with `#approvals` notifying on all messages.
  *Here: the drafts in `.scratch/mission-control/setup/`, and the digest still writing `daily-summary.json`. The copy to `outputs/growth/setup/` is checked at release.*
- [ ] **X14, the PNG.** A valid PNG of the expected size, one cell per job per day with scout-send and publish collapsed, design-system tokens only, each status as text or a glyph as well as colour (checked on the grid HTML before rendering).
- [ ] **X12 (one-pager job).** The 08:00 job calls `expire_due()` before it builds.
- [ ] AC-M1.5 (owned by 01) covers the new `one-pager` job.
- [ ] `tests/test_social_render.py` passes unchanged, and `grep jura_growth.agents. jura_growth/one_pager.py jura_growth/images.py` finds nothing.
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Ting Yu's U3, U4 and U5 (and reinstalling the schedule, which is his) are under ticket 13. Then wait for go-ahead.

## Pointers

- PRD: MC SC1, SC14, §4.1 (design system), §4.2, §5.4, §5.3 (`one_pager.py`, `config/settings.yaml`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T4, T6, N4, N8
- `.scratch/mission-control/reviews/technical-v2.md`: B6, N12
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M1.1, AC-M1.6, AC-M14.1), §4.3 (X12, X14), §11.2 row MC-09
- `jurasolutions/design-system/SKILL.md`, then `README.md` (read-only)
- Code: `jura_growth/agents/social/render.py`, `jura_growth/images.py`, `discord.py`, `digest.py`, `remote.py` (from 11), `config/settings.yaml`
