# Code review, final: crew/morning-brief

- **Branch:** `crew/morning-brief` at `33fb30d`
- **Fixed point:** `1206360`, its merge-base with `main` (29 commits, 69 files)
- **Spec:** `prd-jura-morning-brief-2026-10-31.md`, with `reviews/functional.md` §2 where they differ
- **Other branch:** `crew/approvals-first-social-depth` at `2c9e18d`, and its ticket 02 branch at `9b7b310`. Both are still moving.

## Verdict: changes-requested

There are two blocking findings, and both are small.

- **B1.** The outreach Fix line that this branch adds is cut on the picture for every real wording, which is the same break of MB3 that code review 01's B4 blocked.
- **B2.** Once a `social-post` card has been answered, the verdict tells Ting Yu to post by hand a draft the publish job will post. The planned merge order makes this live.

The rest holds. On the ordinary first mornings after an evening `schedule install`, the order works end to end and every row reads correctly. All of code review 01's B1 to B6 and code review 02's B1 and S1 are really fixed. The suite is green. There is no security finding and no blocked path.

File references are at `33fb30d`. "Reproduced" means I ran it on temp data. The probes are in the scratchpad and aren't on the branch.

## How the two tickets meet

| Moment | What the picture says | Finding |
|---|---|---|
| Sunday 1 Nov 09:00, after a Saturday 21:00 install | Social and App factory "Ran". Scout, Outreach and Community "Not today". No false "missed" | Clean |
| Monday 2 Nov 09:00, same install | All five rows "Ran", including Outreach from its quiet 08:30 trace. With nothing else wrong, "Nothing needs you right now." through the real plug-ins' figures | Clean |
| `outreach-requests` never fires on Monday | Row "Didn't run", Fix "Check `outreach-requests`: no trace of its run today." | Clean. Code review 01's B1 holds |
| `/growth one-pager` on install day, after the install | "Not installed / No run on record yet" for jobs that ran and are installed | S1 |
| After the merge, before `schedule install`, the old 08:00 plist fires | Fix names the out-of-date and uninstalled jobs. Rows read "Out of date" | Clean |
| A job silent two mornings | Two Fix lines for one job | S2 |
| A Fix list over 4 | The message says to ask `/growth status`, which doesn't list most of them | S3 |
| A card answered before 09:00, once a platform is in `browser` mode | "1 to post by hand" | B2 |
| Merged with approvals-first | False "0.5 hours off", and the restart instruction is cut | M1, M2 |

## Fixes confirmed

| Finding | Fixed? | Evidence |
|---|---|---|
| 01 B1, installed job with no trace | Yes | `picture.py:57-67`; `test_an_installed_job_that_has_never_left_a_trace_reads_didnt_run`; reproduced through a real read |
| 01 B2, recorded reply hidden | Yes | `picture.py:114,311`; `test_a_recorded_reply_shows_even_with_reply_detection_off` |
| 01 B3, guessed zero in the Decide heading | Yes | `picture.py:452`; `test_the_decide_heading_shows_a_dash_when_approvals_cant_be_read` |
| 01 B4, plug-in lines cut | Yes for the four named lines. `picture_world.py:102` now holds them and `test_each_real_fix_wording_fits_its_row_whole` passes. The list still misses outreach's line (B1 below) | Test run |
| 01 B5, cut before masked | Yes | `mission.py:240,299,361`; `test_an_address_straddling_a_cut_is_masked_before_the_cut` |
| 01 B6, lock during mask learning | Yes | `mission.py:224`; `test_a_lock_during_mask_learning_is_an_unfinished_write_and_never_an_unmasked_page`, with a real lock |
| 02 B1, stale 08:00 lines | Yes | `.env.example:20`, `discord.md:22,46,114`; `test_morning_schedule.py:124` adds the row and `:133` fails on a missing path |
| 02 S1, hand run while paused posts a card | Yes | `outreach/cli.py:107`; `test_by_hand_while_paused_it_posts_nothing_and_says_so` |
| 01 S1 to S9, 02 S2, S3, N2 | Yes, as the conductor sent them back | Security pass and Standards reviewer read each one; `test_a_plist_time_in_the_future_doesnt_hide_an_upcoming_slot` |
| 02 S4, drift and the install rule | Still open, as logged. It can only be done at the merge | M2 below |

