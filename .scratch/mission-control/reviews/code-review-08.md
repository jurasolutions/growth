# Code review 08: the read model and the one-pager text (MC-08)

- **Branch:** `crew/mission-control-08-read-model-and-one-pager-text` at `d5e6037` (commits `506b4c5`, `a0e4caf`, `1d150ad`, `6652405`, `d5e6037`), reviewed against the fixed point `8e3d9b4` (`git diff 8e3d9b4...crew/mission-control-08-read-model-and-one-pager-text`)
- **Changed files (17):** `README.md`, `docs/adr/0002-…`, `jura_growth/agents/__init__.py`, `agents/outreach/__init__.py`, `cli.py`, `config.py`, `digest.py`, `discord.py`, `health.py` (new), `mission.py` (new), `one_pager.py` (new), `tests/conftest.py`, `tests/mission_world.py` (new), `tests/test_isolation.py`, `tests/test_mission_health.py` (new), `tests/test_mission_read.py` (new) and `tests/test_one_pager.py` (new). I read every one in full.
- **Spec:** `issues/08-read-model-and-one-pager-text.md` (with its S-5 comment); PRD SC1, SC11, SC13, §4.2, §4.3, §5.3 and §5.4; ADR 0002; `reviews/round-2-decisions.md` §1 and §2; test strategy v3 (the MC-08 rows, D4, D5, D6, X15, E4, E6)
- **Date:** 2026-10-26

## Verdict: changes-requested

There is one blocking finding, B-1. The read model picks "the last one-pager" as the newest scheduled time strictly before now. The 08:00 job never starts at exactly 08:00:00, so on the real job that window is a few seconds long. In practice this empties three things the one-pager owes Ting Yu: the Terminal-decision note (AC-M6.4), the lapsed-unused listing (AC-M8.5) and the outbox counts. Every test runs at exactly 08:00:00, so the suite doesn't see it.

Everything else holds. The read model never writes and never repairs `growth.db`: I tried to break that and couldn't. The changed write guard still refuses every way into the repo or `jurasolutions/` that I tried. No blocked path is touched. The security pass found two hardening items and nothing that leaks.

## Evidence

All commands ran in the developer worktree `.claude/worktrees/agent-abb07bdc53c310ef8`, with `JURA_ROOT` set and the data and outputs variables pointing at `mktemp -d` folders. The live `growth.db` was never opened.

| Command | Result |
|---|---|
| `uv run pytest -p no:cacheprovider -rs` | 1575 passed in 36.14s, 0 skipped |
| The four new or changed test files | 93 passed in 3.32s |
| `git status --short` before and after the suite | empty both times |
| E6 greps (`db.connect`, `db.session`, `paths.writable`, `immutable=1`, `journal_mode`, `flock`, `locks.`) in `mission.py`; `jura_growth.agents.` in `mission.py`, `health.py` and `one_pager.py`; `taskwise`/`zenexflow` in the diff | no hits |
| `git diff --name-only` against the blocked paths (`inputs/`, `design-system/`, `.env`, `data/growth/`) | no hits |
| `pyright` on the seven changed source files (run by the Standards reviewer) | 0 errors, and 0 at `8e3d9b4` |
| `git merge-tree --write-tree` against `crew/mission-control-03-run-updates` (`17f04ff`) and `crew/mission-control-04b-terminal-decisions-and-cards` (`29023eb`) | both merge cleanly. They overlap only on `README.md` and `agents/__init__.py` (03), and on `cli.py` and `discord.py` (04b) |
| The suite on the merged 08 + 03 + 04b tree (`git archive` into the scratchpad) | 1779 passed in 47.07s |
| Write-guard probe `scratchpad/probe/guard_probe.py` | see "The write guard" below |
| Read-model probe `scratchpad/probe/read_probe.py` | see Security; D4 gives `unfinished write` / `SQLITE_READONLY_ROLLBACK` |
| Window probe `scratchpad/probe/window_probe.py` | see B-1 |

There is no build. The operating card says nothing is built or deployed.

### The write guard (`tests/conftest.py:54-57`)

I passed each of these through `WriteGuard._protected()`. Only the three marked "connect" were real opens, and they targeted a folder under `jurasolutions/data/` that doesn't exist, so a miss could not have created a file.

| Input | Judged |
|---|---|
| A plain path, `file:` with no mode, `mode=rw`, `mode=rwc` and `mode=ro` into `data/growth/growth.db` | protected |
| `Path.as_uri()`, `file://localhost/…`, `file:////…`, a fully percent-encoded path, `..` climbing from a temp folder, a fragment, a bytes URI | protected |
| A temp symlink to `data/growth/` (both the plain path and a `file:` URI through it) | protected (resolved by `realpath`) |
| A `file:` URI into the repo | protected |
| A `file:` URI into a temp folder; `file::memory:` | allowed, as intended |
| connect `file:…?mode=rw`, `file:…` and `file:…?mode=rwc` | `PermissionError` |

