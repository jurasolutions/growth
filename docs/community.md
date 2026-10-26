# Community scout

Finds Singapore SME groups (mostly Facebook groups) by web search and drafts a weekly plan of
value-first posts that Ting Yu posts himself. Built against
`prd/pending/prd-jura-community-scout-2026-10-24.md`, blocks 1 and 2.

**Nothing is posted by code.** Meta removed the Groups API's publishing permission in April 2024,
and driving an account with browser automation breaks Meta's terms. The run never fetches
facebook.com either. The domains it may not fetch have one list, `blocked_fetch_domains` in
`config/community.yaml` (Facebook's own domains are always on it). The community plug-in turns
each domain into two Claude Code rules for this job, `WebFetch(domain:facebook.com)` for the
domain and `WebFetch(domain:*.facebook.com)` for every subdomain, so adding a domain to the list
blocks it with no edit to `config/settings.yaml`. Each entry must be a bare domain: a URL, path or
port would make rules that match nothing, so the job refuses to start and the run fails with an
alert instead. `add-group` refuses source URLs on those domains,
and `community audit-run` proves the run fetched none of them from its transcript.

## How a Monday goes

1. **07:30 SGT**, launchd runs `jura-growth run community` (`prompts/community.md`).
2. `jura-growth community context --json` records any ticked checklist items first, then gives the
   register, the groups a plan may use and their open days.
3. **Register (block 1).** Web search for groups; facts only from search results and
   non-Facebook pages. `community add-group --file` records them; `community summary` posts the
   register to `#community`.
4. **Joins (block 1b)**, only with `browser: true`: the run proposes joins as the Jura Page for
   good-fit groups from `context`'s `joins.candidates`, up to `joins.left` (the weekly cap less
   the week's proposals), with `community propose-join <id>`. It never opens a group itself.
5. **Plan (block 2)**, only for groups marked joined and good fit: up to 3 posts written fresh
   per group and 2–3 reply ideas, through `community plan-add --file`, then
   `community publish-plan` writes `outputs/growth/community/YYYY-Www.md` and posts it.
   With no joined good-fit group the run ends `SKIP:`.
6. **During the week** Ting Yu posts by hand and ticks the checklist or runs
   `community posted <item-id> [url]`.
7. The **digest** reports the register, joined count, posts planned and posted this week, and
   audits that day's community run for Facebook fetches.

## What Ting Yu does

- Join the good-fit groups you want, as yourself (see "Open questions"). Read each group's real
  rules inside, then:
  `jura-growth community set <id> joined=yes rules="<the rules as stated>" rules_confirmed=yes`
  That records the rules and raises a `group-rules` card in #approvals (MC §5.7). Nothing in
  Terminal confirms rules or sets open days. Confirm the card from Discord, typing the open days:
  `/growth approve A-nnnn promo_days=<days> post_days=<days>`. Every group needs both day fields,
  whatever its rules say: each is `any` (no day limit), `none`, or days like `sat,sun` or
  `mon-fri`. For "No promotion on weekends", that is `promo_days=mon-fri post_days=any`; for rules
  that say nothing about days, `promo_days=any post_days=any`. An approve without both days is
  refused. Skip the card, or leave it for 14 days, and the rules stay unconfirmed: posts there
  carry no link, and the group has no open day.
- `community set` refuses `promo_days=` and `post_days=`, and refuses `rules_confirmed=yes` when
  the group has no rules text yet ("set the rules first"). However a yes is spelled or quoted
  (`yes`, `y`, `true`, `1`, `on`, `"yes"`), it only raises the card. Running `rules_confirmed=yes`
  again names the card already waiting. New rules text clears the confirmation and the days, and
  raises a new card. Rules the community run found by web search never raise a card by themselves.
- **To change a confirmed group's days**, run `community set <id> rules_confirmed=yes` again. It
  raises a new card over the same rules; approve it with the new days and they replace the old
  ones. Skip it, or leave it for 14 days, and the group keeps the confirmation and days it had.
  `rules_confirmed=no` unconfirms a group at once, with no card.
- **Groups confirmed before group-rules approvals** keep their confirmation and days. A one-off
  pass writes each down once as a `community.group.rules_confirmed_earlier` event, before the next
  community run or `community set`, and then never runs again: a confirmation that appears later
  without a decision is not written down as history. A group confirmed before ticket 07 has no
  days and stays closed: run `community set <id> rules_confirmed=yes` and confirm its card with
  the days. `jura-growth community groups --joined` lists them, with "no post until Ting Yu
  confirms the open days".
- Post the plan's items yourself, then tick `- [x]` in the checklist or run
  `jura-growth community posted <item-id> [url]`.
- If an admin removes a post or warns you: `jura-growth community removed <group-id>`. The group
  becomes `skip` for good and its planned posts are skipped.

## Commands

| Command | Does |
|---|---|
| `community context --json` | Records checklist ticks, then the week, limits, register, plannable groups with parsed rules and open days, this week's plan, recent texts, live tools |
| `community add-group --file <json>` | One group, a list, or `{"groups": [...]}`. Validates, dedupes by URL (and name), rejects Facebook source URLs |
| `community groups [--fit] [--joined] [--channel] [--json]` | The register |
| `community set <id> key=value ...` | `joined=yes`, `joined_as=page` (or `profile`, `none`), `rules="..."`, `rules_confirmed=yes`, `fit=...`, `fit_reason=...`, `notes=...` (also audience, size_hint, active_hint, name). `rules=` and `rules_confirmed=yes` raise a `group-rules` request; days are typed only in its decision. New rules text clears the confirmation and the days |
| `community plan-add --file <json>` | Weekly plan items, checked in code, then brand-gated |
| `community publish-plan [--week]` | Writes the checklist and posts it to `#community`. With `browser: true`, each planned post in a group joined as the Jura Page also gets a `community-post` card in `#approvals` |
| `community propose-join <group-id>` | With `browser: true`: a `group-join` card for a good-fit group not joined as the Jura Page, up to the weekly join cap. Exit 1, with the reason, when the group can't be proposed |
| `community posted <item-id> [url]` | Records a post (or a used reply idea) |
| `community sync-ticks` | Records ticked `- [x]` items from every week's checklist |
| `community removed <group-id>` | Permanent skip |
| `community summary [--no-post]` | The register summary for `#community` |
| `community audit-run <run-id> [--json]` | Scans that run's transcript for any fetch of a Facebook domain; exit 1 if it finds one |

### A group record

```json
{"channel": "facebook", "name": "…", "url": "https://www.facebook.com/groups/…",
 "audience": "…", "size_hint": "about 40,000 members, per <source>", "active_hint": "…",
 "promo_rules": "promo Saturdays only", "fit": "good fit", "fit_reason": "…",
 "source_urls": ["https://<a non-Facebook page>"], "notes": "…"}
```

`channel` may be facebook, linkedin, telegram, whatsapp, sbf, asme, event, forum or other (PRD
§5.4). A Facebook group's `url` must be its facebook.com/groups link: recorded for Ting Yu, never
fetched. `source_urls` needs at least one non-Facebook page. `fit` is `good fit`, `possible` or
`skip`, always with a reason. `promo_rules` is required; "not stated in public sources" is a
valid value and reads as unknown.

### A plan file

```json
{"week": "2026-W44",
 "posts": [{"group_id": 4, "day": "2026-10-31", "text": "…", "rules_ok": "…", "sources": [], "image_path": null}],
 "replies": [{"group_id": 4, "question": "…", "text": "…"}]}
```

`day` is a date in that week or a weekday name. `rules_ok` is required when the group's rules
can't be read in code. `sources` are official pages for any statutory figure (used by the numbers
rule, never linked in the text).

