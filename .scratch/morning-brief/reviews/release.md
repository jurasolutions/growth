# Release: morning brief

```
Recommendation: open the PR, and Ting Yu merges it after reading its first section
Tested commit:  crew/morning-brief @ 4b926fc (base origin/main @ 68a1911, 0 commits behind)
Suite:          4481 passed, 0 skipped, on Python 3.14 and 3.12
```

This file's commit adds only this file and `reviews/pr-body.md`, so the run above stands for the branch tip.

**Three things changed under this release, and the conductor should read them first.**

1. **Main moved while I worked.** The brief expected HEAD to include `origin/main`, and it did at `f9a9ad6`. PR #17, the apps idea command, then landed at `68a1911`, leaving the branch 7 commits behind. I merged it (`412e9c1`), since the checklist needs the branch up to date and the merge is on this branch only.
2. **That merge had no textual conflict and still broke.** Five tests failed on it, four for a crash and one for a stale time. I fixed both in `4b926fc`, which changes 6 lines:
   - `apps idea --source x` crashed with a `TypeError`. Main's refusal calls `_short(option, 20)`, and this branch had dropped `_short`'s `limit`. I restored the argument.
   - The reply told Ting Yu the factory runs at 06:30, and it now runs at 07:00 (SC7). I changed the reply, one comment and the test's expected wording.
3. **So the gate's GO no longer sits on the current SHA.** It was given at `b953955`. `4b926fc` has only the suite behind it, and nobody else has read it. The conductor should read it before opening the PR. The gate asks for criteria 2, 3 and 6 after any rebase. The results are under "Rechecks since the gate".

## Readiness

| Item | Result | Note |
|---|---|---|
| Quality gate says GO at the current SHA | No, waiver W1 | GO at `b953955`. Since then: two merges from main, the gate's own record, and `4b926fc` |
| Every `code-review-*.md` approves, `final` included | No, waiver W2 | `code-review-final-2.md` approves at `00b0ab4`. `01`, `02` and `final` read changes-requested, and each of their blockers is confirmed fixed in the next review. `b953955` and `4b926fc` came after the approval |
| Up to date with its base, and the suite green after that | Yes | 0 behind `origin/main` at `68a1911`, checked after the last fetch. Suite above |
| No commit touches a blocked path | Yes | `git diff --name-only origin/main...HEAD` holds nothing under `inputs/`, `design-system/`, `.github/` or `data/growth/`, and no `.env` |
| No secrets or credentials in the diff | Yes | The checklist's grep finds setting names and test fixtures only. A second search for real key, webhook and private-key shapes finds nothing |

## Package

| Item | Result | Note |
|---|---|---|
| Version bumped per convention | n/a | `pyproject.toml` has stayed at 0.1.0 since the first commit, there are no tags, and the gate's criterion 6 freezes the file |
| `CHANGELOG.md` entry | n/a | The repo has none. The card says release notes go in the PR body |
| Release notes for users | Yes | In the PR body |
| PR body | Yes | `reviews/pr-body.md`, ending with the requested lines |
| Gate criterion 10 | Yes | Approvals-first isn't merged, so the body's first step says to merge it first if ready |
| Gate criterion 11 | Yes | The body opens with the steps, and links the three renders with their paths |

## Runtime

| Item | Result | Note |
|---|---|---|
| Migrations | n/a | None on this branch. An older checkout runs against the same `growth.db` |
| New configuration or environment variables | n/a | None. `config/settings.yaml` changes job times and adds one job. `retention.one_pager_days` keeps its name and value, and now covers the picture and page too |
| Feature flags | n/a | None. The nearest things to one are `jura-growth pause <agent>` and `jura-growth schedule uninstall <job>` |
| What to watch | Yes | Below |

### What to watch

**For the first two mornings:**

- The picture arrives at 09:00, not midnight. This is the only test of the restart, because without approvals-first nothing else reports the drift.
- `jura-growth status` shows the new times, and `outreach-requests` is listed.
- `data/growth/launchd/<job>.log` for the five moved jobs and `outreach-requests`.

**Through the first week, while UAT U1 to U7 run:**

- `#alerts` for any failure.
- `one_pager.picture_failed`, `one_pager.not_posted`, `one_pager.upkeep_skipped` and `run.database_locked` in the mirror.
- A "Check `one-pager`: it failed" line on a morning after that post did arrive. That is Sf2.
- Whether a tall picture shrinks on Discord. If it does, MB5's 1,600 px maximum comes down.

On a Mac that had the install the evening before, Sunday's picture should show Social and App factory as "Ran", and Scout, Outreach and Community as "Not today". Monday's should show all five rows as "Ran", if the ICP is in place.

## Rechecks since the gate

| Check | Result |
|---|---|
| Criterion 2, full suite | Passed on `4b926fc`, as above |
| Full suite on Python 3.12 | 4481 passed, 0 skipped |
| Criterion 3, the picture's fixtures | Offline: `uv run python tests/picture_chrome.py` gives `problems: []` on all five, at 900, 1190, 949, 949 and 1554 px, the same as the gate. `--live-fonts` wasn't rerun, because `git diff b953955 HEAD` is empty for `picture.py`, `images.py`, `one_pager.py`, `mission.py`, `health.py`, `runner.py`, `slots.py`, `tests/picture_chrome.py` and `tests/picture_world.py`. The committed renders are still current for the same reason |
| Criterion 6, frozen files | `git diff origin/main` is empty on the frozen list, and the three limited test files have no change since `b953955` |
| Pyright on the two touched modules | 0 errors on `remote.py` and `ideas.py` |

