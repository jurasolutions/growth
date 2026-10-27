# Code review 04: MC-04a, the approvals core (round 1)

- **Branch:** `crew/mission-control-04-approvals-core` at 75a3b67 (commits 2b06e4e, 75a3b67)
- **Fixed point:** 2ce000d (`crew/mission-control`). Diff: `git diff 2ce000d...crew/mission-control-04-approvals-core`
- **Spec:** `issues/04-approvals-core.md`; PRD MC §4.6 (A1 to A17, `on_approve`), §5.7, SC4, SC6, SC7; MC1 and MC3 (crew-log G2 entry); `reviews/technical-v2.md` B1, B2, B4; `reviews/tickets-technical.md` T2; `reviews/test-strategy-v3.md` §5 and §11.2 row MC-04a
- **Reviewer:** crew reviewer, 2026-10-25

## Verdict: changes-requested

There is one blocking finding (B1). The core holds up well against the attacks in the brief. Reusing an approval, racing two `use()` calls, changing the content after an approval, using it after expiry or a revoke, and claiming while paused are all refused in the database. `origin.py` reads no environment variable, flag or TTY, so nothing can spoof an origin through them in this ticket. The trigger freezes used and closed records. A database built from `main` (855e48c) migrates through `0003_approvals` with no row changed.

The blocker is in the audit trail. A claim that rolls back still leaves an `approval.used` line in the append-only JSONL mirror. `decide()` already holds its events back for exactly this reason, but `use()` doesn't. B1 is small to fix. S1 to S3 are cheap fixes to the contract that 04b, 10 and 11 will build on, so they belong in the same fix round.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest -o addopts="" -q -rs` in the 04 worktree, with `JURA_ROOT` and temp data and outputs dirs | 1454 passed in 57.41s, 0 skipped |
| `uv run pytest tests/test_approvals.py tests/test_approval_gates.py -rs` | 108 passed, 0 skipped |
| `git status --short` in the worktree, before and after the suite | identical (empty) |
| Reviewer probe script (scratchpad `probe04.py`, fake kind, temp dirs, no Discord) | reproduces B1, S1, S2, S3, N1 and N5; output quoted under each finding |
| Migration probe: a `growth.db` built by `git archive main` code (and again by 2ce000d), with a run row and a pause flag, then `db.migrate` by the branch | all 20 existing tables have an identical digest before and after; `core/0003_approvals.sql` recorded once |
| E6 greps: `jura_growth.agents.`, `taskwise`, `zenexflow` in `approvals.py`, `origin.py`, `0003_approvals.sql`; `os.environ`, `getenv`, `click` in `origin.py` | no hits |
| Blocked paths: `git diff --stat 2ce000d...` | no file under `inputs/`, `design-system/`, `.env` or `data/growth/`; only `.env.example` gains `CONTROL_DISCORD_USER_ID=` (an empty placeholder, not a secret) |
| `pyright` on `approvals.py` and `origin.py` (via the standards reviewer) | 0 errors; 4 new errors in the new test helpers (N3) |

## Standards

**Blocking:** none.

**Should fix**

- **S-St1. The README's plug-in table is stale.** `README.md:176` still says "`approval_kinds()` | The approval kinds the agent owns (ticket MC-04)". `agents/__init__.py:52-57` now documents `-> dict[str, approvals.ApprovalKind]`, the claim through `use()`, the pause flag and failing closed. The repo's `CLAUDE.md` says "`README.md` covers layout, commands, tests and the plug-in interface", so the two descriptions now disagree. Update the README row, and list the optional `ApprovalKind` members (`decision_args`, `args_help`, `on_approve`, `switched_off`, `on_skip`, `on_expire`, `on_lapse`), since the kind tickets will read it.
- **S-St2. Reuse: `_atomic` belongs in `db.py`.** `approvals.py:486-500` is a general savepoint form of `db.transaction()` (`db.py:41-50`): its own `BEGIN IMMEDIATE`, or a savepoint inside the caller's. It isn't approval logic. Ticket 08's read model and the later kinds will need the same thing, so move it to `db.py` as `db.atomic(conn)` (or give `db.transaction` a savepoint branch) before a second copy appears.

