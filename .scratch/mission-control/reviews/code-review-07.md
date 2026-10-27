# Code review 07: the slot classifier (MC-07)

- **Branch:** `crew/mission-control-07-slot-classifier` at `7db030f`, reviewed against the fixed point `8bff848` (`git diff 8bff848...crew/mission-control-07-slot-classifier`)
- **Changed files:** `jura_growth/slots.py` (new, 214 lines) and `tests/test_mission_slots.py` (new, 437 lines). I read both in full.
- **Spec:** `issues/07-slot-classifier.md`; PRD SC2 (AC-M2.1 to AC-M2.4), §4.5 and §5.3; test strategy v3 rows AC-M2.1 to AC-M2.4, D1, §8 and §11
- **Date:** 2026-10-25

## Verdict: approve

There are no blocking findings. Every acceptance criterion assigned to MC-07 has a passing test. The classifier is pure: it opens no file, database or socket when given a `business_day` callable, and importing it loads neither `sqlite3`, `db` nor `log`. No blocked path is touched, and the security pass found nothing.

Nine findings are *should fix*. Two of them change what the one-pager tells Ting Yu (S-1 and S-2), and one breaks on the repo's own row type (S-3). These should be fixed before 08 builds on the classifier, either in a follow-up commit on this branch or as the first step of 08.

## Evidence

All commands ran in the developer worktree `.claude/worktrees/agent-a0ba27a3ea50c8a1d`, with `JURA_ROOT` set and the data and outputs variables pointing at `mktemp -d` folders.

| Command | Result |
|---|---|
| `uv run pytest -p no:cacheprovider` | 1159 passed in 23.47s |
| `uv run pytest -p no:cacheprovider tests/test_mission_slots.py` | 117 passed (39 tests, each run under 3 time zones) |
| `pyright --pythonpath .venv/bin/python jura_growth/slots.py tests/test_mission_slots.py` | 0 errors, 0 warnings |
| `git status --short` in the worktree after the suite | clean |
| `git diff --name-only 8bff848...HEAD` | only the two files above, so no blocked path is touched |
| E6 greps (`db.connect`, `paths.writable`, `flock`, …) in `slots.py` | no hits |
| Probe script `scratchpad/probe07.py` and inline probes | results quoted in the findings below |

There is no build. The operating card says nothing is built or deployed.

## Standards

### Blocking

None.

### Should fix

- **ST-1. The domain type uses a name the glossary forbids.** `slots.py:90` `class SlotState`, `slots.py:195` `_state`, `slots.py:107` `states`, and in the tests `state()` at `test_mission_slots.py:241` and `states` at :249. CONTEXT.md, under **Slot status**, says "_Avoid_: result, state". Rename them to `SlotStatus` and `_slot_status` (or similar) before 08 imports the name.
- **ST-2. `BUSINESS_DAY_KINDS` is copied, not shared (reuse).** `slots.py:27` repeats `runner.py:41` word for word. Nothing checks that the two stay equal. I confirmed they are equal today with `slots.BUSINESS_DAY_KINDS == runner.BUSINESS_DAY_KINDS` → True. The copy was made so that `slots` would not import `runner`, which imports `db`. `schedule.py` is imported by both modules and imports no database code (`config, paths, timeutil`), so the constant can live there and both modules can import it. The launchd weekday formula `(day.weekday() + 1) % 7` at `slots.py:121` also repeats `schedule.py:84`. Duplicating a schedule shape this way is what lets a new kind, such as BP's daily repeating shape (test strategy X4), drift between the runner and the classifier.
- **ST-3. `mac_zone` undoes the suite's isolation before `isolated` tears down.** At `test_mission_slots.py:34-40`, `monkeypatch.undo()` acts on the test's shared `monkeypatch`. That reverts every variable that conftest's `isolated` fixture set (`JURA_GROWTH_DATA_DIR`, `_OUTPUTS_DIR`, `_DISCORD`, `JURA_PRD_DIR`, …) while `isolated`'s own teardown (`conftest.py:163-170`) is still to run. That teardown writes nothing today, so nothing breaks yet, but any later teardown step would then see the live paths. Fix: save and restore `TZ` alone, or let pytest undo the patch and call `time.tzset()` in a finalizer registered before it.

### Nit

