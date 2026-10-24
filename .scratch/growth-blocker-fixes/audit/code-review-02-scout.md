# Code review 02: scout and outreach agents against the scout PRD

- **Repo:** `jurasolutions/repos/growth`, branch `main`, HEAD `6eabfe7`. The point of comparison is `00f163f`, the parent of `66d4f07`, which added both agents. The diff is `git diff 00f163f...HEAD`, restricted to the scope below.
- **Spec:** `jurasolutions/prd/pending/prd-jura-scout-2026-10-24.md`. Its status reads "pending sign-off". The brief said not to police that, so this review compares the code to the PRD and nothing more.
- **Scope:** `jura_growth/agents/scout/`, `jura_growth/agents/outreach/`, `config/scout.yaml`, `prompts/scout.md`, `docs/scout.md`, `tests/test_scout_*.py`, `tests/test_outreach_*.py`, and the setup files `outputs/growth/setup/icp-draft.md` and `do-not-contact.example.csv`. I read the core modules (`caps`, `suppression`, `cloudflare`, `gate`, `brand_check`, `holidays`, `timeutil`, `pause`, `runner`, `cli`) only where these agents call them.
- **Method:**
  - I read every file in scope myself.
  - mattpocock `code-review` ran its Standards and Spec reviewers in parallel. Both used fresh contexts and were not given my findings.
  - I did the security pass myself, using the `security-review` methodology. The brief caps fan-out at two sub-agents, and `code-review` used both.
  - I reproduced each finding I could with a throwaway pytest harness outside the repo (see Evidence).

## Verdict: changes-requested

Five blocking findings (B1 to B5). Each one is a way for unattended sending to get past a limit the PRD says lives in code ("This PRD makes sending automatic and puts every limit in code, where the model can't talk its way past it", §1), or a way to leak the outreach secrets.

Shadow mode is still the default, and live sending refuses to start until a person sets `mode: live` and `legal_review_done: true`. So nothing here is sending real email today. All five must be fixed before the switch to live.

---

## Spec coverage

Key: **impl** = implemented, **partial**, **missing**, **deviates**. File references are at HEAD.

### Success criteria (§2)

| # | Criterion | State | Evidence |
|---|---|---|---|
| 1 | Daily research, ICP qualification, an email queued per qualified company with an address | partial | The 09:00 headless job (`config/settings.yaml:61-67`, `prompts/scout.md`). `scout/__init__.py:27-41` gates the run. The code enforces `add-lead` (`leads.py:179-301`) and `queue` (`queue.py:129-210`). Whether every qualified lead gets an email is up to the model. |
| 2 | Sends only 09:30–16:30 SGT on business days, spaced out, never above the caps | partial | The window, holidays, caps and one send per run are in code (`send.py:122-133`, `190-200`, `214-285`). Two gaps: config can lift the warm-up (B2), and the model can bypass spacing (B3). |
| 3 | Every address published by the business on its own site, source page recorded, nothing guessed or bought | partial | The code fetches the source page and finds the exact address on it (`leads.py:304-351`, `contact.py:219-251`). The page URL is stored (`leads.py:287-292`). Gap: the address does not have to belong to the business (B5). |
| 4 | Brand checker passes, plus sender identity, the why line and a one-click unsubscribe | impl | Signature and footer are added in code (`compose.py:38-43`, `118-128`). The email channel checks are at `compose.py:234-318`. The gate runs at queue and again at send (`queue.py:173-180`, `send.py:325-335`). `List-Unsubscribe` and one-click headers: `compose.py:83-87`, `send.py:402`. |
| 5 | Unsubscribes, bounces and complaints suppress the address before the next send run | impl | Each send syncs D1 suppression right before it goes (`send.py:250-260`, `sync.py:40-111`), and the address is checked per message (`queue.py:56-93`). Reply unsubscribes are only handled when IMAP is set up (`replies.py:200-201`). |
| 6 | Pauses itself on any complaint or a high bounce rate | deviates | A complaint for an address that is already suppressed never pauses (B1). The bounce-rate rule is correct (`store.py:111-124`). |
| 7 | Every lead, address, email and outcome in `growth.db` and visible in Discord | partial | Leads go to `#scout-leads` (`leads.py:354-372`). Sends go to `#outreach-sent` (`send.py:341-357`). Bounces and unsubscribes go to `#outreach-replies` (`sync.py:87`, `96`). Complaints and pauses go to `#alerts`. Skipped messages are only logged (`send.py:306-319`). |
| 8 | No company approached more than once (plus one follow-up) | impl, by domain | A unique index (`outreach/migrations/0001_outreach.sql:32-33`, `0002:8-9`), the live-send count and `contacted_domains` (`queue.py:76-92`), and dedupe at research (`leads.py:87-119`). One company under two domains can still get two first emails (N4). |