The change does what the developer said: a `mode=ro` open of a temp database is no longer refused, and nothing that names a protected file got through. The two gaps I found are listed under Standards as ST-8 and ST-9.

## Standards

### Blocking

None.

### Should fix

- **ST-1. Duplicated helpers (reuse).**
  - `mission.py:379-381` `_at` re-implements `timeutil.parse(value).astimezone(SGT)` (`timeutil.py:79-81`). `slots.py` already uses that helper.
  - `mission.py:320-326` `one_pager_around` repeats the slot expansion in `slots.py:190-200` `_slot_times` (`sgt_slots` and `launchd_weekday`).
  - `mission.py:497` `_midnight` and `health.py:132` build SGT midnight the same way.
  - `mission.py:212-234` `_outbox` repeats the JSONL read-and-parse loop of `_lines` in the same file (`:450-468`).
  - The `"discord-outbox"` folder name is now hard-coded both in `mission.py:163` and in `discord.py:300`. Give `paths` or `discord` one `outbox_dir()` and use it in both places.
- **ST-2. The glossary's avoided term.**
  - Lists of `SlotStatus` are named `states` (`mission.py:261`, `health.py:181`, `one_pager.py:100`). CONTEXT.md, under **Slot status**, says "_Avoid_: result, state". Code review 07 ST-1 renamed `SlotState` for exactly this reason.
  - `Request.state` (`mission.py:113-129`) introduces a second approval vocabulary next to the stored status, and CONTEXT.md doesn't define it.
  - The same block rebinds `APPROVED`, `SKIPPED` and `SUPERSEDED`, which `approvals.py` already uses for stored statuses.

  Rename the slot lists. Then either add the clock-judged request reading to CONTEXT.md (for example **Request reading**: waiting, lapsed, approved, lapsed unused, used) or rename it so the two vocabularies can't be confused.
- **ST-3. The `db_state` switch is written twice.** It appears in `health.py:194-205` (`_database`) and again in `one_pager.py:55-62` (`_unavailable`). One map from state to wording, kept beside the states in `mission.py`, would keep the two in step.

### Nit

- **ST-4.** `health.py:139` imports `mission` lazily, and `_database(snapshot, mission)` (`:194`) receives the module as a parameter, to get around an import cycle. `health.py` also does two jobs: setup gaps and install state for `status`, and the one-pager's strip text. Moving `strip()` into `one_pager.py`, or the state constants into a small module of their own, would remove the cycle.
- **ST-5.** Fields that nothing reads: `Source.prd` and `Source.outputs` (`mission.py:45-46`), `Request.close_reason` (`:131`), and `Snapshot.days` (likely for 09's grid). The states `LAPSED`, `USED` and `SUPERSEDED` are assigned but never compared. Keep what 09 needs and say so in a comment.
- **ST-6.** `digest.py:78` (`cost or 0.0`) and `mission.py:297` (`or 0.0`) are now redundant, because `spend()` already returns 0.0.
- **ST-7.** `health.py:73` says "out of date", while CONTEXT.md's **Install state** says "installed but out of date". The strip text (`health.py:167`) matches the glossary; only the constant differs.
- **ST-8. The write guard misses a `PathLike` whose text starts with `file:`.** `conftest.py:54` handles only `str`. `sqlite3.connect(Path("file:/…/data/growth/growth.db"), uri=True)` is opened as a URI by SQLite. The guard instead judges it as a relative path, and once the working directory is a temp folder it allows it (probe: `None` after `chdir`). This is unlikely in practice. `value = os.fspath(value)` before the `startswith` check would close it.
- **ST-9. This predates the diff: the guard never sees `ATTACH` or `VACUUM INTO`.** CPython raises no audit event for either. The probe's `ATTACH 'file:…?mode=rwc'` and `VACUUM INTO` reached SQLite unrefused (they failed only because the target folder didn't exist). `privacy._read_only()` uses `ATTACH` on `paths.db_path()`, which is a temp folder in tests, so nothing is exposed today. The guard's docstring should say that it doesn't cover these two.

## Spec

### Blocking

