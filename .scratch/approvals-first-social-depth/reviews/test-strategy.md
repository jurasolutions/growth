# Test strategy: approvals first, feeds after, social depth

*QA lead, 2026-10-31. Written against `jurasolutions/prd/pending/prd-jura-approvals-first-social-depth-2026-10-31.md` (cited as PRD) and the draft at `a6c2cca`. Acceptance wording follows `reviews/functional.md` section 3 where that review rewords a criterion.*

**What was run for this strategy.** The full suite on the draft (41 failed, 3939 passed, 308s). The 41 failures again with short tracebacks. A throwaway Chrome spike in the session scratchpad, rendering 12 worst-case cards offline. Nothing live was touched, and no file outside this folder was written.

**Three dependencies.**

- `reviews/technical.md` doesn't exist yet, so every seam below is proposed. A disagreement from the tech lead comes back as a question.
- `reviews/functional.md` makes decisions the conductor can overrule (B1 to B6, S1 to S14). Cases that depend on one carry its tag, such as `[B2]`. If a decision is overruled, the case keeps its shape and takes the PRD's value instead.
- Tickets don't exist yet. Test file names are proposals, and the QA report traces to whatever names ship.

## 1. Coverage map

The 18 criteria in PRD §2, one row each. "End to end" means the whole engine through its real commands, with doubles only at the outside edge: Discord, the `claude` binary, Resend and D1. Nothing here reaches a real service.

| Criterion | Level | Seam / location | Data needed | Automated? |
|---|---|---|---|---|
| **AF1** One card with exact text, images in order, sources; nothing asks to post by hand | End to end, plus integration for the maximum case | `submit.submit(offline=True)` then `cards.sweep()`, read at the Discord double. `tests/test_approvals_first.py` | D-DEEP, D-MAX, shipped config | Yes. How it looks in Discord: UAT S1, L3 |
| **AF2** Approval posts it the same day by 18:00; nothing posts unapproved | End to end, plus the existing gate matrix | Card, then `approvals.decide(origin=Origin.ssh())`, then `runner.run("publish")` with `publish_fake`. Clock table at `claim.next_item`. `tests/test_approvals_first.py` | D-DEEP, D-CLOCK, shipped config | Yes. First real post: UAT L4, L5 |
| **AF3** Browser mode with no card gets a note and no hand-post request | Integration | `submit.submit` with the double. Table: no `page_url`, window closed `[B2]`, no images `[B5]`. Every message read for the hand-post phrases in section 3 | D-DEEP | Yes |
| **AF4** A run after the window skips before Claude starts | Integration | `social.precheck` table, then `runner.run("social")` with the fake `claude`: `fake.started` stays empty | D-CLOCK | Yes |
| **AF5** `draft` mode is still the way back | Integration | `submit.submit` with `pw.social_config`. Facebook `draft`, Instagram `browser`, and the reverse, and both `draft` | D-DEEP | Yes. UAT S10 |
| **FD1** One masked line per change, on the right channel | Integration, table-driven | `cards.sweep()` with the double, over the real kinds from the `gate_adapter_*` modules. `tests/test_feed.py` | D-KIND, D-PRIV | Yes. UAT E3 |
| **FD2** No line on a successor or on a claim; the action reports itself | Integration, plus end to end for the action's own message | `cards.sweep()` table. Publish run update and `#outreach-sent` through E2E-1 and E2E-2 | D-KIND | Yes |
| **FD3** A kind applied on decide reports once | Integration | `cards.sweep()`, repeated. Parametrised over `app-build` **and** `group-rules`, which is applied on decide as well | D-KIND | Yes |
| **FD4** A failed line never holds up a sweep or a decision | Integration | Double in `500`, `429`, `unreachable` and `edit-fails` modes, and `discord.post` patched to raise. Two cards, so the second proves the sweep went on | D-KIND | Yes |
| **DP1** Word ranges | Unit, table-driven | `brand_check.check(channel_name="social-<platform>", context={"theme": {"id": ...}})`, at the low and high edge of every theme and platform. `tests/test_social_depth.py` | Generated N-word text | Yes |
| **DP2** `ai-news` needs two sources | Integration | `submit.submit`: 1 source, 2 on one host `[S12]`, 2 hosts, 4 sources | D-DEEP | Yes. Independence itself: UAT L3 |
| **DP3** Card items with details; carousel on any day | Integration, table-driven | `submit.submit` per theme at `min_items - 1` and `min_items`, on a non-carousel day. Slide names and order read from the card's files | D-DEEP, stub PNGs | Yes |
| **DP4** The prompt asks for insight | Unit on the prompt; manual for the result | `prompts/social.md` and `plan.render_text(plan.build(...))`: the four asks, the numbers rule, ranges equal to the config `[B4]`, no stale text | Shipped prompt and config | Prompt yes. Quality: UAT L3, judged by Ting Yu |
| **DP5** A shortfall keeps the regeneration; a word miss doesn't | Integration | `submit.submit`: exit code 2 and no `social_submissions` row on a shortfall; "attempt 1 of 2" and one row on a word miss. In one test, a shortfall then a word miss then a pass | D-DEEP | Yes |
| **PC1** Diagrams, and an icon on every item | Unit, then integration | `visuals.parse` and `visuals.render` tables. `submit.submit` refuses a headline card with no visual, and a bare item on any `needs_visual` theme. `tests/test_social_visuals.py` | D-VIS | Yes |
| **PC2** Allow-listed Lucide icons, tokens, brand check on every word | Unit, plus integration at the gate | `visuals.icon_problem` table. Each `Visual.words()` field planted with a banned word through `submit.submit` and `social render`. Stroke, SVG safety and token checks over the shipped files | D-VIS | Yes. UAT P2 |
| **PC3** Both sizes, nothing overflowing, real Chrome | Integration in real Chrome, plus a recorded visual review | `render.build_html` with `images.run_chrome(offline=True)` and the probe in section 2. `tests/test_social_cards_real_chrome.py`, no skip allowed | D-VIS | Yes, plus the QA record. UAT P1 |
| **SC1** The one-pager flags steady drift and not a late wake | Unit table, then integration at the read model | `health.schedule_drift` table. Run rows through `mission_world.source()`, `health.strip` and `one_pager.text`, using the job list in `config/settings.yaml`. `tests/test_schedule_drift.py` | D-DRIFT | Yes. Real launchd: UAT L2 |

