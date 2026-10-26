# Social content agent

Daily drafts for Jura's LinkedIn page, Facebook Page and Instagram, with branded image cards,
delivered to `#social-drafts`. A platform in `draft` mode is posted by Ting Yu by hand; a platform
in `browser` mode is posted through Chrome once he approves that day's post in `#approvals`.

PRD: `jurasolutions/prd/pending/prd-jura-social-content-2026-10-24.md`. Blocks 1 (drafts and
images) and 2 (schedule and history) are built. Block 3 is replaced by browser publishing
(`prd-jura-browser-publishing-2026-10-25.md`, which supersedes the social PRD's §1 last sentence,
§2 criterion 5, the "Later block", §5.6 block 3 and §6 question 3; see its §3.3): the Graph API,
the Posts API, `publish_mode: auto` and the two-hour skip window are dropped. `publish_mode` is
`draft` (the default, and every platform today) or `browser`.

## How a day runs

1. 07:00 SGT: launchd runs `jura-growth run social`. The plug-in's precheck skips the run when
   today's drafts are already in, every platform is skipped, "No draft today" was already posted,
   or it's a weekend and `weekends: false`.
2. Headless Claude follows `prompts/social.md`: `jura-growth social today`, research (web search
   and fetch only), one core post adapted per platform, five files in
   `data/growth/work/social/YYYY-MM-DD/`, then `jura-growth social submit`.
3. `submit` enforces the rules in code (below), renders the cards, writes
   `outputs/growth/social/YYYY-MM-DD/`, logs `social_posts` and posts to `#social-drafts`.
