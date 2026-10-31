# Code review 02: the morning order

- **Branch:** `crew/morning-brief-02-the-morning-order` at `61e6657`
- **Fixed point:** `bf8c73e` (5 commits, 32 files)
- **Spec:** `issues/02-the-morning-order.md`, with what it points to in `reviews/technical.md`, `reviews/functional.md` §2 and `reviews/test-strategy.md`, and the PRD

## Verdict: changes-requested

There is one blocking finding: the ticket's own acceptance line about stale times isn't met. It is a four-line fix plus a stronger guard. The behaviour under review is sound, and the three things you asked me to look at hard hold up (see "The three questions").

File references are at `61e6657` unless they name another branch.

## The three questions

**Can `outreach raise-due` send or raise outside the rules? It can't send, and it can't raise. A hand run can post a card that is already pending (S1).**

| Case | Result | Evidence |
|---|---|---|
| Sends | Never. The command reaches only `approvals.request` and the card sweep | `outreach/cli.py:103-110`; `test_outreach_raise_due.py` asserts no Resend call in every case |
| Shadow | Raises nothing, posts nothing, slot reads `ok` | `approval.py:279-281,296,329`; test |
| Live problem | Raises nothing, posts nothing | Test; `raising_problem` |
| Paused flag or PAUSE file, as the job | Stopped before the command runs. Slot reads `skipped` | `runner.py:78,106`; test for the flag; my probe for the PAUSE file |
| Paused, by hand | Raises no new request (probe), but posts a card already pending (probe, S1) | `approval.py:284,329` |
| Over the room | Refused inside `BEGIN IMMEDIATE`, and the quota is checked again at send | `approval.py:300-310`; `send.py:339-341` |
| Headless jobs | Only `outreach-requests` may use it. All five Claude jobs are refused | `headless.py:83-84,143-150`; test |

**Does the `installed_at` rule hide real misses? Only slots from before an install, as T-B5 accepted. It can't hide one after, or hide one silently.**

- **What stays visible.** In my probe, a daily job with an install at 12:00 on 1 Nov read `not installed` for 30 and 31 Oct, and `missed` for the 1 Nov slot at 23:30. `test_a_slot_after_the_install_with_no_trace_is_a_true_miss` holds the same rule.
- **What can move the time.** Only `schedule.install` writes the plist (`schedule.py:162`), and its one caller is the CLI (`cli.py:369`). `render` writes elsewhere, which my probe confirms. `schedule` is in `NEVER`, so no headless run can reach it.
- **No safety decision reads it.** `check_auto_pause` reads `runs`, and pause and send decisions don't read slots. Slot status is for display only.
- **Remaining costs.** N1 and N2 below.

**Is changing `test_mission_health.py`'s four golden times right? Yes. The criterion that forbids it is what's wrong (S2).**

- The old test file fails at this commit on the first moved line, `app-factory`. The test compares `kept == STATUS_GOLDEN`, and only jobs outside the golden are filtered out (`:226-232`). The four moved jobs are inside it, so moving them has to change the file.
- The diff is four time values. Columns, order and the set of jobs are unchanged, so the guard on `status`'s format is intact.

## Standards

**Blocking:** none.

**Should fix:** none. The hard violations reported on this axis, `CONTEXT.md:84` and `:34-35`, are ticket 01's file (see S3).

**Nit** (all judgement calls; none breaks a documented rule):

- `tests/test_mission_health.py:164`: the comment says the golden is the output at `8e3d9b4`. It no longer is. Say the times follow the morning brief PRD.
- `jura_growth/agents/scout/__init__.py:67-69`: possible Duplicated Code. It repeats the `icp.path().exists()` check from `icp.py:32`, and the literals restate `icp.path()` and `draft_path()`. Apps keeps its wording beside its rule (`apps/__init__.py:78`), so this could sit beside `missing_reason`.
- `jura_growth/schedule.py:192`: Duplicated Code. `launch_agents_dir() / f"{label(job)}.plist"` also appears at `health.py:107` and, nearly, at `schedule.py:178`. A small `plist_path(job)` would serve all three.
- `jura_growth/slots.py:200`: Speculative Generality. `since` defaults to `None`, but the only caller always passes it.
- `jura_growth/mission.py:76` and `slots.py:148,175`: "no install time" is spelled two ways, `lambda job: None` and `None`.
- `jura_growth/agents/outreach/cli.py:103`: `raise_due_cmd` has a suffix it doesn't need. `sync_cmd` needs one because the `sync` module is imported; nothing collides here.
- `jura_growth/agents/outreach/__init__.py:4`: 110 characters in a docstring that wraps near 80.
- `tests/test_slots_installed_at.py:20-26` repeats `MORNING` from `test_morning_schedule.py`. `test_morning_schedule.py:60-61` adds nothing to `:46-48`.

