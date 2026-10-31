# Quality gate: morning brief

```
Decision: GO, for opening the PR with the body set out under criteria 10 and 11
Branch: crew/morning-brief @ b953955 (base main @ 1206360; origin/main is at f9a9ad6)
```

Nine of the eleven exit criteria are met on this commit. Criteria 10 and 11 are conditions on a PR body, and the operating card opens the PR only after G4, so they can't be met until after this call. The release must check them.

**This go rests on two readings a stricter reader could reject.** Both are mine, and both are set out below so they can be overruled:

1. **Criterion 6.** Two added comment lines are outside its letter.
2. **Criterion 8.** I grade Sf2 as minor. Called a false verdict, it is major and this becomes a no-go.

## Exit criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Every row has a passing test or recorded case | Met | Trace below, against this run's JUnit |
| 2 | Full suite: 0 failed, 0 skipped, at least 3,982 collected | Met | **4388 passed, 0 skipped, in 431.91 s** |
| 3 | P offline, and `--live-fonts` with all three fonts | Met | Offline: `test_the_page_holds_together` 5 passed, and the helper reports `problems: []` on all five. Live: below |
| 4 | W, Q and B at 550 px, every word read | Met | Below, read at b953955 |
| 5 | Risk 1 tests exist, pass, and name the `.html` and the spy page | Met | `tests/test_picture_privacy.py`, 78 passed. Its fixture spies on `images.screenshot`, reads `picture-2026-11-10.html` from disk and asserts the two are equal. Nine routes in `ROUTES`, each planted alone |
| 6 | Frozen files unchanged; three files differ only in time values or clock arguments | **Met, with one disclosed exception** | Frozen list: empty diff against `main` and `origin/main`. Every other changed line normalises to its original, apart from one comment (below) |
| 7 | Nothing under `inputs/` or `design-system/`; no `<script` | Met | `git diff main --name-only` and `git diff origin/main...HEAD --name-only`: no such path. `grep '<script' jura_growth/picture.py`: none. A page saved by the real command: 0 |
| 8 | Zero open critical or major defects; minors listed with an owner | Met, on my grading of Sf2 | 0 critical, 0 major, 5 minor (below). Issues 03 to 08 are fixed |
| 9 | No unresolved blocking review finding; pyright adds no error | Met | Reviews and pyright below |
| 10 | Approvals-first: rebase if merged, else the PR body says to merge it first | Branch state met. **PR body for the release** | `git ls-remote`: `2c9e18d` is not an ancestor of `origin/main` at `f9a9ad6`. No PR exists for this branch yet |
| 11 | PR body opens with the four after-merge steps and attaches three renders | **For the release** | The renders are refreshed from b953955 (below). The text is below |

The strategy predates a rename. I read its `brief.py`, `brief.html()`, `tests/brief_chrome.py` and `tests/brief_world.py` as `picture.py`, `picture.html()`, `tests/picture_chrome.py` and `tests/picture_world.py`.

### Criterion 6: the exception

I replaced times and `world.source(...)` arguments in each changed line, then compared the lines with their originals.

| File | Changed lines | Outside a time value or clock argument |
|---|---|---|
| `tests/test_mission_read.py` | 22 | 0 |
| `tests/test_one_pager.py` | 1 | 0 |
| `tests/test_mission_health.py` | 5 removed, 6 added | **2 comment lines:** "…before the gap lines, with its / times following the morning brief PRD." |

The comment isn't executed and changes no assertion. `code-review-02.md:47` asked for it, because the golden no longer matches the commit the comment named. I count this as met because the criterion exists to stop assertions being rewritten. By its letter, "every changed line", these two lines don't qualify. The strategy is unchanged, and I did not reword a criterion to pass it at the gate.

### Criterion 8: defects

**Fixed, on fresh evidence.** The ticket files still say `Status: ready-for-agent`, which is stale. The conductor should close them.

