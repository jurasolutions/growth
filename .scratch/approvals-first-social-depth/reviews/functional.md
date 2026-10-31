# Functional review: approvals first, feeds after, social depth

*Functional lead, 2026-10-31. Reviewed `jurasolutions/prd/pending/prd-jura-approvals-first-social-depth-2026-10-31.md`, cited as `PRD:<line>`, against the draft at `a6c2cca` on `crew/approvals-first-social-depth`. Code paths are relative to the worktree.*

*How this was checked: by reading the PRD, docs, config, prompts and code. This session had no shell, so nothing was run. Every "the code does X" below comes from reading the cited line, and character counts are marked as estimates. The draft has 41 failing tests (crew-log), and some gaps below may be planned for the tickets. I report them anyway, because the tickets don't exist yet.*

*Following Ting Yu's standing instruction, this review asks him nothing. Each finding carries the decision I recommend, ready for the conductor to take.*

## Verdict

The PRD answers what Ting Yu asked for, and the core of it is sound: asks go to #approvals, outcomes go to the feeds, and approval stays bound to the exact content. It isn't ready to build as written. There are **6 blocking findings**, 14 should-fix findings and 9 notes. Of the 18 acceptance criteria, 6 are testable as written and 12 are reworded in section 3.

The three surprises Ting Yu would hit soonest:

1. A deep news post doesn't fit in one Discord message, so its card breaks in two (B1).
2. An approval tapped late in the afternoon is told it will post, then never does (B2).
3. An unanswered card looks open until 23:30 (B3).

## 1. Findings

### Blocking

**B1. A deep post breaks its own card.** `PRD:33`, `PRD:48`.
- A card is cut at 2,000 characters on line boundaries (`discord.py:125`, `:208`). The post sits inside a code fence (`publish/kinds.py:180`), and each URL appears twice: once in the text and once on the "Links in the text" line (`:182`).
- My estimate: a Facebook post with two or three sources passes the limit at about 190 to 220 words, so most of the new 160 to 280 range splits.
- When it splits, the fence is cut, so the second half renders wrongly. Buttons go on the first piece and images on the last (`discord.py:214-215`), so he sees the picture at the bottom and has to scroll up to approve.
- **Decision.** Quote the post with `> ` on each line, as outreach does (`outreach/approval.py:116`). Drop the "Links in the text" line and keep only the sources that aren't in the text. On a split card, send the images with the first piece, beside the buttons and the status line, so the second piece holds only the rest of the text.

**B2. An approval after about 17:20 can be told it will post, and then not post.** `PRD:34`, `publish/kinds.py:157`, `:205`.
- The last publish slot is 17:40 (`config/settings.yaml:139`). A claim needs 20 minutes since the previous claiming run's start (`publish/claim.py:125`), so a few seconds of start-time jitter can push a second platform back a slot.
- The card says "decide by 18:00", and the feed line says "It goes out on the next publish run, by 18:00 SGT".
  - Approved at 17:45: no run is left. It lapses as "approved but not used in time".
  - Both approved at 17:25: Facebook can go at 17:40, and Instagram can't.
- **Decision.** The `social-post` decide-by becomes **17:00 SGT**, which leaves slots at 17:00, 17:20 and 17:40. The use-by stays 18:00, so an approved item can still post until then. `items.create_social` (`items.py:163`) and AF4's precheck must test against the decide-by, because `approvals._insert` raises on a decide-by already passed (`approvals.py:377`). This changes a deadline value, not how an approval is decided or bound, so `PRD:71` still holds. It amends BP's deadline and the Posting window entry in `CONTEXT.md`.

**B3. Nothing happens at the deadline.** `PRD:41`.
- `expire_due()` runs only from the one-pager (08:00), the heartbeat (12:00) and the backup (23:30) (`cli.py:211`, `:386`, `:411`). The publish precheck doesn't call it (`publish/job.py:43-45`).
- So an unanswered social card keeps showing "decide by" and live buttons until 23:30. The expired feed line posts at 23:30.
- The 17:30 digest runs before any social item can expire. It reads "2 drafts waiting in #approvals", and its "expired" count for that day is always 0 (`publish/__init__.py:66`).
- **Decision.** Move the `digest` job to **18:05** and have it run the approval upkeep first. That one change fixes the card, the feed line and the count. It needs `jura-growth schedule install` after merge, which goes in `PRD:94`.

