# 04: Rehearse the Discord flow without a live post

Status: ready-for-agent
Blocked by: 02

Add the seven harness items H1 to H7 listed in `reviews/uat.md`, so Ting Yu's UAT proves the flow on the fixture with no live post and no Dispatch UAT key. Test code only (`tests/uat/`, `tests/test_uat_seed*.py`). Functional B6.

**Acceptance:** the new seeds are covered by `tests/test_uat_seed*.py`, and `uat.md` names commands that exist. No run touches the live `data/growth/`, Discord or launchd.

## Comments
