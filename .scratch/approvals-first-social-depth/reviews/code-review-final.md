# Final code review: approvals first, feeds after, social depth

Reviewed `crew/approvals-first-social-depth` at `f0db1e5` against its merge-base with `origin/main`, `68a1911`. That merge-base is main's tip, so this branch holds all of main, including PRs #15, #16 and #17. The spec is the PRD (`jurasolutions/prd/pending/prd-jura-approvals-first-social-depth-2026-10-31.md`) and `reviews/functional.md` §3.

## Verdict: changes-requested

Two findings block. Both are small fixes, and each needs a test that fails today.

- **The 18:05 digest and the next morning's brief still report expired posts as waiting (SP-B1).** This is real, and it is what Ting Yu asked to stop.
- **A typed approval of a refused card is recorded and the post is claimed (SP-B2).** This is the one part of round 2's R2-B2 that doesn't hold in a real process.

Everything else in round 2 holds. No blocked path changed. Nothing can post without a human approval of its exact hash. Normal outreach emails and app PRDs pass the stricter numbers rule. The pyright errors in the editor are almost all it reading the main checkout.

## Standards

No blocking findings.

### Should fix

- **ST-S1. The plug-in interface doesn't document the new hooks.** `CLAUDE.md` says "`README.md` covers layout, commands, tests and the plug-in interface". The kind members `feed_channel`, `feed_approved`, `card_problem` and `own_copy` are missing from the table at `README.md:241-245`, and `FEED_CHANNEL` (`feed.py:43`, `outreach/__init__.py:18`) is missing from the plug-in table at `README.md:191`. A grep of `README.md` and `agents/__init__.py` finds none of them, apart from a general mention of `own_copy` at `README.md:150`.
- **ST-S2. Two documents contradict the numbers rule as it now runs.** `CLAUDE.md` says "Only the phrases in `config/approved_claims.yaml`". `compose.py:488` adds a second allowed figure through `allowance=CALL_ASK_RE`. The conductor's ruling allows this, so update the rule or add the claim to the file.
- **ST-S3. Reuse.**
  - `visuals.py:206`: `2 * 3.14159` duplicates `math.tau`.
  - `mission.py:431`: `'approval.card_refused'` duplicates `cards.REFUSED_EVENT` (`cards.py:58`).
  - `privacy.py:111`: `"[redacted]"` repeats the literal in `config.py:248,256,258,304`.

### Nits and judgement calls

- `checks.py:252` and `prompts/social.md:272` show the run literal figures ("3,000 to 4,000"). Round 1 removed "86%" from the prompt because a model copies what it sees.
- `limits.py:20`: `DECIDE_BEFORE_CLOSE` is a hard deadline outside `caps.py`. Config can't raise it, so the lower-only rule holds.
- `docs/agents/crew.md:12` says pyright reports 84 errors. It now reports 70 on main and 73 here. `:9` says the venv is Python 3.12, and this worktree's is 3.14.
- Possible Duplicated Code: the "Nothing goes out, and it lapses" wording at `health.py:179` and `cards.py:248`; the same fence at `kinds.py:203` and `group_kinds.py:306`; the `stated` set at `drafts.py:145,180`.
- Possible Primitive Obsession: `cards.py:272` `_card_title` scrapes the title back out of stored text. `checks.py:255` infers the kind of mask from its rendered words.
- Possible Divergent Change: core `privacy.py:89` now holds social's theme vocabulary, so new post wording can mean editing core masking.

## Spec

Every criterion in `functional.md` §3 has a code path and a test, apart from the two blockers and the partial items below: AF1–5 (`test_approvals_first.py`), FD1–4 (`test_feed.py`, `test_feed_real_kinds.py`), DP1–5 (`test_social_depth.py`, `test_social_prompt.py`), PC1–3 (`test_social_visuals.py`, `test_social_figures.py`, `test_social_cards_real_chrome.py`), SC1 (`test_schedule_drift.py`).

### Blocking

**SP-B1. Expired posts still read as waiting.** `agents/social/__init__.py:52`, `:71`, `:78-79`, `:98`; `digest.py:82`.