| Ticket | Was | Evidence at b953955 |
|---|---|---|
| 03, long lock stops the post | Major | Real lock through the real command, below. The three tests the ticket names pass, as do the real-lock tests the fix added |
| 04, real Fix lines cut | Major | `test_each_real_line_about_live_outreach_fits_its_fix_row_whole` 8 passed. **New with real fonts:** all 26 real wordings in `world.health_pages()` show no cut Fix row, at most 3 lines |
| 05, contract names the grid | Minor | `test_the_dispatch_contract_no_longer_says_the_one_pager_carries_the_grid` passed. The search below is clean |
| 06, answered card reads as by hand | Major | `test_only_a_draft_on_a_draft_mode_platform_is_to_post_by_hand` 2 passed, through a real read |
| 07, two Fix lines for one job | Minor | `test_a_job_silent_two_mornings_is_one_fix_line` passed |
| 08, installed job reads not installed | Minor | `test_an_installed_job_with_a_run_on_record_never_reads_not_installed` passed |

**Open: 0 critical, 0 major, 5 minor. None blocks.**

| Id | Defect | Owner | Why minor |
|---|---|---|---|
| Sf2 | A lock landing after delivery and lasting past 30 seconds leaves a run row that later reads as failed. The next morning shows one false line and counts it | Conductor, accepted 00:30. Developer if it is ever seen | See below |
| Sf1 remainder | Under an `EXCLUSIVE` lock the pause flag can't be read, so a paused `digest` still posts to his own channel | Conductor, accepted 00:30 | No criterion covers a `digest` pause, and criterion 8's critical list doesn't name it. The `IMMEDIATE` case is fixed (`test_a_paused_job_read_under_a_lock_stays_skipped_and_posts_nothing`), and the PAUSE file is checked before any lock. This case rests on reading `runner.py` and the reproduction in `code-review-final-2.md`. I didn't rerun it |
| G1, **new** | Under a real lock with four or more other Fix lines, the lock's own line, "Send `/growth status` to clear it", falls under "and N more" | Developer, after release | Reproduced, with the temp setup supplying the other lines: "6 to fix", and the line isn't among the four shown or in the message. The picture still says it under Decide. A configured Mac has few such lines, and MB5 allows the cap |
| T1 | Two tests are weaker than their names, `test_an_answered_social_card_is_not_a_draft_to_post_by_hand` and `test_every_unset_setting_is_named_on_its_fix_row`, and `.s-not-judged` has no token test | Developer, after release | `code-review-final-2.md` nits. Other tests hold the behaviour |
| N1 | `jura-growth status`: `outreach-requests` pushes its row out of line (QA E17) | Developer, after release | Cosmetic |

**Sf2, confirmed further than the review did.** Through the real `_abandon_stale` on a row that was really left running, the next morning's real read gives:

```
Check `one-pager`: it failed on Sat 31 Oct, 21:43 SGT.
> abandoned: the process stopped before finishing
```

The line is false, because the post went out, and it adds one to the verdict's count.

My grading is minor, for three reasons:

- The verdict counts correctly what the engine recorded. The record is what's wrong.
- It errs toward looking. It can't falsely clear him, which is what the PRD and risk 2 fear.
- Acting on it costs a glance, for one morning, after a rare coincidence.

**The case against:** issue 06 was graded major as "a false verdict" although it was also a false alarm. The difference I rest on is harm. That line would have had him post by hand what publish also posts. Anyone who reads any false count as a false verdict should treat this as major and a no-go. The way back is under "To turn a NO-GO into a GO".

### Criterion 9: reviews and pyright

| Review | Verdict | Blocking findings now |
|---|---|---|
| `code-review-01.md` | Changes requested | B1 to B6, each confirmed fixed in `code-review-final.md` |
| `code-review-02.md` | Changes requested | B1, confirmed fixed in `code-review-final.md`. The search below agrees |
| `code-review-final.md` | Changes requested | B1 and B2, confirmed fixed in `code-review-final-2.md` |
| `code-review-final-2.md` | Approve, at `00b0ab4` | None |

**b953955 has had no review.** The conductor made it directly after the approval. I read its diff in full: one word in `picture.py`, two lines and a docstring in `runner.py`, a new test, a changed test value, and README and ADR wording. Sf1's `IMMEDIATE` case, Sf3 and Sf4 are fixed as ruled.

**Pyright, 27 touched modules:** 2 errors at b953955, at `runner.py:84` and `:201`. On the same modules at `1206360`, the same two messages, at `:81` and `:159`. The branch adds none.