- **ST-4.** `sys.addaudithook(_watch)` at `test_mission_slots.py:361` installs a permanent, process-wide hook when the module is collected. This duplicates the guard pattern `conftest.py` already uses (`GUARD`, `NETWORK`, `take()`). A conftest-level hook would fit the suite better.
- **ST-5. Duplicated tests.** `test_a_quiet_run_seconds_after_its_slot_is_ok` (:394) repeats the AC-M2.1 param "quiet run at 10:00:03" (:106). `test_slots_the_mac_slept_through_…` (:405) repeats "slept through three slots" (:107-113). Also, :421 builds `slots.Record("run", …)` with a literal string instead of the `run()` helper or `slots.RUN`.
- **ST-6.** `Record.is_skip` (`slots.py:79`) and the `_state` docstring (:198-200) use a bare "skip" next to slot statuses. CONTEXT.md, under **Skip**, says "_Avoid_: bare 'skip' in mixed contexts". This is minor.
- **ST-7.** `_state` takes seven positional arguments (`slots.py:195-197`). This is a possible data clump: per-job context (`now`, `first`, `loaded`) is mixed with per-slot values (`at`, `end`, `window`). It's a judgement call.

## Spec

### Blocking

None. Each row of AC-M2.1 has a test that passes. Row 1 is tested on Fri 2026-11-06 rather than the frozen day, because row 2 uses the same 10:00 slot on 11-10. That is reasonable, and noted here. AC-M2.2 (the dedupe test at :182), AC-M2.3 (the order and the counts) and AC-M2.4 (the statuses; the listing belongs to 08) also hold.

### Should fix

- **S-1. A paused agent on a holiday hides a missed slot.** At `slots.py:86` and :179-187, only a skip whose reason starts "not a business day" is set aside. The runner, however, checks pause before the schedule: the PAUSE file at `runner.py:74-77`, and `pause.is_paused` before `_schedule_reason` at `runner.py:102-104`. So on a holiday with the agent paused, the record is "paused: …", it falls into the previous business day's window, and an unrecorded slot reads skipped instead of missed. Reproduced: scout-research ok on Thu 11-05, nothing on Fri 11-06, and a skip row "paused: scout" on Mon 11-09 (observed Deepavali) → Friday shows `('skipped', 'paused: scout')`. `test_a_holiday_skip_does_not_hide_the_miss_before_it` (:142) exists to prevent exactly this outcome, but it only covers the holiday reason. PRD §4.5 says "A skip whose reason starts 'not a business day' counts for no slot", and §4.5 also says a slot "is missed only once that next slot has passed with nothing recorded". The reason-prefix rule doesn't fully deliver the second sentence. Recommended fix: a skip of a business-day kind that lands on a day with no slot for that job counts for no slot, whatever its reason. Keep the prefix rule as well.
- **S-2. A quiet run that is still going reads as missed.** A quiet command job writes nothing until it finishes (`runner.py:120`, :142-148), so scout-send can never show **running**. Reproduced: a 10:00 run still going at 10:12, with the lock skip "previous run still going" at 10:10 → `[('10:00', 'missed'), ('10:10', 'skipped')]`. This corrects itself once the run finishes, but an on-demand one-pager (AC-M1.6) taken in that gap shows a false missed slot, which ranks second only to failed. Recommended fix: when the next window holds a "previous run still going" skip and nothing of its own, read the earlier slot as **running**. Alternatively, accept this explicitly in §4.5.
- **S-3. `Record.from_run` fails on the repo's own row type.** `slots.py:66` calls `row.get("summary")`. `db.connect()` sets `row_factory = sqlite3.Row` (`db.py:23`), and `sqlite3.Row` has no `.get`. Reproduced: `AttributeError: 'sqlite3.Row' object has no attribute 'get'`. `from_event` happens to work with a Row, but only because `"payload" in row` searches the row's values, not its keys (`slots.py:48`). These constructors exist for 08 to feed the classifier. Index the columns (`row["summary"]`), or say in the docstring that callers must pass `dict(row)`, and add a test that uses a real `sqlite3.Row`.
- **S-4. AC-M2.3 doesn't classify a mixed publish day.** Test strategy row AC-M2.3 says "Table-driven over the eight statuses for scout-send and `publish` cells". The table test builds hand-made states labelled `scout-send` (:241-254), and publish is only checked as ok plus upcoming (:133-139). Add one mixed publish day that goes through `classify`.
- **S-5. The classifier relies on a contract that isn't written down for 08.** The docstring at `slots.py:157-159` says "Pass one record from before the first day for each job". Ticket 08 doesn't say this. Without that record, a job installed before the window shows its first slot as **not installed** instead of **missed** (`test_a_record_from_before_the_days_shown_still_counts_as_the_first`, :201). The conductor should add this to `issues/08-read-model-and-one-pager-text.md`.
- **S-6. The D1 fortnight fixture is partial.** Test strategy §3 D1 calls for "ok, failed and running runs; a `skip_run` row; … PAUSE-file and lock skips in the JSONL mirror only; … a community weekly slot". The `D1` list (:72-92) holds only ok runs, `run.quiet` events and the holiday skip. The other cases appear in separate tests. That is enough for the MC-07 rows, but 08 also reuses D1, so build the complete dataset once and share it.