### The test data

| Name | What it is |
|---|---|
| **D-DEEP** | `TIP` and `NEWS` in `tests/test_social.py`, made deep. `TIP`: Facebook 120–180 words, Instagram 110–160, at least 2 detailed items with icons, a visual. `NEWS`: Facebook 160–180, Instagram 130–160, the same 2 items with icons added. These bands sit inside both the default and the theme range on purpose, so the tests in class C pass without a changed line. Every substring a test replaces (`for you.`, `invoice`, `#Automation`, `#Singapore`, `Link in bio for more small automations.`) stays |
| **D-MAX** | Facebook at 280 words with 3 long source addresses, Instagram at 240 with 4 slides, plus one post containing a code fence and one with a `> ` line |
| **D-VIS** | Each visual kind at its minimum and at every `visuals.LIMITS` and `render.LIMITS` value. A figure with a ring, a figure with no ring, `100%`, `120%`, `3.5x`. A list card with 5 items and icons, and carousel slides. A card with the real words of the `uat.md` Part P samples, for the record |
| **D-KIND** | One request of each of the seven kinds from the gate adapters, each in each state. A completeness test: `set(approvals.kinds())` equals the FD1 table, so a new kind with no channel fails |
| **D-PRIV** | `tests/sweep.py` `planted()`: secrets and personal values in the rows behind each card's title and `close_reason`, then `assert_clean` |
| **D-CLOCK** | Pinned through `JURA_GROWTH_NOW`: 07:05, 16:59, 17:00, 17:01, 17:20, 17:40, 17:41, 17:59, 18:00, 18:05, 22:00, a Saturday |
| **D-DRIFT** | Run rows from the SC1 wording in `reviews/functional.md`, plus the cases in section 3 |

## 2. Real Chrome: how PC3 is measured

Chrome 156 is on this Mac, and the seam works offline. The spike rendered 12 worst-case cards in about 14 seconds. It proved the seam, not the criterion, because of two things it found.

**1. The page sees a shorter window than the picture has (`V1`).** With `--window-size=1200,630`, scripts report `innerHeight` 487, in both `--dump-dom` and `--screenshot`. At 1080×1350 they report 1207. The screenshot then lays out again at full height: the footer rule sits at 350 in the DOM and 493 in the PNG. So:

- A probe that simply reads `--dump-dom` measures a layout that never reaches the picture. `scrollHeight` as worded in `reviews/functional.md` PC3 would be checking the wrong page.
- `card.js` `fit()` runs against the short window. A card shrinks more than it needs to. Every maximum-length card hit the 0.56 floor, and a flow's labels end up very small at 1200×630. This predates the draft, but diagrams make it matter. Ticket 1 should look at it. It is a legibility problem rather than a clip, so it isn't an automatic failure of PC3.

**2. Offline means fallback fonts.** `design-system/tokens/fonts.css` loads Outfit, DM Sans and IBM Plex Mono from Google, and none is vendored. Text widths differ with the real fonts, and the worst-case cards leave little room: read by eye from the PNGs, a 1080×1350 compare ended about 3px above the footer rule, and a list's subtitle at 1200×630 about 5px above it.

The automated test therefore takes two passes, in a helper such as `tests/card_probe.py`:

1. Run Chrome with the production arguments and read `data-fit` from the DOM, so the test uses the scale the real picture gets.
2. Measure the page's height shortfall, then load the same page in a window that really is W×H, with `--fit` forced to that value and `fit()` turned off. Read `getBoundingClientRect` for every visible element under `.main`.

**A pass** means every element is inside the card and above the top of `.foot`, and no text box has `scrollWidth > clientWidth`. The oracle is independent of `card.js`'s own `overflowing()`, which checks only some elements. The PNG from the production pass must also be exactly W×H.

**The matrix:** flow-3, flow-4, compare, figure with a ring, figure with no ring, at minimum and maximum lengths, plus the list and carousel slides with icons, each at 1200×630 and 1080×1350. If a maximum case fails, the fix is a tighter limit or a real fit, never a lighter test.

**Every render uses `offline=True`.** Chrome is a subprocess, outside `NetworkGuard`, so the only protection is the resolver rule in `images.run_chrome`. A unit test asserts the rule is in the argument list.

**Recorded by QA, not in pytest:**

- Each PNG in the matrix is opened and viewed. The record lists file, `data-fit`, and whether any word is clipped or overlaps.
- The same matrix once more with `offline=False`. This is the single network touch in this strategy: Chrome fetches public font files from Google, as every live render already does, sends no Jura data, and contacts no Jura service. PRD §4 bars it from the suite, which is why it stays out. If the conductor rules it out as well, it becomes the waiver W1 in section 6. Ting Yu still sees every picture before approving it.

## 3. Risk-based depth

Riskiest first. Each has negative cases and at least one end-to-end path.

### R1. A post or email goes out without approval of that exact content

Public and irreversible, and this change switches browser posting on in shipped config.

- **Keep unchanged:** the gate matrix (`test_approval_gates.py`, `gate_adapter_*`), `test_terminal_refusal_every_kind.py`, and the field-change supersede tests in `test_publish_items.py`.
- **New, with the shipped `config/social.yaml` rather than `pw.social_config`:** with both platforms in browser mode, `publish next` hands out nothing while the request is pending, skipped, expired, superseded or paused.
- **New:** after approval, changing the text, an image, the image order or the page address supersedes the request, and nothing posts.
- **New:** shipped modes and addresses are asserted exactly: Facebook `browser` at `https://www.facebook.com/jurasolutionssg`, Instagram `browser` at `https://www.instagram.com/jura_solutions/`, LinkedIn off.
- **E2E-1, social day.** Shipped config, real `social submit`, two cards. Approve one and skip one. A publish run with the fake binary claims only the approved one, and its run update carries the address. One feed line each, and no second line on the claim.

### R2. A figure on a picture Jura can't evidence

The numbers rule is non-negotiable.

- Negative table through `submit.submit`:
  - a figure with no `source`
  - a figure whose `source` matches no publisher in `sources.md` `[S1]`
  - a figure on a theme with no sources
  - a figure about Jura ("Jura saves 62%")
  - a results figure inside a flow label or a compare point
  - a figure in `items[].detail`
- Each field of `Visual.words()` is proved to reach the `social-card` check, including `value`, `label`, `source` and `caption`.
- `V2`: `render.py` and `visuals.py` take `source` as a free label today, so `[S1]` is new code.

### R3. A hand-post request in browser mode, or a post made twice

