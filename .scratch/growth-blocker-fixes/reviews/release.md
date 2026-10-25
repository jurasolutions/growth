# Release: growth-blocker-fixes

Branch `crew/growth-blocker-fixes` at db218a0, base `main` at 6eabfe7 (local and `origin`).
Prepared 2026-10-25 by the release manager. Nothing has been pushed, merged or tagged.

## Checklist

### Readiness

| Item | Mark | Note |
|---|---|---|
| `reviews/quality-gate.md` says GO at the current SHA | ❌ (waiver) | No quality gate was run. This was a bug-route delivery, and the conductor skipped the separate QA phase because the audit had already reproduced every blocker (`crew-log.md`, 2026-10-24T22:20). The evidence that stands in for it: each audit reproduction is now a regression test, and the suite is green at db218a0. Ting Yu waives this at G4 or asks for a gate first. |
| Every `reviews/code-review-*.md` approves, `final` included | ❌ (waiver) | 01, 02, 03, 05, 06, 08 and final approve. The last written verdict for 04 (round 2) and 07 (round 3) is changes-requested. Their final fix rounds (04: f8eb442; 07: a8e33b1) were verified by the conductor, not re-reviewed, and the final review then approved the merged tree with both inside. Ticket 09 has no review file; the conductor verified it. Ting Yu waives this at G4 or asks for a round-3 review of 04 and a round-4 review of 07. |
| Branch up to date with its base; suite green after that | ✅ | `git merge-base main HEAD` is 6eabfe7, the same as `main` and `origin/main` (`git ls-remote origin` shows 6eabfe7). `uv run --frozen pytest` at db218a0 gives 987 passed in 21.82s. |
| No commit touches a blocked path | ✅ | `git diff --name-only main...HEAD` lists nothing under `inputs/`, `design-system/` or `data/growth/`, no `.env*` file and no `_ds_bundle.js`. The final review checked the same. |
| No secrets, `.env` files or credentials in the diff | ✅ | The secret grep over the diff finds only code that handles secrets and test or audit fixtures with fake values (`re_FAKEKEY123`, `https://discord.com/api/webhooks/111/FAKE...`). No real webhook, key or token. |

### Package

| Item | Mark | Note |
|---|---|---|
| Version bumped per the repo's convention | n/a | The repo has no bump convention yet: `pyproject.toml` and `jura_growth/__init__.py` say 0.1.0, which has never changed, there are no tags, and nothing installs or reads the version. Recommendation: keep 0.1.0 in this PR. If Ting Yu wants to start tagging, make it 0.2.0 on `main` after merge, because operators see changed behaviour (groups closed until days are set, stricter numbers rule, `.env.example` refused). |
| `CHANGELOG.md` entry | n/a | The repo has no changelog. Per `docs/agents/crew.md` "Release", release notes go in the PR body. |
| Release notes for users | ✅ | In the PR body: four release notes and the follow-up list. |
| PR body via `crew:pr` | ✅ | `.scratch/growth-blocker-fixes/pr-body.md` (the brief puts it there rather than under `reviews/`). |

### Runtime

