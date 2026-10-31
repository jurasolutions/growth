# Code review: ticket 01, depth and pictures

Branch `crew/approvals-first-social-depth-01-depth-and-pictures`, commits `ffea6e4..f767351`, reviewed against `crew/approvals-first-social-depth` (merge-base `9374c14`). Paths are relative to the repo.

## Verdict: changes-requested

One blocking finding: **numbers on a card can skip the tie to the post (Standards B1).** Everything else is should fix or nit. The rest of the ticket is sound, and the fix is small.

## Standards

### Blocking

**B1. A number on a card can skip the tie to the post, and part of the hole is in the core numbers rule.**
`jura_growth/brand_check.py:370`, `:391`, `:382-387`, `:521`; `jura_growth/agents/social/drafts.py:166`.

- **Rule broken:**
  - `design-system/README.md` §3: "Never publish a figure the business cannot evidence."
  - PRD §4: "Illustrative figures never go on a live card."
  - `reviews/test-strategy.md` §7: "an unevidenced figure passes the gate" is a critical defect.
  - The branch also claims more than the code does: `prompts/social.md:186-188`, `docs/social.md` and commit `2dc2057` all say "any other number" on the card must be in the post.
- **Why it happens:** `_card_evidence` reads the card through `figures_in`, which inherits every exemption in `_without_exempt`. It also reads digits only.
- **Reproduced:** I put each line below in an item's `detail` on an `ai-news` card, with neither post stating it. All of them passed both `drafts._card_evidence` and the `social-card` gate:

| Text on the card | Why it slips through |
|---|---|
| `62 marketing teams use it`, `40 junior staff saved hours`, `30 decisions a day handled`, `Marketing 62% faster` | `MONTHS` is `(?:jan\|...\|dec)[a-z]*`, so "marketing", "junior" and "decisions" read as months (`:370`) |
| `A 62-percent drop in errors`, `10-times faster than before`, `A 5-million dollar saving` | the "2-step" identifier rule (`:391`) |
| `2000 shops use it`, `1900 owners use it` | the year rule's noun list has no "shops" or "owners" (`:382-387`) |
| `Sixty-two percent of firms tried it`, `Nine in ten firms tried it`, `Forty firms saved hours` | `figures_in` reads digits only (`:521`), and `news_ok` passes number words in the gate |

- **The same hole reaches past social, and it predates this branch.** These pass the core check on the `general` channel, as claims about Jura:
  - `We helped 62 marketing teams.`
  - `Jura served 40 junior staff.`
  - `We cut errors by 62-percent.`
  - `We are 10-times faster.`
  - `Jura has 2000 shops on its books.`

  `MONTHS` is unchanged from `main`. So the core gap is older, but this ticket now relies on it for its guarantee.
- **Fix:**
  1. Make `MONTHS` real month names with a word boundary.
  2. Keep quantity words out of the hyphen rule: percent, times, fold, hundred, thousand, million, billion.
  3. Treat a year followed by a lower-case plural noun as a figure.
  4. Have the card tie also hold number words above `SMALL_COUNT_MAX`, a number word before "percent", and the "nine in ten" shape, so "Two AI updates" on a headline still passes.
  5. Add these inputs to `tests/test_social_figures.py` and the core brand tests, and run the core brand tests for false positives on real dates.

### Should fix

- **S1. The tie can be met by a date, a URL or a hashtag.** `drafts.py:140-142`. `states_figure` searches the raw post. Reproduced: `"62"` is found in `https://x.example/news/62/flow`, `"31"` in `2026-10-31`, `"45"` in `10:45`, `"62"` in `#62`. So a card saying "31 firms tried it" passes on a post that says "released on 31 October" on both platforms. Fix: compare against `brand_check.figures_in(post)`, so both sides are read the same way. That also fixes S2.
- **S2. Honest cards are refused, and the message is wrong.** `drafts.py:142`, with `FIGURE_RE` at `brand_check.py:394`.
  - **Post worded identically, still refused:** `1950s` (read as `1950`), `5G`, `3D`, `2nd`. The message says the post doesn't state it, when it does.
  - **Trailing comma kept:** `Pick 3, then test them` is read as `"3,"`, and `Over 1,000, mostly small firms` as `"1,000,"`.
  - **Impact:** `ai-fun-facts` is the theme most likely to hit this ("the 1950s"). A refusal costs no regeneration, so the post survives, but the only way out is to take the fact off the card. Strip trailing punctuation as part of the S1 fix.
