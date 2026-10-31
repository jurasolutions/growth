# Release: approvals first, feeds after, social depth

```
Recommendation: open the PR, and Ting Yu merges it only after the mode check and his answer on C2
Tested commit:  crew/approvals-first-social-depth @ 9036d1b (base origin/main @ 019133d, 0 commits behind)
Suite:          5967 passed, 0 skipped, at 9036d1b on Python 3.12.14, in a stand-in root (the gate's: the same on 3.14.7, at a43e36a)
Gate:           GO WITH CONDITIONS, at a43e36a
```

This file and `reviews/pr-body.md` are uncommitted, as the brief asked. Committing them adds only records, so the run above stands for the tip.

**Read these first. Each one is something the earlier records get wrong or leave out.**

1. **The gate's C6 now points at the wrong step.** `quality-gate.md` says "Skip `uat.md` L1 step 4", which meant moving the ICP draft. `9036d1b` renumbered L1, so step 4 is now the env file mode check, the one step that must not be skipped. I can't edit the gate from here. The PR body says this outright, and C6 now means L1 step 6.
2. **"Skip it" in L1 step 5 didn't say how, and Terminal can't do it.** `jura-growth skip A-0001` in the stand-in printed `refused: decisions aren't taken in Terminal: approve or skip it in #approvals.`, exit 2. A row found by that query has no card to press, so the PR body says to send `/growth skip A-nnnn` in Discord. `uat.md` still reads "Skip it". `tests/test_outreach_decisions.py` and `tests/test_publish_queue.py` cover a skip after approval, and `decide()` allows one until the claim.
3. **The live checkout runs Python 3.12, and every run recorded on this branch was on 3.14.** The worktree's `.venv` is 3.14 and the live checkout's is 3.12. The gate's run was on 3.14.7. I ran the tip on 3.12.14, with the result under "Evidence".
4. **An edited `social.yaml` blocks the revert's pull.** In a temp clone, with `publish_mode: draft` left uncommitted, the update stopped with "Your local changes to the following files would be overwritten". The two rollback routes therefore collide unless he restores the file first. It's in the rollback steps below and in the PR body.
5. **Ticket 12 still says the prospect's word is "unconfirmed".** The gate's probe settled it: the prospect gets the real word. The PR body uses the gate's result.
6. **The samples predate one small style change.** `reviews/samples/` was committed at `be96ff1`. `card.css` and `visuals.py` have changed since: caption tracking, uppercase captions and a measure variable. The gate's 34 fresh renders are in the session scratchpad only. The PR body says the samples are older, and Part P draws current ones.
7. **The operating card is still stale on two points.** The gate's X12 row 13 names suite size, Python and pyright, and `9036d1b` corrected only suite size. This is minor and the conductor's to tidy.

## Readiness

| Item | Result | Note |
|---|---|---|
| Quality gate says GO at the current SHA | **No, waiver W1** | GO WITH CONDITIONS at `a43e36a`, and the tip is `9036d1b`. `git diff --stat a43e36a HEAD` shows only `.scratch/` records and one row of `docs/agents/crew.md`, so no code moved. The conditions are his |
| Every `code-review-*.md` approves, `final` included | **No, waiver W2** | `03` and `13` approve. `01`, `02`, `10`, `11` and `final` read changes-requested. The gate traces every blocker to its close (its "Ruling on X13") and rewrites the check as A3. That is a correction he has to accept. It doesn't change the files |
| Up to date with its base, and the suite green after that | Yes | `git ls-remote` shows `main` at `019133d` and the branch at `9036d1b`. `origin/main` is an ancestor of the tip, 0 behind and 74 ahead. Suite under "Evidence" |
| No commit touches a blocked path | Yes | 224 files in `git diff --name-only origin/main...HEAD`, none under `data/`, `inputs/`, `design-system/`, `.github/` or `launchd/`, and no `.env` |
| No secrets or credentials in the diff | Yes | The checklist's grep gives 58 added lines. Outside tests, docs and records there are 3, all the `REDACTED` constant and its comment. A search for real webhook, Resend, Anthropic, GitHub, AWS and private-key shapes over the whole diff gives 0. The fakes in `uat.md`, such as `re_uat_9Xq7Lm2Pz`, are meant to never work |

