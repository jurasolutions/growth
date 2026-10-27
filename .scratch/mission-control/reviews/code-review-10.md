# Code review: ticket 10 (MC-10, app ideas wait for approval)

- **Branch:** `crew/mission-control-10-app-factory-kinds` at `c7fac06` (commits 3e93664, a2604ee, 73241bb, c7fac06)
- **Compared against:** merge-base `04a609e` (`git diff 04a609e...crew/mission-control-10-app-factory-kinds`), 12 files, +1227 / -85
- **Spec:** `prd-jura-mission-control-2026-10-25.md` SC4, SC9, §4.6 A3/A6, §5.7 `app-build` row, §5.9, the 2026-10-26 amendment; ticket `issues/10-app-factory-kinds.md`; `reviews/test-strategy-v3.md` §5.2, §11.1 E3, §11.2 row MC-10
- **Reviewer:** crew reviewer, 2026-10-27
- **How it was run:** both axes and the security pass were run inline by the reviewer, not through the `code-review` and `security-review` sub-agent skills; every changed file was read in full.

## Verdict: changes-requested

One blocking finding: the build handoff can hand Dispatch PRD text that Ting Yu never approved (B1, reproduced). Everything else is should-fix or nit.

## Evidence

| Command | Result |
|---|---|
| `pytest` in the developer worktree (temp data, outputs and PRD dirs) | 1842 passed, 10 skipped; `git status --short` empty afterwards |
| `pytest` on `git merge-tree` of the branch with `crew/mission-control-11-remote-core` (`7a467a1`, exported to a temp folder) | 2032 passed, 10 skipped |
| `git merge-tree --write-tree` against `crew/mission-control` (`c2b468f`) and against ticket 11 | both clean, no conflicts |
| `growth.db` built by `main`'s code (`git archive main`), three real-shaped `app_prds` rows, then opened by the branch's `db.connect` | rows identical, `UNIQUE(app_id)` and `app_prds_day` kept, `app_prds_slug` added, `foreign_key_check` empty, `integrity_check` ok; a second open applies nothing |
| Same database, 0003 run up to `DROP TABLE app_prds` inside `BEGIN`, then the process killed (`os._exit(9)`) | reopening rolled the journal back, then applied 0002 and 0003 cleanly; rows identical |
| Reviewer repro R1 (scratch copy of `tests/`, not on the branch) | fails: see B1 |
| Reviewer repro R2: approve refused while `app-factory` is paused, then recorded after resume | passes |
| Read-only `catalog.prd_files()` over the live `jurasolutions/prd/` | the one-off pass would raise one request, for APP-003 (factory-authored); APP-001 and APP-002 are Ting Yu's and get none |
| Blocked paths | no change under `inputs/`, `design-system/`, `.env` or `data/growth/` |
| `taskwise` / `zenexflow` in changed files | no hits |

## Migration `apps/0003` (asked for above all)

Safe. `db.migrate` wraps each file and its `schema_migrations` row in one `BEGIN … COMMIT`, so an interruption rolls back whole (shown above). Every column is copied by name with ids kept, so nothing is renumbered. No table references `app_prds`, so the `DROP` under `foreign_keys = ON` deletes nothing elsewhere. The only side effect is that the stored DDL now quotes the name (`CREATE TABLE "app_prds"`), which does no harm. `main`'s code still runs against the rebuilt table, because `submit` checks `taken()` before it inserts. The rollback note that follows from this is under nit N1.

## Standards

**Blocking:** none.

**Should fix**

- **St1. The ten skips break exit criterion E3.** `tests/test_approval_gates.py:70` (the `claimed` fixture) and `:291` skip 10 cases for `app-build`. E3 (`test-strategy-v3.md` §11.1) requires "0 skipped in the files named in section 1", and the harness is one of them (§1, line 122). On `main` the suite has 0 skipped. The skips don't hide untested behaviour:
  - G4b, G7, G17 and G25 "approved" don't apply to a kind applied on decide (§5.2).
  - G9, G19 (PAUSE file, paused agent), G21 and G22 do apply to `app-build`. They are traced in `tests/test_app_builds.py`: AC-M9.4 at `:235`, the pause cases at `:492`, the Dispatch poll at `:191`, the failed write at `:211`.
  - G19 "the kind's switch" has no switch to test for `app-build`.

  The fix belongs to the MC-04a harness, which T7 says a kind's ticket must not edit. Two ways to fix it: make `pytest_generate_tests` leave applied-on-decide adapters out of those cases, so they are never collected, or amend E3 to exempt §5.2's documented non-applicable cases. Ticket 05 (`group-rules`) will hit the same skips. This is a question for the user below.
