# Code review 03: social content and community scout agents

**Verdict: changes-requested.** Two findings block it, and both are in the community scout. The social agent has no blocking findings. Its gaps are should-fix items.

| | |
|---|---|
| Repo | `jurasolutions/repos/growth`, branch `main`, HEAD `6eabfe7`, clean |
| Point of comparison | `66d4f07` (parent of `8726d96`). The diff is `git diff 66d4f07...HEAD` over the scoped paths, 33 new files and 6,521 lines |
| Commits | `8726d96` social blocks 1–2 and `7ccc164` community scout (the apps agent was not reviewed). `064845a` and `6eabfe7` only touch outreach and core copy checks |
| Specs | `prd/pending/prd-jura-social-content-2026-10-24.md`, `prd/pending/prd-jura-community-scout-2026-10-24.md` (both pending sign-off; I compared the code to them and did not check the sign-off itself) |
| Read in full | every file in scope: `jura_growth/agents/social/**` (with templates), `jura_growth/agents/community/**`, `config/social.yaml`, `config/community.yaml`, `prompts/social.md`, `prompts/community.md`, `docs/social.md`, `docs/community.md`, the setup checklist and images. I read `runner.py`, `gate.py`, `transcripts.py`, `discord.post`, `caps.py`, `config/settings.yaml` and the `brand_check` link rules as far as these agents use them. I read the test files selectively |
| Operating card | There was none when the review started, which is fine for a read-only review. During the run another session added `docs/agents/crew.md`, `docs/agents/issue-tracker.md` and `.scratch/mission-control/` (21:22), and changed `CLAUDE.md` and `.gitignore`. Those changes are not mine and are not reviewed here. The card lists these blocked paths: `inputs/`, `design-system/`, `.env` and the live `data/growth/` |

All paths below are relative to `repos/growth/` unless they start with `outputs/` or `prd/`.

## Evidence

- `.venv/bin/python -m pytest -o addopts="" -q -p no:cacheprovider tests/test_social.py tests/test_social_render.py tests/test_community.py` gave **134 passed** in 12.25s, with nothing skipped, so the real-Chrome render tests ran. The conductor's full baseline was 515 passed.
- `scratchpad/growth-prd-audit/verify/test_verify_social_community.py` gave **9 passed** in 0.39s. These are my own reproductions. They use the repo's `isolated` fixture, so data, outputs, the env file and Discord all point at pytest temp folders and nothing touched the real `data/` or Discord. Each finding below marked "reproduced" is one of these tests.
- Claude Code 2.1.286 (`~/.local/share/claude/versions/2.1.286`) is the installed version. Its WebFetch permission matcher compares `domain:` rules by exact host. Only a rule written as `domain:*.example.com` matches subdomains. I confirmed this by reading the matcher in the binary's strings, which is what finding C-B2 rests on.
- Setup images: the PNG headers read 1080×1080 for both profile pictures, 1128×191 for the LinkedIn cover and 1640×624 for the Facebook cover.
- Google Chrome is at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. There are no `sg.jurasolutions.growth.*` jobs in `~/Library/LaunchAgents`, so nothing is scheduled yet.

---

## Social content PRD

### Spec coverage

