# Technical review: approvals first, feeds after, social depth

Reviewed on 2026-10-31 against `prd-jura-approvals-first-social-depth-2026-10-31.md` and the draft at `a6c2cca`.

**Verdict:** the approach is sound and it needs no new seam. The draft has seven blocking problems. Each has a fix below, and none changes the shape of the design.

## What was run

| Check | Result |
|---|---|
| `uv run pytest` on the draft | 41 failed, 3939 passed. All 41 are social flow fixtures and shipped-config assertions; none comes from `feed.py` or its import |
| Importing `feed`, `cards`, `approvals`, `discord`, `publish.job`, `community`, `apps`, `mission`, `health`, each in a fresh process | All clean, so there is no import cycle |
| Probe: change a request's content, then `expire_due()`, `sweep()`, `request()` | The feed posts "A-0001 withdrawn", then A-0002 raises with `supersedes = None` (B1) |
| Probe: `discord.split` on a realistic card | Facebook at 280 words with 3 links: 2824 characters, 2 pieces, one fence in each. Instagram at 240 words: 2227 characters, 2 pieces, and the split falls just after the closing fence, with 43 characters of headroom (B2) |
| Probe: `health.schedule_drift` | True drift is found. A routine 09:00 wake is not flagged. The morning after a restart gives a false alarm, and a true drift with one outlier is missed (B7) |
| Probe: worst-case flow, compare and figure in real Chrome, offline fonts | `data-fit` 0.68 to 0.84, above the 0.56 floor, and both sizes I viewed were legible |

The probes ran in the session scratchpad against temp folders and the Discord double. Nothing touched the live system.

## Answers to the specific questions

### Can a feed line be lost, doubled, or posted for a request with no card?

- **Doubled: no.** The sweep holds the `approval-cards` lock, and `shows` is updated in autocommit before `announce`. A crash between the edit and the update repeats the edit and then announces once. The callers I read sweep only after their transaction commits (`db.transaction` closes first).
- **Lost: yes, in two narrow cases, and that is acceptable.** A crash between the `UPDATE` and `announce` loses the line. A Discord failure saves it to the outbox, which nothing replays, though the one-pager counts it. Feed lines are at most once by design. They are a courtesy report, and `approvals` and the run updates stay the record. Say this in the `feed.py` docstring.
- **Posted with no card: no.** `_edit_changed` reads only `approval_cards`. The reverse does happen: a request that never got a card (no webhook, a refused preview) gets no line. FD1 should say "a request that had a card". See N5.
- **Wrongly posted: yes.** This is B1.

### Cycles and test doubles

- There is no cycle. `feed` imports `agents`, `approvals`, `discord` and `log`, and none of them imports `cards` at load. Plug-ins that import `cards` load lazily through `agents.plugins()`.
- The doubles still work. `discord_double` patches `discord.httpx.Client`, so it catches the feed's posts too.
- The suite is silent on `feed.py` for a reason worth fixing. `FakeKind` has no `feed_channel` and its fake plug-in names no channel, so `channel_for` returns None and nothing is posted. The feed has no coverage yet, not even from the privacy sweep. See the seams for ticket 02.
- `announce` catches `Exception`. `pytest.fail` raises a `BaseException`, so an assertion in a double still surfaces.

### The 18:00 precheck, and a carousel with no items

- The precheck is correct. `>=` matches `create_social` and `in_window`. It returns a plain string, so the skip leaves a `runs` row and a run update, as AF4 wants. A typo in `publish.yaml` raises `LimitsError`, which is a failed run with an alert. That is the documented precheck behaviour, and publishing is broken in that case anyway.
- A carousel with no items is safe. `slides()` returns `[self]`, so one image goes out with no `-1-of-1` suffix. Any theme with `min_items` is refused earlier, without using the regeneration. `from-the-toolbox` on a Monday by fallback gets one image, which is right.
- One way around DP3 remains: `"carousel": false` in `card.json` still wins over `theme.carousel`. See N8.