- **S3. Fabricated case study risk in the new ask.** `prompts/social.md:81-84`, against `design-system/README.md` §3 ("no fabricated case study results") and `jurasolutions/CLAUDE.md` ("no fabricated case studies"). The prompt tells the run to name a kind of business and "say what that person's day looks like afterwards", and never tells it to frame that as hypothetical. A post that reads "a clinic now closes its month by lunchtime" reads as a client result, and no check can catch it. Add one sentence: write it as a picture ("Picture a clinic..."), never as something that happened to a real business or client.
- **S4. A stale rule, and a literal figure, in the prompt.** `prompts/social.md:107-109`, `docs/social.md:455-458`. Both say the checker reads "were", "well" and "wed" as "we". It no longer does (`brand_check.py:462-464`, `test_were_and_us_are_not_jura`; reproduced: `86% were using AI` raises no numbers issue). The lines also put "86%" in front of the run, while the developer's own test says "A model copies what it sees". Remove both.

### Nit

- `drafts.py:187`: `normalise_url(...).split("/")[0]` depends on the shape of a comparison key. Use `brand_check.host_of(url).removeprefix("www.")`. It also causes a bug (Spec S1).
- `card.css:396`: `--subtitle-measure: 80ch` is over `--measure-prose` 66ch (`design-system/README.md:115`). It only applies to a landscape carousel slide, and only Instagram gets slides, so no live card uses it. Remove the rule or use the token.
- `config/social.yaml:163-164`, `settings.py:68`: `chars_max` and `hashtags_max` have no `caps.py` constant, and config can raise them (`docs/agents/crew.md:48`). The Standards reviewer called this hard. I rank it a nit: `hashtags_max` has always been a platform setting, and technical N9 specifies config. Move them to `caps.py` if they should be true limits.
- Possible smells (judgement calls):
  - Duplicated Code: `printed_words` and `body` in `render.py:157,166`; the two `words={...}` literals in `settings.py:132-165`, kept in step by a test; `FIT_FLOOR` in `tests/card_probe.py:30` copying `card.js:25`; the `figures_in` and `_numbers` comprehension in `brand_check.py:521,535`.
  - Primitive Obsession: `_publishers` re-splits `source.line` (`drafts.py:147`), where a `Source.publisher` field would fit.
  - Mysterious Name: `needs_visual` now also locks the layout and requires icons.

### Checked, clean

No `CODING_STANDARDS.md` or `CONTRIBUTING.md` exists. `brand_check.py` imports no agent by name. `card.css` has no raw colour or font family. Commit voice matches the card.

## Spec

### Blocking

None of its own. Standards B1 is also the gap against test strategy R2, whose digit cases pass as tested.

### Should fix

- **S1. DP2, two hosts: a query string counts as a host.** `drafts.py:187`. "two on one host... refused". Reproduced: `https://example.com?a=1` and `https://www.example.com?a=2` give two hosts. Separately, `openai.com` and `blog.openai.com` count as two sites, while the prompt says "another site". That meets the PRD's word "hosts", so log the choice or compare the registrable domain.
- **S2. Missing or partial tests.** The code is right in each case; the criterion just isn't pinned.
  - PC1 "Every item on any such theme's card has an icon": `card_items(icons=False)` (`tests/test_social_depth.py:126`) is never called, so no headline theme is exercised.
  - DP3 "cover first": `tests/test_social_depth.py:222` checks filenames only, and nothing asserts the first image is the cover. It runs on a Wednesday where the criterion says Tuesday, which is equally a non-carousel day.
  - R2 "each field of `Visual.words()`... including `value`": `tests/test_social_visuals.py:222` plants label, source and caption only. `value` and the compare's right column have no case.
  - Test strategy's DP2 row: the 4-source refusal on `ai-news` has no case.
  - PC3 "every field at its maximum length": `figure-no-ring-full` is 11 characters against a limit of 12 (`tests/test_social_cards_real_chrome.py:72`). The Spec reviewer probed 12 characters in Chrome and it passes. I didn't rerun that.
