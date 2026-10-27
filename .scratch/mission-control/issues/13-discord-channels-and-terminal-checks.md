# 13 — Ting Yu: add the two Discord channels, retire the morning-brief line, check that Terminal can't decide

Status: ready-for-human
Blocked by: 03, 04b, 09
PRD source: MC SC1, SC3, SC14, SC7 and §4.6 A8 (amended 2026-10-26: no Terminal decisions), §5.12; not a §5.12 ticket, because only Ting Yu can do it
Covers: test strategy v3 §7 U1 to U5; `uat.md` Part A

## What to do

These steps need Ting Yu's own Discord server, his `.env`, his launchd schedule and his phone, so no agent can do them. They are the first time mission control runs for real, before Dispatch exists. *Amended 2026-10-26:* nothing can be decided before Dispatch exists, because Terminal decisions are off, so requests raised now post and then lapse unanswered.

1. Follow `outputs/growth/setup/discord.md` (drafted in 09, copied there at release): add `#mission-control` and `#approvals` in Jura HQ and set `#approvals` to notify on all messages.
2. Store the two webhook URLs in `repos/growth/.env` yourself. If you'd like a guided walk-through, ask for the `wizard`; it prompts you without the values ever entering a file, log or chat. If Dispatch later needs to own the `#approvals` webhook for buttons, that swap happens in ticket 15.
3. After the merge, run `uv sync` and `jura-growth schedule install` (the job list gains `one-pager`).
4. Remove the morning-brief line in Cowork, as `outputs/growth/setup/morning-brief.md` says.
5. Run the checks below and record each as pass or fail in `.scratch/mission-control/reviews/qa-NN.md`.

## Checks

- [ ] **U1** *(amended 2026-10-26)*. On a request raised by a test PRD: `jura-growth approvals` lists it; `jura-growth approve A-nnnn` and `jura-growth skip A-nnnn` each refuse with a pointer to `#approvals`; the request is still pending afterwards (`jura-growth approvals` shows it again); and its card in `#approvals` shows no code.
- [ ] **U2.** After the next real social run, its run update appears in `#social-drafts` with the approval ids it raised.
- [ ] **U3.** `jura-growth one-pager` once from Terminal, then the next 08:00 one-pager read on your phone, including the grid image.
- [ ] **U4.** The Cowork morning-brief line is gone, and the 17:30 digest still writes `daily-summary.json`.
- [ ] **U5.** A request in `#approvals` reaches your phone as a notification.

## Pointers

- `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U1 to U5)
- `.scratch/mission-control/uat.md` "Before you start" and Part A
- `.scratch/mission-control/setup/discord.md`, `.scratch/mission-control/setup/morning-brief.md` (from 09)
- `docs/agents/crew.md` (running `jura-growth schedule install` is Ting Yu's, never an agent's)

## Comments

### 2026-10-26T21:02+0800 conductor

Ting Yu turned Terminal decisions off (Discord only; PRD amended before §6). Drop the Terminal-approval checks from this ticket and check instead that `jura-growth approve` and `skip` refuse with a pointer to #approvals.
