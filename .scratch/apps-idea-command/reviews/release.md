# Release: apps idea command

- **Branch:** `crew/apps-idea-command`, code at 725f272, into `main` through PR #17 (https://github.com/jurasolutions/growth/pull/17).
- **Base:** `origin/main` at f9a9ad6, fetched 2026-11-01. The branch's merge-base is 1206360.
- **Spec:** `issues/01-apps-idea-command.md` and `prd/pending/prd-jura-app-factory-2026-10-24.md` §5.6, the "Amended 2026-10-31" bullet.
- **Release manager:** crew release, 2026-11-01.
- **On top of 725f272:** one commit that adds this feature folder under `.scratch/apps-idea-command/` and changes no code. QA's transcripts, harness and backlog snapshots are included. Its temp `growth.db` files, lock files, `.DS_Store` and its two copies of the whole `jurasolutions/prd/` tree are left out. They are binary or regenerable, and the PRD copies would duplicate live documents that go stale.

## Readiness

| | Item | Note |
|---|---|---|
| ❌ | `reviews/quality-gate.md` says GO at the current SHA | No quality gate was run (route S). **Waiver for Ting Yu:** QA 01 passed every acceptance criterion at 6b69230, and its two defects (02, 03) were fixed in d4748a7. The full suite is green on the merged tree (below). |
| ❌ | Every code review approves, the final one included | Round 2 approved 6b69230. Round 3 asked for changes at d4748a7, and 725f272 answers them by removing the recovery path. **The final re-review of 725f272 is running in parallel and has no verdict yet. Don't merge until it approves.** |
| ✅ | Up to date with the base, suite green afterwards | `main` gained two commits since the merge-base (PR #16: `config/settings.yaml`, `docs/app-factory.md`, `.scratch/`). `git merge-tree` reports no conflicts. `docs/app-factory.md` auto-merges, with the two edits in separate places. Full suite on the merged tree, uncommitted: **4075 passed** in 334s (`uv run pytest -q -rs -p no:cacheprovider -o addopts=""`, worktree exports, temp data and outputs). No commit needed on the branch: GitHub's merge commit does the same merge. |
| ✅ | No commit touches a blocked path | `git diff origin/main...HEAD --name-only` has nothing under `inputs/`, `design-system/`, `.env`, the live `data/growth/` or CI. |
| ✅ | No secrets in the diff | `git diff origin/main...HEAD` added lines grepped for `secret|token|password|api[_-]?key`: no matches. The feature folder was grepped the same way, and the only hits are prose ("tokens" for design tokens). |
| ✅ | No commits that shouldn't ship | Four commits (8b34f3c, 6b69230, d4748a7, 725f272), each a review round, all in `jura_growth/`, `prompts/`, `docs/` and `tests/`. The QA branch `crew/apps-idea-command-qa01` with its red tests isn't in this branch, and it isn't meant to ship. |

## Package

| | Item | Note |
|---|---|---|
| n/a | Version bumped | `pyproject.toml` stays at 0.1.0. The repo has no release tags and has never bumped it per PR (operating card, Release). |
| n/a | `CHANGELOG.md` entry | The repo has no changelog. Release notes go in the PR body (operating card). |
| ✅ | Release notes | Below, and in the PR #17 body. |
| ✅ | PR body | `reviews/pr-body.md`, set on PR #17 with `gh pr edit 17 --body-file`. |

## Runtime

| | Item | Note |
|---|---|---|
| n/a | Migrations | None. No `.sql` file and no `migrations/` path in the diff. An older checkout runs unchanged against the same `growth.db`. |
| ✅ | New configuration | None. Nothing under `config/` changes, there are no new environment variables, and `pyproject.toml` and `uv.lock` are unchanged. The command's limits (500 characters, a 60-character name, a 300-character reason, a 30-second lock wait) are constants in code. |
| ✅ | Schedule | `jura-growth schedule install` is **not** needed. The job list and the times are unchanged, and `config/settings.yaml` isn't in the diff. The 06:30 `app-factory` run reads `prompts/app-factory.md` at run time, so the next run after the pull uses the new prompt. |
| ✅ | Dispatch | **No change needed.** `/growth` sends Ting Yu's text verbatim after `--`, and growth's `ALLOWLIST` in `jura_growth/remote.py` is the gate (`docs/dispatch-contract.md`). QA drove the same `shlex.join` and `shlex.split` round trip, and the real `bin/growth-remote`. Optional: if Dispatch keeps its own copy of growth's command list for help or autocomplete, add `apps idea <text>` there so the two stay in step. Dispatch doesn't filter on that copy, so leaving it out breaks nothing. The crew log's first developer entry records only "Dispatch /growth passes free text through, no change needed", and the earlier PR body calls the mirror optional, so the exact Dispatch file isn't named here. Not yet driven: a real `sshd` hop as Dispatch's `dispatch` user (QA, AC7), which only Ting Yu's Mac can do. |
| ✅ | Feature flags | None. The command is live once the pull lands. To keep it off, don't merge. To stop the factory without a revert, run `jura-growth pause app-factory`. |
| ✅ | What to watch | For the first week, or until the first idea has its PRD filed: the reply in Discord after the first `/growth apps idea`; the next 06:30 `#app-factory` message and the run's `OK:` or `SKIP:` line, which should name "Ting Yu's idea <slug>"; digest lines "your idea … wasn't picked first: …"; the events `apps.idea.added` and `apps.idea.held` (`jura-growth status`); and any "refused: the backlog is busy", which should be rare. Also check that a seed-idea PRD isn't filed while one of his ideas waits unheld. |

## Rollback

| | Item | Note |
|---|---|---|
| ✅ | What to revert | If PR #17 is merged with a merge commit, as the history does: `git revert -m 1 <merge sha>` on `main`, through a PR. The range is 8b34f3c..<the release-folder commit> on top of 1206360. Then `git pull --ff-only` and `uv sync` on the Mac. |
| ✅ | What a revert doesn't undo | Listed below. None of it breaks the older code. |

What stays after a revert, and how to handle it:

- **Ting Yu's backlog rows.** Rows with `source: ting-yu`, and any `held`, `held_reason` and notes, stay in `data/growth/app-backlog.yaml`. The older `backlog.load` keeps any row with a name, so they become ordinary ideas. Delete one by hand if it shouldn't be picked.
- **Filed PRDs and their cards.** PRDs already filed from his ideas stay in `prd/pending/apps/`, with their `app-build` requests in #approvals. Skip a card to set it aside, as for any app PRD.
- **Events.** `apps.idea.added` and `apps.idea.held` stay in `growth.db`, which is append-only. Nothing in the older code reads them.
- **The lock file.** `data/growth/locks/app-backlog.lock` stays. It is harmless, and the older code never takes it.
- **The backlog's file mode.** The new atomic save keeps the file's existing mode, so a revert finds the same permissions.
- **Nothing outside the Mac.** The command sends no email and makes no Cloudflare call. Discord gets only the reply and the existing digest.

## Release notes

Ting Yu can now send a toolbox app idea from Discord with `/growth apps idea <text>`, for example `/growth apps idea Site visit report: write up a site visit with photos and a signature, and save it as a PDF`. The idea goes into the app backlog in his own words. The app factory takes his ideas before any other candidate, oldest first, at its 06:30 run. Each idea still has to pass the factory's checks: a rule confirmed at the official source, no near-duplicate, and none of the excluded kinds. When one fails, the factory holds it and says why in the digest and in its run summary, then falls back to the normal pick. Every idea still becomes a PRD that waits for his `app-build` approval in #approvals, and any build still waits for his `app-release` approval. There are no migrations and no config changes, and the schedule doesn't need reinstalling.

## Options for G4

PR #17 is already open, so the "open a PR" option is done. Ship path: a GitHub PR into `main` (operating card).

1. **Merge PR #17 on GitHub with a merge commit.** This is the repo's convention ("Merge pull request #N"). Then run the post-merge commands below on the Mac. **Recommended, once the final re-review of 725f272 approves.** If it asks for changes, a developer round comes first, and this package needs only the new SHA and suite line.
2. **Merge locally into `main` and push.** It does the same thing, but it skips the PR record that every earlier feature has. Not recommended.
3. **Keep the branch and the PR open.** Use this while the final re-review runs, or if you'd rather wait. Nothing changes on the Mac. `main` may move again, but the merge is clean today.
4. **Discard.** Close PR #17 and delete `crew/apps-idea-command`. The live backlog was never touched, so there is nothing to clean up.

## After merge: commands for Ting Yu's Mac

Run these in `/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth`, outside the 06:30 run. The checkout is on `main` at 1206360, so the pull also brings PR #16 (public app previews).

```
git switch main
git pull --ff-only
uv sync
uv run jura-growth apps context --json | grep -A2 ting_yu_ideas
```

The last line is read-only. It should list `ting_yu_ideas` (empty until the first idea). Then send the first real idea from Discord with `/growth apps idea …` and read the reply. `jura-growth schedule install` isn't needed.
