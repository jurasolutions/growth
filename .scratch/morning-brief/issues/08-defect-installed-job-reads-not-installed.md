# 08: On install day, an installed job reads "Not installed"

Status: done
Blocked by: none
Severity: minor. Owner: the developer on the fix round. MB7 says the picture only shows what the engine recorded, and this row says two untrue things, but it shows only on an on-request post on install day. The scheduled 09:00 after an evening install is clean. The same finding as `reviews/code-review-final.md` S1.

## Steps

Build a snapshot at 10:10 with `social`'s 07:30 slot `not installed` (the classifier's word for a slot from before the install), `installs["social"] == installed` and `installed_at` at 10:00. Read Social's row from `picture.agent_rows`.

## Expected

The row doesn't say the job isn't installed.

## Actual

"Not installed", "No run on record yet", in amber.

## Evidence

The built snapshot in the test, at `33fb30d`. I did not repeat the final review's real read. My first-morning probes on Sunday 1 and Monday 2 November, with an install the evening before, read clean (`reviews/qa-01.md`, E2).

## Failing test

`tests/test_qa_01_defects.py::test_an_installed_job_with_a_run_on_record_never_reads_not_installed` (uncommitted, in the feature worktree).

## Comments
