# 17 — The UAT seed for the outreach steps

Status: ready-for-agent
Blocked by: 06
PRD source: MC §5.3 (`tests/uat/seed.py`, the UAT harness, functional S15); not a §5.12 ticket. Follow-up from the QA lead's `uat.md` revision for Discord-only decisions (2026-10-27)
Covers: test strategy v3 §4.3 X13; `uat.md` "Seed data" S1, S3, S4, S9, S10, and Part A step A4 and Part B step B6

## What to build

`uat.md` now makes every decision in `#approvals` through Dispatch, on the real clock, and its
outreach steps follow ticket 06. The seed (`tests/uat/seed.py`, from 04b) can't yet set any of that
up. This ticket adds what the outreach steps need, so Ting Yu can run Part A's email gate and Part B's
requeue against a temp folder.

## What to change

- **`--today <date>`** on `tests.uat.seed`: every seeded row is dated from that day (default: today
  in SGT), instead of the fixed Tue 2026-11-10. `--today` refuses a day that isn't a business day.
  The history's shape stays the same: eight days back, one business day's scout-send traces missing
  two slots with a quiet run six minutes late, and the previous business day for lead 233. This is
  needed because Dispatch decisions are stamped with the real clock (ADR 0004 as amended 2026-10-26),
  so seeded deadlines must line up with today.
- **`outreach-live` (S3).** Writes `$UAT/config` so that `outreach.mode: live` has every live
  pre-condition met except the buttons switch: warm-up day 3 (cap 5), Resend pointed at the stub
  through `JURA_GROWTH_RESEND_BASE_URL`, and `approvals.discord_buttons: false`, so A4's first check
  sees "approval buttons not set up". Never writes the real `config/`.
- **S4's requests come from the outreach commands.** The seed never inserts approval rows. A test
  proves that after `base` and `outreach-live`, the first `send-due` of the day raises
  exactly 5 `outreach-email` requests for S4 (lead 233 included, as due), leave the rest "waiting
  for a request slot", and post their cards.
- **`edit-draft --lead <id>` (S9).** Changes that lead's queued `draft_body` (as a hand edit would),
  so the next read or claim supersedes its request and raises a new one. Refuses a lead with no
  queued email.
- **`shadow-trial` (S10).** Seeds 40 shadow-trial emails in the shape `requeue-shadow` reads, for
  B6.
- Each scenario refuses a non-temp folder, like `base`, and the Resend stub stays refused for one.

## Out of scope

The other scenarios `uat.md` names belong to their kinds' tickets: `new-app-prd` (10),
`note-rules --group <id>` (05), `social-approved` and `claimed-not-closed` (browser-publishing#02),
`community-plan` (browser-publishing#02b). The UAT route through Dispatch (a UAT-only key whose
forced command fixes the UAT folder variables) is waiting on the tech lead and isn't seed work.

## Acceptance criteria

- [ ] `--today` on a business day dates every `base` row from it; on a weekend or public holiday it
  refuses and seeds nothing.
- [ ] After `base` and `outreach-live`, `outreach send-due` refuses with "approval buttons not set
  up"; after `approvals.discord_buttons: true` in the temp config, the first `send-due`
  raises exactly 5 requests and posts 5 cards (AC-M8.2 at the harness's data).
- [ ] `edit-draft --lead 240` after lead 240's request is approved makes the next `send-due`
  supersede it, raise a new request, and send nothing for lead 240.
- [ ] `shadow-trial` then `requeue-shadow` in live mode raises requests only up to today's remaining
  quota (AC-M8.13 at the harness's data).
- [ ] Every scenario refuses a non-temp folder; the real `config/` and live `data/growth/` are
  unchanged (stat snapshot).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion passes, `uv run pytest` passes, and Ting Yu can run `uat.md` A4 and B6 from the seed
alone. Then wait for go-ahead.

## Pointers

- `.scratch/mission-control/uat.md` "Before you start", "Seed data", A4, B6
- `tests/uat/seed.py` (04b); `tests/resend_stub.py` and `JURA_GROWTH_RESEND_BASE_URL` (06)
- `.scratch/mission-control/issues/06-outreach-gate.md`; `reviews/test-strategy-v3.md` §3 D8, §4.3 X13
