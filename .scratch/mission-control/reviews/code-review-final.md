# Code review: final pre-release (mission-control and browser-publishing)

- **Branch:** `crew/mission-control` at 14baac1. Base: `main` at 855e48c, which is also the merge-base, so `git diff main...crew/mission-control` is the whole change: 265 commits, 304 files, +47,250 / -528.
- **Specs:** `prd/pending/prd-jura-mission-control-2026-10-25.md` and `prd/pending/prd-jura-browser-publishing-2026-10-25.md`, read with their dated amendments.
- **Scope:** every ticket already has its own review. This one looks at the joins between tickets, at rules applied in one place but not another, at leftovers, and at docs that no longer match the code.
- **Date:** 2026-10-27. Reviewer: crew reviewer.

## Verdict: approve-with-follow-ups

Nothing blocks the release.

- No blocked path changed.
- I found no outward action that can happen without a claimed approval over the exact bytes.
- Decisions only come in through the SSH forced command.
- The full suite passes with nothing skipped.

Two should-fix findings break a signed acceptance criterion: Sp1 (AC-P10.1) and Sp2 (MC §4.3). Neither lets anything go out unapproved, and both are small changes. I recommend fixing them on this branch before the G4 merge. If they ship as follow-ups instead, U-step evidence should be gathered with that in mind: a killed publish run is not paused right away.

## Evidence

- `JURA_ROOT=… JURA_GROWTH_DATA_DIR=$(mktemp -d) JURA_GROWTH_OUTPUTS_DIR=$(mktemp -d) uv run pytest -rs -p no:cacheprovider -o addopts=""` gave **3295 passed in 147.28s**, with no skip lines.
- The live `jurasolutions/data/growth/growth.db` had mtime `1792927593` before and after the run, so it was untouched. `git status --short` was clean afterwards.
- Blocked paths: `git diff --name-only main...crew/mission-control | grep -E '(^|/)(inputs|design-system)/|\.env$|data/growth|\.github'` found nothing.
- Secrets: I scanned the added lines for API-key, token, webhook-URL, private-key and Discord-token shapes and found none. The 17 to 20 digit numbers are test fixtures (`111…`, `7254…`). The email addresses are fixtures on `example.com.sg`, plus Jura's own sender address. `.env.example` adds only an empty `CONTROL_DISCORD_USER_ID=`.
- Reproductions:
  - Sp1: in one process, a second `fcntl.flock(LOCK_EX|LOCK_NB)` on the same lock file blocks. So a run's own `locks.is_held(job)` is True, and `_abandon_stale` never settles that job's dead run.
  - Sp2: the spec reviewer ran `privacy.for_discord('FAIL: [approve A-0412 here](https://evil.test/x) ```')` and it came back unchanged. `health.strip` adds no escaping on top.
  - St1, St2 and St3: confirmed with `grep`, quoted below.

## Invariants checked end to end

| Invariant | Holds? | Where |
|---|---|---|
| Every outward action needs an approval of the exact bytes | Yes. There are 7 `approvals.use()` sites, and each recomputes `content()` under `BEGIN IMMEDIATE`. Publish re-hashes the bytes it hands out (`claim._hand_out`) and the image copies (`job._copy_problems`). Outreach rebuilds the email and checks its hash. | `approvals.py:441`, `publish/claim.py:283-341`, `outreach/send.py`, `apps/builds.py`, `apps/releases.py`, `community/group_rules.py` |
| Decisions only through the SSH forced command; Terminal decisions off | Yes. `decide()` has one caller (`approvals_cli.py:80`). It needs `ctx.obj["origin"]`, which only `remote.handle` sets, after `origin.detect_ssh()` (forced-command variable, a root `sshd` ancestor, no `claude` ancestor or marker). No other code writes `status='approved'`. `bin/growth-remote` splits the command with `shlex`, then calls `execv`, with no shell. | `origin.py:190`, `remote.py:309-344`, `bin/growth-remote` |
| Claim before effect | Yes, at all 7 sites. `publish resolve not-posted` withdraws the item and never re-queues it. | as above |
| Only the publish job gets `--chrome`, scoped to the claimed item's hosts and group path | Yes. `runner.py:266-302` gates on `caps.BROWSER_JOBS`. The domain rules cover the enabled platforms (AC-P9.2, ADR 0005). The audit narrows to the claimed platform's hosts and the group's address. File paths in `publish` commands go through `paths.guard` (`headless.GuardedPath`), so a run can only pass files from its own scratch folder. | `publish/scope.py`, `publish/job.py:208-221` |
| `after_run` fails closed and carries no page or model text | Yes for publish. `__init__.after_run` returns `failed_closed` on any exception. The summary and error are rebuilt from records. | `publish/__init__.py:112-124`, `publish/job.py:59-120` |
| Run updates escape model text | Yes. `run_update._clean/_escape/_cut`. **The one-pager does not (Sp2).** | `run_update.py:200-249` |
| No secrets in the repo, logs, cards or run updates | Yes. Cards, run updates and remote answers all go through `privacy.for_discord`. `remote.command` events record the words and the answer, never the output. | `remote.py:431-439` |
| Tests never touch live files; `inputs/` and `design-system/` never written | Yes (evidence above). `paths.writable` refuses the read-only folders. | `paths.py:141` |

