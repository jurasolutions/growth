# Social content agent

Daily posts for Jura's Facebook Page and Instagram, each with something to read and a picture: a
branded image card that draws a diagram of the post's own facts (Ting Yu, 2026-10-31: "more
detailed insights", "no pictures ... so it looks dull"). A platform in `browser` mode is posted
through Chrome once he approves that day's post in `#approvals`. A platform in `draft` mode is the
way back: he posts it himself from `#social-drafts`.

**LinkedIn was dropped on 2026-10-29** (Ting Yu: "drop the linkedin updates. No need to work on
linkedin anymore."). It is switched off with `platforms.linkedin.enabled: false` in
`config/social.yaml`, not removed. A switched-off platform gets no draft, no image, no
`#social-drafts` message, no publish item, no approval card, no browser host and no setup cover,
isn't counted in the digest, is left out of `social skip all`, and the community register takes no
LinkedIn group (by channel or by a linkedin.com address). A card raised before the switch is
superseded at the next sync and its item withdrawn, an item approved before the switch is never
claimed, and neither lifts the publish run's `file_upload` deny. Its settings, brand channel,
card sizes and publish steps stay, so switching it back on brings all of that back.

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
   and fetch only), one core post with insight (what happened, why now, what changes for a small
   business with an example, one thing to do this week), adapted per platform, a file per platform switched on plus
   `sources.md` and `card.json` in `data/growth/work/social/YYYY-MM-DD/`, then
   `jura-growth social submit`.
3. `submit` enforces the rules in code (below), renders the cards, writes
   `outputs/growth/social/YYYY-MM-DD/`, logs `social_posts` and delivers each platform's post by
   its `publish_mode`.
4. For a platform in `draft` mode, Ting Yu copies the post, or skips it, and can record that it
   went out. For a platform in `browser` mode, see "Publishing through the browser" below.

## Commands

| Command | Does |
|---|---|
| `jura-growth social today [--date D] [--json]` | Today's theme and fallbacks with the word range and card needs of each, platform rules, the 14-day history (story URLs, tools, themes), the toolbox's newest and most-used tools, the icons a card may use, and the scratch folder |
| `jura-growth social submit <dir> [--theme ID]` | Check, render, save, log and post the drafts in `<dir>` |
| `jura-growth social render <spec.json> --out <dir> [--size NAME\|WxH ...] [--carousel N] [--source URL ...]` | Render a card on its own, after a brand check of its words. Default sizes: each platform switched on (facebook, instagram); any named size still renders with `--size` |
| `jura-growth social skip <date> <platform\|all> [--reason]` | Don't post that draft. Works before the draft exists too (`tomorrow` is accepted). `all` is every platform switched on |
| `jura-growth social published <date> <platform> [--url]` | Record that a draft went out by hand, for the digest's published count |
| `jura-growth social history [--days 14] [--json]` | Posts in the window, with status, tool and sources |
| `jura-growth social no-draft "<reason>"` | Post "No draft today" with the reason |
| `jura-growth social setup-images [--out DIR]` | Profile picture and a cover for each platform switched on that has one (the Facebook cover; the LinkedIn cover only while LinkedIn is on), into `outputs/growth/setup/social-images/` |

## The submission folder

```
data/growth/work/social/YYYY-MM-DD/
  facebook.md    exactly the text to post, one file per platform switched on
  instagram.md
  sources.md     one line per source: - URL | Publisher | YYYY-MM-DD | Title
  card.json      the image card spec (below)
```

Every http(s) URL in `sources.md` is a source and a story for the no-repeat rule. News themes need
the published date on each line. A file for a platform that is switched off (a leftover
`linkedin.md`) is ignored.

## What `submit` enforces

In this order. Steps 1 to 4 refuse without using up the day's regeneration.

1. **Platforms to draft:** enabled, not skipped, not already drafted today (one post per platform
   per day, `caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY`, held by a unique index).