- **Rules broken:**
  - Functional B3 names this exact defect: the digest "reads '2 drafts waiting in #approvals'" after the day has closed. The PRD amendment moved the digest to 18:05 for that reason, "so an unanswered card closes".
  - AC FD1 and Ting Yu's own words: "The updates and feeds after they are approved, skipped or sent".
- **Reproduced through the real `digest` command** at 18:05, on the Discord double, with two unanswered cards:
  - `Publishing: 0 posted, 0 skipped, 2 expired, 0 stopped`
  - `Social: 2 drafts with no card (facebook, instagram), 0 skipped, 0 published`
  - `social_drafts_waiting: 2`
  - `brief_line: Jura growth, 2026-11-10: no app PRD today; 2 social drafts waiting.`
- **Why it matters:** `brief_line` is what the 08:00 morning brief prints, so the next day opens by saying two posts are waiting when neither can ever go out. The same digest contradicts itself ("2 expired"), and "with no card" is false, because each had a card that lapsed.
- **Also wrong:**
  - An approved post not yet claimed reads "1 draft with no card" on a digest run before 18:00.
  - An approved post that lapsed unused reads the same at 18:05.
  - `on_expire` leaves `social_posts.status = 'draft'` (`kinds.py:24-25`), and the digest counts that status.
- **Why the tests pass:** `test_digest_closes_the_day.py:16` checks `publish_expired` and never reads the social line or the brief. `docs/social.md:467-470` documents the wrong wording as intended.
- **Fix:**
  - Read the latest request for each draft, as `items.platforms_on_a_card` already does.
  - A post waits only while its request is pending. An approved one says it is waiting on a publish run.
  - A closed one leaves `social_drafts_waiting` and the brief, and the line counts it as expired.
  - A refused card stays "with no card", since its request is still open.
  - Add assertions on the figure, the line and `brief_line` to `test_digest_closes_the_day.py`, and correct `docs/social.md`.

**SP-B2. A typed approval of a refused card goes through in a real process.** `agents/publish/kinds.py:235-251`.

- **Rules broken:** PRD §4, "Nothing goes out without an approval of that exact content". Round 2's R2-B2, "Have the kind refuse the typed approval too". `docs/social.md:325`, "a typed approval is refused".
- **Cause:** `card_problem` asks `privacy.own_copy_as_shown`, which masks with what this process has learned. Nothing on the decision path learns first. `remote.py:412` loads the masks in `_masked`, after the decision has run, and `cards.py:179` loads them only for the sweep. A learned name is the only realistic reason a post past the gate is refused, since the gate already stops phones and addresses.
- **Reproduced through `jura-growth remote approve`**, with a real `contacts` row naming a word in the post, and `config.reset_caches()` standing in for a new SSH process:
  - The sweep refuses the card, and the one note goes to #social-drafts.
  - `{"answer": "recorded", "text": "A-0001 approved."}`, status `approved`.
  - The next `publish next` claims `P-0001 facebook`.
- **Why the test passes:** `test_approvals_first.py:579` plants a phone number, which masks by pattern in any process, and it runs in the process that already knows everything.
- **How likely:** rare. It needs a failed first post or a name learned between the gate and the sweep, and then Ting Yu typing `/growth approve` after a note that says the post has no card. The hash still binds. It is still a yes to words he hasn't read on a card, and the docs say this can't happen.
- **Fix:** call `privacy.learn(conn)` at the top of `card_problem`, or have `on_approve` refuse when `cards.refusal(conn, latest.id)` is set. Add a test with a `contacts` row and `config.reset_caches()` before the decision.

### Should fix

- **SP-S1. The numbers rule, the masking vocabulary and the typed refusal aren't in the PRD.** PRD §3 says "In: §2. The social prompt and docs" and "Out: Any change to how an approval is decided, claimed or bound".
  - Any digit in a sentence with we, our, us or Jura now fails on every channel, including outreach and app PRDs (`brand_check.py:593`, `:650`).
  - `NOT_NAMES` changes what Discord shows everywhere (`privacy.py:85-92`).
  - `on_approve` adds a refusal to a decision (`kinds.py:244`). It stays inside the kind and `decide()` is untouched, as round 2 advised.
  - All three are reasonable, and the crew-log records the first two as rulings. Ting Yu hasn't read the PRD and the merge is his acceptance, so add them to the PRD's amendments and put them in the PR body.
