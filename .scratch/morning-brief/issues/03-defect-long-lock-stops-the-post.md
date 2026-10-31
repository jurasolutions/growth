# 03: A lock past 30 seconds stops the morning post

Status: ready-for-agent
Blocked by: none
Severity: major (test strategy criterion 8: a criterion failing). Found by QA 01; no review has it.

## What is wrong

The PRD says a held lock at 09:00 "is retried for up to 60 seconds on the post path", and test strategy risk 4 says that past the wait he gets the bad-day page. That retry only wraps `mission.read`. Three ordinary connections sit outside it, and each waits 30 seconds and then raises:

- `runner.run` opens `db.connect()` before the job starts (`runner.py`, the job path launchd uses).
- `one_pager_cmd` opens `db.session()` for the upkeep (`cli.py:414`), so `read_patiently` is never reached.
- `discord.post` calls `_record` after the post (`discord.py:397`).

So a lock that outlasts 30 seconds gives no picture, no long text and no bad-day page. He gets nothing, and the job leaves a traceback. Locks under 30 seconds are fine, because SQLite's own wait covers them.

The existing tests, `test_past_its_patience_the_post_path_gives_the_bad_day_snapshot` and `test_a_locked_database_gives_the_bad_day_page`, pass because they call the read directly.

How likely this is: unknown. Functional S4 says nobody measured how long publish holds a write, and this branch is what puts the one-pager in publish's minute. The same crash exists on `main`, but `main` posts at 08:00 with nothing beside it.

## Steps

On temp data, with no webhook set:

1. Seed a temp `growth.db`.
2. In another process: `sqlite3.connect(db, isolation_level=None).execute("BEGIN EXCLUSIVE")`, and hold it for 90 seconds.
3. Run `jura-growth one-pager`.

## Expected

The post path waits, then posts the picture or the bad-day page, with exit 0. A post that went out is reported as posted.

## Actual

| Lock | Held | Result |
|---|---|---|
| `BEGIN EXCLUSIVE` | 10 s | Waits, then saved to the outbox with the picture. Exit 0 |
| `BEGIN IMMEDIATE` | 25 s | Same. Exit 0 |
| `BEGIN IMMEDIATE` | 45 s | Picture drawn and the message saved to the outbox (no webhook is set), then `sqlite3.OperationalError: database is locked` from `discord.py:397`. Exit 1 after 33 s. With a webhook, the third test below shows the post goes out and the command still fails, so asking again would post twice |
| `BEGIN EXCLUSIVE` | 90 s | `sqlite3.OperationalError: database is locked` from `db.py:25`. Exit 1 after 33 s. No files, no message, nothing in the outbox |

Runs were on a temp database through the real CLI. The job path was not run for real, because `jura-growth run` is off limits, and the test exercises it in process with `db.connect` raising. A real exclusive lock raises the same error from the same function.

## Evidence

- `reviews/qa-01.md`, exploratory charter, E11.
- Scripts in the QA scratchpad: `qa_lock.sh`, `qa_hold.py`, `qa_hold2.py`, `qa_cli5.sh`, `qa_cli7.sh`.

## Failing tests

`tests/test_qa_01_defects.py` (uncommitted, in the feature worktree). The first two stand in for the wait by making `db.connect` raise what it raises after 30 seconds, since no test can spend them:

- `test_the_command_gets_the_morning_post_out_past_the_write_connections_wait`
- `test_the_job_gets_the_morning_post_out_past_the_write_connections_wait`
- `test_a_lock_after_delivery_doesnt_report_a_post_that_went_out_as_failed`

## Comments
