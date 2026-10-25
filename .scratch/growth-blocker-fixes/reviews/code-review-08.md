# Code review 08: tests and build runs never write to the repo or live data

- **Verdict:** approve
- **Branch:** `crew/growth-blocker-fixes-08-tests-never-touch-live-files` (035628b, 6851f96)
- **Point of comparison:** `crew/growth-blocker-fixes` at 01ce0e9 (merge-base). Diff: `git diff crew/growth-blocker-fixes...crew/growth-blocker-fixes-08-tests-never-touch-live-files`, 7 files, +273 / -4.
- **Spec:** `.scratch/growth-blocker-fixes/issues/08-tests-never-touch-live-files.md`
- **Reviewed on:** 2026-10-25. All seven changed files read in full at the branch tip.

The verdict is approve because there are no blocking findings. All three acceptance criteria hold when I re-run them. The two should-fix items are small and can follow in this branch or a later one.

## Evidence

All commands ran in the developer's worktree (`.claude/worktrees/agent-abc87f65c844b8aa4`) with `JURA_ROOT=/Users/tingy/OneDrive/Desktop/projects/jurasolutions`.

| Command | Result |
|---|---|
| `uv run pytest` with `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` on fresh temp folders | 530 passed in 19.48s |
| `uv run pytest` with neither variable exported | 530 passed in 19.28s |
| `uv run pytest <test files in reverse order>`, no exports | 530 passed in 22.47s |
| `stat` mtime and ctime of every entry under `jurasolutions/data/`, `jurasolutions/outputs/` and the main repo's `launchd/`, taken before and after the three runs (156 entries) | identical |
| `git status --porcelain --ignored` in the worktree, before and after | identical; no `launchd/generated/` created |
| `JURA_GROWTH_NOW=2026-10-26T07:00:00+08:00 jura-growth status`, no data or outputs override, real `JURA_ROOT`, run under a reviewer audit hook that refuses any open of the live folders | `Error: JURA_GROWTH_NOW=... freezes the clock, so this run would leave test data dated on that day in .../data/growth and .../outputs/growth. Point JURA_GROWTH_DATA_DIR and JURA_GROWTH_OUTPUTS_DIR at a temporary folder, or unset JURA_GROWTH_NOW.`, exit 1, the hook never fired |
| Same, with only the data folder on a temp folder | refusal names only the outputs folder and its variable, exit 1 |
| `jura-growth status`, no `JURA_GROWTH_NOW`, temp folders | exit 0 |
| `jura-growth status`, `JURA_GROWTH_NOW=` (empty), temp folders | exit 0 |
| `timeutil.frozen_clock_problem()` with no `JURA_GROWTH_NOW` and the real live paths | `None` |
| `pyright --pythonpath .venv/bin/python jura_growth/timeutil.py jura_growth/schedule.py jura_growth/paths.py` | 0 errors |

I never wrote to, opened, or deleted anything under the live `data/growth/` or `outputs/growth/`. The stale `growth.db-journal` is unchanged.

### The two questions in the brief

- **Can the frozen-clock refusal block Ting Yu's normal use?** No. `frozen_clock_problem()` returns at `timeutil.py:29-31` before touching any path when `JURA_GROWTH_NOW` is unset or empty, and `now()` takes the real-clock branch at `timeutil.py:52-58`. The launchd plists set only `PATH` and `PYTHONUNBUFFERED` (`schedule.py:108`). `.env` values are not loaded into `os.environ` (only `runner.py:187-197` sets run, agent and job IDs). `runner._abandon_stale` already used the real clock. The check is in the CLI root callback (`cli.py:40-43`), which is the right place: it runs before any command opens `growth.db`, so the stale journal is never rolled back by a refused run.
- **Can a write guard false positive make the suite flaky?** I found no nondeterministic path. The tests start no threads or subprocesses, so a late write can't be pinned on the wrong test. The `os.mkdir` exemption for existing folders is a plain `isdir` check. Bytecode and `.pytest_cache` writes are exempt. Three full runs in two orders were all green. The false positives that do exist are deterministic and environmental: pytest's own session-end outputs into the repo are refused (see N4). They fail every time, so they are not flaky.

