# Code review: ticket 03, the schedule drift check

Branch `crew/approvals-first-social-depth-03-schedule-drift` at 19d6465, diffed against its fixed point `crew/approvals-first-social-depth` (9374c14). Line numbers are on the branch.

**Verdict: approve.** There are no blocking findings. The line fires on the live 9-hour pattern and stops after a restart. Should fix 1 is worth doing before this merges: it is one condition, and it closes the only way I found for the line to stay silent day after day. It does not affect this Mac as it is set up today.

## What I replayed

I read the live `growth.db` through `mode=ro` with `query_only` on. Every write went to temp folders. Nothing touched launchd.

**The live pattern fires.** The live rows match the brief: heartbeat 03:00, digest 08:30, backup 14:30, one-pager 23:00, social 22:00.

| Read | Result |
|---|---|
| Sat 31 Oct 19:30, the pure check | Line, -9 hours |
| Sat 31 Oct 23:00, `mission.read` and `one_pager.text` | Under Needs you: "about 9 hours off: `heartbeat` is due at 12:00 SGT and ran at 03:00 SGT" |
| Every 08:00 and 23:00 read over the live history | First line at 28 Oct 23:00, then at every read since. `runs` only starts on 24 Oct, so this is the first read with enough rows |

`app-factory`'s newest live row is off-pattern (01:01 on 31 Oct, after 21:30 runs). It drops out of the group and doesn't hide the drift, so the outlier fix from B7 is working on real data.

**A restart stops it.**

| Scenario | Result |
|---|---|
| Restart Sat 20:00, then `mission.read` and `one_pager.text` on Sun 08:00 | No hours-off line. Rows since the restart: backup 23:30, app-factory 06:30, social 07:00, one-pager 08:00 |
| Restart at each of 24 hourly times, Mac awake, reads every 30 minutes for 72 hours | The next 08:00 read is quiet every time. The line never comes back after the first on-time run |

My first version of the sweep showed false lines. It treated a drifted firing as using up that day's on-time firing, which launchd doesn't do. I corrected the script, and the results above are from the corrected one.

This models a restart that fixes the clock. The PRD says the cause is not proved, so only UAT L2 on the real Mac can prove the restart works.

**Judging the reported limit: a wake within 30 minutes of a due time.** The limit is real, and it is larger than reported.

- **As reported, it costs a few hours.** With one wake or hand run near a slot, the line is gone only until the next job in the group runs. With a heartbeat wake at 11:45, the line is quiet at 11:50 and back on the 23:00 one-pager. A `jura-growth run one-pager` at 08:05 is quiet at 08:05 and the line is back at 08:31.
- **As a routine, it costs every morning.** On a Mac asleep overnight with a real 9-hour drift, the one-pager fires at the wake and reads the job on time. A wake at 08:10 gave a quiet one-pager on all five days I read. `health.strip` reaches you only through the one-pager, so that is the only place the line appears. A 15:00 read in the same runs does show the line.
- **This Mac has a repeating 06:15 wake** (`pmset -g sched`). If it ever slept through the night, `app-factory` would fire at 06:15, read on time (15 minutes off), and silence the 06:15 one-pager every day. I reproduced this by assuming four jobs fire at that wake and `app-factory`'s row lands first.
- **It doesn't apply today.** The machine is a Mac mini (`Mac16,10`) on AC power with `sleep 0`. `pmset -g log` has no sleep entries back to where it starts on 24 Oct. None of the 30 live daily rows reads as on time.

So I accept it for today's Mac, and it does not block. It still deserves the small fix below, because this check exists to catch exactly the kind of quiet schedule fault the PRD found by hand.

## Standards

No hard violations. ADR 0002 holds: `_drift` only reads on the existing read-only connection. No blocked path is touched. Pyright reports 0 errors on `health.py` and `mission.py`, on both the branch and the fixed point.

**Should fix**

- `jura_growth/health.py:207`: new code duplicates `_plural` (`health.py:135`). `_plural` takes an int and would print "9.0", so widen it to a float with `{n:g}` and use it for both. Rule: reuse, reviewer step 5.

**Nit**

- `jura_growth/mission.py:298-301`: the `try` also wraps the pure `health.schedule_drift`, so a `ValueError` from a bug in that check would read as "no drift". Its docstring only excuses a malformed `started_at`, which only `_recent_starts` parses. Narrow the `try`.
- `jura_growth/health.py:231`: the docstring says a job counts when it has two runs, but `health.py:248-249` counts one recent run towards `on_time`.
- `jura_growth/health.py:224,247,271`: `gap`, `gaps` and `_gap` mean a time offset, in the module where `Gap` means a Setup gap (`CONTEXT.md:103`). `_offset` would avoid the clash. Rule: `docs/agents/domain.md`, use glossary terms.
- `jura_growth/health.py:277` and `:288`: `_apart` returns a timedelta and `_slots_apart` returns a bool. The names read as a pair but aren't.