- Every message from E2E-1 and from the AF3 table is scanned for `by hand`, `post it`, `Copy the text`, `social published` and `Posted it?`, in all channels. The scan first asserts the double saw messages.
- The merge-day case stays: a draft already written that day gets no item, and no post (`test_drafts_written_before_a_platform_moved_to_browser_get_no_item`).
- A rollback case is added: flip a platform back to `draft` with a card open. The card closes with one line, nothing posts, and the next day's post has hand-posting text.
- `#social-drafts` before a decision may hold only the run update and a note. An allow-list, so anything else fails.

### R4. Feed lines lost, doubled, false, or leaking

- **The change table, over all seven kinds:**

  | Change | Lines |
  |---|---|
  | pending → approved, approved → used | 1, then 0 |
  | pending → used in one sweep gap, not applied on decide | 1 |
  | pending → used, applied on decide | 1, never again |
  | pending → skipped | 1 |
  | pending → expired | 1 |
  | approved → expired | 1 more, 2 in all |
  | approved → skipped | 1 more, 2 in all |
  | superseded with a successor | 0 |
  | superseded on changed content, no successor yet `[S4]` | 0 |
  | item gone, no successor | 1 |

- **Exactly-once:** a second and third sweep add nothing. Two sweeps under the lock give one line. With `#outreach-sent` failing, one outbox entry that replays once.
- **`edit-fails`:** one follow-up in #approvals and still one feed line.
- **Masking:** `assert_clean` over all seven kinds, including a line built from `close_reason` and a title falling back to `approval.reason`. The title comes from `first_piece`, so one case uses a card that split.
- **`@everyone` in a title:** the line carries `allowed_mentions: {"parse": []}`.
- **A request that never got a card:** no line, pinned as `reviews/functional.md` note 5 rules. No webhook for #approvals also means no lines.
- **E2E-2, outreach:** `send-due` raises a card, approve gives one line, the send gives one `#outreach-sent` message through the Resend stub, and no email is sent before approval. **E2E-3, apps:** the factory's `app-build` approved gives one line. An `app-release` goes through approve, then claim.
- **E2E-4, silence `[B3]`:** at 18:05 the digest upkeep expires both cards, gives two lines and an expired count of 2, and nothing posts.

### R5. A deep post breaks its own card

Measured with `discord.split`: a 280-word post with three long sources makes a 2,417-character card, in 2 pieces, each with one unpaired fence. This confirms `reviews/functional.md` B1.

- With D-MAX: rejoin the pieces, and every line of the post appears in order, unchanged.
- Each piece is well formed for the chosen quoting `[B1]`, including a post that itself holds a fence or a `> ` line.
- Status line and buttons on the first piece, and the images beside them `[B1]`.
- The first-line edit changes only the status and keeps the rest.
- Ten files is still the limit, and a carousel never reaches it.
- What Ting Yu approves is what posts: planted phone number and titled name in the post, card shows them in full `[S9]`, and `assert_clean` still holds for every other surface.

### R6. Deadlines

Table at `claim.next_item` and `approvals.decide`, on D-CLOCK:

- Approve at 16:59: both platforms post at the 17:00 and 17:20 slots.
- Tap at 17:01: answers `expired` `[B2]`.
- `create_social` at or after the decide-by: no item, and the AF3 note.
- Approved and unclaimed at 18:00: one `expired` line saying "approved but not used in time".

The feed's promise of a post is tested against this table: no line says "it goes out" when no slot is left. A paused publisher changes the line `[S8]`.

### R7. A picture that is clipped, off-brand or unsafe

- PC3's matrix in section 2.
- `V3`: a visual's words go into the page through `_text`, and its icons through the allow-list. A table plants `<img src=x onerror=...>` and `<script>` in each field and asserts it comes out escaped. The page runs from `file://` with scripts on, so this isn't cosmetic.
- Icon names: `../../etc/passwd`, `Rocket`, ` mail`, an empty string, and `rocket`, which isn't vendored.
- Each vendored SVG: parses, has `stroke-width` of 1.75 after `icon_svg`, uses `currentColor`, and holds no `script`, `href` or `style`. The folder has a Lucide `LICENSE`.
- `test_templates_use_design_system_tokens_only` stays, and is extended: it doesn't look inside `icons/`, and every `var(--x)` in `card.css` must be defined either in the design system or in `card.css`.

### R8. SC1 cries wolf or stays silent

A table on `schedule_drift`, with the job list from `config/settings.yaml`:

| Runs | Expected |
|---|---|
| Two jobs at −9h, twice | Flag, "about 9 hours" |
| Every daily job at −9h | Flag |
| One job at −9h | None |
| Two jobs at −9h and +3h | None |
| Late wake, 09:30 then 08:10, on two jobs | None |
| Same wake time two days running, jobs due at different times | None |
| Latest run on time after a run off | None, so the line clears after the restart |
| 29 minutes off, 30 minutes off | None, flag |
| Second run differs by 5, then 6 minutes | Flag, none |
| A run across midnight, ±12h | Correct sign and hours |
| A skip row counts as a start | Pinned |
| A job with one run, or none | Ignored |
| Non-`daily` schedules (`daily_every`, `business_days`) | Ignored |

Also: `runs` table absent or empty, and a job with a malformed `daily` or an unparsable `started_at`, must not break the one-pager. The read model writes nothing (ADR 0002): `_recent_starts` is covered by the existing `stat_snapshot` check. The shipped list must have at least two `daily` jobs, so the check can actually fire.

## 4. The 41 failing tests

All 41 were read and rerun. **None may be deleted or skipped, and none may pass by lowering a rule through config.** There are three classes.

### Class A: rewrite, because each guards an approval, privacy or shipping rule (11)

The assertion changes because the correct behaviour did. The rule it guards must end up as strong or stronger. "Must survive" is what the gate checks in the rewritten test.

| Test | Rule it guards | Rewrite to | Must survive |
|---|---|---|---|
| `test_publish_items.py::test_every_platform_ships_in_draft_mode` | What ships switched on | An **exact** map of each platform's mode, address and `enabled` switch | Exact equality. `{"draft", "browser"}` membership is loosening |
| `test_publish_items.py::test_publish_mode_is_draft_or_browser_and_auto_is_gone` | Only two modes exist | First line only: the shipped map | `auto` still raises `SettingsError` |
| `test_social.py::test_carousel_days_and_publish_mode` | The same | Line 276 only: the shipped map | Carousel days and the `auto` refusal, as written |
| `test_publish_items.py::test_submit_raises_one_social_post_request_for_facebook_only` | One card, exact content | The links line per `[B1]`, the decide-by per `[B2]` | Exactly one request, exact text, identity, address, day, brand-check line, file list |
| `test_publish_instagram_linkedin.py::test_submit_raises_exactly_one_social_post_request_for_the_platform_in_browser_mode[instagram]` | The same | The pointer block becomes "no message for this platform in #social-drafts" | Every card assertion. **Exactly one** request |
| Same test, `[linkedin]` | The same | The same | The same |
| `test_publish_items.py::test_the_social_drafts_message_for_facebook_points_at_the_card` | The post's text and images don't leak out of the card; draft mode keeps hand-posting | Rename. Browser platform: no text, no file, no message. Draft platform: one message with files and the hand-post words | Both halves. This becomes the core AF1 and AF5 test |
| `test_publish_items.py::test_browser_mode_without_a_page_url_falls_back_to_posting_by_hand` | No item without an address | Rename. Invert the last assertion: `by hand` absent everywhere, a note naming `page_url` in #social-drafts | No item, reason shown |
| `test_publish_items.py::test_social_post_cards_and_the_pointer_carry_nothing_planted` | Privacy | No pointer now. Decide a card, so the planted label reaches a **feed line** | `assert_clean` unchanged, with the marker reaching the card and the line. Coverage grows |
| `test_publish_run.py::test_nothing_planted_reaches_discord_from_a_publish_run` | Privacy on every publish message | Fails at `assert 9 == 4`: 4 run updates plus 5 approved lines. Assert **4 and 5 separately** | Every scenario and `assert_clean`. `>=` or removing the count is loosening |
| `test_publish_items.py::test_a_saturday_draft_on_a_browser_platform_raises_a_request` | The deadline on a weekend | The fixture, and one literal if `[B2]` stands | A pending request bound to that day's deadline |

### Class B: rewrite, because they describe the old hand-post flow (4)

Each keeps its assertions under a pinned `pw.social_config(browser=())`, so it becomes an AF5 guard, and gets a browser-mode twin.

| Test | Rewrite to |
|---|---|
| `test_social.py::test_submit_delivers_everything` | Pinned draft mode, every assertion kept. The twin asserts files, rows and two cards under shipped config |
| `test_social.py::test_submit_monday_news_with_carousel` | The same. The twin asserts the slides on the Instagram card, in order |
| `test_social_linkedin_off.py::test_submit_drafts_renders_and_posts_nothing_for_linkedin` | Pinned draft mode keeps `len(posts) == 3`. The twin asserts none under shipped config. All LinkedIn absences stay |
| `test_social.py::test_word_ranges` | The new numbers, literally. LinkedIn's stays. DP1's table covers the rest |