| PRD item | Status | Evidence |
|---|---|---|
| SC1: by 07:15 SGT, `#social-drafts` has LinkedIn, Facebook and Instagram versions with correctly sized branded images, ready to copy | **partial** | The job runs daily at 07:00 (`config/settings.yaml:54-59`). There is one message per platform with the text in a code block and its images (`agents/social/submit.py:305-338`). Each PNG's size is read back and must match exactly (`render.py:345-347`, test `test_social_render.py:64`). Nothing measures, checks or alerts on 07:15: the string appears nowhere in code, config or docs. The run timeout is 30 minutes (`settings.yaml:24`), so a slow run delivers after 07:15 with no flag. See S-S1 |
| SC2: every draft passes the brand checker; news posts link sources, in Jura's own words | **partial** | Every variant and the card's words go through `gate.gate` (`submit.py:146-164`). LinkedIn and Facebook must link every listed source (`checks.py:170-172`), and news needs sources (`checks.py:177-178`). "Own words" is checked only as double-quoted passages of more than 12 words (`checks.py:44,103-109,180-184`). See S-S4 |
| SC3: no story or tool repeated within 14 days | **implemented for URLs and tool slugs; partial for "story"** | `history.py:83-97`, window `caps.NO_REPEAT_DAYS` (`caps.py:24`). Drafts count whatever became of them (`history.py:4-9`). Tests at `test_social.py:296,302,310,655`. The same story at a different URL passes. See S-S5 |
| SC4: drafts and sources saved to `outputs/growth/social/YYYY-MM-DD/` and logged | **implemented** | Folder at `submit.py:188`, files at `:262-284`, `social_posts` rows at `:287-302`, and the `social.delivered` event at `:216-220`. `sources.md` is skipped when empty (`:265-266`). See S-N2 |
| SC5 / block 3: auto-publish at 09:00 unless skipped | **deferred by plan (confirmed absent)** | `Platform.effective_publish_mode` always returns `"draft"` (`settings.py:60-63`), and a non-draft value only adds a warning (`:164-170`). There is no publish job in `settings.yaml` and no Meta or LinkedIn API code. `social skip` and the `social_skips` table were built early (`history.py:148-166`, `migrations/0001_social.sql:27-33`) |
| 5.1.1 Gather: news from the last 48 h, SG business news, new toolbox tools, original sources | **deviates (documented)** | The prompt covers sources and the 48 h preference (`prompts/social.md:23-43`). Toolbox plan at `toolbox.py:109-125`. In code, Monday's "AI this week" accepts stories up to **7 days** old (`config/social.yaml:35-37`, `drafts.py:125-135`), with the reason given in config and in `docs/social.md:174-175`. Other themes have no age rule. The 8-search and 8-fetch cap is in the prompt only (`prompts/social.md:10`); the hard ceiling is the US$3 budget (`settings.yaml:26`) |
| 5.1.2 Theme from the rhythm, next one if nothing fits | **implemented** | `rhythm.py:19-33`, `social.yaml:18-25`, `--theme` at `submit.py:107-111`. A fallback is recorded in `qa_json` (`submit.py:214`) |
| 5.1.3 One core post, adapted per platform | **implemented** | The prompt asks for one core post (`prompts/social.md:50-86`). The per-platform rules are enforced in code (`checks.py:130-190`) |
| 5.1.4 HTML card templates on the design system, three layouts, PNG per platform size, headless Chromium | **implemented** | `templates/headline.html`, `list.html` and `tool.html` link `design-system/styles.css` (`render.py:237`) and inline the design system's logo SVGs (`render.py:247-249`). Rendering uses headless Google Chrome (`render.py:302-348`). A test asserts there are no raw colours (`test_social_render.py:105`). A few ad-hoc values remain (S-N4, under Standards) |
| 5.1.5 Check every variant with `jura-growth check` | **implemented** | The same channels run inside `submit` (`checks.py:235-251`), and `jura-growth check --channel social-<platform>` runs them by hand |
| 5.1.6 Deliver: three `.md` files, images, `sources.md`, `social_posts` row, `#social-drafts`; "No draft today" when nothing passes | **implemented; partial for failed runs** | `submit.py:178-233`. "No draft today" is posted when everything fails twice (`submit.py:179-186`) or the agent calls `social no-draft` (`commands.py:137-147`). A crash, timeout or budget stop only posts to `#alerts` (`runner.py:133-134`), so `#social-drafts` stays silent. See S-S1 |
| 5.2 Weekly rhythm in `config/social.yaml` | **implemented** | `social.yaml:18-68` matches the table, including Sat/Sun "light" |
| 5.3 Lengths 120–220 / 60–120 / 50–120 | **implemented** | `social.yaml:79,88,97`, `checks.py:142-145`. Links and hashtags don't count as words (`checks.py:79-81`) |
| 5.3 Links: in the post, in the post, "Link in bio" with no URL | **implemented** | `checks.py:159-175`. Instagram refuses any URL or bare domain and requires "Link in bio" (`checks.py:159-163`, test `test_social.py:396`) |
| 5.3 Images 1200×627, 1200×630, 1080×1350 | **implemented** | `social.yaml:82,91,100`, checked exactly (`render.py:345-347`) |
| 5.3 Instagram carousel of up to 5 on Mon and Thu | **implemented, with a gap** | `social.yaml:101`, `submit.py:194-197`, `render.py:168-187`. Config can raise the cap to 10 (`settings.py:184`). The 5th item of a 5-item list gets no slide (S-N1) |
| 5.3 Hashtags: up to 3 at the end, 0–2, up to 8 at the end | **implemented** | `checks.py:147-153`. Every hashtag must sit on the trailing hashtag lines |
| 5.4 `social_posts` columns | **implemented** | `migrations/0001_social.sql:4-22` has every PRD column, plus `tool_slug`, `run_id`, `created_at` and `updated_at`, and is unique on (date, platform) |
| 5.5 Setup checklist with the three accounts and images from the card templates | **implemented** | `outputs/growth/setup/social-accounts.md:60-115`, images from `render.py:395-417` (sizes verified above) |
| §4 Images from design-system tokens and assets only | **implemented, minor exceptions** | No hex or rgb values, and every `var()` is a design-system token. Exceptions are at `card.css:102,278,295` (S-N4) |
| §4 News: short quotes with attribution, always link the original, no speculation as fact | **partial** | Quote length: only double quotes are checked (S-S4). LinkedIn and Facebook must link every source; Instagram names sources in words. Speculation is prompt-only (`prompts/social.md:38-40`) |
| §4 No politics, elections, tragedies, named private individuals, criticism of competitors | **partial** | Politics and tragedies are a word list (`social.yaml:113-135`, `checks.py:186-187`). Named private individuals and criticism of competitors are prompt-only (`prompts/social.md:38-39`) |
| §4 Grants and schemes: official page, linked, the eligibility sentence, never imply Jura secures funding | **partial** | `checks.py:193-211` requires the exact sentence, a `.gov.sg` link on LinkedIn and Facebook, and no funding claims. The detector misses many scheme names (S-S2, reproduced) |
| Block 1 done-when | **met in tests** | Three variants pass with sized images (`test_social.py:490`), Monday news with a carousel (`:514`), broken links refused (`:579`). I did not observe a live run |
| Block 2 done-when | **met in tests** | Two runs pick different stories (`test_social.py:655`). Digest figures at `agents/social/__init__.py:39-76` (`test_social.py:710,725`) |