- **S3. X3 needs a record.** Appendix A prints `same` for 23 of 24 and `CHANGED` for `tests/test_social.py::test_hashtag_limits_and_position`. The change is legitimate, so QA has to list it under N9 for the gate.

### Nit

- `visuals.py:204`: a percentage over 5 characters (`99.99%`) draws no ring, where PC1 says "a percentage draws a ring". `docs/social.md` records this, but `crew-log.md` doesn't.
- `drafts.py:160-165`: `items[].source` must be a publisher, where PC1 asks this only of a figure. I'd keep it: it stops a made-up "Source:" on a slide.
- `.scratch/.../reviews/samples/`: QA's record per test strategy §2, added early. Harmless, and the 50% is labelled a placeholder.

### Implemented and verified

- **DP1:** boundaries for every theme on both platforms.
- **DP2, DP3, DP5:** two sources and two hosts; items per theme; exit 2 with no `social_submissions` row against "attempt 1 of 2" with one.
- **N8, N9, N13:** all done.
- **N14:** the portrait headline now uses the card's width (viewed in `samples/figure-1080x1350.png`).
- **PC1:** figure source match. **PC2:** `rocket` and `leverage` refused.
- **PC3:** the matrix passes at both sizes on fallback fonts. The web-font record is QA's (X9).
- **Sequencing:** `publish_mode: draft` and `page_url: null` restored in the first commit.
- **Stale wording:** X11 prints nothing.

## Security

No HIGH or MEDIUM finding at confidence 8 or above. Checked:

- **HTML injection:** a payload in every card field comes out escaped (Security reviewer, through `build_html` in memory). `_fill` is single-pass, and each raw `{{{...}}}` slot is escaped first or comes from the design system.
- **Vendored icons:** `LICENSE` is the Lucide ISC text. My grep of all 77 SVGs for `script`, `href`, `style`, `on*`, `foreignObject`, `image`, `use`, `xlink` and `url(` found nothing.
- **Icon names:** `../../etc/passwd`, `Rocket`, ` mail`, the empty string, `rocket`, `a/b`, `*` and `mail.svg` are all refused, and `mail` is accepted (run). `icon_problem` compares exactly against the listing. `icon_svg` itself doesn't guard, but both callers of `load_spec` stop on problems first, and a top-level `icon` in `card.json` is ignored.
- **Network:** an online render fetches only the fixed Google Fonts import. Tests render offline.
- **Secrets and approvals:** no secrets in the diff. The ticket touches no approval, card or publish code. X6 prints nothing.
- **Blocked paths:** none touched. X7 prints nothing, and no live `data/growth` was used.

## UI

Reviewed against the Web Interface Guidelines. The cards are fixed-size images, so the focus, form, touch, hover, navigation, hydration and i18n rules don't apply.

`jura_growth/agents/social/templates/card.css`, `card.js`, `headline.html`, `list.html`, `tool.html`: pass. Notes:

- The guidelines ask for Title Case headings. The design system's sentence case wins (a contradiction, not a finding).
- `card.js` measures the layout to fit the type. That is its job on a fixed canvas, and the rule against it targets responsive pages.
- Empty overline, subtitle and caption are hidden (`card.css:87`). Decorative icons and the ring are `aria-hidden`. Headings use `text-wrap: balance`.

## The questions in the brief

**Can an invented figure reach a card or a post?**
- **Card: yes**, in the forms under B1. The plain digit forms are held: `40%`, `62 firms`, a figure's `value`, and any item or figure source label.
- **Post: yes, by design.** `A small clinic saved 62% of its admin hours with this.` passes on a sourced channel (`brand_check.py:557`). The PRD accepts this ("This doesn't prove the figure true"), so Ting Yu's read of the card is the real control. DP4's example makes that read matter more, hence Standards S3.

**Does it refuse honest posts?**
- `2026`, `26 October` and `GPT-5.5` pass.
- `3 steps` passes if the post says `3`, and is refused with a clear message if the post says "three". That is by design.
- `Claude 4` and `Step 1` follow the same rule.
- Standards S2 lists the honest cards it wrongly refuses. None of these uses the regeneration.