## Package

| Item | Result | Note |
|---|---|---|
| Version bumped per convention | n/a | `pyproject.toml` stays at 0.1.0, as the card records, with no tags. No diff in `pyproject.toml` or `uv.lock` |
| `CHANGELOG.md` entry | n/a | The repo has none. The card says release notes go in the PR body |
| Release notes for users | Yes | In the PR body |
| PR body | Yes | `reviews/pr-body.md`, opening with "What merging switches on" and ending with the requested lines. No `@` in it |
| Gate's "for the conductor, before the PR" | Yes | `uat.md` L1 and PRD §5 now hold the mode check and S2's query, and no longer move the draft over `inputs/icp.md`. I read both at the tip |

## Runtime

| Item | Result | Note |
|---|---|---|
| Migrations | n/a | None. No file under any `migrations/` folder changes, and no added line in `jura_growth/` creates, alters or drops a table, index or trigger. An older checkout runs against the same `growth.db` |
| New configuration or environment variables | Yes | No new environment variables in `jura_growth/`. `config/social.yaml` gains `words`, `carousel`, `min_items`, `needs_visual` and `min_hosts` per theme, and `chars_max` for Instagram, documented in `docs/social.md`. The one environment is the Mac's checkout |
| Feature flags | Yes | `publish_mode`, per platform, now `browser` on Facebook and Instagram. `community.browser` stays `false`, and must until ticket 12. `approvals.dispatch_builds` is on, set by growth PR #15, not by this branch |
| What to watch | Yes | Below |

### What to watch

**The morning after the restart, and two days on (`uat.md` L2):** the one-pager arrives at 09:00, the social run update says about 07:30, and after two days "Needs you" has no line about hours off. This is the only real test of the 9-hour finding.

**Until the first post on each platform has gone out (L3 to L5):**

- The post on the Page matches the card word for word, with its image. Instagram's slides are in order.
- `#alerts` for a browser or read-back failure.
- `uv run jura-growth publish queue`. An item in `unknown` pauses publishing and names `/growth publish resolve`.
- `data/growth/launchd/publish.log` and `digest.log`.

**Through the first two weeks:**

- Any warning, limit or restriction from Meta on the Page, the Instagram account or his personal profile. It is the risk he accepted, and no code here would notice it. Stop with `pause publish` and read it first.
- `#outreach-sent` and #approvals for masked cards, since the ICP means real outreach cards can now appear. Any card showing "[name removed]" means reading `jura-growth outreach preview <id> --html` before deciding.
- How often the masked-word refusal drops a platform's day. The accepted cost in `code-review-02.md` assumed it would be rare.

## Rollback

**To stop all posting at once:** `uv run jura-growth pause publish`. Every claim stops, and approvals stay unused. `uv run jura-growth resume publish` undoes it.

**To put one platform back on hand posting:** in `config/social.yaml` on the Mac's checkout, set `publish_mode: draft` under `facebook:` or `instagram:`.

- It needs no reinstall, because each run reads the file.
- A waiting card stays live until it lapses at 18:00 and posts nothing. Approving it refuses the claim, and the feed line says so.
- The next social run gives that platform's text and "post it by hand" in #social-drafts, with no card.
- Rehearsed in `uat.md` S10, which he hasn't run.
- This leaves the checkout dirty. Run `git restore config/social.yaml` or commit the change before any `git pull` that touches that file, or the pull refuses.

**To revert the whole thing:** merge with a merge commit, as PRs #16 to #20 were. Then use GitHub's Revert button or `git revert -m 1 <merge commit>`. The branch's own range is `019133d..crew/approvals-first-social-depth`, from `a6c2cca` to the tip. In a temp clone, the merge and `git revert -m 1` both went through without conflict, and the tree after the revert is identical to `019133d`, with `publish_mode: draft` on both platforms and the digest at 17:30.

