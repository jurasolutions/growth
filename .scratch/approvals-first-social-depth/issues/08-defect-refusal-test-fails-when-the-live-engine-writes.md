# 08: Defect: a refusal test fails whenever the live engine writes during it

Status: done
Severity: minor (a test only; no product behaviour is wrong, and nothing was written to live data by a test)
Owner: developer
Found by: QA at f0db1e5, `reviews/qa-final.md`. This is the intermittent failure ticket 02 asked QA to hunt.
Failing test: `.scratch/approvals-first-social-depth/issues/test_qa_final_defects.py`, the test under "08"

## The failure

```
FAILED tests/test_uat_seed_outreach.py::test_every_scenario_refuses_the_live_folders_and_changes_nothing[note-rules]
tests/test_uat_seed_outreach.py:381: assert untouched_snapshot() == before
Differing items:
{'.../jurasolutions/data/growth/runs/2026-11-01.jsonl': (False, 349, 1793462402620496874)} != ...
1 failed, 5166 passed
```

## Why

- `untouched_snapshot()` stats the live `data/growth/` before and after each scenario's refusal, and leaves out only `growth.db` and `locks` as `ENGINE_CHURN`.
- The live engine writes other things there too: `runs/<day>.jsonl`, `discord-outbox/`, `one-pager/`, `daily-summary.json`, `app-backlog.yaml`, `backups/`, `transcripts/`, `work/`.
- So the test fails if any live job or Dispatch command writes one of those while a case runs. The 36 cases take about 3 seconds of a run in all, and each compares its own before and after.

**Who wrote it.** Not the test. That mtime is 00:00:02.62 on 2026-11-01, and `runs/2026-11-01.jsonl` starts with the live publish job's `run.quiet` at 00:00:02 and the live one-pager's `run.start` at 00:00:02. Those two lines are exactly the 349 bytes in the failure's diff. Line 380 had already asserted the seed refused with exit 2, before anything could be written. The jobs fire at 00:00 because of the steady 9-hour offset SC1 reports (`publish` 09:00 at 00:00).

## How often

Two parametrized tests compare this snapshot (`..._refuses_the_live_folders...` and `..._refuses_the_real_config_folder`), 18 cases each, one per seed scenario. Live writes land every 10 to 20 minutes and with each Dispatch command, so most runs miss those 3 seconds. This is why it looks random. Run alone straight afterwards, all 36 pass.

`ENGINE_CHURN` is the same on `main`, so this predates the branch, and any repo checkout on this Mac can hit it while the engine is live. Ticket 02's run failed unnamed, so I can't prove that was this one. It fits, and nothing else failed in any run here.

## Steps

The failing test reproduces it every time with stand-in folders: it snapshots, writes `runs/<day>.jsonl` as the live job did, and compares. To see the original, run the suite so that the test runs while a live job fires.

## Expected

The test passes whatever the live engine does at the time, and still fails if the seed writes anything.

## What I'd do

Don't widen `ENGINE_CHURN`, since listing most of the folder guards little. Have the test build a stand-in "live" tree under a temp `JURA_ROOT`, so its snapshot sees only the seed's own writes. Keep the check that the refusal happens before anything is opened. The same applies to the `real_config_folder` test.

## At the gate

If X1's rerun shows this exact test and a `runs/`, `discord-outbox/` or similar path in the diff, the rerun of that one test is the check, until this is fixed.