### Criteria 10 and 11: what the release must do

The PR body must open with the following, in substance, and attach these three renders:

1. **Merge `crew/approvals-first-social-depth` first, if it is ready.** That rebase does M1 to M4 of `code-review-final.md`, and criterion 2 is rerun.
2. `git pull` and `uv sync` in the Mac's checkout.
3. `uv run jura-growth schedule install`, because times moved and there is a new job.
4. Restart the Mac once and log in, or 09:00 fires at midnight.
5. Put the ICP in `inputs/icp.md`, from the draft at `outputs/growth/setup/icp-draft.md`.
6. Copy `discord.md` and `morning-brief.md` from `.scratch/mission-control/setup/` to `outputs/growth/setup/` (`code-review-final.md` S6, the 23:10 ruling).

Steps 2 to 5 are the four in criterion 11. The body must also say that UAT U1 to U7 run after merge, and that a failure means revert.

Renders, 1200 px wide, from b953955 with real fonts:

- `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/2e83ea48-1f12-40ea-9c1c-3041ffd846ed/scratchpad/renders/full.png`
- `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/2e83ea48-1f12-40ea-9c1c-3041ffd846ed/scratchpad/renders/quiet.png`
- `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/2e83ea48-1f12-40ea-9c1c-3041ffd846ed/scratchpad/renders/bad-day.png`

**Three things the release should know:**

- **Local `main` is stale.** It is at `1206360`, two commits behind `origin/main`. This branch merges cleanly with `f9a9ad6`, which changes one YAML comment, `docs/app-factory.md` and `.scratch` files. I didn't run the full suite on that merge. The three test files that read those docs or the guides pass on it: 69 passed.
- **The rebase has grown.** The conflicts with `2c9e18d` are still `health.py` and `mission.py`. Ticket 02's tip is now `2283be8`, later than the `9b7b310` the final review checked, and it also conflicts in `CONTEXT.md`, `README.md`, `docs/scout.md`, `discord.py` and `tests/test_mission_health.py`. That last file is one criterion 6 limits, so a rebase must check it again.
- **This go covers b953955 only.** Any rebase needs criterion 2 rerun, as criterion 10 says, and criteria 3 and 6 are worth rerunning with it.

## Fresh run

All on b953955, with a clean worktree before and after apart from this file. Every probe used temp folders, an empty env file and `JURA_GROWTH_DISCORD=off`.

| Command | Result |
|---|---|
| `uv run pytest -rs -p no:cacheprovider -o addopts=""` with the worktree exports, `JURA_GROWTH_DISCORD=off` and `--junitxml` | **4388 passed in 431.91 s.** JUnit: 0 failures, 0 errors, 0 skipped. `conftest.py` sets the Discord variable itself for each test |
| `uv run python tests/picture_chrome.py --live-fonts --out <temp>` | Exit 0, table below |
| `uv run python tests/picture_chrome.py` (offline) | Exit 0, `problems: []` on all five: 900, 1190, 949, 949, 1554 px |
| QA's `document.fonts` status read, re-run | All five fixtures, live: DM Sans, Outfit and IBM Plex Mono, each 400 and 500 `loaded`. Offline: none |
| `uv run pyright` on 27 modules, at the branch and the base | 2 errors each, the same two |
| `git diff main --stat` on the frozen list | Empty |
| `git merge-tree` with `origin/main` | Clean |
| `git merge-tree` with `2c9e18d`, then `2283be8` | 2 conflicting files, then 7 |

**`--live-fonts`:**

| Fixture | Height | Measured | PNG | Cut | Problems |
|---|---|---|---|---|---|
| quiet | 894 | 894 | 1200×894 | 0 | `[]` |
| typical | 1184 | 1184 | 1200×1184 | 0 | `[]` |
| database missing | 943 | 943 | 1200×943 | 0 | `[]` |
| database locked | 943 | 943 | 1200×943 | 0 | `[]` |
| worst | 1548 | 1548 | 1200×1548 | 13 clamps, all W's deliberately long text | `[]` |

**The real command, on seeded synthetic data at a frozen 09:00:**