### Spec findings, ranked

**Blocking:** none.

**Should fix**

- **S-S1. The 07:15 deadline is neither measured nor reported, and a failed run leaves `#social-drafts` silent.** This breaks SC1 ("Every morning by 07:15 SGT, `#social-drafts` holds...") and §5.1.6.
  - Nothing compares delivery time with 07:15.
  - launchd runs a missed 07:00 slot when the Mac wakes, so drafts can arrive hours late with no mark.
  - When the headless run fails, the runner only alerts `#alerts` (`runner.py:133-134`). Social has no hook to post "No draft today" in `#social-drafts`.
  - Fix: record the delivery time in `qa_json` and the digest. Flag `#alerts` and the digest when delivery is after 07:15. On a failed `social` run, post a short "No draft today (the run failed: …)" to `#social-drafts`.
  - Block 3 depends on this, because its two-hour skip window assumes the drafts arrived at 07:00.
- **S-S2. The grant and scheme detector misses common scheme names (reproduced).** This breaks §4: grants are "linked, with 'Check the official page for current eligibility.'"
  - `GRANT_RE` (`checks.py:45-49`) does not match "Jobs Growth Incentive", "Senior Employment Credit", "CDC vouchers", "Market Readiness Assistance" or "rebate".
  - A post about any of these needs neither the eligibility sentence nor the `.gov.sg` link.
  - Fix: add incentive, credit, voucher, rebate, assistance, support scheme, co-pay and similar terms, and add tests.
- **S-S3. Jura's own links are never checked, and the toolbox registry is read from whatever branch is checked out.** This touches §5.3 (links in the post) and the block 1 done-when ("working source links").
  - `linkcheck` covers `sub.urls` only (`submit.py:125`). The tool URL and `jurasolutions.sg` links go out unchecked (`submit.py:143`, `checks.py:173-175`).
  - The registry comes from `repos/landing-page/src/apps/registry.json` (`toolbox.py:24,45-46`), and that checkout is on the `toolbox` branch.
  - The domain is not live yet (root CLAUDE.md open thread: DNS to Cloudflare Pages). Today's drafts would point readers at pages that may not resolve.
  - Fix: link-check the Jura links too, at least the tool URL, or hold tool posts until the site answers.
- **S-S4. "Own words" is enforced only for double-quoted passages (reproduced).** §4 asks you to "rewrite in Jura's own words, quote at most a short phrase".
  - `QUOTE_RE` (`checks.py:44`) skips ‘single’ and 'straight single' quotes, and unquoted copying is not detected at all.
  - Fix: extend the quote marks. A stronger fix is to compare each variant with the text of the pages fetched in the link check (word-trigram overlap, like `community/plan.py:140-148`).
- **S-S5. The 14-day rule compares URLs, not stories.** SC3 says "No story or tool is repeated within 14 days."
  - `history.repeats` (`history.py:83-97`) blocks a repeated normalised URL. The same announcement from another outlet passes.
  - A tool counts only when the card uses the tool layout (`submit.py:118`), so a tool named in a Tuesday tip is not tracked.
  - Fix: either record a story key, such as the headline or the original announcement URL, or amend the PRD to say "story URL".
- **S-S6. Images can go out off-brand, and the post only carries a note.** SC1 asks for "correctly sized branded images".
  - If the Google web fonts don't load, the PNGs are delivered in fallback fonts with a note in the footer (`submit.py:199-203`). There is no `#alerts` entry.
  - `card.js:19` stops shrinking text at 0.56 scale. Anything still overflowing is clipped (`card.css` `.main { overflow: hidden }`), and nothing reads `data-fit` back to catch it.
  - Fix: alert on missing fonts, and fail the render (or note it) when `data-fit` hits the floor.
