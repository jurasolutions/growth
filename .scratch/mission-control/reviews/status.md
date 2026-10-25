Feature: mission-control   Route: L   Phase: tickets cut and revised after the tech lead's ticket review (G3 pending)   As of: 2026-10-25 SGT
Next decision for the user: G3, approve the ticket breakdown in `issues/`, and answer the branch question below. Before any build: the blocker-fix PR's G4.

Precondition for every agent ticket, in order:
  1. `crew/growth-blocker-fixes` (PR #1) merged into `main` through its G4.
  2. The conductor creates `crew/mission-control` from that `main`, and its first commit adds `CONTEXT.md`, `docs/adr/`, `.scratch/mission-control/` and `.scratch/browser-publishing/` (all untracked today) before any worktree (tickets-technical T11).
No `crew/mission-control` branch exists yet.

Frontier (ready to start): none today. 01 runner and guards and 02 redaction start as soon as the precondition holds.

In flight: none.

Blocked (wave once the precondition holds — blocked by — what would clear it):
  - 01 MC-01 runner and guards — w1 — the precondition — PR #1 merged, shared files committed
  - 02 MC-02 redaction — w1 — the precondition — as above
  - 04 MC-04a approvals core — w2 — 01, 02 — both merged
  - 07 MC-07 slot classifier — w2 — 01 — 01 merged
  - 04b MC-04b Terminal decisions and cards — w3 — 04 — 04 merged
  - 08 MC-08 read model and one-pager text — w3 — 07, 04 — both merged
  - 03 MC-03 run updates — w3 — 01, 02, 04 — all merged
  - 06 MC-06 outreach gate — w4 — 04b — 04b merged
  - 11 MC-11a remote core — w4 — 04b — 04b merged
  - 10 MC-10 app ideas to handoff — w4 — 04b, 08 — both merged
  - 05 MC-05 `group-rules` kind — w5 — 04b, 11 — both merged
  - 09 MC-09 one-pager PNG, job and guides — w5 — 08, 11 — both merged
  - 10b MC-10b app release — w5 — 10 — 10 merged
  - 12 MC-11b remote apps commands — w6 — 11, 10b — both merged
  - 13 Ting Yu: Discord channels and Terminal checks (ready-for-human) — w6 — 03, 04b, 09 — all merged
  - 14 Ting Yu: open the Mac to Dispatch (ready-for-human) — from w5 — 11; Dispatch D1 to D4, D8, D9 — 11 merged and Dispatch deployed on its always-on machine
  - 15 Ting Yu: buttons, then live outreach (ready-for-human) — from w6 — 06, 14; Dispatch D5 — those done, then U17 passed
  - 16 Ting Yu: previews and first app build (ready-for-human) — from w7 — 12, 14; Dispatch D6, D8; `landing-page` toolbox on its `main` — all of those done

Done: none.

Critical path to the first real use: 01 and 02, then 04, 04b, 11, 09, then 13 (Terminal decisions, run updates and the one-pager on Ting Yu's phone). Six agent waves, then Ting Yu's checks.
Parallel lanes: w1 01, 02; w2 04, 07; w3 04b, 08, 03; w4 06, 11, 10, browser-publishing#02; w5 05, 09, 10b, browser-publishing#02b, #03; w6 12. Shared files in each wave have one owner per behaviour (tickets-technical "Files shared by parallel tickets" and N8 anchors).

Risks:
  - The blocker-fix PR can't land: `gh auth login` isn't done on this Mac, and PR #1 waits for its G4 — likely / high (blocks everything) — Ting Yu — `gh auth login`, then the release gate
  - Worktrees miss the untracked shared files, so 01 can't accept ADR 0001 and no developer can read their ticket — certain if skipped / high — conductor — the shared-files commit before any worktree (precondition 2)
  - Dispatch is not deployed and its always-on machine is not chosen, so phone decisions and live outreach wait — likely / medium — Ting Yu — every kind is decided from Terminal meanwhile; outreach stays in shadow (TY3)
  - Reverting past 06 restores a `send.py` with no gate — unlikely / high — release — set `outreach.mode: shadow` before any rollback past 06 (in 06's release note)
  - Setup guides are drafted in `.scratch/mission-control/setup/` and only copied to `outputs/growth/setup/` at release, so a missed copy leaves Ting Yu without a guide — possible / low — release persona — the copy is a release-checklist item (tickets-technical N4)

Open questions:
  - G3: approve the revised breakdown (18 tickets here, 7 in browser-publishing)? Recommended: yes.
  - Branch (tickets-technical T11): build both features on one integration branch, `crew/mission-control`, with ticket branches `crew/mission-control-NN` and `crew/mission-control-bpNN`? Recommended: yes; at G4 you still choose one PR or two cut at a merge point, and nothing in browser publishing posts until you set a platform to `browser` and reinstall the schedule.
