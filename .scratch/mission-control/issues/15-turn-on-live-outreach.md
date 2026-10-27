# 15 — Ting Yu: turn on the Approve and Skip buttons, check them, then turn on live outreach

Status: ready-for-human
Blocked by: 06, 14; and, outside this repo, Dispatch D5 (Approve and Skip buttons on each card in `#approvals`)
PRD source: MC SC8 (AC-M8.11), §5.1 TY3, §5.8, §5.12 ("Live outreach needs MC-06, D5 and `approvals.discord_buttons: true`"); not a §5.12 ticket, because only Ting Yu can do it
Covers: test strategy v3 §7 U17 and U6; `uat.md` Part B (buttons) and Part E

## What to do

Ting Yu decided that outreach stays in shadow mode until the Dispatch buttons work (TY3). Buttons can appear only if growth sends them, and only a webhook owned by the Dispatch application accepts them, so the steps go in this order.

1. Dispatch creates the `#approvals` webhook it owns. Store it as `DISCORD_WEBHOOK_APPROVALS` in `repos/growth/.env` yourself (the `wizard` can guide you).
2. Set `approvals.post_buttons: true` in `config/settings.yaml`, so cards carry Approve and Skip.
3. Run U17 below. A `group-rules` card has no buttons, by design.
4. Only when U17 passes, set `approvals.discord_buttons: true`, then `outreach.mode: live`. `jura-growth status` should list no live problems.
5. Run U6, and record each check in `.scratch/mission-control/reviews/qa-NN.md`.

Rollback: set `outreach.mode: shadow` before reverting any merge past ticket 06 (MC §5.8).

## Checks

- [ ] **U17.** Approve and Skip on a card record the decision with `discord:<your id>` and edit the card's first line in place.
- [ ] Before step 4, `outreach.mode: live` is refused with "approval buttons not set up"; after it, accepted.
- [ ] **U6.** One real outreach email approved in live mode sends at the next slot inside the window, and only then.

## Pointers

- PRD: MC SC8, §4.8 (D5), §5.8
- `.scratch/mission-control/reviews/tickets-technical.md`: T10
- `.scratch/mission-control/uat.md` Parts B and E; `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U17, U6)
