# 05: The Dispatch contract still says the one-pager carries the grid

Status: ready-for-agent
Blocked by: none
Severity: minor. Owner: the developer on the fix round. The same finding as `reviews/code-review-final.md` S5.

## Steps

`git grep -n "14-day grid" docs/dispatch-contract.md`

## Expected

MB12 and SC7: the grid is no longer posted, and the docs describe the one-pager as it now is.

## Actual

`docs/dispatch-contract.md:96` reads: "Posts the one-pager to `#mission-control` with the 14-day grid, dedupe off". No test reads this file. Dispatch's own repository may hold a copy, which I can't reach from here.

## Evidence

The search above, at `33fb30d`. `reviews/qa-01.md`, SC7.

## Failing test

`tests/test_qa_01_defects.py::test_the_dispatch_contract_no_longer_says_the_one_pager_carries_the_grid` (uncommitted, in the feature worktree).

## Comments