### Class C: fixtures only, every assertion stays exactly as written (26 cases, 24 test functions)

The cause is `TIP` and `NEWS` being too thin, so a submission is refused before reaching what the test checks. **Fix D-DEEP, and leave the test function identical.** Appendix A's script proves it.

These are the ones that matter most, because each guards a rule, and would be easy to "fix" by weakening:

- `test_a_variant_that_fails_the_brand_gate_gets_no_item_and_no_request`: no card without the brand gate.
- `test_drafts_written_before_a_platform_moved_to_browser_get_no_item`: no double post on merge day.
- `test_on_a_carousel_day_the_instagram_card_carries_every_slide_in_order`: ADR 0003 covers each slide and its order.
- `test_social_submit_says_refused_when_the_fixture_is_refused`: the fixture host stays locked.
- `test_submit_raises_a_card_only_for_the_enabled_platform_in_browser_mode`: a switched-off platform gets no card.
- `test_brand_failure_allows_one_regeneration`, `test_second_failure_drops_only_that_variant`, `test_nothing_passes_posts_no_draft_today`: the two-attempt rule.
- `test_repeated_story_is_refused_without_using_the_regeneration`, `test_broken_source_link_is_refused`: refusals that keep the regeneration.

The rest are:

- `test_publish_items.py::test_linkedin_and_instagram_in_draft_mode_raise_nothing`
- In `test_social.py`:
  - `test_fixture_variants_pass[facebook, instagram]`
  - `test_news_variants_pass_with_their_sources[facebook, instagram]`
  - `test_hashtag_limits_and_position`
  - `test_tool_theme`
  - `test_tool_theme_without_a_tool_card_is_refused`
  - `test_theme_gap_zero_switches_the_variety_rule_off`
  - `test_two_runs_pick_different_stories`
  - `test_render_failure_still_delivers_text`
  - `test_skip_before_the_draft`
  - `test_skip_after_the_draft_and_published`
  - `test_digest_figures`
  - `test_precheck`
  - `test_runner_skips_the_job_once_drafts_are_in`

A functional decision may force a change here, for example `[B5]` altering `test_render_failure_still_delivers_text`. Then the changed line and the decision's id go in the QA report, and Appendix A's `CHANGED` line is read against that list.

### What counts as loosening

Any of these fails the gate:

- Deleting, skipping or `xfail`-ing a listed test.
- Turning off `min_items`, `needs_visual`, `min_sources` or a theme's `words` through config in any test outside the depth and visual test files.
- Replacing an exact value with a range or `in`, or a count with `>=`.
- Dropping a `assert_clean`, or letting the sweep pass with no marker seen.
- Changing `TIP` or `NEWS` so a test's `replace()` silently no longer changes anything.

## 5. Non-functional

- **Security and privacy.** R1, R4, R7. `NetworkGuard` and `WriteGuard` stay on for the whole suite. Nothing is run with live folders.
- **Migration and rollback.** No new migration is expected; if one appears, it is checked against an older checkout, as the operating card asks. R3 covers both directions of the mode change. The rollback remains `publish_mode: draft` and a revert of the merge.
- **Performance.** Keep the new Chrome tests under 60 seconds of suite time. At the spike's rate (12 cards in about 14 seconds, each with a screenshot and a DOM pass) that fits. The suite took 308 seconds on the draft, and the card's 132 is out of date. Reported, not gated.
- **Browsers.** Only Chrome draws cards, on this Mac. Nothing else applies.
- **Accessibility.** The cards are pictures in social feeds. Colours are tokens, and the PRD asks for no alt text. Phone-size legibility is checked by eye in UAT P1, with `data-fit` recorded for each case.

## 6. Not tested, and why