- **B-1. "Since the last one-pager" collapses to seconds on the real 08:00 run.** At `mission.py:327`, `before = [at for at in times if at < now]` makes today's 08:00 slot "the last one-pager" as soon as `now` is past it by any amount. The `one-pager` job starts after launchd, Python start-up and `expire_due()` (PRD §4.2), so it always runs a few seconds late.

  Reproduced with `scratchpad/probe/window_probe.py`: a Terminal approval at Mon 21:14, an approved request expired at Mon 16:31, and an undelivered post at Mon 12:00.

  | `now` | last | Terminal note | A-0160 listed | undelivered |
  |---|---|---|---|---|
  | `08:00:00` | Mon 08:00 | yes | yes | 1 |
  | `08:00:05` | Tue 08:00 | **no** | **no** | **0** |

  This breaks three things in the daily one-pager:
  - PRD §5.4.3's "a line for any decision made from Terminal since the last one-pager", which is AC-M6.4's "the next one-pager notes the Terminal decision" (`one_pager.py:86`).
  - AC-M8.5's "listed in the next one-pager" (`mission.py:341` `closed_at > ?`).
  - §5.4.2's undelivered and outbox counts (`mission.py:163`, `:268`).

  Every test pins the clock to exactly 08:00:00 (`test_one_pager.py:23`, `test_mission_read.py:22`), so nothing catches this.

  **Fix:** make the window the scheduled one-pager before the current scheduled one. One way: when `now` falls within a grace window after a scheduled time (for example the job's own timeout, or a few minutes), that slot counts as "this one-pager" and the window starts at the slot before it. Add tests at `08:00:05` and at `08:04` for AC-M6.4, AC-M8.5 and the outbox count, and keep the on-request case (`11:05` gives today 08:00).

### Should fix

- **S-1. `CONTROL_DISCORD_USER_ID` is not a setup gap.** Core `approvals.py:551` reads it, and when it is unset every Dispatch decision is refused ("CONTROL_DISCORD_USER_ID isn't set, so a Dispatch decision can't be checked"). Yet `health.setup_gaps()` checks only Discord (`health.py:102`). CONTEXT.md defines a **Setup gap** as "a setting or secret the engine needs that isn't configured yet". The PRD doesn't list it by name, and that list is open. Recommendation: add it to the core checks next to Discord, as `Gap("CONTROL_DISCORD_USER_ID", ok=config.is_set(...))`. It is core, not a plug-in setting, so it belongs in `health.py`. This is one line plus one test row, and the `status` golden is unaffected because only gap lines change.
- **S-2. The Yesterday section repeats digest lines that say "today".** At `mission.py:297` and `one_pager.py:121`, under **Yesterday** it prints the plug-ins' own wording:
  - "App factory: no run today" and "no PRD today; the run failed" (`agents/apps/__init__.py:81-90`)
  - "Social: no draft today (…)" (`agents/social/__init__.py:74`)
  - "Outreach (…): nothing sent today" (`agents/outreach/__init__.py:83`)

  It also repeats the broken-plug-in lines that the health strip already shows (`digest.py:65`, `health.py:174`). The code follows X15 ("Yesterday equals `digest.build()` for yesterday") to the letter, but the result misleads. Recommendation: keep X15's word-for-word equality and make the plug-ins' digest lines name no day ("no run", "no PRD; the run failed", "no draft", "nothing sent"). Each digest is already headed with its date (`digest.render`, "Jura growth digest, YYYY-MM-DD"), so nothing is lost there. Do it as a small follow-up on this branch, or as a ticket before 09, rather than rewriting text in `one_pager.py`, which would break X15. The broken-plug-in lines can be left out of Yesterday by building the section from the plug-in lines only, or accepted as a duplicate. Ting Yu to choose (see the report's question).
- **S-3. The shared-gaps test compares the wrong pair.** AC-M11.2 and the test strategy say "`status` and the health strip list the same gaps from one fixture". `test_mission_health.py:154` compares `status` with `health.setup_gaps()`, and `test_mission_read.py:308` compares the snapshot with `setup_gaps()` separately. Neither compares `status`'s gap lines with the strip's lines from one plug-in fixture. Add one test that does: the same `EXTRA_TOKEN` plug-in, `status` gap lines equal to the gap items in `health.strip(mission.read(...))`.
- **S-4. Today collapses by slot count, not by job.** PRD §5.4.4 says "scout-send and publish as counts per status". `one_pager.py:21,105` collapses any job with more than three slots in a day. The output is right for today's schedules. A future frequent job would be collapsed too, and a publish day with three or fewer slots would be listed instead of counted. Either key the rule on the job's schedule shape (`business_days_every` and publish's repeating shape, the same test `slots.day_cell` would need), or record in §5.4 that the rule is "more than three slots".

### Nit

- **S-5.** `health.py:163-165` lists every kind that lapsed unused. §5.4.2 says "approved emails that lapsed unsent", but AC-M8.5 and the ticket ("an approved request that lapsed unused") cover any kind, so this is fine. Just note it in §5.4.
- **S-6.** The broken-plug-in item (`health.py:174`) isn't in §5.4's list. It is useful; add it to §5.4 or to CONTEXT.md's **Health strip**.
- **S-7.** Outreach's `REQUIRED_SETTINGS` leaves out `OUTREACH_IMAP_*`, which technical review N6 named. `replies.py:3` makes the reply sync opt-in ("On only when … are set"), so leaving them out is defensible, and the developer said so. Add a one-line comment beside `REQUIRED_SETTINGS` so the next reader doesn't "fix" it.
- **S-8.** An approved request past its use-by, and not yet expired by a write, is listed as lapsed unused on every read until `expire_due()` writes it, and then once more (the row is selected by `closed_at > last`). This is harmless while the heartbeat runs `expire_due()`.

## Security

### Blocking

None. These are the checks I made against the diff:

- **The read model can't write or repair.** `open_read_only` uses `mode=ro` together with `query_only` (`mission.py:138-143`). The probe query at `:186` runs before any plug-in hook sees the connection.

  | Probe | Result |
  |---|---|
  | A `health(conn)` hook that runs `PRAGMA query_only = OFF` and then writes | `OperationalError` (`mode=ro` still refuses), 0 rows written |
  | `PRAGMA journal_mode = WAL` from a hook | refused; `journal_mode` still `delete` |
  | D4 hot journal | `unfinished write` / `SQLITE_READONLY_ROLLBACK`, bytes of the database and journal unchanged (the existing test asserts this too) |

  The other paths are read-only too:
  - With a hot journal or a missing file, `privacy.load_for_masking(None)` falls back to `privacy._read_only()`, which attaches with `mode=ro`.
  - The read model runs `digest.build()` and the plug-ins' `digest()` hooks on the read-only connection. I read all five hooks and `community.audit()`: they only read.
  - No path helper creates a folder (`paths.data_dir` and the rest, `schedule.launch_agents_dir`).
- **Setup gaps carry no value.** `config.is_set()` never resolves a `keychain:` reference (the test asserts the Keychain is never asked). `Gap.name` must match `[A-Z][A-Z0-9_]*`, and the lines are `NAME: not set` or `Discord: n of m webhooks`.
- **SQL.** Every value is bound. The f-strings in `_records` (`mission.py:406-417`) splice only constant column lists and `?` placeholders.
- **Redaction.** Every string the snapshot returns goes through `privacy.for_discord`, and `one_pager.messages()` masks the whole text once more before `discord.split()`. The sweep test asserts its marker arrived first (E4).
- **Untrusted text.** Failure text is cut to 300 characters and quoted, and the PAUSE-file reason is cut to 200 (§4.3).

### Should fix

- **SEC-1. A plug-in can put a value into a gap line.** `Gap` checks only the name. `have` and `of` aren't type-checked, and nothing stops a plug-in from returning the Discord gap. Probe: `setup_gaps=lambda: [health.Gap("Discord", have="re_uat_9Xq7Lm2Pz", of=1)]` produced the line `Discord: re_uat_9Xq7Lm2Pz of 1 webhooks`. In Discord, `for_discord` would mask a known secret, but `jura-growth status` prints the line as it is. §4.3 says "Setup gaps are names and booleans only". Make `__post_init__` require `isinstance(ok, bool)` and `int` for `have` and `of`, and have `_plugin_checks` drop any plug-in gap named `Discord`.
- **SEC-2. A malformed `REQUIRED_SETTINGS` crashes both `status` and the one-pager.** `health.py:65` builds `Gap(...)` outside the `try`, so a lower-case name raises `ValueError` out of `setup_gaps()`, which `mission.read()` calls outside its own handling (`mission.py:161`). Probe: `REQUIRED_SETTINGS=("lower_case",)` raised `ValueError` from `mission.read()`. Elsewhere one plug-in never breaks the one-pager. Wrap the shorthand in the same `try` and fall back to `<NAME>_SETUP_CHECK`.

### Nit

- **SEC-3.** A `health(conn)` hook can `ATTACH … ?mode=rwc` and create a file (probe: created). `query_only` still blocks writes into the attached file. Plug-ins are first-party, so this is a note for the hook's docstring, not a gate.
- **SEC-4.** A `health()` hook that returns a `str` is iterated character by character (`mission.py:309`; probe: `('a', 'b', 'c')`). Accept a `str` as one line, or ignore anything that isn't a list.
- **SEC-5.** `Request.decided_origin` (`mission.py:369`) is the one string in the snapshot that isn't passed through `_clean`, against the module docstring's "Every string in a snapshot has been through `privacy.for_discord()`". It is a controlled value (`terminal` or `ssh`), so this is cosmetic.

## UI

There are no UI files in the diff (the PNG grid is 09's), so `web-design-review` doesn't apply.