## Standards

Sources: `CLAUDE.md`, `README.md`, `docs/agents/crew.md`, `docs/agents/domain.md`, `CONTEXT.md`, and the conventions in neighbouring code. Baseline smells are judgement calls.

### Blocking

None.

### Should fix

- **S1. `jura_growth/schedule.py:121-122`: `render()` writes without `paths.writable()`, and the new override can now point it at `inputs/`.** Rule: `paths.py:8-9`, "Every write helper in this package goes through `writable()`, which refuses them". The direct `mkdir` and `open(path, "wb")` were already there, but the folder was fixed to `launchd/generated/`. This branch made it configurable (`schedule.py:40-42`), so the read-only guard now matters. Reproduced in a scratch root: `JURA_GROWTH_PLIST_DIR=<root>/inputs/plists` rendered `sg.jurasolutions.growth.heartbeat.plist` into `inputs/`, where `paths.writable()` refuses the same location. Fix: `path = paths.writable(generated_dir() / f"{label(job)}.plist")`.

### Nits

- **N1. Duplicated code and possible feature envy, `timeutil.py:24-48`.** The check "at or under `JURA_ROOT/<folder>`" (`timeutil.py:37-38`) repeats the loop in `paths.writable()` (`paths.py:71-73`). `frozen_clock_problem` works almost entirely on `paths` data, and it makes `timeutil` import `paths` for the first time. One `paths` helper, plus a `LIVE = ("data", "outputs")` next to `READ_ONLY`, would give both callers one definition. The double check (CLI callback and `now()`) is justified: the callback has to run before the database opens, and `now()` covers non-CLI callers.
- **N2. Names.** `schedule.generated_dir()` (`schedule.py:40`) is set by `JURA_GROWTH_PLIST_DIR`. Its neighbours are named after their variables (`launch_agents_dir`, `prompts_dir`), so `plist_dir()` would fit. `FrozenClockRefused` (`timeutil.py:20`) breaks the `*Error` pattern most exceptions here follow (`JobError`, `DiscordError`, `RenderError`).
- **N3. Proportionality, `tests/conftest.py:91-93`.** `prompts/` is copied for all 530 tests, but only the three `test_claude_*` tests in `test_core.py` write a prompt, and the guard allows reads of the real folder. A fixture used only by those three would do. The copy is cheap (the suite took 19.5s against the card's 16s baseline, and only part of that is the copy), and `test_isolation.py:69-73` locks the per-test copy in.
- **N4. The guard refuses pytest's own outputs into the repo or `jurasolutions/`.** Reproduced: `pytest tests/test_isolation.py --junitxml=<guarded root>/report.xml` dies at session end with `PermissionError: tests must not write into the repo or jurasolutions/: open .../report.xml`. The same would hit `pytest --cov`, which writes `.coverage` with SQLite in the working directory. Neither is configured today (no CI, no pytest-cov), so this is a nit. If either is added, exempt it or write it outside the repo.
- **N5. `isolated` docstring, `tests/conftest.py:83-84`.** It doesn't mention the plist folder, the prompts copy, or that the guard fails a test.

## Spec

### Blocking

None. Each acceptance criterion holds when re-run (see Evidence):

- "After `uv run pytest`, `git status` shows no change and nothing under `jurasolutions/data/` or `jurasolutions/outputs/` has changed": met. Note that `launchd/generated/` is gitignored (`.gitignore:15`), so `git status` alone could never have caught the original bug. The mtime comparison and the write guard are the real proof.
- "`JURA_GROWTH_NOW=2026-10-26T07:00:00+08:00 jura-growth status` with no `JURA_GROWTH_DATA_DIR` exits with a clear refusal": met. Exit 1, the message names the folder, the variable to set, and the alternative, and it appears before any database open (`test_isolation.py:101` asserts the data folder is never created).
- "`uv run pytest` passes": met, 530 passed.

"Give `schedule.render()` an output-folder override ... and point it at a temp folder in `tests/conftest.py`": done (`schedule.py:40-42`, `conftest.py:90`). `schedule install` (`schedule.py:142`) and a manual `schedule render` keep the old default.

"Find the other tests that write into the repo or the real `jurasolutions/` folders": done. The three `test_claude_*` tests wrote `fake.md` into `prompts/`; they now get a per-test copy (`paths.py:48`, `conftest.py:91-93`). The guard staying green across the suite shows no other in-process test writes there.

"Don't touch the live database": respected. The diff has no data changes, and the mtimes are identical.

### Should fix

- **S2. `README.md:158-160` overclaims the guard.** "Its write guard fails any test that writes into this repo or anywhere under `jurasolutions/`" is not quite true. Subprocess writes are outside the audit hook. Operations relative to an open folder (`dir_fd`) are skipped (`conftest.py:63`). `__pycache__` and `.pytest_cache` are exempt (`conftest.py:37`, `55`). The conftest docstring states these limits and the README should too. The ticket exists because `README.md:157` made a claim the code didn't keep, so this line should be exact.

### Nits (scope)

- **N6. The write guard (`conftest.py:10-78`, `103-115`, `test_isolation.py:20-49`) goes beyond "point them at temp folders".** I accept it. It is the only regression check that would catch the gitignored `launchd/generated/` case, and refusing even read-only SQLite opens protects the stale journal. Two small gaps: violations raised during collection or in higher-scoped fixtures are discarded by `GUARD.take()` at the next test's setup (`conftest.py:103`), although the `PermissionError` still raises. `os.rename` checks only `src_dir_fd`, and `os.chown` isn't covered.
- **N7. The refusal also covers the outputs folder (`timeutil.py:35`).** The ticket asks only for a temp `JURA_GROWTH_DATA_DIR`. The wider scope is justified by infra A6 (`outputs/growth/social/2026-10-26/` was left behind) and matches the operating card. The only user-facing description is the `timeutil.py` docstring.
- **N8. Library callers aren't refused before the database opens.** Calling `db.connect()` directly under a frozen clock opens the live `growth.db` before `timeutil.now()` raises. No dated row can be written, but the open alone can roll back the stale journal. Every real entry point (`jura-growth`, launchd, headless runs, `python -m`) goes through the CLI callback, so this is noted only.

## Security

`security-review` method applied to this ticket's diff. No findings at or above the reporting threshold.

- `JURA_GROWTH_PLIST_DIR` and `JURA_GROWTH_PROMPTS_DIR` are trusted environment input. A headless run can't set them: its allowlist is `Bash(jura-growth:*)`, and prompts are read only by `run`, which is refused. The `inputs/` reach in S1 is a guard gap, not an exploit.
- The refusal message echoes only the timestamp and folder paths. No secrets reach the output or the logs.
- The audit hook is test-only. The diff adds no SQL, no subprocess calls, and no secret or credential handling.

## Blocked paths

None touched. The diff changes `README.md`, `jura_growth/{cli,paths,schedule,timeutil}.py` and `tests/{conftest,test_isolation}.py`. Nothing is under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.

## Reuse

No new code duplicates a standard-library feature or an installed dependency. The duplication within the repo is N1 (`paths.writable()`'s containment check).

## Cross-ticket note

`cli.py:40-43` adds four lines to the root callback, which ticket 01 also edits. Ticket 01 is not yet on `crew/growth-blocker-fixes` (ticket 03 is), so the conductor should expect a small merge in `cli()`. The refusal must stay ahead of anything that opens `growth.db`.
