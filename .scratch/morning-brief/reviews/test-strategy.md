# Test strategy: morning brief

Spec: `prd-jura-morning-brief-2026-10-31.md`, as reworded by `reviews/functional.md` §2. `reviews/technical.md` doesn't exist yet, so these are the seams the existing tests name plus one new one, P.

**Seams.** U: `brief.*` and `one_pager.summary()` on a built `Snapshot`. S2: `mission.read()` on temp data. S5: `one_pager.post` through the Discord double. S9: `runner.run` in process. **P (new):** `brief.html()` in real Chrome through `images.run_chrome`, in a helper `tests/brief_chrome.py`. It adds a measuring script to a test copy of the page and reads the result with `--dump-dom`. The production page stays script-free.

## Coverage map

All automated unless the row says otherwise.

| Criterion | Level and seam | Asserts | Data |
|---|---|---|---|
| MB1 | U, S5, P | The verdict across all four counts. One POST with one `.png`. The verdict is the first text after the header | built, T |
| MB2 | P | Computed size of every text node is at least 21 px; PNG width 1200 | all |
| MB3 | U, P | Decide sort with ties by id; missed line has no `HH:MM`; five rows; section order in the DOM | T |
| MB4 | U | Every `slots.WORST_FIRST` status and "none" has a word. The grid's token test runs on `brief.html` | built |
| MB5 | P | The oracle below, offline in the suite, with real fonts recorded by QA | all |
| MB6 | U | Table of clock, slot and record: "Due now", "Didn't run" plus a Fix line (a Monday community slot too), "Not today" with no second line. `slots.py` keeps its `due` | built |
| MB7 | U, S2 | Every route in functional B2 shows a dash. A recorded 0 shows 0 | built, B |
| MB8 | U, P | `<img onerror>`, `<script>` and `` `<b>` `` through every text route: no such element exists in Chrome. Masking is risk 1 | hostile |
| MB9 | S5, P | Both files exist. The footer scrolls into reach at 1200×700. `backup` prunes `brief-*.png` and `.html`, and keeps other names | temp |
| MB10 | U, S5 | Every required part is present. W is at most 2,000 characters, so it never splits from the PNG | built, W |
| MB11 | S5, CLI | Bad Chrome path and failed `.html` write: long text with the reason, `one_pager.brief_failed`. `--no-post` passes `stat_snapshot` | temp |
| MB12 | CLI | `--grid` prints a path and posts nothing. A normal post writes no `grid-*` | D1 |
| MB13 | S2 | Spies on every kind's `content()` and `preview()` see no call; `stat_snapshot` is unchanged, `_morning` included | D1, T |
| SC1, SC5 | U | Exact schedule of the six jobs; a golden table of every other job | settings |
| SC2 | S9 | Live with 3 queued and room 2: 2 requests, 2 cards, rerun adds none. Room 0, shadow, paused, PAUSE file: nothing. No Resend call. Quiet, no run update | outreach |
| SC3 | integration | Queue at 06:40: card posted, right decide-by, nothing sent. New test in `test_outreach_cards.py` | lead 233 |
| SC4 | U | Computed for each weekday: slot plus `claude.timeout_minutes` ends by the next slot and by 09:00 | settings |
| SC6 | S2 | Through scout's `health()`, Saturday and business day, temp inputs folder: present when absent, gone when present | temp |
| SC7 | U, manual | README job table against settings; `CONTEXT.md` wording. QA records a search for old times. README's AI OS "08:00" and publish's 09:00 stay | repo |

**End to end** (`tests/test_morning_order.py`): the clock steps 06:40, 08:30, 09:00 in live mode. An email is queued, a leftover raised, the job posts through real Chrome. Decide lists both, soonest first, and nothing sends.

## Worst-case fixtures and the overflow oracle

`tests/brief_world.py` holds **Q** quiet, **T** typical, **B** bad day (database missing, then locked), and **H**, one page per real wording in `HEALTH_ITEMS`. **W** is the worst case: 50 requests, 20 fixes, 400-character reasons, a 120-character unbroken token, a CJK company name, long skip reasons on all five rows, five-digit tiles, US$12,345.67, all three warnings, the longest verdict and the widest date.

P fails a fixture unless:

1. A token resolves, so an unstyled page can't pass.
2. Every section heading is inside the page, and "and N more" has the right N.
3. No text leaves the page, nothing but a clamp has scroll size above client size, and a clamp shows whole lines.
4. No two text rects from different blocks overlap.
5. PNG height equals the measured content height, at most 1,600 px. The gap above the footer is at most 100 px.
6. The PNG's bottom 20 px are plain background (a small `zlib` decoder, no new dependency).

**Measured on the draft at 73c13d5:**