## Standards

**Blocking:** none.

**Should fix**

- **St1. New code duplicates a helper in the same module.** `images.py:139-142` repeats the temp folder and `card.html` write at `images.py:152-155`. Share one small context manager.
- **St2. A glossary entry is now short of the job list.** `CONTEXT.md:28` gives the quiet jobs as "(scout-send, publish)", and `config/settings.yaml:109` makes `outreach-requests` quiet too.

**Nit** (judgement calls unless they say otherwise)

- `one_pager.py:35,49`: `CONTEXT.md:93` lists "summary" under the One-pager's _Avoid_. A small breach. `short_message` would do.
- `picture.py:133,162,322`: reaches the private `health._plural`, from the S7 fix, and no other core module reaches a private name this way. It sits close to `run_update.count:82`. Make one of them public.
- `mission.py:125`: possible Mysterious Name. `morning: Yesterday` holds today's figures.
- `mission.py:383-389,397-402`: possible Duplicated Code. `_yesterday` and `_morning` repeat one try block.
- `digest.py:28`, `privacy.py:204,241,262`: possible Shotgun Surgery. `reraise` passes through four signatures, with one real value.
- `picture.py:407-411`: possible Primitive Obsession. It parses `health.strip`'s text and undoes `untrusted_line`'s escaping.
- `backup.py:27`: possible Mysterious Name. The local `grids` now counts pictures and pages. Keeping the event's key is right.
- `remote.py:223-224`: possible Middle Man. `_short` is now a one-line wrapper, and the refactor wasn't needed.
- `README.md:189,200`: a doc gap, no rule broken. The plug-in table doesn't say the core reads `digest` figure keys by name, so a renamed key shows a dash and blocks the all-clear. It also doesn't say the picture draws only a `health` item's first line.

**Checked, no finding:** the core imports no agent. `caps.py` is unchanged. ADR 0002 holds: `read_patiently` only re-reads, and `installed_at` only stats a file. `_masked` duplicates nothing. Commit subjects follow the card. `pyright` on the 15 touched modules reports 0 errors.

## Spec

### Blocking

**B1. The outreach Fix line is cut on the picture for every real wording.** `agents/outreach/__init__.py:63`; `tests/picture_world.py:102`.

- **Rule:** MB3 as reworded, "A Fix item is one list row of at most 3 rendered lines, and its instruction is not cut". Test strategy criterion 8 counts a failing criterion, or anything cut off on a fixture, as major. Code review 01 blocked B4 on the same rule.
- **Reproduced in Chrome, offline, through `oracle.inspect`:** all seven `send.live_problems` wordings report `lines: 3, cut: True`. They run from 129 to 294 characters, and a row holds about 114.
- **Why it matters:** the row keeps "Clear what stops live outreach, or no email is asked for:" and loses what to clear. In the render, the row ends at "RESEND_API_KEY_OUTREACH is not…". `config/scout.yaml:17` is `mode: live`, so this shows whenever a live problem exists. The message does carry the whole line.
- **Why the test missed it:** `PLUGIN_WORDINGS` has the apps and ICP lines and not this one, and `test_picture_read.py:444` checks only the text.
- **Same cause, smaller:** `health.py:246` puts every unset setting on one line. Up to three names fit. Four or more are cut, as the render shows.
- **Fix:** do what the B4 fix did. Give the line a short first line, and put the problem on a second line for the message and the long text. Do the same for four or more settings. Add both to `PLUGIN_WORDINGS`.

**B2. A draft whose card was answered reads as "to post by hand".** `picture.py:106`.