- **S-S7. `sources.md` refuses addresses with brackets that the core handles (reproduced).**
  - `drafts.URL_RE` (`drafts.py:22-24`) claims "same stopping characters as `brand_check.find_links`", but core has accepted balanced brackets since `00f163f` (`brand_check.py:153-155`).
  - So IRAS pages such as `.../goods-services-tax-(gst)/...` are refused (`drafts.py:61-62,98-102`). That is the official source the Friday explainer needs.
  - `docs/social.md:208-209` describes the old behaviour.
  - Fix: reuse `brand_check.find_links` in `drafts._parse` and delete the known-issue entry.

**Nit**

- **S-N1. A five-item list loses its fifth slide (reproduced).** The list layout takes 2–5 items (`render.py:127-128`), but `slides()` keeps the cover plus 4 (`render.py:173`). The cover still shows all five.
- **S-N2. `sources.md` is only written when it has content** (`submit.py:265-266`). PRD §5.1.6 lists it in every day's folder. Write an empty one, or "No sources".
- **S-N3. Precheck allows a second full headless run after a partial day.** When the final attempt dropped one platform, `active` is non-empty and the status is `partial`, not `dropped` (`agents/social/__init__.py:91-96`). A manual re-run then spends a run only to hit "used-up".
- **Scope added beyond the PRD (accepted, listed for the record):** `social skip` (a block 3 item), `social published`, `social render`, `social setup-images`, `qa.json` and `card.json` in the output folder, and the `social_skips` and `social_submissions` tables. All are small and support the PRD.

### Human setup items (social)

| Item | Where the code or docs read it |
|---|---|
| Create the LinkedIn company page (Ting Yu as super admin), the Facebook Page and the Instagram professional account, linked in Meta Business Suite | `outputs/growth/setup/social-accounts.md:60-95` |
| Decide the page name and handles (`@jurasolutions`, or `jurasolutionssg` if taken) and the contact email for the pages | `social-accounts.md:18-22` (all "to be confirmed") |
| Upload the profile and cover images, already rendered at the right sizes | `outputs/growth/setup/social-images/*.png`; regenerate with `jura-growth social setup-images` (`commands.py:172-184`) |
| Google Chrome at `/Applications/Google Chrome.app/...` (present on this Mac) or `JURA_GROWTH_CHROME` | `config/social.yaml:146`, `settings.py:199`, `render.py:287-290,305` |
| Network access to `fonts.googleapis.com` at 07:00 for Outfit, DM Sans and IBM Plex Mono | `design-system/tokens/fonts.css:5` via `styles.css:1`; checked at `render.py:351-362`, `submit.py:199-203` |
| The design system checkout with `styles.css` and the logo SVGs (present) | `render.py:60-61,197-200,237,247-249` (`paths.JURA_ROOT/design-system`) |
| The toolbox registry with at least one `live` tool (today: `quote-builder` on the landing-page `toolbox` branch) and a live jurasolutions.sg so tool links resolve | `toolbox.py:24,45-79`; `config/social.yaml:12` (`site`) |
| Optional: a copy of the site's D1 `app_usage` table in growth.db for "most used". Nothing syncs it yet | `toolbox.py:87-106` |
| Discord webhooks `DISCORD_WEBHOOK_SOCIAL_DRAFTS` and `DISCORD_WEBHOOK_ALERTS` in `.env` (I did not read `.env`) | `discord.py:43-50`; placeholders in `.env.example:15,17` |
| Install the schedule (`jura-growth schedule install`) and keep the Mac awake at 07:00 | `config/settings.yaml:54-59`; nothing is installed yet |
| Post by hand, then `social skip` or `social published` | `social-accounts.md:97-115` |

### Open PRD questions (social)

1. **Handles and page names:** still open (`social-accounts.md:18-19`).
2. **Weekend posts:** defaulted to yes (`config/social.yaml:7-10`), waiting for Ting Yu to confirm.
3. **Which platforms go to `auto` first:** still open; it belongs to block 3.
4. **New, from this review: the Monday 7-day news window** deviates from §5.1's "last 48 hours". It is documented in code. Recommended: amend the PRD to say "AI this week: last 7 days".

### What block 3 will need

- A 09:00 publish job in `config/settings.yaml`.
- Real `auto` handling in place of the hard-coded `effective_publish_mode` (`settings.py:60-63`).
- Respect for `social_skips` and `status = 'skipped'`.
- `published_url` and `published_at` filled from the API response. The columns already exist (`0001_social.sql:14-15`), and `history.mark_published` currently logs `how: by hand` (`history.py:169-181`).
- Meta: an app Ting Yu owns, a long-lived Page token and the Instagram business account ID as new `.env` keys (never in config). The exact permissions and review steps are to be confirmed at build time, as the PRD says.
- Instagram's content publishing API takes images by public URL (verify at build time). The local PNGs would need a public host, and carousels need child containers.
- LinkedIn: Community Management API approval for `w_organization_social`, the organisation URN, image upload and token refresh. If approval doesn't come, LinkedIn stays manual.
- A rule for late drafts (S-S1). The skip window should run from delivery, not from 07:00.
- Section 7 of `social-accounts.md` written with the app and token steps.