2. **The folder:** the variant files, a valid card spec, and what the theme needs:
   - source counts, and `ai-news`'s two different sites (`min_hosts`), which compare without `www.`.
     Independence itself stays a prompt rule, and Ting Yu's eye on the card;
   - dates (news within `max_source_age_days`);
   - the theme's own layout, and the tool card for `from-the-toolbox`;
   - `min_items` card items with a detail, an icon on every item and, on the headline layout, a
     `visual` (`needs_visual`);
   - no `"carousel": false` on a theme that goes out as a carousel;
   - **what the picture says, tied to the post:** a figure's value and any other number on the
     card, in digits or in words past a small count ("forty", "nine in ten", "two-thirds", "twice"),
     appear the same way in every variant, read as the numbers rule reads them, so a date or a link
     in the post doesn't count. A `source` label on a figure or an item is
     the publisher on a line of `sources.md`. This doesn't prove a figure true. It means the
     picture says nothing the post and its sources don't, and Ting Yu reads those on the card.
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
| `social-facebook` | The theme's word range (below); 0–2 hashtags on the last line; at least one link; every source in `sources.md` linked; no undeclared third-party links |
| `social-linkedin` | Not used while LinkedIn is switched off; kept for `jura-growth check` and for switching it back on. 120–220 words; up to 3 hashtags, all on the last line; links as Facebook |
| `social-instagram` | The theme's word range (below); up to 5 hashtags on the last line; at most 2200 characters; no URL or domain at all; says "Link in bio" |
| `social-card` | The card's words, every word on the picture included: no links, no hashtags, no markdown. Headline and item titles are checked as headings (sentence case, not a question) |

A word-range miss is a brand-gate failure, so it uses the regeneration. Instagram's hashtag and
character limits are set low on purpose: neither is confirmed from Meta, lowering them costs
nothing, and a caption the composer cut short would read back as a mismatch and pause publishing.

| Themes | Facebook | Instagram |
|---|---|---|
| `ai-news`, `ai-this-week`, `ai-finding` | 160–280 | 130–240 |
| `ai-fun-facts`, `ai-good-read`, `automation-tip` | 120–220 | 110–200 |
| `from-the-toolbox`, and any check with no theme | 90–180 | 80–160 |

`jura-growth check --channel social-facebook` has no theme, so it uses the last row. `prompts/social.md`
holds no ranges: the run reads them from `social today`, which reads this config.

And on all three post channels:

