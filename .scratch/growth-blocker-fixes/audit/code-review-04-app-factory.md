# Code review 04: the daily app PRD factory (growth repo)

- **Repo:** `jurasolutions/repos/growth`, branch `main`, HEAD `6eabfe7`, clean.
- **Fixed point:** `8726d96`, the parent of `7ccc164` ("Add the community scout and the daily app PRD factory"). The diff is `git diff 8726d96...HEAD`, scoped to `jura_growth/agents/apps/`, `config/apps.yaml`, `prompts/app-factory.md`, `docs/app-factory.md`, `tests/test_apps.py` and `jura_growth/copy_check.py`. That is 13 files, +2646 and -2 lines.
- **Spec:** `jurasolutions/prd/pending/prd-jura-app-factory-2026-10-24.md`, growth share only: §5.6, §5.7 and block 4, plus the parts of §2, §4 and §5.5 that the growth code owns.
- **Reviewed:**
  - Every file in the factory diff was read in full.
  - From core, only what the factory calls: `runner.py`, `gate.py`, `digest.py`, `cloudflare.py`, `copy_check.py`, `transcripts.py`, `caps.py`, `paths.py` and `config/settings.yaml`.
  - The template `prd/templates/prd-app-template.md`, and APP-003 as the sample of factory output.
  - The website's registry and D1 schema, read only.
- **No operating card:** `docs/agents/crew.md` is missing. This is a read-only review outside a feature, so it went ahead without one.
- **Side effects:** none. All reproductions ran against copies of `prd/` and `config/` in the scratchpad, with the data directory and `.env` pointed at scratch paths.

## Verdict: approve

Nothing is blocking:

- No blocked path is touched.
- The hard limits the PRD names are enforced in code: one PRD a day, the waiting pile of 7, one brand regeneration before an item is dropped, and the sign-off gate sentence.
- The block 4 done-when holds for the parts that can be checked without side effects.

Every gap below sits behind Ting Yu's own "approved, build ..." sign-off on each app PRD, so none of them can put copy or code live by itself.

Nine findings are ranked *should fix*. Fix them before the factory runs unattended for long. The four that matter most:

- S1: unquoted copy skips the brand gate.
- S2: the official-sources bypass.
- S3: AI-tier PRDs are not held to the 2-tries rule.
- S4: §5.5 usage is missing from the digest.

## Spec coverage table