---

## Community scout PRD

### Spec coverage

| PRD item | Status | Evidence |
|---|---|---|
| SC1: register with audience, apparent activity, promotion rules and fit rating, from web search only | **implemented; web-search-only is only partly enforced** | `groups.py:76-159` requires name, URL, fit, fit_reason, promo_rules and at least one non-Facebook source URL, and records audience and size/activity hints. The Facebook fetch block has gaps (C-B2) |
| SC2: every Monday, a plan for up to 3 joined groups in `#community` and `outputs/growth/community/`, a different value-first post per group that respects its rules, plus reply ideas | **deviates (bug)** | The plan and checklist work (`plan.py:257-455,573-648`). For common negated phrasings, "respects that group's rules" is inverted (C-B1) |
| SC3: everything passes the brand checker | **implemented** | `plan.py:483`, channels `community-post` and `community-reply` (`agents/community/__init__.py:36-48`, `plan.py:683-717`) |
| SC4: posted items recorded; no group suggested twice within 14 days | **implemented** | `posted` and ticks at `plan.py:520-567`; rotation at `plan.py:333-349`; open days in `context` (`__init__.py:214-233`); test `test_community.py:288` |
| 5.1.1 Search for SG SME, F&B, contractor and other groups | **implemented (prompt)** | `prompts/community.md:32-41` |
| 5.1.2 Record name, URL, audience, approximate size, apparent activity, stated promotion rules | **implemented** | `groups.py:23,76-128`, `migrations/0001_community.sql:3-27` |
| 5.1.3 Rate `good fit`, `possible` or `skip` with a reason | **implemented** | `groups.py:20,98-103`; `CHECK` constraint at `0001_community.sql:25` |
| 5.1.4 `jura-growth community set <id> joined=yes rules="..."` | **implemented** | `groups.py:162-201`, `__init__.py:172-186`, test `test_community.py:213`. The headless run can call it too (C-S1) |
| 5.2 Only groups marked joined and good fit | **implemented** | `groups.py:228-233` (Facebook, joined, good fit, not removed) |
| 5.2 Up to 3 groups a week (config) | **implemented** | `plan.py:47-48,392-395`, `caps.py:23`, config can only lower it (`test_community.py:281`) |
| 5.2 None repeated within 14 days | **implemented** | `plan.py:333-349` (config may lengthen, never shorten: `plan.py:51-52`) |
| 5.2 None on a day its rules forbid | **deviates (bug)** | `rules.py:142-163`, applied at `plan.py:378-380`. See C-B1 |
| 5.2 A fresh post per group, 60–150 words | **implemented** | Words at `plan.py:351-354`. Shared sentences and trigram similarity across this week and the last 28 days at `plan.py:397-409,140-159` |
| 5.2 Promotion in one closing line linking one toolbox tool and jurasolutions.sg with `utm_source=facebook_group&utm_campaign=<slug>` | **implemented** | `plan.py:165-210`, brand channel at `plan.py:683-704`, test `test_community.py:361,368` |
| 5.2 Unknown rules: a value post with no link | **implemented, stricter than the PRD** | `plan.py:359-365` also refuses links until `rules_confirmed`, which suits §4 ("Ting Yu ... confirms each group's real rules") |
| 5.2 2–3 reply ideas, no links | **partial** | No links (`plan.py:442-443`) and at most 3 (`plan.py:451-454`). The minimum of 2 is read but never enforced. See C-S4 |
| 5.2 Optional image from the social card templates | **implemented, unsafe** | `image_path` at `plan.py:316,388-389`, attached at `plan.py:644`. See C-S2 |
| 5.3 `outputs/growth/community/YYYY-Www.md` checklist with day, group link, text, image and rules reminder, posted to `#community` | **implemented** | `plan.py:573-648` |
| 5.3 `community posted <item-id> [url]` or tick; the next Monday run reads ticks | **implemented** | `plan.py:520-567`. `context` syncs ticks first (`__init__.py:209`); so do `plan-add` and `publish-plan` |
| 5.3 Admin removal or warning sets the group to permanent `skip` | **implemented** | `groups.py:204-217`. It can't be undone through `set` (`groups.py:188-189`), and its planned posts are skipped |
| 5.4 Non-Facebook communities tagged by channel; drafts only for Facebook | **implemented** | `groups.py:21` channels, `groups.py:232` `channel = 'facebook'`. `whatsapp` was added |
| 5.5 `community_groups` and `community_posts` columns | **implemented** | `0001_community.sql` has every PRD column, plus slug, url_key, removed, source_urls_json, question and posted_via |
| Block 1 done-when: at least 10 groups with source URLs and rule notes; the run log shows no facebook.com fetches | **partial** | The prompt asks for 12 on the first run (`prompts/community.md:41`); there is no count check in code. Every record must carry source URLs and promo_rules (`groups.py:104-126`). The audit is built: `audit-run` and the digest (`__init__.py:78-91,386-445`), tests at `test_community.py:450-528`. Prevention has gaps (C-B2) |
| Block 2 done-when: 3 different texts that pass and respect each group's rules; a ticked item recorded | **met in tests, but the rules half fails for negated rules** | `test_community.py:234`. My reproduction for C-B1 |
| §3 Nothing posts to Facebook groups automatically; no browser automation; no facebook.com fetch | **confirmed for posting and browser use; partial for fetching** | Neither agent calls a Facebook API. The only outbound HTTP is `social/linkcheck.py:45-54` and Discord webhooks. Chrome only renders local files (`render.py:302-348`). For fetching, see C-B2 |
| §4 No DMs, tagging or collecting members' details | **implemented** | `TAGGING` at `plan.py:33-37`, checked at `:386-387,444-445,689-690,715-716` |

