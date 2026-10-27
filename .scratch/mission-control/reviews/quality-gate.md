# Quality gate: mission control and browser publishing

QA lead, 2026-10-27, 07:46 to 08:10 SGT. One gate for both features, on their shared branch.

```
Decision: NO-GO
Branch: crew/mission-control @ 0354503 (into main @ 855e48c, the merge-base)
```

**What this gate judges.** Merging this branch into `main`, not going live. The code ships with
everything outward switched off, and nothing is scheduled. Ting Yu's setup tickets (mission-control
13 to 16, browser-publishing 01) and the live UAT steps come after the merge. Turning each thing on
waits for them.

**Why it is NO-GO.** The criteria in test strategy v3 section 11.1 were written for the release.
Six of the fourteen don't hold at `0354503`. Four of the six can be cleared by the crew today, or
waived at G4. The other two, plus parts of E1 and E2, can only be met by Ting Yu's live steps, or
deferred by him in his own words. The code itself passed everything that can be tested on this Mac:
a fresh suite (twice), the structure greps, the caps, the typecheck baseline, the defect count and
the final code review.

## Exit criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| E1 | Dependencies | **not met** (live-only part) | Met: `main` (855e48c) is the merge-base and an ancestor of HEAD; `1662793` is an ancestor of `main`; every agent ticket's blockers are merged (crew-log merge entries through 8d6640e). Not met: BP-03's `Blocked by:` names BP-01 (Ting Yu's, `ready-for-human`, not done), and BP §5.1 still lists U10, U11 and U18 as open (PRD lines 425-427). Only BP-01 can meet this. The conductor decided on 2026-10-27 at 03:51 that BP-01 gates live posting rather than the build. That is a decision about scope, and the criterion's wording doesn't follow from it. |
| E2 | Every row traced | **not met** | `reviews/qa-release.md`: of 170 ids, 168 are traced to passing node ids. **G34** has no test: the generated test over `headless.leaves(cli)` doesn't exist. My own walk found 77 leaves, none taking both a kind and a subject, and the 7 `approvals.request(` call sites all sit behind A11's raisers. **G38** is tested on the fake kind's pending record only, not on every kind × D7 state. The refusal comes before any database is opened (`test_a_terminal_refusal_asks_for_nothing_and_opens_no_database`), so the risk is low, but the case isn't covered as written. **Manual parts not recorded (live-only):** AC-M7.5 U16, AC-M8.11 U17, AC-M14.1 U4, AC-P9.4 U11, AC-P11.1 R6. |
| E3 | Fresh suite | met | Two runs at 0354503: 3305 passed, 0 failed, 0 errors, 0 skipped (137.6s and 140.1s). `main` at the branch point collects 987. |
| E4 | Fixtures prove themselves | met | All six are named with their assertions in `qa-release.md` ("Fixtures that prove themselves"), and all passed. |
| E5 | Nothing touched | **not met** (timing clause only) | The run was bracketed 07:48:21 to 07:50:42 SGT, which is outside both allowed windows (18:30 to 23:15 and 00:00 to 06:15). Everything else holds. `git status --short` was empty before and after. A stat-only snapshot of 122 paths under `data/growth/`, `outputs/growth/` and `repos/landing-page/.git/refs/` was identical. `pgrep -f "jura-growth run"` printed nothing before or after. `launchctl list` shows no growth job loaded, and `~/Library/LaunchAgents` has no growth plist. |
| E6 | Structure holds | **not met** (setup-guide copies) | Negative greps: all hold. `mission.py` has no writer, lock or journal call; no core module imports an agent; `origin.py` reads only `SSH_ORIGINAL_COMMAND` and `CLAUDE_MARKERS`; only `remote.py` reads `obj["origin"]`; there is no Terminal origin and no code prompt; `bin/growth-remote` and `remote.py` use no shell; no plug-in migration has decision columns. Two greps were read past their literal hits. (1) `taskwise`/`zenexflow`: no added line in `jura_growth/`, `bin/`, `tests/`, `config/` or `prompts/` names either. The raw hits are the "Jura only" rule lines already on `main`, `.scratch/` docs (this strategy among them), and one added separation instruction in `setup/morning-brief.md`. (2) `--chrome`: the only code line is `runner.py:302`, inside the `BROWSER_JOBS` branch; `runner.py:262` and `publish/job.py:27` are a docstring and a comment. Positive greps: the drafts in `.scratch/mission-control/setup/` pass. At the release gate, though, the strategy checks the copies in `outputs/growth/setup/`. There, `discord.md` and `morning-brief.md` are the 2026-10-24 versions without `#mission-control` or the removal step, `remote-control.md` is missing, and `browser-publishing.md` was never drafted anywhere. |
| E7 | Caps | met | `caps.py` defines `BROWSER_JOBS = frozenset({"publish"})`, `COMMUNITY_POSTS_PER_DAY = 1`, `COMMUNITY_JOINS_PER_WEEK = 3`, `PUBLISH_ITEMS_PER_RUN = 1`, `PUBLISH_MINUTES_BETWEEN_ACTIONS = 20`, `PUBLISH_WINDOW = ("09:00", "18:00")` and the deadline maxima. `git diff main...HEAD -- jura_growth/caps.py` removes only the module docstring line, and raises no value. |
| E8 | No new runtime dependency | met | `git diff main...HEAD -- pyproject.toml` is empty. |
| E9 | Defects | met | No defect ticket exists in either `issues/` folder. That makes 0 critical and 0 major open; the 7 minor follow-ups are listed below, each with an owner. |
| E10 | Code review | **not met** | `code-review-final.md`: approve-with-follow-ups, with no blocker. Its should-fixes were merged in 8d6640e, with tests. Every review records a security pass. But eight ticket reviews end on changes-requested, with no later reviewer round: mc 02 (round 2), 04b, 06, 08, 10 and 10b, and bp 03 (round 2) and 04. The conductor verified each fix round with the reviewer's repros; for bp 04 it was the developer's repro output. Every blocking finding in those eight now has a passing regression test, listed below. mc 04 does end on approve (round 2, line 131), so the release review's count of nine is one too many. |
| E11 | Typecheck (advisory) | met | `pyright --pythonpath .venv/bin/python jura_growth`: 70 errors at HEAD against 76 on `main` (exported copy), and 0 in new modules. `agents/outreach/send.py` went from 2 to 3. |
| E12 | ADRs | met | 0001 to 0005 each start `Status: accepted`. |
| E13 | Manual steps | **not met** (live-only) | No U or R step is recorded as passed, and none is waived. It needs Ting Yu: mission-control 13 (U1 to U5), 14 (U7, U16), 15 (U17, then U6), 16 (U8); BP-01 (U9, U10, U11, U18); then R1 to R6 (bp 07 stays open on R1b), and U12 to U15. |
| E14 | Live outreach stays off | met | `config/settings.yaml`: `discord_buttons`, `post_buttons` and `dispatch_builds` all `false`. `git diff main -- config/scout.yaml` doesn't touch `mode` (still `shadow`). Also off in the shipped config: every platform `publish_mode: draft`, and `community.yaml` `browser: false`. |

