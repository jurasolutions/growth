# Code review 02: BP-02a, the publish queue for social posts (no browser)

- **Branch:** `crew/browser-publishing-02-publish-queue` (d15bf73, f54e934, e15bc3e), compared with its merge-base 4cc477e
- **Ticket:** `.scratch/browser-publishing/issues/02-publish-queue-no-browser.md`. **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md` (signed off, amended 2026-10-26) §2, §4.2 to §4.7, §5.4 to §5.7, §5.10, §3.3; MC §4.6 A1 to A17 and SC4; test strategy v3 §4.2, §4.3, §5
- **Reviewed:** 2026-10-27. I read every changed file in the diff: the publish plug-in (`__init__`, `claim`, `commands`, `hosts`, `items`, `job`, `kinds`, `limits`, migration 0001), `caps.py`, `headless.py`, `config/publish.yaml`, `config/social.yaml`, the social `__init__`, `plan`, `settings` and `submit`, `docs/social.md`, `tests/publish_world.py`, `tests/gate_adapter_social_post.py`, the four new publish test files, `tests/uat/seed.py`, and the changes to `test_headless`, `test_mission_health`, `test_run_update` and `test_social`. For context I also read `approvals.py` (`request`, `use`, `_lapse_if_due`) and the `after_run` call in `runner.py`.

## Verdict: changes-requested

There are two blocking findings. Both go against the brief's first check, that nothing can be claimed without an approval of its exact content, or against AC-P1.3. I reproduced both.

- **B1.** A content change reuses the same item, which breaks AC-P1.3 in two concrete ways.
- **B2.** The claim checks the copied images against a second read of the files, not against the approved hash.

Everything else the brief asked about holds:
- No existing value in `caps.py` was raised. `git diff main -- jura_growth/caps.py` only adds lines.
- `use()` re-checks the PAUSE file, `pause publish`, `pause all` (and with it auto-pause) and `publish_mode: draft` inside the claim's `BEGIN IMMEDIATE`, without consuming the approval.
- Expiry falls at the end of the posting window: 17:59:59 can claim, while 18:00:00 and approve-at-18:02 come back `expired`.
- No other job can reach a publish command. No plug-in declares one, `claude_rules` denies every undeclared leaf, `_enforced` refuses at run time, and `publish resolve` is in `NEVER`.

## Evidence

- `uv run pytest -p no:cacheprovider` in the developer worktree (e15bc3e, clean) printed **2310 passed in 83.49s**. It ran with `JURA_ROOT` set, temp `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`, the Discord double only and no browser.
- The publish, headless and gate files (`test_publish_queue`, `test_publish_items`, `test_publish_limits`, `test_uat_seed_publish`, `test_headless`, `test_approval_gates`) printed **254 passed**.
- I wrote reviewer repros in a scratch copy of `tests/`, outside the repo (`<session scratchpad>/probe02/tests/test_reviewer_probe.py`), and ran them against the worktree's code. **5 passed.** Each one asserts that a gap exists:
  - r1 and r2 are B1.
  - r3 is B2.
  - r4 and r5 are S3.
- `git diff main crew/browser-publishing-02-publish-queue -- jura_growth/caps.py` shows only `+` lines. The six new constants are present, and no existing value changed.
- `git merge-tree --write-tree crew/mission-control crew/browser-publishing-02-publish-queue` reports **CONFLICT** in `jura_growth/agents/social/settings.py` and in `tests/uat/seed.py` (5 hunks). See S1.
- Pyright, from the Standards sub-agent: `agents/social/submit.py` has 8 errors on the branch and 6 at base. The `agents/publish/*` files are clean. See S5.

## Blocked paths

No change touches `inputs/`, `design-system/`, `_ds_bundle.js`, `.env`, CI or the live `data/growth/`. Every test uses temp folders. **No finding.**

## Standards

### Blocking

None.

### Should fix

- **S1. Merge conflicts with `crew/mission-control`.**
  - `social/settings.py:18`: mission control moved `DEFAULT_CHROME` to `images.DEFAULT_CHROME` (bdb99eb), and this branch rewrote `PUBLISH_MODES` beside it.
  - `tests/uat/seed.py`: 5 hunks against tickets 17 and 18.
  - Rebase on the current head and re-run the suite before merging.
- **S2. `runner.py:314` `_commands_line` still filters with `c.split()[0] not in headless.NEVER`.** That is the third site of the rule d15bf73 changed. This ticket owns that change ("`may_use` and `claude_rules` match `NEVER` entries as a leading run of command words"), and `headless.never()` now exists for it. Nothing can be exploited today, because enforcement uses `never()`. But a job that declared `publish resolve` would see it listed in its preamble as allowed. Route this site through `headless.never()` too.
- **S3. Two duplicated implementations.** Both are reuse findings.
  - `publish/commands.py:70` `_mark_published` repeats `agents/social/history.py:169` `mark_published`: the same `UPDATE social_posts` and the same `social.published` event. Give `history.mark_published` a `how` argument and call it.
  - `publish/claim.py:204-232` `claimable()` hand-copies the checks in `approvals.use()`: status, use-by, hash and switch. BP-03's precheck will depend on it, and the copy can drift from the real gate. For example, it skips the `_refresh` re-raise and the unknown-kind refusal. Prefer a read-only form in `approvals`, or run `use()` inside a transaction that rolls back.
- **S4.** `social/settings.py:178` has its own `startswith("https://")` check on `page_url`, while `publish/hosts.problem()` is the real check, which `create_social` also runs. Use `hosts.problem` in both places, or keep it in one.
- **S5. New pyright errors in a touched file.** This breaks the operating card's "don't add new errors in files you touch". `social/submit.py:328` calls `int(post)`, and `db.scalar` there returns `Any | None`.

### Nit

- The same `YYYY-MM-DD` is parsed three ways: `items.py:138` uses `timeutil.parse(... + "T00:00:00")`, `claim.py:115` uses `datetime.fromisoformat`, and `kinds.py:83` uses `date.fromisoformat`.
- `items.SOCIAL = "social_post"` sits beside `items.SOCIAL_KIND = "social-post"`, which is easy to confuse. Item states are bare string literals across four modules.
- The `caps.py` module docstring says "Config may lower any of these". `PUBLISH_MINUTES_BETWEEN_ACTIONS` instead rises from config (`limits.py:70`). Say so in the docstring.
- Speculative for now, but planned for 02b and 03: `BROWSER_JOBS`, the community caps and `limits.community_*`, and the community kinds and outcomes in the migration. That is acceptable, because the ticket asks for all six constants.

## Spec

### Blocking

- **B1. A content change re-raises on the same item, not on a new one.**
  - AC-P1.3 says: "when any one field changes, then the item's `content()` no longer matches, its request is superseded and a new item and request are raised." BP §4.2 says: "Any change to … day … makes a new item that needs a new approval." BP §5.4 calls the item's content "frozen".
  - `kinds.SocialPost.content()` reads the draft live (`kinds.py:103`). The item's `day`, `target_url` and `posting_identity` columns never change, and the claim overwrites `content_json` (`claim.py:169-179`). Two concrete failures follow from this.
  - **r1, the day.** I moved the approved draft from 2026-11-10 to 2026-11-11. The re-raised request covers the 11-11 content, but `deadlines()` uses the item's old day (`kinds.py:137-138`), so its decide-by is **2026-11-10 18:00**. The card asks about a Wednesday post with a Tuesday deadline, and on the 11th `publish next` answers "expired". The post can never go out.
  - **r2, the heartbeat path.** I edited the text, then called `approvals.expire_due()`, as the noon heartbeat or the 08:00 job does. The request is superseded with no new one, and the next `publish next` runs `items.sync()` (`items.py:188-198`), which withdraws the item for good. Ting Yu gets **no card** for the edited post, and the draft stays `draft`. This breaks A3 ("on a mismatch a new request is raised") and AC-P1.3.
  - `test_publish_items.py:224` only follows the `use()` path, and it never checks the new request's deadlines.
  - Fix: on a mismatch, withdraw the old item and create a new item, with its own subject and the content frozen into its columns. Have `content()` compare the live draft with the item's own content. Then the day, the deadlines and the subject always agree, and whichever path notices the change first raises the new card. Add tests for the day case and the heartbeat case.
- **B2. The images handed out are checked against a second read, not against the approval.**
  - The brief asks that nothing be claimed without an approval of its exact content. A6 says `use()` "recomputes the content through the kind". `claim.py`'s docstring says copies are "checked against the approved bytes".
  - In fact `next_item` calls `use()`, which hashes the image files. It then calls `kinds.social_content()` again (`claim.py:169`), which reads and hashes the files a second time. `_copy_images` compares each copy with that **second** hash (`claim.py:195`), never with `approval.content_hash`.
  - **r3:** I swapped the image on disk between `use()` and the second read. The claim succeeded, and `publish next` handed out an image Ting Yu never approved. The window is narrow, and it needs a write to `outputs/growth/social/<day>/`, but it is the one guarantee this ticket exists to give.
  - Fix: after copying, assert `approvals.content_hash(kinds.hashed({**content, images from the copies}))` equals `approval.content_hash`, and raise `CopyFailed` (which rolls back) otherwise. Add a repro test.

### Should fix

- **S6. A claim that `after_run` never sees can't be settled.** AC-P10.1 and SC10 say "Ting Yu settles it from Discord".
  - `job.after_run` only looks at its own `run_id` (`job.py:20-22`). A claim from a run whose process was killed (r4), or from a Terminal `publish next` with no run (r5, `used_by_run` NULL), stays `claimed` for good. There is no alert and no pause, and `publish resolve` refuses it ("isn't unknown").
  - It can't double-post, because the cap counts it. But it is a silent dead end.
  - Settle claimed items whose run is no longer running (or that have no run) as `unknown`: on the next `publish next` or in `after_run`. Alternatively, let `resolve` accept a stale `claimed` item. Or record now that BP-03 owns this.
- **S7. The digest misses skips made by hand (AC-P8.3).** After `social skip` on a browser platform, the request is `superseded`, not `skipped`, so `publish/__init__.py:54` doesn't count it as skipped. Count `withdrawn` items whose request was superseded because they were skipped by hand (`superseded_note` already tells the two apart).

### Nit

- **MC A3 says content is "UTF-8, NFC-normalised".** The kind hashes the exact bytes (`kinds.py:9-10`). That is stricter, and it follows code review 06 for `outreach-email`. Amend A3, or record it in ADR 0003, so the contract and the code agree.
- **Unasked additions to record in the PRD (§5.10):**
  - the `page_url` and `identity` keys;
  - the fallback to posting by hand when a `browser` platform has no `page_url`;
  - the refusal to raise an item after the window has closed.
  All are reasonable, and `docs/social.md` covers them.
- **`hosts.py:17` adds `m.facebook.com` and `web.facebook.com`.** BP-03 turns this list into `ClaudeInChromeDomain` rules (AC-P9.2). Confirm each host in BP-01 before it widens the browser's scope.
- **The `#social-drafts` pointer promises something BP-03 delivers.** It says "the publish job posts it" (`submit.py`), but that job is BP-03's. Every platform ships in `draft`, so nobody sees this until then.

## Security

I ran the security pass on this diff only. There are **no findings at 8/10 confidence or higher**. I checked:

- **SQL.** Every query is parameterised.
- **URLs** (`hosts.problem`). It accepts only `https`, rejects user info, any `@` in the netloc and any port, and needs an exact host. `facebook.com.evil.test`, `https://www.facebook.com@evil.test`, `evil.test#@www.facebook.com` and `javascript:` are all refused, and tests cover them.
- **Files.**
  - `--live-text-file` and `--screenshot` go through `GuardedPath`/`paths.guard`.
  - A screenshot is named in an alert only if it sits under `work/publish`.
  - Image copies use `source.name` under `work/publish/<A-id>/` through `paths.writable`.
  - The live text is hashed and compared, never posted.
- **Discord.** Alerts carry the A-id, the P-label, the platform, the day, a validated URL and a reason from a closed list. Page text never reaches them. `assert_clean` runs over the cards and the pointer.
- **Reachability.** No headless job can run a publish command, as described under the verdict. `publish next` from Terminal is allowed by design.

B2 is the one integrity gap. It is filed under Spec because exploiting it needs local write access.