### Spec findings, ranked

**Blocking**

- **C-B1. The rules parser reads negated day rules as permissions (reproduced).** The PRD asks for "none on a day its rules forbid" (§5.2), and the block 2 done-when asks for posts that "respect each group's rules". §1 says groups "remove or ban members who post repeated or purely promotional content".
  - In `rules.parse` (`rules.py:142-145,153-156,162-163`), any clause with a day becomes the set of allowed days, whatever the negation.
  - "No promotion on weekends." parses as *promotion only on Sat, Sun*.
  - "No posts on Sundays." parses as *posts only on Sun*.
  - "Promotion allowed Monday to Friday. No links on weekends." parses as promotion on all seven days.
  - All three come back `parsed = True`, so no human `rules_ok` is asked for. `context` then offers exactly the forbidden days as `days_open` (`__init__.py:222-233`), and the checklist shows the wrong "Planned as" line (`plan.py:615`).
  - The test table (`test_community.py:133-147`) has no negated-day case without "except".
  - Fix: when a clause is negative and has no `EXCEPT_RE`, treat its days as forbidden (complement the set, or keep a `banned_days` set). Mark mixed or ambiguous clauses `parsed = False` so `rules_ok` is required. Add the three cases above as tests.
- **C-B2. The facebook.com fetch block covers six exact hosts, and the config says otherwise.** §3 rules out "Fetching or scraping facebook.com pages" and §4 says "No fetches of facebook.com". The README says "the community job can't fetch facebook.com".
  - The deny list is `config/settings.yaml:93-99`: facebook.com, www, m and web, plus fb.com and fb.me.
  - Claude Code 2.1.286 matches `WebFetch(domain:…)` by exact host (see Evidence), so `mbasic.`, `business.`, `l.`, `touch.` and locale subdomains of facebook.com stay fetchable.
  - `fb.watch`, `fbcdn.net`, `facebook.net` and `messenger.com` are in `config/community.yaml:28` but not denied at all (reproduced). `community.yaml:26` claims "settings.yaml denies WebFetch on them too".
  - The audit (`__init__.py:404-445`) matches suffixes, so it would *detect* such a fetch afterwards, but nothing *prevents* it.
  - Fix: add `WebFetch(domain:*.facebook.com)`, `WebFetch(domain:*.fb.com)`, the four missing apexes and their `*.` forms. Better still, generate the deny list from `groups.blocked_domains()` in `runner.claude_command`, so the two lists can't drift. Add a test that every blocked domain and its wildcard appear in the argv.

**Should fix**

- **C-S1. A headless run can perform Ting Yu's own steps (reproduced for `set`).** §5.1.4 says "Ting Yu updates `joined`, `rules_confirmed`"; §4 says "Ting Yu joins groups himself and confirms each group's real rules".
  - The runner allows `Bash(jura-growth:*)` and denies only `run`, `resume` and `schedule` (`runner.py:226-238`).
  - So the community run can execute `community set <id> joined=yes rules_confirmed=yes`, which makes a group plannable and link-eligible. `groups.py:162-201` has no guard.
  - It can also run `community posted` and `removed`, and any other agent's commands. `social submit` fetches any URL in a `sources.md` with httpx (`linkcheck.py:30-32`), which gets around the Facebook deny list, and the audit can't see it.
  - Fix: deny `Bash(jura-growth community set:*)`, `posted`, `removed`, `social skip`, `social published` and `social submit` in the community job's `disallowed_tools`. Alternatively, refuse those commands when `JURA_GROWTH_JOB` is set.