Then, on the Mac, from `repos/growth`:

```bash
uv run jura-growth pause publish    # only if it's between 09:00 and 18:00
git restore config/social.yaml      # only if you edited it
git pull && uv sync
uv run jura-growth schedule install
uv run jura-growth resume publish   # only if you paused it
```

**What `schedule install` does for the digest.** It renders every job in the current list from `config/settings.yaml`, writes each plist to `~/Library/LaunchAgents`, and runs `launchctl bootout` and `bootstrap` on each. After the revert, the digest's plist goes back to 17:30. Without it, the digest stays at 18:05 and the one-pager lists it as "installed but out of date", which does no other harm. The bootout stops any job that is mid-run, and a publish run stopped with a claim open leaves that item `unknown` and pauses publishing, which is why the steps pause it first. No job is added or removed on this branch, so no `schedule uninstall` is needed. I read this in the code and didn't run it, because the card forbids it.

**If he reverts and later wants it back,** the same branch won't merge again without reverting the revert first.

**What a revert doesn't undo:**

| Left behind | What to do |
|---|---|
| Posts already published on Facebook or Instagram | Delete by hand, on the Page or the account. The run update in #social-drafts gives each address |
| Any warning or restriction Meta has placed on an account | It stays. Only Meta can lift it |
| Emails already sent | They can't be recalled. A reply follows the normal route |
| Cards and feed lines in Discord | They stay. A waiting card lapses or is decided as usual |
| App PRDs already handed to Dispatch, and their branches | They stay. A release still needs its own approval |
| Migrations | None to undo |
| `inputs/icp.md` | It stays, so research and outreach cards keep coming. `uv run jura-growth pause scout` stops research. Removing the file is his call |
| `chmod 600` on `.env`, and the restart | They stay. Both are harmless |
| Rows in `growth.db`, and files under `outputs/growth/social/` | They stay. The schema is unchanged, so older code reads them. Nothing to do |

**A revert also brings back what this branch closes.** A typed approval with no card works again for social and outreach. "We helped 62 marketing teams." passes the numbers rule again. The outreach no-card route matters most here, because outreach stays live.

## Waivers for Ting Yu

Merging accepts all of these, and the PR body says so.

- **W1.** The gate's GO has conditions and sits at `a43e36a`, with only records and one doc row after it.
- **W2.** Five review files read changes-requested. The chain of closes is in the gate, under A3.
- **C1.** A1 to A4. Refusing one means no-go until the fix beside it is done.
- **C5.** Ticket 12, the three known limits of the numbers rule, and `community.browser` off until ticket 12. Refusing the outreach half puts ticket 12 first. Refusing the number limits means no-go.
- **C7, X15.** No UAT part has been run by him. This one is his alone, and the crew can't grant it.
- **PRD §7 reads "not signed",** and code was drafted before the PRD. After merge and acceptance, the PRD moves to `prd/done/` with the ship date at the top.

**Not waivers. These must be true:**

- **C2.** `inputs/icp.md` at 01:38 on 2026-11-01 was his own step. The file still reads 01:38:12 and 2,527 bytes. If it wasn't his, it's no-go until explained.
- **C3.** The mode check prints `600`, or he fixes it. No agent has looked at that file for this release, or may.

**Carried minors,** from the gate's X12, each with an owner there: F1, F2, S2, ST-S2, and the "Growth is on it" listing of a refused card.

## Checklist items not met

| Item | Status |
|---|---|
| Gate says GO at the current SHA | Waiver W1 |
| Every code review approves | Waiver W2 |

Every other item is met or n/a. Nothing blocks the package. What holds the merge is his: C1, C2, C3, C5 and C7.

## Options for G4

The ship path on the card is a GitHub PR from `crew/approvals-first-social-depth` into `main`. Merging is Ting Yu's, in every option. The branch is pushed at `9036d1b`, and nothing was pushed for this release.