## Standards

### Blocking

None.

### Should fix

**St1. README and the `ApprovalKind` docstring still say content is NFC-normalised. ADR 0003, as amended on 2026-10-27, says there is no Unicode normalisation.**

- **Where:** `README.md:238` says "The canonical bytes of what would go out now (UTF-8, NFC-normalised, JSON with sorted keys)". `jura_growth/approvals.py:91` says the same.
- **The rule:** ADR 0003 (amended 2026-10-27): "the hash covers the exact bytes handed out … with no Unicode normalisation."
- **What goes wrong:** the plug-in contract in the README is what the next kind's author follows. A kind that normalises lets one yes cover NFD bytes Ting Yu never saw. That is the case the amendment closed for outreach (`outreach/approval.py:51-55`) and publish (`publish/kinds.py:48`).
- **Fix:**
  - Correct both docstrings to "the exact bytes, no normalisation".
  - `apps/releases.py:70` and `community/group_rules.py:57` still NFC their content. The release fields are regex-checked ASCII, so that NFC changes nothing. The rules text never goes out. Either drop both calls or add one sentence to the ADR saying non-outward kinds may normalise.
  - Judgement call (Duplicated Code): the canonical encoding is written five times, so one `approvals.canonical(value)` helper would keep them in line.

**St2. `.env.example` is missing the two new webhooks.**

- **Where:** `.env.example:10-17` lists 8 `DISCORD_WEBHOOK_*` entries. `config/settings.yaml:20-21` adds the `approvals` and `mission-control` channels. `discord.py:54` names them `DISCORD_WEBHOOK_APPROVALS` and `DISCORD_WEBHOOK_MISSION_CONTROL`.
- **What goes wrong:** a fresh setup copied from the example posts no approval cards (`cards.py:25`: "No `DISCORD_WEBHOOK_APPROVALS` means nothing is posted or saved to the outbox") and no one-pager. Every gated action then waits until its request lapses. Only a setup gap would show it.
- **Fix:** add both lines, each with a one-line comment.

**St3. `_normal()` is duplicated across the audit and `publish done`.**

- **Where:** `agents/publish/audit.py:317` and `agents/publish/commands.py:60`. Both are `re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()`.
- **The rule:** Duplicated Code (judgement call). These two copies must agree on whether "the live text matches the approved text".
- **What goes wrong:** someone edits one copy. The transcript audit and `publish done --live-text-file` then disagree, so publishing is paused for a match, or not paused for a mismatch.
- **Fix:** keep one copy (for example in `publish/hosts.py` or a small `publish/text.py`) and import it in both modules.

### Nits

- **St4. Repeated switches on publish item kinds** (judgement call).
  - **Where:** `items.raise_request` (377-389, whose bare `else` means "answers"), `kinds.read/closes/opens/skipped_by_hand`, `group_kinds.STEP`, `commands.STEPS` and `POSTS`, `outcomes.JOIN_KINDS` and `GROUP_KINDS`, and `claim._item_problem`.
  - **Why it's only a nit:** most of these raise `KeyError` on an unknown kind, so drift fails loudly.
  - **Fix:** if a fifth kind is planned, add one per-kind table in `items.py`.