**Nits**

- **N-St1. Unused import.** `approvals.py:30` imports `SSH` and never uses it.
- **N-St2. Two constants with one name.** `approvals.REFUSED` (an answer, `approvals.py:36`) and `origin.REFUSED` (an origin kind, `origin.py:20`) share the name and the value `"refused"` but mean different things, and `approvals` imports its neighbours from `origin`. Consider `origin.NOT_HUMAN`, or keep the origin kinds behind `Origin.human`.
- **N-St3. Duplicated code.** The live predicate (`status IN ('pending','approved') AND used_at IS NULL`) is written out at `approvals.py:157`, `:261` and `:513`, as well as in the migration's partial index. The "fetchone, then `Approval.from_row(row) if row else None`" shape repeats in `get`, `_live`, `_latest` and `_successor`. `_refuse` (`:595-609`) also rebuilds `_audit`'s payload by hand. A single `_one(conn, sql, params)` helper, and `_refuse` building on `_audit`, would cover all three.
- **N-St4. `Approval.number` and `Approval.id`.** `number` is the row id and `id` is `A-nnnn` (`approvals.py:124`, `:147`). That is the opposite of what `approval_id` means in `decide()` and in `approval_decisions.approval_id`. Name the field `row_id`, or add a comment at the field.
- **N-St5. `kinds()` rebuilds the registry on every call.** `kinds()` (`approvals.py:204-224`) walks every plug-in and calls `approval_kinds()` on each `request`, `use` and `decide`, inside `BEGIN IMMEDIATE`. That is fine with today's plug-ins. Cache it per process if a plug-in's declaration ever gets slow.

Rejected baseline smell: the standards reviewer flagged the eight per-kind constants in `caps.py:37-44` as speculative generality. They stay. Test strategy v3 E7 asks `caps.py` to define "the §5.7 deadline maxima (MC-04a and later)", and `caps.py` is where the operating card says hard limits live.

## Spec

**Blocking**

- **B1. A rolled-back claim leaves `approval.used` in the append-only JSONL mirror.** This breaks test strategy v3 §5.2: "Expected in every refusal case: nothing went out, the record is unchanged except where the case says, and no `approval.used` event exists". It also breaks A16 ("Every transition writes an append-only event") and G22.
  - **Cause.** `log.event()` writes the mirror line straight away (`log.py:50-52`), whatever happens to the transaction. `use()` logs through `_audit` with no hold (`approvals.py:327-331`, `:482`). So when the caller's in-flight write fails and the `BEGIN IMMEDIATE` rolls back, the `events` row goes but the mirror line stays.
  - **Reproduced** with the fake kind: approve, set `fail_in_flight`, run the gated action. The output was `db: used_at = None | approval.used rows in events: 0` and `mirror approval.used lines: 1`.
  - **Wider than `use()`.** The same leak affects the `approval.superseded`, `approval.requested` and `approval.expired` events that `use()` writes when the caller lets `NotApproved` escape the `with` block (which the docstring at `:455` allows). It also affects any `expire_due()` savepoint that rolls back after an event.
  - **Why it blocks.** The mirror is append-only and cannot be corrected later. A false "used" there records an outward action that never happened, on the very record SC6 exists to keep honest. `decide()` already solves this with `_holding_events` (`:283-299`, `:661-663`).
  - **Fix.** Hold events in `use()`, `request()` and each `expire_due()` step the same way, and release them only when the outermost transaction commits. A commit hook on the connection, or releasing them in `db.transaction`'s `else` branch, works when `use()` runs inside the caller's transaction. Then add the mirror to G22's assertion, and to every refusal case through a shared helper.

**Should fix**