**Would the prompt pass the gate first try on a news day, with the depth he asked for?**
Yes, for a run that follows it carefully. I wrote a Friday `ai-news` draft from the prompt alone: a placeholder story, two sources on two sites, three items, a compare.
- `submit.submit(..., theme_id="ai-news", offline=True)` returned `delivered` on attempt 1: Facebook 226 words, Instagram 173, four Instagram images.
- The four DP4 parts are each asked for, and `social today` prints the ranges and needs for the theme and every fallback.
- This is one hand-written draft with screenshots stubbed, because `jura-growth run` is off limits. Real depth stays Ting Yu's judgement (UAT L3).

Prompt traps that could use the regeneration, none fatal alone:
- **Should fix: item titles are headings, and the prompt doesn't say so.** `prompts/social.md:150-153,160` puts sentence case, "never a question" and `proper_nouns` on the headline only. Reproduced: `Flow Studio reads Purchase Orders` fails as Title Case, and `Does it read handwriting?` fails as a question. A news day names products in its item titles, and every theme now needs items. Say that `proper_nouns` covers item titles, and that item titles follow the headline's rules.
- **Nit: a bare-domain company name.** "Character.AI" or "Perplexity.ai" counts as a link on Instagram and on the card (`BARE_DOMAIN_RE`). One line in the prompt covers it.
- **Nit: "half", "twice" and "double" next to "we" or "our"** fail as figures (reproduced: `We can cut that in half.`). `prompts/social.md:104-106` names digits and number words only.

**Vendored icons:** the licence is kept, no script or link, and a name can't be a path. See Security.

**Was a test loosened?**
No. `test_hashtag_limits_and_position` still tests both sides of the limit: 6 tags fail with "at most 5", and exactly 5 pass. The fixture dropped two tags to fit, and the test guards no approval or privacy rule.
- All 30 `replace()` calls on the fixtures still change something (AST check).
- Removed lines in the tests are fixture text or the old limits.
- `f767351` rewords a docstring and a condition to clear the X5 grep. Chrome still fails rather than skips, and every headline theme is still checked, so nothing was weakened.
- X5 prints nothing.

## Evidence

- `uv run pytest` on the ticket's named files plus the new test files: 427 passed.
- Full suite: 4307 passed, 7 failed. All 7 are in ticket 02's table: `test_publish_items.py` (4), `test_publish_instagram_linkedin.py` (2), `test_publish_run.py` (1).
- Worktree exports on every run. Probes lived in the scratchpad, with temp data folders.

---

# Round 2: fix commits `12fef2e`, `078cf4a`, `322afa7`, `04f9c4e`

Checked at `04f9c4e`. Round 1 above stands as written; this section replaces its verdict.

## Verdict: changes-requested

One blocking finding remains: **a made-up count about Jura still passes the numbers rule (R2-B1).** Round 1's B1 is closed for every form it named. All round 1 should-fixes and nits are closed except the `caps.py` nit, which stays a nit. R2-B1 and one regression (R2-S1) share a root and can go in one commit, so this should be the last round.

## Round 1 findings, checked

**B1, the five forms: closed, on the card and on the core rule.** Each was rerun, not read.

| Form | On a card, post silent | Core rule, about Jura |
|---|---|---|
| Month: `62 marketing teams`, `40 junior staff`, `30 decisions`, `Marketing 62% faster` | refused | `We helped 62 marketing teams.` and `Jura served 40 junior staff.` fail |
| Hyphen: `62-percent`, `10-times`, `5-million` | refused | `We cut errors by 62-percent.` and `We are 10-times faster.` fail |
| Year: `2000 shops`, `1900 owners` | refused | `Jura has 2000 shops on its books.` fails |
| Words: `Sixty-two percent`, `Forty firms` | refused | `Sixty percent of our clients stay.` fails |
| Share: `Nine in ten`, `Two-thirds` | refused | `Nine in ten of our clients stay.` fails |

Each of these cards passes when the posts say the same thing.