### Criteria only Ting Yu's live steps can meet

- **E13**, in full.
- **E2's manual parts:** U16 (AC-M7.5), U17 (AC-M8.11), U4 (AC-M14.1), U11 (AC-P9.4) and R6
  (AC-P11.1).
- **E1's BP-01 clause:** BP-01 done, and U10, U11 and U18 recorded in BP §5.1.

None of these can be produced by the crew. For a merge-only release, the expected route is a G4
deferral in Ting Yu's own words, which E13 requires. Each step then becomes the gate for turning on
the thing it checks:

| Before turning on | These must be recorded as passed |
|---|---|
| `approvals.post_buttons`, then `approvals.discord_buttons` and live outreach | U17, then U6 |
| Any platform's `publish_mode: browser`, or `community.browser: true` | U9, U10, U11, U18, then R1 to R4 and R6 (with R1b for bp 07), then U12 (U13, U14 and U15 per platform and per group step) |
| `approvals.dispatch_builds` | U8 |

## Fresh run

- `uv run pytest -rs -p no:cacheprovider -o addopts=""` (with `JURA_ROOT` set and temp
  `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`) -> 3305 passed in 137.63s, exit 0, no skip
  lines.
- The same command with `--junitxml`, bracketed by E5 snapshots -> 3305 passed in 140.12s, exit 0.
  The JUnit file has 3305 cases and all of them passed. The snapshots were identical.
- `pytest --collect-only` on an exported `main` (855e48c) -> 987 tests.
- `pyright` at HEAD and on exported `main` -> 70 and 76 errors; 0 in new modules.
- E6, E7, E8, E12 and E14 checks -> as in the table.
- A walk over `headless.leaves(cli)` -> 77 leaves, none taking both a kind and a subject (G34).

No sends, posts, Discord or network calls were made. No launchd job was touched. Nothing was
committed.

## Open defects: 0 critical, 0 major, 7 minor

None of these blocks the merge.

| # | Severity | What | Owner |
|---|---|---|---|
| 1 | minor | St4: repeated per-kind switches on publish item kinds (`code-review-final.md`) | developer, follow-up ticket |
| 2 | minor | St5: the `app-build` use-by is written but never reached | developer, follow-up ticket |
| 3 | minor | St6: the `NotApproved` reasons don't match its docstring | developer, follow-up ticket |
| 4 | minor | St7: "publish window" wording; three time formats reach Discord | developer, follow-up ticket |
| 5 | minor | Sp4: the schema still accepts a `terminal` origin, and `use()` doesn't check the origin (defence in depth; a new migration) | developer, follow-up ticket |
| 6 | minor | `agents/outreach/send.py` has one more pyright error than on `main` (the total fell) | developer, follow-up ticket |
| 7 | minor | No ticket's `Status:` line moved past `ready-for-*`, so the merged ones still read `ready-for-agent` | conductor |

Known limits accepted earlier, not defects: personal-profile joins can't be made impossible in code
(crew-log, 2026-10-27, 05:56); posts held for admin approval stop as unidentified until U14 shows how
often it happens (06:51).

