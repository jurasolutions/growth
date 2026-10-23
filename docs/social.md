# Social content agent

Daily drafts for Jura's LinkedIn page, Facebook Page and Instagram, with branded image cards,
delivered to `#social-drafts` for Ting Yu to post by hand.

PRD: `jurasolutions/prd/pending/prd-jura-social-content-2026-10-24.md`. Blocks 1 (drafts and
images) and 2 (schedule and history) are built. Block 3 (auto-publishing) is not: `publish_mode`
is `draft` for every platform and any other value is treated as `draft`.

## How a day runs

1. 07:00 SGT: launchd runs `jura-growth run social`. The plug-in's precheck skips the run when
   today's drafts are already in, every platform is skipped, "No draft today" was already posted,
   or it's a weekend and `weekends: false`.
2. Headless Claude follows `prompts/social.md`: `jura-growth social today`, research (web search
   and fetch only), one core post adapted per platform, five files in
   `data/growth/work/social/YYYY-MM-DD/`, then `jura-growth social submit`.
3. `submit` enforces the rules in code (below), renders the cards, writes
   `outputs/growth/social/YYYY-MM-DD/`, logs `social_posts` and posts to `#social-drafts`.
4. Ting Yu copies each post, or skips one, and can record that it went out.

## Commands

| Command | Does |
|---|---|
| `jura-growth social today [--date D] [--json]` | Today's theme and fallbacks, platform rules, the 14-day history (story URLs, tools, themes), the toolbox's newest and most-used tools, and the scratch folder |
| `jura-growth social submit <dir> [--theme ID]` | Check, render, save, log and post the drafts in `<dir>` |
| `jura-growth social render <spec.json> --out <dir> [--size NAME\|WxH ...] [--carousel N] [--source URL ...]` | Render a card on its own, after a brand check of its words. Default sizes: linkedin, facebook, instagram |
| `jura-growth social skip <date> <platform\|all> [--reason]` | Don't post that draft. Works before the draft exists too (`tomorrow` is accepted) |
| `jura-growth social published <date> <platform> [--url]` | Record that a draft went out by hand, for the digest's published count |
| `jura-growth social history [--days 14] [--json]` | Posts in the window, with status, tool and sources |
| `jura-growth social no-draft "<reason>"` | Post "No draft today" with the reason |
| `jura-growth social setup-images [--out DIR]` | Profile picture and the LinkedIn and Facebook covers, into `outputs/growth/setup/social-images/` |

## The submission folder

```
data/growth/work/social/YYYY-MM-DD/
  linkedin.md    exactly the text to post
  facebook.md
  instagram.md
  sources.md     one line per source: - URL | Publisher | YYYY-MM-DD | Title
  card.json      the image card spec (below)
```

Every http(s) URL in `sources.md` is a source and a story for the no-repeat rule. News themes need
the published date on each line.

## What `submit` enforces

In this order. Steps 1 to 4 refuse without using up the day's regeneration.

1. **Platforms to draft:** enabled, not skipped, not already drafted today (one post per platform
   per day, `caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY`, held by a unique index).
2. **The folder:** the variant files, a valid card spec, and what the theme needs: source counts,
   dates (news within `max_source_age_days`), the tool card for `from-the-toolbox`.
3. **No repeats:** no story URL and no tool used in the last 14 days (`caps.NO_REPEAT_DAYS`).
   A story used on the 10th is free again on the 25th. URLs compare without scheme, `www.`,
   tracking parameters, fragment or trailing slash. Drafts count whatever became of them.
4. **Working links:** each source is fetched. 404, 410 or no such host refuses; 401, 403, 429
   and 5xx are accepted with a note (sites that turn scripts away).
5. **The brand gate** (`gate.gate`) on each variant and on the card's words. The first gated
   submission of the day that fails anywhere delivers nothing, lists every reason and posts one
   alert. The second is final: what passes is delivered, what fails is dropped. There is no
   third. If nothing passes, "No draft today" goes to `#social-drafts` with the reasons.