| Case | Result |
|---|---|
| `one-pager --no-post`, no database | Exit 0, folder unchanged |
| `outreach raise-due`, shadow, 08:30 | "no requests raised", exit 0, every file byte-identical, 0 approvals, 3 still queued |
| `one-pager --no-post`, database | 40 lines, exit 0, every file byte-identical |
| `one-pager --grid` | Prints its path, exit 0, writes only the grid, no outbox message |
| `one-pager --grid --no-post` | Prints the grid's path, exit 0 |
| `one-pager` | Exit 0. One message of 587 characters, one 1200 px PNG, the `.html` beside it with 0 `<script` |
| `one-pager`, real `BEGIN EXCLUSIVE` held 90 s | **Exit 0 in 48 s, then 45 s on a second run.** One message with the picture, "Not available" throughout, `one_pager.upkeep_skipped` in the mirror |
| `one-pager`, real `BEGIN IMMEDIATE` held 90 s | **Exit 0 in 5 s.** One message with the picture |
| `one-pager`, wrong Chrome path | No file. Ends "(The picture couldn't be drawn: Google Chrome not found at …)", and `one_pager.picture_failed` is logged |

The lock runs leave about 12 to 15 seconds of Dispatch's 60, before a real upload's time, which these runs don't include. `code-review-final-2.md` notes that a lock and a Discord rate limit together could pass 60. Dispatch would then report a failure on a post that went out. I record this as a limit, not a defect. It doesn't affect the scheduled job.

**The search for old times (SC7),** `git grep` over README, `CONTEXT.md`, docs, prompts, config, `.env.example`, the setup guides and `jura_growth`, read line by line:

| Old time | Finding |
|---|---|
| 06:30 | `scout-research`'s new time only |
| 07:00 | `app-factory`'s new time only |
| 07:30 | `social`'s new time only |
| 08:00 | `community`'s new time; the AI OS brief (`CONTEXT.md:100`, `README.md:108`, `digest.py:6`), which stays; two timezone offsets in ISO timestamps in `docs/dispatch-contract.md` |
| 09:00 | The one-pager's new time; publish's window, which stays |

"14-day grid" appears only where the docs say it is no longer posted, or as `--grid`. "Publish window" appears nowhere in the code, tests, README or docs.

## Trace

Every test named here passed in this run's JUnit. Parametrised cases count separately, and a test can serve two rows.

