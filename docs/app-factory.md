# App factory

The daily job that writes one new app PRD for the free toolbox on jurasolutions.sg/apps. Built
against `prd/pending/prd-jura-app-factory-2026-10-24.md` §5.6, §5.7 and block 4. (Blocks 1 to 3,
the toolbox shell, APP-001 and APP-002, are built in the landing-page repo.)

The factory writes PRDs. It never builds an app. Each PRD goes to Ting Yu as an `app-build`
request in #approvals, and his approval there is the sign-off for that PRD
(`prd-jura-mission-control-2026-10-25.md` §5.9, which supersedes the app factory PRD's
build step).

## How a day goes

1. **06:30 SGT**, launchd runs `jura-growth run app-factory`.
2. `precheck` first raises an `app-build` request for any factory PRD in `prd/pending/apps/`
   that has never had one (the catch-up pass, which `submit-prd` also runs: it gives each PRD
   filed before requests existed exactly one request, and does nothing once each has one). Then it skips the run before Claude starts when:
   - the factory already wrote a PRD today (one a day, `caps.APP_PRDS_PER_DAY`),
   - 7 or more app PRDs are waiting for an `app-build` decision (`caps.APP_PRDS_WAITING_MAX`), or
   - today's PRD failed the brand check twice and was dropped.

   The skipped run is recorded with its reason, and the digest says so.
3. Headless Claude runs `prompts/app-factory.md`: reads `jura-growth apps context --json`, picks
   an idea, confirms any rule on the official page with WebFetch, writes the PRD to the template
   in its scratch folder (`data/growth/work/app-factory/`), checks it with
   `apps submit-prd --dry-run`, then files it with `apps submit-prd`.
4. `submit-prd` writes `prd/pending/apps/prd-app-NNN-<slug>-YYYY-MM-DD.md`, records the row in
   `app_prds`, raises the `app-build` request over the file's bytes and marks the backlog. The
   request's card goes to #approvals when the command ends, with the PRD attached, the pitch, the
   tier and the lead types. The run update in #app-factory names the request.
5. Ting Yu approves or skips it in #approvals (see "Building an app PRD").

## Commands

| Command | Does |
|---|---|
| `jura-growth apps status` | Waiting count, next APP number, today's PRD or the limit, live tools from the site registry, pending and built PRDs, the backlog |
| `jura-growth apps context --json` | Everything the prompt needs in one call: the above plus usage (D1 `app_usage`, last 7 days, or "not configured") and the last 30 days of scout insights |
| `jura-growth apps backlog [--json]` | The backlog with the status worked out from the PRD folders and the registry |
| `jura-growth apps submit-prd <file> [--dry-run]` | The gate. `--dry-run` runs every check, brand check included, without filing, raising a request or using an attempt |
| `jura-growth apps handoffs [--json]` | Build handoffs waiting for a builder, oldest first. `--json` is what Dispatch polls: each with `handoff: {repo, base, prd_text, prd_sha256, approval}`, within 64 KB |

## What `submit-prd` checks in code

In this order. A structural rejection never uses up the brand gate's one regeneration.

1. **Limits**: one factory PRD a day, fewer than 7 waiting for a decision, at most 4 structural rejections a day
   (`config/apps.yaml`).
2. **The template's shape** (`agents/apps/prd.py`, `validate_shape`): the five header lines and
   `---`; Tier `browser` or `ai`; Category one of Sales, Finance, Admin, HR, Marketing,
   Documents; the "To build:" line naming `prd/pending/apps/prd-app-NNN-<slug>-YYYY-MM-DD.md`
   with the title's number, the Created date and a slug made from the name; exactly sections 1 to
   7 with the template's headings and subsections, in order; the three §1 bullets; the
   always-include success criteria (360 px and 44 px, keyboard and labels, contrast,
   `jura-growth check`, `?from=apps/<slug>`, the usage counter) plus at least two tool-specific
   ones; the §4 Official sources, Privacy and Tier rules bullets and the design-system line;
   numbered user-flow steps; the §5.2 strings (title equal to the name, subtitle equal to the one
   line word for word, privacy note, buttons, the talk-to-us heading, body and button, try-limit
   messages for AI tools); the §5.3 folder and registry entry matching the header; AI tools'
   function path, `max_tokens`, `claude-haiku-5-5`, system prompt and output schema; the sign-off
   gate sentence "Do not start building. This PRD requires explicit sign-off before any code is
   written." with the file's own path.
   The hand-written APP-001 and APP-002 pass the shape check. A factory PRD is held to the strict
   form too: the template's author line `app factory (for Ting Yu)`, the "One line (also the page
   subtitle)" label, the contrast criterion, the Tier rules bullet, and Dependencies and State
   in §5.3.
3. **Numbering and duplicates**: the number must be the next free one (highest APP number across
   `prd/pending/apps/`, `prd/done/apps/`, the site registry, the backlog and `app_prds`, plus
   one); Created must be today; the slug and the name must not belong to a live, pending or
   built app or to a backlog row that already has a PRD.
4. **The name**: a few plain words in sentence case. No CamelCase, figures, agency names or
   marketing words (`banned_name_words`), and each word must be in the system dictionary
   (`/usr/share/dict/words`, with simple plural and suffix handling) or in `name_words`.
