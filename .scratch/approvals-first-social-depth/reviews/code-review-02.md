# Code review 02: approvals first, feeds after

Reviewed `crew/approvals-first-social-depth-02-approvals-first-and-feeds` at `ff03e5d` against its merge-base with `crew/approvals-first-social-depth` (`2c9e18d`), which includes `bb47345`. That is 10 commits and 48 files. The PRD, `reviews/functional.md` §3, `reviews/technical.md` and `reviews/test-strategy.md` are the spec.

## Verdict: changes-requested

Three findings block, and all three concern the same promise: what Ting Yu reads on the card must be what goes out.

- A post can hold text the card hides, and he is asked to approve it anyway (SP-B1).
- A post or a headline can break out of the card's code fence (SEC-B1).
- `discord.split` can drop a line of text from the card (SEC-B2).

The approval binding itself holds. Nothing in this branch lets anything post without a human approval of its exact hash. The rest of the ticket is sound, and these fixes are small.

## Standards

No blocking findings.

### Should fix

- **ST-S1. Three comments still give the old deadline or read wrongly.** `caps.py:54-55` and `config/publish.yaml:7` say a post's decide-by is the end of the window, which contradicts `CONTEXT.md:208` (Posting window). `config/social.yaml:126` reads as "posts it by 17:00", though posting runs to 18:00. Neither `caps.py` nor `config/publish.yaml` is in the diff. Exit criterion X6 expects no diff on `caps.py`, so a comment fix there needs a line in the QA report.
- **ST-S2. Reuse: the digest's query repeats what `items` already names.** `social/__init__.py:96-97` hardcodes `'publish_item:'`, `'social_post'` and `'social-post'`. These duplicate `items.subject_of`, `items.SOCIAL_ITEM` and `items.SOCIAL_KIND`. The status repeats `approvals.PENDING`.
- **ST-S3. Reuse: the release line hardcodes its channel.** `apps/releases.py:389` writes `"app-factory"`, which duplicates `RUN_UPDATE_DISCORD_CHANNEL` in `apps/__init__.py:116`.

### Nits

- Glossary drift: bare "card" in `docs/social.md:318,329,331` and `items.py:10`, a rule this diff adds to `CONTEXT.md`; "used" for a claim at `approvals.py:41`; "expiry" alone at `feed.py:22`.
- `limits.py:19`: `DECIDE_BEFORE_CLOSE` assumes the 20-minute gap, which config may lengthen (`caps.py:53`). A note beside it would do.
- `social/__init__.py:91`: an inner `from jura_growth import db`.

### Judgement calls (labelled smells)

- Possible Duplicated Code: `cards.py:220` `_own_copy`, `cards.py:100` `_superseded_note` and `feed.py:46` `_next_step` share one hook, try and log shape. `kinds.py:232` re-reads the row that `preview` reads.
- Possible Feature Envy: `social/__init__.py:88` `_where_they_wait` joins publish's tables and belongs in `publish.items`.
- Possible Speculative Generality: `feed.py:48-50` `callable(step)`. Only `outreach/approval.py:84` is still a string, so it could be a method too.
- Possible Primitive Obsession: `feed.py:80` compares `close_reason`, a display string, to a constant. Technical B1 asked for this constant, so I'd leave it.
- Possible Mysterious Name: `discord.py:409` `allowed` holds a timeout, `discord.py:421` local `wait` shadows the meaning of `post`'s `wait`, and `kinds.py:139` `decide_closes` isn't the glossary's "decide-by".
- Possible Data Clumps: `silent` and `patience` travel through `post`, `_send` and `_deliver`; `submit.py:309` `_log_rows` gained a twelfth positional for one field.
- Possible Divergent Change: `items.py:395` `unless_paused` puts feed wording in the item module.