- **S1. A duplicate `--ref` that arrives while the first copy is still being decided gets `already-decided`, not the first answer.** AC-M6.2 says "the same `--ref` delivered twice, then the decision is recorded once and the second call returns the first answer with exit 0". PRD §4.7 adds that Dispatch "may retry within its 60-second window; `--ref` makes that safe".
  - **Cause.** The `source_ref` lookup runs before `BEGIN IMMEDIATE` (`approvals.py:654-659`). A second copy that arrives while the first holds the lock passes the lookup, waits for the lock, then finds the record approved and answers through `_closed_answer`.
  - **Reproduced** with two connections, where the first copy's `on_approve` sleeps 1.5 s and the second starts 0.5 s later. The output was `first: recorded | A-0002 approved.` and `second: already-decided | A-0002 was already approved.`. The record itself is correct. But in 11, `already-decided` maps to its own exit code, so Dispatch would report a failure for a decision that was recorded.
  - **Fix.** Repeat the ref lookup inside the transaction, at the top of `_decide_locked`. Keep the early read as a fast path if you like. Add the two-connection test to G16.
- **S2. Any exception from `on_approve` other than `BadArgs` escapes `decide()` as an exception, not a closed answer.** A10 says "Every decision answers one of `recorded`, `expired`, `superseded`, `already-decided`, `already-used`, `unknown-id`, `refused`". `decide()` catches only `BadArgs` (`approvals.py:665`).
  - PRD §4.6 says `app-build`'s `on_approve` "claims its approval and writes the build handoff". That claim is a `use()` call, which raises `NotApproved` when the factory agent is paused or its kind's switch is on (G19 applies to `app-build`). So in ticket 10, `approve A-nnnn` while app-factory is paused will throw out of `decide()`, and through 11's `remote` with no answer.
  - **Reproduced:** an `on_approve` that raises `NotApproved("paused", …)` gives `decide() raised NotApproved fake-agent is paused | record: pending`. The rollback is correct; only the answer is missing.
  - **Fix.** In `decide()`, map `NotApproved` raised from `on_approve` to `refused` with its text. Log `approval.refused` after the rollback, as for any refusal (G12). Let other exceptions propagate as programming errors. Add the case to G37.
- **S3. The trigger stops 04b from ever marking a card posted once its record is decided or closed.** `0003_approvals.sql:52-53` refuses every change to a skipped, expired or superseded record, and `:58-63` refuses a `posted_at` or `message_id` change on an approved one.
  - A12 says "Requests are posted after their transaction commits, by `approvals.post_unposted(conn)` … `posted_at` records it". AC-M5.2 covers a crash between commit and post. If Ting Yu approves or skips from Terminal (which lists unposted requests), or the request lapses, before the sweep runs, `post_unposted()` can never set `posted_at`. It will either repost on every sweep or have to leave the record unposted forever.
  - **Reproduced:** `UPDATE approvals SET posted_at = …` on an approved, unposted record aborts with "an approved request's decision never changes while it stays approved". On a skipped one it aborts with "a skipped, expired or superseded approval never changes".
  - **Fix.** Allow `posted_at` and `message_id` to go from NULL to a value exactly once on any record that isn't used, and keep refusing every other change. Alternatively, record in the ticket that `post_unposted()` posts only pending records, and that the one-pager lists the others. The first keeps 04b free to choose.
- **S4. Gate-matrix cases that are scoped "core" or "every kind" are missing or only partly asserted.** §11.2 row MC-04a asks for "fake: every core case, G12, G16 and G37", and the ticket's done-when says "every core case of the gate matrix runs with 0 skipped".
  - **G29** (`test_approval_gates.py:292-310`) leaves out `approval.expired`, though the case says "Walk a record through every transition". It checks only that the keys exist, not that `origin` and `ref` carry the decision's values or that `at` is growth's clock.
  - **G32** (`test_approvals.py:558-578`) has no closed-to-closed pairs (skipped→expired, expired→superseded, superseded→skipped) and no used→superseded pair. The case says "Raw SQL for each from-to pair in A7".
  - **G36** ("Run each writer over a due record: `decide`, `use`, …: Each writes the transition once") has no test. Its `decide` and `use` writers are in this ticket. G4b (`test_approval_gates.py:117`) checks the refusal but not that `use()` wrote the lapse in the caller's transaction.
  - **G5** (`:151`) re-checks `on_expire` but not `on_lapse` after the second `expire_due()`, and doesn't check that the record is unchanged.
  - **G15** (`:198-205`) also accepts `already-used`, and doesn't check that the record is unchanged.

