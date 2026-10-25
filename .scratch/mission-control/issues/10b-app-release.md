# 10b — MC-10b app releases wait for a second approval, bound to the commit

Status: ready-for-agent
Blocked by: 10
PRD ticket: MC-10 in `prd-jura-mission-control-2026-10-25.md` §5.12, second half: preview to release (split by the ticket review)
Covers: SC9 (preview to release), SC4 (the `app-release` row)

## What to build

When a handed-off build is finished on its own task branch with a preview, `apps built` raises an `app-release` request bound to the exact head commit SHA. Going to production is that second approval: `apps release-plan` claims it and prints the merge for that SHA only, and `apps released` refuses unless `main` of the landing-page repository contains it, then moves the PRD to `prd/done/apps/` with the ship date and a sign-off line naming both approvals.

## What to change

- The `app-release` kind (content: app id, task id, branch and head commit SHA; decide-by 7 days; use-by 14 days), as in the MC §5.7 row.
- `apps built <APP-NNN> --task --branch --sha --preview`, `apps release-plan <APP-NNN>` and `apps released <APP-NNN> --task`, as in MC §5.9 steps 3 and 4.
- The SHA check against `paths.site_repo()` (already `JURA_SITE_REPO`, pointed at `tmp_path/site` by `tests/conftest.py`): `git -C <site_repo> merge-base --is-ancestor <sha> main`. It never fetches, pulls or writes. A test asserts the checked path is under `tmp_path`, because the write guard doesn't cover subprocesses.
- `prd/done/apps/` with the ship date and the sign-off line; the backlog updated.
- `tests/gate_adapter_app_release.py`. Call 02's `assert_clean` over release cards.

## Acceptance criteria

- [ ] **AC-M9.7** Given an approved, handed-off build, when `apps built APP-014 --task T-0031 --branch
  claude/T-0031-paynow-qr --sha <sha> --preview https://<branch>.<project>.pages.dev` runs, then an
  `app-release` card posts with the preview link and the short SHA. Given a build that wasn't
  handed off, the same command exits 1.
- [ ] **AC-M9.8** Given an approved `app-release`, when `apps release-plan APP-014` runs, then it claims
  the approval and prints the exact merge command for the approved SHA only. Given none, it exits 1
  and prints nothing to run.
- [ ] **AC-M9.9** Given no claimed `app-release`, or `main` of `repos/landing-page` not containing the
  approved SHA, when `apps released APP-014 --task T-0031` runs, then it exits 1 and the PRD stays
  in `pending/`. Given both, it records the release, moves the PRD to `prd/done/apps/` with the ship
  date and a sign-off line naming both approvals.
- [ ] AC-M4.1 to AC-M4.7 (owned by 04) hold for `app-release` through its adapter file, with the claim in `release-plan` before anything is printed to run (AC-M4.3).
- [ ] **X2 and X3 for this kind.**
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC SC9, §4.8 (D7), §5.7 (`app-release` row), §5.9 steps 3 and 4, §6 Q4 (accepted: Cloudflare Access on previews, ticket 16)
- `.scratch/mission-control/reviews/tickets-technical.md`: T9, Q7
- `.scratch/mission-control/reviews/technical-v2.md`: N5 (the release hash binds the SHA); `.scratch/mission-control/reviews/functional.md`: B3
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M9.7 to AC-M9.9), §3 (D9, D13), §11.2 row MC-10
- Code: `jura_growth/agents/apps/`, `jura_growth/paths.py` (`site_repo`), `tests/conftest.py`