- **Rule:** PRD "The verdict can't falsely clear him" sets the standard for the verdict, and test strategy criterion 8 counts a false verdict as major. Functional §4 says "A decision before 09:00 simply lowers the count". Approvals-first AF3 says a `browser` platform gets "never a request to post by hand".
- **Reproduced through a real read:** one `draft` row today and one `approved` `social-post` request today give "1 to post by hand". On a built snapshot, `skipped` and `used` give the same. Only a `waiting` request is subtracted, and a draft stays `draft` until it is posted (`publish/kinds.py:61,243`).
- **Why it matters:** cards reach him from 07:30, and he may answer one before 09:00. He would then post by hand what publish posts anyway, on Meta, under his own page. An answered skip reads the same way.
- **Reach:** every platform is `publish_mode: draft` today (`config/social.yaml:118,128,139`), so no card exists yet and nothing on this branch alone can trigger it. The approvals-first PRD switches Facebook and Instagram to `browser`, and PRD L66 merges that first.
- **This isn't the S3 ruling again.** That ruling settled which day counts. It says nothing about a request's reading, and functional B1's "less waiting" didn't foresee the answered case.
- **Fix:** have the social digest report drafts on `draft`-mode platforms as their own figure, and read that. Add the approved and skipped cases to the MB1 table.

### Should fix

**S1. On install day, a job that ran reads "Not installed / No run on record yet".** `picture.py:260-261`; pinned at `tests/test_picture_read.py:218`.

- **Rule:** MB7, "The picture only shows what the engine recorded." Both words are untrue here: the job is installed and a run is on record.
- **Reproduced:** install at 10:00 on Monday 2 Nov, ask at 10:10. Social, Community and App factory read "Not installed / No run on record yet", while their old-time runs from 06:30 to 07:30 are in `runs` and Fix is rightly quiet. Outreach reads the same, and it does have no run yet. The render is amber on those rows.
- **Scope:** only an on-request post on install day. The first 09:00 after an evening install is clean. Functional §4 calls this row correct for `outreach-requests` until its first trace, and it didn't consider a job with history. The same word shows for `outreach-requests` before 08:30 on its first business day, which that note covers.
- **Fix:** when `installs[job]` is `INSTALLED`, a `not installed` slot that isn't overdue should say so plainly, for example "Not judged / Installed at 10:00", and keep "Not installed" for a job launchd doesn't have.

**S2. A job silent two mornings gets two Fix lines.** `picture.py:95`, with `health.py:232`.

- **Rule:** MB3, "one line per item". `test_a_job_silent_for_days_is_one_fix_line` states the intent, and it covers only `not installed`.
- **Reproduced:** "Check `social`: no trace of its run today." and "Check `social`: it missed 1 slot since Mon 2 Nov.", which adds 2 to the verdict's count.
- **Why it matters:** with `FIX_SHOWN` at 4, a Mac that slept through two mornings fills the list with these (five agents would give ten lines, by reading the code, not by a run), and the ICP line or a real failure falls under "and N more".
- **Fix:** drop a job's missed-count line from `fixes()` when `_didnt_run` already names it.

**S3. "and N more: `/growth status`" points at something that doesn't list them.** `one_pager.py:64`; `cli.py:290-315`.

- **Rule:** MB10, the message exists so he can act from a notification. `status` prints pause flags, last runs and setup gaps. It doesn't print the plug-in lines, the ICP line, missed slots or failures.
- **Reproduced:** six items before `schedule install` drop the live-outreach and ICP lines from the message, and neither appears in `status`.
- **Fix:** name `jura-growth one-pager --no-post` on the Mac, or carry the plug-in lines ahead of the "no trace" ones. The first is one line.

**S4. "Later today" states what the schedule says as if it will happen.** `picture.py:278`.

- **Rule:** MB7, as above. Code review 01 left this as a nit. I raise it because the brief asks what reads wrongly on the first real morning.
- **Reproduced:** with every platform in `draft` mode, the picture says "Posts go out 09:00–17:40" beside "N to post by hand" when drafts are waiting. "Emails send 09:30–16:30" also shows while outreach is paused.
- **Fix:** name the windows, not the outcome: "Publish window" and "Send window".

