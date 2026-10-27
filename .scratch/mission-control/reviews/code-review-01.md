# Code review 01: the runner and the guards (MC-01)

- **Branch:** `crew/mission-control-01-runner-and-guards` at `c2d57eb` (commits `8342675`, `29e9586`, `8b24306`, `c2d57eb`).
- **Compared against:** the fixed point `1acc1eb`, with `git diff 1acc1eb...crew/mission-control-01-runner-and-guards`. That covers 13 files, and I read every one in full.
- **Specification:** `.scratch/mission-control/issues/01-runner-and-guards.md`, plus PRD MC §4.5, §5.3, §5.8, AC-M1.5, AC-M7.1, AC-M8.11 and AC-M15.1. Also `reviews/tickets-technical.md` T3, `reviews/test-strategy-v3.md` §2, §4.3 X1 and §11.2 row MC-01, and the operating card `docs/agents/crew.md`.
- **Reviewed:** 2026-10-25.

## Verdict: approve

There are no blocking findings. Every acceptance criterion in the ticket is met, and I reproduced each one either by running the tests or by reading the code. Live outreach is refused before anything is sent, not just warned about. No scheduled run behaves differently than it did before this branch. The should-fix items below can be fixed on this branch before the merge, or carried to the tickets named against them.

## Evidence (run by the reviewer)

All runs used the developer's worktree `.claude/worktrees/agent-abf36f1b6fb7ea476`, read-only, with `JURA_ROOT=/Users/tingy/OneDrive/Desktop/projects/jurasolutions` and `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` set to fresh `mktemp -d` folders.

- **Full suite.** `uv run pytest -p no:cacheprovider -o addopts="" -q` printed **1042 passed in 23.01s**. The baseline was 987, so the branch adds 55 tests. A run with `-rs` reported nothing skipped.
- **New and changed test files.** `uv run pytest -rs tests/test_runner.py tests/test_network_guard.py tests/test_outreach_approval.py tests/test_headless.py` printed **109 passed**, with 0 skipped.
- **AC-M15.1.** I took snapshots before and after the full run: `git status --porcelain` in the worktree and in the main checkout, and the modification time and size of every file under the live `jurasolutions/data/` and `jurasolutions/outputs/`. All three were identical before and after. The network guard failed no test, and every test that provokes it on purpose clears its own record.
- **Pyright** (advisory, from the Standards reviewer). The six changed source files show the same 5 errors on the branch as at `1acc1eb`. The branch adds no new errors.
- **`*.localhost` lookups.** I checked that this Mac's resolver answers `publish-fixture.localhost` locally (`::1` and `127.0.0.1`, in 0.07s). The lookup the guard lets through never leaves the machine.

## Blocked paths

None of the changed files is under `jurasolutions/inputs/`, `jurasolutions/design-system/`, `.env` or the live `jurasolutions/data/growth/`. The diff touches only `docs/adr/`, `jura_growth/` and `tests/`. **Pass.**

## Standards

### Blocking

None.

### Should fix

1. **The README is out of date on a security property.** `README.md:115` still says the refused commands are "`run`, `resume`, `schedule` and `discord` always". `headless.NEVER` (`jura_growth/headless.py:45`) now also holds `approve`, `skip`, `approvals` and `remote`.
   - The README's plug-in table (`README.md:151-159`) doesn't list `NothingToDo`, `after_run`, `run_update` or `approval_kinds`. Only the docstring in `jura_growth/agents/__init__.py:25-56` was updated.
   - The Tests section (`README.md:167` onwards) describes the write guard but not the new network guard.
   - Rule: `repos/growth/CLAUDE.md` says "`README.md` covers layout, commands, tests and the plug-in interface."
2. **The code uses a word the glossary says to avoid.** `CONTEXT.md:82` says, for "Run update": "_Avoid_: notification, log line". The diff calls it a notification anyway:
   - the function `_notify` (`jura_growth/runner.py:159`) and its docstring at `:160`;
   - the module docstring;
   - the test section heading and the `notified` fixture in `tests/test_runner.py`.

   The ticket itself says "Core run-update notification", so the developer followed the ticket. Even so, ticket 03 will build on these names, and `_run_update` is a cheap rename now. Rule: `docs/agents/domain.md` and `CONTEXT.md`.