The Python check is mine, and the gate didn't ask for it. The live checkout's `.venv` is Python 3.12, while this worktree's is 3.14, so every run recorded on this branch was on a version the jobs don't use.

## Rollback

**To revert:** the merge commit of the PR, with GitHub's Revert button or `git revert -m 1 <merge commit>`. The branch's own range is `68a1911..crew/morning-brief`, from `73c13d5` to the tip.

**On the Mac afterwards, from `repos/growth`:**

```bash
uv run jura-growth schedule uninstall outreach-requests
git pull && uv sync
uv run jura-growth schedule install
cp .scratch/mission-control/setup/discord.md .scratch/mission-control/setup/morning-brief.md ../../outputs/growth/setup/
```

- `schedule install` only handles the jobs in the current list, so without the first line `outreach-requests` stays loaded and fails at 08:30 on business days with "unknown job". `schedule.uninstall` takes any name, so it works before or after the revert. I read this in the code and didn't run it, because the card forbids it.
- The `cp` restores the guides: at `68a1911` both files match the live guides byte for byte.

**To stop one job without reverting:** `jura-growth pause <agent>` or `jura-growth schedule uninstall <job>`.

**What a revert doesn't undo:**

| Left behind | What to do |
|---|---|
| Requests raised and cards posted by `outreach raise-due` | Nothing. They lapse or get decided as usual. An approved email that was sent stays sent |
| Discord posts already made | Nothing, or delete them by hand |
| `picture-*.png` and `picture-*.html` in `data/growth/one-pager/` | Delete by hand, because the older `backup` prunes only `grid-*.png` |
| `inputs/icp.md`, once Ting Yu adds it | It stays, so research keeps running. Removing it stops research |
| The restart | Nothing. It's harmless |

## Waivers for Ting Yu

Merging accepts all of these, and the PR body says so.

- **W1.** The gate's GO is at `b953955`, not the tip.
- **W2.** The last review approval is at `00b0ab4`. `b953955` was read at the gate, and `4b926fc` hasn't been reviewed.
- **Sf2, the pause trade under `EXCLUSIVE`, and G1.** These are accepted by the conductor, not by him.
- **Criterion 6's two comment lines.**
- **UAT U1 to U7 run after merge,** and a failure means revert. The picture's inline height on Discord (U1) is unverified.
- **PRD §7 reads "not signed".** The gates were ruled under the standing instruction, so merging is his acceptance. After merge and acceptance, the PRD moves to `prd/done/` with the ship date at the top.

## After merge

**Steps 1 to 6 are at the top of the PR body.** I checked their facts on this Mac:

- `inputs/icp.md` is missing, and the draft exists.
- The guides on `outputs/growth/setup/` are on the old times, and the only differences from the new copies are the lines about the time and the post's contents.
- The main checkout is clean and on `main`.
- Approvals-first (`832fd0f`) has no open PR and no gate, and `git merge-tree` shows 7 conflicting files with this branch: `CONTEXT.md`, `README.md`, `docs/scout.md`, `discord.py`, `health.py`, `mission.py` and `tests/test_mission_health.py`.

## Options for G4

The ship path on the card is a GitHub PR from `crew/morning-brief` into `main`. Merging is Ting Yu's, in every option.

| Option | What happens next | View |
|---|---|---|
| **Open a PR** | The conductor pushes the branch and opens the PR with `reviews/pr-body.md`. Ting Yu reads it, merges, and does the steps. UAT follows | **Recommended.** It's the card's path, and it puts the steps, the renders and the trades in front of him |
| **Merge locally** | Merge into local `main`, rerun the suite, and push `main` | Not recommended. It skips the PR body, and the crew may not do it |
| **Keep the branch** | Nothing changes. The worktree stays, and the jobs keep old times and fire about 9 hours early | Reasonable only if he wants approvals-first first, and the rebase on it then falls here |
| **Discard** | The branch and the worktree are deleted after he confirms | Not recommended. Offered only because the checklist asks for all four |

The card opens the PR "only after the user's G4 answer", while the crew log has the conductor opening it under the standing instruction. That conflict is the conductor's call, so I name it here and open nothing. Opening the PR changes nothing live, and the merge is still his.

## Evidence

| Command, with the card's worktree exports and temp folders only | Result |
|---|---|
| Full suite at `fea62e2`, before main moved | 4388 passed in 284.91 s |
| Tests on the merge `412e9c1`: `test_morning_schedule.py`, `test_apps_idea.py`, `test_remote.py` | 5 failed, 303 passed |
| The same files with the fixes | 308 passed |
| `uv run pytest -rs -q -p no:cacheprovider -o addopts=""` at `4b926fc` | 4481 passed, 0 skipped, in 302.36 s, on Python 3.14.7 |
| The same on Python 3.12, in a temp venv | 4481 passed, 0 skipped, in 382.41 s, on Python 3.12.14 |
| `test_picture_chrome.py`, `test_picture_privacy.py`, `test_morning_order.py` alone, with `JURA_GROWTH_DISCORD=off` | 135 passed |
| `uv run pyright --pythonpath .venv/bin/python` on `remote.py` and `ideas.py` | 0 errors, 0 warnings |
| `git rev-list --count HEAD..origin/main`, after fetch | 0 |
| `git status -s` after the suite | Clean |

**Boundaries, as they went.** Nothing was posted or pushed. `jura-growth run`, `schedule install` and `schedule render` were never typed. The suite calls `schedule.render` itself under `conftest.py`'s temp folders, as earlier reviews recorded. Afterwards the newest plist in `~/Library/LaunchAgents` was still dated 29 October, and the newest file in the live `one-pager` folder 30 October.
