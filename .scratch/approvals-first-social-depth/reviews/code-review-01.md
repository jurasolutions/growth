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