**Nits**

- **N1. The trigger allows a few changes A7 says it refuses.** A7 says the trigger "refuses everything else". Three changes still get through:
  - `used_by_run` can change on an approved record while `used_at` stays NULL.
  - `closed_at` and `close_reason` can change on an approved record that stays approved.
  - `use_by`, `decided_by` or `decided_origin` can be set on a pending record, or on a pending→expired or pending→superseded transition.

  None of these is reachable through the module. Tighten the trigger (or the CHECKs) while S3 has it open.
- **N2. `get()` and `pending()` don't compare hashes, though A3 says every read does.** A3 says "`request`, `use` and every read compare the record's hash", and the docstring at `approvals.py:247-248` says on purpose that they don't. `expire_due()` superseding stale records before the one-pager builds covers the case that matters, and G36 says "the read model writes none". Record in the ticket which rule wins, so 04b's `approvals` listing doesn't quietly show stale content as pending.
- **N3. Four new pyright errors in the new test helpers.** The operating card says "don't add new errors in files you touch".
  - `tests/approval_world.py:100-101` sets attributes on a `ModuleType`.
  - `tests/approval_world.py:183`: `record()` returns `dict | None` but is typed `dict`.
  - `tests/gate_adapter_fake.py:29`: `raise_request()` returns `Approval | None` but is typed `Approval`.
- **N4. X3 is only half here.** The X3 row says "the deadline settings live in the `approvals:` block", and the ticket review puts that block in 04b (T10). For this ticket, `test_approvals.py:513` checks `caps.effective` only. Make sure 04b's ticket names X3 for the settings half.
- **N5. A hand-built `Origin` skips `Origin.terminal()`'s check.** `Origin("terminal", code=…)` with no user is accepted. It records `decided_by = terminal:None` (reproduced: `answer: recorded | decided_by: terminal:None`). Move the check into `__post_init__`, so every `Origin` is valid however it is built.
- **N6. `parse_id` accepts non-ASCII digits.** `parse_id("A-٤١٢")` returns 412 (`approvals.py:178`, `\d`). This is harmless, but `[0-9]` matches what Ting Yu types and what G30 assumes.

**Scope beyond the ticket, accepted:** the 14-day ceiling `APPROVAL_DEADLINE_MAX_DAYS` (§5.7 says "never lengthened"; E7 asks for deadline maxima), the `switched_off` hook (AC-M4.6 "the kind's own switch"), refusing arguments a kind doesn't take, the Terminal actor-mismatch check, failing closed on a kind two plug-ins declare, and `decide()` refusing an unknown kind. All of them are fail-closed refinements inside the spec's intent. `request()` returning `None` or the expired record, where §4.6 has `-> Approval`, should be noted in §4.6 when the PRD is next touched.

## Security

There is no high-confidence vulnerability beyond B1, which is an integrity issue. Each attack from the brief, and what happened:

| Attack | Result |
|---|---|
| Approve your own item (a prompt-injected run) | There is no decision CLI in this ticket. `decide()` needs an `Origin` object, and nothing in `origin.py` derives one from the environment, a flag or a TTY. The real guard is 04b's `detect()`, ticket 01's `NEVER` list and the `JURA_GROWTH_JOB` refusal. |
| Reuse an approval | Refused: `used` (G7). A request raised later for the same subject is a new instance and needs its own decision. |
| Approve, then change the content | `use()` recomputes the content through the kind, supersedes the record and raises a new one (G9, AC-M4.2). |
| Race two `use()` calls | Exactly one claim (AC-M4.4, two connections under `BEGIN IMMEDIATE`). |
| Use after expiry or after a revoke | Refused at the deadline even when the lapse isn't written yet (G4b). A skip before the claim wins (G17). |
| Decide or claim while paused | The claim is refused and not claimed (G19, probe P7). The decision is still recorded: §4.6 doesn't ask the core to refuse a decision while paused, and the fake kind has no effect at decision time. Kinds applied on decide (05 `group-rules`, 10 `app-build`) must check the pause themselves; see S2 for what happens when they do. |
| Spoof the origin through env vars or a fake TTY | `origin.py` reads nothing (E6 grep). For SSH, `CONTROL_DISCORD_USER_ID` comes from `config.secret()`, which prefers the environment. That is acceptable only because §4.6 A8 makes it a consistency check, not the guard. |
| Freeze growth's clock to dodge a deadline | `JURA_GROWTH_NOW` raises `FrozenClockRefused` against the live data folder (`timeutil.py:51-58`), so it can't move deadlines on the real `growth.db`. |
| Direct SQL on `growth.db` | Raw SQL can still approve a pending record with fabricated decision fields, and the claim then goes out (probe P6). No trigger can authenticate the writer. This doesn't change the verdict: headless rules allow only `Bash(jura-growth …)` (`headless.py:121-136`), and ADR 0004's layers are the guard. Note it in ADR 0004 as a known limit for interactive sessions. |
| Migration on a live `growth.db` built at `main` | Adds only. No existing row changed (migration probe). An older checkout ignores the extra `schema_migrations` id. |
| SQL injection | Every query is parameterised. The only f-string SQL is in tests. |
| Secrets and personal data | Event payloads go through `log.event`'s `config.redact`. `args_json` and the event `args` hold Ting Yu's typed decision arguments only. |

## Blocked paths

None touched. `.env.example` is not blocked, and its new line is an empty placeholder.

## What the fix round should do

Fix B1 and S1 to S4. Fold in S-St1, S-St2, N-St1 and N3, which are each a line or two. Leave the other nits to the developer's judgement. Then re-run the full suite and the probe script.

---

# Round 2 (after fix round 1)

- **Branch head:** bbb6557. The fix commits are 84e6dc3 (the mirror waits for the commit; `db.atomic`), 95b5aa4 (B1 on the approvals side, S1, S2, S3, N1, N6), f78b8eb (S4), 0e3a098 (README, N5, N-St2 to N-St4, N3) and bbb6557 (the ADR 0004 note on raw SQL).
- **Reviewed:** `git diff 75a3b67..bbb6557`, every changed file read. The conductor's brief added a check of the engine-wide logging change, and a check of the `Callable` typecheck report.

## Verdict: approve

Every round-1 blocking and should-fix finding is fixed, and each fix is proved by a test and by the round-1 probe. The new `db.after_commit` mechanism is sound for the cases the conductor asked about. It leaves three should-fix items (R2-S1 to R2-S3), none of them blocking:

- a mirror write that fails after the commit makes a committed transaction raise and drops the lines after it;
- `use()` accepts a raw `BEGIN` that bypasses the deferral;
- the commit-to-mirror gap isn't documented.

They're small, and they can go in the next fix round or be folded into 04b. The verdict follows from the blocking findings alone, and there are none.

## Round-2 evidence

| Command | Result |
|---|---|
| `uv run pytest -o addopts="" -q -rs` in the worktree, with `JURA_ROOT` and temp data and outputs dirs | 1499 passed in 40.18s, 0 skipped |
| Runner, slot and core subset (`-k "pause or lock or skip or quiet or mirror or slot"` over `test_runner.py`, `test_mission_slots.py`, `test_core.py`) | 226 passed |
| `git status --short` before and after | identical (empty) |
| Round-1 `probe04.py` | P1 `mirror approval.used lines: 0`; P2 `first: recorded`, `second: recorded`; P3 `posted_at set` on approved and skipped records; P4 `answer: refused refused: fake-agent is paused.`; P5 `ValueError: a terminal origin needs the user and the typed code`; P8 `parse_id('A-٤١٢')` is `None` |
| Round-2 `probe04r2.py` (scratchpad) | Q1 to Q4 below |
| `pyright --pythonpath .venv/bin/python` on `db.py`, `approvals.py`, `origin.py` and the four approval test files | 0 errors, 0 warnings |
| `pyright` on `log.py` | 1 error at `log.py:72` (`start_run` returns `int | None`); the same error exists at 2ce000d (line 70 there), so it is not new |