### Nit

- **S-7.** A slot whose window ends exactly at `now` is already missed (`slots.py:212`, `end > now`). §4.5 says "once that next slot has passed". At 10:10:00 the 10:10 run has only just started, so `end >= now` reads closer to the spec. `test_the_friday_window_runs_to_the_next_business_day` (:302) pins the current behaviour.
- **S-8.** A naive `now` is read in the Mac's own zone. `now.astimezone(SGT)` at `slots.py:165` treats a naive time as local, whereas the repo's own rule (`timeutil.parse`) treats it as SGT. Reproduced with `TZ=America/New_York`: a naive 11:05 gives `{'missed': 42, 'due': 1}`, while the aware SGT time gives `{'missed': 9, 'due': 1, 'upcoming': 33}`. Real callers pass `timeutil.now_sgt()`, so this only bites a careless caller. Either refuse a naive time or use `timeutil.parse`'s rule. The three-zone fixture never exercises this path, because every `now` in the tests is aware.
- **S-9.** A run status outside the eight slot statuses passes straight through `_state` (`slots.py:205`), and `day_cell` then raises `KeyError` (`slots.py:110`). Reproduced with status "abandoned". The runner writes only ok, failed, skipped and running today, but a plug-in's `after_run` hook can return any `Outcome`. Map unknown statuses to failed.
- **S-10. Holiday handling differs between the runner and the classifier for mixed schedules.** The runner skips the whole job on a holiday if any of its kinds is a business-day kind (`runner.py:186-191`). The classifier filters kind by kind (`slots.py:124`). No job in `settings.yaml` mixes kinds, so this is a latent drift only. It goes away with ST-2.
- **S-11. Scope.** The `installed=` and `business_day=` keyword arguments go beyond the PRD signature. `installed` is needed for AC-M2.4, and `business_day` makes the purity test possible, so both are justified. `SlotState.records` and `Record.from_*` lean towards read-model work, which is acceptable.

### Edge cases probed (brief)

| Case | Result |
|---|---|
| Mac asleep 09:30 to 10:50, one coalesced run at 10:58 | 8 missed, 10:50 ok, 11:00 due. Correct under §4.5 |
| Asleep across Fri 16:30; launchd fires the coalesced run on Saturday and it records a weekend skip | The skip is dropped; Fri 16:30 is missed once Tue 09:30 passes. Correct |
| Late run after waking (app-factory at 08:42) | ok. Correct |
| SGT against Mac zones (`TZ` Singapore, UTC, New York) | Same results with an aware clock. A naive clock differs (S-8) |
| Holiday skip with a pause reason | Hides the miss (S-1) |
| scout-send's 10-minute slots, a quiet run still going | False missed (S-2) |
| A run at 09:59:59, a second before its slot | Counts for 09:50. Acceptable, since launchd doesn't fire early |
| Copied `BUSINESS_DAY_KINDS` against the runner's | Equal today, with no test guarding it (ST-2) |
| Holiday known to the runner but not to the classifier (YAML changed afterwards) | The skip is not dropped and the slot reads missed. Only matters if `sg-public-holidays.yaml` is edited after the fact |
| A fortnight of every `settings.yaml` job, no records | 0.009s |

Outside this diff: `schedule.to_local` (`schedule.py:76-85`) bakes in the Mac's offset at render time. On a Mac in a zone with daylight saving, every launchd slot moves an hour at the changeover until the plists are rendered again. The classifier would then report the shift honestly as missed slots. The cause is in the existing schedule code, not here.

## Security

The `security-review` pass was done inline on this branch's two files. The skill's default diff (`crew/mission-control` against `main`) covers ticket 01, which was reviewed separately, so I didn't use it.

- No findings. `slots.py` runs no SQL, starts no subprocess, opens no file path, makes no network call and handles no secrets. `json.loads` on `payload_json` (`slots.py:48`) is safe deserialisation of local, trusted data. The skip reasons carried in `SlotState.reason` were already redacted when written (`log.event` and `finish_run` call `config.redact`). Any text bound for Discord passes through 02's redaction inside `discord.post()`, so 08 must keep using that path.
- The test file's `subprocess.run([sys.executable, "-c", <fixed string>])` (:389) takes no outside input.
- The diff touches no auth, money or personal data.

## Blocked paths

None touched. The diff is limited to `jura_growth/slots.py` and `tests/test_mission_slots.py`, and no test wrote into the repo or under `jurasolutions/`: the write guard passed and the worktree was clean afterwards.

## UI

There are no UI files in this diff, so `crew:web-design-review` doesn't apply.