- **SP-S2. The health strip and the docs don't mention the new lines.** `CONTEXT.md:89-94` lists what "Needs you" holds, and it lacks schedule drift (`health.py:168`) and refused cards (`health.py:179`). A grep finds no doc that mentions drift. Ting Yu is told to restart the Mac by a line nothing explains.
- **SP-S3. `social today` offers Facebook a carousel.** `plan.py:69` is `p.carousel_on(day) or theme.carousel` for every platform, while `submit.py:211` allows only Instagram. On 10 November the plan gives `facebook: (True, 1)`, which prints "carousel of up to 1 today", in the text the run reads. DP3 says "Instagram posts them as a carousel".

### Nits

- `visuals.py:204`: "12.75%" and "62 per cent" draw no ring. PC1 says "with a ring for a percentage", and the length limit is pinned by a test, so this looks deliberate.

## Security

No high-severity finding. No way to post without an approved hash, no injection into the rendered page, no bypass of masking. SP-B2 above is the one approval gap, and a person still has to type it.

### Should fix

**SEC-S1. The UAT harness can reach the live Discord.** `tests/uat/seed.py:156-171`, `paths.py:60`.

- **Rules:** PRD §4, "Nothing here is run against the live system". Crew card, "Never run anything that … posts to Discord … outside a test double".
- **Cause:** `refusal()` checks the data, outputs, PRD and config folders, but not `JURA_GROWTH_ENV_FILE`, which defaults to `REPO_ROOT/.env`, and not `DISCORD_WEBHOOK_*` in the shell.
- **Failure:** run from the main checkout without that one export, every scenario's `sweep_safely` posts UAT cards to live #approvals. Feed lines follow to the live feeds. `app-prd` doesn't need `JURA_GROWTH_CONFIG_DIR`, so `post_buttons: true` applies, and that card's `growth:approve:A-0001` button would decide live A-0001, a different request. `uat.md:82` has the export, so this takes one missed line.
- **How I checked:** read the code. I didn't run it, since running it is what the finding warns about.
- **Age:** the gap predates this branch. `social-day`, `app-prd` and `decide` widen it.
- **Fix:** refuse unless `JURA_GROWTH_ENV_FILE` is set and outside the repo, and refuse any `DISCORD_WEBHOOK_*` in the environment. Do this before anyone runs the UAT.

### Checked, nothing to report

- **Render:** every `card.json` field is escaped. Icons are allow-listed at parse, before the only file read from a name. The vendored SVGs hold no script.
- **Own copy:** it relaxes only the "never show" values and the owner address, and secrets are redacted before the split.
- **Feed lines and the refusal note:** all go through `discord.post`, masked, mentioning nobody.
- **`NOT_NAMES`:** an address stays masked. "Ai Ling" now shows as `Ai [name removed]`, a fragment the crew-log accepts. No attack path.
- **Approval binding:** `on_approve` and `create_social` only add refusals.
- **Read paths:** `_requests`, `refusal` and `_recent_starts` are parameterised or static SELECTs with no writes (ADR 0002).

### Blocked paths

None changed. The diff has nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.

## UI

Reviewed `card.css`, `card.js`, `headline.html`, `list.html` and `tool.html` against the Web Interface Guidelines. These templates render to a PNG in headless Chrome, so the rules on interaction, focus, forms, motion, touch and hydration don't apply. `headline.html` has `lang`, one `h1`, `aria-hidden` on its decorative marks, and `text-wrap` on the headline and subtitle.

### Should fix (design system)

- **UI-S1. Mono captions are mixed case and run as reading text.** `card.css:257` (`.visual-caption`) and `:377` (`.figure-source`). `design-system/README.md:111` says mono is "Small and uppercase, never for reading". `.caption` at `:79-85` does it right. `reviews/samples/figure-1200x630.png` shows a two-line sentence set in mixed-case mono. Rerun the Chrome overflow matrix after the change, because uppercase runs wider.

### Notes