| Option | What happens next | View |
|---|---|---|
| **Open a PR** | He opens it with `reviews/pr-body.md`, runs the mode check, answers C2, and merges with a merge commit. Then the steps in the body, then `uat.md` L2 to L5 | **Recommended.** It's the card's path, it puts the switch-on and the incidents in front of him, and opening it changes nothing live. If he has time, Part P before merging, since it touches nothing real |
| **Merge locally** | He merges into local `main`, reruns the suite and pushes. The steps are the same | Not recommended. It skips the PR body as the place he reads this, and the crew may not do it |
| **Keep the branch** | Nothing changes. Social stays on hand posting and the jobs keep firing early. Outreach cards can still reach #approvals, with the no-card route open. If `main` moves, the branch needs merging again and a fresh suite run | Reasonable if he wants ticket 12 first, or wants to run UAT before merging |
| **Discard** | The branch and the worktree are deleted, only if he asks in so many words and types the confirmation | Not recommended. Listed because the checklist asks for all four |

## Evidence

| Command | Result |
|---|---|
| `git ls-remote origin main crew/approvals-first-social-depth` | `019133d`, `9036d1b` |
| `git merge-base --is-ancestor origin/main HEAD`; rev-list counts | Ancestor; 0 behind, 74 ahead |
| `git diff --stat a43e36a HEAD` | 8 files: `.scratch/` records and `docs/agents/crew.md` |
| `git diff --name-status origin/main...HEAD`, filtered for migrations and SQL | Nothing |
| Added lines in `jura_growth/` with `CREATE`, `ALTER` or `DROP` of a table, index or trigger; with `environ` or `getenv` | Nothing; nothing |
| Added lines in the whole diff shaped like a real credential | 0 |
| Temp clone: merge `--no-ff`, `git revert -m 1`, `git diff --quiet 019133d HEAD` | Clean, and identical to `019133d` |
| Temp clone: revert with `config/social.yaml` edited | Refused, "Your local changes ... would be overwritten" |
| L1 step 5's query on a freshly migrated temp database | Exit 0, no rows, so the columns exist |
| `jura-growth skip A-0001`, temp data, in the stand-in | `refused: decisions aren't taken in Terminal`, exit 2 |
| `ps`, `ls -la /etc/localtime`, `uptime` | `UserEventAgent (Aqua)` since 28 Sep 00:42; `/etc/localtime` to Singapore on 1 Oct; up 34 days, so no restart yet |
| `stat` on `inputs/icp.md` | 2026-11-01 01:38:12, 2527 bytes |
| `uv run --frozen --offline --python 3.12 pytest -rs -rfE -q -p no:cacheprovider -o addopts="" --tb=short` at `9036d1b`, stand-in root | 5967 passed in 377.44 s. Junit: 5967 tests, 0 failures, 0 errors, 0 skipped. 22 opens of a file named `.env`, all planted under `pytest-of-tingy/`: the canary 0, the live path 0. Stand-in `claude` log never created |
| The gate's full suite at `a43e36a`, stand-in root, Python 3.14.7 | 5967 passed, 0 failed, 0 skipped, 365.62 s (`quality-gate.md`, "Fresh run") |

**How the stand-in was built:** as the gate did, `git archive 9036d1b` under a scratchpad `jurasolutions/repos/growth`, copies of `design-system/` and `prd/`, a canary `.env`, its own offline `uv sync --frozen`, `JURA_ROOT` unset, temp data and outputs, a stand-in `claude` first on `PATH`, and an audit hook logging opens of files named `.env`.

**Boundaries, as they went.** I wrote only this file and `reviews/pr-body.md` in the worktree, and my scratch work is in the session scratchpad. I did not read, grep, count, stat or chmod the live `.env`. I did not run `git status` in the main checkout, because that scans its folder, so I didn't check whether it's clean. `git worktree list` shows it on `main` at `019133d`. Nothing was posted, sent, pushed, committed or tagged, and I ran no `jura-growth run` and no `schedule` command. The suite exercises `schedule.render` under its own temp folders, as the gate's did.