## Round-1 findings

| Finding | Status | Evidence |
|---|---|---|
| B1 the mirror kept a rolled-back claim | fixed | `log.event` routes its mirror line through `db.after_commit` (`log.py:50-54`, `db.py:41-99`). `test_core.py` covers a rolled-back transaction and a rolled-back savepoint, and `test_a_refusal_the_caller_lets_escape_leaves_nothing_in_either_store` covers approvals. Probe P1 finds 0 lines |
| S1 a duplicate `--ref` during the first decision | fixed | `_first_answer` runs again under the lock (`approvals.py`, top of `_decide_locked`). A two-connection test was added. Probe P2: both copies answer `recorded` |
| S2 `NotApproved` from `on_approve` | fixed | `decide()` answers `refused` and logs after the rollback. Other exceptions roll back and propagate, which is tested |
| S3 the trigger blocked marking a card posted | fixed | `posted_at` and `message_id` can now be set once on any record that isn't used. `test_a_card_is_marked_posted_once` covers it, and probe P3 confirms |
| S4 gaps in the gate matrix | fixed | G29 now covers `approval.expired` and checks values; G32 gains the closed-to-closed pairs and used→superseded; G36 is covered for `decide`, `use` and `expire_due`; G5 checks `on_lapse` and that the record is unchanged; G15 is strict |
| S-St1 README, S-St2 `db.atomic` | fixed | README has an "Approval kinds" section and table. `db.atomic` replaces `_atomic` |
| N1 trigger gaps, N3 pyright, N5 `Origin`, N6 `[0-9]`, N-St1 to N-St4 | fixed | Trigger rules and CHECKs tightened (`0003_approvals.sql:30-87`); the test helpers' typecheck is clean; `Origin.__post_init__`; `NOT_HUMAN`; `_LIVE` and `_one`; `_refuse` built on `_audit`; a comment at `number` |
| N2 plain reads, N4 X3 settings half | open, as noted | Both stay with 04b, unchanged |
| P6 a raw-SQL approval | accepted | Recorded as a known limit in ADR 0004 |

## The engine-wide logging change (conductor's checks)

`db.after_commit` changes when every event's mirror line is written. Today the deferral touches events written inside one of the six `db.transaction` sites: `approvals.py` (decide, use's caller, `expire_due` through `db.atomic`), `suppression.py:117`, `agents/social/submit.py:289`, `agents/scout/leads.py:269` and `agents/outreach/requeue.py:105`. Each check the conductor asked for:

- **Events written outside a `db.transaction` still mirror at once.** Yes. `after_commit` returns False when no `transaction()` is registered for the connection, and `log.event` then mirrors straight away (`log.py:53-54`). Probe Q1: an autocommit event and a `conn=None` event each have their line before the next statement.
- **The runner's PAUSE-file and lock-skip lines still happen.** Yes. Both call `log.mirror()` directly with no database (`runner.py:74`, `:79`), which this change doesn't touch. The runner opens no `db.transaction`, so its `run.start`, `run.skipped` and `run.quiet` events mirror at once as before. The runner and core tests pass, including `test_the_lock_skip_gets_one_run_update_without_opening_the_database` and `test_pause_file_pauses_everything_without_db`.
- **The slot classifier still sees every `run.skipped` and `run.quiet`.** Yes. `slots.py` takes records from both `events` and the mirror and counts a record found in both once (`slots.py:86-89`, `:149-150`). An event whose mirror line is lost after the commit (Q4) still arrives through `events`. The only records that live in the mirror alone are the runner's database-free skips, and those are unchanged. `tests/test_mission_slots.py` passes.
- **A crash between the commit and the mirror write.** Its lines are lost, while the `events` rows stay. Probe Q4: a child process exits inside the first after-commit callback, and the result is `events row: 1 | mirror lines: 0`. This is the right trade: `growth.db` is the log of record (`db.py:1`), and the old order had the opposite and worse failure, a mirror line for a write that never committed. But it isn't documented: see R2-S3.