**B4. The social prompt contradicts the new rules.** `PRD:48-51`, `PRD:66`.
- `prompts/social.md` still says:
  - "Ting Yu copies it from #social-drafts" (`:5`);
  - Facebook 60–120, aim about 90 (`:97`), and Instagram 50–120 (`:98`);
  - "One or two sources" for `ai-news` (`:39`);
  - carousels on Mondays and Thursdays only (`:131-133`).
- It has no `visual`, no `icon` and none of DP4's insight asks. A run that follows it fails the word gate on every news day, and a second failure means "No draft today".
- `docs/social.md` is stale too (`:4`, `:34`, `:97-99`, `:153`, `:250-251`). `:251` still says a platform without `page_url` is "posted by hand".
- **Decision.** Rewrite the prompt and docs in ticket 1, not at the end, and add a test that the prompt's stated ranges match `config/social.yaml`.

**B5. A post can still reach a card with no picture, and Instagram can't post without one.** `PRD:11`, `PRD:33`, `PRD:56`.
- If the card's words fail the final gate, or rendering fails, the variants still go on with no images (`social/submit.py:219-223`). This gets more likely now that the picture adds words to the brand check. `read_social` accepts an empty image list (`publish/kinds.py:72`), and the card just says "No image."
- For Facebook, that is the dull post he rejected. For Instagram, nothing refuses the item before a run, and Instagram needs media. A run can only stop, and a stop pauses publishing for every item, including an approved Facebook post.
- **Decision.** No images means no card on either platform. The AF3 note says why, and #alerts already gets the render failure. `from-the-toolbox` follows the same rule.

**B6. The Discord flow can't be rehearsed with today's harness, so the only proof would be live posts.** `PRD:80`, `PRD:86-92`, `PRD:101`.
- `tests/uat/seed.py` has no way to make a pending two-platform day through real `social submit`, and no way to skip a request without the Dispatch UAT key.
- Its fixture items carry one image (`seed.py:505-527`), while under DP3 nearly every Instagram post is now a carousel.
- The `new-app-prd` scenario in `uat.md` was never added (`seed.py:689-702`).
- The seed refuses weekends for every scenario (`seed.py:722`), and social runs daily. Today is a Saturday.
- It copies `post_buttons: true` into the UAT config, but a plain webhook can't carry buttons (`discord.py:166-168`).
- **Decision.** Add the seven harness items H1 to H7 listed in `uat.md` to ticket 2. They are test code only.

### Should fix (non-blocking)

