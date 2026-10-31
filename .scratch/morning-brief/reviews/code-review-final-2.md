# Code review, final 2: crew/morning-brief

- **Branch:** `crew/morning-brief` at `00b0ab4`
- **Fixed point:** `279c4a8`, the commit that recorded the final review and QA (5 commits and the merge, 24 files)
- **Spec:** `prd-jura-morning-brief-2026-10-31.md`, `reviews/code-review-final.md`, `issues/03` to `08`, and the `crew-log.md` entries from 23:10 and 23:50

## Verdict: approve

There are no blocking findings. Every finding from the final review and every defect ticket is fixed. The suite is green at 4387 passed, with nothing skipped. A real exclusive lock through the real command now ends in a post, with exit 0, inside Dispatch's 60 seconds.

Four should-fix findings remain. The first is the one to decide on: a paused `digest` still posts during a long lock. None of them makes the release wrong, because each needs a long lock to coincide with something rare, or is a word or a doc.

File references are at `00b0ab4`. "Reproduced" means I ran it on temp data. The probes are in the scratchpad and aren't on the branch.

## The questions in the brief

| Question | Answer | Evidence |
|---|---|---|
| Can the shared code change behaviour for another job? | Only in one rare, better way, and one extra log line. See the table below | `test_other_jobs_still_stop_at_a_lock`, and reading each caller |
| Can the morning post go out twice? | No, not through this code. Dispatch's 60 seconds is the one remaining route, and the margin is about 10 seconds | Traced below |
| Can it be lost silently? | Not to a lock. A non-lock database error at the job's first connection still leaves only a traceback, as it does for every job and as it did before | Traced below |
| Can approval lapses be skipped wrongly? | No | Reproduced below |
| Are the two pyright errors old? | Yes, both | `git blame` and pyright at `279c4a8`, below |

### The shared code, job by job

| Code | Effect on other jobs |
|---|---|
| `runner.run` | A one-name gate, `POSTS_PAST_A_LOCK` (`runner.py:74`). Every other job takes the same `db.connect()` and `_run_locked` as before. `ran` stays `None` and does nothing |
| `db.connect`, `db.session` | With no `wait`, the timeout is still 30 and the pragma still 30000, because the default is `BUSY_SECONDS`. `session` only gained a keyword-only argument |
| `discord.post`, `_noted` | **This one does reach every poster.** A lock on the record after delivery is now kept to itself and the post is reported as delivered. It used to raise. The record was lost either way, so a same-day re-run of a deduplicated post could already post again, and this doesn't make that worse. The job now carries on instead of failing on a message that went out. The 23:50 log says "only one-pager runs past a lock", which is true of the runner and not of this helper |
| `discord.post` with `None` | Not new. `None` already meant no record and no dedupe. `one_pager.post` is the only new caller |
| `remote._masked`, `remote._record` | The short wait applies only when `words[:1] == ["one-pager"]`, and `test_other_remote_commands_keep_the_long_wait` holds that. Every command now gets a mirror line when the database can't take its audit event. That is harmless, and it wasn't asked for |
| `mission` | `_is_lock` and `_state_of` give the same answers through `db.is_lock`. `LOCK_PATIENCE` is read only by `read_patiently`, and `cli.py:442` is its only caller |
| `images._page_file` | Same file, same URI, same lifetime for social's images |
| `social_drafts_by_hand` | A new key in the digest's figures. The digest doesn't print figures by key, and its `brief` line is unchanged (`test_digest_figures`) |
| Fresh imports | `discord` and `mission` now import `db` at the top. Each of nine modules imports alone in a new process with no cycle. `log` already imported `db` |

### Twice

- **The job.** `_run_locked` sets `ran` straight after the body's `except Exception`, so a body that started always leaves an outcome (`runner.py:176-179`). Only a lock before the body reaches the fallback at `runner.py:118`. `test_a_lock_landing_after_the_post_never_posts_twice` holds this with a real lock, and my own run gave one post.
- **The command.** `_post_past_a_lock` retries with `None` only if `one_pager.post` raises a lock. Nothing writes after delivery except `_noted`, which keeps a lock to itself. `one_pager.post` returns straight after `discord.post` (`one_pager.py:317`). Its other writes, `picture_failed` and `attachment_refused`, come before the send.
- **Dispatch.** The real command under a real `EXCLUSIVE` lock took 45 seconds with Discord off, against the developer's 43. `remote` adds up to two more 2-second waits, and the upload isn't in my figure. That gives about 50 seconds, leaving about 10. A Discord 429 can wait 10 seconds. So a lock past 30 seconds and rate limiting together could still pass 60, and then Dispatch reports a failure on a post that goes out. I read that as acceptable. `test_the_whole_wait_stays_inside_dispatchs_window` counts one wait per connection, while the upkeep can spend three on one connection under `IMMEDIATE`. The sum still fits.