| Row | Passed | Tests, not all | Fresh recorded case |
|---|---|---|---|
| MB1 | 27 | `test_the_verdict_counts_all_four_things`, `test_the_job_posts_one_message_with_the_picture_on_it`, `test_only_a_draft_on_a_draft_mode_platform_is_to_post_by_hand` | Renders; real post |
| MB2 | 6 | `test_every_font_is_at_least_21_px_in_every_fixture`, `test_the_page_holds_together` | PNGs 1200 wide; read at 550 |
| MB3 | 65 | `test_decide_lists_the_soonest_first_with_ties_by_id`, `test_a_missed_slot_line_holds_a_count_and_no_time`, `test_each_real_line_about_live_outreach_fits_its_fix_row_whole` | Renders; 26 wordings with real fonts |
| MB4 | 3 | `test_every_slot_status_has_a_word_and_a_token_colour`, `test_the_page_uses_design_system_tokens_only` | Renders |
| MB5 | 13 | `test_the_page_holds_together`, `test_the_worst_case_says_how_many_more_and_stays_under_the_maximum`, `test_a_quiet_day_has_no_large_blank_area` | `--live-fonts` |
| MB6 | 17 | `test_a_slot_with_no_trace_reads_by_how_long_ago_it_was`, `test_a_monday_community_slot_that_left_no_trace_reaches_fix_on_monday_and_the_day_after`, `test_no_slot_today_says_so_once` | None needed |
| MB7 | 29 | `test_a_plugin_whose_digest_raises_shows_dashes_not_zeros`, `test_a_recorded_zero_from_the_database_stays_zero`, `test_an_installed_job_with_a_run_on_record_never_reads_not_installed` | Bad-day renders. Sf2 noted |
| MB8 | 86 | `test_no_planted_value_reaches_the_page_the_file_or_the_message`, `test_hostile_text_is_only_ever_text_through_every_route`, `test_an_address_straddling_a_cut_is_masked_before_the_cut` | Saved page: 0 `<script` |
| MB9 | 6 | `test_the_page_is_saved_beside_the_picture`, `test_the_page_scrolls_to_its_footer_in_a_small_window`, `test_the_2330_backup_keeps_fourteen_days_of_pictures_pages_and_grids` | Real post wrote both |
| MB10 | 5 | `test_the_message_holds_the_header_verdict_counts_soonest_and_fix_lines`, `test_the_message_never_splits_from_the_picture` | Real message, 587 characters |
| MB11 | 5 | `test_when_the_picture_cant_be_drawn_the_long_text_posts_and_says_why`, `test_when_the_page_cant_be_saved_the_long_text_posts_and_says_why`, `test_no_post_still_writes_nothing_and_expires_nothing` | Wrong Chrome path; `--no-post` |
| MB12 | 4 | `test_grid_draws_its_file_prints_its_path_and_posts_nothing`, `test_a_normal_post_writes_no_grid`, `test_the_dispatch_contract_no_longer_says_the_one_pager_carries_the_grid` | `--grid` |
| MB13 | 3 | `test_the_read_calls_no_kinds_content_or_preview`, `test_a_healthy_database_is_read_once` | `--no-post`, byte-identical |
| SC1, SC5 | 16 | `test_each_morning_job_has_the_prds_time`, `test_nothing_else_moves`, `test_community_stays_weekly` | None needed |
| SC2 | 16 | `tests/test_outreach_raise_due.py`, `test_outreach_requests_is_a_quiet_command_job_of_the_outreach_agent` | `raise-due` in shadow. Live mode only through the doubles |
| SC3 | 3 | `test_an_email_queued_by_the_morning_run_gets_its_card_ahead_of_the_send_window` | None needed |
| SC4 | 8 | `test_every_morning_slot_ends_by_the_next_and_by_the_one_pager` | None needed |
| SC6 | 8 | `tests/test_scout_health.py`, `test_the_real_icp_line_reaches_the_page_with_no_absolute_path` | The real message puts the ICP line first |
| SC7 | 10 | `test_a_moved_jobs_own_files_no_longer_name_its_old_time`, `test_readme_lists_every_job_with_its_time` | The search above |
| End to end | 2 | `tests/test_morning_order.py` | None needed |
| Risks 1 to 5 | 78, 6, 1, 20, 1 | `tests/test_picture_privacy.py`; `test_a_job_that_didnt_run_stops_the_all_clear`; `test_it_posts_only_cards_and_no_run_update`, with SC2 and SC3; `test_the_job_posts_through_a_real_lock_held_throughout`, `test_a_lock_landing_after_the_post_never_posts_twice`; `test_every_registered_approval_kind_has_one_row` | Real locks |

**Tests QA named that no longer exist:**

- `test_a_draft_with_its_own_request_is_decided_not_posted_by_hand`, `test_more_social_requests_than_drafts_never_counts_below_zero` and `test_a_social_request_from_an_earlier_day_doesnt_offset_todays_draft` were removed by `d22924a`, when the `social_drafts_by_hand` figure replaced that arithmetic. `test_only_a_draft_on_a_draft_mode_platform_is_to_post_by_hand` and `test_a_card_for_one_platform_leaves_the_other_platforms_draft_to_post` hold the rule now.
- `test_the_whole_wait_leaves_dispatch_room_to_answer` is now `test_the_whole_wait_stays_inside_dispatchs_window`.

## Renders at 550 px, every word read

From b953955 with real fonts, resized to 550 px. All of it is legible, the captions included. This is a resized file, not Discord, which U1 checks.

**W, `full.png`, 1200×1548.**

- Verdict: "50 to decide, 20 to fix, 12345 to post by hand, 12345 replies to read." Then "Jura growth · Wed 25 Nov, as of 23:59 SGT".
- Decide in #approvals 50:
  - Outreach email A-9000, "Send to the company with the longest name…", Decide by Thu 26 Nov 00:59.
  - Social post A-9001, "Xxxxxxxx…", Decide by Thu 26 Nov 01:00.
  - Community post A-9002, "新加坡贸易有限公司新加坡贸易有限公司新加…", Decide by Thu 26 Nov 01:01.
  - Group join A-9003, "Send to the company with the longest name…", Decide by Thu 26 Nov 01:02.
  - and 46 more.
