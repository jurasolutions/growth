# 01 — MC-01 prefactor: the runner and the guards

Status: ready-for-agent
Blocked by: - (precondition for every ticket in this folder: `crew/growth-blocker-fixes` is merged into `main` through its G4, and the conductor's first commit on `crew/mission-control` adds `CONTEXT.md`, `docs/adr/` and both feature folders before any worktree)
PRD ticket: MC-01 in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC2 (the quiet-run trace), SC3 (the call sites only), SC7 (the first two layers), SC8 (the first guard line), SC15; ADR 0001

## What to build

A quiet run that found nothing to do leaves a trace, so the one-pager can later tell it from a slot the Mac slept through. The runner gains its two call sites: a plug-in `after_run` hook that can change a run's final outcome (the publish audit needs that), and a core run-update notification on every path a run can take, including skips and the lock skip, so ticket 03 fills in `run_update.py` without touching `runner.py`. `runner.py` changes here and in browser-publishing#03 only. Before any approval code exists, the guards are in place: no headless run can call the decision or remote commands, live outreach refuses because the approval gate isn't installed yet, and the suite can't reach the network.

## What to change

- **The quiet-run trace.** When a quiet `command` job succeeds with nothing to do, `runner._run_locked` writes an append-only `run.quiet` event `{"job", "started_at"}`. A quiet run that did work records its real start through `log.start_run(..., started_at=)`.
- **`NothingToDo`.** `agents/__init__.py` gains `class NothingToDo(str)`. When a precheck returns one, the runner writes `run.quiet {"job", "started_at", "reason"}`, never `run.skipped`, whatever the job's `quiet` flag. Any other precheck string stays a skip, as today. ADR 0001 gains one sentence about prechecks.
- **A quiet `claude` job still gets its run row before Claude starts**, so its environment, transcript name and `used_by_run` carry a real run id. `quiet` keeps its meaning only for `command` jobs.
- **Plug-in `after_run(conn, job, run_id, outcome) -> Outcome | None`.** Called in `_run_locked` after the job body and before `finish_run`, only for runs that actually started. A returned `Outcome` replaces the original, so the run row, `#alerts` and `check_auto_pause` all see the final status. An exception is logged as a `run.after_run_error` event and the original outcome stands.
- **Core run-update notification.** A new `jura_growth/run_update.py` with `after_run(conn | None, job, spec, run_id, outcome) -> None`, which does nothing yet. The runner calls it once on every path except the PAUSE file: a pause-flag, schedule or precheck skip; a quiet run with nothing to do; a finished run, after `finish_run`, the alert and auto-pause; and the lock skip, with `conn=None`, so the database is never opened. It is wrapped like the plug-in hook.
- The plug-in protocol docstring in `agents/__init__.py` names the optional hooks the later tickets add (`approval_kinds()`, `run_update()`, `after_run()`), discovered with `getattr` like `digest()`.
- `headless.NEVER` gains `approve`, `skip`, `approvals` and `remote` (not `one-pager`, which is a scheduled job). The Claude Code rules the runner builds for every claude job deny all four.
- A test generated from `config/settings.yaml` that every scheduled command job passes `headless.may_use` and that its command resolves to a real CLI leaf (`headless.command_name` is not empty), so the `one-pager` job (09) is covered the day it lands.
- `send.live_problems()` in `agents/outreach/send.py` lists "approval gate not installed". While it shows, `outreach.mode: live`, `send-due` in live mode and `requeue-shadow` refuse. Ticket 06 replaces the line.
- **The network guard** (test strategy v3 §2): a second session audit hook in `tests/conftest.py` on `socket.connect` and `socket.getaddrinfo` that refuses and records anything that isn't loopback, with its self-test. This is the only ticket in the first wave that touches `conftest.py`.
- ADR 0001 moves from proposed to accepted.

## Acceptance criteria

- [ ] **AC-M1.5** Given `JURA_GROWTH_JOB=one-pager`, when the scheduled job runs its own command, then
  `headless.may_use` allows it. A test asserts this for every scheduled command job.
- [ ] **AC-M15.1** After `uv run pytest`, `git status --porcelain` is unchanged, the live
  `jurasolutions/data/` and `outputs/` folders are unchanged, and the network guard recorded no
  connection outside loopback.
  *This ticket owns AC-M15.1 and its network guard. Every later ticket keeps it passing.*
- [ ] **X1, from MC §4.5.** When a quiet job succeeds with nothing to do, `runner._run_locked` writes one append-only `run.quiet` event and no run row. A quiet run that did work records its real start. Failures and skips don't write `run.quiet`, and a job that isn't quiet never writes it. The existing outreach tests pass unchanged.
- [ ] A `NothingToDo` precheck writes one `run.quiet` with its reason and no run row; any other precheck string writes a skip as today.
- [ ] A quiet `claude` job's transcript and environment carry a real run id.
- [ ] The core notification runs exactly once on each path listed above, with `conn=None` on the lock skip, and never for the PAUSE file.
- [ ] A plug-in `after_run` that returns a failed `Outcome` is what the run row, the alert and auto-pause record. One that raises leaves the original outcome, and a `run.after_run_error` event is written (the hook half of AC-M3.6, which 03 owns).
- [ ] **The first layers of AC-M7.1 (owned by 04b).** `headless.NEVER` holds `approve`, `skip`, `approvals` and `remote`, and the Claude Code rules for every claude job deny them.
- [ ] **The first sentence of AC-M8.11 (owned by 06).** Before MC-06 lands, `live_problems()` lists "approval gate not installed", and live mode, live `send-due` and `requeue-shadow` refuse.
- [ ] The network guard's self-test resolves `discord.com` and connects to `1.1.1.1:443`, expects both refused, and finds both recorded.
- [ ] `docs/adr/0001-quiet-runs-leave-an-event-not-a-run-row.md` says accepted, with the precheck sentence.

## Done when

Every criterion above passes, `uv run pytest` passes above the 987 baseline with 0 skipped in the new tests, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC §4.5, §4.6 A8 (the `NEVER` layer), §5.3 (`runner.py`, `log.py`, `headless.py`), §5.8 (the guard), §5.12, §5.13
- `.scratch/mission-control/reviews/tickets-technical.md`: T3, T12, N2
- `.scratch/mission-control/reviews/technical-v2.md`: B5, B6, N7
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M1.5, AC-M7.1, AC-M8.11, AC-M15.1), §4.3 (X1), §2 (network guard), §11.2 row MC-01
- `docs/adr/0001-quiet-runs-leave-an-event-not-a-run-row.md`; `CONTEXT.md` (Quiet run, Slot, Run)
- Code: `jura_growth/runner.py` (`run`, `_run_locked`), `log.py`, `headless.py` (`may_use`, `command_name`), `agents/__init__.py`, `agents/outreach/send.py`, `tests/conftest.py`