- **St5. The `app-build` use-by is never reached** (judgement call).
  - **Where:** `builds.day_deadlines` writes a use-by from `caps.APP_BUILD_USE_BY_DAYS` (settings `use_by_days: 1`). But `on_approve` claims at decision time, so the request is never approved and unclaimed. The sibling `group-rules` kind, also applied on decide, returns `use_by=None`.
  - **Fix:** return `None` and drop the cap and the config key, or note why they stay.
- **St6. `NotApproved` reasons don't match its docstring.**
  - **Where:** the docstring is `approvals.py:55`. Callers also raise `gone`, `changed` and `mismatch` (`outreach/send.py:485-495`) and `unwritten` (`apps/builds.py:204`).
  - **Fix:** list them, or make them constants.
- **St7. Terminology and formatting.**
  - `caps.py:2` says "publish window", a term CONTEXT.md avoids in favour of "posting window".
  - Times reach Discord in three formats: `cards.when_at` "Tue 10 Nov, 16:30 SGT", `health.when` "Tue 10 Nov 16:30", and `publish/items.py:212` "Tue 03 Nov 16:30 SGT". One `timeutil` formatter would fix it.
- **St8. The operating card's "Verified" column is stale.** `docs/agents/crew.md` still records "515 passed" (2026-10-24). The suite now runs 3295 in about 150s. Refresh it at release.

## Spec

### Blocking

None.

### Should fix

**Sp1. A publish run that is killed mid-claim isn't settled or paused before the next slot claims again.**

- **Where:** `agents/publish/claim.py:283` (`_select`, and so `claimable`), `agents/publish/job.py:284-306` (`_settle_unknown`), `runner.py:203-218` (`_abandon_stale`) and `locks.py:43`.
- **Spec line:** BP AC-P10.1: "Given a claim with neither `done` nor `stopped` when the run ends, then `after_run` marks the item `unknown`; it is never claimed again, `publish` is paused".
- **What goes wrong:**
  1. A run claims P-0042, then the Mac sleeps hard or reboots, or the process is killed. No `after_run` runs, and the run row stays `running`.
  2. At the next slot, `_abandon_stale` runs inside the new publish run. It skips the dead row, because `locks.is_held("publish")` is True from the run's own lock: a second `flock` in the same process blocks, as reproduced above.
  3. `_select` never looks at `state='claimed'` items. The 20-minute gap counts from the dead run's start, so the new run claims and posts P-0043.
  4. Its `after_run` calls `_settle_unknown`, which only takes orphans whose run is not `running`, so it passes over P-0042 as well.
  5. Only a different job's `_abandon_stale`, 45 or more minutes later, makes the orphan settle-able. Until then posts keep going while one outcome is unknown, and `publish` isn't paused.
- **Limits of the impact:** each later post is still its own approved, capped item, and P-0042 is never claimed twice. What breaks is the AC's pause. That pause exists so Ting Yu checks the account (a checkpoint or a half-made post) before anything else goes out.
- **Test gap:** `tests/test_publish_regressions.py:132` (`test_r4_…`) sets the dead run to `failed` by hand, so it never exercises this path.
- **Fix:** at the start of `_select`, treat any `claimed` item whose `run_id` is not the current run as an orphan. The job lock rules out a live sibling, and a run-less Terminal claim is already `stale_claim`. Settle it as `unknown`, pause `publish`, alert with the `publish resolve` lines, and claim nothing. Add a test in which the dead run stays `running` and the next run's `publish next` is refused.

**Sp2. The one-pager posts a failed run's model-written `FAIL:` line without the run-update escaping.**

- **Where:** `jura_growth/health.py:164-166` adds `"\n> " + failure.error` into `#mission-control`. `failure.error` is `runs.error` (`mission.py:275`, masked and cut to 300 characters). For a claude job that is the model's own `FAIL:` line (`runner.py:392`).
- **Spec line:** MC §4.3: "Model-written text is untrusted. It is redacted, cut to 300 characters, and posted inside a quote block."
- **What goes wrong:** run updates escape backticks, `](` and mentions (`run_update._escape`), but the one-pager only masks. A scout, community or social run that read a hostile page can end with `FAIL: [approve A-0412 here](https://evil.test/x)`. That line then shows in `#mission-control` as a masked link under "Needs you", or as a code fence that breaks the rest of the strip.
- **Fix:** pass the error through the run update's single-line form (`run_update._line`, or one shared `untrusted_line()` used by both). Add a test with a masked link and a fence in `runs.error`.