- Fix 20:
  - "Build handoff waiting for a builder: APP-000 xxxxxxxx…".
  - APP-001, APP-002 and APP-003, each "Send to the company with the longest name we could find, which has a…".
  - and 16 more.
- This morning: all five Skipped. Scout "…longest name we could find…"; the others "…longest nam…". Outreach 8 to approve, Social 7, Community 21, App factory 14, which add up to 50.
- Yesterday: 12345 emails sent, 12345 replies, 12345 social posts, US$12,345.67 Claude spend. "12345 unsubscribes, 12345 bounces, 12345 complaints, 12 lapsed unanswered".
- Later today: Posting window 00:00–00:01, Send window 00:00–00:01, Digest 00:00–00:01.

Nothing runs together or is clipped. Only clamps end in an ellipsis.

**Q, `quiet.png`, 1200×894.**

- Verdict: "Nothing needs you right now." Then "Jura growth · Tue 10 Nov, as of 09:00 SGT".
- Decide in #approvals 0, "Nothing waiting for you." Fix 0, "Nothing broken."
- This morning, all Ran: Scout "0 new leads kept"; Outreach "0 emails queued"; Social "0 drafts waiting"; Community "0 posts planned"; App factory "No new PRD".
- Yesterday: 0 emails sent, 0 replies, 0 social posts, US$0.00 Claude spend.
- Later today: Nothing else scheduled.

There is no gap. Later today is empty because this fixture holds no later slots.

**B, `bad-day.png`, database locked, 1200×943.**

- Verdict: "1 to fix." Then the same overline.
- Decide in #approvals –, "Not available: growth.db has an unfinished write".
- Fix 1, "Send `/growth status` to clear it: growth.db has an unfinished write."
- This morning: all five "Not available", with no second line.
- Yesterday: four dashes over emails sent, replies, social posts, Claude spend.
- Later today: Not available.

No zero appears, and no "Not today".

## To turn a NO-GO into a GO

This doesn't apply as graded. If Sf2 is regraded as major:

- Have `_abandon_stale` finish the row with the status in the mirror's `run.database_locked`, or record an explicit acceptance that names it as major.
- Rerun criterion 2.

If criterion 6 is held to its letter:

- Drop the two comment lines' added words from `tests/test_mission_health.py`, or amend the criterion by ruling.
- Rerun criterion 2.

## Waivers the user may grant at G4

None is needed on my grading. Merging accepts all of these:

- Sf2 as minor, and the `EXCLUSIVE`-lock trade, both ruled by the conductor rather than Ting Yu. The crew log records them under the standing instruction.
- The comment exception in criterion 6.
- UAT U1 to U7, which run after merge and don't gate, by criterion 11.
- PRD §7 reads "not signed", proceeding under the standing instruction, with merge as his acceptance. No exit criterion tests this. I record it so the merge is made knowing it.

## Not tested, beyond the strategy's list

- The full suite on the merge with `origin/main`. Only the three doc-reading test files ran there.
- A real upload's time inside Dispatch's window, and Dispatch's own timeout.
- `jura-growth run`, which is forbidden. The job path ran only in process, inside the suite.
- The `remote` path with real waits.
- `outreach raise-due` in live mode through the real command. Doubles cover it.
- A paused `digest` under a real `EXCLUSIVE` lock on this commit.

## Boundaries, as they went

- Nothing posted: no webhook was set and Discord was off. Nothing called Resend. `jura-growth run`, `schedule install` and `schedule render` were never typed.
- The full suite calls `schedule.render` itself under `conftest.py`'s temp folders, as earlier reviews recorded. The newest plist in `~/Library/LaunchAgents` is still dated 29 October.
- Beyond the commands the brief named, I ran `jura-growth one-pager` without `--no-post` on temp data, so the message went to a temp outbox. The temp `scout.yaml` was set to `mode: shadow`, because the committed one is live.
- Chrome fetched Google Fonts for the live-font runs and the `one-pager` runs. The pages hold only synthetic data and stayed on disk.
- I did not open the live `growth.db`. The newest file in the live `one-pager` folder is still from 30 October.