- **C-S2. `plan-add` accepts any existing file as `image_path`, and `publish-plan` uploads it to Discord (reproduced with a dummy file).**
  - The only check is `Path(item.image_path).is_file()` (`plan.py:388-389`). `publish` attaches the file (`plan.py:644`), and `discord.post` uploads attachments when a webhook is set (`discord.py:110-116`).
  - The runner denies `Read(.env)` (`runner.py:233`), but this path lets a run, or a page that injects instructions into it, push `.env` or any file under `jurasolutions/` to `#community`.
  - Fix: accept only `.png` files under the job's scratch folder or `outputs/growth/`, and check the PNG header (`render.png_size`).
- **C-S3. A reply idea can get three brand-gated attempts (reproduced).** CLAUDE.md says "A second failure drops the item"; foundation §5.6 says regenerate once.
  - The gate key is positional: `community:<week>:reply:<n>`, where `n` starts at the count of stored replies (`plan.py:467-482`).
  - When an earlier reply fails and a later one in the same batch passes, the resubmitted failing reply gets a fresh key. My test shows retry, then retry, then dropped.
  - Fix: key replies by their question (normalised) or by a stable id from the plan file.
- **C-S4. The minimum of two reply ideas is not enforced.** §5.2 asks for "2–3 helpful-reply ideas".
  - `replies_range()` returns the minimum, and `prepare` discards it (`plan.py:451`). A plan with no replies is accepted and published.
  - Fix: require at least the configured minimum when the week has posts.
- **C-S5. The block 1 target of at least 10 groups is prompt-only.** `community summary` posts whatever was added (`__init__.py:344-383`). A short register is reported as a normal run. Fix: add a "below 10 groups" line to the summary and the digest until the register reaches 10.

**Nit**

- **Scope added (accepted):** the `whatsapp` channel, `audit-run`, `rules_confirmed` as a precondition for links (stricter than the PRD), the `question` column on reply ideas, and `posted_via`.

### Human setup items (community)

| Item | Where |
|---|---|
| Decide whether Ting Yu posts personally or as the Jura Facebook Page (open question 1). The default is personally | `config/community.yaml:22-24`, `plan.py:588,594`, prompt example at `prompts/community.md:78-82` |
| Join the good-fit groups, read the real rules inside, then `jura-growth community set <id> joined=yes rules="…" rules_confirmed=yes` | `docs/community.md:32-34`; register summary hint at `__init__.py:376-382` |
| Post each item by hand; tick `- [x]` or run `community posted <id> [url]`; on an admin warning run `community removed <id>` | `plan.py:594-597` (checklist header) |
| The Discord webhook `DISCORD_WEBHOOK_COMMUNITY` (and `_ALERTS`) in `.env` (not read) | `.env.example:16-17`, `discord.py:43-50` |
| Install the schedule; the job runs Mondays at 07:30 | `config/settings.yaml:88-100` |
| A live toolbox tool for the closing-line link (today: `quote-builder`), and a live site | `plan.py:106-115,208-209` |
| Optional images: `jura-growth social render` must exist at run time (it does) | `__init__.py:250-278` (`image_renderer`) |

### Open PRD questions (community)

1. **Post as Ting Yu personally or as the Jura Page:** defaulted to personally (`config/community.yaml:22-24`), waiting for confirmation.
2. **Three groups a week:** defaulted to 3, the hard cap (`config/community.yaml:7`, `caps.py:23`), waiting for confirmation.

---

## Standards

The sources are the repo's `CLAUDE.md` and `README.md` (plug-in interface; hard limits in `caps.py`), `jurasolutions/CLAUDE.md` (built from the design system's tokens, never ad-hoc styles) and the Fowler smell baseline. Every smell below is a judgement call.

**Blocking:** none.

**Should fix**

- **ST-1. Reuse: community copies the social agent's toolbox registry reader, and the copies already disagree.**
  - `community/plan.py:106-115` reimplements `social/toolbox.py:45-79`.
  - Community accepts `{"apps": [...]}`; social rejects anything that isn't a list (`toolbox.py:58-59`). If the registry shape changes, one agent will see tools and the other won't.
  - Fix: move the reader to a core module, as was done with `transcripts.py`.
- **ST-2. Reuse: platform sizes are defined three times.**
  - The places are `render.SIZES` (`render.py:44-48`), `settings.DEFAULT_PLATFORMS` (`settings.py:119-126`) and `config/social.yaml:82-100`.
  - `social render` with no `--size` uses `render.SIZES`, not the config (`commands.py:83-85`). A config change would split the command from `submit`.
  - Similar duplication: `settings.DEFAULT_THEMES` and `DEFAULT_RHYTHM` repeat the yaml (`settings.py:92-118`), and the URL-normalising prefix logic is repeated (`history.py:29`, `community/groups.py:40`, `community/plan.py:187,698`).