| Round 1 finding | Result | Evidence |
|---|---|---|
| Standards S1, tie met by a date, URL or hashtag | closed | `31 October`, `10:45`, `/news/62/flow`, `#62` no longer state a figure (run) |
| Standards S2, honest cards refused | closed | `1950s`, `5G`, `3D`, `2nd`, `Pick 3,` and `Over 1,000,` pass when every post says them (run) |
| Standards S3, fabricated case study | closed | `prompts/social.md:83-85`: "Write it as a picture... never as something that happened to a real business or client" |
| Standards S4, stale "were" rule and its "86%" | closed | removed from `prompts/social.md` and `docs/social.md`; `grep '86%'` finds nothing |
| Prompt, item titles as headings | closed | `prompts/social.md:154-155` and the `proper_nouns` line |
| Prompt nits, bare domains, "half" and "twice" | closed | `prompts/social.md:106,111` |
| Spec S1, query string as a host | closed | `example.com?a=1` and `www.example.com?a=2` give one host (run). A subdomain counts as another host; the commit and `test_a_subdomain_counts_as_another_host` record that choice |
| Spec S2, test gaps | closed | new tests for an icon on every theme, cover first on a Tuesday (it reads the pages, not only the names), a figure's `value` at the gate, the compare's right column, 4 sources refused, a 12-character value |
| Spec S3, X3 record | still QA's | `test_social.py` is untouched by these commits, so Appendix A's one `CHANGED` line is unchanged. QA lists it under N9 |
| Nit, `80ch` | closed | `card.css:396` uses `--measure-prose`, which exists in `tokens/typography.css:35` |
| Nit, host helper | closed | `drafts.py:200` uses `brand_check.host_of` |
| Nit, `chars_max` not in `caps.py` | open, still a nit | no change |

## Standards

### Blocking

**R2-B1. A made-up count about Jura still passes the numbers rule, on every channel.** `jura_growth/brand_check.py:396-403` (year) and `:408-409` (compound).

- **Rule broken:** `design-system/README.md` §3 ("Never publish a figure the business cannot evidence", with "trusted by 90+ companies" as the banned example); `repos/growth/CLAUDE.md` (the numbers rule); `reviews/test-strategy.md` §7, where "an unevidenced figure passes the gate" is critical and no waiver covers it.
- **Reproduced, all passing the numbers rule at `04f9c4e`:**

| Sentence | Form |
|---|---|
| `We helped 2000 small shops.` `Jura served 1999 local owners.` `Our 2000 happy owners stay.` `We served 2000 retail shops in Singapore.` `Our 2000 Singapore shops stay.` | a year-shaped number, then another word, then a noun off the list |
| `We served 100-plus firms.` `We served 50-odd firms.` `Our 500-strong client base grows.` `We have a 500-client base.` `We deliver 6-figure savings.` | a number fused to a word by a hyphen (new to this round: `:408-409` closes percent and times, and leaves these) |

- **On a card, the same forms skip the tie:** `2000 small shops use it`, `1999 local owners use it`, `100-plus firms use it`, `50-odd firms use it`, `A 500-strong client base`, `A 6-figure saving` all pass the tie and the gate with the posts silent.
- These are older than the branch (`main` passes them too). They block because the branch's job is to close this class, and the strategy allows no open critical at the gate.

**Can "2000 small shops" reach a live post about Jura? Yes, if Ting Yu approves it.**
- I put `We helped 2000 small shops do this.` into both posts of the Friday draft. `submit.submit` returned `delivered`: Facebook `pass`, Instagram `pass`, card `pass`, on attempt 1. The checker doesn't stop it.
- What stands after the checker: the prompt forbids a digit in a sentence about Jura, and that is an instruction, not a check. Then Ting Yu reads the post on its approval card (or, in `draft` mode as this branch ships, posts it by hand). So a fabricated client count reaches the public only if he misses it. His read is the only check left.
- The same goes for outreach, since `outreach/queue.py` uses the same core rule. An email saying `We helped 2000 small shops` passes the numbers check and then waits on its own approval.

**The developer's two calls:**

- **"2000 small shops stays a commented limit": not acceptable.** The reason given is that "2026 tax rates" reads alike. That is true only because the exemption is decided before the sentence is read. Inside a sentence about Jura the costs are lopsided: a false refusal costs one rewrite, and a miss is a fabricated client count. The limit also has no test, only a comment at `:397-398`. And the branch doesn't hold the line it defends: `The 2026 tax rates apply to you.` passes while `The 2026 rates apply to you.` now fails (R2-S1).
- **"May needs its capital": acceptable.** `It closes on 30 May`, `It opens on 1 May` and `May 2026` pass, and `30 may apply` counts as a figure. What's left is `We helped 5 May firms`, `We have served 12 Dec firms` and `May 30 staff use it`, which nobody writes, and `it closes on 30 may`, which fails safe. Keep the comment.