Clean: commit voice, the core imports no agent by name, and pyright reports no new errors on the touched files (6 at base, 6 at head, from the standards reviewer's run).

## Spec

### Blocking

**SP-B1. He approves a post he can't fully read.** `agents/publish/kinds.py:199-200`.

- **Rules broken:** PRD §4, "Nothing goes out without an approval of that exact content". AF1, "holding the exact text". `reviews/test-strategy.md` R5, "What Ting Yu approves is what posts: planted phone number … card shows them in full". ADR 0003 refuses normalisation because it "would let a yes cover bytes Ting Yu never saw", and this is the same case.
- **Why the note isn't enough:** `privacy.for_discord` masks phones, named addresses and learned names even in own copy, and MC §4.4 forbids showing them. So the developer was right that S9 can't be done by passing `own_copy`, and right not to weaken the mask. But the note only tells him something is hidden. It doesn't let him judge it, and the Approve button stays live. No crew-log entry rules on this.
- **Reproduced through the real code:**
  - A sourced `ai-news` Facebook post holding `Call 8123 4567 today.` **passes** the brand gate, because a phone is only a figure and any third-party source clears the numbers rule. The card shows `Call [phone removed] today.` and then posts the real number on a public Page. The same goes for `jane.tan@example.com`, shown as `j***@example.com`.
  - A web page steering the run is the threat here: the run reads the web, and a phone number is exactly what a scam would plant.
  - Learned names hit ordinary words. With `mark.lee@` and `grant.ong@` known from leads, the card reads `[name removed] your calendar. A new [name removed] helps.`
  - A link with an eight-digit id reads `https://www.straitstimes.com/tech/story-[phone removed]`, in the post and on the "Links in the text" line. `privacy.py`'s docstring lists public source URLs as allowed, so this one is also a masking bug.
- **Fix I recommend, as a decision for the conductor:** what the card can't show can't be approved, the same rule as "no images means no approval card". In `social/checks.py`, make it a brand-gate failure when `privacy.for_discord(text, own_copy=[text]) != text`. The regeneration can then fix it, and a second failure drops the variant. Remove the note, and rewrite `test_what_the_card_masks_it_says_it_masks` (`tests/test_approvals_first.py:125`) to assert no card. Stop masking phones inside URLs, or accept that such a link is refused. If the conductor keeps the note instead, record that in `crew-log.md`, amend R5, and refuse phones and addresses at the gate at the very least.
- **Correction to S9's premise:** titled names ("Ms Tan") are not masked by `for_discord`. `titled_names` is used only in `strip_personal`. So the masked names are learned ones only.

### Should fix

- **SP-S1. A replacement raised after 17:00 can be approved with no slot left, and the line promises a post.** `agents/publish/kinds.py:230`, `:171`.
  - **Rules:** PRD amendment, "so an approval always has a publish slot left". R6, "no line says 'it goes out' when no slot is left".
  - **Reproduced:** approved at 16:59, content changed, claim at 17:20. The claim is refused, and A-0002 is raised with decide-by 18:00. Approved at 17:45, the feed says "It goes out on a publish run today, by 18:00 SGT". No run is left, and at 18:05 it reads "Approved but not used in time."
  - **Is 18:00 right?** The carve-out is needed, because `_insert` raises on a past decide-by and that would fail the run with an approved post in its hands (`approvals.py:382`). The value is wrong for approvals made after the last slot starts at 17:40. Make the line true: when no slot remains it should say this lapses at 18:00, or the card's decide-by should come earlier while a slot remains.
  - **Can it be abused?** No, see "Answers to the brief".
  - **Coverage and docs:** `test_a_post_that_changes_after_the_decide_by…` (`tests/test_approvals_first.py:217`) doesn't pin the new decide-by. The exception is missing from `CONTEXT.md:208` and `docs/social.md:329`.
- **SP-S2. Facebook is the one section that doesn't say what to write as the live text.** `prompts/publish.md:83`, `:104`.
  - **Rule:** technical B3, "A long post that went out correctly pauses publishing".
  - **Failure:** step 8 says to write the text "as it reads on the page", and `text.same` is exact after whitespace. Instagram (`:137`), LinkedIn (`:175`) and groups (`:215`) each add "write only" the post's text, and Facebook doesn't. I confirmed that `same("Our post text.", "Jura Solutions\n2h\nOur post text.\nLike\nComment\nShare")` is false, and a mismatch pauses `publish` for every item, so an approved Instagram post would lapse that day. I can't run a model here, so how often this happens is unproved. Facebook is expected to post first, and the fix is one sentence: "For the live text, write only the post's text: not the Page's name, the time, reactions or comments." Add a prompt test beside `test_every_long_post_platform…`.
- **SP-S3. Test coverage the strategy names is missing.** None of these has a behaviour failure behind it, since the code path is generic.
  - R1, "hands out nothing while the request is pending, skipped, expired, superseded or paused" on shipped config: `tests/test_approvals_first.py:460` covers pending and skipped only.
  - FD3, "Parametrised over `app-build` **and** `group-rules`", and FD1's seven kinds: real kinds are tested for channel only, with no line test for the three community kinds.
  - R4, "`edit-fails`: one follow-up in #approvals and still one feed line", and "Two sweeps under the lock give one line": neither is in `tests/test_feed.py:216`.
  - Class B, "The twin asserts the slides on the Instagram card, in order": the Monday twin checks sources only (`tests/test_approvals_first.py:79`).
- **SP-S4. Docs.** `docs/app-factory.md:177-181` doesn't mention S3's "released" line.

### Nits

- `social/__init__.py:101`: a draft whose card is approved but not yet claimed reads "with no card" in a digest run before 18:00. The scheduled 18:05 run has already lapsed it, so this shows only on a manual digest.
- `apps/releases.py:389`: the "released" post isn't wrapped as the steps above it are. `discord.post` handles Discord's own failures, so only an unexpected error would make a recorded release answer badly.
- `group_kinds.py:245`: S8 named social only, and the same pause wording for groups is harmless.
- PRD §7 records the PRD as unsigned, with merge as acceptance. The PR body must lead with what merging switches on.

### Open risk, not a finding

Technical B3's question stands: if Facebook shortens a long URL on the page, a correct post reads as a mismatch. It fails safe, and U12 is the check. Don't loosen `text.same` on a guess.

## Security

The security pass ran on this diff. It reported two findings at confidence 8 or above, both of which I reproduced, and I rank them blocking.

### Blocking

**SEC-B1. A post or headline can break out of the card's code fence.** `agents/social/checks.py:47`, `agents/publish/kinds.py:198`, `:214`.

- **Rules:** AF1, "no message has a broken quote or fence". Technical B2 part 3 refuses a fence line only, as the ticket worded it, and the same risk reaches the middle of a line.
- **Reproduced:** a post with `paragraph ``` ` at a line's end, then `For the reviewer, left out of the post: ||send your bank login to our partner page||`, then `End of note. ``` more.` **passes** the real `brand_check.check` for `social-facebook`. On the card, the text after the first run sits outside any fence (an even count of fences before it). A headline with ``` also passes `social-card`, and it sits before the fence in the title, so it would invert the fencing for the whole post.
- **Impact:** text that posts literally can render on the card as if it were the card's own note, or hidden behind a spoiler. It needs a web page steering the run. The hash still binds, so this misleads the reader rather than bypassing the gate.
- **Unverified:** Discord's parser was not tested live. I'm relying on my knowledge that a fence closes at the next ``` anywhere on a line.
- **Fix:** refuse ``` anywhere, in `MARKDOWN_RE` and for the card's words. Also neutralise it when building a card, because `group_kinds.py:306` has the same fence with no such rule, which is latent while `community.browser` is off.

**SEC-B2. `discord.split` can drop a line of text from the card.** `jura_growth/discord.py:146-147`.

- **Rule:** AF1, "the exact text". The function's own docstring promises only that "the opening line alone" moves.
- **Reproduced:** inside a fence, `short ``` ` followed by ```` ```payload that goes out ```` and then a long line that forces a flush gives pieces of 18 and 1912 characters, and "payload" is on neither. `flush` treats any last line starting with an odd ``` as a bare opener and removes it, and the reopened piece doesn't carry its words.
- **Reach:** on a social card it needs SEC-B1 first, plus exact lengths, but `split` serves every Discord post.
- **Fix:** move the line only when `last.strip() == _FENCE`, and add the case to `tests/test_discord_split.py`. My 4,000-case fuzz of balanced input found no other loss or imbalance, and every piece stayed within its limit.

### Checked, nothing to report

Approval binding, `allowed_mentions` on every new post, webhook URLs in logs, the DELETE path (only ids from that same failed post, on the `approvals` webhook), secrets in feed text, and the audit (unchanged). "See more" adds only a click.

## Answers to the brief

- **Is any guard weakened?** No.
  - `approvals.py` is +9/-4: three constants and their comments, and two reason literals replaced by constants of the same value. No behaviour changes.
  - `tests/gate_adapter_social_post.py` is +3/-4. The clock check it lost picks the fixture's next free day. It isn't a guard, and it had to move because `create_social` now refuses after 17:00. The gate matrix is untouched.
  - X6 fails as written on both files, so QA must list them.
- **Can a replacement be abused into a post nobody approved?** No. It is a new pending record with its own hash, and only `decide()` over SSH can approve it. `use_by` stays 18:00, and `create_social` and `items.sync` keep their 17:00 guards (`items.py:163`, `:467`). A tap on a pending card after 17:00 lapses first, in `_refresh`. A skip tapped on an approved card whose content changed raises the replacement and records no skip, as it did before this branch.
- **The first live day.** Walked through tests and my own probes, on the Discord double and the fake binary.
  - The 07:00 submit raises two cards, sweeps, and leaves #social-drafts empty.
  - Approve gives one line, the next slot claims it, and the audit passes.
  - A long post typed in one go and a "See more" click both pass the audit. A click only moves the focus field.
  - A five-slide carousel with a long caption: five files on the first piece, beside the buttons, five copies handed out, and no audit failures or warnings.
  - The remaining risks to the read-back are SP-S2 and the URL question above. Real Facebook and Instagram remain U12 and U13.
- **Feed lines.** All seven kinds map to the right channel in an exact table over the real kinds. One line per change, none on changed content with or without a successor, masked (`assert_clean`), silent (flag `1 << 12`), and at most five seconds a line (the test asserts the request's timeout), with a feed answering 500, 429 or unreachable holding up neither sweep nor decision. Sweeps run at submit, at each decision, on each publish precheck, at the 08:00, 12:00, 18:05 and 23:30 upkeeps. At 18:05 an unanswered card and an approved, unclaimed one each close with their own line. Between 17:00 and 18:05 an unanswered card keeps live buttons, and a tap answers `expired`, as the PRD accepts.
- **The card on Discord.**
  - Fences balance across pieces for balanced input. Images and buttons sit on the first piece.
  - An edit can't cut a fence: the first piece keeps 120 characters free, and by my count the longest status line grows by about 50.
  - N7: a later piece failing deletes the earlier ones, and the next sweep posts the card whole, so no second set of live buttons appears.
  - The exception is a DELETE that also fails. The orphan then keeps live buttons, a press on it decides the same request correctly, and `discord.delete_failed` is logged. That is the noise technical N7 accepted.
- **Masked card.** See SP-B1.
- **Asked to post by hand?** No. Hand-post text exists only in `submit._post`, behind `rules.browser` (`submit.py:355`, `:366`, `:388`). A repo-wide grep found no other ask to post by hand. The test scans every message of a submit, on content only.
- **The flip.** `ff03e5d` is the tip. It changes only `publish_mode` and `page_url` for two platforms in `config/social.yaml`, plus tests, with no code. The ticket names one test. The two added shipped-config tests come from R1, so I accept them.
- **Blocked paths.** None changed. No UI files are in this diff, so no web design review applies. Loosening checks X5: no `skip` or `xfail` added, and no lowered rule.

## Evidence

- Full suite, `uv run pytest -rs -p no:cacheprovider -o addopts=""` with the worktree exports: 4768 passed, none skipped, none failed, in 444s.

- Targeted run: `tests/test_approval_gates.py`, `test_feed.py`, `test_approvals_first.py`, `test_publish_items.py`, `test_digest_closes_the_day.py`, `test_discord_split.py` gave 350 passed.
- Probes in the session scratchpad, on temp data folders and the Discord double: the split fuzz (4,000 cases passed), the gate on phones, addresses and fences, the masking output, the replacement flow, the split's lost line, a five-slide carousel from card to audit, and the read-back comparison. Nothing touched Discord, Chrome, launchd, a model or the live `data/growth`.
- Not checked: how Discord really renders any of this, how the live pages read back, and how the suite behaves at different times of day (`tests/conftest.py` clears `JURA_GROWTH_NOW`, so a pinned run proves nothing).

---

# Round 2

Reviewed `1a98b87` and the rewritten flip `9687ee0` at the branch tip. The conductor's ruling stands as taken: anything the masking layer changes fails the gate, and the card note is gone. I judged the fix against that ruling and didn't reopen it.

## Verdict: changes-requested

Two findings block. Both are small, and neither lets anything post unapproved. Every round 1 finding is fixed.

- The gate's reason often can't show the run what to rewrite, so a fixable post loses its platform's day (R2-B1).
- A card the sweep refuses leaves a pending request that nobody is told about, and three messages say otherwise (R2-B2).

## Round 1 findings

| Finding | Status | How I checked |
|---|---|---|
| SP-B1 masked card | Fixed | A phone, a named address and a phone-shaped link now fail the gate on a post and on the picture's words. The note is gone. The gate also learns names from the database through `privacy.learn(None)`: a `contacts` row refused "Mark your calendar" |
| SEC-B1 fence escape | Fixed | ``` anywhere fails `MARKDOWN_RE` (`checks.py:47`), for a post and a headline. `discord.no_fence` covers the title, the reason, the community post and the email draft |
| SEC-B2 lost line | Fixed | My round 1 payload stays on a piece (pieces 47 and 1912). The 4,000-case fuzz passes, and `discord.py:152` now moves only a bare fence |
| SP-S1 late replacement | Fixed | `kinds.py:171-178`: approved from 17:40, the line says it lapses at 18:00. Tests pin the decide-by and the words at 17:39, 17:40 and 17:45. Docs carry the exception |
| SP-S2 Facebook read-back | Fixed | `prompts/publish.md:104`, with a test over all four post sections |
| SP-S3 test gaps | Fixed | `tests/test_feed_real_kinds.py` runs each real kind through its own adapter. Also covered: all five non-approved states on shipped config, `edit-fails`, the held lock, and the Monday slides |
| SP-S4 docs | Fixed | `docs/app-factory.md:181` |
| ST-S1, S2, S3 | Fixed | Comments updated. `items.platforms_on_a_card` replaces the digest's literals. `releases.py` uses `RUN_UPDATE_DISCORD_CHANNEL` |

**`caps.py`:** comment only. The diff has no changed line that isn't a comment, so no limit moved. X6 lists this file, so QA records it.

**The flip:** `9687ee0` is the tip. Against `1a98b87` it changes only `publish_mode` and `page_url` for two platforms, plus tests, with no code.

## Blocking

**R2-B1. The gate's reason can't always show what to rewrite.** `agents/social/checks.py:233-236`.

- **Rule:** the ruling relies on the regeneration to recover a post. `prompts/social.md:271` tells the run to "Fix every reason listed, in every file, in one pass", and the second submission is final.
- **Failure 1, the excerpt stops at 120 characters of the line.** A deep post's paragraphs run longer than that. I reproduced this with a phone, with "3000-4000 employees", with a phone-shaped link and with a learned name, each past character 120. All four give the same reason, quoting only the paragraph's opening words, with no `[phone removed]` or `[name removed]` in it. The run can't find a learned name by looking, since it doesn't know the leads, and a link or a range doesn't look like the "phone" the reason names.
- **Failure 2, only the first masked line is reported.** `Call 8123 4567 today.` with `Firms with 3000-4000 employees.` two paragraphs later reports only the first. Fixing what it was told, the run then fails its final attempt and the platform is dropped.
- **Fix:** one reason per masked place, each quoting a short window around the marker, never the value. Name the link case in the words, since "a phone" misleads there. Add a test with the mask past character 120 and a test with two masked lines. A line in `prompts/social.md` would also save regenerations on what the run can see for itself: no phone numbers, no digit ranges written as `3000-4000`, and no source link with a long digit run.

**R2-B2. A refused card leaves a request that nobody hears about.** `cards.py:151-154`, `:204`, `agents/publish/kinds.py:235`.

- **Rule:** PRD AF3, "A platform in `browser` mode that can't get a card gets a note saying why". Test strategy §7 makes a failed §2 criterion a major defect, and X12 allows none open.
- **Answer to the brief's question: yes, he hears nothing true.** I reproduced it. Discord answers 500 during `social submit`, a lead then teaches a word in the post, and the next sweep runs. The Instagram card posts. For Facebook:
  - Discord receives nothing, in any channel. Only a warning event is written, again at every sweep.
  - The submit's own lines said "Approval requested: facebook as A-0001 in #approvals".
  - The digest says "2 drafts waiting in #approvals".
  - The one-pager, if it runs while the request is pending, says "The heartbeat posts it" (`health.py:180`). It never will. If the request was raised after 08:00, it lapses before the next one-pager.
  - The lapse gets no feed line, since there is no card row.
- **How often:** rarely. The gate and the first sweep are seconds apart, so it needs a failed first post or a row changed past the gate. Nothing unapproved goes out.
- **A second gap:** the request stays pending, so a typed `/growth approve A-nnnn` can still approve it with no card. That is the one remaining way to approve words he hasn't read. `decide()` has no card check, by design, and it stays that way.
- **Fix:** on a `card_problem` refusal, send one note, once per request, to #alerts or the feed, naming the A-id and the reason, and make the one-pager's line true for it. Have the kind refuse the typed approval too: `on_approve` runs inside the decision and a `BadArgs` from it rolls back, so this stays inside the kind and leaves `approvals` alone. Add a test that reads every channel.

## Can text still differ between the card and the post?

On a card that posts, no.

- The post's text is shown whole in own copy, and `card_problem` refuses it when anything would change. It runs after `load_for_masking`, so it sees at least what the gate saw.
- `no_fence` adds only invisible characters, and only to a row that got past the gate.
- A card's edit keeps the first piece as it was sent.
- What can still read differently is outside the post's text: a source URL on the `Sources:` line isn't gated, so an Instagram card can show a masked source link. That is a nit, since Instagram's caption holds no link.
- A community post's card has no `card_problem`, so it can still mask. This is latent while `community.browser` is off, and the PRD leaves that out of scope. Take it up before switching it on.

## Are the reported costs acceptable?

**The news-source link: not common enough to lose posts often.** I accept it.

- Of 34 URL shapes I wrote from memory of common news, research and vendor sites, three mask: BBC's older `technology-68123456`, a PubMed id starting 3, and an FT address I built with an all-digit first group. Reuters, CNBC, Bloomberg, The Verge, TechCrunch, CNA, The Straits Times, SCMP, arXiv and the rest pass. Seven digits, nine digits and a date in the path don't match. This is a sample by hand, not a measurement.
- The live record, read with `mode=ro` and counts only: 13 posts, 3 source URLs, none masked.
- It costs Facebook only, since Instagram's caption holds no link. The run can choose another source if the reason tells it which link, which is R2-B1.

**"3000-4000 employees" and press@openai.com:** accepted, and easy to rewrite once the reason shows them. "3,000-4,000" and "3000 to 4000" pass.

**"Mark Zuckerberg" and "Mark your calendar":** accepted as recorded. The live database holds no named addresses today, so this costs nothing until scout has its ICP.

**A larger cost than the ones reported, should fix before the ICP goes in.** `scout/contact.py:346` calls any address that isn't an exact role "named". So `sales.singapore@` teaches "Singapore", `marketing.team@` teaches "Team" and "Marketing", and `ai.ling@` or `ai@` teaches "AI". I confirmed `AI tools help` shows as `[name removed] tools help` after one such address. Most of these can be rewritten, but a news post about AI can't avoid "AI". One such contact would drop both platforms on the attempts that say it, every day, until someone removes it. #alerts would say so, so he hears it, and nothing wrong goes out, which is why this doesn't block. The cheap fix is to add the words a Jura post can't avoid to `privacy.NOT_NAMES` (`privacy.py:81`), starting with `ai`, and to read the scout's role list against `sales.singapore`-style addresses.

## Nits

- `kinds.py:171-178`: approved in the seconds after 17:40, a run that has already started may still claim it, so "No publish run is left" can occasionally be wrong in the safe direction.
- The `approval.card_refused` event repeats at every sweep. R2-B2's fix can make it once.

## Evidence

- Full suite, `uv run pytest -rs -p no:cacheprovider -o addopts=""` with the worktree exports: 4834 passed, none skipped, none failed, in 448s.
- `pyright` on the touched source files: 0 errors.
- Probes in the session scratchpad on temp data and the Discord double: the failure reason at each position, the refused card across every channel, the gate learning from a `contacts` row, the split fuzz and payload, and URL shapes.
- One read of the live `growth.db` with `mode=ro`, printing counts only. Nothing was written, and no name or value was recorded.
- Not checked: Discord's real rendering, and how a real run responds to a reason. That a clearer reason gets fixed on the regeneration is my judgement, not something I ran.