## What `plan-add` checks in code

Structural problems reject the whole plan and store nothing, without touching the brand gate:

- Only Facebook groups marked joined, good fit and not removed.
- **Cap:** at most 3 groups a week (`caps.COMMUNITY_GROUPS_PER_WEEK`; config may lower it), one
  post per group per week.
- **Rotation:** no group within 14 days of its last suggested or posted item
  (`caps.NO_REPEAT_DAYS`; config may lengthen it).
- **Days:** the day is in the plan week and not past, and it is one Ting Yu opened. Code never
  reads days out of the rules text: day, frequency and holiday rules ("promo Saturdays only",
  "#FridayPromo thread", "once a week") are too easy to invert or miss. Every group has no open
  day, in `context`'s `days_open` or in a plan, until Ting Yu types both `promo_days` and
  `post_days` in the group's `group-rules` decision; then only those days count, and the
  checklist's "Planned as" line shows them.
  `promo_days` limits promotional posts and `post_days` limits every post. A post is
  promotional when it mentions Jura or carries a link. When the rules seem to mention timing,
  the register listing and the checklist say "the rules mention timing, so check the day
  against them"; that hint never opens a day. Rules still parse in code for bans
  (`agents/community/rules.py`): "no self-promo" and "no links" are bans, and a links ban
  stated beside a day rule ("promo Saturdays only, no links") is kept. Rules the parser can't
  read need a `rules_ok` statement.