- Plain text: no markdown bold, headings, `[text](url)` links, block quotes or code.
- Quotations of more than 12 words fail (`max_quote_words`).
- Blocked topics (`blocked_topics`: elections, political parties, tragedies) fail.
- A grant or scheme mention needs "Check the official page for current eligibility." and, on
  Facebook (and LinkedIn, while it is on), a `.gov.sg` link. Any sentence implying Jura secures, gets, claims or
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
    {"title": "IMDA opens a programme for smaller firms trying AI", "detail": "It starts with documents.", "source": "IMDA", "icon": "landmark"},
    "A plain string works too, on a theme with no card items to meet"
  ],
  "visual": {"type": "flow", "caption": "How it runs", "steps": [{"icon": "inbox", "label": "It comes in"}, {"icon": "search", "label": "It gets read"}, {"icon": "send", "label": "It goes out"}]},
  "tool": "quote-builder",
  "carousel": true,
  "proper_nouns": ["Acme"]
}
```

(That lists every key. A real card uses `visual` on the headline layout and `tool` on the tool layout.)

| Key | Notes |
|---|---|
| `layout` | `headline`, `list` (2 to 5 items) or `tool` |
| `overline` | Mono label above the headline, at most 32 characters. Defaults to the theme label in `submit` |
| `headline` | At most 90 characters; a statement in sentence case. The tool layout defaults it to the tool's name |
| `subtitle` | At most 150 characters. The tool layout defaults it to the tool's description |
| `caption` | Optional mono line under the subtitle, at most 60 characters (for example "Source: IMDA") |
| `items` | Strings, or `{title, detail, source, icon}` (90, 220 and 40 characters at most). A `source` is a publisher on a line of `sources.md` |
| `visual` | The picture, on the headline layout: see below |
| `tool` | A live slug from the site registry (`repos/landing-page/src/apps/registry.json`) |
| `carousel` | `false` turns Instagram's Monday and Thursday carousel off for this card. It is refused on a theme with `carousel: true`, which is all but `from-the-toolbox` |
| `proper_nouns` | Capitalised names the sentence-case check should accept |

### The picture

`visual` draws a small diagram of the post's own facts (`agents/social/visuals.py`). `design-system/README.md`
§4 rules out stock illustration and scenes drawn in SVG, and says diagrams are fine, so a post has
no photograph. Each theme with `needs_visual` on the headline layout must have one; a list theme's
items carry their icons instead.

| `type` | Keys | Draws |
|---|---|---|
| `flow` | `steps`: 3 to 4 `{icon, label}` | Steps joined by a line, the last in the brand green |
| `compare` | `left`, `right`: `{icon, label, points}`, 2 to 3 points | Two columns, the right one tinted green |
| `figure` | `value`, `label`, `source` | One number from a source, what it counts and who says so. A percentage up to 100, 5 characters at most, sits in a ring |

All take an optional `caption`. The limits are `visuals.LIMITS`: labels 32 characters, points 60,
`caption` 60, `value` 12, a figure's `label` 90 and `source` 40. A figure's value has a digit in it.

Icons are Lucide (the design system's one set), at its 1.75 stroke, vendored with their licence in
`templates/icons/`. Only a name in that folder is accepted, read from the folder's listing, so a name
can't be a path. `social today` lists them. To add one, copy the SVG from Lucide into the folder.

### Sizes

| Name | Size | Use |
|---|---|---|
| `linkedin` | 1200×627 | LinkedIn post (LinkedIn is switched off: rendered only when asked for by name) |
| `facebook` | 1200×630 | Facebook post |
| `instagram` | 1080×1350 | Instagram post. A carousel of up to 5, the card then one slide per item, on any day for a theme with `carousel: true`, and otherwise on Monday and Thursday if the card has items |
| `profile` | 1080×1080 | Profile picture (mark only; `profile-green` is the white mark on the deep green) |
| `linkedin-cover` | 1128×191 | LinkedIn page cover (not in `setup-images` while LinkedIn is switched off) |
| `facebook-cover` | 1640×624 | Facebook Page cover (phones crop the sides, so the words stay central) |

Any `WIDTHxHEIGHT` works with `render --size`.

### How cards are made

`jura_growth/agents/social/templates/` holds `headline.html`, `list.html` and `tool.html`, plus
`card.css` (layout only) and `card.js` (shrinks the type in small steps until nothing overflows,
after the web fonts load), and the `icons/` folder. A card takes its own size from the body, because
headless Chrome's window is shorter than `--window-size` when `card.js` measures. Each template links `design-system/styles.css` by `file://` URL, so
every colour, font, weight, radius and space is a design-system token; there are no raw colour
values in the templates (a test checks). The logo is the design system's own SVG, inlined.

Headless Google Chrome renders each card:
`--headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=W,H
--virtual-time-budget=8000 --screenshot=...` with a throwaway profile. The PNG's size is read back
from its header and must match exactly. Before rendering, one `--dump-dom` pass records which web
fonts loaded (`qa.json`, `fonts_loaded`); if Outfit, DM Sans or IBM Plex Mono didn't, the Discord
post says the images use fallback fonts. `--offline` blocks the network (the tests use it).

`tests/test_social_cards_real_chrome.py` draws every kind of card at 1200×630 and 1080×1350 with
each field at its limit, in real Chrome, and measures every element against the footer. That test
runs on fallback fonts, because the suite stays off the network. Rerun `tests/card_probe.py` with
`offline=False` after a change to the layout, to check the same cards with the web fonts.