**S5. The Dispatch contract still promises the grid.** `docs/dispatch-contract.md:96`.

- **Rule:** MB12, "The 14-day grid is no longer posted", and SC7. The line reads "Posts the one-pager to `#mission-control` with the 14-day grid". No test reads this file.
- **Fix:** one line. Dispatch's repository may hold a copy to check.

**S6. The live guides stay on the old times after merge.** `outputs/growth/setup/discord.md:22,46,114`; `morning-brief.md:7,9,15,37`.

- **Rule:** SC7. Only the `.scratch` drafts moved. Code review 02 noted that the release must copy them, and PRD §5's after-merge steps don't say so.
- **Fix:** add the copy to the release notes' after-merge steps.

### Nit

- `picture.py:419`: MB3 says "how many requests it has waiting", and a row shows the count only when it is above 0. The empty case reads cleanly.
- `reviews/test-strategy.md:59` still says "past 60 seconds"; `mission.py:69` is 45, which is within "up to" and came from code review 01's S5.
- `picture.py:66-67` uses the raw plist time where `slots.py:176` clamps it to now. It matters only with a wrong clock at install.
- `builds.py:291`, `releases.py:412`: rewording the plug-in lines also changed the long text, where MB11 says "the existing long text". It follows functional S1, so I'd accept it.

### Not asked for

The refactor at `remote.py:223`, noted above. Everything else traces to a review or a ruling: the third verdict wording, `outreach.health` (technical N5) and the 45-second patience.

### Criteria

| Id | Status | Held by |
|---|---|---|
| MB1 | Met, apart from B2 | `test_the_verdict_counts_all_four_things` |
| MB2 | Met | `test_every_font_is_at_least_21_px_in_every_fixture` |
| MB3 | Not met: B1, S2 | `test_the_sections_appear_in_the_order_ting_yu_acts_on_them` |
| MB4 | Met | `test_every_slot_status_has_a_word_and_a_token_colour` |
| MB5 | Met | `test_the_worst_case_says_how_many_more_and_stays_under_the_maximum` |
| MB6 | Met | `test_a_slot_with_no_trace_reads_by_how_long_ago_it_was` |
| MB7 | Met for figures. S1, S4 on words | `test_a_plugin_whose_digest_raises_shows_dashes_not_zeros` |
| MB8 | Met | `test_no_planted_value_reaches_the_page_the_file_or_the_message` |
| MB9 | Met | `test_the_page_is_saved_beside_the_picture` |
| MB10 | Met, apart from S3 | `test_the_message_never_splits_from_the_picture` |
| MB11 | Met | `test_when_the_picture_cant_be_drawn_the_long_text_posts_and_says_why` |
| MB12 | Code met. S5 on the doc | `test_a_normal_post_writes_no_grid` |
| MB13 | Met | `test_the_read_calls_no_kinds_content_or_preview` |
| SC1, SC5 | Met | `test_each_morning_job_has_the_prds_time`, `test_nothing_else_moves`, `test_community_stays_weekly` |
| SC2 | Met | `tests/test_outreach_raise_due.py`, `tests/test_morning_order.py` |
| SC3 | Met | `test_an_email_queued_by_the_morning_run_gets_its_card_ahead_of_the_send_window` |
| SC4 | Met | `test_every_morning_slot_ends_by_the_next_and_by_the_one_pager` |
| SC6 | Met | `test_a_missing_icp_says_what_to_do_with_the_action_first` |
| SC7 | Partly: S5, S6 | `test_a_moved_jobs_own_files_no_longer_name_its_old_time` |

## Security

**No findings at confidence 8 or above.** A separate pass traced the diff, and I reproduced nothing further.