- **ST-3. PRD limits sit in config with no ceiling, while `settings.yaml:3-4` says config may only lower a limit** (README: "its hard limits in `caps.py`").
  - Word ranges, hashtag maxima and image sizes are read without bounds (`settings.py:177-181`). The carousel clamp is 10, not the PRD's 5 (`settings.py:184`). Community word ranges are the same (`plan.py:55-59`).
  - `caps.SOCIAL_POSTS_PER_PLATFORM_PER_DAY` is never read; only the unique index enforces it (`0001_social.sql:21-22`, comment at `submit.py:82`).
  - Fix: put the PRD values into `caps.py` and use `caps.effective`.

**Nit**

- **ST-N1. Ad-hoc values in the card CSS.** `card.css:102` uses `letter-spacing: 0.02em`, which matches no token (the tokens are 0.005em and 0.11em). `card.css:278` and `:295` use raw `270px` and `300px` padding. The header's "every … space below is a design-system token" (`card.css:3-5`) is therefore not quite true. The type sizes are in px on purpose, and the header explains why.
- **ST-N2. Magic numbers.**
  - `social/plan.py:23` uses `>= 2` where `gate.MAX_ATTEMPTS` exists.
  - `commands.py:151` uses `default=14` where `caps.NO_REPEAT_DAYS` exists.
  - `community/plan.py:644` uses `[:10]` where `discord.MAX_FILES` exists.
- **ST-N3. Data clumps.** `submit._write_outputs`, `_log_rows` and `_post` (`submit.py:262,287,305`) pass the same day, theme, submission, results and images bundle as 10–12 positional arguments. A small `Delivery` dataclass would carry it.
- **ST-N4. Middle man.** `community/transcript.py` is a four-line re-export added in a brand-new file. It exists because `apps/factory.py` imports it; import `jura_growth.transcripts` directly there.
- **ST-N5. Divergent change.** `community/__init__.py` (445 lines) holds the plug-in hooks, every click command and the audit. Social keeps its commands in `commands.py`.
- **ST-N6. Speculative generality (acceptable).** `PUBLISH_MODES` and `effective_publish_mode` (`settings.py:18,51,60-63,164-170`) are the seam for block 3, and their docstrings say so. Keep them, but cover them with block 3's tests when it lands.
- Tests follow the README rule: `conftest.py` isolates every path, link checks are monkeypatched or use `MockTransport` (`test_social.py:168,600`), and real Chrome runs offline (`render.py:320-321`).

---

## Security

I ran `security-review` as a skill, but its diff was empty because `main` is clean with no pending changes. I applied its method by hand to the fixed-point diff, without sub-agents (the fan-out budget was spent on the two review axes).

**High-confidence vulnerabilities (confidence 8 or above): none.**

Checked and clean:

- **SQL.** `set_fields` builds its `SET` clause only from the `SETTABLE` whitelist (`groups.py:162,179-180,198-199`). The `app_usage` column names come from a fixed list (`toolbox.py:97-101`). Everything else is parameterised.
- **Command injection.** Chrome runs from an argv list with no shell (`render.py:307-325`).
- **Template and HTML injection.** Every `{{…}}` value is escaped. The raw `{{{…}}}` slots get `_text()`-escaped text or design-system SVGs (`render.py:203-216,243-269`). This matters because Chrome renders the page from a `file://` URL.
- **Discord mentions.** `allowed_mentions: parse []` (`discord.py:147`) stops group names fetched from the web from pinging `@everyone`.
- **PII.** The register stores group names and links, not members. Tagging and "DM me" are refused (`plan.py:33-37`).

Defence-in-depth items. They are filtered out of the high-confidence list because each needs the headless agent to misbehave or be steered by injected page content, but they cross a boundary the repo states (the runner's `.env` deny and "Ting Yu does X himself"):

- **C-S2, should fix.** An arbitrary file can be uploaded to Discord through `image_path` (`plan.py:388-389,644`). This gets around `Read(.env)`.
- **C-S1, should fix.** A headless job can run human-only and other agents' commands (`runner.py:226-238`). That includes an unfiltered httpx GET through `social submit` (`linkcheck.py:45-54`, `follow_redirects=True`). It is a blind GET, but it reaches any host, including the LAN and Facebook.
- **C-B2, blocking for spec reasons.** The facebook.com deny list has gaps. It is a compliance control rather than a vulnerability.

Blocked paths: the diff writes nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`, the paths the operating card lists. The `design-system/` files are only read, through `file://` URLs. My own check runs used temp folders only.

---

## How the verdict follows

The verdict is changes-requested because of C-B1 (the rules parser inverts forbidden days) and C-B2 (Facebook subdomains and four listed domains are not denied).

Both live in the community scout, and both are small, testable fixes:

- C-B1: a negation branch in `rules.parse`, plus three test cases.
- C-B2: wildcard deny rules generated from `groups.blocked_domains()`.

The social agent meets its blocks 1–2 done-when conditions in tests, and block 3 is absent as planned. Its should-fix items are S-S1 to S-S7. The first to schedule are S-S1 (the 07:15 deadline and the silent failure) and S-S2 (scheme detection), before Ting Yu starts posting.