**Sp3. A lost `apps release-plan` answer can't be fetched again** (liveness, lower priority).

- **Where:** `jura_growth/agents/apps/releases.py` (`plan_release`, `merge_plan` at 283).
- **Spec lines:** MC AC-M9.8 ("claims the approval and prints the exact merge command for the approved SHA"), and A6 / ADR 0003 ("its own retries … aren't a second use").
- **What goes wrong:** the claim commits, then the SSH reply to Dispatch is lost or times out. Every retry answers "already used … There is no merge to run". Ting Yu can still rebuild the merge by hand from the card, which shows the full SHA and branch, but the system doesn't give it back.
- **Fix:** when the `app-release` record was used by `release-plan` and the build still hashes to it, print the same `merge_plan` again without a new claim. This is idempotent, because the merge names a fixed SHA.

### Nits

- **Sp4. The schema still accepts a `terminal` origin, and `use()` doesn't look at the origin.**
  - **Where:** `migrations/0003_approvals.sql:21-22,104` and `approvals.py:441`.
  - **Spec line:** AC-M6.4: "no record ever holds a `terminal:` actor or a `terminal` origin".
  - **Status:** the code never writes one. ADR 0004 already accepts that raw SQL can forge a decision.
  - **Fix (defence in depth):** add a refusal in `use()` for `decided_origin != 'ssh'`, and a trigger refusing a move to `approved` unless the origin is `ssh`. Being a new migration, this can follow later.
- **Sp5. AC-P1.3 text lags the amended A11.** The code raises a fresh request on the same item, as the amended A11 says, but AC-P1.3 still reads "a new item and request". The BP crew-log entry of 2026-10-27T03:41 is still `needs-human`. Update the PRD text when it moves to `done/`.

### Also checked, nothing found

- Expiry, supersede and revoke behave the same across all seven kinds. Group removal now goes one way from either path (`groups.remove_for_good`).
- Pause, the PAUSE file and draft-mode switches are checked inside `use()`.
- Caps go only through `caps.effective` or `max` floors, so config can only tighten them.
- `docs/dispatch-contract.md` lists exactly the 16 `remote.ALLOWLIST` entries, in order.
- CONTEXT.md lists the 7 registered kinds.
- No TODO, FIXME, XXX or HACK was added.
- No scope creep.

## Security

I found no vulnerability that meets the high-confidence bar. What I checked:

- **Forced command:**
  - `bin/growth-remote` runs `shlex.split` and then `execv` with a fixed program, so no shell ever sees the words.
  - `remote._with_options`, `_publish_resolve` and `_decision` put free words after `--` and options as `--opt=value`, so a value is never read as an option.
  - The `--actor` check is attribution, as ADR 0004 says.
  - `remote.command` events never store the output.
- **Origin:** a root `sshd` ancestor is needed, which a user-owned symlink can't fake. Claude markers and a `claude` ancestor refuse. The remaining limits (other keys in `authorized_keys`, raw SQL from an interactive session) are recorded in ADR 0004 and its setup guide.
- **Publish run inputs:**
  - Every `click.Path` option (`--live-text-file`, `--file`) is a `GuardedPath`, so inside a run it accepts only `work/publish/` and `outputs/growth/`, and never a secrets file. A prompt-injected run can't send `~/.ssh` or `.env` to a card through `note-rules`.
  - The domain rules allow page tools only by host. Scripting, network and upload tools are denied.
- **Merge command shown to Ting Yu:** the branch must match `BRANCH_RE` (alphanumeric first, no `..`), the SHA must be a full hex SHA, and both are `shlex.quote`d in `merge_plan`. Pasting the merge command can't inject shell.
- **SQL:** every f-string query puts in only module constants (`_LIVE`, `_SUBJECT_SQL`, placeholder lists, fixed column names). Values are always parameters.
- **HTML for the one-pager PNG:** `one_pager.py` escapes every interpolated value, and Chrome runs headless on a throwaway profile with `--disable-extensions` and the offline resolver.
- **Low, not a vulnerability:** `publish resolve` doesn't check origin. It is denied to every scheduled run (`headless.NEVER`), records no decision and can't cause a post. That matches the contract ("It records no decision").