- W hides the whole Fix section while the verdict says "13 to fix", and the tiles run into Later today. Q leaves a large gap. Both must fail P until fixed.
- For a 1,120 px window, `--dump-dom` lays out at 977 px offline and 1,033 px with network, while `--screenshot` lays out at 1,120. Neither the oracle nor a two-pass height measure can trust the viewport, which is why item 5 reads the PNG.
- Offline, Chrome has no design-system fonts: the tile row is 637 px, against 591 px with them. Both happen in production, since the fonts come from Google at 09:00. The suite proves the fallback. QA runs the same helper with `--live-fonts` (not collected by pytest, because no test may touch the network; synthetic data only), records its JSON, and views W, Q and B at 550 px.

## Risk-based depth

1. **Privacy.** The `.html` is written directly, not through `discord.post()`. New tests sweep three things with `assert_clean` through `SimpleNamespace(texts=…)`: the page handed to `images.screenshot` (a spy), `brief-<day>.html` read from disk, and the message. The spy page must equal the file, which is what stands in for the PNG's pixels. The posted PNG holds only `PIXEL_CHUNKS`. **Trap:** the picture keeps only an item's first line and first sentence, so planting `Planted.text()` as one block passes with most values untested. Plant each value alone, as the first line, per route: `approvals.reason`, `runs.summary`, `runs.error`, `pause_flags.reason`, PAUSE file, a plug-in health line, the ICP line, `app_prd_today`, and a value nested in a digest figure (`_digest_day` cleans top-level strings only). Each route must show the marker.
2. **A false "Nothing needs you"** (functional B1): the MB1 and MB6 tables, with drafts to post by hand and replies.
3. **Cards and sends:** SC2 and SC3 negatives, and no Resend call at any end-to-end step.
4. **The 09:00 collision with publish** (functional S4): at S2, a held lock retries, and past 60 seconds gives the bad-day page. Clock faked.
5. **A kind no row owns:** every registered approval kind maps to one `brief.AGENTS` row.

## Existing tests

The draft fails 13 of 3,982 today, all in `test_mission_read.py` (7), `test_one_pager_post.py` (5) and `test_one_pager.py` (1).

- **Time values only:** those 7, and the one in `test_one_pager.py`, move from 08:00 to 09:00, because `ONE_PAGER_DEFAULT` moved.
- **Behaviour:** in `test_one_pager_post.py`, the 0800 job, 2,000-character split, can't-draw, one-file-a-day and split-pieces sweep tests now describe the picture and fallback. The settings test moves to 09:00, the backup test gains `brief-*`, and `stub_grid` also stubs `brief.render`.
- **Small:** the import guard in `test_one_pager_grid.py` adds `brief.py`. `test_mission_setup_guides.py` and its guide move to 09:00.
- **Time values only, added by code review 02:** `STATUS_GOLDEN` in `test_mission_health.py`, because `status` prints the live schedule.
- **Stay as they are:** the rest of `test_one_pager.py` (the long form is MB11's fallback) and of `test_one_pager_grid.py`, the existing tests in `test_outreach_cards.py`, `mission_world.py`, `sweep.py`, `test_mission_slots.py`, and `fortnight.py` (D1 is frozen history on the old times; new times get new data).

## Not tested, and why

Ting Yu accepts these by merging (PRD §7).

- Discord's real display, height limit and phone view: no test touches Discord. UAT U1, U2.
- Words in the PNG's pixels: no OCR here. The spy page equalling the swept file covers it.
- launchd firing and the 9-hour drift: his steps and the other PRD's SC1.
- Real fonts in the suite: network ban. QA records them.
- What headless Claude really drafts: faked. UAT U6.
- Colour contrast: design-system tokens, an internal page, and every status is also a word.

## Exit criteria

On `crew/morning-brief` with the worktree exports:

1. Every row names a passing test or a recorded case in a `reviews/qa-*.md`.
2. `uv run pytest -rs -p no:cacheprovider -o addopts=""`: 0 failed, **0 skipped** (a missing Chrome would skip P silently), at least 3,982 collected.
3. P passes on all fixtures offline, and QA's `--live-fonts` JSON passes with DM Sans, Outfit and IBM Plex Mono loaded.
4. QA's record holds W, Q and B at 550 px, every word read.
5. The risk 1 tests exist and pass, and name the `.html` file and the spy page.
6. `git diff main` is empty for `tests/sweep.py tests/fortnight.py tests/mission_world.py tests/test_mission_slots.py pyproject.toml uv.lock`. In `tests/test_mission_read.py`, `tests/test_one_pager.py` and `tests/test_mission_health.py`, every changed line differs only in a time value or clock argument.
7. `git diff main --name-only` has nothing under `inputs/` or `design-system/`; `brief.html` has no `<script`.
8. Zero open critical or major defects. Critical: an unmasked value in any output, an email sent, or a card lost. Major: a criterion failing, a false verdict, or anything cut off on any fixture. Minor ones are listed with an owner.
9. No unresolved blocking finding in any `reviews/code-review-*.md`; `pyright` adds no error in a touched file.
10. If `crew/approvals-first-social-depth` has merged, the branch is rebased and criterion 2 rerun. If not, the PR body says to merge that one first (functional S2).
11. The PR body opens with the four after-merge steps and attaches the three renders (functional S3). UAT U1 to U7 run after merge and don't gate this decision; a failure means revert.