### Lost

- **A lock.** The upkeep skips with a mirror line. The read gives the bad-day snapshot past its patience. The post goes with `None`. If even that fails, `one_pager.not_posted` and `run.database_locked` are in the mirror and the failure goes to `#alerts`, which `test_when_even_the_post_is_impossible_the_failure_leaves_a_clear_trace` holds.
- **Not delivered.** With no webhook, or when Discord refuses, the message goes to the outbox and the next post counts it.
- **Slot.** The `run.quiet` line works for a job that isn't quiet. After the fallback, the next morning's real read gives the 09:00 slot as `ok`, with no missed line (reproduced).

### Lapses

Reproduced with a real `IMMEDIATE` lock and a request at its decide-by:

| Moment | Result |
|---|---|
| During the post | Exit 0, posted, one `one_pager.upkeep_skipped` line. The row is still `pending`, it reads `lapsed` by the clock, and `waiting()` is empty |
| The next writer, the heartbeat | The row is `expired`, and the card has one edit |

The picture can't ask him to decide a lapsed request. `decide` and `use` check the clock themselves (`approvals.py:402,551`), so a late click on a card that hasn't been edited yet is refused. The short wait makes the skip more likely, at any lock over 2 seconds instead of 30, and that delays the write and the card's edit until the heartbeat at 12:00. The doc that says otherwise is under Sf3.

### Pyright

`uv run pyright` on the 12 touched source modules at `00b0ab4` reports 2 errors: `runner.py:84` and `runner.py:199`.

- **`git blame`:** both lines are `^3969a43`, the root commit of 2026-10-24.
- **At `279c4a8`:** the same two errors at `runner.py:81` and `runner.py:159`. A third error there, `"runner.Outcome" is not assignable to "jura_growth.runner.Outcome"`, comes only from my checking an extracted copy, which gives the module two names. It isn't in the worktree's run.
- **The card's rule, no new errors in files you touch:** holds.

## Fixes confirmed

| Finding | Fixed? | Evidence |
|---|---|---|
| B1, issue 04, outreach and unset-settings lines cut | Yes | `outreach/__init__.py:56`, `health.py:247`; `test_each_real_line_about_live_outreach_fits_its_fix_row_whole` builds each wording through real `live_problems()`, in Chrome |
| B2, issue 06, answered card reads as by hand | Yes | `social/__init__.py:51,74`, `picture.py:108-112`; `test_picture_read.py:443` holds it through a real read |
| S1, issue 08, installed job reads "Not installed" | Yes | `picture.py:259,275-282`; `test_an_installed_job_with_a_run_on_record_never_reads_not_installed` |
| S2, issue 07, two lines for one silent job | Yes | `picture.py:100`; `test_a_job_silent_two_mornings_is_one_fix_line` |
| S3, "and N more" pointed at `status` | Yes | `one_pager.py:64` |
| S4, Later today stated an outcome | Yes, with the wrong word (Sf4) | `picture.py:297` |
| S5, issue 05, contract named the grid | Yes | `docs/dispatch-contract.md:96`; `test_mission_setup_guides.py:23` |
| S6, live guides after merge | Not code. The 23:10 ruling puts the copy in the after-merge steps, so the release notes must carry it | `crew-log.md` |
| St1, repeated temp folder | Yes | `images.py:125` |
| St2, quiet jobs in the glossary | Yes | `CONTEXT.md:28` |
| Issue 03, long lock stops the post | Yes | `cli.py:395,408`, `discord.py:391`, `runner.py:102`, `remote.py:457`; real run below |
| E15 ruling, real items ahead of "no trace" | Yes, and further than the ruling (nit below) | `picture.py:103-106` |