### Does a changing carousel affect an existing approval?

No approval is affected.

- The hash covers each image's SHA-256 in order, and not its path (`kinds.hashed`). Rendering finishes before `_log_rows`, and the request is raised after that, so a new request covers the final slides.
- Drafts from before the merge never get an item (`items.py`: "items are made only at submit"), and the PRD records an empty publish queue, so no live `social-post` request exists for the new `page_url` to supersede.
- A same-day re-render can't reach a live request either: the first failed gate delivers nothing, and the final attempt is the last.
- On the merge day, a draft already written for that day stays where it is. `active_platforms` calls it already drafted, so that day gets no card and no second post. The digest then says it waits in #approvals (N11). The release notes should say so.

### The card past 2000 characters

The card is not right as drafted. See B2.

- A fence split across pieces leaves the first piece unclosed, and the second renders its text as markdown with stray backticks. AF1's exact text is the thing that breaks.
- `first_piece` and its edit keep the broken fence. Only the first piece gets a new status, which is acceptable, since the later pieces carry no status.
- `edit()` truncates at 2000. A longer status line can cut the end of a nearly full first piece, including its closing fence.

### Word budget against the publish run and audit

- **Typing audit: no change needed.** Text is gathered per field and compared after `normal()`, with no length rule, and several `type` calls with no click between them still count as one field. 280 words doesn't change the verdict.
- **Read-back: this is the real problem, B3.** A truncated read-back is a mismatch, and a mismatch pauses `publish` for every item.
- **Instagram caption limit:** nothing checks characters. Instagram's limit is 2200, from my own knowledge and not re-checked here. 240 words comes to about 1700 characters in the probe, so it fits today, but 240 long words plus 8 hashtags could pass it. If the field stops accepting input, the transcript still shows the whole text while the page holds less. See N9.
- **Instagram hashtags:** I recall Instagram capping hashtags at 5 per post from December 2025. There was no network here to confirm it. `hashtags_max: 8` could then fail on the first live post. Lowering the cap costs nothing. See N9.
- **Upload size:** the worst-case portrait slide was 314 KB, so five slides are about 1.6 MB. That is within Discord's attachment limit as I know it, and within the `file_upload` path the prompt already handles.

### `health.schedule_drift`, and ADR 0002

- **The read model stays read-only.** `_recent_starts` is one `SELECT` per job on the `mode=ro` connection, inside the `"runs" in tables` guard. A hot journal still raises `sqlite3.Error` and is handled as before. The `drift` field defaults to None.
- **The docstring's reasoning is wrong, though the result holds.** It says a wake moves one slot by a different amount each day. A Mac opened at 09:00 every day moves several slots by the same steady amount. It still doesn't trip, because the daily slots differ by at least 30 minutes, so their gaps can't agree. That difference between slots is the real proof, and it should be stated and tested.
- **False positive and false negative:** see B7.

## Blocking findings

### B1. A changed request posts a false "withdrawn" line (FD2, ticket 02)

`has_successor` reads `approvals.successor`, which follows `supersedes`. `_approval_upkeep` runs `expire_due()`, which supersedes without raising (`raise_new=False`), and sweeps straight away. Later `items.sync()` raises the new request through `approvals.request`, which finds no live record and inserts `supersedes = None`. So Ting Yu is told the post was withdrawn, and a new card follows on the next publish precheck. The link never appears.

**Fix:** suppress the line when `close_reason` is the "content changed" reason, as well as when a successor exists. Name both reasons as constants in `approvals` (`CONTENT_CHANGED`, `ITEM_GONE`), so that `feed` doesn't match on prose. Don't write a link into `request()`: the PRD puts the approval contract out of scope.

The one case this leaves without a line is content that changes after the window closes, with nothing replacing it. The digest covers that, so accept it.

### B2. A long card breaks its fence, and an edit can cut it (AF1, ticket 02, first commit)

**Fix, in three parts:**