- **`outreach raise-due`:** only `outreach-requests` may use it, it isn't on Dispatch's allowlist, it takes no arguments, and it reaches no send code. `pause all` stops it.
- **The page:** a hostile string through every text route gives one `</body>`, no `<script` and no `<img`, so `measure_height`'s `str.replace` has one target.
- **Fields Fix draws:** masked at the snapshot, built from an integer, or from config.
- **Files and queries:** paths come from the date, the prune matches full names only, queries are bound, and Chrome gets an argument list.

**Looked at, not reported, each older than this diff or below the line:** the long-text fallback skips `_markdown_safe`. `apps/__init__.py:107,110` cuts before masking into a digest line the picture doesn't draw. A `privacy_terms` error other than a lock still leaves names unlearned, as code review 01 recorded.

## Blocked paths

None. `git diff --name-only 1206360..HEAD` holds nothing under `inputs/`, `design-system/`, `.env`, `.github/` or live `data/growth/`. `.env.example` isn't blocked. The frozen test files, `pyproject.toml` and `uv.lock` have an empty diff.

## UI

`crew:web-design-review` on `jura_growth/picture.py`. It is a fixed image, so the rules on focus, forms, animation, touch, hover, hydration and navigation don't apply. I viewed the Sunday, Monday, install-day and not-yet-installed renders.

```text
## jura_growth/picture.py

jura_growth/picture.py:412 - straight quotes around a run's own words → “ ” (nit)
jura_growth/picture.py:260 - "Not installed" on a job that is installed (S1)
```

**Notes, not findings:** Title Case gives way to the design system's sentence case. `%H:%M` suits a single-reader SGT image.

## Merging with approvals-first

**Conflicts.** At `2c9e18d`, `git merge-tree` conflicts in two files only: `health.py` one hunk, `mission.py` three. At the ticket 02 tip `9b7b310`, there is also one hunk in `discord.py`. All are small and mechanical.

| Hunk | Resolve by |
|---|---|
| `health.py`, the failures loop | Keep this branch's `worded(...)` lines, then add `if snapshot.drift is not None:` from theirs, then keep `_missed_counts(snapshot) if short else _missed(snapshot)` |
| `mission.py`, `Snapshot` fields | Keep both: `morning`, `drift`, and this branch's `unavailable()` |
| `mission.py`, `_from_db` | Keep both: their `facts["drift"] = _drift(...)`, this branch's `_yesterday(conn, now, _claude_jobs(source.jobs))` and `facts["morning"]` |
| `mission.py`, `_failures` | Take their loop with its `try`, but **keep this branch's order**: `_clean(row["error"] or "")[:300] or None`. Theirs is `_clean((row["error"] or "")[:300])`, which brings code review 01's B5 back |
| `discord.py`, at `9b7b310` | Keep this branch's `shortened` and take their `split` whole |

**What the merge must also do.** These don't show as conflicts. They block whichever merge lands second, and not this HEAD.

