# 06: A draft whose card was answered reads as "to post by hand"

Status: done
Blocked by: none
Severity: major (test strategy criterion 8: a false verdict), but it can't happen on this branch alone. The same finding as `reviews/code-review-final.md` B2, which also has the real-read repro and the fix.

## What is wrong

`picture._to_post_by_hand` subtracts only requests that are still waiting. A draft stays `draft` until it is posted, so once its `social-post` card is approved or skipped, the verdict tells him to post it by hand. If he approved it, publish would post the same thing.

Every platform is `publish_mode: draft` today, so no such card exists until the approvals-first PRD switches Facebook and Instagram to `browser`. The PRD's merge order puts that first, so this goes live with the merge.

## Steps

Build a snapshot with `social_drafts_waiting=1` and one `social-post` request from today, in the reading `approved` or `skipped`, then call `picture.verdict`.

## Expected

The verdict doesn't include "to post by hand".

## Actual

"1 to post by hand."

## Evidence

Both readings, on built snapshots at `33fb30d`. I did not repeat the final review's real read.

## Failing test

`tests/test_qa_01_defects.py::test_an_answered_social_card_is_not_a_draft_to_post_by_hand` (2 cases; uncommitted, in the feature worktree).

## Comments