5. **Guardrails** (read from the name, the one line, in-scope features, the user flow and the
   copy; out-of-scope lists and negations like "no sign-in" are ignored): no legal, medical or
   financial advice; nothing that imitates a government service or official document; no
   accounts, logins or stored customer data. A statutory calculator (a calculator or checker that
   relies on GST, CPF, a levy or a tax) must label its result an estimate in the copy.
6. **Official sources**: if the tool relies on a rule (GST, CPF, MOM, IRAS, PayNow, public
   holidays…), the Official sources line must carry a full URL on an official host (any
   `*.gov.sg`, plus `abs.org.sg` for PayNow) and a date checked within the last 7 days. Inside a
   scheduled run, every cited official URL must also have been opened with WebFetch in that run;
   `submit-prd` reads the run's transcript to check. "None" is accepted when nothing is relied
   on, or with a stated reason ("extracts what is printed and does not calculate tax").
7. **The brand gate** (`gate.gate`, item key `app-prd:<date>`): every §5.2 string (through
   `copy_check.items_from_markdown`), the §1 one line, who it is for, why it helps Jura and the
   registry description, on the `app-copy` channel, which also refuses claims of time or money
   saved. Official URLs are passed as sources, so a statutory rate with its .gov.sg page passes
   the numbers rule. A failure posts to `#alerts` and allows one regeneration; a second drops
   today's PRD.

The §5.2 bullets are unwrapped and split before `copy_check` reads them, because the core
extractor reads one line per bullet and would miss wrapped strings and the card's body and
button.

## Files

| Path | What |
|---|---|
| `jura_growth/agents/apps/` | The plug-in: `prd.py` (template and factory rules), `catalog.py` (PRD folders, registry, numbering, limits), `backlog.py`, `inputs.py` (D1 usage, scout insights), `factory.py` (`submit-prd`, the `app-copy` channel), `builds.py` (the `app-build` kind, handoffs, skip and expiry, the catch-up pass) |
| `jura_growth/agents/apps/migrations/` | `0001` `app_prds`; `0002` `app_builds`; `0003` lets an expired idea's slug be filed again |
| `jura_growth/agents/apps/backlog-seed.yaml` | The §5.7 seed, used when the data file is missing |
| `jurasolutions/data/growth/app-backlog.yaml` | The live backlog |
| `prompts/app-factory.md` | The headless prompt (§5.6 steps 1 to 6) |
| `config/apps.yaml` | Limits (lower only), official hosts, source age, name words |

## Decisions

- **The factory's own record decides "one a day".** APP-001 and APP-002 are dated the same day
  the factory was built, so the date in a file name can't be the test. The `app_prds` table is,
  with a fallback to files whose author line is `app factory (for Ting Yu)`.
- **The waiting pile counts PRDs waiting for an `app-build` decision** (MC §5.9 step 6). A
  handed-off build no longer waits for Ting Yu, and his own PRDs (APP-001, APP-002) have no
  request, so neither counts.
- **A backlog idea is the expected pick, not a duplicate.** Duplicates are slugs and names that
  already have a PRD or are live.
- **PayNow** is run by the Association of Banks in Singapore, so `abs.org.sg` counts as official
  for it, alongside any `*.gov.sg` host.
- **Scout insights** come from `jura-growth scout insights --days 30 --json` when the scout
  provides it, else straight from the `leads` table (industry, observations), else nothing. The
  factory never imports the scout's code.
- **Usage** reads D1 `app_usage` through `cloudflare.query` once the Cloudflare secrets are set,
  and says "not configured" until then.
- **The registry** is read from `repos/landing-page/src/apps/registry.json`, a list of entries (an
  `{"apps": [...]}` object also works). If it is missing, status and context say so and nothing
  counts as live.

## Building an app PRD

Each filed PRD waits for Ting Yu's answer to its `app-build` request in #approvals
(`agents/apps/builds.py`; MC §5.7 and §5.9). The request covers the PRD file's bytes, so changing
one byte supersedes it and raises a new one.

- **Approve.** The decision claims the request and writes a build handoff, an `app_builds` row
  with the PRD's path and SHA-256 and the request's id and date, in one transaction. Nothing is
  written into the PRD, so its hash stays the one Ting Yu saw. Dispatch polls
  `apps handoffs --json` and builds the app in `repos/landing-page` on its own task branch from
  `main` (Dispatch D6). Until `approvals.dispatch_builds` is set to `true`, the decision's answer
  and the one-pager say how to build it by hand: "Build it: open Claude Code in `jurasolutions/`
  and say: build the approved PRD `<path>` (approval A-nnnn)". The handoff is listed until the
  build is reported (ticket 10b).
- **Skip.** The PRD moves to `prd/skipped/apps/` with "Skipped by Ting Yu on <date>" at the top,
  and the backlog idea is dropped for good.
- **No answer for 7 days.** The PRD moves to `prd/skipped/apps/` with "Expired unanswered on
  <date>". The backlog idea goes back to `idea` with a `reopens` date 30 days on, shows as
  `resting` until then, and may be proposed again from that date under a new number.

The PRD template's "To build:" header line and its §7 say the same thing: approve the PRD's
`app-build` request in #approvals. `prd.py` checks that wording on every new factory PRD, and still
reads the old header, which asked for a typed reply, on the PRDs filed before it changed (APP-001
to APP-003), whose bytes are what their requests cover.