## Should fix (round 2)

- **R2-S1. A mirror write that fails after the commit makes a committed transaction raise, and drops every later line.** `db.transaction` runs the waiting callbacks in a plain loop after `COMMIT` (`db.py:63-66`). The first `OSError` (OneDrive holding the day's file, a full disk) propagates out of a `with` block whose work is already committed, and the remaining callbacks never run.
  - **Reproduced** (Q2): two events in one transaction, with the first mirror write failing. The output was `committed transaction raised: OneDrive held the file` and `events rows a,b: 2 | mirror a,b: 0 0`. The second line was lost although its own write would have worked.
  - **Why it matters.** Before this change, a mirror failure inside a transaction rolled the transaction back, so the caller's work and its error agreed. Now the caller sees an exception for committed work. For a gated action, that means the claim is used but the caller skips the outward call (fail closed, but the approval is burned). For the scout, social and requeue transactions, a command reports failure for rows it wrote.
  - **Fix.** Run every callback, catch each error, and report them on stderr, as the plug-in loaders do (`approvals.py:216`). A committed transaction should never raise. Add a test with a failing first mirror write.
- **R2-S2. `use()` accepts any open transaction, so a raw `BEGIN` brings B1 back.** `use()` checks only `conn.in_transaction` (`approvals.py:437-438`). When a caller opens its transaction with `conn.execute("BEGIN IMMEDIATE")` instead of `db.transaction(conn)`, `after_commit` finds nothing registered, so the mirror line is written straight away and a rollback leaves it behind.
  - **Reproduced** (Q3): `used_at: None | new mirror approval.used lines: 1`.
  - No caller exists yet, but 06, 10, 10b and BP-02a will each write one, and the README tells them to use `db.transaction`.
  - **Fix.** Add a public `db.in_transaction(conn)` (true only when `transaction()` registered the connection). Make `use()` refuse otherwise, with the same `RuntimeError`, and add a test.
- **R2-S3. Document the new order.** `log.py`'s module docstring still says "Every event goes to the `events` table and, as one JSON line, to `data/growth/runs/YYYY-MM-DD.jsonl`" and that the mirror "survives a broken database". Add two sentences:
  - inside `db.transaction()` the line is written after the commit and never after a rollback;
  - a crash between the two loses the line, while `events` keeps the row, which is why readers such as `slots.py` take records from both.

  The README's "Runs and events" text, or ADR 0003's consequences, would also do.

## Nits (round 2)

- **R2-N1. Mirror lines are now out of order.** A committed transaction's lines land after any events written meanwhile on other connections. They can also land in the next day's file when the commit crosses SGT midnight, because `mirror()` picks the file name at write time (`log.py:57`) while `ts` is the event's time. `slots.py` keys on `ts`, not on file order, so nothing breaks today. A reader of the mirror should sort by `ts`.
- **R2-N2. `0003_approvals.sql` has changed since round 1.** Any scratch `growth.db` that applied the round-1 file keeps the old trigger, because the migration id is the same. Nothing outside temp folders has applied it. Once merged, the file must not change again: later fixes go in a `0004`.

## Conductor's `Callable` question

Not reproduced, so it is not a finding. `jura_growth/db.py:13` imports `from typing import Callable, Iterator` at every fix commit (84e6dc3, 95b5aa4, f78b8eb, 0e3a098 and bbb6557). At runtime, `jura_growth.db.Callable is typing.Callable` is `True`. `pyright 1.1.414 --pythonpath .venv/bin/python jura_growth/db.py` reports 0 errors.

The annotations at `db.py:43` and `:90` would work under `from __future__ import annotations` even without the import, but the import is there, so pyright resolves the name. The report most likely came from pyright running on another checkout. The repo-root checkout is 2ce000d, whose `db.py` has no `Callable`, and pyright there would resolve `jura_growth` to it rather than to the worktree. The developer's "0 errors in touched files" holds for `db.py`, `approvals.py`, `origin.py` and the new test files. `log.py`, also touched, has one error, and it predates the branch.