1. **Make `discord.split` fence-aware.** Track ``` lines. A piece that ends inside a fence closes with `\n```` and the next reopens with ```` ```\n ````, and the limit allows for those added characters. This keeps the fix in one deep function, every poster gains from it, and `first_piece` holds a balanced fence.
2. **Leave headroom in the first piece.** Add `first_piece_room` to `discord.post`, and have `cards` pass a `HEADER_ROOM` of 120, so a longer status line can't reach the 2000 cut. Keep `[:MAX_CONTENT]` in `edit` as the last guard.
3. **Refuse a bare ``` line in the post.** `MARKDOWN_RE` matches only backticks with text between them on one line, so a ``` line alone passes the brand check and would close the card's fence early. Add `^\s*```` to it.

**Accepted as they are:** Approve and Skip stay on the first piece, the images and the answer line on the last. Moving the buttons would need a migration and a second edit. All pieces post within moments, and the approval binds to the content hash regardless.

### B3. A long post that went out correctly pauses publishing (ticket 02)

`publish done` compares the live text with the approved text, and a mismatch pauses `publish` for every item. `prompts/publish.md` tells the run to click "…more" only in the LinkedIn section. A 160 to 280 word Facebook post, or a long Instagram caption, is the case most likely to be cut short on the page.

**Fix:** add the same instruction to the Facebook and Instagram sections, and to the community post section: if the text is cut short with "See more" or "more", click it once. The audit allows that click, since `_keyboard` only moves focus and nothing has been stopped yet. Add an audit test that shows it.

**Unverified:** Facebook may shorten long URLs on the page, which would also read as a mismatch, and DP2 raises the links to as many as three. It fails safe, since the post is live and publishing pauses with an alert. U12 is the check. If it happens, handle it then with evidence in hand, and don't loosen `text.same` on a guess.

### B4. The social prompt contradicts the gate (DP1, DP2, DP3, DP4, AF1, ticket 01)

The draft didn't touch `prompts/social.md` or `docs/social.md`. The prompt still says:

- Facebook 60–120 words, aiming at about 90, and Instagram 50–120;
- "One or two sources" for `ai-news`;
- carousels on Mondays and Thursdays only;
- `items` for the list layout only, and nothing about `visual` or `icon`;
- "Ting Yu copies it from #social-drafts and posts it by hand".

A run that follows it fails the word check on a news day, uses its only regeneration, and may drop the post. DP4, the actual ask, isn't written at all.

**Fix:** rewrite those parts and add DP4. Remove the numbers from the prompt's table and point at the ranges `social today` prints, so there is one source of truth. Add a test that the prompt holds no word range.

### B5. Nothing ties a figure on a picture to a source (numbers rule, PC1, §4, ticket 01)

`_numbers` lets any figure through once the card has a third-party source (`news_ok`). `visual.source` is free text. So a `figure` card can print an invented number under an invented publisher and pass.

**Fix, in `drafts._card_depth`, which refuses without using the regeneration:** a figure's `value` must appear verbatim in every variant, and its `source` label must appear on a line of `sources.md`. This doesn't prove the figure is true, but it means the picture states nothing the post and its sources don't state, and Ting Yu reads those on the card.

### B6. An Instagram post with no image gets a card, and approving it pauses publishing (AF3, ticket 02)

A render failure, or a card whose words fail twice, leaves `images` empty. In `draft` mode Ting Yu dealt with that by hand. In `browser` mode `create_social` raises a request reading "No image.", he approves it, and the run has nothing to upload. It stops with `unidentified`, and a stop pauses `publish` for every item, using Instagram's post for the day.

**Fix:** `create_social` returns `Made(why="Instagram needs an image: …")` when the content has no images, so AF3's note applies. Set it as `image_required: true` on the platform in `config/social.yaml`. Facebook can still post text alone, and its card already says "No image".

### B7. Drift is wrong after the restart it asks for, and misses a real drift with one outlier (SC1, ticket 03)

Both are probed:

- **False alarm.** After a restart at 20:00 on Saturday, heartbeat and digest haven't run again by 08:00 on Sunday. Their last two runs still agree, so the one-pager says to restart the Mac the morning after he did. The PRD's own post-merge steps lead straight to this.
- **Missed drift.** If any one job is steadily off by a different amount (the Mac asleep during heartbeat's drifted 03:00 slot, so it always fires at wake), `max - min > tolerance` returns None for the whole check.

**Fix:**

- Find the largest group of jobs whose gaps agree, instead of requiring all of them to agree.
- The group needs at least two jobs whose slots are more than `DRIFT_TOLERANCE` apart.
- Return None if any daily job's newest run is on time and newer than the group's newest run. The one-pager's own run row settles it: it is on time once the clock is fixed, and off while it isn't.
- Pass `now`, and ignore runs older than three days, so paused jobs don't hold a stale alarm.

## Sequencing (blocking for the plan)

HEAD is one red commit holding all three tickets. That is acceptable on a feature branch, since `main` sees only the merge, and I would not rewrite it. Two things keep the landing orderly:

1. **Ticket 01 first restores `publish_mode: draft` and `page_url: null` in `config/social.yaml`. The last commit of ticket 02 flips them.** This is the expand–contract step for the one change that alters live behaviour. It also keeps `test_every_platform_ships_in_draft_mode` meaningful until the flip.
2. **The failing tests are a wide mechanical refactor.** There are 41 across 7 files, and most fail because `TIP` and `NEWS` in `tests/test_social.py`, imported by 5 other test files, no longer meet the depth rules. The first commit of ticket 01 makes those fixtures comply in one place. Don't edit each test.

| Ticket | Turns green |
|---|---|
| 01 | `test_social.py` (24) and `test_social_linkedin_off.py` (1), plus any failure in the other files that came only from the fixtures. `test_digest_figures` and `test_precheck` are wording, so they may move to 02 |
| 02 | Whatever remains: `test_publish_items.py` (10), `test_publish_instagram_linkedin.py` (3), `test_publish_linkedin_off.py`, `test_publish_fixture_merge.py`, `test_publish_run.py` |
| 03 | None of the 41. Independent, and can land at any point |

Prefactor commits, in order: the fixture change (start of 01), then the fence-aware `split` (start of 02).

## Test seams per ticket

The feature needs **no new seam**. `feed` is tested through `cards.sweep`, not on its own, because a test that calls `feed.line` directly would pin its shape and miss the wiring.

### Ticket 01: depth and pictures

| Seam | Covers |
|---|---|
| `submit.submit(conn, folder, offline=True)` on the Discord double (`tests/test_social.py`, highest) | DP1 to DP3 and DP5 end to end, the carousel on any day, refusals not using the regeneration |
| `drafts.theme_problems(sub, theme, today)` | B5, DP2, DP3, each theme's `min_items`, `needs_visual` |
| The `social-facebook` and `social-instagram` channels through `gate.gate` | DP1 by theme, including a fallback theme's own range, and N9 |
| `CardSpec.parse` and `visuals.parse` | PC1, PC2, the icon allow-list, a name that is a path |
| `render.render_spec` in real Chrome (`tests/test_social_render.py`) | PC3, at both sizes. Add the worst-case specs and read `data-fit`, asserting it stays above the floor. Every word on a visual reaching `body()` belongs here too |
| `plan.build` and `plan.render_text` | What the run is told. A prompt test for B4 |
| `test_templates_use_design_system_tokens_only` (exists) | PC2 |

### Ticket 02: approvals first and feeds after

| Seam | Covers |
|---|---|
| `cards.sweep(conn)` with `discord_double` and `approval_world`, with a `feed_channel` set on `FakeKind` (highest) | FD1 to FD4, B1: approved, skipped, expired, superseded with and without a replacement, a claim after an approval, an apply-on-decide kind, a feed webhook returning 500 |
| A table test over the real `approvals.kinds()` | FD1's channel for every kind, through `feed.channel_for`. A new kind must fail here until it names a channel |
| `tests/test_approval_cards_sweep.py` with the D2 and D3 datasets | The feed line is masked: `assert_clean` on the feed channel. This is a required test (AC-M11) |
| `discord.split` directly, and `discord.post` on the double | B2: balanced fences in every piece, text preserved, an edit that can't cut a fence |
| `submit.submit` in `browser` and `draft` modes (`test_publish_items.py`) | AF1, AF3, AF5, B6 |
| `social.precheck` through `runner` | AF4, including a mix of browser and draft platforms |
| `claim.next_item` and the publish transcript fixtures with `audit.audit` | AF2 is unchanged, a long text passes whole, a "See more" click passes (B3), a five-slide carousel passes |

### Ticket 03: the schedule drift check

| Seam | Covers |
|---|---|
| `health.schedule_drift(starts, jobs, now)`, pure (highest) | Steady drift, a routine wake, one late job, the morning after a restart, one outlier, stale runs |
| `health.strip(snapshot)` | The line appears under "Needs you", in order |
| `mission.snapshot` with `tests/mission_world.py` | Read-only stays true (`stat_snapshot`), and a hot journal (D4) still gives the "unfinished write" state |

## Blast radius

- **Core:** new `feed.py`; `cards.py`, `discord.py` (`split`, `post`), `approvals.py` (reason constants only), `health.py`, `mission.py`.
- **Plug-ins:** `agents/social/` (`__init__`, `checks`, `drafts`, `plan`, `render`, `settings`, `submit`, new `visuals`, templates and 77 vendored icons); `agents/publish/` (`kinds`, `items`, `group_kinds`, and the docstring in `__init__`, which still says Facebook only); `agents/outreach/` (`__init__`, `approval`); `agents/apps/builds.py`.
- **Config:** `config/social.yaml`, which turns on live posting.
- **Prompts and docs:** `prompts/social.md`, `prompts/publish.md`, `docs/social.md`, `CONTEXT.md`.
- **Schema and data:** no migration. `social_posts`, `publish_items`, `approvals` and `approval_cards` keep their shapes. New rows only, plus `discord_posts` rows for feed lines.
- **External surfaces:** #approvals, #social-drafts, #outreach-sent, #app-factory, #community, the Facebook Page and the Instagram account. The Dispatch contract is unchanged.
- **Tests:** 7 test files plus `approval_world.py`.

## Decisions and ADRs

**No new ADR is needed.** The feed being at most once and fired from the sweep is surprising and a real trade-off, but it is cheap to reverse (a column and a replay), so a docstring is enough. `publish_mode` is a config line. Diagrams over photographs is already decided by the design system.

| ADR | Effect |
|---|---|
| 0001 quiet runs | Unaffected. Drift reads `runs`, and only `daily` jobs, none of them `quiet`. Precheck strings leave a skipped row, so the social job stays measurable |
| 0002 read model | Holds. No amendment |
| 0003 approval binds to content | Holds. Slides are already in the hash. No amendment |
| 0004 decisions | Untouched |
| 0005 browser only in publish | Holds. Both hosts are in `BROWSER_HOSTS` and both page URLs pass `hosts.page_problem` (probed) |

Add **Agent feed** and **Visual** to `CONTEXT.md`, as the crew log expects.

**No prototype.** The one question paper can't settle is how the live pages read back, and that is U12 and U13, the first live posts. They fail safe.

## Non-blocking findings

The tickets should take these unless noted. All are small.

| # | Finding | Do |
|---|---|---|
| N1 | Lapses are written at 23:30 by `backup`, whose comment says "nothing new posts at 23:30". Each expired card now posts a new feed message then, and a post can notify where an edit doesn't | Send feed lines with Discord's suppress-notifications flag (`1 << 12`), through a `silent` option on `post`. The double records `flags`, so it is testable |
| N2 | A withdrawn line says "the item is gone", where the card says "skipped by hand" | Have `cards` pass the note from `_superseded_note` to `announce` |
| N3 | `feed.CLAIMED` copies `cards.CLAIMED`, and `USERNAME` is repeated | Move `CLAIMED` into `approvals` beside the statuses |
| N4 | `_decide` prints its answer after the sweep, and Dispatch's SSH call times out at 60 seconds. A hanging feed webhook can take 30 seconds an attempt, three times. The decision is already committed and a retry returns the first answer, but FD4 says a feed failure holds nothing up | Pass a client with a 5-second timeout from `announce`, built from `discord.httpx.Client` so the double still catches it |
| N5 | FD1 reads as every request, but a request with no card gets no line | Amend FD1 to "a request that had a card"; the one-pager lists the unposted |
| N6 | AF1 says nothing about the post appears in #social-drafts before a decision, but the social job's run update posts there, with the summary quote and "Waiting for you". Notes such as "web fonts didn't load" go there too | Keep both, since they are status and ask for nothing. Amend AF1 to "no post text, no image and no request to post" so QA tests the right thing |
| N7 | Splitting a card adds a partial failure a single message never had. If a later piece fails, the sweep posts the whole card again, up to every 20 minutes, and each orphaned first piece keeps live buttons. A press on one answers correctly, but it is noise | On a partial failure, have `post` return the ids it sent and let `cards` delete them before the next try. Add `discord.delete` and teach the double `DELETE`. If this runs long, split it to a follow-up and record that |
| N8 | `"carousel": false` defeats DP3, and a `list` or `tool` layout avoids `needs_visual` on a headline theme | Refuse both in `_card_depth` when the theme sets `carousel`, or when the layout isn't the theme's |
| N9 | No character ceiling on Instagram, and `hashtags_max: 8` | Add `chars_max: 2200` as a gate failure in `check_post`. Lower `hashtags_max` to 5, which costs nothing whether or not my recollection holds |
| N10 | "It goes out on the next publish run, by 18:00 SGT" is false for an approval after the last run starts at 17:40, and for two approvals close together, given the 20-minute gap. AF2 has the same gap | Word it as "on the next publish run today; the last starts at 17:40 SGT". Leave the deadlines alone. If it lapses, the expired line says so |
| N11 | The digest says "waiting in #approvals" for a browser draft with no card (too late, or from before the merge) | Decide `where` from a pending `social-post` request |
| N12 | The drift line states an unproved cause as fact (the PRD says "likely cause, not proved"). A malformed `started_at` raises `ValueError`, which `_from_db` doesn't catch | Word it as "This usually clears with a restart". Wrap the drift read so it returns None on `ValueError` |
| N13 | `DEFAULT_THEMES` has no `words`, so it differs from the shipped config. The `checks.py` docstring leaves out the middle range | Add them |
| N14 | On the portrait card, a long headline wraps at about half the width and leaves the right side empty. My probe used offline fallback fonts, so real widths will differ | Look at it with the web fonts on during ticket 01. Design only |

## Risks

| Risk | Mitigation |
|---|---|
| The first Instagram run is a carousel, not a single image, because every theme but `from-the-toolbox` now has one, and U11 to U13 are still open | The audit checks order and count, any surprise stops the run and pauses publishing, and each card can be skipped. Accepted in PRD §6.2 |
| A brand-gate miss costs the day's post when word ranges rise | B4 gives one source of truth. A drop costs a day and nothing goes out wrongly |
| Meta's terms forbid automated posting | Accepted by Ting Yu at the browser publishing sign-off (BP §4.1) |
| Instagram or Facebook composer limits I couldn't check here | N9, then U12 and U13. Every failure here stops rather than posts wrong |
| Longer sweeps while holding the `approval-cards` lock, with one more post per change | A second sweep does nothing and the next catches up. N4 bounds the wait |
| A wrong merge order turns on live posting before the feed and card fixes are in | The flip is the last commit of ticket 02. `pause publish` or `publish_mode: draft` stops it afterwards |