`tests/test_qa_01_defects.py` is deleted as logged. All nine of its test functions exist on HEAD with the same assertions or stronger. Two weakened in effect are nits below.

## Standards

**Blocking:** none.

**Should fix**

**Sf3. Three docs now say something the code doesn't.**

- `CONTEXT.md:28` and ADR 0001 define `run.quiet` as a quiet job that found nothing to do. `runner.py:124` writes it for a job that isn't quiet and did post. The slots read it correctly, so this is the term and not the behaviour. Add a line to the ADR.
- `README.md:70` says the command "writes the approval lapses that are due first". It now does so unless growth.db is locked.
- ADR 0002 says "the one-pager job writes those transitions on the runner's own connection before the read model runs". It no longer uses the runner's connection, and the write can be skipped. Amend it. The rule it protects, that the read never writes, holds.

**Sf4. "Publish window" is the glossary's avoided term.** `picture.py:297`, pinned at `tests/test_picture.py:559`. `CONTEXT.md:225` says **Posting window**, _Avoid_: "publish window". The wrong word was my own suggestion in S4, and the developer took it as written. Change the one word and its test.

**Nit** (judgement calls unless they say otherwise)

- `discord.py:391`: possible Data Clumps. `_noted` takes seven positional parameters, one a bare bool.
- `runner.py:133`: possible Primitive Obsession. `ran: list | None` is a list used to hand back one outcome.
- `cli.py:402,414`, `discord.py:397`, `runner.py:111`: possible Duplicated Code. The same lock-or-raise block appears four times. A helper would hide the one line that differs in each, so I'd leave it.
- `runner.py:120,127`: possible Duplicated Code with `:177,204`.
- `runner.py:74`, `remote.py:457`: possible Repeated Switches. Two one-pager special cases, with literals that `mission.ONE_PAGER_JOB` already names, while job flags otherwise live in settings or `caps`.
- `remote.py:433`: the local `payload` shadows the function at `:413`. Harmless here.
- `mission.py:278`: possible Middle Man. `_is_lock` only calls `db.is_lock`.
- `picture.py:101`: possible Feature Envy. It matches `health`'s wording by prefix, and `items[:paused]` relies on the strip's order. Both hold today, and tests would catch a change of wording.
- `health.py:247`: a bare `3`, where `picture.py:42` names its caps.
- `tests/test_one_pager_post.py:449,465,483`: the `remote.env` setup is repeated three times.

**Reuse:** `db.is_lock` consolidates mission's check, and there is no other copy. Nothing duplicates the standard library or an installed dependency.

## Spec

**Blocking:** none.

**Should fix**

**Sf1. During a long lock, a paused `digest` still posts the one-pager.** `runner.py:118`.

- **Rule:** `pause.py`, the kill switch, and the order in `runner.py:3-5`, where the agent's pause flag comes before the job. The 23:10 ruling asked for "the smallest way" to get the post out, and it didn't ask to pass a pause.
- **Reproduced with real locks and `pause digest`:**

| Lock | Status | Posts |
|---|---|---|
| None | `skipped`, "held by hand" | 0 |
| `IMMEDIATE` | `ok`, "posted to #mission-control" | 1 |
| `EXCLUSIVE` | `ok`, "posted to #mission-control" | 1 |

- **Why:** under `EXCLUSIVE` the flag can't be read. Under `IMMEDIATE` it is read correctly: `_run_locked` knows the agent is paused, and then `log.skip_run` (`runner.py:162`) hits the lock while writing the skip. The fallback takes that for "nothing has run yet" and runs the job.
- **Reach:** `one-pager` runs as agent `digest`, a system agent, so `pause all` never covered it. This affects `pause digest` and the auto-pause after three failures. The PAUSE file still stops it (`runner.py:81`). It needs a pause and a lock past 30 seconds at 09:00 together, and what escapes is a post to his own channel, which is why it isn't blocking.
- **Fix:** have the fallback ask `pause.is_paused` on a read-only connection first, and when that can't be read, post and say so in `run.database_locked`. Or have `_run_locked` hand back a reason it found and couldn't record. The `IMMEDIATE` case should end in `skipped`.

**Sf2. A post that went out can read as failed the next morning.** `runner.py:103-106`, `mission.py:351`.

