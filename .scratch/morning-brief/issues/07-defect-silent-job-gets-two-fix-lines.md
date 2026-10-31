# 07: A job silent two mornings gets two Fix lines

Status: ready-for-agent
Blocked by: none
Severity: minor. Owner: the developer on the fix round. MB3 says one line per item, but both lines are true and each names the job, so nothing is hidden or false until the list passes its cap. The same finding as `reviews/code-review-final.md` S2.

## Steps

Build a snapshot where `social` has yesterday's slot `missed` and today's 07:30 slot `due`, installed, at 09:00. Call `picture.fixes`.

## Expected

One line about `social`.

## Actual

Two lines: "Check `social`: no trace of its run today." and "Check `social`: it missed 1 slot since …". Each adds one to the verdict's count. With `FIX_SHOWN` at 4, a Mac that slept through two mornings could push a real failure or the ICP line under "and N more".

## Evidence

The built snapshot in the test, at `33fb30d`.

## Failing test

`tests/test_qa_01_defects.py::test_a_job_silent_two_mornings_is_one_fix_line` (uncommitted, in the feature worktree).

## Comments