- `card.css:103` (`.site`) is mixed-case mono for the web address, and `:433` (`.panel .url`) likewise. Both predate this branch, and an address is a fair exception.
- `.items .num` at `:201` is numbers only, so case doesn't arise.

## Answers to the brief

### Ticket 02's round 2 fixes

| Fix | Status | Evidence |
|---|---|---|
| R2-B1, every masked word named | **Holds** | One post with a phone past character 120, "3000-4000", a learned name, a phone-shaped link and an address gave five reasons. Each quotes a masked window and says what to change, and none holds the value |
| R2-B2, a note on a refused card | **Holds** | Discord 500 at submit, then a `contacts` row and a sweep: one note in #social-drafts, one event after repeat sweeps, Instagram's card still posted |
| R2-B2, submit, digest, one-pager | **Holds** | Digest: "1 draft waiting in #approvals (instagram), 1 draft with no card (facebook)". One-pager: "A-0001 (social-post) has no card … lapses Tue 10 Nov, 17:00 SGT". Submit: `test_approvals_first.py:533`, `:543` |
| Typed approval of a refused card | **Fails** | SP-B2 |
| `NOT_NAMES` class fix | **Holds for what it names, and the class isn't closed** | `ai@`, `sales.singapore@` and `marketing.team@` teach nothing, and `ai.ling@` teaches only "ling". See below |

**Should fix before the ICP goes in: `NOT_NAMES` misses words a post can't easily avoid.** The scout stores any address that isn't an exact role as `named` (`contact.py:346`). Each of these then masks its word, with a real `contacts` row and a real read:

- `solutions@acme.sg` gives `Jura [name removed] helps.`
- `jura@acme.sg` gives `[name removed] Solutions helps.`
- `finance@`, `design@`, `digital@`, `manager@`, `purchasing@`, `asia@` and `facebook@` do the same to those words, capitalised.

It fails safe, and the reason tells the run to use another word, so nothing wrong goes out. Each such contact costs an attempt on every post that says the word, and two attempts lose the day. Add `jura`, `solutions` and the department words to `privacy.py:85-92`. I rank this should fix, as round 2 did the wider case.

### The two opens from ticket 04

**A missing config folder disables the buzzword check. Real, predates this branch, doesn't block, should fix separately.**

- In a fresh process with `JURA_GROWTH_CONFIG_DIR` pointing nowhere, `brand_check.check("Leverage our seamless synergy…")` passes on main and on this branch, and `jura-growth check` prints `pass`.
- The cause is `config.read_lines` returning `[]` for a missing file (`config.py:50-52`), read at `brand_check.py:255`.
- It doesn't block because `config/` is tracked in the repo, and every scheduled job dies first at `config.settings()` (`runner.py:61`) with `FileNotFoundError`. It reaches only hand-run `check` and `social render`, which is how ticket 04 met it, and a folder with `settings.yaml` but no `buzzwords.txt`, which I read from the code and didn't run.
- A gate that fails open is still wrong. Raise when `buzzwords.txt` is missing. `approved_phrases()` is already safe, since no claims means nothing passes.

**Expired drafts read "2 social drafts waiting". Real, blocks: SP-B1.**

### Seams across the tickets

**Would a normal outreach email or app PRD now fail? No.**

| Sample | Main | Branch |
|---|---|---|
| All 7 real PRDs in `prd/pending/apps/` and `prd/skipped/apps/`, through `factory.brand_parts` and the gate | pass | pass |
| `tests/uat/app-prd.md` | pass | pass |
| The reference email in `prompts/scout.md`, through `compose` with the designed frame | pass | pass |
| An email with a digit in a sentence without "we" ("lists 3 servicing packages and a 24-hour line") | pass | pass |
| An email with "since 1998, and we like that" | pass | **fail** |
| A community reply and post, normal wording | pass | pass |

- The one change is the conductor's ruling working as designed. It costs a rewrite, and `prompts/scout.md`, `community.md` and `app-factory.md` all warn the writer. A note for watching the first live days: the scout prompt says two emails failing in a row pause outreach, so this rule can now contribute to a pause.
- The frame's own footer and signature hold no digit.
- All seven approval kinds map to the channels FD1 names.
- **The moved digest and the drift check:** a digest still firing at 17:30 after merge, before `schedule install`, doesn't trip SC1 (`schedule_drift` returns `None` with one job off).

