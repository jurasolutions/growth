# Release checklist: mission control and browser publishing

*Branch `crew/mission-control` at 0354503 into `main` at 855e48c (the merge-base). One shared branch
for both features; the browser-publishing feature folder points here. Run 2026-10-27 by the
release manager.*

## Readiness

- ⏳ **`reviews/quality-gate.md` says GO at 0354503.** Not yet: the QA lead's gate runs in
  parallel. The PR body carries a placeholder line for its verdict. **Blocks the merge** until it
  reads GO at this SHA (or at a later SHA the PR is updated to).
- ❌ **Every `reviews/code-review-*.md` approves, `final` included.** `code-review-final.md`
  approves with follow-ups, and its should-fix findings (Sp1 to Sp3, St1 to St3, St8) were fixed
  and merged in 8d6640e. Nine ticket review files end on changes-requested: mc 02 (round 2),
  04, 04b, 06, 08, 10, 10b, bp 03 (round 2) and bp 04. For mc 04 a round-2 approval is recorded
  only in the crew-log (2026-10-25T21:18), not in the file. For the other eight there was no later
  reviewer round: the conductor verified each fix round with the reviewer's own repros before the
  merge (crew-log merge entries). **Waiver for you**, recommended: accept, because the final review covered the merged
  whole and found no blocker.
- ✅ **Up to date with its base.** `git merge-base HEAD origin/main` is 855e48c, which is
  `origin/main`; `git log HEAD..origin/main` is empty. Suite after that: 3305 passed, 0 skipped,
  in 146s (`uv run pytest -rs -p no:cacheprovider -o addopts=""`, temp data and outputs folders).
  The live `growth.db` mtime was 1792927593 before and after; `git status` clean.
- ✅ **No commit touches a blocked path.** `git diff --name-only main...HEAD` matched against
  `inputs/`, `design-system/`, `_ds_bundle`, `.env`, `data/growth` and `.github`: nothing.
- ✅ **No secrets in the diff.** 418 added lines mention secret, token, password or key; a scan for
  value shapes (Resend, Anthropic, Discord webhook, private key, GitHub, AWS, Slack) and for
  `NAME=value` assignments found only test fixtures (`sk-ant-abcdefghijklmnop0123`,
  `sk-ant-secret-value-123`) and the planted UAT value `re_uat_9Xq7Lm2Pz`, which is meant never to
  work. `.env.example` adds three empty entries.

## Package

- n/a **Version bump.** `pyproject.toml` stays 0.1.0: the repo has no release tags, and the last
  release (PR #1) didn't bump either (operating card, Release).
- n/a **`CHANGELOG.md`.** The repo has none; release notes go in the PR body (operating card).
- ✅ **Release notes.** `.scratch/mission-control/release-notes.md`, summarised in the PR body.
- ✅ **PR body.** `.scratch/mission-control/pr-body.md`, via `crew:pr` (the brief names this path
  rather than `reviews/pr-body.md`).

## Runtime

- ✅ **Migrations.** Seven, all forward-only, applied in order on a database built at `main`.
  `app-factory/0003` rebuilds `app_prds` keeping every row and id; the rest add tables, columns,
  indexes and triggers. No down path, because none is needed: checked today, `main`'s code runs
  `status`, `community groups` and `outreach status` on the migrated database without error
  (extracted `main` in the scratchpad, temp data folder).
- ✅ **New configuration and environment variables.** `.env`: `DISCORD_WEBHOOK_APPROVALS`,
  `DISCORD_WEBHOOK_MISSION_CONTROL`, `CONTROL_DISCORD_USER_ID` (in `.env.example` and
  `setup/discord.md`). New `config/publish.yaml`; new keys in `settings.yaml` (`approvals`,
  `retention.browser_transcripts_days`, `one_pager_days`, `run_update`, two jobs), `apps.yaml`
  (`pages_project`), `community.yaml` (`browser`, `joins_per_week`, `post_as`), `social.yaml`
  (`browser` mode, `page_url`). UAT-only variables are listed in `uat.md`. There is one
  environment, the Mac.
- ✅ **Flags and their defaults.** All outward switches are off in committed config: outreach
  `shadow`, `discord_buttons`/`post_buttons`/`dispatch_builds` false, every platform `draft`,
  community `browser: false`, `pages_project: null`. Table in the release notes.
- ✅ **What to watch.** The daily one-pager and `#alerts` for the first week; each first live
  platform day; the first two live outreach weeks (release notes, "What to watch").

## Rollback

- ✅ **Revert range.** `855e48c..0354503` (first commit 1acc1eb, 275 commits, 31 merges). Revert
  the PR's merge commit with `git revert -m 1`, as a PR, after uninstalling the `publish` and
  `one-pager` jobs and setting outreach to `shadow` (MC §5.8).
- ✅ **What a revert doesn't undo.** Published posts, joins and submitted answers, sent emails,
  landing-page releases, moved PRDs, Discord card states, publish transcripts (fall under 30 days),
  and everything outside the repo. Listed with how to handle each in the release notes.

## Gaps (not blocking the merge)

- The browser-publishing setup guide named in bp 01 step 1 was never drafted.
- `uat.md` step 4 still says the UAT SSH entry's exact form waits on the tech lead.
- The three guides in `setup/` are to be copied to `outputs/growth/setup/` after the merge; the
  copies there today are older. Not done here: the brief keeps this run inside the repo.

## Options for G4

The ship path is a GitHub PR into protected `main` (operating card). Merging locally isn't open.

1. **Open a PR** (recommended). The conductor pushes nothing new (0354503 is already on
   `origin`), opens the PR with this body via `gh`, and you merge it once the quality gate reads GO,
   with a merge commit so a single `git revert -m 1` undoes it. Then the steps in the release
   notes.
2. **Merge locally.** Not available: `main` is protected, PR only.
3. **Keep the branch.** Nothing moves. Worth it only if the quality gate comes back NO-GO.
4. **Discard.** Throws away 275 commits of signed-off work. Not recommended, and only on your
   explicit request.
