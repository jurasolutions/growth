# 04b — MC-04b Terminal decisions and approval cards

Status: ready-for-agent
Blocked by: 04
PRD ticket: MC-04 in `prd-jura-mission-control-2026-10-25.md` §5.12, second half (split by the ticket review)
Covers: SC5, SC7 (the Terminal origin)

## What to build

Ting Yu can list, approve and skip requests from a real terminal by typing the request's six-character code, and no agent process can. Each request is posted to `#approvals` after its transaction commits, and its card's first line is edited in place when it is decided, lapses or is superseded. The `approvals:` settings block that 06, 10 and 11 read is created here.

## What to change

- `origin.detect()`: the real check from the TTYs, the typed code, `SSH_ORIGINAL_COMMAND` and the process ancestry (`ps -o ppid=,comm=`), refusing any `claude` ancestor.
- CLI: `approvals [kind]`, `approve <A-nnnn> [args] [note]` and `skip <A-nnnn> [note]`, with `--ref`, the closed answer enum, and a refusal whenever `JURA_GROWTH_JOB` is set. `approve` and `skip` take their `Origin` from `origin.detect()` unless the in-process click context carries one (`ctx.obj["origin"]`), which only 11's `remote` dispatcher sets. There is no flag and no environment variable for it.
- `discord.py`: cards posted with `?wait=true` and the message id stored; `edit()` for the first line; a one-line follow-up if an edit fails; the `approvals` channel. Images attach as files, at most ten. Cards mention nobody.
- `approvals.post_unposted(conn)`, run at the end of every raising command and at the heartbeat. Lapses are written at the noon heartbeat and the 23:30 backup job too; the 08:00 `one-pager` job joins them in 09.
- The `approvals:` block in `config/settings.yaml`, directly after `channels:`. 06, 10 and 11 only read it. The deadline settings go in the same block, and each may only shorten a deadline.

  ```yaml
  approvals:
    discord_buttons: false   # buttons checked by Ting Yu (U17); unlocks live outreach (06)
    post_buttons: false      # send Approve/Skip components on cards (11); needs Dispatch's own webhook
    dispatch_builds: false   # Dispatch D6 polls handoffs (10)
  ```
- `tests/uat/seed.py`: seeds the `uat.md` scenarios into a temp data folder and refuses unless `JURA_GROWTH_DATA_DIR` is a temp folder.
- Call 02's `assert_clean` over cards built by the fake kind.

## Acceptance criteria

- [ ] **AC-M5.2** Given the process crashes after the request commits and before the post, when the
  next raising command or the heartbeat runs `post_unposted()`, then the card posts once and
  `posted_at` is set; until then the one-pager lists it as unposted.
  *Here: the posting sweep and `posted_at`. The one-pager's "unposted" line is 08's.*
- [ ] **AC-M5.3** Given A-0412's card posted with its message id stored, when A-0412 is approved,
  skipped, lapses or is superseded, then the card's first line is edited in place ("Approved by Ting
  Yu, 10:02 SGT", "Expired: not approved in time", "Superseded: lead unsubscribed") and no new
  message posts.
- [ ] **AC-M5.4** Given 30 pending requests, when `/growth approvals` runs, then it lists the 15
  soonest to lapse and ends "and 15 more: /growth approvals outreach-email".
  *Here: from Terminal. 11 proves `/growth approvals`.*
- [ ] **AC-M5.5** Given a preview with eleven images, when the card is built, then it is refused
  before posting rather than dropping one.
- [ ] **AC-M7.1** Given `JURA_GROWTH_JOB` set to any configured job, when `approve`, `skip`,
  `approvals` or `remote` runs, then it exits 2 with "refused:"; `headless.NEVER` holds all four
  and the Claude Code rules for every claude job deny them.
  *Here: the code-level refusal for `approve`, `skip` and `approvals`. 01 added the `NEVER` and rules layers; 11 proves it for `remote`.*
- [ ] **AC-M7.2** Given no TTY and no `JURA_GROWTH_JOB`, when `jura-growth approve A-0412` runs, then
  it is refused ("decisions need a terminal or the Dispatch link") and A-0412 stays pending.
- [ ] **AC-M7.3** Given a TTY, when the code typed doesn't match the first six hex characters of
  A-0412's hash, then it is refused; with the right code, it is recorded.
- [ ] **AC-M7.4** Given a TTY and a `claude` process among the ancestors, when `approve` runs, then it
  is refused.
- [ ] **AC-M7.7** Given a fake-claude scenario for each claude job that calls `jura-growth approve
  A-0001` with the runner's environment, then the call exits 2 and A-0001 stays pending.
- [ ] **X12 (heartbeat, backup) and X13 (seed).** The heartbeat and the backup job call `expire_due()`; the heartbeat and every raising command call `post_unposted()`; `tests/uat/seed.py` refuses a non-temp data folder.
- [ ] The sweep over approval cards finds no planted secret or personal data (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `security-review` has run on `origin.py`, `uv run pytest` passes, and the report is in. Ting Yu's U1 and U5 are under ticket 13. Then wait for go-ahead.

## Pointers

- PRD: MC §4.6 A8 to A12, §5.6, §5.3 (`origin.py`, `discord.py`, `cli.py`, `tests/uat/seed.py`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T1, T10, N8
- `.scratch/mission-control/reviews/technical-v2.md`: B2, N2
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M5.2 to AC-M5.5, AC-M7.1 to AC-M7.4, AC-M7.7), §4.3 (X12, X13), §5.3 (G13 layer by layer), §11.2 row MC-04
- `.scratch/mission-control/uat.md` Part A (the seed scenarios)
- `docs/adr/0004-…` (referenced; accepted in 11); `CONTEXT.md` (Human origin, Decision)
- Code: `jura_growth/cli.py`, `discord.py`, `headless.py`, `config/settings.yaml`