**Fix: the outcomes to meet.** How is the developer's choice. One way is to make the year rule depend on the word before the number and on whether the sentence is about Jura, and to add `plus`, `odd`, `strong` and `figure`, and client nouns, to the fused words at `:378`.

| Must fail the numbers rule | Must pass the numbers rule |
|---|---|
| the ten sentences in the table above | `We updated the 2026 tax rates.` |
| | `Our 2026 tax rates guide is free.` |
| | `We can look at your 2026 business plan.` |
| | `Your 2026 business plan is due.` |
| | `The 2026 rates apply to you.` |
| | `In 2026 prices rose.` |
| | `Budget 2026 grants open soon.` |
| | `Plan your 2026 sales target.` |
| | `Book a 30-minute call.`, `Our 45-minute call maps one process.`, `We offer a 30-day trial.` |

A card saying `2000 small shops use it`, `100-plus firms use it` or `A 6-figure saving` must be refused when no post says it, and `A survey from 2026` must still pass. Update the "Known limits" comment at `:467`, which names `forty-odd` and `twenty-plus` "shared with the digit path". The word forms can stay there if the digit forms are closed; say which.

`We wrote our 2026 plans.` fails today; either answer is fine, since it costs a rewrite and names no count.

### Should fix

**R2-S1. Honest copy that passes on `main` now fails the core rule.** `brand_check.py:385` (`_COUNTS_A_PLURAL`). It reaches every channel with no sources, outreach email included (`outreach/compose.py:485`), and social posts with none, where it uses the regeneration.

| Sentence | `main` | Branch |
|---|---|---|
| `Your 2026 business plan is due.` | pass | fails: "2026" needs a source |
| `We can look at your 2026 business plan.` | pass | fails: figure about Jura |
| `Plan your 2026 sales target.` | pass | fails |
| `The 2026 rates apply to you.` | pass | fails |
| `Budget 2026 grants open soon.` | pass | fails |
| `In 2026 prices rose.` | pass | fails |

"business" and "sales" match because the guard takes any lower-case word ending in `s`. `_NOT_A_PLURAL` (`:380`) can't be finished as a list. It fails safe, so it doesn't block alone, but the R2-B1 fix should clear it: the table above pins it.

**R2-S2. A ratio can be no share.** `brand_check.py:449` and `:572` (`_shares`). `Step 2 out of 3.` and `It sends one in five minutes.` now fail with "needs a source" on a channel with no sources, and pass on `main`. Skip a ratio that follows "step" or "page", or that a unit of time follows. `_is_interface_quantity` can't help, because a share has no match object.

### Nit

- `drafts.py:175`: `reversed(...)` inside a dict comprehension, so the first spelling wins. It works; a plain loop reads better.
- `Output x10 overnight` still passes the tie as an identifier. The shape is rare, and `10x` is covered.

## Spec

### Blocking

None of its own. R2-B1 is the open gap against test strategy §7.

### Should fix

None new. The ticket's criteria are met and now pinned: DP1 to DP5, PC1 to PC3, N8, N9, N13, N14. `publish_mode: draft` stays.

## Security

No HIGH or MEDIUM finding at confidence 8 or above. The fix commits add no input path, no subprocess and no file access. They change one CSS custom property and a set of regular expressions. X6 prints nothing (no approval code touched), and no blocked path is touched. No live `data/growth` was used.

## UI

`card.css:396` swaps a value for a design-system token. `tests/test_social_cards_real_chrome.py` still passes at both sizes. Otherwise unchanged.

## Friday walk, again

The same `ai-news` draft through `submit.submit`, screenshots stubbed: `delivered` on attempt 1, Facebook 226 words, Instagram 173, four Instagram images. The first-try traps from round 1 are now in the prompt.

## Evidence