- **St2. The G19 cases for `app-build` stop halfway.** `tests/test_app_builds.py:492-503` checks the refusal but not that the request can still be approved once the brake clears, which G19 expects ("claimable again after the switch clears"). Reviewer repro R2 shows the behaviour is right, so the fix is two more lines in the test.

**Nits**

- **N1.** The operating card's Release section says the migrations so far "add tables, columns and indexes … none drops data". `apps/0003` drops and rebuilds `app_prds`, with every row kept. Its release notes should say so, so the rollback note stays true.
- **N2.** `builds.skipped_dir()` (`builds.py:55`) only forwards to `catalog.skipped_dir()`. Call the catalog function directly.
- **N3.** `raise_waiting` is called the "one-off pass", but it runs on every `precheck` and every non-dry-run `submit-prd` (`__init__.py:64`, `:239`). It is idempotent, so this is only wording. The docs already say it "does nothing once each has one".

## Spec

**Blocking**

- **B1. The handoff's hash and text come from a second read of the file, not from the approved content.** `jura_growth/agents/apps/builds.py:153-162`:

  ```python
  approval = approvals.use(conn, KIND, subject, run_id=run_id)
  ...
  "prd_sha256": approvals.content_hash(found.path.read_bytes()),
  ```

  `use()` checks the file's bytes against the approved hash. `hand_off` then reads the file again and stores that second hash. `handoff()` (`:219-234`) hands out any bytes that match the stored hash. So a write between the claim and the second read is recorded as approved and given to Dispatch verbatim. The writer could be the factory, a Claude session editing `prd/pending/apps/`, or OneDrive sync.

  Reviewer repro R1 wraps `approvals.use` so the PRD is edited right after the claim. The output was: `answer: recorded | row sha == approved hash: False | handed-out text edited: True`.

  This breaks the brief's invariant ("an app build can't be handed off without a claimed approval for exactly that idea's content"). It also breaks MC §4.6 A3 and A6 (the claim is over the content the kind computes; one approval authorises that content) and AC-M9.2 (`prd_sha256` is the approved file's SHA-256).

  The fix: read the bytes once, compare `content_hash(bytes)` with `approval.content_hash`, raise `NotApproved("superseded", …)` on a mismatch (the decision rolls back, as with G22), and store `approval.content_hash`. Add R1 as a test.

**Should fix:** none beyond St1 and St2.

**Checked and holding:**

| Criterion | Where it holds |
|---|---|
| AC-M9.1 | Card with the PRD attached, the pitch, the tier and the lead types; no #app-factory post; no "approved, build" line (`test_app_builds.py:83`, `:103`) |
| AC-M9.2 | Claim and row in the decide transaction (`:115`); `--json` shape (`:130`); 64 KB limit (`:155`) |
| AC-M9.3 | Both `dispatch_builds` values, through the answer and the `health()` hook (`:172`) |
| AC-M9.4 | `:235` |
| AC-M9.5 | `:265` |
| AC-M9.6 | Not offered on day 29, offered and filed on day 30 (`:284`) |
| AC-M9.10 | Only pending `app-build` requests count (`catalog.py:108-115`, `:314`) |
| AC-M9.11 | `:329`; the live folder check above |
| AC-M4.7 | Fails closed (`:466`) |
| X2, X3, X7, G31, G37 | All present |
| Sweep over app cards | Present (`:437`) |
| Amendment | Decisions only through `aw.approve` with the SSH origin; no Terminal path added |

## Security

**Blocking:** B1 (above). It is also an approval-bypass path: content that was never approved reaches the builder under a real approval id.

**Nits**

- **N4. File moves can outlive a rolled-back decision.** `_set_aside` (`builds.py:291-318`) moves the PRD file and rewrites `app-backlog.yaml` inside the decision's or expiry's transaction. If that transaction rolls back after the file has moved, the record stays pending. The next read then supersedes it as "the PRD left prd/pending/apps/", and the backlog row is never closed. This needs a second fault to happen. Consider writing the skipped file before unlinking the pending one (already the order) and re-running the backlog update when the hook is retried.

**Checked:**

- `apps handoffs --json` reads only the paths stored in `app_builds` and caps its output at 64 KB.
- The skipped target goes through `paths.writable`.
- No shell or subprocess.
- The planted-secret sweep passes over the card, its edit and the attachment.
- No credentials in code, tests or docs.

## Reuse

Nothing new duplicates an existing helper beyond N2. The kind reuses `approvals.use`, `cards.sweep_safely`, `approval_settings.deadline` and `switch`, and `factory.pitch`.

## Question for the user

1. **E3 versus the documented skips (St1).** Recommended answer: change the MC-04a harness so applied-on-decide adapters aren't collected for the §5.2 non-applicable cases, which keeps E3 strict. Do it as a small 04a follow-up before ticket 05 merges, and keep the `app-build` traces in `test_app_builds.py` as the evidence for G9, G19, G21 and G22.