| # | Finding | Where | Decision |
|---|---|---|---|
| S1 | A picture's figure isn't tied to its source. `source` is a free label, and the numbers rule passes any figure once the post has any third-party source (`brand_check.py:522`, `:551`). A big "62%" with "Source: Gartner" passes on a tip whose only source is unrelated. | `PRD:56`, `PRD:79`, `visuals.py:159` | `visual.source` must match the publisher on a `sources.md` line, or `submit` refuses without using the regeneration |
| S2 | App build feed line hides the handwork. "The build handoff is written" reads as done. With `dispatch_builds: false`, nothing builds until he opens Claude Code. Only the Dispatch reply and the one-pager say so. | `apps/builds.py:85`, `:221`; `PRD:73` | The feed line carries the same "Build it: …" text as the answer, while the switch is off |
| S3 | `app-release` goes quiet after approval. There's no next step, the claim is silent, and `apps released` posts nothing, so FD2's "the action reports itself" is untrue for this kind. | `PRD:42`; no `discord.post` in `agents/apps/` | Add `feed_approved` naming `/growth apps release-plan APP-NNN`, and post one "released" line to #app-factory |
| S4 | A false "withdrawn" line. `expire_due()` supersedes on changed content without raising a new request, so at that sweep there's no successor and the feed says "withdrawn". A new card can follow later. This breaks FD2. | `approvals.py:560-565`, `feed.py:42-45`, `items.py:436` | Post "withdrawn" only for "the item is gone". Stay silent on "the content changed" |
| S5 | The feed's reason differs from the card's. The card says "lead unsubscribed", while the feed says "The request closed: the item is gone." | `feed.py:45`, `cards.py:92` | Pass the card's own note to the feed |
| S6 | The social feed line doesn't say which post. It names the page, day and `P-nnnn`, not the story. | `publish/kinds.py:192`, `PRD:41` | Add the card's headline to the title, which isn't hashed, so nothing supersedes |
| S7 | The outreach feed line is wrong after hours: "inside today's window" for an approval at 20:00 or on a Friday night. | `outreach/approval.py:84` | "It goes out on a send run, inside the send window and the day's caps." |
| S8 | An approval while publishing is paused still promises a post. | `publish/kinds.py:157`, `PRD:34` | When `publish` is paused, the line adds "Publishing is paused, so nothing goes out until you resume it." |
| S9 | The card can mask the text he approves. Cards pass no `own_copy` (`cards.py:192`), while the old draft post did (`submit.py:369`). A phone number or titled name shows masked on the card and posts in full. | `PRD:33` | Pass the post text as `own_copy` for `social-post` |
| S10 | The post-merge list is short. `PRD:94` omits `uv sync` (crew card), `schedule install` (B3), logging in after the restart (LaunchAgents and Chrome need the session), and the Claude in Chrome connection. | `PRD:94` | Use the list in `uat.md` Part L |
| S11 | Merge-day drafts. A draft already written that day gets no item (`items.py:10`), but the digest says it's "waiting in #approvals" (`social/__init__.py:54`). No card exists. | `PRD:66` | Say "no card" for a draft with no item. Merge after 18:05 if possible |
| S12 | DP2 only counts. Two pages on one host pass, though the PRD wants an announcement and an independent report (`drafts.py:139`). | `PRD:49` | Require two different hosts. Independence stays a prompt rule and his eye on the card |
| S13 | SC1 states a cause as fact. The line says launchd "keeps the time zone it started with", while `PRD:26` says "not proved". | `health.py:206-208` | "Most likely launchd kept an old time zone. Restart the Mac once. If it's still off tomorrow, run `jura-growth schedule install`." |
| S14 | Picture language in the PRD. PC1 says "headline card", but list themes also set `needs_visual`, and the code requires icons on them (`drafts.py:128`). | `PRD:56` | Use the PC1 rewording below |

### Notes

1. **Skip has no "try again".** A skip drops that platform for the day, and there's no edit or regenerate. Make it an explicit out-of-scope line. A skipped or expired story also stays used for 14 days (`docs/social.md:75`).
2. **Daily load.** Weekends stay on, so he has 2 social cards every day, plus an app card most days, plus up to 5 emails a day in warm-up, rising to 20. Keep Part E2 of the mission-control UAT as the check on whether that's livable.
3. **Approved looks like waiting.** The digest counts an approved, unposted item as a "draft waiting in #approvals" (`social/__init__.py:52`).
4. **A sweep lock can delay a line.** If a decision lands during another sweep, its line waits for the next one (`cards.py:157-159`). That's at most 20 minutes in the window, and up to the next upkeep outside it.
5. **A card that never posted gets no feed line.** This happens with no #approvals webhook (`cards.py:160`). The one-pager already lists unposted requests, so I rule it out rather than fix it.
6. **Five list items lose one slide.** The carousel is the cover plus 4 items (`render.py:186`, `config/social.yaml:164`), so a fifth item appears on the cover only.
7. **`jura-growth check --channel social-facebook` has no theme.** It uses the default range, so a good 200-word news post fails there and passes in `submit` (`checks.py:144`). The prompt already says not to run it separately.
8. **#social-drafts no longer holds drafts** in browser mode. Keep the name: renaming means new webhooks for no gain.
9. **Sign-off.** Ting Yu hasn't read this PRD (`PRD:108`), so the merge is the only real acceptance. The PR body should lead with what merging switches on: real posts through Chrome on both platforms, under Meta's terms risk (`PRD:82`).