- **Words:** posts 60–150, reply ideas 10–120.
- **Distinct texts:** no sentence of four or more words shared with another group's post this
  week or any post from the last 28 days, and word-trigram overlap at most 0.25.
- **Links:** only when the group's rules are known, confirmed by Ting Yu, and allow promotion and
  links. Then: only in the closing line, which is the only line that may mention Jura; at most one
  toolbox tool link and the home page or `/apps`; only jurasolutions.sg; every link carries
  `utm_source=facebook_group&utm_campaign=<group slug>`; the tool must be live in the site
  registry, and with live tools one of them must be linked. Unknown or unconfirmed rules: no link
  at all. Rules that forbid promotion: no link and no mention of Jura.
- **Reply ideas:** a question, no links, at most 3 a week.
- No tagging, "DM me", or asking for members' details.

Then each item goes through the brand gate on its own channel (`community-post`,
`community-reply`; links to jurasolutions.sg only), item key `community:<week>:post:<group>` or
`community:<week>:reply:<n>`. Passing items are stored; a failing item may be regenerated once.

## The checklist

`outputs/growth/community/2026-W44.md`: per post the day, the group link, a `- [ ] Post item N`
line, a rules reminder (with whether Ting Yu confirmed them), the image and the text as a quote;
then the reply ideas with their own item ids. `sync-ticks` (run by `context`, `plan-add` and
`publish-plan`) reads `- [x] … item N` from every week's file, so ticks in earlier weeks are
recorded on the next run; republishing a week keeps its ticks.

## Data

`community_groups` and `community_posts` per PRD §5.5, plus `slug` (the utm campaign),
`url_key` (dedupe), `removed`, `source_urls_json`, `run_id`, and on posts `question` and
`posted_via`. Migration `agents/community/migrations/0001_community.sql`.

Browser publishing (`prd-jura-browser-publishing-2026-10-25.md` §4.3, §5.6) adds three columns in
`0003_joined_as_the_page.sql`, without changing any existing row:

- `joined_as`: `none`, `profile` or `page`. It is written as `joined_as_set` and read as
  `joined_as`; a group joined before this build (`joined = 1`, nothing recorded) reads as
  `profile`, because Ting Yu joined it as himself.
- `pages_allowed`: `unknown`, `yes` or `no`. `no` means only personal profiles can join or post
  there, so nothing is raised or claimed for the group.
- `join_status`: `requested`, `member` or `declined`, once a join item's run records it.

## Posting and joining as the Jura Page (browser publishing)

Off by default: `browser: false` in `config/community.yaml`. With `browser: true`:

- `community publish-plan` raises a `community-post` card for each planned post in a group joined
  as the Jura Page. On the checklist and in `#community` those posts have no box to tick and say
  they go out through `#approvals`: don't post them by hand. Posts in other groups stay on the
  checklist for you to post as before.
- `community propose-join <group-id>` raises a `group-join` card for a good-fit group that isn't
  joined as the Page, doesn't take only personal profiles, and has no join requested. At most
  `joins_per_week` (hard cap 3) are proposed in an ISO week; one proposed after Sunday's 18:00
  counts in the next week. A proposal you skip, or leave to expire, still counts toward its week's
  three, so the pace never goes above three a week. A join is decided by 18:00 on the Sunday of its
  week.