6. **Delivery:** images, the output folder, `social_posts` rows, one message per platform with
   its images (Instagram's carousel as one message), then a message with the sources and the
   folder. If Chrome fails, the text is still delivered and `#alerts` says why.

`submit` runs the same checker as `jura-growth check --channel social-<platform>`; that is PRD
§5.1 step 5.

### Brand channels

The core checker applies the house rules to everything (no exclamation marks, emoji, buzzwords,
urgency, em-dash rhythm, "this, not that", the numbers rule, links only to jurasolutions.sg or
declared sources). The social channels add:

| Channel | Rules |
|---|---|
| `social-linkedin` | 120–220 words; up to 3 hashtags, all on the last line; at least one link; every source in `sources.md` linked; no undeclared third-party links |
| `social-facebook` | 60–120 words; 0–2 hashtags on the last line; links as LinkedIn |
| `social-instagram` | 50–120 words; up to 8 hashtags on the last line; no URL or domain at all; says "Link in bio" |
| `social-card` | The card's words: no links, no hashtags, no markdown. Headline and item titles are checked as headings (sentence case, not a question) |

And on all three post channels:

- Plain text: no markdown bold, headings, `[text](url)` links, block quotes or code.
- Quotations of more than 12 words fail (`max_quote_words`).
- Blocked topics (`blocked_topics`: elections, political parties, tragedies) fail.
- A grant or scheme mention needs "Check the official page for current eligibility." and, on
  LinkedIn and Facebook, a `.gov.sg` link. Any sentence implying Jura secures, gets, claims or
  guarantees funding, or is an approved or pre-approved vendor, fails.
- A news theme needs sources; a tool post must link `jurasolutions.sg/apps/<slug>`.

Words are counted without links and hashtags.

## Card spec

`card.json`, also the input to `jura-growth social render` (the community agent may reuse it):

```json
{
  "layout": "list",
  "overline": "AI this week",
  "headline": "Two AI updates worth a look this week",
  "subtitle": "What changed, and what it means for a small team.",
  "caption": "",
  "items": [
    {"title": "IMDA opens a programme for smaller firms trying AI", "detail": "It starts with documents.", "source": "IMDA"},
    "A plain string works too"
  ],
  "tool": "quote-builder",
  "carousel": true,
  "proper_nouns": ["Acme"]
}
```

| Key | Notes |
|---|---|
| `layout` | `headline`, `list` (2 to 5 items) or `tool` |
| `overline` | Mono label above the headline, at most 32 characters. Defaults to the theme label in `submit` |
| `headline` | At most 90 characters; a statement in sentence case. The tool layout defaults it to the tool's name |
| `subtitle` | At most 150 characters. The tool layout defaults it to the tool's description |
| `caption` | Optional mono line under the subtitle, at most 60 characters (for example "Source: IMDA") |
| `items` | Strings, or `{title, detail, source}` (90, 220 and 40 characters at most) |
| `tool` | A live slug from the site registry (`repos/landing-page/src/apps/registry.json`) |
| `carousel` | `false` turns Instagram's Monday and Thursday carousel off for this card |
| `proper_nouns` | Capitalised names the sentence-case check should accept |

### Sizes

| Name | Size | Use |
|---|---|---|
| `linkedin` | 1200×627 | LinkedIn post |
| `facebook` | 1200×630 | Facebook post |
| `instagram` | 1080×1350 | Instagram post; on Mondays and Thursdays a carousel of up to 5: the card, then one slide per item |
| `profile` | 1080×1080 | Profile picture (mark only; `profile-green` is the white mark on the deep green) |
| `linkedin-cover` | 1128×191 | LinkedIn page cover |
| `facebook-cover` | 1640×624 | Facebook Page cover (phones crop the sides, so the words stay central) |

Any `WIDTHxHEIGHT` works with `render --size`.

### How cards are made

`jura_growth/agents/social/templates/` holds `headline.html`, `list.html` and `tool.html`, plus
`card.css` (layout only) and `card.js` (shrinks the type in small steps until nothing overflows,
after the web fonts load). Each template links `design-system/styles.css` by `file://` URL, so
every colour, font, weight, radius and space is a design-system token; there are no raw colour
values in the templates (a test checks). The logo is the design system's own SVG, inlined.

Headless Google Chrome renders each card:
`--headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=W,H
--virtual-time-budget=8000 --screenshot=...` with a throwaway profile. The PNG's size is read back
from its header and must match exactly. Before rendering, one `--dump-dom` pass records which web
fonts loaded (`qa.json`, `fonts_loaded`); if Outfit, DM Sans or IBM Plex Mono didn't, the Discord
post says the images use fallback fonts. `--offline` blocks the network (the tests use it).

## Settings: `config/social.yaml`

| Key | Default | |
|---|---|---|
| `weekends` | `true` | `false` makes the 07:00 job skip Saturday and Sunday (PRD open question 2) |
| `rhythm` | PRD §5.2 | Weekday to theme. Fallbacks are the following days' themes, in order |
| `themes.<id>` | | `label`, `brief`, `layout`, `news`, `min_sources`, `max_sources`, `max_source_age_days`, `needs_tool` |
| `platforms.<name>` | PRD §5.3 | `label`, `enabled`, `words`, `hashtags_max`, `links` (`post` or `bio`), `image`, `carousel`, `publish_mode` |
| `eligibility_line` | "Check the official page for current eligibility." | |
| `max_quote_words` | 12 | |
| `blocked_topics` | elections, parties, tragedies | Whole words or phrases |
| `verify_links` | `true` | Fetch each source before accepting a draft |
| `render.chrome` | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` | `JURA_GROWTH_CHROME` overrides |
| `render.virtual_time_budget_ms` | 8000 | Time for the web fonts to load |

Monday's theme is "AI this week". The 48 hours before 07:00 on a Monday are a weekend, so it
accepts stories from the last 7 days (`max_source_age_days: 7`), newest first.

## Data

`social_posts`: id, date, theme, platform, text, image_paths (JSON), source_urls (JSON), qa_json,
status (`draft`, `published`, `skipped`), published_url, published_at, plus tool_slug, run_id,
created_at, updated_at. Unique on (date, platform).

`social_skips`: date, platform, reason. Set before or after the draft.

`social_submissions`: each gated submission and each "No draft today", for the one-regeneration
rule and the digest.

## Digest

`social.digest(conn, day)` gives `social_drafts_waiting`, `social_skipped` and
`social_published` (published by `published_at` day), a `#daily-digest` line, and a brief
fragment such as "3 social drafts waiting" or "no social draft today".

## Toolbox registry

Read from `paths.site_repo() / "src/apps/registry.json"` (the landing-page repo). Only `live`
entries count. A missing or empty registry is a note, and `from-the-toolbox` becomes unavailable,
so the run takes the next theme. "Most used" needs usage counts: if growth.db has an `app_usage`
table (`day`, `app_slug`, `opens`, `completions`, as in the website's D1), the last 30 days rank
the tools; otherwise tools are ranked by newest.

## Known issues

- **"were", "well" and "wed" count as "we" in the core numbers rule.** `brand_check.JURA_SELF_RE`
  makes the apostrophe optional (`we'?re`, `we'?ll`, `we'?d`), so a news sentence such as "86%
  were using AI" is read as a figure about Jura and fails. The prompt tells the run to avoid
  those words next to digits until the core pattern requires the apostrophe.
- **Source addresses with brackets** (for example IRAS's `goods-services-tax-(gst)`) are cut at
  the bracket by the core link finder, so `submit` refuses them and asks for another address.
- **Instagram "Link in bio"** points at jurasolutions.sg, not the article; Instagram news captions
  name the source in words instead.