- Brand and social test files, including the new ones: 680 passed.
- Full suite: 4425 passed, 7 failed. The same 7 as round 1, all in ticket 02's table (`test_publish_items.py` 4, `test_publish_instagram_linkedin.py` 2, `test_publish_run.py` 1).
- X5 prints nothing. X6 prints nothing. X7 prints nothing.
- `main`'s `brand_check.py`, loaded beside the branch's, for the `main` column.
- Probes lived in the scratchpad, with temp data folders.

---

# Round 3: commit `0dcd665`

Checked at `0dcd665`. This section replaces the round 2 verdict. The conductor's ruling stands as given: in a sentence naming Jura, we, our or us, any digit fails unless it is an approved claim or the channel's allowance. The round 2 must-pass rows that conflict with it (`We updated the 2026 tax rates.` and the like) now fail by decision, and I don't count them against the branch.

## Verdict: changes-requested

One blocking finding, and the fix is one line: **a figure with a thousands comma, fused to a noun, newly passes (R3-B1).** Round 2's blocker is closed. The conductor can confirm the fix by running the sentences below, without a round 4.

## 1. The newly passing sentences

The developer's list of 174 isn't on disk, so I rebuilt the comparison: `main`'s `brand_check._numbers` against `0dcd665`, over 44,015 unique sentences from every tracked text file (Python strings included), `outputs/growth` and `design-system/README.md`. I can't say whether my set contains all 174, since I don't have theirs. It is wider than the repo alone, which is why it finds more.

| Channel | Newly pass | Newly fail |
|---|---|---|
| general (no sources) | 416 | 279 |
| email | 416, the same sentences | 276 |
| news, with a source | 0 | 236 |

I read all 416.

| What they are | Count | Brand-facing figure? |
|---|---|---|
| A small count followed by a comma (`With 3, on a Tuesday`, `Blocked by: 01, 02`, `substr(ts, 1, 10)`). Values run 0 to 12 only | 409 | No. They now read as the small counts they are, as `5 tips` always did. Nearly all are tickets, crew logs, SQL and JSON |
| `1,900-character cap`, twice | 2 | **Yes, this is R3-B1** |
| `18:00 decide-by` (2), `17:00 decide-by` (1): `main` read "00 decide" as a date | 3 | No. It's a clock time |
| `CVE-2025-27516`, `growth-2026-10-` | 2 | No. They're identifiers |

**Figures about Jura newly passing: none.** Only one of the 416 matches the Jura pattern at all: a review note quoting the host `x.jura-site.pages.dev`, and once the link is blanked it doesn't name Jura. It holds no claim.

**Brand-facing figures with no source newly passing: one form.** The trailing-comma attribution is right for the 409 and hides this one, because the same change opened it.

## Blocking

**R3-B1. `A 5,000-user rollout.` passes on the branch and fails on `main`.** `jura_growth/brand_check.py:410`.

- **Rule broken:** `design-system/README.md` §3; `reviews/test-strategy.md` §7 ("an unevidenced figure passes the gate").
- **Why it happens:** the compound rule blanks `000-user`, leaving `5`. `main` read the remainder as `5,`, which isn't a small count, so it refused it by accident. With the trailing comma gone it reads as `5`, a small count.
- **Reproduced, general channel, no source:**

| Sentence | `main` | Branch |
|---|---|---|
| `A 5,000-user rollout.` | fail | passes |
| `A 2,000-store chain.` | fail | passes |
| `A 12,000-person survey.` | fail | passes |
| `A 12,400-hour project.` | fail | passes |

- **Reach:** every channel with no sources, outreach email included, in a sentence that doesn't name Jura. It also weakens the card tie, which reads this as `5`: a card saying `A 5,000-user rollout.` passes when the posts say only `There are 5 steps.` (run).
- **It blocks** because this branch introduces it, on the rule the whole ticket exists to hold. An unsourced `12,400-hour` is the shape the design system names as not allowed.
- **Fix:** add `(?<![\d,])` in front of the rule at `:410`. Tried in memory: all four sentences above fail again and read whole (`figures_in` gives `5,000`), and `Book a 30-minute call.`, `A 3rd-party tool.`, `A 2-step handover works.`, `Pick 3, then test them.` and `Version 1.2-beta is out.` still pass. Add the four sentences to the core tests, and `A 5,000-user rollout.` to the card tie's table.