- **How a join goes** (the publish run, `prompts/publish.md`, after you approve the card). The run
  opens the group and checks that the Jura Page is the identity the join would use. Another
  identity selected is a stop (`publish stopped --reason wrong-identity`): `publish` pauses and
  `#alerts` says so. A screen with no way to join as a Page is not a stop: the run records
  `publish done <A-id> --outcome pages-not-allowed`. Otherwise it clicks Join once and records
  `--outcome requested` (waiting for an admin), `member` or `declined`, which sets the group's
  `join_status`; `member` also sets `joined_as = page`. Posting there still waits for your
  `group-rules` decision on its rules and open days.
- **Only personal profiles.** `pages-not-allowed`, from a join, its answers or (BP-05) a post
  composer, sets `pages_allowed = no` and `fit = skip` ("only personal profiles can join or post"),
  supersedes every card still waiting for that group, and the group is never proposed again. It
  neither alerts nor pauses.
- **Rules seen inside a group.** When the run sees the group's rules on the join screen, in the
  questions or in its About panel, it records them with `publish note-rules <group-id> --file
  <rules.txt>`, which raises one `group-rules` card. Rules you already confirmed, seen unchanged,
  raise nothing; rules that differ replace the researched text and clear the old confirmation and
  days. Only the publish run that claimed an item in that group may record them; researched rules
  never raise a card.
- If a group asks membership questions, the run submits nothing: it closes the form and records
  `publish done <A-id> --outcome questions --file q.json` with the questions and its drafted
  answers. The answers pass the brand gate first (a failure raises nothing; the run may fix them
  once, and a second failure drops them). Then they come to you as their own `group-join` card,
  decided by 18:00 on the third day after they are raised. Only once you approve it does a later
  run submit exactly those answers; if the form's questions have changed by then, it submits
  nothing and sends the new questions back to you the same way. A fresh card for changed answers, or for
  a group whose address changed, gets its own three days.
- `publish next` hands a community post out only on its day, in a good-fit group joined as the
  Page whose rules and open days you confirmed, on a day they leave open, with one community post
  a day, three groups an ISO week and 14 days between posts in one group. A promotional post (a
  link, or Jura named) also needs the rules to allow promotion (promotion days of `none` allow
  none), and a post with a link needs rules that are known and don't forbid links. A join goes out only
  inside three joins an ISO week. Turning `browser` off again stops every claim without using the
  approvals.
- Changing a post's text, image, group or day, a group's URL, or a join's answers supersedes its
  card and raises a fresh one on the same item, unless `browser` is off: then no card is raised
  until it is on again. A post whose group is no longer joined as the Page, was removed or takes
  only personal profiles has its card superseded with no new one.

## Decisions and open questions

- **Open question 1, to be confirmed by Ting Yu:** posts go up as Ting Yu personally,
  mentioning Jura Solutions in the closing line (`post_as` in `config/community.yaml`). If he
  decides on the Jura Facebook Page instead, change `post_as` and the prompt's closing-line
  example; nothing else depends on it.
- **Open question 2:** 3 groups a week to start (`groups_per_week: 3`, the hard cap).
- **Links need confirmed rules.** Rules found by web search are recorded as stated, but a link
  goes in only after Ting Yu has read the group's real rules and approved their `group-rules`
  card. No group has an open day until he types its days in that decision.
- **Promotion days apply to promotional posts.** `promo_days=sat` doesn't stop a plain value
  post on a Tuesday; it does stop the Jura closing line on a Tuesday.
- **Source URLs must be real pages.** A search results page is not a source; the run cites the
  article or directory page it saw the group on.
- **Images** come from the social agent's `jura-growth social render` if that command exists at
  run time (`context` reports `image_renderer`); nothing depends on it.
- `audit-run` treats a fetch the permission rules refused as refused, not as a fetch, and lists
  it. A transcript with no final result record is reported as incomplete, not clean.
