# QA final: approvals first, feeds after, social depth

*QA engineer, 2026-10-31, at `f0db1e5` on `crew/approvals-first-social-depth`. Checked against `reviews/test-strategy.md` §7, `reviews/functional.md` §3 and `reviews/uat.md`.*

## Summary

- **Not ready for G4 as it stands: one major defect is open.** A typed approval of a refused card goes through, and the post is handed to the browser (ticket 09, the final review's SP-B2). I reproduced it in separate processes.
- **Every other acceptance check passes,** at its automated seam and in a walk through the real `jura-growth` commands. No critical defect. Four minor defects are filed, each with an owner and a failing test (tickets 05, 06, 07 and 08). Ticket 05 is minor by the strategy's definition, but it is also the final review's blocker SP-B1, so it has to be fixed before merge either way.
- **The intermittent failure is named.** It recurred once in 9 full runs: `tests/test_uat_seed_outreach.py::test_every_scenario_refuses_the_live_folders_and_changes_nothing[note-rules]`. The live publish job wrote its run log during the test, so the test failed. No product behaviour is wrong and the test wrote nothing to live data. Ticket 08. The other 8 runs were clean.
- **X9 is met, so no waiver is needed for it:** the web-font matrix passed 34 of 34.
- **Not met:** X12 (ticket 09 is open) and X13 (the final review requests changes). X5 and X6 don't pass as worded either: they print lines their checks say should be absent. I read each one and no rule moved, so the gate has to rule on those two. X15 is the one waiver for G4.
- **`main` moved during this QA, and the branch no longer merges cleanly.** `origin/main` went from `68a1911` to `c11eb61` (PRs #18 and #19). A trial merge conflicts in `CONTEXT.md`, `README.md`, `docs/scout.md`, `jura_growth/discord.py`, `jura_growth/health.py`, `jura_growth/mission.py` and `tests/test_mission_health.py`. Three of those are code this change relies on, so **this evidence is for `f0db1e5` only**. X1 to X8 need rerunning after the merge.

## Exit criteria

| # | Verdict | Command | Result |
|---|---|---|---|
| X1 | **Met, with one named intermittent failure** | `uv run pytest -rs -p no:cacheprovider -o addopts=""` with worktree exports, a stand-in `claude` first on `PATH` | 5167 passed, 0 failed, 0 errors, no `SKIPPED` line in 8 of 9 full runs. The floor is 3980. The ninth had 1 failed: ticket 08, a test racing the live engine. A gate rerun can hit it too, and the ticket says how to read that |
| X2 | **Met** | Parsed the runs' junit files for the named tests (section "Trace") | All 18 criteria name passing cases |
| X3 | **Met, one change listed** | Appendix A script | `same` 23 times. `CHANGED tests/test_social.py test_hashtag_limits_and_position`: Instagram's cap fell from 8 to 5 (technical N9, PRD "Amended 2026-10-31"). Its assertions are the same shape at the new number |
| X4 | **Met** | Read each diff, then checked each name in junit | See "Classes A and B" |
| X5 | **Not met as worded; no rule lowered** | The grep in X5, and `git diff main...HEAD -- tests \| grep -nE '^\+.*(pytest\.skip\|mark\.skip\|skipif\|xfail\|importorskip)'` | The first prints 5 lines. All are a parametrize argument named `words` (a list of words, not a theme's range): `test_approvals_first.py:253`, `test_card_readability.py:23` and `:33`, one in `test_schedule_drift.py` (`("hours", "words")`), one in `test_uat_seed_script.py` (`commands()`). The second prints nothing. The gate should read the check's `words=` part as the config key |
| X6 | **Not met as worded; no behaviour changed** | The two diffs in X6 | `approvals.py`: 3 constants added and 4 string literals replaced by them, with the same values. `caps.py`: a comment only, no limit moved. `tests/gate_adapter_social_post.py`: 4 lines deleted, all under `[B2]`: the docstring's "posting window" wording, the `limits` import line, and `pw.limits_window(day)` with `now < closes`, replaced by `now < limits.decide_by_on(day)`. Code review 02 had already said QA must list these. No waiver covers X6, so the gate has to rule on it |
| X7 | **Met** | `find` over `inputs` and `design-system` newer than `a6c2cca`'s time; `git diff --name-only main...HEAD \| grep '^data/'` | Both print nothing |
| X8 | **Met** | Junit, and the record below | The PC3 file passed with no skip. A literal `grep -c 'offline=True'` on the test file gives 0, because every render goes through `card_probe.probe`, whose default is `offline=True`. `test_a_render_in_the_suite_cannot_reach_the_network` asserts the resolver rule. Matrix below: 34 of 34 pass |
| X9 | **Met** | `x9_matrix.py`, the same cases and probe with `offline=False` | 34 of 34 pass, all three web fonts loaded for each card. See "Real fonts" for what Chrome fetched |
| X10 | **Met** | `crew-log.md` G2 and G3; junit | Every blocker is recorded as taken. Named passing cases are in "Trace". S9 took the conductor's stricter ruling (a post the mask would change is refused), recorded in the log at ticket 02 |
| X11 | **Met** | `grep -nE '60–120\|50–120\|One or two sources\|copies it from' prompts/social.md docs/social.md` | Prints nothing. `test_social_prompt.py` passes |
| X12 | **Not met** | This report; `issues/test_qa_final_defects.py` | 0 critical, **1 major open (ticket 09)**, 4 minor with an owner (tickets 05, 06, 07, 08) |
| X13 | **Not met** | Read each `code-review-*.md` | `code-review-final.md`, which appeared while this QA ran, ends "Verdict: changes-requested" with two open blockers: SP-B1 (ticket 05) and SP-B2 (ticket 09). `code-review-03.md` approves. `code-review-01.md` and `-02.md` end with changes requested, and the final review confirms their later fixes hold, apart from SP-B2 |
| X14 | **Met** | The commands below | No `jura-growth run`, `schedule install`, `schedule render` or real send. `uat.md` was dry-run: see "UAT dry run" |
| X15 | **Waiver for G4** | - | Parts P to C have not been run by Ting Yu, and Part L can only run after merge. His G4 answer decides this. The PR body must open with "What merging switches on" and name the parts not run |

**Waiver for G4: X15 only.** X9 no longer needs one.

## The intermittent failure

Ticket 02 saw one unnamed failure in one full run. Every run here keeps failure names through `-rfE` and a junit file.

| Run | Order and clock | Result | Time |
|---|---|---|---|
| `run1` | In order, real clock, Saturday night | 5167 passed | 432s |
| `run2` | In order, real clock | 5167 passed | 453s |
| `run3` | In order, real clock, competing with other runs | 5167 passed | 724s |
| `shuffle1b` | Shuffled, seed 20261031 | 5167 passed | 481s |
| `shuffle2` | Shuffled, seed 7 | 5167 passed | 376s |
| `clock-tue-1000` | In order, clock from Tuesday 10:00 | 5167 passed | 478s |
| `clock-tue-1658` | In order, clock from Tuesday 16:57, crossing the 17:00 decide-by | 5167 passed | 397s |
| `clock-tue-2358` | In order, clock from Tuesday 23:58, crossing midnight | 5167 passed | 260s |
| `midnight` | In order, real clock, 23:56 to 00:00:05 | **1 failed**, 5166 passed | 245s |

Besides the in-order runs:

- **Order.** `pytest-randomly` isn't installed, so a throwaway plug-in in the session scratchpad shuffles the collected tests from a seed. The Chrome file stays together because its module fixture takes about 14 seconds to rebuild each time it is split up. My first shuffled attempt didn't keep it together, and I stopped it partway as too slow: no failure in the tests it had reached.
- **Load.** Two runs were deliberately left competing with other runs and with real Chrome renders.
- **Time of day.** All in-order runs fell on a Saturday night, so a test reading the real clock would never see a weekday or the posting window. A second throwaway plug-in starts the suite's clock at a chosen time, and it ticks from there. Tests that pin `JURA_GROWTH_NOW` are unaffected.
- **Midnight.** One run on the real clock crossed midnight SGT.

**The failure:**

```
FAILED tests/test_uat_seed_outreach.py::test_every_scenario_refuses_the_live_folders_and_changes_nothing[note-rules]
tests/test_uat_seed_outreach.py:381: assert untouched_snapshot() == before
{'.../jurasolutions/data/growth/runs/2026-11-01.jsonl': (False, 349, 1793462402620496874)} != ...
```

**The cause.** The test stats the live `data/growth/` before and after each case and excuses only `growth.db` and `locks`. The live engine also writes `runs/<day>.jsonl` and other files there. The mtime is 00:00:02.62, and the file's first two lines are the live `publish` job's `run.quiet` and the live one-pager's `run.start`, both at 00:00:02. Those two lines are exactly the 349 bytes in the diff. The jobs fire at 00:00 because of the 9-hour offset SC1 reports.

**It wasn't the test writing to live data.** Line 380 had already asserted the seed refused with exit 2. Run alone straight afterwards, all 36 cases of the two tests that take this snapshot pass, in 3 seconds. They run for about 3 seconds in each suite, which is why a hit is rare.

**How sure I am it is ticket 02's failure.** That run kept no name, so I can't prove it. It fits, nothing else failed in any run, and neither order nor time of day made anything fail. `ENGINE_CHURN` is the same on `main`, so this predates the branch. Ticket 08 has a test that goes red every time, using stand-in folders, and a recommended fix.

## Acceptance criteria

Automated cases are from junit, in the runs above. "Walk" means I drove the real `jura-growth` commands in a temp folder and read the messages. Discord was a recorder on `127.0.0.1`; see "How the walk ran".

| AC | Automated cases passed | Walk | Result |
|---|---|---|---|
| AF1 | 4 named | Two cards. A 280-word post splits into 2 pieces, fences balanced, status line and image on the first, answer line on the last. Instagram's images in order. #social-drafts empty. No hand-post phrase in any message. **Negative case fails:** a refused card can still be approved by typing (ticket 09) | 2 of 3 pass, 1 major |
| AF2 | 9 | Approve at 16:59 and 16:59:30: claimed 17:00 and 17:20. 16:59:59 approves. 17:00:00 and 17:01 answer `expired`. A claim at 17:59:59 works and 18:00:00 refuses. Unapproved or paused: nothing handed out | 2 of 2 pass |
| AF3 | 4 | No `page_url`, submit at 17:00, and no images each give a note and no card. 16:59 still gets cards. No "by hand" | 2 of 2 pass |
| AF4 | 6 | Not walked, because it needs `jura-growth run` (X14). `test_a_late_run_on_the_shipped_config_skips_before_claude_starts` runs it with a fake binary | 1 of 1 pass |
| AF5 | 4 | Facebook draft, Instagram draft, both draft: hand-post text only for the draft platform. Rollback with a card open: nothing posts (ticket 06 on its line) | 2 of 2 pass, 1 minor |
| FD1 | 13 | One line on the mapped channel for each row in "Feed lines" | 2 of 2 pass |
| FD2 | 4 | Changed content: no line, with or without a successor. A claim: no line | 2 of 2 pass |
| FD3 | 2 | `app-build` approved: one line, none at later sweeps | 2 of 2 pass |
| FD4 | 5 | Feed answering 500: the decision stands, the card moves on, the line goes to the outbox. Feed taking 30s: the decision returns in 6.1s. Edit failing: one follow-up and still one line | 2 of 2 pass |
| DP1 | 17 | A 15-word Facebook post: "160–280 words here; this is 15". 288 words refused | 2 of 2 pass |
| DP2 | 3 | One source and one host each refused, exit 2. Two hosts pass | 2 of 2 pass |
| DP3 | 9 | 2 items refused, 3 on a Tuesday give 4 images, 4 give 5, cover first. 5 on a list give cover plus 4. 5 on a headline card refused ("at most 4") | 2 of 2 pass |
| DP4 | 23 | Prompt only. Whether a post has insight is Ting Yu's judgement in UAT L3 | 1 of 1 pass, the judgement open |
| DP5 | 2 | Every shortfall: exit 2, `social_submissions` unchanged. A word miss: "attempt 1 of 2", one row | 2 of 2 pass |
| PC1 | 16 | Flow, compare and figure drawn. 62% has a ring; 120% and 3.5x don't. Items have icons | 2 of 2 pass |
| PC2 | 92 | `rocket` and `../../etc/passwd` refused. "Leverage" refused at both `submit` and `render`, with no PNG. HTML in a label comes out as literal text | 2 of 2 pass |
| PC3 | 53 | Matrix below, both font sets, every PNG viewed | 2 of 2 pass |
| SC1 | 4 named of the file's many | `drift`: "about 9 hours off... Restart the Mac once" under Needs you. `late-wake`: no line | 2 of 2 pass |

### Feed lines, as read

| Kind, channel | Approved | Skipped | Expired | Superseded, no replacement | Superseded, replaced |
|---|---|---|---|---|---|
| `social-post`, #social-drafts | "It goes out on a publish run today, by 18:00 SGT. The run's update here gives the post's address." | One line | "Not approved in time." or "Approved but not used in time." | `social skip`: "The request closed: skipped by hand." `page_url` removed: "The request closed: the item is gone." | Image bytes changed, pending or approved: card "Superseded: the post changed", **no line**, new card |
| `outreach-email`, #outreach-sent | "It goes out on a send run, inside the send window and the day's caps." Then one "**Sent**" message and no second approved line | One line | "Not approved in time." | `outreach suppress`: "The request closed: address suppressed." | Draft edited: **no line**, new card at the next `send-due` |
| `app-build`, #app-factory | "Handed to Dispatch: it builds APP-101 on its own branch from main." Once | One line, PRD moved with "Skipped by Ting Yu on..." on top | "Not approved in time." | PRD removed: "The request closed: the PRD left prd/pending/apps/." | PRD edited: **no line** |
| `app-release`, #app-factory | "Next: `/growth apps release-plan APP-101` prints the merge of exactly this commit." No line on the claim | One line | "Not approved in time." | Build no longer waiting: "The request closed: the build is no longer waiting for a release." | Preview changed: **no line** |
| `group-rules`, #community | With its days: one line, no next step. Without them: refused, as designed | One line | "Not approved in time." | Group removed: "The request closed: the group was removed." | Rules changed: **no line**, new card when the rules are noted again |
| `community-post`, #community | "It goes out on a publish run, inside the posting window." (ticket 06) | One line | "Not approved in time." or "Approved but not used in time." | Group removed: "The request closed: the group was removed." | Text changed: **no line**, new card at the next `publish next` |
| `group-join`, #community | Same wording as above | One line after its approved line | "Approved but not used in time." | Group removed: "The request closed: the group was removed." | Not walked: `tests/test_feed.py` covers this path with a fake kind. My changed address failed the address check, so it read as gone, with one line |

The superseded cells for `app-release`, `group-rules`, `community-post` and `group-join` were reached by editing rows in the temp database, as the seed's `edit-draft` does. A pending `group-join` lapsing is in `test_feed_real_kinds.py`, because the seed only leaves it approved.

Lines carry flags 4100 (no link preview, silent) and `allowed_mentions` empty. A named address on a line is masked per `tests/test_feed.py`.

### The specifics in the brief

- **The digest's words after a card expires.** The cards, the feed lines and "Publishing: 0 posted, 0 skipped, 2 expired, 0 stopped" are right. "Social: 2 drafts with no card" and the brief's "2 social drafts waiting" are false: ticket 05, the final review's SP-B1.
- **The 18:05 upkeep.** `config/settings.yaml` has `digest` at `{daily: "18:05"}`. At 18:05 the digest writes the lapses first, even under `pause all`. A second digest at 18:06 adds no line and no post. If the Mac is off then, the next morning's one-pager closes them, with the same one line each. A publish run's `publish next` closes them earlier if it runs after 17:00.
- **No images, no card.** With Chrome missing: both platforms get a note in #social-drafts, a render alert goes to #alerts, no request and no item exist, and `publish next` has nothing due. No hand-post words.
- **A long post's card.** Pieces of 1874 and 369 characters, each with balanced fences. The image and the status line are on the first. The edit keeps the first piece well formed at 1873 characters. With shipped `post_buttons: true`, buttons go on the first piece only, and the edit sends `components: []`. One 280-word paragraph: a 275-character first piece holding the header and image, then the text whole in the second. Every non-blank line of the post appears in order (`test_a_280_word_post...`).
- **The five-slide carousel.** `social submit` with 4 items gave 5 images. The card said "5 images attached, posted in this order." `publish next --json` handed out `1-instagram-1-of-5` to `5-instagram-5-of-5`. Those exact paths through the audit's own transcript fixtures:

  | Uploads in the transcript | Audit |
  |---|---|
  | All five, one call | No failures, no warnings |
  | All five, one call each | No failures, no warnings |
  | 2 and 3 swapped | "out of their approved order" |
  | Four of five | "4 of its 5 approved images sent" |
  | The last twice | "image 5 ... more than once" |
  | None | "0 of its 5 approved images sent" |

- **Drift.** See SC1. The line says "Most likely launchd kept an old time zone", not a cause stated as fact.

## Real fonts (X9)

**What it fetched.** Each Chrome run went through a wrapper adding `--log-net-log`, which gave 141 net logs over the matrix and the news sample.

- **The page** requests only `fonts.googleapis.com` and `fonts.gstatic.com`: public font files, with no Jura data in the request.
- **Chrome itself**, on the throwaway profile each render uses, also calls its own Google services: `www.google.com`, `accounts.google.com`, `clients2.google.com`, `clientservices.googleapis.com`, `update.googleapis.com`, `www.gstatic.com` and `edgedl.me.gvt1.com` (variations, component updates, a time check).

So "fetches only public Google fonts" holds for the page and not for the browser. These are Google's own endpoints, carry nothing of Jura's, and every live render already makes them. No Jura, Meta, Discord or other host appears.

**The record.** The fallback set is `offline=True`, for X8. The web set is `offline=False`, for X9. All PNGs were viewed on contact sheets: no word is clipped or overlapping in either set's checks, and none in the web-font PNGs by eye.

| Case | Size | PNG | Fit, fallback fonts | Smallest type | Result | Fit, web fonts | Smallest type | Result |
|---|---|---|---|---|---|---|---|---|
| compare-2-full | 1200×630 | 1200×630 | 0.88 | 15.0 | pass | 0.88 | 15.0 | pass |
| compare-2-full | 1080×1350 | 1080×1350 | 0.96 | 20 | pass | 0.96 | 20 | pass |
| compare-2-short | 1200×630 | 1200×630 | 1.0 | 17 | pass | 1.0 | 17 | pass |
| compare-2-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| compare-3-full | 1200×630 | 1200×630 | 0.88 | 15.0 | pass | 0.88 | 15.0 | pass |
| compare-3-full | 1080×1350 | 1080×1350 | 0.88 | 20 | pass | 0.92 | 20 | pass |
| compare-3-long-word | 1200×630 | 1200×630 | 0.88 | 15.0 | pass | 0.88 | 15.0 | pass |
| compare-3-long-word | 1080×1350 | 1080×1350 | 0.92 | 20 | pass | 0.92 | 20 | pass |
| figure-no-ring-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| figure-no-ring-full | 1080×1350 | 1080×1350 | 0.88 | 20 | pass | 0.88 | 20 | pass |
| figure-ring-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| figure-ring-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| figure-ring-short | 1200×630 | 1200×630 | 1.0 | 15 | pass | 1.0 | 15 | pass |
| figure-ring-short | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| figure-ring-whole | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| figure-ring-whole | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| flow-3-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| flow-3-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| flow-3-short | 1200×630 | 1200×630 | 1.0 | 17 | pass | 1.0 | 17 | pass |
| flow-3-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| flow-4-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| flow-4-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| flow-4-long-word | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| flow-4-long-word | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| headline-only | 1200×630 | 1200×630 | 0.72 | 17 | pass | 1.0 | 17 | pass |
| headline-only | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| list-2-short | 1200×630 | 1200×630 | 1.0 | 17 | pass | 1.0 | 17 | pass |
| list-2-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| list-5-full | 1200×630 | 1200×630 | 0.68 | 15.6 | pass | 0.8 | 17 | pass |
| list-5-full | 1080×1350 | 1080×1350 | 0.76 | 22 | pass | 0.76 | 22 | pass |
| list-5-no-icons | 1200×630 | 1200×630 | 0.68 | 12 | pass | 0.8 | 13.6 | pass |
| list-5-no-icons | 1080×1350 | 1080×1350 | 0.76 | 18.6 | pass | 0.76 | 18.6 | pass |
| slide-full | 1200×630 | 1200×630 | 1.0 | 15 | pass | 1.0 | 15 | pass |
| slide-full | 1080×1350 | 1080×1350 | 0.92 | 20 | pass | 0.96 | 20 | pass |

**Seen by eye, not defects:**

- `figure-no-ring-full` at 1080×1350 squeezes its label into a narrow column beside `000,000.000x`. That value is at the field's limit; `62%`, `120%` and `3.5x` look fine.
- A maximum-length card is hard to read at phone width (390px): a flow's labels render at about 5px. The real samples read fine. This is Ting Yu's call in UAT P1.
- Carousel slides 2 onward leave their lower half empty. Clean, but plain: his call in P1.
- A list's fifth item appears on the cover only (functional note 6).

## One real news sample, end to end

A draft folder (`facebook.md` 243 words, `instagram.md` 179 words, `sources.md` with two hosts, `card.json` with a 62% figure and 4 items), through `jura-growth social submit <folder> --theme ai-news` with real Chrome and web fonts. The words are test data about an example survey, in a temp folder, and reached nothing live.

- **Delivered:** passed on attempt 1, with two cards in #approvals.
- **Images:** `facebook-1200x630.png` and `instagram-1-of-5` to `5-of-5` at 1080×1350, in Outfit, DM Sans and IBM Plex Mono.
- **Looked at each image:**
  - The ring fills to 62% with the figure inside it.
  - The label, "Source: Example Research" and the caption are all legible, on the card's grid.
  - Slides 2 to 5 lead with their icon, then "02 / 05 · AI NEWS", the title and the detail.
  - The footer logo and address are in place. Nothing is clipped.
- **The figure's tie held:** `Example Research` matches the publisher in `sources.md`, and 62% appears in both posts. The same card with "Jura saves you 62%" fails on the numbers rule.

## Classes A and B (X4)

Each confirmed by reading the diff; each name passed in junit.

| Test, as named now | Must survive | Confirmed |
|---|---|---|
| `test_publish_items::test_each_platform_ships_exactly_as_decided` (was `test_every_platform_ships_in_draft_mode`) | Exact equality | Exact map of mode, address and `enabled`, plus a host check |
| `test_publish_items::test_publish_mode_is_draft_or_browser_and_auto_is_gone` | `auto` raises | First line only changed |
| `test_social::test_carousel_days_and_publish_mode` | Carousel days and `auto` | One line changed, to an exact map |
| `test_publish_items::test_submit_raises_one_social_post_request_for_facebook_only` | One request, exact content | Only the deadline literal and the links line changed |
| `test_publish_instagram_linkedin::test_submit_raises_exactly_one...[instagram, linkedin]` | Every card assertion, exactly one | Pointer block replaced by "no message". Instagram's files are now the 3 slides |
| `test_publish_items::test_a_browser_platform_stays_out_of_social_drafts_and_a_draft_platform_gets_its_hand_post` | Both halves | Both |
| `test_publish_items::test_browser_mode_without_a_page_url_gets_a_note_and_never_a_request_to_post` | No item, reason shown | Both, and no "by hand" |
| `test_publish_items::test_social_post_cards_and_their_feed_lines_carry_nothing_planted` | `assert_clean`, marker reaches card and line | Both. Cards fell from 2 to 1 because a post past the gate that the mask would change now gets no card (code review 02, SP-B1): tighter |
| `test_publish_run::test_nothing_planted_reaches_discord_from_a_publish_run` | 4 and 5 separately | Exactly that |
| `test_publish_items::test_a_saturday_draft_on_a_browser_platform_raises_a_request` | Bound to the day's deadline | One literal, 18:00 to 17:00 |
| `test_social::test_submit_delivers_everything` plus twin `test_browser_mode_writes_the_same_files_and_rows_and_raises_a_card_for_each` | Assertions kept under draft mode | Pinned draft mode. The size literal updated for the carousel |
| `test_social::test_submit_monday_news_with_carousel` | The same | The same |
| `test_social_linkedin_off::test_submit_drafts_renders_and_posts_nothing_for_linkedin` | `len(posts) == 3`, absences | Function unchanged: its helper `linkedin_off` pins `browser=()`. The twin is `test_a_day_on_the_shipped_config_asks_in_approvals_and_posts_only_what_was_approved` |
| `test_social::test_word_ranges` | Numbers literal | Literal |

## Trace (X2, X10)

Names checked as passed in junit by `x24.py`.

| Finding or criterion | Case |
|---|---|
| AF1 | `test_approvals_first`: `test_each_platform_gets_one_card_and_social_drafts_hears_nothing`, `test_a_card_carries_the_sources_the_post_relies_on`, `test_a_280_word_post_splits...`, `test_a_day_on_the_shipped_config...` |
| AF2 | `test_both_approved_at_1659_both_go_out_before_1800`, `test_a_tap_at_1701_answers_expired_and_nothing_goes_out`, `test_nothing_unapproved_goes_out`, `test_a_pause_stops_an_approved_post`, `test_on_the_shipped_config_a_request_that_isnt_approved_hands_out_nothing` |
| AF3 | `test_no_page_url_gets_a_note_saying_so`, `test_a_submit_after_the_decide_by_gets_a_note_and_no_card`, `test_a_render_failure_gets_a_note_no_card_and_an_alert`, `test_no_image_means_no_item_and_no_request_on_either_platform` |
| AF4 | `test_the_precheck_tests_against_the_decide_by`, `test_a_platform_in_draft_mode_still_runs_late`, `test_a_late_run_skips_before_claude_starts_and_says_why`, `test_a_late_run_on_the_shipped_config_skips_before_claude_starts` |
| AF5 | `test_hand_posting_text_appears_only_for_a_platform_in_draft_mode`, `test_going_back_to_draft_mode_with_a_card_open...` |
| FD1 | `test_feed`: `test_an_approval_posts_one_line...`, `test_a_skip_posts_one_line`, `test_an_expiry_posts_one_line_saying_why`, `test_an_item_gone...`, `test_every_real_kind_names_its_feed...`; `test_feed_real_kinds::test_an_approval_posts_one_line_named_as_its_card_named_it` |
| FD2 | `test_a_request_superseded_with_a_successor_posts_no_line`, `test_a_request_superseded_on_changed_content_posts_no_line_before_its_successor_exists`, `test_a_claim_after_an_approval_posts_no_line`, `test_a_social_day_from_approval_to_the_run...` |
| FD3 | `test_a_decision_claimed_before_the_sweep_reports_as_approved_once`, `test_further_sweeps_add_nothing` |
| FD4 | `test_a_failing_feed_never_holds_up_the_sweep_or_the_decision`, `test_a_post_that_raises...`, `test_a_failed_edit_gives_one_follow_up_and_still_one_line` |
| DP1 | `test_social_depth::test_each_theme_has_its_own_word_range_on_each_platform`, `test_social::test_word_ranges` |
| DP2 | `test_ai_news_with_one_source...`, `test_ai_news_with_two_sources_on_one_host_is_refused`, `..._on_two_hosts_is_delivered` |
| DP3 | `test_each_theme_refuses_one_item_short...`, `test_on_a_tuesday_ai_news_goes_out_with_the_cover_first`, `test_a_list_of_five_items_gets_the_cover_and_four_slides`, `test_from_the_toolbox_needs_no_items_and_one_image` |
| DP4 | `test_social_prompt`: `test_the_prompt_asks_for_insight_in_four_parts`, `test_every_existing_brand_rule_stays`, `test_the_prompt_holds_no_word_range` |
| DP5 | `test_a_word_miss_uses_the_regeneration`, `test_a_shortfall_then_a_word_miss_then_a_pass` |
| PC1 | `test_social_visuals`: `test_each_kind_at_its_sizes_parses`, `test_a_percentage_draws_a_ring`, `test_a_headline_theme_needs_a_visual`, `test_every_item_on_a_list_theme_needs_an_icon` |
| PC2 | `test_an_icon_off_the_list_is_refused`, `test_each_vendored_icon_is_lucide_safe_and_at_the_design_systems_stroke`, `test_a_buzzword_on_the_picture_fails_the_social_card_gate`, `test_every_variable_the_card_uses_is_defined` |
| PC3 | `test_social_cards_real_chrome`: `test_nothing_overflows_at_either_size`, `test_type_stays_above_the_design_systems_minimum`, `test_fit_measures_the_page_the_picture_gets` |
| SC1 | `test_schedule_drift`: `test_two_jobs_steadily_nine_hours_early_are_flagged`, `test_a_mac_waking_at_the_same_time_every_day_is_not_drift`, `test_steady_drift_reaches_needs_you`, `test_a_late_wake_says_nothing` |
| B1 | `test_a_280_word_post_splits...` |
| B2 | `test_a_card_is_decided_by_1700_and_used_by_1800` |
| B3 | `test_digest_closes_the_day`: `test_the_1805_digest_closes_an_unanswered_card_and_counts_it`, `test_the_digest_is_scheduled_after_the_use_by` |
| B4 | `test_social_prompt::test_nothing_stale_survives` (14 cases), and X11 |
| B5 | `test_no_image_means_no_item_and_no_request_on_either_platform` |
| B6 | `test_uat_seed_discord_flow.py` |
| S1 | `test_social_figures.py` |
| S2 | `test_app_builds::test_the_feed_line_says_who_builds_it_and_posts_once` |
| S3 | `test_app_releases::test_a_recorded_release_posts_one_released_line` |
| S4, S5, S6, S8, S11, S12, S13 | `test_a_request_superseded_on_changed_content...`, `test_an_item_gone...`, `test_a_card_names_the_headline_and_the_title_is_not_hashed`, `test_an_approval_while_publishing_is_paused_says_so`, `test_merge_day_a_draft_written_before_browser_mode_says_no_card`, `test_ai_news_with_two_sources_on_one_host_is_refused`, `test_the_line_says_how_far_off_and_what_to_do_without_stating_the_cause_as_fact` |
| S9 | Overtaken by the conductor's ruling: `test_a_post_the_card_would_mask_fails_the_gate_and_uses_the_regeneration` |
| S7 | Walked: the outreach line reads as S7 asked |
| S10 | `uat.md` Part L1 |
| S14 | PC1's wording in `test_social_visuals.py` |

## Exploratory charter

The cards have no screens of their own, so the usual charter maps to this: odd inputs, a tap after the fact (back button), a command repeated (refresh), a slow Discord (slow network), simultaneous taps and sweeps (two tabs), and pictures at phone width.

| Tried | Saw | Verdict |
|---|---|---|
| Empty folder, missing folder, unknown theme, broken `card.json`, one missing variant | Each exit 2, a plain reason, no regeneration used | Fine |
| A post with a fence and a `> ` line | Refused at the gate, naming each | Fine |
| `@everyone` opening a headline | Refused as not sentence case. `allowed_mentions` is empty on every line anyway | Fine |
| Phone and titled name in a post | Refused, each with its own reason, the value masked in the alert | Fine |
| HTML in a card's labels and headline | Drawn as literal text | Fine |
| Figure about Jura in the post and on the card | Numbers rule fails | Fine |
| Approve twice; approve, skip, approve; a tap after expiry | "already approved", skipped once, "already skipped", "expired". Lines: one approved, one skipped | Fine |
| `social submit` again after delivery | "already drafted", no second card | Fine |
| Digest twice | No second post, no second line | Fine |
| Feed taking 30s | Decision returned in 6.1s; line in the outbox | Fine |
| Three taps at once on one card | One approve and one skip recorded, the third "already skipped". Two lines, the second at the next sweep (functional note 4) | Fine |
| Three sweeps at once | One edit, one line | Fine |
| Mac off at 18:05 | Next 08:00 one-pager closes yesterday's cards, one line each, and "approved but not used" appears under Needs you. Today's `publish next` hands out nothing | Fine, but its "Yesterday" repeats ticket 05's words |
| Saturday | Cards, 17:00 decide-by, claim, digest all work. Digest shows ticket 05 | Fine, ticket 05 |
| `pause all`, then 18:05 | Digest still closes the day | Fine |
| Approve at 08:30 | Refused to claim at 08:45, claimed at 09:00. Line still promises today, which is true | Fine |
| Flip to `draft` with a card open | Ticket 06 | Minor |
| Community post approved at 17:50 | Ticket 06 | Minor |
| A decided card | Its body keeps "Answer: Approve / Skip" (one-piece cards keep it in the edit; a split card's second piece is never edited). Buttons do go. A late tap gets a true answer. Predates this branch | Note, no ticket |
| The UAT seed's `app-prd` after a skip | Reuses the skipped number (APP-102 twice). Harness only, and UAT A2 isn't affected | Note, no ticket |

## UAT dry run

Parts P to C were dry-run on the frozen clock. Part P's commands ran as written, with real Chrome and web fonts. S1, S2's decide and claim, S4, S5, S6, S8, S10, E1 to E4, A1 to A3, C1 and C2 ran as their seed and CLI steps, and their expected words match what I read, down to the feed line wording. These were not run, by design: S2's and S3's browser posting, S7, and S9's `jura-growth run` (X14), which belong to Ting Yu. No correction to `uat.md` is needed. S5's "known wording gap" now points at ticket 05.

## How the walk ran

**Discord.** The brief asks for `JURA_GROWTH_DISCORD=off`, and I ran that case too. It writes no card: `cards.sweep` returns at once with no webhook, the recorder saw 0 messages, and `social submit` says "its card goes to #approvals once Discord takes it". So no card or feed line exists to read under `off`. To read the messages, each temp folder has an env file with loopback webhooks to a recorder in my script (`127.0.0.1`), and `DISCORD_WEBHOOK_*` scrubbed from the environment. No real webhook could be reached.

**Limits kept.**

- Every command had temp data, outputs, PRD, config, inputs and pause paths, a fixed `JURA_GROWTH_NOW`, and a stand-in `claude` first on `PATH`. The stand-in's call log doesn't exist, so nothing called `claude` from these commands. The suite's own `fake-claude` is a test double.
- `resend_stub` on `127.0.0.1:8025` took the one test email. Nothing reached real Facebook or Instagram.
- `heartbeat`, `digest` and `one-pager` read launchd's state through `launchctl print` and `~/Library/LaunchAgents`. That is a read: nothing was installed, loaded or rendered.

**Changes outside my temp folders during this QA, none of them mine.**

- `~/Library/LaunchAgents/sg.jurasolutions.growth.*.plist` were rewritten at 23:32:28. Their `WorkingDirectory` is the main checkout, the digest is at 17:30, and they include `outreach-requests`, a job this branch doesn't have, so another session's `schedule install` from `main` wrote them.
- Live `growth.db`, `app-backlog.yaml` and `runs/2026-10-31.jsonl` changed at 23:36 and 23:37: the run log shows `remote.command` rows from Ting Yu's own Discord user (`apps idea`, `apps handoffs`, `apps released`). I read that log's tail and the plists; I wrote nothing there.

**Commands.**

- `uv sync`; `git fetch origin`; `git switch --detach origin/crew/approvals-first-social-depth`; the Appendix A script; the X5, X6, X7 and X11 greps and diffs; `git merge-tree --write-tree --name-only origin/main f0db1e5`.
- Suite: `uv run pytest -rs -rfE -p no:cacheprovider -o addopts="" --junitxml=... --tb=short`, with the plug-ins above where noted. `.venv/bin/python -m pytest` for the clock runs, the defect tests and one rerun of the failed test.
- `jura-growth` in temp folders: `social submit`, `social render`, `social skip`, `social history`, `approvals`, `publish next --json`, `publish queue`, `publish done`, `pause`, `resume`, `heartbeat`, `digest`, `one-pager`, `outreach send-due`, `outreach suppress`, `apps handoffs`, `apps release-plan`.
- `python -m tests.uat.seed` scenarios: `base`, `social-day`, `decide`, `outreach-live`, `edit-draft`, `app-prd`, `app-built`, `note-rules`, `community-plan`, `fixture-join`, `drift`, `late-wake`.
- `python -m tests.resend_stub`; real Chrome through `render` and `card_probe`.

**Left behind.** My temp folders are still at `/private/tmp/qa-*`: fake data and loopback webhooks only. My cleanup command was refused by the session's permission classifier, so I left them. They can be deleted.

**Where this report is.** The brief asked for this file in the feature folder of the `approvals-first` worktree. This session may write only in its own worktree, and it refused that path, so this file and the tickets are in `.scratch/approvals-first-social-depth/` of `agent-aead883fed6300432`, uncommitted. The conductor needs to copy them across.

**Evidence kept** in the session scratchpad's `qa/` folder: `runs/` (suite output and junit), `walk1.txt` to `walk9.txt` (every message), `x8/` and `x9/` (the PNGs), `news-sample/`, `netlog/`.

## Defects

| Ticket | Severity | Owner | Failing test |
|---|---|---|---|
| `issues/05-defect-digest-calls-closed-cards-no-card.md` | Minor | Developer | `issues/test_qa_final_defects.py`, 2 cases |
| `issues/06-defect-approved-line-promises-what-cannot-go.md` | Minor | Developer | `issues/test_qa_final_defects.py`, 2 cases |
| `issues/07-defect-missing-config-silently-drops-the-buzzword-check.md` | Minor | Developer | `issues/test_qa_final_defects.py`, 1 case |
| `issues/08-defect-refusal-test-fails-when-the-live-engine-writes.md` | Minor (a test, not the product) | Developer | `issues/test_qa_final_defects.py`, 1 case |
| `issues/09-defect-typed-approval-of-a-refused-card-goes-through.md` | **Major** | Developer | `issues/test_qa_final_defects.py`, 1 case |

All 7 cases are red on `f0db1e5`, each at the assertion its ticket names: `7 failed in 8.09s`. To run them, use `-p conftest` with `PYTHONPATH=tests`, or copy the file into `tests/`.

**Against the final review.** Its SP-B1 is ticket 05 and SP-B2 is ticket 09. Its "Should fix" items, such as SEC-S1 (the UAT seed can reach live Discord if `JURA_GROWTH_ENV_FILE` isn't exported) and UI-S1 (mixed-case mono captions, visible in the matrix PNGs), stay with that review. Fixing UI-S1 needs the Chrome matrices rerun, because uppercase runs wider, and that reopens X8 and X9. SEC-S1 should be fixed before Ting Yu runs the UAT. I didn't run it, for the reason the review gives.

Open items from `crew-log.md`:

- "A missing config folder silently disables the buzzword check." Confirmed, and now ticket 07. It predates the branch, the numbers rule still holds, and a live run always has the folder.
- "Expired drafts read 2 social drafts waiting." This is now ticket 05.

## After the merge

*Developer, ticket 10, 2026-11-01, on `crew/approvals-first-social-depth-10-final-fixes`, which holds `origin/main` at `c11eb61`. Everything above this section is QA's record at `f0db1e5`. X1 to X8 are rerun here because the merge moved code they rely on. This is the developer's own run, for the reviewer and the gate to check: it isn't a QA verdict, and X10 to X15 stay with them.*

Every command had temp data and outputs folders and a stand-in `claude` first on `PATH`. That stand-in's call log doesn't exist, so nothing called it.

### Exit criteria, rerun

| # | Verdict | Command | Result |
|---|---|---|---|
| X1 | **Met** | `pytest -rs -rfE -p no:cacheprovider -o addopts="" --tb=short --junitxml=...`, twice at the last code commit | Run 1: 5653 passed in 373 s. Run 2: 5653 passed in 517 s. No failure, error or `SKIPPED` line in either. The floor is 3980 |
| X2 | **Met** | A script reads every test name in this file's "Trace" and "Classes" tables and looks for it as passed in run 1's junit | 122 names read. Two don't match by name, and neither is a miss: `test_every_platform_ships_in_draft_mode` is the old name QA listed beside its new one, and `test_submit_raises_exactly_one...` is an abbreviation of a test that passed |
| X3 | **Met, two changes listed** | Appendix A, against `origin/main` | `same` 22 times. `CHANGED test_hashtag_limits_and_position`, as QA listed (technical N9). `CHANGED test_digest_figures`: main's version pins a by-hand count of 3, which is a draft-mode claim, and Facebook and Instagram ship in browser mode here. It now adds `monkeypatch` and `pw.social_config(monkeypatch, browser=())`, with every assertion exactly as on main |
| X4 | **Met** | Each Class A or B test's parsed form compared between `f0db1e5` and the tip | All unchanged since QA read them. `tests/test_publish_instagram_linkedin.py` has no diff at all |
| X5 | **Not met as worded, no rule lowered: the gate rules, as before** | The two greps in X5, against `origin/main` | The first prints the same 5 lines QA read, all a parametrize argument named `words`. The second prints nothing |
| X6 | **Not met as worded, no behaviour changed: the gate rules, as before** | The two diffs in X6, against `origin/main` | The same as QA's: `approvals.py` 3 constants and 4 literals with the same values, `caps.py` a comment, `tests/gate_adapter_social_post.py` 4 lines under `[B2]`. `claim.py`, `origin.py`, `approvals_cli.py` and the ADRs show no diff. Ticket 09's refusal is in `agents/publish/kinds.py`, inside the kind |
| X7 | **Met** | `find` over `inputs` and `design-system` newer than `a6c2cca`; `git diff --name-only origin/main...HEAD` filtered to blocked paths | Both print nothing |
| X8 | **Met** | Run 1's junit, and the matrix below through `card_probe.probe`, whose default is `offline=True` | The PC3 file passed with no skip. 34 of 34 pass |

UI-S1 made two captions uppercase, which runs wider, so X9's record was stale too. It is rerun below, and it needs no waiver.

### The matrix, on fallback fonts (X8)

| Case | Size | PNG | Fit | Smallest type | Result |
|---|---|---|---|---|---|
| flow-3-short | 1200×630 | 1200×630 | 1.0 | 17 | pass |
| flow-3-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass |
| flow-3-full | 1200×630 | 1200×630 | 0.88 | 15 | pass |
| flow-3-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass |
| flow-4-full | 1200×630 | 1200×630 | 0.88 | 15 | pass |
| flow-4-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass |
| flow-4-long-word | 1200×630 | 1200×630 | 0.88 | 15 | pass |
| flow-4-long-word | 1080×1350 | 1080×1350 | 1.0 | 20 | pass |
| compare-2-short | 1200×630 | 1200×630 | 1.0 | 17 | pass |
| compare-2-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass |
| compare-2-full | 1200×630 | 1200×630 | 0.88 | 15.0 | pass |
| compare-2-full | 1080×1350 | 1080×1350 | 0.92 | 20 | pass |
| compare-3-full | 1200×630 | 1200×630 | 0.88 | 15.0 | pass |
| compare-3-full | 1080×1350 | 1080×1350 | 0.88 | 20 | pass |
| compare-3-long-word | 1200×630 | 1200×630 | 0.88 | 15.0 | pass |
| compare-3-long-word | 1080×1350 | 1080×1350 | 0.88 | 20 | pass |
| figure-ring-short | 1200×630 | 1200×630 | 1.0 | 15 | pass |
| figure-ring-short | 1080×1350 | 1080×1350 | 1.0 | 20 | pass |
| figure-ring-full | 1200×630 | 1200×630 | 0.88 | 15 | pass |
| figure-ring-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass |
| figure-ring-whole | 1200×630 | 1200×630 | 0.88 | 15 | pass |
| figure-ring-whole | 1080×1350 | 1080×1350 | 1.0 | 20 | pass |
| figure-no-ring-full | 1200×630 | 1200×630 | 0.88 | 15 | pass |
| figure-no-ring-full | 1080×1350 | 1080×1350 | 0.88 | 20 | pass |
| list-2-short | 1200×630 | 1200×630 | 1.0 | 17 | pass |
| list-2-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass |
| list-5-full | 1200×630 | 1200×630 | 0.68 | 15.6 | pass |
| list-5-full | 1080×1350 | 1080×1350 | 0.76 | 22 | pass |
| list-5-no-icons | 1200×630 | 1200×630 | 0.68 | 12 | pass |
| list-5-no-icons | 1080×1350 | 1080×1350 | 0.76 | 18.6 | pass |
| headline-only | 1200×630 | 1200×630 | 0.72 | 17 | pass |
| headline-only | 1080×1350 | 1080×1350 | 1.0 | 22 | pass |
| slide-full | 1200×630 | 1200×630 | 1.0 | 15 | pass |
| slide-full | 1080×1350 | 1080×1350 | 0.92 | 20 | pass |

**Real fonts (X9):** the same cases with `offline=False`: 34 of 34 pass. The fonts loaded: `headline-only` at 1200×630 fits at 1.0 on web fonts and 0.72 on fallback, and `list-5-full` at 0.8 and 0.68, the same as QA's figures.

**By eye:** `figure-ring-full` at 1080×1350 and `flow-4-full` at 1200×630, the two captions UI-S1 changed at their limit. The uppercase captions take two lines, inside the panel, and nothing is clipped.

### The clock

The merge doesn't touch the 9-hour shift, so no test may lean on the real time. Both runs below used the same throwaway plug-in as QA's: it starts the suite's clock at the time named and lets it tick. Tests that pin `JURA_GROWTH_NOW` are unaffected, and a subprocess keeps the real clock.

| Clock starts | Why | Result |
|---|---|---|
| Tue 10 Nov, 00:00 | Where the live publish and one-pager jobs fire under the shift | 5653 passed in 382 s |
| Sat 14 Nov, 16:58 | A weekend, crossing the 17:00 decide-by | 5653 passed in 481 s |

Ticket 08's race is closed by construction: the refusal tests no longer stat the live data folder. The seed runs under an audit hook that stops it at the first thing it opens or changes there, and the file-by-file comparison uses a planted folder nothing else touches.

### The defects, walked

The real commands, each its own process, with a recorder on `127.0.0.1` for Discord and `DISCORD_WEBHOOK_*` scrubbed from the environment.

| Ticket | Walked | Read |
|---|---|---|
| 05 | `social-day`, then `digest` at 18:05 | "Publishing: 0 posted, 0 skipped, 2 expired, 0 stopped" and "Social: 2 drafts expired (facebook, instagram), 0 skipped, 0 published". `social_drafts_waiting` is 0 and the brief line has no "waiting" |
| 06, case 1 | Facebook to `draft`, approve, `publish next` | Line: "Facebook is in draft mode, so nothing is posted through the browser, and this lapses at 18:00 SGT." `publish next` hands out nothing. Digest: "1 draft approved, held by draft mode (facebook)", with no #social-drafts claim |
| 09 | Webhook answering 500, a contact teaching a word in the post, `heartbeat`, `decide`, `publish next` | One note for each card and no card posted. `decide` answers "Discord would mask part of the post, so its card can't show the exact text, so it can't be approved". `publish next` says "A-0001 is waiting for a decision" and hands out nothing |

Ticket 09's limit from QA still stands: this is the seed's `decide` in a new process, not a real SSH call, and it makes the same `approvals.decide` call. `tests/test_qa_final_defects.py` also decides in a real second process.

Ticket 06's case 2 and ticket 07 are covered at their seams in the same test file, and ticket 08 in `tests/test_uat_seed_outreach.py`: a seed let into a planted folder fails both of the new checks, so a broken refusal can't pass them.

### Open for the gate

- **X5 and X6** read as QA reported, so the gate still has to rule on the wording of both.
- **CLAUDE.md's numbers rule (ST-S2).** It still says "Only the phrases in `config/approved_claims.yaml`", and the email's "30-minute call" is the one allowance beside them. The allowance is now written in `config/approved_claims.yaml`. CLAUDE.md is Ting Yu's to change, so it isn't changed here. Suggested words: "Only the phrases in `config/approved_claims.yaml`, and the allowance it names."
- **A wording cost to check at the gate.** A refused card's short line on the picture and in the message says "Let A-nnnn lapse ...: it has no card, so nothing goes out." The reason itself is in the note in #social-drafts and in the long text.