3. **The new tests duplicate existing test helpers** (reuse).
   - `tests/test_runner.py` `fake_claude` repeats `tests/test_core.py:199` `_fake_claude`.
   - `_with_jobs` and `claude_job` repeat `tests/test_core.py:212` `_settings_with`, and the `failing_job` fixture in `tests/test_discord_down.py`.
   - `mirrored` repeats the mirror-file reading in `tests/test_core.py`.
   - `events` and `run_rows` call `conn.execute` directly instead of `db.rows` (`jura_growth/db.py`), which the rest of the suite uses.

   Move the shared ones into a common helper, the way `test_scout_support.py` is already shared, or reuse them where they are.

### Nit

4. **The glossary's "Quiet run" is now too narrow.** `CONTEXT.md:27-29` defines a quiet run as a run of a job "marked quiet". A `NothingToDo` precheck now makes a quiet run whatever the job's flag. ADR 0001 was updated; the glossary entry wasn't.
5. **Two job lists are built two ways.** `tests/test_headless.py:376` builds `COMMAND_JOBS` by loading `settings.yaml` with `yaml.safe_load`, while `ALL_JOBS` and `CLAUDE_JOBS` in the same file use `config.settings()`. If loading the raw YAML is deliberate (generating from the file itself), say so in a comment. Otherwise use `config.settings()` and drop the `yaml` import.
6. **One import is out of order.** In `tests/test_outreach_approval.py:15`, `import pytest` comes after the local imports.
7. **Imports repeated inside test bodies.** `from jura_growth import pause` is imported inside six test functions in `tests/test_runner.py`. One import at the top of the file would do.
8. **Two hooks share a name.** The plug-in hook `after_run(conn, job, run_id, outcome)` and the core `run_update.after_run(conn, job, spec, run_id, outcome)` have the same name, different signatures and different call points, and both log their errors as `run.after_run_error`. The `hook` field in that event tells them apart, so this works. The shared name will still confuse whoever writes ticket 03.

## Spec

### Blocking

None.

### Should fix

1. **A quiet run reaches the run update in two different shapes.** A `NothingToDo` precheck passes `Outcome("ok", str(reason))` to `run_update.after_run`, with the reason as its summary (`jura_growth/runner.py:110`). A quiet command job with nothing to do passes `Outcome("ok")` with no summary (`:147`). The runner's own test for "nothing happened" is `outcome.status == "ok" and not outcome.summary` (`:143`), so a `NothingToDo` quiet run looks like a run that did work. That is the line ticket 03's run update will need to draw.
   - Spec: "When the runner sees one, it writes `run.quiet {"job", "started_at", "reason"}`, never `run.skipped`" (ticket, What to change). The spec doesn't say what status or summary the hand-off should carry.
   - No current precheck returns `NothingToDo`, so nothing regresses today.
   - Either keep the reason out of `summary` (put it on a field of its own), or record the decision as a note in ticket 03 so that it tells quiet runs apart by path rather than by summary.
2. **Some exception paths skip the run update.** Spec: "The runner calls it once on every path except the PAUSE file". If a precheck, `log.finish_run`, `discord.alert` or `pause.check_auto_pause` raises, the exception leaves `_run_locked` (`jura_growth/runner.py:105-107` and `:149-156`) and `run_update.after_run` is never called.
   - Before this branch, those exceptions escaped too, and `discord.post` spools to the outbox rather than raising on a Discord failure. In practice, only a database or programming error reaches this path.
   - The paths the spec lists are all covered. Exception paths aren't in the spec, so this isn't a defect in 01. Give ticket 03 a note, since a crashed run would post no run update.

### Nit

3. **The ordering test doesn't prove the order.** `tests/test_runner.py:366` `test_a_failed_run_notifies_once_after_the_alert_and_auto_pause` reads the alerts and the pause state after `run()` returns, not when the notification fires. It would still pass if the notification fired before the alert. The code order is right (`runner.py:149-156`). Record the pause state and the alert count inside the `notified` fixture to prove it.
4. **The gate is a seam the ticket didn't ask for.** `send.approval_gate_problem()` (`jura_growth/agents/outreach/send.py:70`) is a function of its own, and `tests/test_scout_support.py` `live_ready(approval_gate=True)` stubs it out. X1 says "The existing outreach tests pass unchanged". Their test files didn't change, but the shared helper did. The seam is reasonable, because MC-06 replaces the line and AC-M8.12 brings an approval fixture anyway. Recorded so MC-06 knows to remove the stub.
5. **The network guard leaves some routes open.** It hooks only `socket.getaddrinfo` and `socket.connect`, which is exactly what test strategy §2 names. It doesn't hook:
   - `socket.gethostbyname`, `gethostbyname_ex` and `gethostbyaddr`, which raise audit events of their own;
   - `socket.sendto`, for UDP;
   - subprocesses, which its docstring admits.

   None of these is required, and `httpx` goes through `getaddrinfo`. They are worth adding when the subprocess-based fake-`claude` scenarios in §2 arrive.