| # | Requirement (PRD line) | State | Evidence |
|---|---|---|---|
| 1 | §5.6 "The daily factory (06:30 SGT)", headless Claude with `prompts/app-factory.md` | Implemented | `config/settings.yaml:47-52` (`daily: "06:30"`, `kind: claude`, `prompt: app-factory.md`). `schedule.py` converts SGT to the Mac's zone. Nothing runs until someone runs `jura-growth schedule install` (README.md:93) |
| 2 | §5.6 input: `data/growth/app-backlog.yaml` | Implemented | `backlog.py:37-45` reads the data file, or the seed if the file is missing |
| 3 | §5.6 input: the site's app registry | Implemented, with a deviation | `catalog.py:63-64` reads `repos/landing-page/src/apps/registry.json`. The PRD says `registry.(ts|js)`; the site's `registry.js` imports the JSON, so they agree. The file exists only on the landing-page `toolbox` branch, not on `main` |
| 4 | §5.6 input: `prd/pending/apps/` and `prd/done/apps/` | Implemented | `catalog.py:51-56` and `78-105` |
| 5 | §5.6 input: last 30 days of scout leads (industries, pain points) | Implemented | `inputs.py:34-90` uses `scout insights --days 30 --json`, falling back to the `leads` table. `config/apps.yaml:25` sets `insights_days: 30` |
| 6 | §5.6 input: last 7 days of app usage | Partial | `inputs.py:18-31` queries D1 `app_usage`, but only once the Cloudflare secrets are set; until then it returns "not configured". The window is today plus 6 days back (`inputs.py:22`), and at 06:30 today is nearly empty |
| 7 | §5.6.1 pick by industries, generic, browser preferred, distance; "Never duplicate" | Partial | Weighting is left to the prompt (`prompts/app-factory.md:31-54`). The code rejects only exact slug or name clashes (`prd.py:602-606`). Near-duplicates pass (finding S6) |
| 8 | §5.6.2 check any rule against IRAS/MOM/CPF/MAS/ACRA, cite URL and date; if it can't be confirmed, pick another | Partial | `prd.py:767-797` requires an official host, a date no more than 7 days old, and a fetch in this run (read from the transcript). Two ways round it: "None" plus any negation word, and statutory terms written out in full (finding S2). The code also accepts any `*.gov.sg` host plus `abs.org.sg` (`prd.py:749-753`, `config/apps.yaml:13-14`), which is wider than the PRD's list |
| 9 | §5.6.3 write `prd/pending/apps/prd-app-NNN-<slug>-YYYY-MM-DD.md` following the template exactly | Implemented | The file name comes from the "To build" line, which is checked against the title number, the Created date and a slug made from the name (`prd.py:56-58`, `326-333`). The file is written at `factory.py:125-128`. The strict shape check is `prd.py:295-349`. APP-003 passes both the strict shape and the factory rules (repro 1) |
| 10 | §5.6.3 numbering | Implemented | `catalog.py:141-164` takes the highest APP number across pending, done, the registry, the backlog and `app_prds`, then adds one. Checked at `prd.py:595-597` |
| 11 | §5.6.4 run all user-facing copy through `jura-growth check` | Partial | `factory.py:64-77` and `116` gate the §5.2 strings, the §1 text and the registry description on the `app-copy` channel. Only quoted §5.2 strings are extracted (`prd.py:275-281`), so an unquoted copy line is never checked (finding S1) |
| 12 | Sign-off gate text on every PRD ("Do not start building ...") | Implemented | `prd.py:36-37` and `524-538`. A factory PRD must carry the template sentence exactly, plus the "approved, build <path>" line and the signature line. APP-003 §7 carries it |
| 13 | §5.6.5 update the backlog | Implemented | `backlog.py:71-89` (`mark_written`), called at `factory.py:135-143`. The data file is created on the first filing. `seed_if_missing` is never called |
| 14 | §5.6.6 post to `#app-factory`: name, pitch, tier, lead types, the exact "To build" line | Implemented | `factory.py:155-184`. The wording matches the PRD. `discord.py:146` sets `allowed_mentions: parse []`. Without a webhook the post goes to `data/growth/discord-outbox/` |
| 15 | Guardrail: one PRD a day | Implemented | `caps.py:31`, `catalog.py:197-214`, checked in `precheck` (`__init__.py:44-49`) and again in `submit` (`factory.py:90-92`). Tested by `test_one_a_day` |
| 16 | Guardrail: 7 or more waiting, skip the day and say so in the digest | Implemented | `caps.py:32` and `catalog.py:215-217`. The runner writes a skipped run row (`runner.py:108-113`), and the digest reports it (`__init__.py:72-74`). Tested by `test_waiting_pile_guard` |
| 17 | Guardrail: no legal, medical or financial advice; nothing that imitates a government service or official document; statutory calculators need a source and an "estimate" label | Partial | Regex checks at `prd.py:562-577` and `695-707`. Several wordings get past them (finding S5) |
| 18 | Guardrail: no accounts, stored customer data or third-party logins | Partial | `prd.py:567-568`. "your Jura account" passes, and §2 and §4 are not scanned (finding S5) |
| 19 | Guardrail: plain sentence-case names, no invented brand words | Implemented, with a gap | `prd.py:614-648`. Any all-caps word of 2 to 5 letters passes (`prd.py:635`). The dictionary check is skipped silently when `/usr/share/dict/words` is missing (`prd.py:659-662`) |
| 20 | §5.7 backlog seed, 20 rows, browser unless marked AI | Implemented | `backlog-seed.yaml:1-145` matches the PRD table row for row, with 6 AI rows. Tested by `test_backlog_seed_has_the_twenty_ideas` |
| 21 | Block 4 done-when: a manual run writes APP-003 in the template's shape, passes the checker, posts to `#app-factory`; a second run the same day does nothing | Implemented (the post is unverified) | APP-003 passes the strict shape, the factory rules and the brand gate (repro 1). The second-run skip is tested by `test_one_a_day`. Whether APP-003 actually reached Discord can't be checked without reading `data/growth/`, which was off limits |
| 22 | §5.5 "The digest reports yesterday's counts" | **Missing** | `__init__.py:52-82` reports only the day's PRD and the waiting count. No plug-in digest reads `app_usage` (grep), so usage appears nowhere in the digest (finding S4) |
| 23 | §5.5 "the scout uses them to choose which tool to mention" | Implemented (scout's code) | `agents/scout/registry.py:61-78`. Outside the factory, listed here for completeness |
| 24 | §1 and §5.3: AI tools "limited to 2 tries per visitor per day", as far as the template and factory must state it | Partial | The template's Tier rules sentence says only "shared limiter". Code requires just one §5.2 label containing "tries" or "limit" (`prd.py:482-483`). The 2-tries criterion, Turnstile, input limits and the content of the Tier rules line are not required (finding S3) |
| 25 | §4 "Tool pages must not claim time or money saved" | Partial | The `app-copy` channel enforces it inside the factory (`factory.py:189-201`). At build time the template's criterion says only "All copy passes `jura-growth check`", and without `--channel app-copy` "in seconds and save hours" passes (finding S7) |
| 26 | §2.6 "Every morning a new app PRD appears ... with its pitch posted" | Implemented | Rows 9, 14 and 15. Two conditions: the waiting-pile guard, and `DISCORD_WEBHOOK_APP_FACTORY` being set |
| 27 | §5.6 "Building an app" (Claude Code builds, deploys after go-ahead, moves the PRD to `prd/done/apps/`) | Out of growth scope | The factory supplies the build line. `prd/done/apps/` does not exist yet. `catalog.py:55` treats a missing folder as empty |

## Findings ranked

### Spec

**Blocking:** none.

**Should fix**

- **S1. Unquoted §5.2 copy skips the brand gate.**
  - Where: `prd.py:248-281` (`copy_items` keeps only quoted strings), feeding `factory.py:64-77`.
  - Rule broken: PRD §5.6 step 4, "Run all user-facing copy through `jura-growth check`", and repo `CLAUDE.md`, "The brand checker is the gate."
  - Repro 2: in APP-003, replacing `- Done: "Your file is ready. Check your downloads."` with `- Done: Your file is ready in seconds, saving you hours!` gives 0 rule errors and a brand pass. The same text in quotes fails.
  - Fix: treat any §5.2 bullet with a label and no quoted string as a structural rejection, or check its text as body copy.

- **S2. The official-source requirement can be bypassed.**
  - Rule broken: §5.6 step 2, "If it can't be confirmed, pick another idea."
  - Path (a), `prd.py:771-779`: "None" is accepted whenever the rest of the line contains "not", "no" or "only".
    - Repro 3: a GST checker with `Official sources: None. Not checked today.` and an "Estimate only." string gives 0 errors.
    - Plain `None.` is correctly rejected.
  - Path (b), `prd.py:572-577`: `STATUTORY` has no entry for spelled-out terms.
    - A tool named "Price tax helper" whose in-scope line reads "Works out goods and services tax on a price at the current rate" is found to rely on no rule (`relies_on_rule == []`).
    - It is then filed with `None.` and needs no estimate label (repro2).
  - Fix:
    - Accept "None" only when `relies_on_rule` is empty.
    - Add "goods and services tax", "central provident fund" and "skills development levy" to `STATUTORY`.

- **S3. AI-tier PRDs are not held to the 2-tries rule.**
  - Where: `prd.py:482-483` (any one label matching `tries|limit`) and `prd.py:442` (the "Tier rules" bullet is checked for presence only).
  - Rule broken: PRD §1, "limited to 2 tries per visitor per day", and §5.4. The hand-written APP-002 carries the criterion "A visitor gets exactly 2 tries per SGT day; the third is refused without an API call". The template and the factory require nothing like it.
  - Repro 4: an AI PRD with a single `Limit reached: "You have 3 free tries left today."` and `Tier rules: AI tools allow 5 tries a day, no Turnstile.` passes every rule and the brand gate. `jura-growth check --channel app-copy "You have 3 free tries left today."` gives `pass`.
  - Why it matters: Claude Code builds the PRD in one pass and could set a per-tool limit from it.
  - Fix:
    - For `tier == "ai"`, require the template's Tier rules sentence word for word.
    - Require both the "Tries left" and "Limit reached" strings and a daily-cap string.
    - Add an always-include AI criterion for "2 tries per SGT day; the third refused without an API call".
    - Put the same criterion in the template.

- **S4. The digest does not report app usage.**
  - Where: `__init__.py:52-82`.
  - Rule broken: §5.5, "The digest reports yesterday's counts."
  - Fix: add the previous SGT day's opens and completions per slug to `digest()`, reusing `inputs.usage` (or the shared reader from finding T1), with "not configured" while the Cloudflare secrets are missing.

- **S5. The guardrail regexes have gaps.**
  - Where: `prd.py:562-569`, `674-680` and `683-692`.
  - Rules broken: §5.6 guardrails, "nothing that imitates a government service" and "No accounts, stored customer data".
  - Each of these passes (repros 2 and 5):
    - In scope "Fills in the IRAS GST F5 return boxes, ready to copy into myTax Portal" (no guardrail error).
    - "Saves every merged bundle to your Jura account".
    - Login wording placed in §2 criteria, because `scan_text` skips §2 and §4.
  - The negation window (any "no" within 40 characters before a match) also cancels real hits, for example "With no jargon, tax planning tips ...".
  - Fix:
    - Add `return|myTax|filing` and `\baccount\b` patterns.
    - Scan §2 and §4 as well.
    - Tighten `NEGATION` so the negator must sit right before the matched phrase.

- **S6. "Never duplicate" catches only exact matches.**
  - Where: `prd.py:602-606`.
  - Rule broken: §5.6 step 1.
  - Repro 5: "PDF joiner" passes while "PDF merge and split" is pending. Distance is left to the prompt.
  - Fix: add a token-overlap check that flags a near-duplicate as a rejection the model must justify in §6. Or record this explicitly as prompt-only in `docs/app-factory.md` (the "What submit-prd checks in code" section currently implies more).

- **S7. At build time the saving-claims rule is off by default.**
  - Where: template §2, "All copy passes `jura-growth check`"; `cli.py:86-104`, where `check-copy` applies no channel unless `--channel` is given.
  - Rule broken: PRD §4, "Tool pages must not claim time or money saved".
  - Repro: `jura-growth check "Make a quote in seconds and save hours every week."` gives `pass` (exit 0). With `--channel app-copy` it fails.
  - Fix:
    - Name `jura-growth check-copy --channel app-copy src/apps/<slug>/copy.js` in the template's criterion and in the §5.4 done-check guidance (`prompts/app-factory.md:119`).
    - The template lives in `jurasolutions/prd/templates/`, so changing it is Ting Yu's call.

**Nit**

- **S8.** The usage window is "today plus 6 days back" (`inputs.py:22`), while the scout uses 30 full days plus today (`scout/registry.py:65`). Use the 7 days before today.
- **S9.** The one-a-day fallback counts any same-day file whose author is `app factory (for Ting Yu)` (`catalog.py:203`). That is the template's default author line, so a PRD Ting Yu writes by hand from the template blocks that day's factory run.
- **S10.** `BUILD_RE` (`prd.py:56-57`) accepts exactly 3 digits, while `FILENAME_RE` accepts 3 or more. Numbering breaks after APP-999. This is far off.

### Standards

These findings come from the Standards sub-agent. I re-checked the ones marked as verified.

**Blocking:** none.

**Should fix**

- **T1. New code duplicates existing readers.**
  - `catalog.registry` (`catalog.py:63-133`) duplicates `scout/registry.py:22-46` and `social/toolbox.py:46-83`. The three handle the file's shape differently: apps accepts `{"apps": [...]}`, scout accepts `apps` or `entries`, social accepts a list only.
  - `inputs.usage` (`inputs.py:18-31`) duplicates `scout/registry.py:61-78`.
  - `inputs._from_leads_table` (`inputs.py:68-90`) re-implements `scout/leads.py:378` `insights`.
  - Fix: move the registry and D1 usage reader into core, as was done with `transcripts.py` in this same diff. Verified by reading all three readers.
- **T2. Two limits sit outside the hard-limit pattern.**
  - Rule broken: README "Writing an agent plug-in" ("its hard limits in `caps.py`"), and the `config/apps.yaml:3-4` header ("A value here may lower a limit, never raise it").
  - `max_rejections_per_day` (`factory.py:93`) has no ceiling in `caps.py`, so config can raise it without limit.
  - Setting `prds_per_day: 0`, the natural way to switch the factory off, crashes `catalog.limit_reason` with `IndexError` at `catalog.py:212-214` (repro 6). It is called from `precheck`, outside the runner's try block (`runner.py:105-107`), so the scheduled job dies with no run row.
  - Fix: add the cap to `caps.py`, and guard against an empty `written` list.
- **T3. The factory imports from another plug-in.**
  - `factory.py:45` imports `jura_growth.agents.community.transcript`. That module is a shim; the same diff moved its code to core `jura_growth.transcripts`, and that module's docstring names submit-prd as a user.
  - This couples one plug-in to another. If the community plug-in fails to import, the fetch check breaks.
  - Fix: import `jura_growth.transcripts`.
- **T4. A core change weakens heading checks.**
  - `copy_check.py:26` (`BODY_KEYS`, added in this range) makes keys such as `buttonText`, `ctaText` and `headingText` read as body text, so they lose the sentence-case and no-question heading rules.
  - Repro: `items_from_js('{ buttonText: "Get Started Now?" }')` gives `kind == "body"`; with `button:` it gives `heading`.
  - This weakens §2.7, "All page copy passes the brand checker", for the toolbox's `copy.js` files.
  - Fix: give the HEADING_KEYS match on the last camel-case segment priority over BODY_KEYS.

**Nit**

- **T5.** Tests read the real `jurasolutions/prd/pending/apps/` (`tests/test_apps.py:17`, `33` and `195`), so they break once APP-001 moves to `prd/done/apps/`. The name tests depend on `/usr/share/dict/words`. Copy fixtures into `tests/fixtures/`.
- **T6.** Some helpers duplicate existing ones:
  - `_proper_nouns` (`prd.py:651-655`) duplicates `brand_check`'s copy, and `config.reset_caches` does not clear it.
  - `slugify` (`prd.py:284`) has the same body as `community/groups.py:63`.
  - `is_official` (`prd.py:749`) overlaps `transcripts.host_of`.
- **T7.** There is dead code: `catalog.live_apps`, `backlog.seed_if_missing` and `backlog.STATUSES` have no callers (grep).
- **T8.** Categories are listed three times (`prd.py:34`, `config/apps.yaml:9`, `backlog.py:32`), and `__init__.py:178` hard-codes the author line instead of using `prd.FACTORY_AUTHOR`.
- **T9.** `prd.py` is 803 lines covering parsing, shape, factory rules, guardrails, sources and the dictionary. This is possible Divergent Change. Consider splitting out `guardrails.py` and `sources.py`.
- **T10.** `inputs.py` is a confusing name in a repo where `inputs/` means the human-maintained, read-only folder. `NAME = "app-factory"` differs from the package and CLI group name `apps`.
- **T11.** The domain `jurasolutions/CLAUDE.md` PRD workflow says new PRDs go to `prd/pending/` as `prd-{project-name}-...`, which doesn't mention `prd/pending/apps/`. That is a documentation gap, not a code fault.

### Security

The `security-review` pass was run inline, without sub-agents, because the brief caps fan-out at two and both were used by the two review axes. The skill's own view of the branch was empty (main has no unpushed changes), so the pass covered the factory diff named above.

**High or medium findings at confidence 8 or above:** none. These checks came back clean:

- SQL: every factory query is parameterised (`catalog.py`, `factory.py:80-85` and `131-134`, `inputs.py:24-27`). `inputs.py:76-77` builds its column list from fixed strings only.
- Path traversal: the written file name comes from `BUILD_RE`, which allows only `[a-z0-9-]` in the slug, and goes through `paths.writable` (`factory.py:125`).
- YAML and JSON: `yaml.safe_load` (`backlog.py:43`) and `json.loads`. Nothing is deserialised unsafely.
- Discord mentions are disabled (`discord.py:146`).
- No secrets reach logs or context. D1 errors carry Cloudflare's messages, not the token (`cloudflare.py:49-50`).

**Notes (not vulnerabilities, recorded for the owner)**

- **X1. Prompt-injection path into a PRD.** The 06:30 run reads web pages through WebFetch and writes a PRD that Claude Code later builds. Injected text could end up in §5.3 Technical (for example, an extra dependency or script). The mitigation is Ting Yu's per-PRD "approved, build" review. Read §5.3 Dependencies before approving.
- **X2. The allowlist is broad (pre-existing, out of scope).** The job's allowlist `Bash(jura-growth:*)` (`runner.py:226-238`, from the foundation commit `3969a43`) lets the factory run every agent's commands, including outreach and `discord post`. Scoping it per job (`Bash(jura-growth apps:*)`, `Bash(jura-growth check:*)`) belongs to a foundation review.

## Human setup items

| # | What a person must do or supply | Read at |
|---|---|---|
| H1 | Install the schedule: `jura-growth schedule install`. Nothing runs at 06:30 until then. The Mac must be on; a run missed during sleep runs on wake | `README.md:93-97`, `config/settings.yaml:47-52` |
| H2 | Have the `claude` CLI installed and signed in on the Mac. Accept or change the US$3 per-run ceiling (up to about US$90 a month at one run a day) | `config/settings.yaml:23-26`, `runner.py:239-256` |
| H3 | Set `DISCORD_WEBHOOK_APP_FACTORY` in `repos/growth/.env`. Without it the pitch goes to `data/growth/discord-outbox/`. Also set `DISCORD_WEBHOOK_ALERTS` (brand-gate failures) and `DISCORD_WEBHOOK_DAILY_DIGEST` (the skip notice) | `discord.py:44-50`, `gate.py:79`, `digest.py:110`; guide at `outputs/growth/setup/discord.md:63` |
| H4 | For usage counts: create a Cloudflare API token with D1 read on `jura-toolbox`, and put `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `D1_DATABASE_ID` in `repos/growth/.env`. **No setup guide covers this.** `toolbox-ai.md` step 1 creates the database but never says to copy its ID or the account ID into the growth `.env`; the only mention is a checkbox at `docs/scout.md:247`. Until it is done, usage reads "not configured" | `cloudflare.py:22-23`, `inputs.py:20`; add a step to `outputs/growth/setup/toolbox-ai.md` |
| H5 | Keep `repos/landing-page` checked out on a branch that has `src/apps/registry.json`. Today that is `toolbox`; `main` has no registry. Merge `toolbox` into the site's `main` | `catalog.py:63-64`, `120-133` |
| H6 | Keep `prd/templates/prd-app-template.md` in place. If it is missing, `precheck` skips every run | `__init__.py:47-48` |
| H7 | Keep `/usr/share/dict/words` available (macOS has it by default). Without it the plain-word name check is skipped silently | `prd.py:659-662` |
| H8 | Give each app PRD its own sign-off ("approved, build <path>"). After shipping, move the PRD to `prd/done/apps/`; the folder doesn't exist yet and is created with the first ship. This step frees a place in the waiting pile of 7 | `catalog.py:55`, `215-217` |
| H9 | Optionally edit `data/growth/app-backlog.yaml` by hand, keeping its keys. Mark ideas `dropped` to stop them being picked | `backlog.py:1-10`, `catalog.py:184-189` |
| H10 | For AI-tier app PRDs to get built and run, do the website-side steps in `outputs/growth/setup/toolbox-ai.md`: D1 database and migration, the `DB` binding, Turnstile keys, the website-only Anthropic key with a monthly spend limit, `VISITOR_SALT`, `AI_TRIES_PER_DAY=2`, `AI_SITE_CAP=200`, `AI_LIMIT_SCOPE=all`, then redeploy. The factory itself reads none of these | `toolbox-ai.md:16-122` |

## Website dependencies

The factory reads, or assumes, these things from `repos/landing-page`:

1. **Registry** at `src/apps/registry.json`.
   - Shape: a list of `{slug, name, description, category, tier, status: live|draft, added, prd: "APP-NNN"}`.
   - Read at `catalog.py:63-133`. Only `status: "live"` counts as live; every entry counts for slugs, names and numbering.
   - Today it lists `quote-builder` (live, APP-001) and `receipt-reader` (draft, APP-002), on the `toolbox` branch only.
   - The scout and social plug-ins read the same file with different shape rules (finding T1).
2. **D1 `app_usage(day, app_slug, opens, completions)`**, keyed by SGT day.
   - Defined at `landing-page/migrations/0001_toolbox.sql:28-34`, written by `server/usage.js:49` using `sgtDay`.
   - This matches the factory's query at `inputs.py:24-27`.
3. **Per-tool folder** `src/apps/<slug>/` with `copy.js`, and the registry entry the PRD's §5.3 dictates. This matches the `registry.js` header comment.
4. **Enquiry form** accepting `?from=apps/<slug>`. Every factory PRD requires it as an always-include criterion (`prd.py:66`); it comes from website block 1.
5. **AI tools** at `functions/api/apps/<slug>`, using the shared limiter (`server/ai-tool.js`, `functions/api/apps/limit.js`) and the env `AI_TRIES_PER_DAY`. The factory requires the function path and model name in the PRD (`prd.py:510-520`), not the try count (finding S3).
6. **Build-time copy check.** The site build should run `jura-growth check-copy --channel app-copy` on each tool's `copy.js` (finding S7).

## Open PRD questions

1. **§6.1 Where the site's code lives:** answered in practice. The site is `repos/landing-page` (see the folder map in `jurasolutions/CLAUDE.md`), deployed on Cloudflare Pages (`toolbox-ai.md`).
   *Recommended:* mark it resolved in the PRD.
2. **§6.2 Limit across all AI tools, or 2 per tool:** not confirmed. The code defaults to all (`AI_LIMIT_SCOPE=all`, `toolbox-ai.md:111`).
   *Recommended:* across all tools, as the default.
3. **§6.3 Site-wide cap of 200 and the website key's monthly spend limit:** 200 is implemented as the default. `toolbox-ai.md:65-72` suggests US$10 a month, but nobody has decided.
   *Recommended:* 200 a day and US$10 a month to start, reviewed after the first month.
4. **§6.4 The "Made with jurasolutions.sg/apps" line:** the PRD's default is yes, but the PRDs disagree.
   - APP-001 has it (`prd-app-001-quote-builder-2026-10-24.md:55-56`).
   - The template's §4 says "the visitor's branding on anything they export, not Jura's".
   - APP-003 §4 says "no Jura footer, watermark or metadata added".

   *Recommended:* decide once. If yes, add an optional, switch-off-able line to the template's §4. If no, remove it from APP-001.
5. **New: "Time-saved calculator" (§5.7) against §4 "Tool pages must not claim time or money saved".**
   - The `app-copy` channel rejects its natural copy: "Your time saved each month" fails.
   - If the factory picks it, it will probably fail the brand gate twice and lose the day.

   *Recommended:* rename it to "Task time calculator" with copy about "your own totals", or mark the row `dropped`.
6. **New: official hosts.** The PRD names IRAS, MOM, CPF Board, MAS and ACRA. The code accepts any `*.gov.sg` host plus `abs.org.sg` for PayNow.
   *Recommended:* accept this, since ABS runs PayNow, and record it in §5.6 step 2.
7. **Housekeeping:** the factory PRD's status still reads PENDING SIGN-OFF (line 4), although the growth side is built against it. Not policed here; noted for Ting Yu.

## Evidence

- `.venv/bin/python -m pytest -o addopts="" -q -p no:cacheprovider tests/test_apps.py`: 67 passed in 0.46s. The conductor's full-suite baseline was 515 passed.
- `scratchpad/scripts/repro.py`, run against scratch copies of `prd/` and `config/`:
  - APP-003: strict shape `[]`, factory rules `[]`, brand pass.
  - Unquoted copy: rules `[]`, brand pass (the quoted version fails).
  - GST checker with "None. Not checked today.": `[]`.
  - AI PRD with "3 free tries" and a rewritten Tier rules line: `[]`, brand pass, no 2-tries criterion.
  - "PDF joiner": `[]`.
  - "your Jura account": `[]`.
  - `prds_per_day: 0`: `IndexError`.
- `scratchpad/scripts/repro2.py`:
  - Spelled-out GST: `relies_on_rule == []`, errors `[]`.
  - myTax return filler: no guardrail error.
  - `buttonText` reads as body.
- `jura-growth check "Make a quote in seconds and save hours every week."`: pass. With `--channel app-copy`: fail on "in seconds" and "save hours".
- `jura-growth check --channel app-copy "You have 3 free tries left today."`: pass.
- `jura-growth check-copy --channel app-copy` on APP-003 gives 33 of 33 strings pass; on APP-002, 19 of 19.
- `git -C repos/landing-page cat-file -e main:src/apps/registry.json`: not on `main`. The file exists on the checked-out `toolbox` branch.