## Settings: `config/social.yaml`

| Key | Default | |
|---|---|---|
| `weekends` | `true` | `false` makes the 07:00 job skip Saturday and Sunday (PRD open question 2) |
| `rhythm` | PRD §5.2 (amended 2026-10-30) | Weekday to theme. Fallbacks are the following days' themes, in order |
| `theme_gap_days` | 2 | A theme posted in the last this many days (not counting today) is unavailable in `today` and refused by `submit`, without using the regeneration, so the same kind of post never runs two days in a row. `0` switches it off |
| `themes.<id>` | | `label`, `brief`, `layout`, `news`, `min_sources`, `max_sources`, `min_hosts` (different sites its sources sit on), `max_source_age_days`, `needs_tool`, `words` (by platform, over the platform's own), `carousel` (Instagram posts it as a carousel on any day), `min_items` (card items with a detail), `needs_visual` (a `visual` on the headline layout, an icon on every item) |
| `platforms.<name>` | PRD §5.3 | `label`, `enabled` (`false` switches the platform off everywhere, whatever its `publish_mode`; LinkedIn since 2026-10-29), `words`, `hashtags_max`, `chars_max`, `links` (`post` or `bio`), `image`, `carousel`, `publish_mode` (`draft` or `browser`), `page_url` (the page a browser run posts to; `https://` on the platform's own host; for LinkedIn the company page, `/company/<page>/`, and for Instagram the account's profile, `/<account>/`), `identity` (the posting identity the run must see; defaults to the Jura Solutions page or account) |
| `eligibility_line` | "Check the official page for current eligibility." | |
| `max_quote_words` | 12 | |
| `blocked_topics` | elections, parties, tragedies | Whole words or phrases |
| `verify_links` | `true` | Fetch each source before accepting a draft |
| `render.chrome` | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` | `JURA_GROWTH_CHROME` overrides |
| `render.virtual_time_budget_ms` | 8000 | Time for the web fonts to load |

### The weekly rhythm

Every post is about AI or automation, and each day has its own kind of post (Ting Yu, 2026-10-30:
new toolbox tools, AI fun facts, findings and good reads, and AI news, varied). It replaced the
industry pattern, the explainer and the weekend question.

| Day | Theme | Card | Card items, at least | Sources |
|---|---|---|---|---|
| Mon | `ai-this-week`: 2–3 developments that matter to a small business | list | 2 | 2–3, news, last 7 days |
| Tue | `ai-finding`: one result from a published AI study or survey | headline with a visual | 3 | 1–2, dated, last 30 days |
| Wed | `from-the-toolbox`: a toolbox tool, newest first | tool | none | none |
| Thu | `ai-fun-facts`: 3–4 short, true, surprising facts about AI | list | 3 | 1–4 |
| Fri | `ai-news`: one AI story from the last few days | headline with a visual | 3 | 2–3 on two different sites, news, last 3 days |
| Sat | `ai-good-read`: a newsletter, report, podcast or long read about AI | headline with a visual | 2 | exactly 1 |
| Sun | `automation-tip`: one small thing to automate, with AI or without | headline with a visual | 2 | optional, up to 2 |

Every theme but `from-the-toolbox` goes out on Instagram as a carousel, whatever the day: the card,
then one slide per item.

The 48 hours before 07:00 on a Monday are a weekend, so "AI this week" accepts stories from the
last 7 days (`max_source_age_days: 7`), newest first.

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

## Publishing through the browser (browser publishing PRD, BP-02a, BP-03 and BP-04)

Nothing posts without Ting Yu's approval of that exact post (MC §4.6). The queue (BP-02a) works
from Terminal and the tests; the scheduled `publish` job (BP-03, below) drives Chrome. The
Facebook Page (BP-03) and the Jura Instagram account (BP-04) can be put in `browser` mode, each on
its own once its fixture rehearsal and first live post are done. BP-04 built the Jura LinkedIn
company page too, but LinkedIn was switched off on 2026-10-29: a switched-off platform gets no
item, card or browser host even with `publish_mode: browser`. Its post counts as gone, so the
next `items.sync()` supersedes a waiting card ("LinkedIn page is switched off") and withdraws the
item; until then `use()` refuses it ("turned off in config/social.yaml"). Draft mode is different:
there a waiting card stays live until it lapses (A13).

**Weekends stay on.** This was decided at sign-off (BP1, for the Facebook Page). BP-04 asked again
(BP §6 Q1), and the crew's recorded decision keeps weekends on with every platform switched on in
`browser` mode, so Saturday and Sunday bring up to two approval cards each. To turn weekend
posts off, set `weekends: false` in `config/social.yaml`: the 07:00 social job then skips
Saturday and Sunday, so no weekend draft, item or card is made for any platform. There is no
per-platform weekend switch.

1. `social submit` makes a **publish item** for each platform in `browser` mode whose variant
   passed the brand gate, and raises one `social-post` approval request for it. The card in
   `#approvals` shows the A-id, the page and its URL, the day, the exact text, the image, the
   links in the text, the brand-gate result and "decide by <day>, 18:00 SGT". Drafts written
   before a platform moved to `browser` mode get no item. A platform in `browser` mode without
   `page_url` set gets a note in `#social-drafts` saying why, and no card.
2. Ting Yu approves or skips in `#approvals`. A skip, until the item is claimed, withdraws it and
   records `social skip <date> <platform>`. Unanswered or unclaimed by the end of the posting
   window (18:00 SGT on its day), the request expires and the draft stays as it is.
3. `publish next` claims at most one approved item inside one `BEGIN IMMEDIATE` transaction. In
   that transaction it reads the text and every image once, refuses unless exactly those bytes
   hash to the approval, writes those bytes to `data/growth/work/publish/<A-id>/`, and prints
   that text.
4. The run then records `publish done <A-id> --url <url> --live-text-file <f>`, which marks the
   draft published with its URL, or `publish stopped <A-id> --reason <r>` on a stop signal.

When Instagram's post is a carousel, the item carries every slide, and the card
says "N images attached, posted in this order". The approval covers each slide's bytes in that
order, so changing any slide, or their order, raises a new card.

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
| `jura-growth publish done <A-id> --url <url> --live-text-file <f>` | the publish run | Records the post. The URL must be `https://` on the platform's own host, and for Instagram and LinkedIn the post's own address: Instagram `/p/<code>/` or `/reel/<code>/`; LinkedIn `/feed/update/urn:li:activity:<n>/` (or `share`, `ugcPost`) or a `/posts/…-activity-<n>-…` address. A profile, feed or company page is refused (`hosts.post_problem`). For a community post it is one post's own address inside the item's group, `/groups/<group>/posts/<n>/` or `/permalink/<n>/` (`hosts.group_post_problem`), and the planned post becomes `posted` with `posted_via = browser`. Live text that differs from the approved text (after Unicode NFC, collapsing whitespace and trimming) is recorded, alerts and pauses `publish` |
| `jura-growth publish done <A-id> --outcome <o> [--url <group url>] [--file <q.json>]` | the publish run | What a group join came to (`requested`, `member`, `declined`, `questions`) or that a group's screen takes only personal profiles (`pages-not-allowed`). No alert, no pause. See docs/community.md |
| `jura-growth publish note-rules <group-id> --file <f>` | the publish run that claimed an item in that group | Records the rules seen inside the group and raises a `group-rules` card |
| `jura-growth publish stopped <A-id> --reason <r>` | the publish run | A stop signal (`login`, `captcha`, `checkpoint`, `warning`, `restriction`, `rate-limit`, `removed`, `admin-warning`, `wrong-identity`, `unidentified`): the item stops, `publish` pauses for every item, and `#alerts` gives the reason and the run id. `removed` or `admin-warning` on a group item also does what `community removed` does for that group (AC-P6.2) |
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
- **What the run may do.** `--chrome`, only because `publish` is in `caps.BROWSER_JOBS`;
  `--add-dir` for its own scratch folder only, so the upload tool may read the image copies. The tab tools by name, and the page tools only through one
  `ClaudeInChromeDomain(<host>)` rule per host of each platform switched on and in `browser` mode
  (none of LinkedIn's while it is switched off). The lists are
  `hosts.BROWSER_HOSTS`, one per platform, exact (`www.` and the bare host, plus
  `business.facebook.com` for the Page's composer) until BP-01's check U18 shows how the rule
  treats subdomains. No image CDN, link shim or country host is listed: a run never opens one
  in its tab, and `publish done` refuses a post URL on one. The rules are the union of the
  enabled platforms, because they are set before anything is claimed; the audit holds each run to
  its claimed item's own platform (below). Facebook's rules are also set while `browser` is on
  in `config/community.yaml` (group joins and posts), and a group item's run is held to its own
  group's address.
  Scripting, network, console, shortcut, recording, browser-switching, batch and
  resize tools, `upload_image`, web search and fetch are denied, and `file_upload` too unless the
  item due has an image. Bash runs only `publish next`, `done`, `stopped` and `note-rules`.
- **The prompt** (`prompts/publish.md`) checks the connected browser before `publish next` (no
  browser ends `SKIP:` and claims nothing), opens its own tab, checks the posting identity before
  typing, posts exactly the approved text and images, reads the live post back and records it,
  and closes its tab. Any stop signal ends in `publish stopped`. Each platform has its own
  section, with its target, identity check, posting steps, permalink and stop signals:
  - **Facebook Page:** the Page's composer names the Page, not a person. Permalink on
    `www.facebook.com` with `/posts/` or `story_fbid`.
  - **Instagram:** signed in as the Jura account (its own profile shows "Edit profile"; "Follow"
    or a "Switch accounts" prompt is the wrong identity). Create, Post, then every image in the
    order given, never reordered or edited; the caption typed once; Share once. Permalink
    `https://www.instagram.com/p/<code>/` (or `/reel/<code>/`).
  - **LinkedIn company page** (switched off since 2026-10-29; no LinkedIn item is handed out):
    from the page's admin view, with the company name and logo at the
    top of the composer, never a person's. Permalink
    `https://www.linkedin.com/feed/update/urn:li:activity:<number>/` (or `share`, `ugcPost`).
    `page_url` must be the company page (`/company/<page>/`): a person's profile (`/in/…`)
    raises no item.

  Images go up only through the composer's file input (`find`, then `file_upload` with its ref),
  never by clicking an upload button, which opens a file picker the extension can't see or
  close. The run never uses a "Switch" control to change who it posts as: it stops with
  `wrong-identity` instead.
- **After the run** (`after_run`, before the run row is finished): an open claim becomes
  `unknown`. The transcript audit fails the run and pauses `publish` for:
  - a URL off the claimed item's own platform hosts (any enabled platform's hosts when nothing
    was claimed), asked for or shown as a tab's address in any later result, or a tab address it
    can't read; so an Instagram item posted on the LinkedIn company page or the Facebook Page
    fails;
  - a Discord host;
  - a tool call on a tab the run didn't open;
  - a field typed with anything but an approved text, judged whole and in order, or typing
    before the claim;
  - an upload that isn't the claimed item's own read-only image copy, or a copy that no longer
    hashes to the approved image;
  - images uploaded out of their approved order or more than once, or a run that went on to
    `publish done` with fewer images sent than were approved; a failed or denied upload sends
    nothing (an Instagram carousel's slides go up in order);
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

- **Source addresses with brackets** (for example IRAS's `goods-services-tax-(gst)`) are cut at
  the bracket by the core link finder, so `submit` refuses them and asks for another address.
- **Instagram "Link in bio"** points at jurasolutions.sg, not the article; Instagram news captions
  name the source in words instead.