**Reuse:** `run_update.count` is sound reuse. Nothing new duplicates a dependency or the standard library. The duplications are the path and ICP nits above.

**Checked, no finding:** the `health` hook is documented (`README.md:200`). The core gains no import of an agent, and no cap changes. `tests/conftest.py:152` isolates the LaunchAgents folder, so no test reads real plists.

## Spec

### Blocking

**B1. The search for old times still finds the one-pager's 08:00.**

Ticket: "A search for each moved job's old time finds no stale reference." Functional SC7: "A search of docs, prompts and config for each job's old time finds no reference to these jobs."

| Line | Text |
|---|---|
| `.env.example:20` | "The 08:00 one-pager and its health strip." |
| `.scratch/mission-control/setup/discord.md:22` | "arrives in `#mission-control` at 08:00 SGT every day" |
| `.scratch/mission-control/setup/discord.md:46` | "The one-pager at 08:00 SGT" |
| `.scratch/mission-control/setup/discord.md:114` | "so the 08:00 job is loaded" |

- **Reproduced with:** `git grep -nE "08:00"`, excluding tests. Ticket 01's branch touches neither file, so nothing else will fix them. Technical (d)'s list left them out, but the ticket's search has no such limit, and this diff already fixed the sibling `morning-brief.md`.
- **Why the test missed it:** `OLD_TIMES` (`tests/test_morning_schedule.py:119`) has no 08:00 row, and the guide test at `:146` reads only `morning-brief.md`.
- **Fix:** change the four lines. Add `("08:00", [".env.example", ".scratch/mission-control/setup/discord.md"])` to `OLD_TIMES`.
- **Also change at `test_morning_schedule.py:132`:** a mistyped or renamed folder currently passes, because `rglob` on a missing path finds nothing. Assert that each path exists.
- **For the release:** `discord.md` is copied to `outputs/growth/setup/discord.md`, so the live guide changes only when the release copies it.

These lines are correct to leave alone: `README.md:108` and `digest.py:6` (the AI OS brief), publish's 09:00, and dated `.scratch` records. `CONTEXT.md:84` is ticket 01's, and its branch changes it.

### Should fix

**S1. A hand run while paused posts a pending card and says it did nothing.** `jura_growth/agents/outreach/cli.py:107,109`; `docs/scout.md:27` says "In shadow mode or paused, it does nothing."

- **Reproduced:** live mode, one pending unposted request, outreach paused. `jura-growth outreach raise-due` printed "no requests raised" and posted 1 card. `post_cards` checks only the mode (`approval.py:329`).
- **Impact is small.** The scheduled job can't reach this, because the runner stops it first, so SC2 holds. Nothing can send, because a claim is refused while paused (`approvals.py:486-492`). `send-due` and the heartbeat already sweep during an outreach pause.
- **Fix:** call `post_cards` only when `raising_problem` is empty, and add a test that runs the command directly while paused. Every pause test in the new file goes through the runner, so the raiser's own pause check isn't exercised on this path. If you would rather keep the sweep, make `docs/scout.md:27` say "the job" and word the output so it doesn't deny the post.

**S2. Test strategy criterion 6 now can't pass.** `reviews/test-strategy.md:91` requires an empty diff for `tests/test_mission_health.py`, and `:69` lists it under "Stay as they are". The change is right (see above), but the quality gate would fail on the letter of the criterion. The conductor should amend both lines to allow time values in `STATUS_GOLDEN`.

**S3. The glossary doesn't have the new "not installed" rule.** `CONTEXT.md:34-35` gives two conditions, and `slots.py:249` adds a third. The ticket keeps `CONTEXT.md` for ticket 01, whose list doesn't include this, and its branch still has the two-condition text. This should go to ticket 01 or the conductor, in one clause.

**S4. Drift needs the install rule when the branches meet.** `crew/approvals-first-social-depth` has `schedule_drift` (`health.py:228` there) with no reference to `installed_at`, and this branch can't change it yet. Technical's conflicts section says "Whichever branch lands second makes this change". With functional S2's order, that's this one, at the rebase. Without it, `app-factory` and `social`'s 30-minute move meets `DRIFT_MINIMUM` and can raise a false "0.5 hours off". The conductor should carry this into the rebase.

### Nit

- `tests/test_outreach_cards.py:158`: the comment says 06:40 is outside the window, but the assertion doesn't prove it. With `outside_window` mutated to always allow sending, the test still passes, because the request isn't approved. The card and decide-by assertions are the real test of SC3. Drop the comment, or approve the request first.
- `tests/test_morning_schedule.py:24` pins the digest at 17:30, and the comment says the other branch updates it "when it lands". Under the planned merge order, the rebase is what breaks it. Exit criterion 10's rerun will catch that.
- Ticket 01 still has "the one-pager's grid PNGs" at `config/settings.yaml:53`, and `discord.md:46,114` still describe the 14-day grid in the post. Both are its wording to fix, not this ticket's.

