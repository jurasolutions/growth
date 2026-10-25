# 04 — MC-04a the approvals core

Status: ready-for-agent
Blocked by: 01, 02
PRD ticket: MC-04 in `prd-jura-mission-control-2026-10-25.md` §5.12, first half (split by the ticket review; the second half is 04b)
Covers: SC4 (with a fake kind), SC6, AC-M7.6; the approval contract MC §4.6 A1 to A17; ADR 0003

## What to build

The approval contract every later kind registers against, proved end to end with a fake kind and no CLI. A gated action names a kind and a subject; the module owns the content hash, the state machine, both clocks, the claim before the effect, the decision hook, and the audit events. Decisions take an injected `Origin`, so this ticket needs no real terminal or SSH detection (that is 04b). The file keeps the name `04-…` so every `mission-control#04` reference stays valid.

## What to change

- `migrations/0003_approvals.sql`: the `approvals` table (with `posted_at` and the card's message id), the partial unique index allowing one live request per `(kind, subject)`, the unique `(approval_id, source_ref)` index, and the transition trigger in A7, including the refusal of `DELETE` on a decided record.
- `approvals.py`: `request`, `decide` (taking an injected `Origin`), `use`, `expire_due`, `pending`, `get` and `raised_by(conn, run_id)` (which 03 needs). `use()` runs inside the caller's `BEGIN IMMEDIATE`, recomputes the content through the kind, and refuses unless approved, before its use-by, unused and matching. Unknown kinds fail closed (A15). Every transition writes its `approval.*` event (A16). The core never imports an agent by name; kinds come from `approval_kinds()` through `getattr`.
- **`expire_due()` also supersedes** live records of loaded kinds whose content changed or is gone (no re-raise; A15 still leaves unknown kinds alone), so the one-pager job's pre-build step catches stale requests the read model can't.
- **`on_approve` in the `ApprovalKind` protocol:** `on_approve(self, conn, subject, args: dict[str, str]) -> str | None`, optional, with a no-op default. `decide()` calls it inside the decision's `BEGIN IMMEDIATE` transaction after it writes `approved`. It may raise `approvals.BadArgs(text)`; the answer is then `refused` with that text and nothing is recorded. A returned string is appended to the answer text (the "Build it: …" line in 10). `decide()` refuses with `BadArgs` when any of the kind's `decision_args` is missing.
- `origin.py`: the `Origin` value type only (`terminal`, `ssh`, `refused(reason)`); detection is 04b.
- The fake kind declares `decision_args = ("promo_days", "post_days")` and an `on_approve` that records its call, so 11 can test the remote grammar without the real kind.
- `tests/test_approval_gates.py`: the gate-matrix harness (test strategy v3 §5), owned by this ticket alone. It collects adapters from every `tests/gate_adapter_*.py` module through `pytest_generate_tests`. This ticket ships `tests/gate_adapter_fake.py`; each kind ticket adds only its own adapter file. `tests/approval_world.py` holds only the core and fake-kind builders.
- ADR 0003 moves to accepted.

## Acceptance criteria

- [ ] **AC-M4.1** Given the request is missing, pending, skipped, expired, lapsed past its use-by,
  superseded or already used, when the gated action runs, then it refuses and nothing outward
  happens: no Resend call, no build handoff row, no flag change, no claim.
- [ ] **AC-M4.2** Given A-0412 approved over hash H1, when the draft body changes so the kind's
  `content()` hashes to H2 and the gated action runs, then it refuses, A-0412 becomes superseded,
  and A-0413 is raised over H2.
- [ ] **AC-M4.3** Given A-0412 approved, when the gated action runs, then `used_at` and `used_by_run`
  are set in a committed `BEGIN IMMEDIATE` transaction before the outward call; the Resend, Dispatch
  and publish doubles each assert at call time that the record is already used.
- [ ] **AC-M4.4** Given A-0412 approved, when two connections claim it at once, then exactly one
  succeeds.
- [ ] **AC-M4.5** Given A-0412 used once, when the gated action runs again for the same subject, then
  it refuses; a retry of the same outreach message under its existing idempotency key is not a
  second use.
- [ ] **AC-M4.6** Given a valid approval and the PAUSE file, a paused agent or the kind's own switch
  on, when the gated action runs, then it refuses and the approval is not claimed.
- [ ] **AC-M4.7** Given an approval whose kind's plug-in failed to import, when `use()` or
  `expire_due()` runs, then `use()` refuses and `expire_due()` leaves the record alone.
  *Owned here for the fake kind. Each real kind's ticket proves the same seven through its own adapter file: 05, 06, 10, 10b, browser-publishing#02 and #02b.*
- [ ] **AC-M6.1** Given `approve A-0412` arriving over SSH with actor `discord:111` and `--ref
  1234567890:dlv-77` at 10:02:15, then the record holds `decided_by = discord:111`,
  `decided_origin = ssh`, `decided_at = 2026-11-10T10:02:15+08:00` (growth's clock), the content
  hash and the ref; one `approval.approved` event carries the same.
  *Here: through `decide()` with an injected SSH origin. 11 proves it through `jura-growth remote`.*
- [ ] **AC-M6.2** Given the same `--ref` delivered twice, then the decision is recorded once and the
  second call returns the first answer with exit 0.
- [ ] **AC-M6.3** Given direct SQL that sets a decided record back to pending, changes its kind,
  subject or hash, changes a used record at all, or deletes a decided record, then the trigger
  aborts it.
- [ ] **AC-M6.4** Given `approve A-0412` typed in Terminal with the right code, then `decided_by =
  terminal:<macOS user>` and `decided_origin = terminal`, and the one-pager notes that the decision
  came from Terminal.
  *Here: the record, with an injected Terminal origin. 04b proves the real Terminal path; the one-pager's note is 08's.*
- [ ] **AC-M7.6** Given an SSH origin with actor `discord:999`, when `approve A-0412` runs, then it is
  refused (consistency check) and A-0412 stays pending.
- [ ] `on_approve` runs inside the decision transaction; a `BadArgs` from it, or a missing `decision_args` value, gives `refused` and records nothing; a returned string is appended to the answer.
- [ ] `expire_due()` supersedes a live record whose content changed or is gone, and leaves an unknown kind's records alone.
- [ ] `docs/adr/0003-an-approval-binds-to-content-and-is-claimed-once.md` says accepted.
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, every core case of the gate matrix runs with 0 skipped, `security-review` has run on `approvals.py`, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC §4.6 (A1 to A17 and the plug-in interface), §5.7, §5.3 (`approvals.py`, `origin.py`, `0003_approvals.sql`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T1, T2, T7, N6
- `.scratch/mission-control/reviews/technical-v2.md`: B1, B4, N1, N3; Seams; Specialist guidance (the trigger and indexes belong in the migration)
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §5 (the contract matrix), §3 (D7 approval world), §4.1 (AC-M4.x, AC-M6.x, AC-M7.6), §4.3 (X3, X7), §8 (concurrency, time zones), §11.2 row MC-04
- `docs/adr/0003-…`; `CONTEXT.md` (Approval request, Approval kind, Decision, Decide-by, Use-by, Claim, Gated action, Skip)
- Code: `jura_growth/db.py` (`transaction`, `migrate`), `log.py` (`event`), `agents/__init__.py`