**Reuse checked, no finding**

- `_daily_slot` overlaps `schedule._hm` (`schedule.py:59`), but `_hm` is private, accepts "25:00" and raises `AttributeError` on 420. The tests require None for those values, so `strptime` is justified.
- `_gap` and `_after_midnight` duplicate nothing in the package.

## Spec

B7, N12, S13 and the docstring correction from `technical.md` are all implemented. Every row of the R8 table and every seam in "Ticket 03" has a named test.

**Should fix**

1. `jura_growth/health.py:248`: any run within 30 minutes of its slot clears the group, so a wake close to a slot reads as a fixed clock. SC1: "says so when scheduled jobs fire at the wrong SGT time by a steady amount". The code follows B7's wording ("any daily job's newest run is on time"), so this is a limit of the spec's rule, not a coding error. See the judgement above.
   - **Fix:** count a run as on time only within `DRIFT_TOLERANCE`, keeping `DRIFT_MINIMUM` as the bar for being off. Live launchd firings land within 5 seconds of the slot, so a real on-time run passes easily.
   - **Tried in a scratch copy:** the 132 tests in the four ticket files stay green. The 06:15 and 08:10 wakes now show the line. A wake at 08:03 stays quiet, and that remaining limit is small.
   - **The cost:** after a restart, a Mac that slept overnight and woke at, say, 08:10 shows the line one extra morning, until heartbeat at 12:00. One false alarm is better than silence that never ends.
2. `tests/test_schedule_drift.py`: no test pins this limit, whichever window is chosen. Add one table row for a wake near a slot during real drift, so the behaviour is a decision on record. Rule: `test-strategy.md` R8, "cries wolf or stays silent".
3. `jura_growth/mission.py:339`: an unparsable `started_at` on a `failed` row still breaks the one-pager. R8: "an unparsable `started_at`, must not break the one-pager."
   - **Reproduced:** one such row makes `mission.read` raise `ValueError: Invalid isoformat string: 'not a date'`. `test_a_malformed_started_at_costs_the_check_and_nothing_else` only corrupts an `ok` row.
   - **Why it doesn't block:** the line predates this diff, N12's narrower fix is done, and `started_at` is `NOT NULL`. I saw no path that writes a bad stamp in `log.start_run` or the runner, but I did not audit every writer.
   - **Fix:** guard `_failures` the same way, or have the conductor record that R8 is narrowed to the drift read.

**Nit**

- `jura_growth/health.py:250`: `abs(gaps[1]) >= DRIFT_MINIMUM` wasn't asked for and has no test. Reproduced: 30 then 27 minutes off returns None, though those runs differ by under 5 minutes (R8: "Second run differs by 5"). The rule is sensible, so pin it with a test.
- `jura_growth/health.py:285`: ties go to the first group in job order. Reproduced: two jobs at +1 hour and two at -9 hours report `app-factory`, 1 hour. The spec only says "largest group". Add a test, or prefer the larger offset.
- `tests/test_schedule_drift.py:20-27`: the table uses a hand-typed `JOBS`, while R8 says "with the job list from `config/settings.yaml`". It matches today, and the shipped list is used from line 276 on.
- After a restart, if the Mac slept overnight and woke past 08:30, the next one-pager still shows the line (reproduced with an 08:40 wake). Heartbeat's on-time 12:00 run clears it. The Mac doesn't sleep today, and I don't suggest code for this.

## Security

No findings at confidence 8 or above.

- **Injection:** the diff adds no SQL, subprocess, file open or eval. `_recent_starts` is unchanged and parameterised.
- **The Discord line:** `job` is a settings key, `due` and `ran` are re-rendered as HH:MM, and `hours` is numeric. No raw `runs` text reaches Discord, and both Discord payloads set `allowed_mentions: {"parse": []}`.
- **Read-only (ADR 0002):** `sqlite3.Error` still reaches `db_state`, and the diff adds no writes. `test_reading_drift_changes_no_file_and_never_opens_a_writable_connection` and `test_a_hot_journal_is_still_the_unfinished_write_state` both pass.

The security pass ran on the ticket's diff by reading the code. It did not use the skill's injected diff, which covered the whole feature branch against `main`.

## Tests and builds

| Command | Result |
|---|---|
| `uv run pytest tests/test_schedule_drift.py tests/test_mission_health.py tests/test_mission_read.py tests/test_one_pager.py` | 132 passed |
| `uv run pytest` on the branch | 41 failed, 3977 passed |
| `uv run pytest` on the fixed point | 41 failed, 3939 passed |
| Failing test IDs compared between the two | The same 41, none new and none fixed. All are in `test_publish_*` and `test_social*`, belonging to tickets 01 and 02 |

No build or linter is configured. No UI files changed, so `crew:web-design-review` does not apply.