- **Rule:** MB7, "The picture only shows what the engine recorded", and issue 03's "A post that went out is reported as posted".
- **Reproduced in two parts.** A lock landing at `finish_run` gives one post and leaves the row `running`, so the slot reads `running` that morning. Then, with a row finished exactly as `_abandon_stale` finishes it, the next morning's read gives "Check `one-pager`: it failed on Tue 10 Nov, 09:00 SGT." with the quote "abandoned: the process stopped before finishing", and it adds to the verdict's count. I built that row by hand, because `_abandon_stale` runs on the real clock.
- **Reach:** it needs a lock that starts after the upload and lasts past 30 seconds. The line lasts one morning, until the next `ok`. The trade against a double post is right, and the developer logged it. The false line wasn't ruled on.
- **Fix, or accept:** `_abandon_stale` could finish the row with the status in the mirror's `run.database_locked`. If that is more than it's worth, the conductor can accept the one line.

**Nit**

- `picture.py:103-106`: plug-in lines now sort ahead of failed runs, further than the ruling's "real items sort ahead of no trace lines". The developer logged it. Reproduced: with a pause and four plug-in lines, a failed run falls under "and N more", and by the order three would do it. The failure has also gone to `#alerts`, and the `--no-post` pointer finds it. Moving `plugins` after the failures would match the ruling exactly, but then a failure streak could push out the ICP line, which is what E15 feared. It's the conductor's call.
- `tests/test_picture.py:65`: `test_an_answered_social_card_is_not_a_draft_to_post_by_hand` keeps its assertion but can no longer fail on the card's reading, because `_to_post_by_hand` reads neither approvals nor `social_drafts_waiting`. `test_picture_read.py:443` is what holds B2.
- `tests/test_picture_chrome.py:166`: `test_every_unset_setting_is_named_on_its_fix_row` now passes on a row that names no setting, as issue 04's "at least ends with what to do" allows. The name overstates it.
- `tests/test_picture.py:251`: MB4's token test walks `STATUS_WORDS`, so `.s-not-judged` has no test. The class is at `picture.py:379` and the word is pinned at `test_picture.py:372`.
- `runner.py:127`: if an alert goes out and `check_auto_pause` then hits the lock, the fallback alerts again. Two lines in `#alerts`, and never a second post. The auto-pause check doesn't run on that path. By reading.
- `discord.py:399`: a non-lock database error after delivery still raises, and `one_pager.not_posted` then says something untrue. It raised before this round too. By reading.
- PRD L64 says "up to 60 seconds" and `LOCK_PATIENCE` is now 30. That is within "up to", and it serves the same 60 seconds.

**Not asked for:** `_noted`'s reach to every poster and the mirror line for every remote command, both above. Both are harmless, and neither needs undoing.

### Criteria touched by this round

| Id | Status | Held by |
|---|---|---|
| MB1 | Met | `test_picture_read.py:443` |
| MB3 | Met. B1 and S2 are closed | `test_each_real_line_about_live_outreach_fits_its_fix_row_whole`, `test_a_job_silent_two_mornings_is_one_fix_line` |
| MB4 | Met. The new class has no test (nit) | `test_every_slot_status_has_a_word_and_a_token_colour` |
| MB7 | Met, apart from Sf2 | `test_an_installed_job_with_a_run_on_record_never_reads_not_installed` |
| MB10 | Met | `test_the_message_never_splits_from_the_picture` |
| MB12 | Met. S5 is closed | `test_the_dispatch_contract_no_longer_says_the_one_pager_carries_the_grid` |
| Held lock, PRD L64 | Met | `test_the_job_posts_through_a_real_lock_held_throughout`, `test_dispatchs_path_answers_through_a_real_lock` |

## Security

**No findings at confidence 8 or above.** A separate pass traced this diff.