## 2. One full day, flow by flow

### Social

| SGT | What happens | Where he'd be surprised or asked to act |
|---|---|---|
| Before merge | Jobs fire about 9 hours early | SC1 tells him. Restart is by hand, then log in and open Chrome (S10) |
| 07:00 | Draft, gate, images, two cards in #approvals. The run update in #social-drafts names the requests | Card splits (B1). Picture may be missing (B5) |
| 08:00 | One-pager counts the cards | None |
| Approve | Card edits. One feed line. Next slot from 09:00 claims one item; the run update gives the URL | Chrome must be open on the Jura profile every day. Late approval (B2). Line doesn't name the post (S6). Paused (S8) |
| Skip | Item withdrawn, platform skipped for the day, one feed line. The other platform's card stays | No retry (note 1) |
| Unanswered | Nothing visible at the deadline. Today it all lands at 23:30 | B3 |
| Stop signal | `publish stopped`, #alerts, publishing paused for every item | He signs in, then sends `/growth resume publish`. Unavoidable |
| `unknown` item | #alerts asks him to settle it | `/growth publish resolve …`. Unavoidable |

Nothing else asks him to post by hand in `browser` mode. The only remaining hand-post text is in `submit._post`, behind `draft` mode (AF5).

### Outreach email

| SGT | What happens | Where he'd be surprised or asked to act |
|---|---|---|
| Once | `inputs/icp.md` is missing, so research stops before any lead | His step (`PRD:94`). The draft is at `outputs/growth/setup/icp-draft.md` |
| 09:00 | Research keeps leads; they post to #scout-leads and emails queue | Leads aren't asks, so they stay outside #approvals. Correct |
| 09:30 on | First `send-due` raises cards, up to the day's quota | None |
| Approve | Card edits, feed line in #outreach-sent, then a second line when it sends | Two lines is right (FD2). Wrong wording after hours (S7) |
| Skip | Email cancelled, lead `declined_by_ty` for good, one line | A skip is permanent for that company and the line doesn't say so. Accept: the mission-control UAT already covers it |
| Unanswered | Cancelled at 16:30 next business day, lead stays `new` | Today the line lands at 23:30. B3's 18:05 upkeep fixes it |
| Lead unsubscribes | Request closes with no replacement | Vague feed reason (S5) |

### App PRD

| SGT | What happens | Where he'd be surprised or asked to act |
|---|---|---|
| 06:30 | Factory files a PRD, card with PRD attached, run update in #app-factory | None |
| Approve | Handoff written, one feed line | **Nothing builds.** He opens Claude Code by hand (S2). `PRD:73` keeps this out of scope until Dispatch polls |
| After build | `apps built` raises `app-release`. Approve does nothing yet | He runs `apps release-plan`, merges, then `apps released`, all by hand. Feed is silent (S3) |
| Skip | PRD moves to `prd/skipped/apps/`, idea dropped for good, one line | Correct |
| Unanswered 7 days | PRD moves, idea rests 30 days, one line | Correct |

## 3. Acceptance criteria

Each criterion is judged as written. Where the verdict is **Reworded**, the Given / When / Then replaces it. Where it's **Testable**, the values are the ones a tester should use.

