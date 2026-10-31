# 10: Merge main, and close the final review and QA

Status: done
Blocked by: 01, 02, 03, 04

**First commit: merge `origin/main` (no rebase; this branch is pushed).** Take M1 to M4 from "Merging with approvals-first" in `.scratch/morning-brief/reviews/code-review-final.md` on main. In `mission._failures` keep mask-then-cut: `_clean(row["error"] or "")[:300] or None`. The digest's 18:05 move carries `tests/test_morning_schedule.py` and `picture.LATER` with it. Main moved social to 07:30, the one-pager to 09:00 and scout research to 06:30: re-check every place this branch states a time, and the first-day walk, against the new schedule.

**Then:** tickets 05 to 09, with the failing tests in `issues/test_qa_final_defects.py` moved into `tests/`. From `reviews/code-review-final.md`: SP-B1, SP-B2, SP-S2, SP-S3, the `NOT_NAMES` should-fix, every other should-fix in that file. The UAT seed must never be able to reach live webhooks (SEC-S1).

**Acceptance:** every defect test green; the full suite green, run twice, with failure names kept. Exit criteria X1 to X8 of `reviews/test-strategy.md` rerun on the merged tree and recorded in `reviews/qa-final.md`'s "after the merge" section.

## Comments
