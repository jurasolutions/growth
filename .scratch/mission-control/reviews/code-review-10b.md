# Code review: ticket 10b (MC-10b, app releases wait for a second approval, bound to the commit)

- **Branch:** `crew/mission-control-10b-app-release` at `aff885e` (7509ecc, d7174ff, 5151c82, 947b2b5, 878635b, 2023439, aff885e)
- **Compared against:** merge-base `4cc477e` (`git diff 4cc477e...crew/mission-control-10b-app-release`), 13 files, +1324 / -36
- **Spec:** `prd-jura-mission-control-2026-10-25.md` SC9 (AC-M9.7 to AC-M9.9), §5.7 `app-release` row, §5.9 steps 3 and 4, §4.6 A6, §6 Q4, the 2026-10-26 amendment; ticket `issues/10b-app-release.md`; `reviews/test-strategy-v3.md` row MC-10b, X2, X3, sweep
- **Outside the repo:** `jurasolutions/prd/templates/prd-app-template.md` matches the change quoted in 7509ecc (line 6 and §7), and `prd.py`'s `BUILD_LINE`, `BUILD_RE` and `PROCEED` match it.
- **Reviewer:** crew reviewer, 2026-10-27. The Standards and Spec axes ran as two parallel sub-agents; the security pass was run inline on this diff (the `security-review` skill reads the checked-out branch, which is the feature branch, not 10b). Every changed file was read.

## Verdict: changes-requested

One blocking finding: `--preview` accepts text that renders a clickable non-`pages.dev` link on the `app-release` approval card (B1, reproduced). Everything else is should-fix or nit.

The three things the brief asked to be checked hold:

- **Production needs a second, separate approval of exactly the built SHA.** `released` requires the latest `app-release` record to be claimed (`used_at`) and its content hash to equal `encode(row)` over app id, task, branch and full SHA (`releases.py:304-311`). `release-plan` claims through `approvals.use`, which re-computes the content first (`approvals.py` `_refresh`). The `app-build` approval is a different kind and is never accepted in its place.
- **A SHA can't be spoofed into a release.** `SHA_RE` takes only 40 or 64 lower-case hex characters; a new SHA, branch or task supersedes the live request (tested), and a claimed request for another commit is refused by `released`.
- **The release plan merges only the approved SHA.** `merge_plan` prints `git merge --no-ff … <full sha>` from the claimed row; the branch is `shlex.quote`d and constrained by `BRANCH_RE`, the task by `TASK_RE`, and `app_id` comes from a stored build row. No shell metacharacter reaches the printed commands (the branch `claude/T-0031 paynow; rm -rf ~` and `-delete` are refused in the branch's own tests).

What is not bound is the preview link, which B1, S1 and S2 below are about.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest` in the developer worktree (`JURA_ROOT` set, temp data and outputs dirs) | 2238 passed in 161s; `git status --short` empty before and after |
| `uv run pytest tests/test_app_releases.py` | 34 passed |
| `git merge-tree --write-tree` against `crew/mission-control` (`fec69b8` named in the brief, and the current tip `abe16b0`, which now includes ticket 09) and against `crew/mission-control-05-group-rules-kind` (`c6a4e79`) | all clean; no other branch adds an `apps/0004` migration |
| `uv run pytest` on the trial merge with `abe16b0` (detached scratch worktree) | 2308 passed in 128s |
| Reviewer probes (run in a scratch worktree at `aff885e`; kept at `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/rv10b-review-probes.py`, not on the branch) | 5 of 5 reproduce: B1, S1, S2, S3, N1 |
| `pyright` on `jura_growth/agents/apps` (Standards sub-agent) | 0 errors |
| Blocked paths | no change under `inputs/`, `design-system/`, `.env` or the live `data/growth/`; the landing-page repo is only read (`merge-base`, `rev-parse`), and a test asserts every git call is under `tmp_path` |

## Security

### Blocking

- **B1. A masked link in `--preview` reaches the approval card.** `releases.py:191-195` checks the scheme, the host suffix and the absence of credentials and port, but not the path, so whitespace and Markdown pass. `check_build`'s docstring says it refuses what can't be "shown on its card", and the card prints the value raw (`releases.py:130`). Reproduced: `apps built APP-101 … --preview "https://x.jura-site.pages.dev/ [open the preview](https://evil.example/login)"` exits 0, and the posted card reads `Preview: https://x.jura-site.pages.dev/ [open the preview](https://evil.example/login)`. Discord renders that as a clickable "open the preview" link to `evil.example`. This is the card Ting Yu opens to judge the release, and the previews sit behind a Cloudflare Access login (§6 Q4), so a look-alike login page there is a credible phishing path. `--preview` comes from Dispatch, which relays a build agent's output, and from `remote` once ticket 11b lands. **Fix:** full-match the whole URL against a strict pattern (for example `https://[a-z0-9-]+(\.[a-z0-9-]+)*\.pages\.dev(/[A-Za-z0-9._~/-]*)?`, with no whitespace, `[]()<>` or backticks), and add the probe as a parametrised case in `test_built_refuses_what_it_cannot_bind_or_show_safely`.

### Should fix

- **S1. Any `*.pages.dev` project is accepted.** `releases.py:193` checks only `host.endswith(".pages.dev")`, and anyone can create a Pages project. Reproduced: `--preview https://not-jura.pages.dev` exits 0. AC-M9.7 names `https://<branch>.<project>.pages.dev`. **Fix:** pin the suffix to the landing-page project (a setting next to `paths.site_repo()`, or a constant), so the card can only link to Jura's own previews.
- **S2. The preview can be swapped after approval without asking again.** The preview isn't part of the request's content (`encode`, `releases.py:66-70`, which follows the §5.7 row), and `report_built` overwrites `preview_url` on a `built` row (`:217-221`). Reproduced: after A-0002 is approved, `apps built` with the same SHA and `--preview https://attacker-project.pages.dev/` exits 0 with "It is approved", and the row and the one-pager now show the new link. What gets merged is still the approved SHA, so this doesn't change the release, but the record no longer shows what was approved. **Fix:** refuse a different preview for the same content while a request is live or claimed, or add the preview to `encode` so that changing it supersedes the request.
- **S3. `on_main` resolves the ambiguous name `main`.** `releases.py:102` passes `main`, which git resolves to `refs/tags/main` before `refs/heads/main`. Reproduced: with the claimed SHA only on the task branch, `git tag main <sha>` in the landing-page repo makes `apps released` record the release, although branch `main` doesn't contain it. `site_ready` already uses `refs/heads/main` (`:95`). **Fix:** use `refs/heads/main` in `on_main`.

### Nit

- **N1. A SHA already on `main` releases without a merge.** Reproduced: `apps built` with the landing-page repo's current `main` head, then approve and `release-plan`, then `released` records a release and moves the PRD, although nothing was built or merged. This still takes both approvals, so it's a nit. `apps built` could refuse a SHA that `main` already contains when the repository is readable.
- **N2. The preview is the branch alias, not the commit.** AC-M9.7's `https://<branch>.<project>.pages.dev` shows the branch's latest deploy, which can be newer than the SHA on the card. A line on the card ("the preview shows the branch's latest push; the release is commit `abc1234`") would stop a reviewer assuming they match.

## Standards

The Standards sub-agent found no hard violation. The branch keeps within the blocked paths and raises no cap, `pyright` reports nothing new, and all seven commit messages are plain sentence-case imperatives.

### Should fix

- **S4. The one-pager ignores `use_by` (ADR 0002).** ADR 0002 says: "Lapsed approvals are shown as lapsed by comparing their deadlines with the clock." `releases.py:393-397` labels any approved, unused record "App release approved: run `jura-growth apps release-plan …`" without comparing `use_by` with the clock. Between the use-by and the expiry job, the one-pager tells Ting Yu to run a command that will refuse. `mission.py:362` shows the comparison to copy.
- **S5. Reuse: new code duplicates existing helpers.**
  - `AppRelease.deadlines` (`releases.py:138-142`) repeats `AppBuild.deadlines` (`builds.py:93-97`) line for line.
  - `app_name` (`releases.py:73-78`) repeats the name lookup in `builds.open_handoffs` and `builds._file_name` (`builds.py:210-218`).
  - `_day` (`releases.py:345-346`) repeats the expression at `builds.py:313`.
  - `claimed_release` (`releases.py:405-410`) and `health_lines` (`:387`) re-implement `approvals._latest` in raw SQL, then convert the result back through `approvals.get(conn, approvals.format_id(...))`.

  Share one deadlines helper and one name lookup. Expose `approvals.latest()` and use it here (and in `builds.py:306`).

### Nit

- **N3. `release_planned_at` copies the claim (ADR 0003).** ADR 0003 says plug-in tables hold their item's lifecycle "and never a copy of the decision". `release_planned_at` (migration 0004, `releases.py:255`) mirrors `approvals.used_at`, and only tests read it. Drop it, or record in the ADR why it counts as lifecycle.
- **N4. The glossary isn't updated (`docs/agents/domain.md`).** `CONTEXT.md` still defines a build handoff as the row written when an app-build approval is claimed. That row now also carries `built` and `released`, and the health strip entry doesn't list the new release lines.
- **N5. Small idioms.** `{approvals.SKIPPED: "skipped"}.get(...) or (...)` (`releases.py:399-400`) is a one-entry dict used as an `if`. `subject()` (`:48-49`) only delegates to `builds.subject`. `health_lines` probes the columns with `PRAGMA table_info` (`:380`), where `builds.health_lines` probes `sqlite_master` (`builds.py:285`).

## Spec

The Spec sub-agent found AC-M9.7 to AC-M9.9, AC-M4.3 (claim before print, checked at call time by the gate adapter), X2 (7 and 14 days under three time zones), X3, and the sweep over the release card and its edits all implemented and tested. The test asserting that the git path is under `tmp_path` exists (`test_app_releases.py:309`). `release-plan --json` is correctly left out: §4.8 D7 and §5.9 step 4 mark it as later.

### Should fix

- **S6. The backlog isn't updated when the PRD is missing.** §5.9 step 4 says "… and updates the backlog". `backlog.release` runs only inside `_file_done` (`releases.py:367`), after the PRD move. When the PRD isn't in `prd/pending/apps/` (`:352-353`), the release is recorded but the backlog row never goes live. `builds._set_aside` updates the backlog whether or not the file is there; follow that pattern.
- **S7. A failed backlog write is reported as a failed move.** `_file_done` unlinks the pending PRD and then calls `backlog.release` (`releases.py:365-368`). If the backlog write raises `OSError`, the PRD has already moved, but the caller logs `apps.prd.done_move_failed` and says "The PRD couldn't be moved … move it by hand" (`:332-337`). Catch the two steps separately.
- **S8. The docs state Cloudflare Access as done.** `docs/app-factory.md:157` says the preview is "protected by Cloudflare Access". §6 Q4 accepted that, but it is a Dispatch D8 setup step in ticket 16 (U8), not yet in place. Say "to be protected by Cloudflare Access (ticket 16)" until it is.

### Nit

- **N6. Scope.** The §5.7 row says a skip "stays on preview" and lists only an expiry or a lapse in the one-pager. `health_lines` also lists skipped builds, and adds "approved, waiting for `release-plan`" and "claimed, waiting for main" lines. These are reasonable, but they weren't asked for; keep them, and add them to §5.4 when the PRD is next revised.

## Blocked paths

None touched. The template edit is outside the repo, under `jurasolutions/prd/templates/`, which isn't a blocked path. It is quoted in 7509ecc, and the ticket's release notes say to revert it together with `prd.py`.
