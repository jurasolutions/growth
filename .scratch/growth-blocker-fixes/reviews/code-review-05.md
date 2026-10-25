# Code review 05: every complaint pauses outreach, and config can't loosen the send limits

- **Branch:** `crew/growth-blocker-fixes-05-outreach-complaints-warmup-spacing` (e47b255, b0e9f81, e40a969)
- **Fixed point:** merge-base with `crew/growth-blocker-fixes`, `01ce0e9`. Diff: `git diff crew/growth-blocker-fixes...crew/growth-blocker-fixes-05-outreach-complaints-warmup-spacing` (9 files, +335 / -62).
- **Spec:** `issues/05-outreach-complaints-warmup-spacing.md`, with audit `code-review-02-scout.md` B1, B2, B3 (spacing half) and "Website dependencies", and scout PRD §5.3 and §5.7.
- **Method:** I read every changed file in full, plus the core modules the change runs through (`db`, `pause`, `discord`, `cloudflare`, `timeutil`, `outreach/store`, `outreach/cli`). mattpocock `code-review` ran its Standards and Spec reviewers in parallel, in fresh contexts that were not given my findings. I did the security pass myself, using the `security-review` method, because the brief caps fan-out at two. I reproduced each finding I could with a throwaway harness outside the repo (see Evidence).

## Round 2 verdict: approve