| Gap | Why | Covered instead by | Who accepts |
|---|---|---|---|
| Real Facebook and Instagram posts (U12, U13) | PRD §4 and the brief: nothing live may run | The fake binary, the fixture site in UAT S2 and S3, then UAT L4, L5 | Ting Yu, PRD §6 question 2 |
| Chrome closed in a real run (U11) | Needs the real extension | `NO_BROWSER` in `test_publish_run.py`, UAT S7. Fails safe, ending `SKIP:` | Ting Yu, PRD §6 question 2 |
| Real Discord: split cards, quoting and buttons as they look | No test touches Discord | The double records payloads and piece boundaries. UAT S1 on his test server | Ting Yu |
| Real launchd, and the cause of the 9 hours | PRD §1 "not proved"; the probe was refused; launchd is his | The detector is tested on run rows. UAT L2 is the real test | Ting Yu |
| Whether a post has real insight (DP4), whether a second source is independent (DP2), whether a figure is what the source says (R2) | Judgement, and needs the model and the web | The prompt, the host check and the publisher match, then his eye on each card. UAT L3 | Ting Yu, and each card waits for his approval |
| Claude writing the drafts | No real model in tests | The fake binary; `social submit` gets checked files | QA lead |
| **W1.** Real fonts in the suite | PRD §4 bars the network from tests | The recorded render in section 2, or the G4 waiver | QA lead; Ting Yu if waived |
| A crash between the card's `UPDATE` and the feed post | `_edit_changed` commits first, so the line is lost and never doubled. Rare, and the card still shows the truth | Noted, no test | QA lead |
| A decision during another sweep waits for the next one | Functional note 4. Delay only, with nothing lost | The lock case in R4 | QA lead |
| UAT parts on a test Discord server | QA has no webhooks, and those steps make real Discord calls | Harness items H1 to H7 get automated seed tests. QA dry-runs Part P and every seed scenario at `JURA_GROWTH_DISCORD=off`. Steps needing a server stay his | Ting Yu at G4 |

**Findings for ticket 1, not gaps:**

- `V1`: `fit()` runs against a window 143px too short.
- `V2`: a figure's source is a free label (same as S1).
- `V4`: `submit.py:210` lets a card's `"carousel": false` opt out of DP3's "on any day". Either refuse it on a `carousel: true` theme, or say in the PRD that it is allowed. The test pins whichever the conductor picks.
- `V5`: `DEFAULT_THEMES` in `settings.py` carries DP3's values but not DP1's `words`, so a config with no themes section gets the old ranges for news. The DP1 table runs on shipped config, and one test pins the defaults to it, or the defaults drop.

## 7. Exit criteria

The gate reruns everything on the release branch, with the worktree exports from `docs/agents/crew.md`. Each is met or not met from its check alone.

**Defect severity.**

- **Critical:** anything can post or send without approval of that exact content; a planted value reaches Discord; an unevidenced figure passes the gate; a write to `inputs/`, `design-system/` or live `data/growth/`.
- **Major:** any §2 criterion fails; a hand-post request in browser mode; a feed line lost or doubled outside the crash case; a clipped or overlapping picture at either size; any item on the "loosening" list.
- **Minor:** wording, stale docs that don't change a run, polish with nothing clipped.