| AC | Verdict | Given / When / Then |
|---|---|---|
| AF1 | **Reworded** ("nothing about that post" fails on the run update, which rightly names it) | Given a 280-word Facebook post and a 3-image Instagram post that pass the gate, when `social submit` ends, then each has one `social-post` card holding the exact text, its images in order and its sources; no message has a broken quote or fence; and #social-drafts holds no post text, no image and no words asking him to post. The run update may name the request |
| AF2 | **Reworded** (B2; also needs its exceptions) | Given both platforms approved at 16:59, publishing not paused and Chrome connected, when the slots to 17:40 run, then both post by 18:00, each with its URL in a run update. Given a tap at 17:01 on a pending card, then it answers `expired` and nothing posts. Given no approval, or a pause, then nothing posts (MC A6) |
| AF3 | **Reworded** (names the cases) | Given a platform in `browser` mode with no `page_url`, or a submit after the decide-by, or no images, when `submit` ends, then #social-drafts has a note with that reason, no card, and no "by hand" text |
| AF4 | **Reworded** (B2) | Given no draft yet and both platforms in `browser` mode, when `run social` starts at 17:00 or later, then it skips before Claude starts and the run update gives the reason. Given one platform in `draft` mode at 19:00, then it runs |
| AF5 | Testable | Set Facebook to `publish_mode: draft`. Facebook's hand-post text appears in #social-drafts with no Facebook card; Instagram has a card and no hand-post text |
| FD1 | **Reworded** (needs timing, and "exactly one" per change) | Given a posted card of each of the seven kinds, when it is approved, skipped, expired or closed with no replacement, then one line goes to the mapped channel, with the card's title, masked as the card is. A decision's line posts as the decision returns. A `social-post` expiry's line posts by 18:10. Approve then skip gives two lines, one per change |
| FD2 | **Reworded** (S3, S4) | Given a request superseded on changed content, at any sweep, then no feed line, with or without a successor yet. Given a claim after approval, then no feed line, and the action's own message follows: #outreach-sent, the publish run update, or the "released" line |
| FD3 | Testable | Approve an `app-build`: one "approved" line, no second line at any later sweep |
| FD4 | Testable | Make the post raise: `approval.feed_error` is logged, the card's `shows` is updated, the sweep finishes, and the decision stands |
| DP1 | Testable | `ai-news` on Facebook: 159 fails, 160 passes, 280 passes, 281 fails. Instagram 129/130/240/241. `ai-fun-facts` on Facebook 119/120/220/221. `from-the-toolbox` on Facebook 89/90/180/181 |
| DP2 | **Reworded** (S12) | Given `ai-news` with one source, or two on one host, when submitted, then refused with no regeneration used. Two hosts pass. Independence stays a prompt rule |
| DP3 | **Reworded** (slide count) | Given `ai-news` with 2 detailed items, then refused. With 3, on a Tuesday, Instagram gets 4 images, cover first. A list with 5 items gets 5 images, cover plus 4. `from-the-toolbox` needs no items |
| DP4 | **Reworded** (a tester can't fail "insight") | Automated: the prompt asks for the four parts and repeats the numbers rule. Human: on three real posts, he finds the specifics, why now, a small-business example and one thing to do this week (`uat.md` L3). This is a judgement, recorded as his |
| DP5 | Testable | A DP2 or DP3 shortfall exits 2 and `social_submissions` gains no row. A word miss prints "attempt 1 of 2" and gains a row |
| PC1 | **Reworded** (S1, S14) | Given a theme with `needs_visual` on the headline layout, then `visual` is required, is a flow of 3–4 steps, a compare of two columns with 2–3 points, or a figure, and a percentage draws a ring. Every item on any such theme's card has an icon. A figure's source must match a publisher in `sources.md`, or it's refused |
| PC2 | Testable | Icon `rocket` is refused (it isn't vendored). A step label with "leverage" fails the `social-card` gate. A test finds no raw colour in the templates |
| PC3 | **Reworded** ("nothing overflowing" names no measure) | Given each visual kind with every field at its maximum length, when rendered in real Chrome at 1200×630 and 1080×1350, then each PNG is exactly that size and no element's `scrollHeight` or `scrollWidth` exceeds its box |
| SC1 | **Reworded** (values, S13) | Given `social` last ran 22:00 and 22:01 and `one-pager` 23:00 and 23:00, when the one-pager builds, then Needs you says "about 9 hours off" and to restart the Mac. Given `social` ran 09:30 and 08:10 and `app-factory` 09:30 and 08:10, then no line. Given two days waking at 09:30, with `social` 2.5 hours off and `app-factory` 3, then no line. Given one run off and the latest on time, then no line |

## 4. Edges

| Edge | Status |
|---|---|
| Empty: no story found | Covered: "No draft today" in #social-drafts, no card |
| Empty: every platform skipped before 07:00 | Covered: precheck skips |
| Empty: no images | B5 |
| Maximum: longest post on a card | B1 |
| Maximum: 5 slides, 10 file limit | Covered. A fifth list item gets no slide (note 6) |
| Maximum: longest strings on a picture | PC3 reworded |
| Concurrent: two quick taps | Covered: `already-decided` |
| Concurrent: two approvals together | Covered by the gap; B2 keeps room for both |
| Concurrent: skip while a run is posting | Covered: after the claim it's too late, and he's told |
| Concurrent: decision during a sweep | Note 4 |
| Out of order: approve before 09:00 | Covered: first slot at 09:00 |
| Out of order: approve after the decide-by | B2: answers `expired` |
| Out of order: approve then skip | Covered: two lines, before the claim |
| Out of order: content changes after approval | Covered by ADR 0003; S4 fixes the line |
| Out of order: social run starts late | AF4; a run that crosses the decide-by gets the AF3 note |
| Permission denied: another Discord user | Covered: refused, no line (mission-control B4) |
| Permission denied: headless run or Terminal decides | Covered: refused (ADR 0004) |
| Permission denied: login wall | Covered: stop, pause, #alerts |
| Before the change: drafts already written that day | S11 |
| Before the change: cards already open at merge | Covered: they get lines when they change, which is fine |
| Before the change: old `draft` rows | Covered: the digest reads one day only |
| Chrome closed (U11) | Covered: ends `SKIP:` with one alert a day; rehearsed in `uat.md` S7 |
| Mac off or asleep at 07:00 | Covered: AF4 or a late card; SC1 ignores it |
| Regenerate or edit from a card | **Out of scope**: add to `PRD:68-74` (note 1) |
| Photographs | **Out of scope**: `PRD:70` |
| Automatic builds after approval | **Out of scope**: `PRD:73`, with S2 making it honest |

## 5. Language

`CONTEXT.md` lacks both terms the crew-log says this PRD adds, and "card" is overloaded. The brief limits my writes to this folder, so these are proposals for the conductor to add.

**Agent feed**: The Discord channel where an agent reports what became of its work: its run updates and one line per decision. #approvals asks; the feed says what happened. _Avoid_: drafts channel.

**Feed line**: The one message an agent feed gets when an approval request is approved, skipped, expired or closed with nothing replacing it. It isn't a run update. _Avoid_: notification.

**Approval card**: The message in #approvals for one approval request. _Avoid_: bare "card".

**Image card**: The rendered picture attached to a post, specified in `card.json`. A carousel is several. _Avoid_: bare "card".

**Visual**: The diagram on an image card: a flow, a compare or a figure, drawn from the post's own facts. _Avoid_: picture (in specs), illustration, photo.

Other points:

- **`PRD:33-37`, `PRD:41` and `PRD:56` use "card" for both.** Qualify each one.
- **"Withdrawn" names two things.** It's a publish item state and also the feed's word for a request superseded with no replacement (`feed.py:45`). Keep it: they describe the same event.
- **"Draft" names two things.** It's a `social_posts` status and also a `publish_mode`. Keep both, and always write `draft` mode in full.
- **Update these entries.** Posting window, for B2's decide-by. One-pager, whose "17:30 digest" becomes 18:05 under B3.

## 6. Decisions taken in this review

All of these follow the standing instruction. The conductor can overrule any of them.

1. The `social-post` decide-by is 17:00 SGT and the use-by stays 18:00 (B2).
2. The digest moves to 18:05 and writes lapses first (B3).
3. No images means no card on either platform (B5).
4. The Discord flow is proven on the fixture, through seven harness additions, with no Dispatch UAT key (B6).
5. Live posting starts with Facebook alone on the first day, Instagram the day after. No config change: he skips Instagram's first card (`uat.md` Part L).
6. Regenerate-from-card and automatic builds stay out of scope, and the PRD says so.