**Main's PRs: no conflict in intent.** Between the ticket merge and main, three files overlap, and I read each:

- `config/settings.yaml`: #15 turns on `dispatch_builds` and #16 sets the preview project. This branch only moves the digest.
- `docs/app-factory.md`: its dispatch wording now matches #15, and the feed line uses `answer_line`, which reads the switch.
- `prompts/app-factory.md`: #17's idea steps and this branch's digit rule sit side by side.

#17 adds no approval kind, and its PRDs go through the same gate. `test_apps_idea.py` passes here.

### Pyright: what is real

Run with this worktree's venv:

| Scope | Main | Branch |
|---|---|---|
| Touched source and `tests/uat/seed.py` | 19 | 21 (two more files in scope) |
| Whole package | 70 | 73 |

- **Real, new:** three errors, at `render.py:187`, `render.py:393` and `commands.py:184`. All have the same shape as the existing ones around them: pyright reads a dict as `dict[str, str]`. They are inference noise, and neither the suite nor the probes show any failure there. None is in `feed.py`, `cards.py`, `privacy.py`, `kinds.py` or `checks.py`. Round 2's "0 errors" was on a narrower file list.
- **Not real, the editor's noise:** with the project root at `repos/growth` and the main checkout's venv, as an IDE opened there would have it, pyright reports 89 errors. 37 are symbols it can't find, such as `no_fence`, `decide_by_on` and `own_copy_as_shown`, plus `Item` not assignable to `Item`. It is resolving `jura_growth` to the main checkout, which doesn't have this code yet. They go away when the worktree is its own root.

### Docs

- **Nothing tells Ting Yu to post by hand in browser mode.** The remaining "by hand" text is `draft` mode (`submit.py:386`, `:408`, behind `rules.browser`), the `social published` command for that mode, `config/social.yaml:123` describing `draft`, and `docs/community.md`, which the PRD leaves out.
- **`docs/social.md` describes what ships,** apart from the wrong digest wording at `:467-470` (SP-B1) and the claim at `:325` (SP-B2).
- **`README.md`:** the schedule is right. The plug-in table is behind (ST-S1).
- **`CONTEXT.md`:** the new terms and the posting window are right. The health strip is behind (SP-S2).
- **No "17:30" is left** in the docs, config, prompts or code.

## Evidence

- Full suite, Python 3.14 (this worktree's venv), stand-in `claude` first on PATH, temp data folders: **5167 passed, none skipped, none failed, in 341s**. No intermittent failure showed up in this review's runs.
- Full suite, Python 3.12 (the main checkout's interpreter, which the live jobs use): 5160 passed, 7 failed. All 7 are `test_isolation.py` and `test_network_guard.py`, caused by my `-p conftest` flag loading the guard twice. Without the flag, those two files give **29 passed** on 3.12 and on 3.14.
- `pyright 1.1.414`: figures above.
- Probes in the session scratchpad on temp data and the Discord double: the digest at 18:05, the refused card across channels, `remote approve` through to a claim, masking per address, a missing config folder on both trees, the gate samples on both trees, drift after the digest moved.
- Live folders: I wrote nothing there. Files in `data/growth` changed during this review. The last entries are `remote.command` events at 23:23 and 23:27, and the one-pager at 23:00, which came from the live jobs and Dispatch, not from these runs.
- **Not checked:** how Discord really renders any of this, how real Facebook and Instagram read back (U12, U13), and the web-font render matrix (X9, left open for QA). A real SSH process wasn't used for SP-B2: `reset_caches()` stands in for it, and a grep of every `learn` caller supports that nothing learns first.
- **Sub-reviews:** the Standards, Spec and security passes ran as separate read-only agents. I reproduced the digest, carousel, numbers and masking findings. I confirmed ST-S1, SP-S2 and UI-S1 by grep or by reading the file, and SEC-S1 by reading `refusal()`. ST-S2 and the security pass's "checked, nothing to report" list rest on those agents' reads.