Re-review after fix round 1. The new commits are 6df5385 (send lock), 235b0aa (cursor marker check, `apply` required), 49e365c (Discord after commit) and 4977f57 (test comments). Diff: `git diff e40a969 crew/growth-blocker-fixes-05-outreach-complaints-warmup-spacing` (11 files, +304 / -61). Round-1 findings S1, S2 and R1 (ST1, SP1) are closed. So are N-sec1/ST2 (`apply` is now required, `suppression.py:88`), ST7 (the test comments now describe behaviour) and SP2 (`docs/scout.md` now says to start the site's table empty). The fixes add no blocking findings.

### Round-1 findings, checked

- **S1, closed.** `send_due` holds `locks.held("outreach-send")` from the pause, cap and gap checks to `_mark_sent` (`send.py:234-242`). A second call takes the lock without waiting, fails to get it, and returns "skipped: another send-due run is still going". My round-1 repros now fail, which means fixed: `test_r1_parallel…` (one send, B skipped) and `test_r1b_parallel…_daily_cap` (1 send at cap 1). They fail on the worktree and on the trial merge. New in-repo tests: `test_parallel_send_due_calls_send_live_only_once`, `test_parallel_send_due_calls_stay_within_the_daily_cap`. The lock also covers shadow mode. That changes nothing a single caller can see (`test_shadow_sends_have_no_minimum_gap` passes).
- **S2, closed for a recreated or rewritten table.** The sync now asks for `id >= cursor` and needs the cursor's own row to come back with the same `email_hash|reason|source|created_at` marker. If the row is missing or different, it raises `D1ContractError`, so the sync fails and outreach pauses (`suppression.py:105-112`, `:132-145`). `test_r2_cursor_ahead…` now fails, which means fixed. `test_r2b_table_rewritten_with_as_many_rows_is_caught` passes: a recreated table with at least as many rows is caught by the marker. **A known limit, documented:** an upsert on an *older* row still can't be seen (`test_r2c_upsert_on_an_older_row_is_still_invisible` reproduces). `docs/scout.md:224-227` says so, and makes plain inserts part of the contract. That is acceptable: only the website can enforce it, and the landing-page follow-up stays a prerequisite before the D1 secrets are set.
- **R1/ST1/SP1, closed.** `apply_rows` only writes to the database now. Posts and pause alerts are collected in `D1Result.posts` and `.alerts` and sent after the commit (`sync.py:65-70`, `:110-153`). The pause rows themselves are written inside the transaction with `notify=False` (`store.py:75-78`, `pause.py:58-61`). `test_r3_write_lock_is_held…` now fails, which means fixed: no "database is locked" during the post. A failed batch posts nothing (`test_a_failed_batch_posts_nothing_from_it`). The except path still pauses and alerts outside the transaction (`sync.py:56-63`).

### Questions from the brief

- **Can the runner lock change deadlock or skip a scheduled run?**
  - **Deadlock: no.** `runner._lock` is now `locks.held`, the same code moved word for word from `runner.py`. Both locks take the lock without ever waiting (`LOCK_NB`), so nothing can block on anything. They are also different files: the runner holds `scout-send.lock` (the job name, `config/settings.yaml:69`) and the sender holds `outreach-send.lock`. So `jura-growth run scout-send`, which runs `send-due` in-process (`runner._run_command`), takes both without contention. `flock` locks go away when the process exits, so a crashed run leaves no stale lock. `runner._lock_held` (which `_abandon_stale` uses) is unchanged and still checks the job lock.
  - **Skips:** a scheduled slot is skipped only while another `send-due` really is running (a manual call, or a slot stuck on a 30 s Resend or D1 timeout). That is the intended safe direction. `test_r6_scheduled_run_skips_cleanly_while_a_manual_send_holds_the_lock` passes: no run is marked failed (so the skip never counts toward the auto-pause), nothing is sent, and the next run sends.
- **Is a manual `sqlite3` cursor reset an acceptable recovery for the S2 pause? Yes.** `test_r5_documented_recovery_replays_and_pauses_again` passes. Clearing the cursor and resuming replays the whole table once. Every event is applied again, which is idempotent in the database, and an old complaint pauses again, as `docs/scout.md:228-231` warns. The second sync after that reports 0 new. Nothing can be skipped, because the replay starts from id 0. It is a rare step a person takes, after checking the site's table. See nit N4 for the better long-term form.
- **Merge with the feature branch (tickets 03, 06, 08 merged, head c9460c8):** `git merge-tree --write-tree crew/growth-blocker-fixes <branch>` → tree `050fea9`, **no conflicts** (exit 0). The `runner.py` hunks from ticket 03 (`_run_locked`) and from this branch (`_lock`) don't overlap, and `fcntl`, `contextmanager` and `Iterator` are all still used after the merge (`_lock_held`, `_run_env`). On the merged tree: full suite **590 passed**, and my harness gives the same results as on the worktree.

### New nits (round 2)

- **N3. A migration edited in place.** `0002_sync_cursors.sql` gained `marker` in place (235b0aa). That is safe only because the file has never left this unmerged branch. The live engine runs from `main`, which never had it. A database that applied the first version would fail the sync with "no such column: marker", so outreach pauses, which is the fail-closed direction. Don't edit it again after merge.
- **N4. The recovery is a raw SQL step.** It works, but a small `jura-growth outreach reset-d1-cursor` command would keep "every side effect goes through `jura-growth`", could log the reset, and could be refused to headless jobs under ticket 01's allowlist. Later, not now.
- **N5. Exactly how the marker compares.** `created_at` and `source` are part of the marker, so if the site ever reformats `created_at` on old rows, the sync fails closed. That is fine, but worth knowing.
- N1 (whole-minute rounding, `test_r4` still reproduces) and ST3–ST6 and SP3–SP6 stay as nits. None blocks.

### Round 2 evidence

- `uv run pytest` in the worktree at 4977f57 (temp data and outputs): **532 passed in 19.00s**.
- Trial merge `git merge-tree --write-tree crew/growth-blocker-fixes <branch>`: tree `050fea9`, exit 0, no conflicts. The full suite on that tree (imports checked to come from the merged tree): **590 passed in 19.93s**.
- Harness `scratchpad/review05/test_review05_repro.py` against the worktree, then a copy against the merged tree, with the same result on both:
  - Now fail, which means fixed: R1, R1b, R2, R3.
  - Wanted behaviour, passes: R2b, R5, R6.
  - Still reproduces, documented: R2c, R4.
- `pyright` on the eight touched modules: **9 errors on the branch, 9 on base** for the same set (`locks.py` adds none).
- Blocked paths: none. The worktree's `git status` is clean. I changed no code.

---

## Round 1 (kept for the record)

## Round 1 verdict: approve

No blocking findings. All three problems in the ticket are fixed, and so is every acceptance criterion: the audit repros F1b, F2 and F3 now fail against this branch, and new regression tests with the corrected expectations pass. The live `growth.db` migration is safe. A retried batch can't apply an event twice in the database.

Two *should fix* findings are paths around a limit (S1 the gap and the daily cap under parallel calls, S2 a cursor that runs ahead of the site's table). Neither is open to the headless agent once ticket 01 lands, and neither is open while the website keeps the D1 contract this branch documents. I recommend fixing both on this branch before `mode: live`, because both are small. **S1 becomes blocking if ticket 01 has not merged by the time live mode is switched on.**

---

## Standards

*(The Standards reviewer's report, lightly cleaned up. Its sources were `CLAUDE.md`, `README.md`, `docs/agents/crew.md` and the module conventions, plus the smell baseline.)*

**Hard violations:** none.
- The floor lives in `caps.py` and can't be configured (`caps.py:17-20`). `warmup_start` can only delay the warm-up (`send.py:184-194`). Both follow crew.md: "Hard limits live in jura_growth/caps.py; a config value may lower a limit, never raise it".
- The migration fits the core `NNNN_name.sql` sequence (README).
- The commit subjects are sentence-case imperatives.
- `docs/scout.md` and the comment in `config/scout.yaml` were updated to match.
- `pyright` reports no new errors on the touched files (7 on the branch, 7 on base).

### Should fix
- **ST1. Network I/O inside `BEGIN IMMEDIATE`** (`suppression.py:103-114` → `sync.py:113`, `:122`, `:134`). This goes against the spirit of the `db.py` docstring ("every connection is short-lived"). The other `db.transaction` users (`requeue.py:105`, `leads.py:259`, `submit.py:289`) wrap SQL only. This is the same issue as R1 below, which reproduces it.

### Nit (judgement calls)
- **ST2. Speculative Generality.** `apply: ... | None = None` (`suppression.py:83`) has one caller, and that caller always passes it. A caller that leaves it out still moves the cursor. Make the argument required (same as N-sec1).
- **ST3. Duplicated list.** `_OUTCOMES` (`sync.py:86`) is a second list of lead statuses beside `store.FINAL_LEAD_STATUSES` (`store.py:17`). It leaves out `do_not_contact` and `replied`, so an unsubscribe still overwrites them. That is unchanged from base, so it is not a regression, but the ranking belongs in `store.py`.
- **ST4. Possible Feature Envy.** `_mark_leads` (`sync.py:89-98`) queries `leads` directly, where every other lead-status write goes through `store.set_lead_status`.
- **ST5. A literal in prose.** The comments repeat "10 minutes" (`caps.py:19`, `send.py:13`) instead of naming the constant.
- **ST6. Redundant filter.** `suppression.py:101` filters `id > after` again after the query has already done it. It is defensible (the test double ignores params), but it needs a one-line comment.
- **ST7. Tests cite the review.** Comments say "Review finding F1/F2/F3" (`tests/test_outreach_send.py:290`, `:355`, `tests/test_outreach_sync.py:150`) and point at `.scratch/` artefacts that won't last. State the behaviour instead, as the neighbouring tests do.

## Spec

*(The Spec reviewer's report, lightly cleaned up and checked by me.)*

**Met:**
- "Act on every D1 event whatever the local suppression state": `sync.py:53`, `apply_rows` gets every event after the cursor.
- "Keep a cursor": `sync_cursors`, `suppression.py:129-138`.
- "Update the D1 contract in `docs/scout.md` to an append-only table": `docs/scout.md:189-221`.
- "Count the warm-up from the later of `warmup_start` and the recorded first live send": `send.py:194`. A future date is treated as day 1 (`:200`).
- "Hard minimum gap ... in `caps.py` (10 minutes), checked in `send-due` against the last recorded live send": `caps.py:20`, `send.py:256-264`.
- "Repros ... become passing regression tests with the corrected expectation": `tests/test_outreach_sync.py:149` (f1, now an appended row as the new contract requires), `:165` (f1b), `tests/test_outreach_send.py:289` (f2), `:354` (f3).
- "A D1 event already processed is never applied twice": holds in the database for new events (`test_a_processed_d1_event_is_never_applied_again`, `test_a_sync_that_fails_part_way_keeps_nothing_and_is_retried_whole`).
- "Shadow mode behaves as today": spacing and warm-up are unchanged in shadow (`test_shadow_sends_have_no_minimum_gap`).
- `uv run pytest`: 526 passed (my own run).

### Should fix
- **SP1. "Never applied twice", side effects.** Discord posts and the pause alert run inside the transaction, so a rolled-back batch posts again on retry. It is documented in the `sync.py:16-19` docstring, but it is still a second application. Same fix as R1.

### Nit
- **SP2. "Never applied twice", cutover.** The cursor starts at 0 on an existing `growth.db`, so if the site backfills old rows they are processed again. Same as N2: document "start the table empty", or treat local `d1:` rows as already seen.
- **SP3. "Shadow mode behaves as today", one deliberate change.** With D1 configured against the current site table (no `id`), a shadow sync now fails and pauses outreach, where before it synced. This is intended under the new contract and documented (`docs/scout.md:220-221`). D1 is not configured in growth yet, per the developer's report.
- **SP4. "Note it as a follow-up in the PR body".** There is no PR yet. The release manager must carry the landing-page follow-up (plain inserts, AUTOINCREMENT) into the PR body.
- **SP5. Scope.** The weak-to-strong lead outcome ranking (`sync.py:83-98`) and the refusal of rows without an id (`suppression.py:119-126`) were not asked for. Both are reasonable and tested.
- **SP6.** The gap reads `max(sent_at)` as text. That is safe while every stamp is SGT `+08:00` (`timeutil.stamp`), which it is today.

## Security

### Should fix

**S1. Two `send-due` calls in parallel both send live, inside the 10-minute gap and past the daily cap.**
- **Where:** `jura_growth/agents/outreach/send.py:251-264` (quota and gap read), `:276` (D1 sync, a network call), `:289` (queue re-read), `:375-377` (`sent_at` recorded only after Resend answers).
- **Rule broken:** the ticket's "hard minimum gap between live sends"; the claim at `send.py:13-14` and `caps.py:17-18` ("however often `send-due` is called"); PRD §5.3 "every limit in code".
- **How it happens:** nothing serialises `send_due`. Call B reads the gap and the quota, then waits on the D1 sync. Call A sends message 1 and records it. B then re-reads the queue, finds message 2 first, and sends it. The Resend idempotency key only stops a second send of the *same* message.
- **Reproduced:** `test_r1_parallel_send_due_calls_both_send_live_inside_the_gap` (two live sends in the same minute) and `test_r1b_parallel_send_due_calls_exceed_the_daily_cap` (cap 1, two sends). The cap overshoot is older than this branch: R1 and R1b both reproduce on the base too. The gap is new, and its doc comment claims more than the code does.
- **Who can reach it:** today, the prompt-injectable `scout-research` run, which has `Bash(jura-growth:*)` and can start background commands. Ticket 01 refuses `outreach send-due` to that job. After that, only a person running `send-due` by hand at the same moment as the scheduled run can reach it.
- **Fix:** in live mode, claim the slot before calling Resend. Inside `BEGIN IMMEDIATE`, re-check the gap and the quota and write a `last_live_attempt_at` claim (for example in `outreach_state`). Then count the gap from the later of that claim and `max(sent_at)`. Alternatively, take the runner's per-job lock inside `send_due` itself.

**S2. A sync cursor ahead of the site's table drops complaints without a sound.**
- **Where:** `jura_growth/suppression.py:95-101`.
- **Rule broken:** PRD §5.7 "pause on any complaint"; the ticket's "act on every D1 event".
- **How it happens:** the sync asks only for `id > cursor`. Suppose the site's table is dropped and recreated (ids start again at 1). Or suppose it gets an `id` column but keeps the old upsert on `email_hash` (`ON CONFLICT DO UPDATE` keeps the id, `INSERT OR IGNORE` writes nothing). Either way, a new complaint never comes back, and nothing fails. The only guard is the check for a missing `id` (`suppression.py:119-126`), which catches the unchanged table and nothing else. The audit's own `test_f1` repro, which models the upsert, still passes (still reproduces) on this branch for exactly this reason.
- **Reproduced:** `test_r2_cursor_ahead_of_a_recreated_d1_table_skips_a_complaint_silently`. Cursor 3, the table is recreated, and a complaint arrives as id 1: "0 new suppressions", and outreach is not paused.
- **Fix:** fail closed when D1 doesn't look like the contract. Two cheap ways: ask for `id >= cursor` and require the cursor's own row to come back, or read `sqlite_sequence` for `suppression` (AUTOINCREMENT) and refuse if it is below the cursor. Either way, raise so the sync pauses outreach. The website follow-up (plain inserts, AUTOINCREMENT) stays a hard prerequisite before the D1 secrets are set.

### Nit

- **N-sec1.** `sync_from_d1(conn, apply=None)` (`suppression.py:83`) moves the cursor even when no one acts on the events. Today the only caller passes `apply` (`sync.py:53`). A future caller that leaves it out would quietly use up complaints. Make `apply` a required argument.
- Nothing else was found. The SQL built in `_mark_leads` (`sync.py:89-98`) adds placeholders only. D1 values reach SQL as bound parameters. The new event log line (`suppression.py:115`) carries counts and an id, no address. No secret is read, logged or echoed. The Discord text built from D1's `source` is unchanged from before, and posts go out with `allowed_mentions: []`.

---

## Other findings from my own pass

### Should fix

**R1. The sync holds the database write lock while it calls Discord.**
- **Where:** `suppression.py:103-114` wraps `apply`, which posts to Discord (`sync.py:113`, `:122`) and sends the pause alert (`sync.py:134` → `pause.py:55`), all inside `BEGIN IMMEDIATE`.
- **Effect:** every other job's write waits. A large batch (the first sync after the site's table goes live, say) or a slow Discord can hold the lock past the 30 s `busy_timeout` (`db.py:26`). The other job's run then fails, and three failures auto-pause it. It is also why a retried batch posts again, which the developer has documented.
- **Reproduced:** `test_r3_write_lock_is_held_while_discord_posts_during_the_sync`. A second connection's insert during the post gets "database is locked".
- **Fix:** have `apply_rows` collect its posts and alerts, and send them after the commit. With ticket 03's outbox, an undelivered post is kept anyway. That also ends the repeat posts on a retry.

### Nit

- **N1. The gap can be 9 minutes 1 second.** The gap is counted in whole clock minutes (`send.py:179-181`): a send at 10:00:59 allows the next at 10:10:00 (`test_r4_whole_minute_rounding_allows_a_gap_under_ten_minutes`). This is deliberate and documented (`caps.py:18-19`, `docs/scout.md:147-148`), so it keeps the 10-minute slots usable. Consider renaming the constant or the comment to "at most one live send per 10-minute slot", so nobody reads it as a strict 600 seconds.
- **N2. The cutover can replay old events once.** On an existing `growth.db` the new cursor starts at 0 (`suppression.py:130`). If the site copies its old rows into the new append-only table, the first sync replays them: Discord posts again, and an old complaint pauses again. That is the fail-closed direction, and the developer reports D1 was never configured in growth, so in practice nothing has been processed yet. Add one line to the setup checklist in `docs/scout.md` saying "don't backfill old rows, or seed `sync_cursors`".

## Migration safety (asked for in the brief)

- `jura_growth/migrations/0002_sync_cursors.sql` only creates a new table. It runs once, as `core/0002_sync_cursors.sql`, inside the same `BEGIN … COMMIT` script as its `schema_migrations` row (`db.py:61-77`), so a crash leaves either both or neither. It doesn't clash with `outreach/0002_requeue_shadow.sql` (different owner prefix), and no parallel branch adds a core migration.
- An older checkout ignores `sync_cursors`. Rolling back loses nothing, and rolling forward again resumes from the stored cursor.
- **Retries:** the local copy, `apply_rows` and the cursor move commit together (`suppression.py:103-114`, `db.transaction`). A failure part-way rolls back all three, and `sync_suppression` then pauses outreach (`sync.py:54-60`). So a retried batch never applies twice in the database (`test_a_sync_that_fails_part_way_keeps_nothing_and_is_retried_whole`, `test_a_processed_d1_event_is_never_applied_again`). It can post to Discord twice (R1). It can't send an email twice, because the sync sends nothing.

## Blocked paths

`git diff --name-only 01ce0e9...<branch>` has nothing under `inputs/`, `design-system/`, `_ds_bundle.js`, `.env`, `data/growth/` or CI. There are no blocked-path findings.

## Reuse

No duplication found. The cursor helpers use `db.scalar` and `db.transaction`, and the gap uses `timeutil.parse`. `minutes_since_last_live_send` follows the shape of the existing `_count` query.

## Evidence

- `uv run pytest` in the worktree, with `JURA_ROOT` set and temp `JURA_GROWTH_DATA_DIR`/`OUTPUTS_DIR`: **526 passed in 16.73s**.
- Audit repros (`audit/repro/test_review_repro.py` F1–F3), copied into `scratchpad/review05/` and run against the worktree (`.venv` imports the worktree's `jura_growth`, checked with `python -I`): **F1b, F2 and F3 fail**, which means fixed. **F1 still passes**, but only because it models the old upsert table, which the new contract forbids. See S2.
- Reviewer repros, `scratchpad/review05/test_review05_repro.py` (each passes when the finding reproduces): R1, R1b, R2, R3 and R4 **all passed**, 6 passed / 3 failed overall with the audit file.
- R1 and R1b against the base checkout (`crew/growth-blocker-fixes`): **2 passed**. The parallel cap overshoot is older than this branch.
- `pyright` on the four touched modules: **7 errors on the branch, 7 on base `01ce0e9`**, so no new errors.
- The worktree's `git status` is clean. I changed no code.