| Item | Mark | Note |
|---|---|---|
| Migrations: forward tested; down path or a reason there is none | ✅ | Forward: the final review built a database at `main`, opened it with the branch, saw each migration applied once with the rows intact, and saw `main`'s code still run on the migrated file. There are no down files, because the migration runner only goes forward and both migrations are additive and ignored by older code. A manual down is written below for completeness. |
| New configuration or environment variables documented | ✅ | New config: `free_mail_contacts` in `config/scout.yaml` (it can shorten the code's ceiling, never extend it). Changed: `config/community.yaml` `blocked_fetch_domains` is now the only list, and the WebFetch denials in `config/settings.yaml` are gone. New environment variables: `JURA_GROWTH_PLIST_DIR` and `JURA_GROWTH_PROMPTS_DIR`, for tests only, documented in `README.md` and set by `tests/conftest.py`. Nothing to set in production. |
| Feature flags and their default state | n/a | No flags. The closest is outreach `mode` in `config/scout.yaml`, which stays at shadow. This change doesn't touch it. |
| What to watch after release, and for how long | ✅ | See "After release" below. Watch for one week, so that every weekly job runs once. |

### Rollback

| Item | Mark | Note |
|---|---|---|
| Revert range or PR to revert | ✅ | The PR's merge commit, reverted with `git revert -m 1 <merge sha>`. The commit range is 6eabfe7..db218a0 (60 commits, first 9ee2d89), plus the release-record commit if Ting Yu makes it. |
| Data and side effects a revert does not undo | ✅ | See "Rollback plan" below. |

### Options for G4

| Item | Mark | Note |
|---|---|---|
| Merge locally / open a PR / keep / discard, with a recommendation | ✅ | See "Options for G4" below. Recommendation: open a PR. |

## Migrations on a live `growth.db`

`db.connect()` migrates on open, so the first `jura-growth` command run on the new code applies these. Core goes first, then each plug-in in name order (apps, community, outreach, scout, social), and files within a set run in filename order. Each file and its `schema_migrations` row commit together.

1. `core/0002_sync_cursors.sql` creates the `sync_cursors` table (name, position, marker, updated_at). It holds no rows until the first D1 sync.
2. `community/0002_confirmed_days.sql` adds `promo_days_confirmed` and `post_days_confirmed` to `community_groups`, both NULL, which means not confirmed. From then on every group stays closed until its days are set.

Already applied on the live file, and not part of this change: `outreach/0002_requeue_shadow.sql`. The audit (`audit/infra.md` A5) found a leftover `growth.db-journal` around it. If that journal is still there, run one `jura-growth status` on the current code first, so SQLite rolls it back and re-applies 0002 cleanly, and confirm the journal has gone before upgrading.

**Manual down**, only if a clean undo is ever wanted. It isn't needed for a revert, because `main` ignores both. Run it after a backup and with every agent paused:

```bash
sqlite3 /Users/tingy/OneDrive/Desktop/projects/jurasolutions/data/growth/growth.db <<'SQL'
BEGIN;
DROP TABLE sync_cursors;
ALTER TABLE community_groups DROP COLUMN promo_days_confirmed;
ALTER TABLE community_groups DROP COLUMN post_days_confirmed;
DELETE FROM schema_migrations WHERE id IN ('core/0002_sync_cursors.sql', 'community/0002_confirmed_days.sql');
COMMIT;
SQL
```

This drops the days you confirmed. `DROP COLUMN` needs SQLite 3.35 or later, which macOS has.

## Before the upgrade (Ting Yu's steps, outside the code)

- **Monday's social run.** `audit/infra.md` A6 is still marked not done. Three frozen-clock test drafts dated 2026-10-26 sit in the live `growth.db`, so a real social run on Monday 2026-10-26 would skip. The launchd jobs aren't installed yet (`launchctl list` shows no Jura jobs), so nothing runs tomorrow unless you install them first. Either delete those rows before installing, or accept one skipped Monday.
- **Website D1 table.** Make it append-only before you set the D1 settings in growth (release note 2).

## After release: what to watch, for one week

- `uv run jura-growth status`: no unexpected pauses, and no job left failed.
- #alerts and the Discord outbox (`data/growth/discord-outbox/`): an outbox file means Discord was unreachable when a post was due.
- Headless transcripts: permission denials. A denied `jura-growth` command means a prompt names a command its job isn't allowed. Ticket 09 aligned the preamble, but the prompts are the source.
- The #community summary and `community groups --joined`: every joined group shows "no post until Ting Yu confirms the open days" until you set them.
- The digest and the brand-check failures on social drafts: number words now fail, so expect a few more regenerations in the first week.
- Outreach `scout-sync`, once D1 is configured: a sync that fails on its cursor pauses outreach. The recovery is in `docs/scout.md` ("To recover once the site's table is right again").

## Rollback plan

1. **Stop the jobs while you decide:** `uv run jura-growth pause all --reason "rolling back the blocker fixes"`. Or `jura-growth schedule uninstall <job>` for one job.
2. **Revert through a PR**, because `main` is protected. Use the "Revert" button on the merged PR, or:
   ```bash
   cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
   git fetch origin && git checkout -b revert-growth-blocker-fixes origin/main
   git revert -m 1 <merge sha>
   git push -u origin revert-growth-blocker-fixes
   gh pr create --repo jurasolutions/growth --base main --title "Revert the growth blocker fixes" --body "Reverts the growth blocker fixes PR."
   ```
   After it merges: `git checkout main && git pull --ff-only && uv sync`.
3. **What a revert doesn't undo:**
   - The two migrations stay recorded, along with the `sync_cursors` table and any confirmed days. `main` ignores them. If the fixes are merged again later, the migrations aren't re-applied and the confirmed days come back. Use the manual down above only if you want them gone.
   - On reverted code, the old day-rule parser plans community posts again, including on forbidden days (the original bug). Keep `community` paused until the fixes are back.
   - The old D1 sync reads the suppression table by `email_hash`. If the website table has already moved to the append-only contract, the old sync may fail or miss complaints. Keep `outreach` paused (it is in shadow mode anyway).
   - The old code lets a headless run read `.env` again. Don't run any `claude` job on reverted code.
   - Discord posts already delivered, outbox files, transcripts, log events and contact rejections recorded by the new code all stay. No email has been sent, because outreach is in shadow mode.

## Options for G4

The repo's ship path is a GitHub PR from `crew/growth-blocker-fixes` into `main` on `github.com/jurasolutions/growth` (`docs/agents/crew.md` "Branches"). `gh` isn't logged in on this Mac yet. The release files (this file, `pr-body.md` and the crew-log entry) are written but not committed. Every option starts by committing them, so the record lands with the branch:

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
git add .scratch/growth-blocker-fixes/reviews/release.md .scratch/growth-blocker-fixes/pr-body.md .scratch/growth-blocker-fixes/crew-log.md
git commit -m "Record the release checklist and PR body for the blocker fixes"
```

### 1. Open a PR (recommended)

This is the repo's ship path, and it gives a revertable merge commit.

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
gh auth login --hostname github.com --git-protocol https --web
git push -u origin crew/growth-blocker-fixes
gh pr create --repo jurasolutions/growth --base main --head crew/growth-blocker-fixes \
  --title "Fix the blocking findings from the growth engine audit" \
  --body-file .scratch/growth-blocker-fixes/pr-body.md
```

When you're happy with it, merge with a merge commit, not a squash, so the ticket merges stay readable and the revert stays one command:

```bash
gh pr merge <number> --repo jurasolutions/growth --merge
```

Then upgrade the checkout the engine runs from:

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
uv run jura-growth backup                      # on the current code, before switching
git checkout main && git pull --ff-only
uv sync
uv run jura-growth db migrate                  # expect core/0002_sync_cursors.sql and community/0002_confirmed_days.sql
uv run jura-growth community groups --joined   # then, for each group:
uv run jura-growth community set <id> promo_days=<days> post_days=<days>
uv run jura-growth status
git branch -d crew/growth-blocker-fixes crew/growth-blocker-fixes-01-headless-secrets \
  crew/growth-blocker-fixes-02-community-blocks-facebook crew/growth-blocker-fixes-03-auto-pause-without-discord \
  crew/growth-blocker-fixes-04-numbers-rule-words crew/growth-blocker-fixes-05-outreach-complaints-warmup-spacing \
  crew/growth-blocker-fixes-06-contact-domain crew/growth-blocker-fixes-07-community-negated-days \
  crew/growth-blocker-fixes-08-tests-never-touch-live-files crew/growth-blocker-fixes-09-final-review-tidy
```

No launchd jobs are loaded today, so nothing runs during the switch. If you install any before merging, run `uv run jura-growth pause all` before `git checkout main`, and `uv run jura-growth resume all` after setting the days.

### 2. Merge locally

This works, but it goes around the repo's ship path and pushes straight to the protected `main`. Not recommended.

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
uv run jura-growth backup
git checkout main && git pull --ff-only
git merge --no-ff crew/growth-blocker-fixes -m "Merge the growth blocker fixes"
uv sync && uv run pytest                        # must stay at 987 passed
gh auth login --hostname github.com --git-protocol https --web
git push origin main
```

Then follow the same `db migrate`, `community set` and branch clean-up steps as option 1.

### 3. Keep the branch

Nothing moves. The branch stays at db218a0 locally, unpushed, and the live engine stays on `main`'s code with every audited defect in place. Choose this if you want the quality gate, or a re-review of 04 and 07, before deciding.

```bash
# nothing to run; optionally back the branch up to GitHub without opening a PR:
gh auth login --hostname github.com --git-protocol https --web
git push -u origin crew/growth-blocker-fixes
```

### 4. Discard

This deletes nine tickets of reviewed work, and the engine keeps every defect. Not recommended. It only goes ahead if you ask for it in so many words and then type `discard` to confirm.

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
git checkout main
git branch --list 'crew/growth-blocker-fixes*' | sed 's/^[* ]*//' | xargs git branch -D
```

This deletes the feature branch and the nine ticket branches. Run `git branch --list 'crew/growth-blocker-fixes*'` on its own first to see what will go.

**Recommendation: option 1, open a PR.** Waive the missing quality gate and the conductor-verified final rounds of 04 and 07: the final review approved the merged tree, and the suite is green at db218a0. Keep 0.1.0.