### Regression tests for the eight reviews without a closing approve (E10)

| Review | Blocking finding | Passing regression test |
|---|---|---|
| mc 02 (round 2) | own copy stopped masking a learned first name | `test_privacy::test_jura_s_own_copy_still_loses_a_learned_first_name` |
| mc 04b | an orphaned `expect` could record a Terminal decision | `test_origin_processes::test_the_orphaned_expect_probe_is_refused` (4 cases) |
| mc 06 | email built before the claim, sent bytes not compared; unbounded retries; NFC | `test_outreach_claim_bytes::test_the_email_sent_is_the_one_the_claim_checked`, `::test_the_window_closes_before_resends_24_hours`, `::test_drafts_that_only_normalise_alike_do_not_match` |
| mc 08 | one-pager window lost seconds at 08:00:05 | `test_mission_read::test_the_scheduled_one_pager_running_late_still_reports_since_the_one_before` |
| mc 10 | handoff SHA read after the claim | `test_app_builds::test_a_prd_edited_between_the_claim_and_the_handoff_is_never_handed_out`, `::test_dispatch_sees_the_handoff_only_after_the_claim_commits` |
| mc 10b | `--preview` accepted Markdown, so a masked link could reach the card | `test_app_releases::test_built_refuses_what_it_cannot_bind_or_show_safely` (23 cases), `::test_the_card_shows_the_preview_as_plain_text_and_says_it_follows_the_branch` |
| bp 03 (round 2) | page or model text in the run row and alerts; fragmented typing; nested JSON made the audit fail open | `test_publish_run::test_a_fail_line_after_a_clean_post_is_withheld_everywhere`, `test_publish_audit::test_text_typed_one_character_at_a_time_is_judged_as_a_whole`, `::test_typing_before_the_claim_fails_even_the_approved_text`, `::test_deeply_nested_json_in_page_text_never_raises`, `test_publish_run::test_a_json_bomb_on_the_page_still_fails_unapproved_typing_and_pauses` |
| bp 04 | the audit used every enabled platform's hosts, not the claimed one's | `test_publish_run_instagram_linkedin::test_an_instagram_item_posted_on_another_enabled_platform_fails_the_run_and_pauses`, `test_publish_join_run::test_the_audit_takes_its_hosts_from_the_claimed_item_never_every_enabled_platform` |

## To turn this NO-GO into a GO (merge into main)

The crew can clear these today, with no live step:

1. **E10.** A reviewer rechecks the blocking findings of the eight reviews above at the merge SHA,
   using the regression tests listed, and appends an approve round to each file.
2. **E2 (automated).** A developer adds two tests. First, a generated test over
   `headless.leaves(cli)` that no leaf takes both a kind and a subject, plus an allowlist of the
   `approvals.request(` call sites (G34). Second, the Terminal refusal parametrised over the nine
   gate adapters × the D7 states, for `approve` and `skip` (G38). Then the QA lead updates
   `qa-release.md`.
3. **E6.** Draft `.scratch/browser-publishing/setup/browser-publishing.md` (bp 01 step 1). Then copy
   the four guides to `jurasolutions/outputs/growth/setup/`, and re-run the four positive greps
   there.
4. **E5.** Re-run the bracketed suite at the merge SHA between 18:30 and 23:15 SGT, or between
   00:00 and 06:15. If items 1 to 3 add commits, re-run it at the new SHA anyway.

Only Ting Yu can clear these:

5. **E13, E2's manual parts and E1's BP-01 clause.** Either run the steps, or, at G4, defer them in
   his own words to the go-live gates in the table above.

## Waivers the user may grant at G4

- **E13, E2's manual parts and E1's BP-01 clause:** defer them to go-live, on the condition that
  nothing in the "Before turning on" table is switched on until its steps are recorded.
  *Recommended: grant.* The merge changes nothing outward: every switch is off and no job is
  installed.
- **E10:** accept the conductor's verification plus the final review instead of eight reviewer
  rounds. *Recommended: grant* (the release review recommends the same). Every blocker has a
  passing regression test, and the final review found no blocker in the whole.
- **E5's timing clause:** accept this morning's run. *Recommended: grant.* No growth job is loaded,
  so no scheduled run could have overlapped, and the snapshots were identical.
- **E6's copy clause:** let the release persona copy the guides after the merge, as the release
  review plans. *Recommended: grant only once `browser-publishing.md` is drafted*, because BP-01
  can't start without it.
- **G34 and G38:** accept the gate's structural evidence instead of new tests. *Recommended: don't
  grant.* Both tests are small, and G38 guards the one decision path left.

If Ting Yu grants all of the recommended waivers and items 2 and 3 are done, every exit criterion is
either met or waived, and the call becomes GO.

## Notes for the strategy (QA lead's own follow-up)

E6's `taskwise`/`zenexflow` grep matches the strategy file itself, and the `--chrome` grep matches
comments. I'll restrict both to code lines in shipped paths. E2 also assumed a `qa-NN.md` per
ticket, and the build never produced one. From here on, the conductor's merge step should ask for
one.