### Proposed plan (§5)

| PRD item | State | Evidence |
|---|---|---|
| 5.1 ICP in `inputs/icp.md`, with a draft in `outputs/growth/setup/icp-draft.md` | impl | The draft has the PRD content. `icp.py:23-37` reads it, and research refuses to start without it (`scout/__init__.py:32-34`). `inputs/icp.md` does not exist yet. |
| 5.1 Exclusions: government, listed group HQs, competitors, do-not-contact | partial | Government domains are blocked in code (`leads.py:216-217`), and the do-not-contact list is checked at research, queue and send (`leads.py:115`, `queue.py:69`). Listed HQs and competitors are left to the model. A do-not-contact file without a header row matches nothing (S3). |
| 5.2.1 Pick 1–2 industries, rotating | impl | `icp.py:68-77`. Not enforced at `add-lead` (the prompt says to stay within them). |
| 5.2.2 Target 15 new companies a day (config) | impl | `leads.py:236-238`, ceiling 30 in `settings.py:25`. |
| 5.2.3 Record name, website, industry, size, what they do, 1–3 observations, sources | partial | Required: company, website, industry, observations, sources and reasons (`leads.py:190-200`). `size_signal` and `what_they_do` are optional. |
| 5.2.4 Score 0–100 with reasons, keep 60+ | impl | `leads.py:201-206`, `232-234`. The floor is clamped in `settings.py:87-88`. |
| 5.2.5 Own-site address, exact page recorded | partial | The page is fetched and the address found on it (`leads.py:313-322`). Off-domain redirects fail (`contact.py:235-237`). Gap: the address's domain is not tied to the company, and the directory deny list is incomplete (B5). |
| 5.2.5 Prefer role addresses; named only if published as the enquiry contact | impl | A role address on the same page is used instead (`leads.py:324-333`). Otherwise `"enquiry_contact": true` is needed (`leads.py:336-340`), which is the model's own word. |
| 5.2.5 Never guess, construct or use lists | partial | Addresses are found on the page, never made up. But the code decodes Cloudflare protection, returns the page's addresses as a hint and substitutes addresses itself (S1). |
| 5.2.5 MX record, no other probing | impl | `contact.py:257-279`, `leads.py:348-350`. |
| 5.2.5 Form only gives `channel = form`, not emailed, listed in the digest | impl | `leads.py:252-256`, `queue.py:48-49`, `scout/__init__.py:44-56`. |
| 5.2.6 Drop known domains, suppressed, do-not-contact, `contacted_domains` | impl | `leads.py:87-119`, `227-230`, `342-347`. |
| 5.2.7 Best tool: industry fit, then usage | partial | The model chooses. The registry validates the choice (`leads.py:240-243`, `queue.py:161-171`). Usage comes from D1 `app_usage` (`registry.py:61-78`). |
| 5.2.8 Write the email and queue it | impl | `queue.py:129-210`. |
| 5.2.9 Post to `#scout-leads` | impl | `leads.py:354-372`. |
| 5.3 `send-due` every 10 minutes, all logic in code | partial | `config/settings.yaml:69-74`, `send.py:214-285`. The headless research run can also call it (B3). |
| 5.3 At most one per run, random spacing | partial | It returns after one send (`send.py:279-281`) and spacing is a probability draw (`send.py:240-242`). There is no minimum gap between sends, so calls made back to back each send (B3). |
| 5.3 Caps: 20/day, 600/30 days, 8,000/365 days, config may only lower them | impl | `caps.py:11-16`, `31-35`, `settings.py:112-125`, `send.py:190-200`. |
| 5.3 Per company: 1 first + 1 follow-up, ever | impl | See criterion 8. |
| 5.3 Warm-up 5, 10, then 20 | deviates | `caps.py:18`, `38-45` are correct. `send.py:172-177` lets `send.warmup_start` in config bring the warm-up forward (B2). |
| 5.3 Before each send: pause, D1 sync, do-not-contact, caps, brand check | impl | `send.py:216-229`, `234-236`, `250-278`, `325-335`. |
| 5.3 Resend with the outreach key, From "Ting Yu, Jura Solutions", Reply-To info@ | impl | `send.py:60-66`, `394-404`, `426-449`. `settings.py:16-18` fixes these in code. |
| 5.3 Plain text plus minimal HTML, no pixel, UTM on jurasolutions.sg only | impl in code | `compose.py:131-180`. Resend's own open and click tracking are a domain setting the code can't control (setup item 6). |
| 5.3 Record in `outreach_messages`, post to `#outreach-sent` | impl | `send.py:375-391`, `341-357`. |
| 5.4 One follow-up 5 business days later, only with reply detection and no reply | impl | `sync.py:117-157`. The reply check runs again just before a follow-up sends (`send.py:288-303`). The "short", "refers to the first" and "newer tool" rules are only in the prompt (N2). |
| 5.5 Unsubscribe link with an HMAC token and no address in the URL | impl (growth side) | `compose.py:69-80`, matching the token scheme in `docs/scout.md:107-118`. The site function is a dependency. |
| 5.5 Resend bounce and complaint webhooks into D1 | dependency | Read by `suppression.sync_from_d1` (`suppression.py:79-103`). See Website dependencies. |
| 5.5 Read-only IMAP, sender address and date only, no bodies stored | impl | `replies.py:102-212`: EXAMINE at `:120`, BODY.PEEK at `:141`, `:179`. Bodies are read in memory only. |
| 5.5 A reply marks the lead `replied`, cancels the follow-up, posts to `#outreach-replies` | impl | `replies.py:186-212`. |
| 5.5 A reply saying "unsubscribe", "remove" or "stop" suppresses | impl, when IMAP is set up | `replies.py:34`, `177-183`, `200-201`. Without IMAP the footer still promises this route, but only a person can honour it (S7). |
| 5.5 Sync before every send run | impl | Before every send that will actually happen (`send.py:250`). |
| 5.6 Under 120 words, one tool link, one `/apps` link, no attachments | impl | `compose.py:272-304`, `send.py:394-404`. |
| 5.6 A first line about something specific and true | partial | A heuristic checks for the company name or a keyword from the observations (`compose.py:306-317`). Truth can't be checked. The "stays in your browser" claim is not checked against the tool's tier (S5). |
| 5.6 Sender name, "Jura Solutions", jurasolutions.sg | impl | `compose.py:38`. No UEN (open question 5). |
| 5.6 The why line, the unsubscribe link and "or reply 'unsubscribe'" | impl | `compose.py:39-40`, `255-265`. |
| 5.6 Subject: sentence case, honest, no "Re:" or "Fwd:", not a question | impl | `compose.py:244-247`. Questions and sentence case are core rules (`brand_check.py:308-311`, `515`). |
| 5.7 Pause on any complaint | deviates | B1. |
| 5.7 Bounce rate above 3% over the last 50 sends | impl | `store.py:111-124`, checked on each new bounce (`sync.py:110-111`). |
| 5.7 Two brand-check failures in a row | impl, ambiguous | `store.py:92-108`. One email that fails its regeneration pauses outreach on its own (asserted by `tests/test_outreach_email.py:339`). The prompt says "Two emails failing in a row" (`prompts/scout.md:166`). See S6. |
| 5.7 Resend auth, quota or domain error | impl | `send.py:407-423`, `359-362`. |
| 5.7 Failed suppression sync | impl | `sync.py:44-52`, `send.py:256-257`. |
| 5.7 `jura-growth resume outreach` | impl | Core `pause.resume`, tested at `tests/test_outreach_sync.py:125-142`. |
| 5.8 Tables `leads`, `contacts`, `outreach_messages`, `contacted_domains` | impl, with extras | `scout/migrations/0001_scout.sql`, `outreach/migrations/0001_outreach.sql`. |
| 5.8 Delete non-replying leads after 24 months, keep the domain, keep suppression forever | impl | `sync.py:204-226`. Foreign keys are on (`db.py:25`), so the delete cascades. |
| 5.9 Website pieces | out of repo | See Website dependencies. The privacy link is in every email (`compose.py:41-43`, `266-267`). |
| Block 1 done-when (5+ leads, none guessed, re-run adds no duplicates) | tests only | `tests/test_scout_leads.py:32`. No live run evidence. |
| Block 2 done-when (10 emails pass, test unsubscribe, simulated bounce) | tests only | `tests/test_outreach_email.py:209-215`, `tests/test_outreach_sync.py:72`, `97`. |
| Block 3: shadow for 3 business days, then Ting Yu says go | partial | Shadow mode works (`send.py:339-347`). The 3-day minimum is not checked anywhere (N5). |
| Block 4 done-when (day one at most 5, a complaint pauses, resume restarts) | partial | Tests exist (`tests/test_outreach_send.py:344`, `tests/test_outreach_sync.py:125`), but B1 and B2 break both conditions in real use. |