- **Posting with no connection.** `mission.read` masks the snapshot. On a lock, `facts` is empty, so no database text reaches the post. What the read learned stays in the process, because `reset_caches` runs only in the CLI callback, before the read. Reproduced under a real `EXCLUSIVE` lock: `discord.post(None, ...)`, `discord.alert(None, ...)` and `one_pager.post(None, ...)` all sent "j\*\*\*@example.com", "[name removed]" and "[redacted]" for a planted address, name and token.
- **Mirror lines.** Each new `log.event(None, ...)` goes through `config.redact`. `not_recorded` is a fixed string.
- **`remote`.** The short wait only makes `_masked` degrade sooner, and `for_discord` still runs. The actor check in `handle` is unchanged.
- **New text.** `LIVE_BLOCKED_LINE` and `_gap_lines` hold setting names, never values. `dnc.path()` can appear in the message, as it could before, and the picture now draws only the first line. `NOT_JUDGED` and the `LATER` labels are constants, and `_installed_row`'s detail passes through the page's escaping.

**Looked at, below the line.** `runner.py:127` cuts `error[:500]` before masking, the same order as the older `runner.py:204`, so an address straddling the cut could lose its mask (the shape of code review 01's B5, on an alert, not the picture). Sf1 is a correctness finding, not a security one.

**One correction to the pass:** it said a paused `all` can post during a lock. `digest` is a system agent, so `pause all` never covered it (`pause.py:9`, `settings.yaml:57`). I also dropped a Standards note that `README.md:215` went stale: `one-pager` has no `run_update`, so `_run_update` posts nothing on that path.

## Blocked paths

None. `git diff --name-only 279c4a8..HEAD` holds nothing under `inputs/`, `design-system/`, `.env`, `.github/` or live `data/growth/`.

## UI

`crew:web-design-review` on the lines of `jura_growth/picture.py` changed since `279c4a8`. It is a fixed image, so the rules on focus, forms, animation, touch, hover, hydration and navigation don't apply.

```text
## jura_growth/picture.py

jura_growth/picture.py:281 - "Due at 07:30", hardcoded time format → single-reader SGT image, as noted last round (note, not a finding)
jura_growth/picture.py:379 - .s-not-judged uses design system tokens ✓ pass
```

Sentence case on "Not judged" follows the design system, not the guidelines' Title Case. The word is on the page as well as the colour.

## For the conductor

- **The decision:** Sf1. I'd take it into the release as a small fix, because a kill switch that a lock can pass is a poor thing to leave behind, and the fix is a few lines. It isn't release-wrong if you choose to log it instead.
- **One departure from the brief to record, the same as last round.** The brief says never to run `schedule render` in a probe. No probe of mine calls it. The full suite does, under `conftest.py`'s temp folders, and I ran the suite as the card and step 7 require. Afterwards the newest plist in `~/Library/LaunchAgents` was still dated 29 October, and the newest file in the live `one-pager` folder 30 October.
- **I ran the real `jura-growth one-pager` once,** with `JURA_GROWTH_DISCORD=off`, an empty env file, temp data folders and a dead proxy, as issue 03's steps do. It wrote to a temp outbox. Nothing posted.
- **Not verified:** the `remote` path with real waits (its waits are asserted by `test_nothing_on_dispatchs_path_takes_the_long_wait`, and I timed only the command); a real upload's time; launchd firing; Dispatch's own timeout.
- **M1 to M4** from the final review are still for the rebase, as ruled. Nothing in this round touches them, and I didn't re-run the merge.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest -q -rs -p no:cacheprovider -o addopts=""`, worktree exports set | 4387 passed, none skipped, in 568 s |
| `uv run pyright --pythonpath .venv/bin/python` on 12 touched modules at `00b0ab4` | 2 errors, `runner.py:84,199` |
| Pyright on `runner.py` from a `git archive` of `279c4a8` | The same 2 at `:81,159`, plus 1 from the copy's module name |
| `git blame -L84,84` and `-L199,199 jura_growth/runner.py` | Both `^3969a43`, the root commit |
| `jura-growth one-pager` under a real `BEGIN EXCLUSIVE`, Discord off, temp data | Exit 0 after 45 s, saved to the outbox, `one_pager.upkeep_skipped` in the mirror |
| Reviewer's probes through the suite's fixtures and real locks | 12 passed; pause, slot, abandoned row, lapse, masking and Fix order as quoted |
| `python -c "import <module>"` for nine modules, each in a new process | No cycle |
| `git diff --name-only 279c4a8..HEAD` filtered to blocked paths | Empty |
| `git status --short` before this file | Clean |

Nothing posted, `jura-growth run` and `schedule install` were never run, and live data wasn't touched.
