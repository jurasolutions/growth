# 13 — Ting Yu: add the two Discord channels, retire the morning-brief line, check from Terminal

Status: ready-for-human
Blocked by: 03, 04b, 09
PRD source: MC SC1, SC3, SC14, §4.6 (Terminal decisions), §5.12 ("until then every kind is decided from Terminal"); not a §5.12 ticket, because only Ting Yu can do it
Covers: test strategy v3 §7 U1 to U5; `uat.md` Part A

## What to do

These steps need Ting Yu's own Discord server, his `.env`, his launchd schedule and his phone, so no agent can do them. They are the first time mission control runs for real, decided from Terminal, before Dispatch exists.

1. Follow `outputs/growth/setup/discord.md` (drafted in 09, copied there at release): add `#mission-control` and `#approvals` in Jura HQ and set `#approvals` to notify on all messages.
2. Store the two webhook URLs in `repos/growth/.env` yourself. If you'd like a guided walk-through, ask for the `wizard`; it prompts you without the values ever entering a file, log or chat. If Dispatch later needs to own the `#approvals` webhook for buttons, that swap happens in ticket 15.
3. After the merge, run `uv sync` and `jura-growth schedule install` (the job list gains `one-pager`).
4. Remove the morning-brief line in Cowork, as `outputs/growth/setup/morning-brief.md` says.
5. Run the checks below and record each as pass or fail in `.scratch/mission-control/reviews/qa-NN.md`.

## Checks

- [ ] **U1.** `jura-growth approvals`, `approve` and `skip` on a request raised in shadow or by a test PRD. Decisions show `terminal:<user>`, and approving needs the six-character code from the card.
- [ ] **U2.** After the next real social run, its run update appears in `#social-drafts` with the approval ids it raised.
- [ ] **U3.** `jura-growth one-pager` once from Terminal, then the next 08:00 one-pager read on your phone, including the grid image.
- [ ] **U4.** The Cowork morning-brief line is gone, and the 17:30 digest still writes `daily-summary.json`.
- [ ] **U5.** A request in `#approvals` reaches your phone as a notification.

## Pointers

- `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U1 to U5)
- `.scratch/mission-control/uat.md` "Before you start" and Part A
- `.scratch/mission-control/setup/discord.md`, `.scratch/mission-control/setup/morning-brief.md` (from 09)
- `docs/agents/crew.md` (running `jura-growth schedule install` is Ting Yu's, never an agent's)