## 2. Round 2's sentences

**Must-fail, all closed.** Each fails the core rule on the general, email and Facebook channels, with a source on Facebook, and on a card.

- About Jura (`We helped 2000 small shops.`, `Jura served 1999 local owners.`, `Our 2000 happy owners stay.`, `We served 2000 retail shops in Singapore.`, `Our 2000 Singapore shops stay.`, `We served 100-plus firms.`, `We served 50-odd firms.`, `Our 500-strong client base grows.`, `We have a 500-client base.`, `We deliver 6-figure savings.`, `We helped 62 marketing teams.`): the `social-card` gate fails each one I ran on a card (nine of the eleven).
- The same forms not about Jura (`2000 small shops use it.`, `1999 local owners use it.`, `100-plus firms use it.`, `50-odd firms use it.`, `A 500-strong client base.`, `A 500-client base.`, `A 6-figure saving.`): the card tie refuses each when the posts are silent.
- End to end: `We helped 2000 small shops do this.` in both posts now returns `retry` with the numbers reason on both platforms. In round 2 it returned `delivered`.

**Must-pass, not about Jura: all pass.** `Your 2026 business plan is due.`, `The 2026 rates apply to you.`, `In 2026 prices rose.`, `Budget 2026 grants open soon.`, `Plan your 2026 sales target.`, `Book a 30-minute call.`, `Step 2 out of 3.`, `It sends one in five minutes.`

**The two reported limits:**

- **`The 2000 shops use it.` passes: acceptable.** It passes on `main` too, it doesn't name Jura, and the sentence can't be told from `The 2026 rates apply to you.` without reading its meaning. The same goes for `Your 2000 shops` and `Last 2000 shops`. The cost is that the card tie misses it, so it relies on Ting Yu's read of the card. Pin it with a test, as it has only a comment now (`:422`).
- **`2026 tax rates apply.` at a sentence start fails: acceptable, should fix at most.** It passes on `main`, and `2026 brings new rules.` still passes, so the line is uneven. It fails safe and costs one rewrite (`Tax rates for 2026 apply.`), and a post with a source passes it, since the numbers rule lets a figure through there.

## Should fix

- **R3-S1. A claim about Jura across two sentences.** `We help shops. 2000 of them renew.` passes the general channel, and `We help shops. 62 of them renew.` passes on Facebook with any source. The rule reads one sentence at a time, so this is the one honest gap left in the conductor's rule, and no regular expression closes it fully. Ting Yu's read is the control. The first form has a cheap fix: a year-shaped number before `of` counts (`_YEAR_COUNTS_RE`, `:414`).
- **R3-S2. A noun compound on a card skips the tie.** `A 500-store chain.` passes the tie and the gate. On the gate that is `main`'s behaviour too, and `_FUSED_QUANTITY` (`:384`) closes only client nouns. The tie could treat any compound of three or more digits as a figure, since a refusal there uses no regeneration.

## Nit

- `\bjura\b` also matches `jura-growth`, so 65 lines in docs, config and code comments newly fail if ever checked, nearly all naming `jura-growth` or a `prd-jura-...` file. None of it goes out, so it doesn't matter today.
- Spec S3 is unchanged: QA lists `test_hashtag_limits_and_position` under N9 for X3.

## Scope and security

The commit also edits `prompts/scout.md`, `prompts/community.md`, `prompts/app-factory.md` and `outreach/compose.py`. Each follows from the conductor's ruling, so they are in scope. `tests/test_brand_check.py` moved four sentences from must-pass to must-fail, which is tighter. No new input path, subprocess or file access, and no security finding at confidence 8 or above.

## Evidence

- Full suite at `0dcd665`: 4497 passed, 7 failed, the same 7 ticket 02 tests as rounds 1 and 2.
- Friday `ai-news` draft through `submit.submit`, screenshots stubbed: `delivered` on attempt 1, Facebook 226 words, Instagram 173.
- X5, X6 and X7 print nothing. `tests/test_social.py` is untouched since round 1, so Appendix A is unchanged.
- Scratchpad probes with temp data folders. `main`'s `brand_check.py` was loaded beside the branch's for the comparison.
