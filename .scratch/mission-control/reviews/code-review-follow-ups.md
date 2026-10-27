# Code review: release follow-ups (PR #3)

- **Branch:** `crew/release-follow-ups`, head `6fcaeab`
- **Base:** `main` at `54be324` (the merge-base)
- **Reviewed:** 2026-10-27, in a detached worktree at `6fcaeab`. Every one of the 28 changed files was read.
- **Spec sources:** the PR #3 body (items 1 to 7); `code-review-final.md` St5, St6, St7 and Sp4; the "Still open" rows of `code-review-fix-rounds.md` (mc 06 Sp1, mc 08 ST-1, ST-2, ST-3 and S-4); the MC PRD; ADR 0003 and ADR 0004.

## Verdict: approve

There are no blocking findings. Migration `core/0005` applies cleanly to a copy of the live `growth.db`, and main's code still runs against the migrated schema. The `not-ssh` refusal is correct for every kind, including the two applied on decide. The mc 06 retry bound uses the same `>=` comparison at the use-by as `use()`'s own lapse check. The should-fix items below are documentation and defence-in-depth gaps. They can go in a follow-up.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest -rs -p no:cacheprovider -o addopts=""` at `6fcaeab`, run in a detached worktree with `JURA_ROOT` set and temp `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` | **3643 passed in 151.51s**, exit 0, no skip lines |
| `sqlite3 <live growth.db> ".backup <tmp>/growth.db"`, then `jura-growth status` from `6fcaeab` with `JURA_GROWTH_DATA_DIR=<tmp>` | exit 0. `schema_migrations` gains `core/0005_ssh_decisions_only.sql`, and both triggers exist. `pragma integrity_check` is ok. `foreign_key_check` gives 17 rows before and 17 after: these are existing `events` to `runs` orphans, not caused by this PR |
| The same migrated copy, opened with `jura-growth status` from `main` (`54be324`) | exit 0 |
| Main's full suite with `core/0005` copied into its migrations folder, to simulate main's code on a migrated `growth.db` (scratch worktree; the file was removed afterwards) | 3623 passed, 1 failed. The failure is `test_approvals.py:831`, which pins main's migration list to end at 0004. That is expected and has no effect on behaviour |
| The live data | `approvals` and `approval_decisions` are both empty, so no Terminal decision exists that the migration or `not-ssh` could strand |
| Trigger probes on a throwaway copy | An `UPDATE` from pending to approved with origin `terminal` is refused. The same with `ssh` succeeds. An `INSERT` into `approval_decisions` with origin `terminal` is refused, and with `ssh` it succeeds. **A raw `INSERT INTO approvals` with `status='approved'` and `decided_origin='terminal'` is accepted** (see Sp-S1) |
| `git diff --name-only 54be324...6fcaeab` checked against the blocked paths | No change under `inputs/`, `design-system/`, `.env` or `data/growth/` |

### The brief's specific questions

- **Does it apply cleanly to the live copy?** Yes, as the evidence above shows.
- **Numbering and placement.** `jura_growth/migrations/0005_ssh_decisions_only.sql` gets the id `core/0005_…`. That follows `core/0003` and `core/0004` in the same folder, and plug-in migrations keep their own numbering. This is consistent.
- **Legitimate paths:**
  - **SSH decision.** `_decide_locked` writes `origin.kind`, which is always `ssh`, because `Origin` can only be `ssh` or `refused` (`origin.py:62-70`). Neither trigger fires.
  - **Revoke or skip of a Terminal-approved record over SSH.** The origin moves to `ssh`, which the trigger allows.
  - **Lapse or supersede.** These leave `decided_origin` as it was. `OLD IS NOT 'terminal'` excludes them, and `test_terminal_decisions_already_on_record_survive_the_migration_and_can_still_lapse` pins this.
  - **Gate adapters.** These decide through `approval_world.approve` or `skip`, which pass `Origin.ssh()` by default.
  - **UAT stub.** `uat_stub.py` only guards URLs and never touches approvals. `uat.md` decides only through Dispatch.
  - **Main's code reopening the DB.** Checked above.
- **`not-ssh` for every kind.** All six claimers go through `use()`: outreach (`send.py:505`), publish (`claim.py:306,326`), app-release (`releases.py:272`), and the kinds applied on decide, app-build (`builds.py:177`) and group-rules (`group_rules.py:113`). For the decide-applied kinds, `_decide_locked` writes `decided_origin='ssh'` before `on_approve` runs `use()`, so `use()` re-reads `ssh` and claims. If `NotApproved` is raised, the decision rolls back and the answer is `refused` (`approvals.py:658-665`). No caller branches on `NotApproved.reason`, so the new reason needs no handling elsewhere.
- **mc 06 retry bound at the use-by edge.** `_retry_closed` (`send.py:465-473`) closes the retry at `now >= use_by`. That is the same comparison `_lapse_if_due` uses (`approvals.py:438`), so a claim and a retry agree on the instant. The test pins both sides: a retry at 16:29 goes, and one at exactly 16:30 is marked uncertain and alerted. `use_by=None` is handled. Outreach always has a use-by.

## Standards

### Blocking

None.

### Should fix

- **St-S1. The retry use-by check contradicts ADR 0003 and the glossary, and neither was amended.**
  - **Where:** `jura_growth/agents/outreach/send.py:465-473`.
  - **The rules it breaks:**
    - `docs/adr/0003-…md:13-14`: "The claim is the point of no return: … no deadline is re-checked after it."
    - `CONTEXT.md:138` (**Claim**): "After a claim … no deadline is checked again."
    - PRD §4.6 A6: "never re-checks a deadline, because the claim already decided."
  - **Assessment:** the behaviour is what mc 06 Sp1 asked for, and it only makes the code more cautious. But the ADR, the glossary and the PRD now disagree with the code.
  - **Fix:** add an "Amended 2026-10-27" note to ADR 0003, saying that an outreach retry is also bounded by the use-by. Make the same change to the **Claim** entry and to A6.

### Nit

- **St-N1. Duplicated parsing.** `mission.py` repeats `timeutil.parse(x).astimezone(SGT)` five times, where `_at` used to be (around lines 319, 380, 401, 402 and 418). ST-1 asked to remove the wrapper, so this is acceptable. A `timeutil.sgt(value)` helper would fold the repeats.
- **St-N2. `builds.day_deadlines` now has one caller, in another module.**
  - **Where:** `builds.py:65-70`. The only caller is `releases.py:150`, and the function still reads `use_by_days`, which app-build no longer has.
  - **Repetition:** `builds.py:117` and `group_rules.py:102` write the same decide-only expression.
  - **Fix:** move it to `approval_settings` with a decide-only variant.
- **St-N3. `Reading`'s docstring overclaims.** `mission.py:149-159` says the two vocabularies "can't be compared by mistake". But `mission.Reading.SKIPPED == approvals.SKIPPED` is `True`, and the same holds for `APPROVED` and `SUPERSEDED`. Either soften the docstring or make `Reading` a `StrEnum` with distinct values.
- **St-N4. `_retry_closed` returns sentence fragments.** At `send.py:469-472` it returns half-sentences ("more than 23 hours ago…", "and the send…"), which read correctly only after `"called under {id} "`.
- **St-N5. `DB_STATES` is used only by tests** (`mission.py:37`). The same type `DbWording` holds both the unfilled templates and the filled result that `db_problem` returns.
- **St-N6. Plug-in job names in core.** `COUNTED_JOBS` (`one_pager.py:28`) names two plug-in jobs. It is not an import, and `caps.BROWSER_JOBS` is a precedent, so this is a judgement call against README's "the core never imports them by name".

## Spec

### Blocking

None.

### Should fix

- **Sp-S1. The schema half of Sp4 is partial, and the migration comment overclaims.**
  - **Where:** `jura_growth/migrations/0005_ssh_decisions_only.sql:5-6,10-20`.
  - **Spec lines:**
    - AC-M6.4: "no record ever holds a `terminal:` actor or a `terminal` origin".
    - Final review Sp4: "a trigger refusing a move to `approved` unless the origin is `ssh`".
  - **The gaps:**
    - The comment says "so raw SQL can't record one either". But a raw `INSERT INTO approvals … status='approved', decided_origin='terminal'` is accepted. My probe recorded such a row, and the PR's own helper `plant_terminal_approval` (`tests/test_approvals.py`, new) inserts one after the migration has run.
    - Neither `decided_by` nor `approval_decisions.actor` is guarded against `terminal:…`.
  - **Why it isn't blocking:** `use()` refuses to claim such a row (`approvals.py:503-506`), and ADR 0004 already accepts that raw SQL can forge a decision.
  - **Fix:** add a `BEFORE INSERT ON approvals` trigger for `decided_origin = 'terminal'`. Consider `LIKE 'terminal:%'` checks on the two actor columns. If that is not done, reword the comment. The test helper would then need to plant its row in a database at 0004, as the survival test already does.

### Nit

- **Sp-N1.** `0003_approvals.sql:21` still documents `decided_by` as "discord:<id> or terminal:<user>". This is history in an applied migration, so it can stay. CONTEXT.md or ADR 0004 could note that the `terminal:` form is legacy.
- **Sp-N2. AC-M6.4 says "ever", but 0005 is forward-only.** This is documented, the live database holds no such rows, and `use()` refuses them. Note the exception in the PRD when it moves to `done/`.

### Checked and correct

- **St5:** the app-build use-by is removed consistently from `builds.py`, `caps.py`, `approval_settings.py` and `settings.yaml`. Its tests run in three time zones.
- **St6:** the reason constants and the docstring list match, an unknown reason raises `ValueError`, and a source scan finds no string literals.
- **St7:** there is one `timeutil.when`, and "posting window" is used.
- **ST-1, ST-2 and ST-3:** done, and CONTEXT.md gains **Request reading**.
- **S-4:** `COUNTED_JOBS` matches PRD §5.4.4 ("scout-send and publish as counts per status").
- **Item 7:** `pages_project: landing-page` is in scope as the PR's seventh item, and the brief confirms the name. `dispatch_builds` stays off.

## Security

There are no findings at high or medium confidence. Every security-relevant change makes the code stricter:

- `use()` refuses any origin other than SSH.
- The new triggers refuse a new `terminal` origin.
- Outreach retries now stop at the use-by as well as the window.
- `preview_pattern` still applies `re.escape` to the project name, and `PROJECT_RE` validates the configured value, so pinning `landing-page` narrows what is accepted.
- `db_problem` fills `db_error` into a constant template through `str.format`. The template is never built from input, so a value can't inject format fields.
- No secrets, SQL built from input, subprocess calls or new input surfaces were added.

The `INSERT` gap in Sp-S1 is a defence-in-depth gap, not an exploit, because `use()` still refuses such a row.

## Blocked paths

There is no change under `jurasolutions/inputs/`, `jurasolutions/design-system/`, `.env` or the live `jurasolutions/data/growth/`. The live `growth.db` was only read, through `.backup`. Every run used temp folders.