### Verified against the spec

- **X1 and the quiet-run trace.** A quiet run with nothing to do writes one `run.quiet {"job", "started_at"}` event and no run row. A quiet run that did work gets its run row with its real start, using `log.start_run(..., started_at=)` (`jura_growth/log.py:61`). The test proves it with a frozen clock that jumps four and a half minutes. Failures and skips write no `run.quiet`, and neither does a job that isn't quiet.
- **`NothingToDo`.** A `NothingToDo` precheck writes one `run.quiet` with its reason and no run row, whatever the job's `quiet` flag. Any other precheck string is still a skip with a skip row.
- **A quiet claude job.** It gets its run row before Claude starts. The fake `claude` records `JURA_GROWTH_RUN_ID`, which equals the row id, and the transcript is `<id>-fake.jsonl`. The only quiet job in `config/settings.yaml:73` is `scout-send`, a command job, so no scheduled job behaves differently.
- **The plug-in `after_run` hook.** It runs only for runs that actually started, after the job body and before `finish_run`. A returned `Outcome` replaces the original. Three replaced failures put three failed rows in `runs`, post three alerts and auto-pause the agent. A hook that raises leaves the original outcome and writes `run.after_run_error`.
- **The core notification.** It runs exactly once on each listed path: the pause-flag, schedule and precheck skips, a quiet run with nothing to do, a `NothingToDo` run, and a finished run after its row is finished. On the lock skip it gets `conn=None`, and `db.connect` is never called. It never runs for the PAUSE file.
- **AC-M7.1, layers 1 and 2.** `headless.NEVER` holds `approve`, `skip`, `approvals` and `remote`, and not `one-pager`. `claude_rules` denies each of the four both bare and with `:*` for every claude job, and `may_use` refuses them for every job.
- **AC-M1.5.** The test builds its job list from `config/settings.yaml`. Every command job resolves to a real CLI command and passes `may_use`.
- **AC-M8.11, the first line: live outreach is refused, not just warned about.** `live_problems()` always lists "approval gate not installed".
  - `_send_due` refuses in live mode before `due()`, before the registry and before any Resend client exists (`send.py:273-276`). The test shows no Resend call, the message still `queued` and an `#alerts` post naming the gate.
  - `requeue_shadow` raises before it touches any row, `--dry-run` included (`requeue.py:85`), and the CLI exits 1.
  - Setting `mode: live` doesn't open a path around these checks: every live Resend send goes through `_send_due`.
  - The gate is a constant in code, so no config, env or flag can clear it before MC-06.
- **The network guard and its self-test.** The self-test resolves `discord.com` and connects to `1.1.1.1:443`, expects both refused, and finds both recorded. A refusal the test swallows is still recorded, and the `isolated` fixture fails that test.
- **ADR 0001.** It says accepted, with the precheck sentence.
- **No regressions.** `agents.by_name` now runs before the pause check. It is cached, catches import errors and returns `None`, so this is harmless. The outreach plug-in's precheck still returns `None`.

## Security

I ran the `security-review` skill, but it diffed the main checkout's branch (`crew/mission-control`, docs only) rather than the ticket branch. I therefore did the security pass by hand on the right diff.

### Blocking

None.

### Should fix

None.

### Nit

None.

### Checked

- **The deny rules** (`headless.py:45`, `:127-128`) only add denials; nothing is newly allowed. The decision and control commands don't exist yet, so the refusal in code (exit 2 with "refused:") still belongs to 04b and 11a, as the test strategy assigns it.
- **The approval gate fails closed.** No setting or secret can lift it.
- **Hook errors** are written through `log.event`, which runs `config.redact` over the payload. An exception text holding a secret value is masked the same way as every other event. The text is also cut at 500 characters.
- **`run_update.py`** does nothing and takes no outside input.
- **Money and personal data.** The only path that touches either is outreach sending, and this branch makes it stricter.