### Not asked for

Nothing out of scope. `CONTEXT.md`, `brief.py`, `picture.py` and the digest are untouched. The README's new `publish` row is unlisted but correct, and the README test needs it.

### Criteria met

| Row | Status |
|---|---|
| SC1, SC5 | Exact table of the six jobs and a golden table of the rest |
| SC2 | All cases have tests. Room 0 is reached by using the only slot |
| SC3 | No code change. The card and decide-by are asserted (see the nit) |
| SC4 | Computed for each day of a week at `timeout_minutes` |
| SC6 | Saturday and business day, present and absent. The line is 109 characters and holds no absolute path |
| SC7 | Partly, see B1 |
| T-B5 | First commit. The probe table is a test, and the rule is in the `slots.py` docstring |
| A11 | Declared in `tests/test_no_generic_request_command.py`; PRD line 65 records it |

`tests/test_morning_order.py` is absent. The ticket allows this because ticket 01 hasn't merged, so it stays with the conductor.

## Security

**No findings at confidence 8 or above.**

- **Personal data:** the run summary is a count, the request reason holds a lead id, the card address is masked (`approval.py:124`), and the health line is fixed text with relative paths.
- **Plist time:** `installed_at` stats a filename built from config and reads no content. Faking a time needs write access to `~/Library/LaunchAgents`, and anyone with that can already remove the job.
- **Injection:** the command takes no arguments, and the `raise_due` query uses bound parameters.

**Nit, no send possible:** at 08:30, no suppression sync has run since 16:45 the day before. An address unsubscribed in between can get a card (`approval.py:89-95`). The send path syncs and runs `blockers` before the claim (`send.py:364,384-390`), so the email never goes. The cost is one card to skip.

## Blocked paths

None. Nothing under `inputs/`, `design-system/`, `.env` or live `data/growth/` changed. `.env.example` isn't blocked. No CI workflow changed.

## UI

No UI files in the diff, so `crew:web-design-review` doesn't apply.

## Installed-at nits

- **N1. `install` rewrites every plist, even unchanged ones** (`schedule.py:162`). The PRD's post-merge `schedule install` therefore also clears real misses on jobs that didn't move, such as `backup` or `heartbeat`. T-B5 accepted this, and the `slots.py` docstring says so. If you want it narrower, write only when the bytes differ: the mtime then moves only for jobs whose schedule moved.
- **N2. A future plist time hides upcoming slots.** In my probe, an mtime two days ahead read `not installed` for today's upcoming slot, because the `since` check comes before the `upcoming` check (`slots.py:249-251`). It needs a wrong system clock at install. `min(since, now)` would close it.

## For the conductor

- **Merge conflicts with ticket 01:** a trial merge conflicts in `README.md` and `.scratch/mission-control/setup/morning-brief.md`. Take 01's wording at `README.md:44`, and this ticket's times.
- **Merge conflicts with approvals-first:** `health.py` and `mission.py`, as technical predicted.
- **Sign-off:** the PRD records "not signed", proceeding under Ting Yu's standing instruction, with merge as his acceptance. I treated this as recorded, not as a finding on this ticket.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest -rs -q -p no:cacheprovider -o addopts=""` at `61e6657` | 13 failed, 4048 passed, no skips listed |
| The three named test files at `bf8c73e` and at `61e6657`, failures compared by name | The same 13 at both: `test_mission_read` 7, `test_one_pager_post` 5, `test_one_pager` 1. None is new |
| `bf8c73e`'s `test_mission_health.py` against this commit | Only `test_status_is_unchanged_apart_from_the_gap_lines` fails, first on `app-factory`'s time; 20 pass |
| `pyright` on the 5 touched modules | 0 errors |
| Mutations on a throwaway copy: rule off, `here()` wiring, `read` wiring, no `post_cards`, not quiet, 08:45 job, ICP line always on | Each one fails its test file |
| Mutation: `outside_window` always allows | The SC3 test still passes (nit above) |
| Probes on temp data with the Discord double | Hand run while paused: 0 new requests, and 1 card when one was pending. PAUSE file: slot reads `skipped`. True miss after install: `missed` |

Everything ran in temp folders or a throwaway copy of the commit. Nothing posted, `jura-growth run` and `schedule install` were never run, and live data wasn't touched.

**One departure from the brief:** the brief says not to run schedule render. To check that render doesn't move a plist's install time, one of my probes called `schedule.render(["social"])` from Python, under the test isolation. It wrote one plist inside the throwaway copy or its temp folder and loaded nothing. Afterwards, no plist in live `data/growth/` or `~/Library/LaunchAgents` was newer than the start of this review.