4. For a platform in `draft` mode, Ting Yu copies the post, or skips it, and can record that it
   went out. For a platform in `browser` mode, see "Publishing through the browser" below.

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
| `platforms.<name>` | PRD §5.3 | `label`, `enabled`, `words`, `hashtags_max`, `links` (`post` or `bio`), `image`, `carousel`, `publish_mode` (`draft` or `browser`), `page_url` (the page a browser run posts to; `https://` on the platform's own host), `identity` (the posting identity the run must see; defaults to the Jura Solutions page or account) |
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

`publish_items` (the publish plug-in's migration): one row per publish item, with its frozen
content, its day and its lifecycle (`ready`, `claimed`, `done`, `stopped`, `unknown`,
`withdrawn`), the live URL and whether the live text matched. It holds no approval state: that
lives only in `approvals`, under the subject `publish_item:<id>`.

## Publishing through the browser (browser publishing PRD, BP-02a and BP-03)

Nothing posts without Ting Yu's approval of that exact post (MC §4.6). The queue (BP-02a) works
from Terminal and the tests; the scheduled `publish` job (BP-03, below) drives Chrome.

1. `social submit` makes a **publish item** for each platform in `browser` mode whose variant
   passed the brand gate, and raises one `social-post` approval request for it. The card in
   `#approvals` shows the A-id, the page and its URL, the day, the exact text, the image, the
   links in the text, the brand-gate result and "decide by <day>, 18:00 SGT". That platform's
   `#social-drafts` message points at the card instead of repeating the post. Drafts written
   before a platform moved to `browser` mode get no item. A platform in `browser` mode without
   `page_url` set is posted by hand as before, with a note.
2. Ting Yu approves or skips in `#approvals`. A skip, until the item is claimed, withdraws it and
   records `social skip <date> <platform>`. Unanswered or unclaimed by the end of the posting
   window (18:00 SGT on its day), the request expires and the draft stays as it is.
3. `publish next` claims at most one approved item inside one `BEGIN IMMEDIATE` transaction. In
   that transaction it reads the text and every image once, refuses unless exactly those bytes
   hash to the approval, writes those bytes to `data/growth/work/publish/<A-id>/`, and prints
   that text.
4. The run then records `publish done <A-id> --url <url> --live-text-file <f>`, which marks the
   draft published with its URL, or `publish stopped <A-id> --reason <r>` on a stop signal.

Any change to the text, the images or their order, the page, the posting identity or the day
supersedes the request and raises a new card over the new content, with deadlines from the new
content's day, and the item freezes the new content. A claim or a decision that finds the change
raises the card at once; one the heartbeat finds is raised by the next `publish next` (and, from
BP-03, by the publish job's precheck, which runs the same `items.sync()` every slot). Posting the draft by hand (`social published`) or skipping it (`social skip`)
supersedes the request too, and then the item is withdrawn with no new card. The hash covers the
exact bytes, with no Unicode normalisation (ADR 0003).

| Command | Who | Does |
|---|---|---|
| `jura-growth publish next [--json]` | the publish run | Claims at most one item, or prints "nothing due" with the reasons |
| `jura-growth publish done <A-id> --url <url> --live-text-file <f>` | the publish run | Records the post. The URL must be `https://` on the platform's own host. Live text that differs from the approved text (after Unicode NFC, collapsing whitespace and trimming) is recorded, alerts and pauses `publish` |
| `jura-growth publish stopped <A-id> --reason <r>` | the publish run | A stop signal (`login`, `captcha`, `checkpoint`, `warning`, `restriction`, `rate-limit`, `removed`, `admin-warning`, `wrong-identity`, `unidentified`): the item stops, `publish` pauses for every item, and `#alerts` gives the reason and the run id |
| `jura-growth publish queue [--json]` | Ting Yu | Every item, its state and its A-id |
| `jura-growth publish resolve <A-id> posted --url <url>` or `not-posted` | Ting Yu only (refused in any scheduled run) | Settles an item whose outcome is unknown |

**Limits, in `jura_growth/caps.py`**, which `config/publish.yaml` may only tighten: one post per
platform per day, one item per run, 20 minutes between the start times of the runs that claim two
items, and claims only from 09:00 to 18:00 SGT. A cap counts an item from its claim, so a stopped
or unknown item still uses its platform's day. The PAUSE file, `pause publish`, `pause all`,
auto-pause after three failed runs and `publish_mode: draft` each stop every claim, and the
approval stays unused.

**A claim left open.** If a run ends having claimed an item without `done` or `stopped`, the
item becomes `unknown`: it is never claimed again, `publish` pauses, and `#alerts` names
`/growth publish resolve A-nnnn posted --url <url>` and `… not-posted`. A claim left by a run
whose process died is settled the same way by the next run, and `publish resolve` also settles a
claim nobody will close: one whose run has ended, or one made in Terminal with no run.
`/growth publish queue` and `/growth publish resolve …` work from Discord too.

### The `publish` job (BP-03, ADR 0005)

Every 20 minutes from 09:00 to 17:40 SGT, every day (`daily_every` in `config/settings.yaml`).

- **Precheck, before Claude starts.** With `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` in
  the environment the run is skipped and says why, because either one silently removes the Chrome
  tools; `jura-growth status` lists the variable as a setup gap. Otherwise the precheck runs the
  queue's `items.sync()` and posts any fresh card, then asks whether anything can be claimed. If
  not, the slot is a quiet run ("nothing due") and no Claude starts.
- **What the run may do.** `--chrome`, only because `publish` is in `caps.BROWSER_JOBS`; no
  `--add-dir`. The tab tools by name, and the page tools only through one
  `ClaudeInChromeDomain(<host>)` rule per Facebook host (`hosts.BROWSER_HOSTS`) while Facebook is
  in `browser` mode. Scripting, network, console, shortcut, recording, browser-switching, batch and
  resize tools, `upload_image`, web search and fetch are denied, and `file_upload` too unless the
  item due has an image. Bash runs only `publish next`, `done` and `stopped`.
- **The prompt** (`prompts/publish.md`) checks the connected browser before `publish next` (no
  browser ends `SKIP:` and claims nothing), opens its own tab, checks the page shows the Jura Page
  as the posting identity before typing, posts exactly the approved text and images, reads the
  live post back and records it, and closes its tab. Any stop signal ends in `publish stopped`.
- **After the run** (`after_run`, before the run row is finished): an open claim becomes
  `unknown`. The transcript audit fails the run and pauses `publish` for:
  - a URL off the publish hosts, asked for or shown as a tab's address in any later result, or
    a tab address it can't read;
  - a Discord host;
  - a tool call on a tab the run didn't open;
  - a field typed with anything but an approved text, judged whole and in order, or typing
    before the claim;
  - an upload that isn't the claimed item's own read-only image copy, or a copy that no longer
    hashes to the approved image;
  - a click, key, input, upload or navigation after `publish stopped`;
  - a never-tool.

  A tab left open is a warning. A run that found no browser alerts once a day. The tab address
  is read only from the tab context that ends each result, never from page text, and nothing a
  page holds can make the audit raise. If the checks fail for any reason at all, the run fails
  with a fixed reason naming it, and publishing pauses (`publish.after_run` fails closed).
- **No model text goes out.** Every publish run's summary and error are written from the item's
  record: the A-id, the platform, what happened, the URL or the closed stop reason, and the run
  id. The model's own summary and `FAIL:` line stay in the transcript.
- **Run updates** (`run_update: claimed-only`) post in `#social-drafts` only for a run that
  claimed an item. Stops, mismatches and unknown items also go to `#alerts`, once each: a stop's
  one alert comes from `publish stopped` and names the run, whose transcript keeps what the page
  showed (there is no screenshot file).
- **Transcripts** of publish runs hold page text, so they are kept 7 days
  (`caps.BROWSER_TRANSCRIPT_DAYS`), not 30, and so are the files a run leaves in
  `work/publish/` (its read-back live text and its image copies).

## Digest

`social.digest(conn, day)` gives `social_drafts_waiting`, `social_skipped` and
`social_published` (published by `published_at` day), a `#daily-digest` line, and a brief
fragment such as "3 social drafts waiting" or "no social draft today".

`publish.digest(conn, day)` adds the day's publish items: `publish_posted`, `publish_skipped`,
`publish_expired` and `publish_stopped`, and a "Publishing: …" line, on days that had items.

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
