# 03 — MC-03 run updates for scout, social, community and app-factory

Status: ready-for-agent
Blocked by: 01, 02, 04
PRD ticket: MC-03 in `prd-jura-mission-control-2026-10-25.md` §5.12 (04 added as an edge by the ticket review)
Covers: SC3

## What to build

Every run of scout-research, social, community and app-factory, whether ok, failed or skipped, posts exactly one run update to that agent's own Discord channel, naming the approval requests the run raised, so Ting Yu knows each job ran and what it made without waiting for the digest. A PAUSE-file skip posts nothing, a lock skip posts without opening `growth.db`, and a failed Discord post never changes the run.

## What to change

- Fill in `jura_growth/run_update.py` (01 created it and wired the runner's calls; this ticket doesn't touch `runner.py`). It builds one run update in the format in MC §5.5 and posts it. It asks the plug-in's `run_update(conn, run) -> lines | None`; `None` posts nothing. Errors are logged and never reach the run's outcome. On the lock skip `conn` is `None`, so it posts without the database and goes to the outbox if Discord is down.
- "Waiting for you: A-nnnn …" lists the requests the run raised, through 04's `approvals.raised_by(conn, run_id)`. Tested with 04's fake kind; the "(social posts)" wording is checked again in browser-publishing#02.
- `run_update()` in each of the four plug-ins (scout, social, community, apps), placed after `digest()`: the "Produced:" lines.
- `run_update: true` in `config/settings.yaml` on exactly scout-research, social, community and app-factory.
- Model-written summaries are redacted, cut to 300 characters and posted inside a quote block, with `discord.post()`'s existing `suppress_embeds` on (no `discord.py` change).
- Call 02's `assert_clean` over run updates from this ticket's own test file.

## Acceptance criteria

- [ ] **AC-M3.1** Given a social run that is ok at 07:00, lasts 4 min 12 s, costs US$0.41 and raises
  A-0153 to A-0155, when it finishes, then `#social-drafts` gets exactly one message whose first
  line is `**social** · ok · 07:00 SGT · 4m 12s · US$0.41 · run <id>`, then a quoted summary of
  at most 300 characters, a "Produced:" line, and "Waiting for you: A-0153, A-0154, A-0155 (social
  posts)".
- [ ] **AC-M3.2** Given social paused by hand, when the 07:00 slot fires, then one message reads
  "skipped: paused by hand".
- [ ] **AC-M3.3** Given a PAUSE file, when the 07:00 slot fires, then no run update posts and the next
  one-pager lists the PAUSE file under Needs you.
  *Here: no run update posts. The one-pager's PAUSE-file line is 08's.*
- [ ] **AC-M3.4** Given the previous social run still holds its lock, when the next slot fires, then
  one run update reads "skipped: previous run still going", posted without opening `growth.db`,
  and goes to the outbox if Discord is down.
- [ ] **AC-M3.5** Given community fails with a timeout, when it finishes, then one run update gives
  the redacted error in one line and `#alerts` gets its usual post.
- [ ] **AC-M3.6** Given the `#social-drafts` webhook returns 500, or the plug-in's `run_update()`
  raises, when the run finishes, then the run's status, its row and the auto-pause counter are the
  same as with Discord up, and the outbox gains the message (or the error is logged).
- [ ] **AC-M3.7** Given a scout-send, scout-sync, digest, heartbeat, backup or one-pager run, when it
  finishes, then no run update posts; `run_update: true` is set on exactly the four agents' jobs.
- [ ] The sweep plants secrets and personal data in a summary, an error and a transcript, and none reaches the Discord double or the outbox (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Ting Yu's U2 is under ticket 13. Then wait for go-ahead.

## Pointers

- PRD: MC SC3, §4.3, §5.5, §5.3 (`run_update.py`, the four plug-ins, `config/settings.yaml`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T3, T4, N8
- `.scratch/mission-control/reviews/technical-v2.md`: N7
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M3.1 to AC-M3.7), §3 (H hostile text), §11.2 row MC-03
- `CONTEXT.md` (Run update, Channel)
- Code: `jura_growth/run_update.py` (from 01), `discord.py`, `agents/*/__init__.py`, `tests/test_discord_down.py`

## Comments

### 2026-10-25T19:46+0800 conductor: from the ticket 01 review

- A NothingToDo precheck hands run_update `Outcome("ok", reason)`, but a quiet nothing-to-do run has no summary (runner.py:110 vs :143). Decide what the run update says for it.
- Exception paths in the runner skip run_update (existing behaviour). Decide whether a crashed run still posts a run update.
See reviews/code-review-01.md, Spec should-fix.