- **M1. The drift line needs an action-first short form.** `Drift.line` is 282 characters, and the picture cuts it before "Restart the Mac once". Reproduced on the merged tree: `lines: 3, cut: True`. This is what functional S2 asked to check, and it matters most in the picture's first days. Give it to `worded(...)`, for example "Restart the Mac once: scheduled jobs run about 9 hours off (`social` due 07:30, ran 22:30)."
- **M2. Drift must ignore runs from before the install (code review 02's S4).** Reproduced on the merged tree: old-time runs give "about 0.5 hours off: `app-factory` is due at 07:00 SGT and ran at 06:30 SGT" with the advice to restart the Mac. It shows from the merge until the jobs' first new runs, on any post in that time. A digest run after those runs also clears it. Once a morning has run on the new times it is quiet: I read `None` at 09:00 on the first morning. Passing `source.installed_at` to `_recent_starts` and dropping earlier starts clears it in my throwaway copy, and a job with no install time still reports.
- **M3. Four tests in `test_schedule_drift.py` need new times.** They read the shipped job list and hold the old times, so they fail on the merge: `test_steady_drift_reaches_needs_you`, `test_the_one_pagers_own_run_clears_the_line_after_a_restart`, `test_a_skipped_run_counts_as_a_start` and `test_reading_drift_changes_no_file_and_never_opens_a_writable_connection`. Three need time values only: `social` at 22:30 and `one-pager` at 00:00. `test_the_one_pagers_own_run_clears_the_line_after_a_restart` also needs today's `one-pager` at 09:00 and the read at 09:05, because the file's clock is 08:00. I checked this in my copy.
- **M4. The digest.** `tests/test_morning_schedule.py:24` pins 17:30, and PRD §3 says approvals-first moves it to 18:05. Neither tip has moved it yet. `settings.yaml` has no diff there, so when it does move, that test and the `LATER` row follow it.

**Full suite on the resolved merge, in a throwaway copy:** 11 failed, 4933 passed.

- **Four are this merge's,** the M3 tests. With the M2 change and M3's time values, `test_schedule_drift.py` passes whole in my copy (67 passed).
- **Seven are not caused by this branch:** two in `test_publish_instagram_linkedin.py`, four in `test_publish_items.py` and one in `test_publish_run.py`. They fail the same way on `2c9e18d` alone, also in a throwaway copy, and pass on this HEAD. That branch's reviewers should look at them. They may be in flight there, or come from running it in a copy. I didn't resolve which.

## For the conductor

- **The order of work.** B1 and B2 can be done on this branch now, and neither touches the conflict hunks. M1 to M4 go with the rebase.
- **One departure from the brief to record.** The brief says never to run `schedule render`, even in a probe. No probe of mine calls it. The full suite does (`tests/test_core.py:353`, `tests/test_isolation.py:70,150`), under `conftest.py`'s temp folders, and I ran the suite as the card and exit criterion 2 require, on this HEAD and on a throwaway merge. My probes called the pure `schedule.plist()` and wrote the result to a temp LaunchAgents folder. Afterwards the newest plist in `~/Library/LaunchAgents` was still dated 29 October, and the newest file in the live `one-pager` folder 30 October.
- **QA is working in this worktree at the same time.** `tests/test_qa_01_defects.py` appeared, untracked, while I reviewed. It isn't mine, and it wasn't in either suite run I report here. Its tests overlap B1 and S5, and it also holds a defect about the post path's write connection during a held lock, which I didn't assess. Read QA's report beside this one.
- **Sign-off.** The PRD records "not signed", proceeding under the standing instruction, with merge as his acceptance. I treated this as recorded, not as a finding.
- **Not verified:** real fonts and `reviews/qa-*.md` (QA's, and none exists yet); Discord's display; launchd firing; whether a Mac that wakes late can show a job as "Didn't run" in the seconds before its run row is written, which I read as out of scope under functional SC4 and did not try.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest -rs -q -p no:cacheprovider -o addopts=""` at `33fb30d`, worktree exports set | 4342 passed, none skipped, in 342 s |
| `uv run pyright --pythonpath .venv/bin/python` on 15 touched modules | 0 errors, 0 warnings |
| `git merge-tree --write-tree --name-only` with `2c9e18d`, then `9b7b310` | `health.py`, `mission.py`; then those and `discord.py` |
| Full pytest on the resolved merge, on a throwaway copy | 11 failed, 4933 passed; listed by name under "Merging with approvals-first" |
| `tests/test_schedule_drift.py` on that copy | 4 failed, 63 passed; 67 passed with M2 and M3 applied |
| `tests/test_publish_items.py`, `test_publish_instagram_linkedin.py` and `test_publish_run.py`'s failing test on `2c9e18d` alone | The same failures; `test_publish_items.py` is 18 passed on this HEAD |
| Probes on temp data, offline Chrome | First-mornings table, B1, B2, S1 to S4, M1, M2 as quoted |
| `git diff --name-only 1206360..HEAD` filtered to blocked paths | Empty |
| `git status` in the worktree before this file | Clean |

Nothing posted, `jura-growth run` and `schedule install` were never run, and live data wasn't touched.