| # | Criterion | Check |
|---|---|---|
| X1 | Full suite passes with no skips | `uv run pytest -rs -p no:cacheprovider -o addopts=""` prints 0 failed, 0 errors, no `SKIPPED` line, and at least 3980 passed (the draft's 3939 + 41) |
| X2 | Each of the 18 criteria traces to a passing case | Every row of section 1 names a test or a recorded case in a `reviews/qa-*.md`. The named test appears as passed in X1 |
| X3 | Class C unchanged | Appendix A prints `same` for all 24 functions. Any `CHANGED` line must be listed in a QA report with its functional decision's id |
| X4 | Classes A and B rewritten, not loosened | A QA report has one line per test in the two tables with its new name, and "must survive" confirmed by reading it. No listed test is missing |
| X5 | No rule lowered through test config | `git diff main...HEAD -- tests ':!tests/test_social_depth.py' ':!tests/test_social_visuals.py' \| grep -E '^\+.*(min_items\|needs_visual\|min_sources\|["'"'"']words["'"'"']\|words=)'` prints nothing, and no `+` line adds `skip` or `xfail` |
| X6 | Approval code and its tests unchanged | `git diff --stat main...HEAD -- jura_growth/approvals.py jura_growth/approvals_cli.py jura_growth/origin.py jura_growth/caps.py jura_growth/agents/publish/claim.py 'docs/adr/0003-*' 'docs/adr/0004-*'` prints nothing. `git diff --numstat main...HEAD -- tests/test_approval_gates.py 'tests/gate_adapter_*' tests/test_terminal_refusal_every_kind.py` shows 0 deleted lines, or each deleted line is a clock literal listed in a QA report under `[B2]` |
| X7 | Blocked paths untouched | `jurasolutions/` isn't a git repository, so check by time: `find /Users/tingy/OneDrive/Desktop/projects/jurasolutions/inputs /Users/tingy/OneDrive/Desktop/projects/jurasolutions/design-system -type f -newermt "$(git log -1 --format=%cI a6c2cca)"` prints nothing, or only files Ting Yu changed himself, each named in a QA report. `git diff --name-only main...HEAD` lists nothing under `data/` |
| X8 | Real Chrome ran | X1 shows the PC3 file's cases passed, not skipped. Every render call in it has `offline=True` (`grep -c`). A `qa-*.md` lists each PNG with its size, `data-fit` and result, for the fallback fonts |
| X9 | Real fonts | The same record for the online render, or W1 listed for G4 |
| X10 | Functional's blockers closed | For each of B1 to B6, `crew-log.md` records the decision (taken or overruled), and a `qa-*.md` names the passing case. S-findings that the conductor takes are traced the same way |
| X11 | Prompt and docs agree with config | The DP4 test passes. `grep -nE '60–120\|50–120\|One or two sources\|copies it from' prompts/social.md docs/social.md` prints nothing |
| X12 | Defects | 0 open critical, 0 open major. Each minor has an owner |
| X13 | Code review | Every `code-review-*.md` ends with an approving verdict and no open blocker |
| X14 | Nothing live ran | Every `qa-*.md` lists its commands. None is `jura-growth run`, `schedule install`, `schedule render` or a real send, and every shell had the temp data exports. `uat.md` was dry-run per section 6, and any step corrected |
| X15 | UAT | Parts P to C of `uat.md` run by Ting Yu with results recorded, or listed as a waiver for G4. The PR body opens with "What merging switches on" and names any part not run, since merging is his acceptance (PRD §7) |

**Waivers Ting Yu may grant at G4:** X9, and X15. Nothing else. No waiver covers a critical or major defect, because a broken approval rule can't be accepted by a merge he hasn't read for.

## Appendix A: the class C check

Copy to a scratch folder and run from the worktree root. It compares each function's parsed form between `main` and the working tree, so comments and formatting don't count. Run on the draft today, it prints `same` 24 times.

```python
import ast, subprocess

CLASS_C = {
    "tests/test_publish_fixture_merge.py": ["test_social_submit_says_refused_when_the_fixture_is_refused"],
    "tests/test_publish_instagram_linkedin.py": ["test_on_a_carousel_day_the_instagram_card_carries_every_slide_in_order"],
    "tests/test_publish_items.py": [
        "test_linkedin_and_instagram_in_draft_mode_raise_nothing",
        "test_a_variant_that_fails_the_brand_gate_gets_no_item_and_no_request",
        "test_drafts_written_before_a_platform_moved_to_browser_get_no_item",
    ],
    "tests/test_publish_linkedin_off.py": ["test_submit_raises_a_card_only_for_the_enabled_platform_in_browser_mode"],
    "tests/test_social.py": [
        "test_fixture_variants_pass", "test_news_variants_pass_with_their_sources", "test_hashtag_limits_and_position",
        "test_brand_failure_allows_one_regeneration", "test_second_failure_drops_only_that_variant",
        "test_nothing_passes_posts_no_draft_today", "test_repeated_story_is_refused_without_using_the_regeneration",
        "test_broken_source_link_is_refused", "test_tool_theme", "test_tool_theme_without_a_tool_card_is_refused",
        "test_theme_gap_zero_switches_the_variety_rule_off", "test_two_runs_pick_different_stories",
        "test_render_failure_still_delivers_text", "test_skip_before_the_draft", "test_skip_after_the_draft_and_published",
        "test_digest_figures", "test_precheck", "test_runner_skips_the_job_once_drafts_are_in",
    ],
}


def functions(source):
    return {n.name: ast.dump(n) for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}


for path, names in CLASS_C.items():
    old = functions(subprocess.run(["git", "show", f"main:{path}"], capture_output=True, text=True, check=True).stdout)
    new = functions(open(path, encoding="utf-8").read())
    for name in names:
        assert name in old, f"{name} is not on main"
        print("same" if new.get(name) == old[name] else "CHANGED", path, name)
```