**Not in the PRD** (the Spec reviewer's list, which I checked):
- `requeue-shadow` and migration `0002`.
- `send.warmup_start`, `research.max_queue` and `allow_named_contacts`.
- The `scout_rejections` table and domain-level suppression.
- The `preview`, `unsubscribe-link` and `suppress` commands.

All are reasonable operator tools. `warmup_start` is the one that harms (B2), and `requeue-shadow` needs to be kept away from the model (B3).

---

## Findings, ranked

### Blocking

**B1. A complaint for an address that is already suppressed never pauses outreach.**
- **Where:** `suppression.py:66-76`, `92-103`; `sync.py:76-111`.
- **Rule broken:** PRD §5.7 "Outreach pauses ... on: any complaint"; success criterion 6.
- **How it happens:** `sync_from_d1` passes on only the rows that `suppression.add` newly inserted. `add` uses `INSERT OR IGNORE` on the unique `email_hash` (`migrations/0001_core.sql:54`). So if the recipient was already suppressed by an unsubscribe link, a one-click POST or a reply saying "remove", their later spam complaint is dropped before `apply_rows` sees it. The message is never marked `complained`, and nothing pauses.
- **Why it matters:** unsubscribe followed by a spam report is the normal "report spam and unsubscribe" pattern. The documented D1 contract makes it worse: `email_hash TEXT PRIMARY KEY` (`docs/scout.md:184`) means D1 can't even hold a second row for the same address.
- **Reproduced:** `test_f1_complaint_after_unsubscribe_does_not_pause` and `test_f1b_complaint_after_reply_unsubscribe_does_not_pause`.
- **Fix:** act on every D1 event whatever the local suppression state. For example, track the last D1 row id or `created_at` processed, and run the complaint and bounce handling even when the address is already suppressed. Make the D1 table append-only (its own id, one row per event).

**B2. Config can lift the warm-up.**
- **Where:** `send.py:172-177`, read from `config/scout.yaml:59-61`.
- **Rule broken:** PRD §5.3 "Hard caps in `caps.py` (config may lower, never raise without a code change)", warm-up "5/day week 1, 10/day week 2"; block 4 "the first live day sends at most 5"; the rule at `caps.py:1` and `config/settings.yaml:3-4`. `docs/scout.md:144` claims config can only lower the caps.
- **How it happens:** a `warmup_start` in the past (for example `2026-01-01`) gives a daily cap of 20 on the first live day. The existing test only tries a date that lowers the cap (`tests/test_outreach_send.py:285`).
- **Reproduced:** `test_f2_warmup_start_in_the_past_lifts_day_one_cap_to_20`.
- **Fix:** count from the later of `warmup_start` and the recorded `first_live_send_at`, so config can only delay the warm-up. Or remove the option.

**B3. The headless research run can reach send-time and review controls.**
- **Where:** `runner.py:226-238`, `config/settings.yaml:61-67`, `outreach/cli.py:88-94`, `106-144`.
- **Rule broken:** PRD §5.3 "At most one email per run, with random spacing ... All logic here is code"; the `requeue-shadow` design that Ting Yu reviews and picks the shadow emails (`requeue.py:1-9`, `docs/scout.md:254-257`).
- **How it happens:**
  - The `scout-research` job runs with `Bash(jura-growth:*)` and blocks only `run`, `resume` and `schedule`. It also fetches arbitrary company websites, so a prompt-injected page is the realistic attacker.
  - It can loop `jura-growth outreach send-due`. Each call re-rolls the spacing draw and can send one email. The runner's per-job lock (`runner.py:60-92`) applies only to `jura-growth run`. Caps still hold, but the day's quota can go out within minutes.
  - The 30-minute timeout (`config/settings.yaml:24`) keeps a 09:00 run mostly out of the window. But launchd runs a missed job when the Mac wakes (README "Schedule"), so a late wake puts research inside 09:30–16:30.
  - In live mode it can also run `requeue-shadow`, queuing every shadow email without Ting Yu's selection.
  - `outreach unsubscribe-link` hands it a token for any address.
- **Reproduced:** `test_f3_back_to_back_send_due_calls_both_send_live`. Two calls in the same minute both reached Resend.
- **Fix:**
  - Add `Bash(jura-growth outreach send-due:*)`, `Bash(jura-growth outreach requeue-shadow:*)`, `Bash(jura-growth outreach unsubscribe-link:*)` and `Bash(jura-growth outreach sync:*)` to the scout job's `disallowed_tools`. Better still, allow only the subcommands the prompt uses.
  - Add a hard minimum gap between live sends to `caps.py` (for example no live send within 10 minutes of the last).

**B4. Security: the headless run can read every secret through `jura-growth check --file` and send it anywhere.**
- **Where:** core `cli.py:51`, `59-83`, reachable through `runner.py:226-238`.
- **How it happens:** the runner blocks `Read(<repo>/.env)`, but `jura-growth check --file <repo>/.env --json` reads the file and prints each issue's excerpt. Webhook URLs come back through the links rule. Keys and secrets that contain digits come back through the numbers rule. The same job is allowed to call WebFetch on any domain, so an injected instruction on a fetched company page can send the values out in a query string.
  - What leaks: the Resend outreach key (sending as Jura), the Cloudflare token (D1 edit), `UNSUBSCRIBE_SECRET`, the IMAP password and every Discord webhook.
  - `jura-growth discord post <channel> <text> --file <path>` (`cli.py:201-209`) can also attach the `.env` to a Discord message.
- **Reproduced with fake values:** `test_f9_check_file_echoes_secret_urls`. The output contained the full fake webhook URL and the fake `re_FAKEKEY123`.
- **Fix:**
  - Make `check --file` and `discord post --file` refuse paths outside the job's scratch folder (or at least refuse `.env`).
  - Narrow the headless allowlist as in B3.
  - Until then, store secrets as `keychain:<service>` references (`config.py:90-98`). The file then holds only service names.
- **Scope note:** this is core code and affects every `claude` job. The scout is the job most exposed, because it fetches unknown websites all day.

**B5. The address does not have to belong to the business.**
- **Where:** `leads.py:304-351`, `contact.py:52-60`.
- **Rule broken:** PRD §5.2.5 "Only an address the business publishes for enquiries on its own website"; "Never use third-party lists, data brokers or scraped directories"; success criterion 3.
- **How it happens:** the code checks only that the address appears on some page of the lead's own domain.
  - `info@someoneelse.sg` on a partners page, or a web designer's credit address in a footer, is accepted. The footer then says "<Company> lists this address for business enquiries", which is false for that recipient.
  - A directory missing from the deny list passes as the company's "own website", for example `sgbizlistings.sg/alder-logistics` with the real company address on it.
- **Reproduced:** `test_f4_unrelated_domain_address_is_accepted` and `test_f4b_unlisted_directory_passes_as_own_site`.
- **Fix:** require the address's domain to equal the site domain (or a subdomain of it), or to be a free-mail provider, which small businesses do use. This one rule also closes the directory hole, because a directory page lists the company's address, not the directory's own.

### Should fix

**S1. Contact finding goes further than §5.2 "narrows contact finding as far as it reasonably can".**
- **Where:** `leads.py:319-322` and `324-333`; `contact.py:148-208`; `prompts/scout.md:107-109`.
- **What happens:**
  - On a miss, `add-lead` returns every address on the page as a hint, and the prompt tells the model to resubmit with one.
  - For a named address, the code itself picks a role address from the page.
  - The code decodes Cloudflare email protection, which site owners turn on precisely to stop address collection.
- **Why it matters:** together these make the verifier behave like software that collects addresses from web pages, which is the point §4 sends to a lawyer.
- **Recommendation:** drop the hint list and the auto-substitution now, and put the Cloudflare decoding to the lawyer explicitly.

**S2. The test clock works in live mode.**
- **Where:** `timeutil.py:16-21`; used at `send.py:215` and `376`.
- **What happens:** `JURA_GROWTH_NOW` moves the window, the business-day check and `sent_at`. A "pretend it's Monday 09:30" run sends real mail on a weekend or after 16:30, and charges the fake day's cap instead of today's.
- **Fix:** refuse a live send whenever `JURA_GROWTH_NOW` is set.

**S3. A do-not-contact file without its header matches nothing, silently.**
- **Where:** `dnc.py:72-85`.
- **What happens:** `csv.DictReader` takes the first company row as the header, so `ZOLL Medical Singapore,,` written as line 1 protects no one, and live mode still starts.
- **Reproduced:** `test_f5_headerless_dnc_matches_nothing`.
- **Fix:** require a `company`/`name`/`domain` column. Make a bad header a live-mode refusal and an `add-lead` error.

**S4. Holidays fail open.**
- **Where:** `holidays.py:28-30`, `50-58`; `send.py:124`.
- **What happens:** with no dates for the current year, public holidays count as business days and only a digest warning appears. 2026 and 2027 are present, so this first bites on 1 January 2028.
- **Fix:** add a live-mode refusal when the current year is missing.

**S5. The "stays in your browser" claim is only a prompt rule.**
- **Where:** `prompts/scout.md:126-128`; `compose.py:234-318`.
- **Rule broken:** "Never invent facts" (`repos/growth/CLAUDE.md`).
- **What happens:** an email that claims "what you enter stays in your browser" for an `ai`-tier tool queues without complaint.
- **Reproduced:** `test_f6_browser_claim_passes_for_ai_tier_tool`.
- **Fix:** fail that phrase in `check_email` when the chosen tool's `tier` is not `browser`.

**S6. What "two brand-check failures in a row" counts.**
- **Where:** `store.py:92-108`; `prompts/scout.md:166`; `docs/scout.md:207-208`.
- **What happens:** the code counts gate verdicts, so one email failing its single allowed regeneration pauses all sending. The prompt tells the model "Two emails failing in a row pause outreach".
- **Fix:** pick one meaning and align the code, the prompt and the docs (question 2 below).

**S7. Reply unsubscribes without IMAP have no code path.**
- **Where:** `compose.py:40`, `settings.py:21`, `replies.py:52-53`.
- **What happens:** every email and the `List-Unsubscribe` mailto promise "reply 'unsubscribe'". Without IMAP, only Ting Yu reading info@ and running `outreach suppress` honours it, and nothing reminds him.
- **Fix:** either require IMAP for live mode, or add a daily digest line saying reply unsubscribes are manual (question 3 below).

**S8. Hard limits live outside `caps.py`.**
- **Rule broken:** the README says "its hard limits in `caps.py`".
- **Where:**
  - `settings.py:23-29`: score floor, target ceiling, window bounds, follow-up floor, retention ceiling.
  - `store.py:111-121`: 50 sends, 3%.
  - `store.py:105`: two failures.
  - `send.py:364`: three attempts.
  - `icp.py:74`: two industries a day.
- **Fix:** move them into `caps.py` (the Standards reviewer's main hard finding after B2).

**S9. New code that duplicates existing helpers (reuse rule).**
- `leads.py:66` `_mask` is a copy of `outreach/store.py:20` `mask`.
- `scout/settings.py:99` `_hm` is a copy of `schedule.py:40` `_hm`.
- `contact.py:79-91` `host_of` and `on_domain` duplicate `transcripts.py:149-159` `host_of` and `on_domains`. The copy drops the `ValueError` guard.
- `compose.py:131-136` and `198-201` duplicate `brand_check.host_of` and `brand_check.is_jura` (`brand_check.py:171-178`).
- `leads.py:380`, `398` and `send.py:167-168` duplicate `timeutil.days_ago`.

### Nits

- **N1. Copy drift since `6eabfe7`.** The privacy line is missing from `docs/scout.md:80-86` and `91-100` and from `prompts/scout.md:115-117`. The HTML footer ends the privacy line with a full stop (`compose.py:173`) but the text footer does not (`compose.py:43`).
- **N2. Follow-up rules are prompt-only.** The 60-word limit (`prompts/scout.md:171`), compared with 120 in code. Also "refers to the first email" (`compose.py:315` accepts the name or an observation instead) and "one newer tool" (`compose.py:296-302` doesn't check that the tool is newer).
- **N3. Narrow reply detection.** It matches only the exact recipient address, and only in INBOX (`replies.py:120`, `153-155`). A colleague replying from another address doesn't stop the follow-up. This is as the PRD specifies.
- **N4. Dedupe is by domain only** (`leads.py:95-110`). One company on `acme.sg` and `acme.com.sg` can get two first emails. This is as the PRD specifies.
- **N5. The shadow-to-live switch.**
  - The 3-business-day shadow minimum is not checked anywhere.
  - Emails still queued at the switch, which were never posted as SHADOW, go out live unreviewed (`send.py:203-208`).
  - Queued email never expires.
- **N6. Discord posts don't suppress mentions.** Model-written company names and subjects post verbatim (`leads.py:366-372`, `send.py:341-357`), so an `@everyone` would ping.
- **N7. The legally required footer uses a model-written name.** `display_name` comes from the model (`leads.py:266`) and goes into the footer (`queue.py:100`).
- **N8. An unevidenced speed claim.** The prompt's reference email says the tool works "in a few minutes" (`prompts/scout.md:147`), which is not in `approved_claims.yaml`. The PRD's own reference shape (§5.6) has it too, so fix both or neither.
- **N9. Settings file name.** Outreach settings live in `config/scout.yaml`, not `config/outreach.yaml` as the README convention says. `docs/scout.md:3-4` documents this.

### Standards (summary of the Standards reviewer, checked)

- **Hard findings:** B2 and S8 above. Also N9, which is low.
- **Judgement-call smells** (no action needed for this review):
  - **Duplicated Code:** queued-count SQL appears four times, `INSERT INTO outreach_messages` three times, the inactive-status list three times (`queue.py:22`, `sync.py:147`, `0002:9`; commit `064845a` had to touch all three), and text and HTML footers are built separately.
  - **Data Clumps:** the `(lead, row)` pair travels through about eight functions. `row` is the contact, which is also a mysterious name.
  - **Primitive Obsession:** `send._skip` branches on substrings of reason text (`send.py:306-318`).
  - **Feature Envy:** `scout/__init__.py:38` and `scout/cli.py:35-41` reach into outreach's tables.

### Security (pass done inline)

- **Blocking:** B4 (secrets through `check --file`). B3 (prompt injection reaching send controls) is also a security finding.
- **Checked and clean:**
  - SQL is parameterised. The f-strings only build `?` placeholder lists or a constant.
  - Email HTML escapes the draft, company, site and links (`compose.py:144-180`).
  - IMAP is read-only, and no bodies are stored.
  - The event log masks addresses (`store.mask`).
  - The Resend key travels only in the Authorization header.
  - The unsubscribe token is an HMAC-SHA256 with no address in the URL.
  - httpx verifies TLS. Page fetches are capped at 3 MB, and off-domain redirects are refused.
- **Blocked paths:** the diff touches nothing under `inputs/` or `design-system/`, and `paths.writable` refuses runtime writes there.

---

## Human setup items

Things a person must supply or do before outreach can go live, with the code that reads each one.

1. **ICP.** Edit `outputs/growth/setup/icp-draft.md`, keep the `## Industries` bullets, and move the file to `inputs/icp.md`. Read by `icp.py:23-37` and `40-65`. Research refuses to start without it (`scout/__init__.py:32-34`). Today `inputs/` holds only `services.md`.
2. **Do-not-contact list.** Create `inputs/do-not-contact.csv` with the header `company,domain,reason` (template: `outputs/growth/setup/do-not-contact.example.csv`). Read by `dnc.py:43-85`. Live mode refuses without it (`send.py:93-94`). Keep the header row (S3). Decide on the TaskWise-related rows (open question 4).
3. **Lawyer's view.** Then set `legal_review_done: true` (`config/scout.yaml:21`, checked at `send.py:76-80`). Take S1 to the lawyer too.
4. **Sending domain.** Choose `jurasolutions.sg` or a subdomain (open question 2) and set `sending_domain` (`config/scout.yaml:26`, `send.py:60-61`, `81-88`). Optionally set `from_local_part` (`config/scout.yaml:27`, `send.py:64-66`).
5. **Leave `send.warmup_start` null** (`config/scout.yaml:61`) until B2 is fixed.
6. **Resend.**
   - Add the domain and publish the DNS records Resend gives: the SPF TXT and MX for its bounce subdomain, and the DKIM TXT. Add a DMARC TXT at `_dmarc`.
   - Create a sending-only key limited to that domain and put it in `RESEND_API_KEY_OUTREACH` (`.env.example:20`, read at `send.py:89-90` and `427`).
   - **Turn off open and click tracking** for the domain. The code promises "no tracking pixel" but can't control this (`compose.py:20-22`).
   - Point a webhook for `email.bounced` and `email.complained` at the site's `/api/resend-webhook`.
   - Check that the free plan's 100 a day and 3,000 a month cover the 20-a-day cap.
7. **`UNSUBSCRIBE_SECRET`** must be the same in `.env` (`.env.example:23`) and the Pages env. Read at `send.py:91-92`, `compose.py:76-80` and `queue.py:103`. To verify: run `jura-growth outreach unsubscribe-link <your address>` (`outreach/cli.py:220-227`), open the link, then run `jura-growth outreach sync`.
8. **D1 access.** Set `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `D1_DATABASE_ID` (`.env.example:26-28`; `cloudflare.py:22-29`). Live mode refuses without them (`send.py:95-96`, `250-253`). A failing sync pauses outreach (`sync.py:44-52`).
9. **IMAP (optional, open question 3).** Set `OUTREACH_IMAP_HOST`, `_PORT`, `_USER` and `_PASSWORD` (`.env.example:31-34`; `replies.py:52-53`, `111-119`) with a read-only app password for info@. Without it there are no follow-ups (`sync.py:117-126`), and reply unsubscribes must be handled by hand with `jura-growth outreach suppress` (`outreach/cli.py:200-217`). See S7.
10. **info@jurasolutions.sg** must exist and be read. It is the Reply-To (`settings.py:18`) and the mailto unsubscribe (`settings.py:21`).
11. **Discord webhooks** for `#scout-leads`, `#outreach-sent`, `#outreach-replies` and `#alerts` (`.env.example:11-13`, `17`). Until they exist, posts go to the outbox.
12. **Site registry with live tools** in the local landing-page checkout: `<JURA_SITE_REPO>/src/apps/registry.json` (`registry.py:22-46`, `paths.py:39-40`). It must match what is deployed.
13. **Schedule.** Run `jura-growth schedule install scout-research scout-send scout-sync` (`config/settings.yaml:61-80`), and keep the Mac awake from 09:00 to 16:45 on business days.
14. **Holidays.** Refresh `config/sg-public-holidays.yaml` each December (`holidays.py:50-58`). See S4.
15. **Secrets in the Keychain.** Store them as `keychain:<service>` references (`config.py:90-98`) to blunt B4 until it is fixed.
16. **Shadow trial, then the switch.** Run three business days in shadow, set `mode: live` (`config/scout.yaml:17`, `send.py:73-75`), and confirm `jura-growth outreach status` shows every pre-condition holding. Review the shadow emails, then run `jura-growth outreach requeue-shadow --dry-run` and then the real run (`requeue.py:84-89`). Decide what happens to emails still queued at the switch (N5).
17. **Footer identity (open question 5).** Showing a UEN or registered name in the footer needs a code change (`compose.py:38-43`).

## Website dependencies (what the growth code expects of `repos/landing-page`)

- **Unsubscribe page and function.** `GET https://jurasolutions.sg/unsubscribe?t=<email_hash>.<sig>` (`settings.py:20`, `compose.py:69-80`).
  - `email_hash` is `sha256(email.strip().lower())` as lowercase hex.
  - `sig` is the base64url HMAC-SHA256 of the hex hash under `UNSUBSCRIBE_SECRET`, with no `=` padding.
  - The test vector is in `docs/scout.md:116-118`.
  - One click, no login, a plain confirmation page, and only the hash stored.
- **One-click POST.** `POST` to the same URL with body `List-Unsubscribe=One-Click` (RFC 8058), because every live send carries `List-Unsubscribe-Post` (`compose.py:83-87`). It must work without cookies or redirects and return 2xx.
- **D1 table `suppression`,** read by `suppression.py:86-90`. Its columns:
  - `email_hash`: the same hash as above.
  - `email`: may be empty for unsubscribes.
  - `reason`: exactly `unsubscribe`, `bounce`, `complaint` or `manual`. Anything else raises and pauses outreach on every run (`suppression.py:57-58`).
  - `source`: free text, stored as `d1:<source>`.
  - `resend_email_id`: Resend's email id, matched to `outreach_messages.resend_id` (`sync.py:60-61`).
  - `created_at`: ISO **text** (`YYYY-MM-DD HH:MM:SS`, UTC) set at insert time. An epoch integer is never selected (`test_f7`). A Resend event time can be missed, because a late webhook retry can fall outside the one-day overlap (`suppression.py:106-112`).
  - The PRD lists only four columns (§5.9). The code also needs `source` and `resend_email_id`.
  - Store **one row per event**, not a primary key on `email_hash` (`docs/scout.md:184`), or B1 can't be fixed.
- **`/api/resend-webhook`.** Verify the signature. Write `email.bounced` (hard bounces only) and `email.complained` rows with `email`, `email_hash` and `resend_email_id`.
- **`/privacy`.** It must be live: what the scout collects, why, and how to opt out (`compose.py:41-43`). Every email links to it.
- **`/apps` and `/apps/<slug>`.** Every registry entry marked `live` must be deployed. The registry fields used are `slug`, `status`, `name`, `description`, `category`, `tier` and `added` (`registry.py:26-46`, `sync.py:175`).
- **D1 `app_usage(app_slug, day TEXT YYYY-MM-DD, opens, completions)`.** Optional, for tool choice (`registry.py:61-78`).
- **A Cloudflare API token** scoped to that one D1 database's query endpoint (`cloudflare.py:26-52`).

## Open PRD questions

1. **Lawyer's view on address harvesting** (§6.1). Unresolved: `legal_review_done: false`. Add S1 to the brief.
2. **Sending domain** (§6.2). Unresolved: `sending_domain: null`.
3. **Mail provider and IMAP app password for info@** (§6.3). Unresolved as far as the repo shows; I did not read `.env`.
4. **Who goes on the do-not-contact list** (§6.4). Unresolved: `inputs/do-not-contact.csv` does not exist.
5. **UEN and registered name in the footer** (§6.5). Unresolved and not built.

**Raised by this review:**

- **A.** Should the D1 suppression table be append-only (recommended) or keyed by `email_hash`? This decides how B1 is fixed.
- **B.** Does "two brand-check failures in a row" mean two checks (current code: one email that fails its regeneration pauses everything) or two different emails (the prompt)? Recommended: two different emails, because one bad email is already dropped by the gate.
- **C.** Should live mode require IMAP, given that the footer promises "or reply 'unsubscribe'"? Recommended: no, but put a daily "reply unsubscribes are manual" line in the digest while IMAP is off.
- **D.** Should the code require 3 business days of shadow sends before live mode starts? Recommended: yes, it is a one-line check in `live_problems()`.

---

## Evidence

- **Full suite:** `.venv/bin/python -m pytest -o addopts="" -q -p no:cacheprovider` gave **515 passed in 18.32s**.
- **Reproduction harness:** `scratchpad/growth-prd-audit/repro-scout/` (a copy of the isolation fixture; temporary data, no network). Running `pytest --rootdir <that folder>` gave **10 passed in 0.29s**. Each test asserts the defect, so a pass means it reproduced: F1, F1b, F2, F3, F4, F4b, F5, F6, F7 and F9.
- **Blocked paths:** `git diff --name-only 00f163f...HEAD` filtered for `inputs/`, `design-system/`, CI and `_ds_bundle` found no blocked-path changes.
- **Repo state:** I made no changes. During the review another session added `docs/agents/` (crew operating card, 21:22), `.scratch/`, and edits to `.gitignore` and `CLAUDE.md`. I left them alone. They don't affect the reviewed HEAD `6eabfe7`.
