# User acceptance script: approvals first, feeds after, social depth

*For Ting Yu. Written 2026-10-31 by the functional lead against `prd-jura-approvals-first-social-depth-2026-10-31.md`. AC numbers are the PRD's own, as reworded in `reviews/functional.md` section 3. Steps expect the decisions in that review (B1 to B6, S1 to S14).*

*Dry-run on 2026-10-31 for ticket 4: every command here was run as written with `JURA_GROWTH_DISCORD=off`, a stand-in for `claude` first on `PATH`, and the clock frozen on a business day. That proves the commands and what they write. What a card and a feed line say was read from the Discord double in `tests/test_uat_seed_discord_flow.py`. Nothing here has yet run against a real webhook or a real Chrome publish: those steps are the point of this script. The QA lead dry-runs it again before it reaches him.*

## What merging switches on

Read this first. Merging is your acceptance, and you haven't read the PRD.

- Each morning's posts come to #approvals as cards. **Approving one posts it for real**, through your Chrome, on Facebook or Instagram. Meta's terms forbid automated posting; you accepted that risk at the browser publishing sign-off.
- You decide by 17:00 SGT. Skip it or ignore it, and nothing posts. Nothing goes out without your approval of that exact post.
- A post the masking layer would change is refused at the brand gate, so no card shows a masked word and what you read is what posts. A second failure drops that platform's post for the day, and #alerts says why.
- Outreach emails and app PRDs already work this way. They gain a line in their feeds.
- Approving an app PRD hands it to Dispatch, which builds it on its own branch from `main` (`dispatch_builds` is on). You don't build it by hand. Nothing reaches the site until you approve its release as well.

## How this script is laid out

| Part | Checks | When | Touches anything real? |
|---|---|---|---|
| P | Pictures | Any time, before merge | No |
| S | Social flow, on the fixture site | 09:00 to 17:00, any day | Your Chrome on `publish-fixture.localhost` only, and the test Discord server |
| E | Outreach feed lines | A business day, 09:30 to 16:30 | Test server and the Resend stub. No email leaves |
| A | App PRD feed lines | Any time, any day | Test server only. Dispatch reads the live folders, never this one, so nothing is built |
| C | The schedule check | Any time, any day | Test server only |
| L | After merge: your steps and the first real posts | First live days | **Yes**: real posts |

A fail on a step marked **(must)** means the work isn't accepted yet. No step before Part L posts anything real or needs the Dispatch UAT key: the harness records decisions through the same code Dispatch reaches.

The feed lines for `group-rules`, `community-post` and `group-join` are checked by the automated tests only. This change doesn't alter how those kinds work (`PRD:72`).

## Harness items this script needs

Built in ticket 4 (`tests/uat/seed.py`, covered by `tests/test_uat_seed_discord_flow.py`). They are test code, and the seed still refuses any folder that isn't temporary.

| # | Item | Used in |
|---|---|---|
| H1 | Scenario `social-day [--theme ID] [--offline]`: the checked-in sample in `tests/uat/social-day/` (Facebook at 280 words, Instagram at 240, 3 detailed items, a visual, 2 sources on 2 hosts, dated today), put through the real `social submit` with `verify_links: false` in `$UAT/config`. Two pending cards with real rendered images, and it prints their A-ids. With the fixture URL set, the pages are `page.html` and `instagram.html`; without it, test pages, never the real ones | S |
| H2 | Scenario `decide --approval A-nnnn --decision approve\|skip`: calls `approvals.decide` as `_approve` does, sweeps the cards and prints the answer, whatever it is | S, E, A |
| H3 | Scenario `app-prd`: a factory-shape PRD (`tests/uat/app-prd.md`) with its `app-build` request raised through the kind's own code. Each run is a new app, from APP-101. It replaces `new-app-prd`, which was never added | A |
| H4 | Scenario `app-built [--app APP-nnn]`: reports the newest waiting handoff, or that app, as built with a stand-in commit and preview, raising its `app-release` request. Its repository is `$UAT/site`, and `JURA_SITE_REPO` must point there | A |
| H5 | Scenarios `drift` and `late-wake`: the run rows in SC1's reworded criterion, yesterday and the day before | C |
| H6 | Refuse a non-business day only for `outreach-live`, `edit-draft` and `shadow-trial`. Social runs daily, so everything else seeds on a weekend | S, A, C |
| H7 | `_prepare_config` sets `post_buttons: false` in the UAT copy, because a plain webhook can't carry buttons | All |

## Before you start (once)

1. **A test Discord server.** You only need the channels and their webhooks: `daily-digest`, `scout-leads`, `outreach-sent`, `outreach-replies`, `app-factory`, `social-drafts`, `community`, `alerts`, `approvals`, `mission-control`. Skip the Dispatch steps in the older script.
2. **The env file**, `~/jura-uat/uat.env`, outside the repo. Copy nothing from the real `.env`. The seed refuses to run without this file, with a real webhook set in your shell, or with one of the live webhooks in it.

   ```
   DISCORD_WEBHOOK_<CHANNEL>=...    one line for each channel above
   CONTROL_DISCORD_USER_ID=<your Discord user id>
   RESEND_API_KEY_OUTREACH=re_uat_9Xq7Lm2Pz
   UNSUBSCRIBE_SECRET=uat-unsubscribe-secret
   ```

   The Resend key is a fake value and must never work. Run `chmod 600 ~/jura-uat/uat.env`, or every command warns about it.

3. **Chrome** open on the engine's profile, chosen in `/chrome`.

## The windows

**Window 1**: leave the fixture site running.

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth/.claude/worktrees/approvals-first
uv run python -m http.server 8765 --bind 127.0.0.1 --directory tests/fixtures/publish-site
```

**Window 2**: run everything else here.

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth/.claude/worktrees/approvals-first
export JURA_ROOT=/Users/tingy/OneDrive/Desktop/projects/jurasolutions   # needed inside a worktree
export UAT=/tmp/jura-uat
export JURA_GROWTH_DATA_DIR="$UAT/data"
export JURA_GROWTH_OUTPUTS_DIR="$UAT/outputs"
export JURA_PRD_DIR="$UAT/prd"
export JURA_GROWTH_CONFIG_DIR="$UAT/config"
export JURA_GROWTH_PAUSE_FILE="$UAT/PAUSE"
export JURA_GROWTH_ENV_FILE="$HOME/jura-uat/uat.env"
export JURA_INPUTS_DIR="$UAT/inputs"
export JURA_GROWTH_PUBLISH_FIXTURE_URL="http://publish-fixture.localhost:8765"
export TODAY="$(TZ=Asia/Singapore date +%Y-%m-%d)"
fresh() { rm -rf "$UAT" && mkdir "$UAT" && uv run python -m tests.uat.seed "$UAT" --scenario "$1" --today "$TODAY" "${@:2}"; }
decide() { uv run python -m tests.uat.seed "$UAT" --scenario decide --approval "$1" --decision "$2" --today "$TODAY"; }
```

Find a card's A-id on the card, in what the seed prints, or with `uv run jura-growth approvals`.

`JURA_GROWTH_NOW` freezes the clock for one command. It refuses the live folders, so it's safe here.

---

## Part P: pictures, before anything else

Your complaint was "no pictures, so it looks dull". The design system rules out stock images and drawn scenes, so the answer is a diagram of the post's own facts. **If these don't look good to you, stop here.** That's the moment to say so, or to reopen photographs (`PRD §6`, question 1).

The sample words are test data. They stay in a temp folder and the number is a stand-in. `fresh base` comes first because it makes `$UAT/config`: with that folder missing the brand check stops and says its word list is missing, and no render runs.

```bash
fresh base
mkdir -p "$UAT/cards"
cat > "$UAT/cards/flow.json" <<'EOF'
{"layout": "headline", "overline": "AI news", "headline": "A model reads the invoice and you check it",
 "subtitle": "What the new feature does with a supplier invoice.",
 "visual": {"type": "flow", "caption": "How one invoice moves through",
   "steps": [{"icon": "mail", "label": "Invoice arrives"}, {"icon": "scan-text", "label": "Model reads it"},
             {"icon": "user-check", "label": "You check it"}, {"icon": "circle-check", "label": "Filed"}]},
 "items": [{"title": "It reads the fields", "detail": "Supplier, date and total come out of the page.", "icon": "file-text"},
           {"title": "You stay in charge", "detail": "Nothing is filed until a person has looked.", "icon": "eye"},
           {"title": "Try it on one supplier", "detail": "Start where the invoices all look the same.", "icon": "lightbulb"}]}
EOF
cat > "$UAT/cards/compare.json" <<'EOF'
{"layout": "headline", "overline": "Automation tip", "headline": "Let the first reminder go out on its own",
 "visual": {"type": "compare", "caption": "The same late invoice",
   "left": {"icon": "clock", "label": "By hand", "points": ["You notice it is late", "You write the email"]},
   "right": {"icon": "zap", "label": "Automated", "points": ["A rule spots it", "The reminder goes out"]}}}
EOF
cat > "$UAT/cards/figure.json" <<'EOF'
{"layout": "headline", "overline": "AI finding", "headline": "Most small firms in this survey already use AI",
 "visual": {"type": "figure", "value": "62%", "label": "of the small firms surveyed use an AI tool at work", "source": "Example survey"}}
EOF
for card in flow compare figure; do
  uv run jura-growth social render "$UAT/cards/$card.json" --out "$UAT/cards/$card" --size facebook --size instagram --carousel 4 --source https://example.org/survey
done
open "$UAT/cards"
```

**P1. The pictures (must, PC1, PC3)**
- Expect: each `render` prints its PNGs at 1200×630 and 1080×1350. The flow card also gives Instagram slides, cover first, one per item.
- Expect: a diagram you can read at phone size. Nothing is cut off. Green and fonts look like the Jura site. The figure has a ring.
- Ask yourself: would you stop scrolling for this?
- [ ] Pass  [ ] Fail

**P2. What it refuses (must, PC2)**
- Do: in a copy of `flow.json`, set one icon to `rocket`, and render it. Then, in another copy, change a step label to `Leverage the model`, and render that.
- Expect: the first is refused, saying it isn't one of the listed icons. The second is refused by the brand check. Neither makes a PNG.
- [ ] Pass  [ ] Fail

---

## Part S: one social day, on the fixture

Run between 09:00 and 17:00. Cards can't be raised after 17:00, and publish runs stop at 18:00. Each `fresh` empties the UAT folder.

**S1. 07:30: draft to card (must, AF1, DP1, DP3)**
- Do: `fresh social-day --theme ai-news`. It prints each card's A-id.
- Expect, in #approvals: two cards, one Facebook and one Instagram, saying "decide by <today>, 17:00 SGT".
- Expect, on each card: the whole post, quoted cleanly with no stray formatting, even split over two messages; sources shown, as "Links in the text" when the post links them and "Sources" when it can't; the status line and the images together at the top, and the answer line at the end of the card; Instagram's four images in order, cover first. The test server shows no buttons, which is expected: you tested those live on 2026-10-31.
- Expect: no masked word on either card. A post the masking layer would change never reaches a card: it is refused at the brand gate.
- Expect: you could decide from the card alone.
- Expect, in #social-drafts: no post text, no image. Search the test server for `by hand`: no results.
- [ ] Pass  [ ] Fail

**S2. Approve: Facebook posts on the fixture (must, AF2, FD1, FD2)**
- Do: `decide <Facebook A-id> approve`
- Expect: the card reads "Approved by Ting Yu, hh:mm SGT". One line in #social-drafts: `A-nnnn approved`, the post's title, "It goes out on a publish run today, by 18:00 SGT. The run's update here gives the post's address."
- Do: `uv run jura-growth run publish --ignore-schedule`, and watch the tab.
- Expect: one new tab, text typed once, image attached, Post clicked once, tab closed. Your other tabs are untouched.
- Expect, in #social-drafts: one run update with `A-nnnn · Facebook Page · posted · <fixture address>`, and no second "approved" line. `uv run jura-growth publish queue` shows it done.
- [ ] Pass  [ ] Fail

**S3. Approve: the Instagram carousel (must, DP3; this stands in for U13's first carousel)**
- Do: `decide <Instagram A-id> approve`, wait 20 minutes from S2's run, then run publish again.
- Expect: every image uploaded once, in the card's order, then the post recorded. The audit passes and publishing isn't paused.
- [ ] Pass  [ ] Fail

**S4. Skip (must, FD1)**
- Do: `fresh social-day --theme ai-news`, then `decide <Facebook A-id> skip`.
- Expect: the card reads "Skipped by Ting Yu". One line in #social-drafts: `A-nnnn skipped`. The Instagram card is unchanged.
- Do: `uv run jura-growth publish next --json`
- Expect: nothing due. `uv run jura-growth social history --days 1` shows Facebook skipped.
- [ ] Pass  [ ] Fail

**S5. Unanswered (must, FD1)**
- Do: `fresh social-day --theme ai-news`, then `JURA_GROWTH_NOW="${TODAY}T18:05:00+08:00" uv run jura-growth digest`
- Expect: both cards read "Expired: not approved in time". Two lines in #social-drafts, each `A-nnnn expired`. The digest's Publishing line in #daily-digest says "2 expired", and its Social line says "2 drafts expired (facebook, instagram)". Nothing in the digest calls them waiting. Nothing posted.
- [ ] Pass  [ ] Fail

**S6. Late in the day (must, AF2)**
- Do: `fresh social-day --theme ai-news`, then `JURA_GROWTH_NOW="${TODAY}T16:59:00+08:00" decide <Facebook A-id> approve` and the same for Instagram.
- Do: `JURA_GROWTH_NOW="${TODAY}T17:00:00+08:00" uv run jura-growth publish next --json`, then the same at `T17:20:00`.
- Expect: each claims one item, so both make it before 18:00.
- Do: `fresh social-day --theme ai-news`, then `JURA_GROWTH_NOW="${TODAY}T17:01:00+08:00" decide <Facebook A-id> approve`
- Expect: it answers expired. Nothing says the post will go out.
- [ ] Pass  [ ] Fail

**S7. Chrome closed (must, U11)**
- Do: `fresh social-day --theme ai-news`, then `decide <Facebook A-id> approve`. Quit Chrome. Run publish.
- Expect: the run ends `SKIP:` and claims nothing. One post in #alerts about the browser. The item is still approved, so opening Chrome and running publish again posts it.
- [ ] Pass  [ ] Fail

**S8. Publishing paused (should, S8)**
- Do: `fresh social-day --theme ai-news`, `uv run jura-growth pause publish`, then `decide <Facebook A-id> approve`.
- Expect: the feed line ends "Publishing is paused, so nothing goes out until you resume it." `uv run jura-growth publish next --json` gives nothing due. `uv run jura-growth resume publish` lets it claim.
- [ ] Pass  [ ] Fail

**S9. A run after the deadline (must, AF4)**
- Do: `fresh base`, then `JURA_GROWTH_NOW="${TODAY}T17:30:00+08:00" uv run jura-growth run social`.
- Expect: it skips at once with no Claude run, and #social-drafts gives the reason. If Claude starts, stop it with Ctrl-C and mark this failed.
- [ ] Pass  [ ] Fail

**S10. The way back (must, AF5)**
- Do: `fresh base`. Set Facebook's `publish_mode: draft` in `$UAT/config/social.yaml`. Then seed the day without emptying the folder: `uv run python -m tests.uat.seed "$UAT" --scenario social-day --theme ai-news --today "$TODAY"`.
- Expect: Facebook's post and "post it by hand" in #social-drafts, with no Facebook card. Instagram has a card and no hand-post text.- [ ] Pass  [ ] Fail

---

## Part E: outreach

Run on a business day between 09:30 and 16:30. Start the stub in a third window:

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth/.claude/worktrees/approvals-first
JURA_GROWTH_DATA_DIR=/tmp/jura-uat/data uv run python -m tests.resend_stub
```

In Window 2:

```bash
export JURA_GROWTH_RESEND_BASE_URL="http://127.0.0.1:8025" JURA_GROWTH_D1_BASE_URL="http://127.0.0.1:8025"
fresh base
uv run python -m tests.uat.seed "$UAT" --scenario outreach-live --today "$TODAY"
```

Outreach is the only part the seed refuses on a weekend or a public holiday.

Set `approvals.discord_buttons: true` in `$UAT/config/settings.yaml` only, then run `uv run jura-growth outreach send-due`, which raises five cards. It prints "nothing approved to send" as it does: nothing is approved yet.

**E1. Approve, then sent (must, FD1, FD2)**
- Do: `decide <lead 233's A-id> approve`
- Expect: one line in #outreach-sent: `A-nnnn approved`, the card's "To:" title, and "It goes out on a send run, inside the send window and the day's caps." The title shows a shared inbox such as `info@example.com.sg` as it is, and masks only an address naming a person.
- Do: `JURA_GROWTH_NOW="${TODAY}T16:30:00+08:00" uv run jura-growth outreach send-due` (the last slot of the day always sends).
- Expect: one request at the stub, and one sent message in #outreach-sent with its domain and subject. No further "approved" line.
- [ ] Pass  [ ] Fail

**E2. Skip (must, FD1)**
- Do: `decide <another A-id> skip`
- Expect: one `A-nnnn skipped` line. The email never reaches the stub.
- [ ] Pass  [ ] Fail

**E3. Nothing else leaked (must, FD1, MC A6)**
- Do: search the test server for `jane.tan` and `re_uat`.
- Expect: no results in any feed line. `info@example.com.sg` is a shared inbox and does show, on purpose. Only five cards exist at warm-up day 3 and neither planted value is among them, so this step checks for leaks from what was raised. A masked named address on a feed line is proved by `tests/test_feed.py`.
- [ ] Pass  [ ] Fail

**E4. Unanswered (must, FD1; do this last, as it jumps the clock)**
- Do: pick the next business day after today, then `JURA_GROWTH_NOW="<that day>T18:05:00+08:00" uv run jura-growth digest`
- Expect: each email card still pending reads "Expired: not approved in time". One `A-nnnn expired` line for each in #outreach-sent, saying "Not approved in time."
- [ ] Pass  [ ] Fail

---

## Part A: app PRD

**A1. Approve says what happens next (must, FD1, FD3)**
- Do: `fresh base`, `uv run python -m tests.uat.seed "$UAT" --scenario app-prd --today "$TODAY"`.
- Expect: a card with the PRD attached.
- Do: `decide <its A-id> approve`
- Expect: exactly one line in #app-factory: `A-nnnn approved · APP-nnn <name>`, followed by "Handed to Dispatch: it builds APP-nnn on its own branch from main." Nothing asks you to build it by hand. Nothing is built here either: Dispatch polls the live folders, and this approval is in the UAT folder.
- Do: `uv run jura-growth apps handoffs`. Expect: the app, with "handed to Dispatch".
- Do: `uv run jura-growth heartbeat`. Expect: no second line.
- [ ] Pass  [ ] Fail

**A2. Skip (must, FD1)**
- Do: `uv run python -m tests.uat.seed "$UAT" --scenario app-prd --today "$TODAY"` again, which makes a new app, then `decide <its A-id> skip`.
- Expect: one `skipped` line. The PRD is in `$UAT/prd/skipped/apps/` with "Skipped by Ting Yu on <today>" at the top.
- [ ] Pass  [ ] Fail

**A3. A release says what's next (should, S3)**
- Do: `JURA_SITE_REPO="$UAT/site" uv run python -m tests.uat.seed "$UAT" --scenario app-built --today "$TODAY"`. It reports A1's app as built, in a stand-in repository inside the UAT folder, and prints the release's A-id.
- Do: `JURA_SITE_REPO="$UAT/site" decide <the release A-id> approve`
- Expect: one line naming `/growth apps release-plan APP-nnn`.
- [ ] Pass  [ ] Fail

---

## Part C: the schedule check

**C1. Wrong by a steady amount (must, SC1)**
- Do: `fresh drift`, then `uv run jura-growth one-pager`
- Expect, under Needs you in #mission-control: scheduled jobs are about 9 hours off, posting and sending windows are missed, and to restart the Mac.
- [ ] Pass  [ ] Fail

**C2. A Mac that woke late (must, SC1)**
- Do: `fresh late-wake`, then `uv run jura-growth one-pager`
- Expect: no such line.
- [ ] Pass  [ ] Fail

When you finish Parts P to C, stop the servers, close the windows and `rm -rf /tmp/jura-uat`. Delete the test server if you like.

---

## Part L: after merge

These are the only steps that touch the real accounts.

**L1. Your steps, once (must)**

Do them in this order, after 18:05 if you can, so that day's digest isn't confused.

1. In `repos/growth` on the Mac: `git pull`, then `uv sync`.
2. `uv run jura-growth schedule install`. The digest moved to 18:05.
3. Restart the Mac. Log in, because the scheduled jobs and Chrome need your session.
4. Move `outputs/growth/setup/icp-draft.md` to `inputs/icp.md`, after reading it. Keep its `## Industries` bullets. Scout research stops until this exists.
5. Open Chrome on the Jura publishing profile, signed in to the Facebook Page and Instagram, with Claude in Chrome connected. Keep it open 09:00 to 18:00, every day.

- [ ] Done

**L2. The clock (must, SC1)**
- Expect, the next morning: the one-pager arrives at 09:00, and the social run update says about 07:30. Two days later, "Needs you" has no line about hours off.
- If it's still off the day after the restart, run `uv run jura-growth schedule install` again and note it here. The cause was never proved, so this is the real test of it.
- [ ] Pass  [ ] Fail

**L3. First real cards (must, AF1, DP4)**

For the first three posts, before deciding, read each card and answer:

| Post | Says what happened, in specifics | Says why now | Small-business example | One thing to do this week | Would you put your name on it? |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

Open a source or two. Any figure on the picture should be there.

- [ ] Pass  [ ] Fail

**L4. First live Facebook post (must, AF2; U12)**
- Do: on the first real day, approve Facebook and skip Instagram. One new platform at a time, as the setup guide says.
- Expect: a run update in #social-drafts with the post's address. The post on the Page matches the card word for word, with its image. Your other tabs are untouched.
- [ ] Pass  [ ] Fail

**L5. First live Instagram post (must, AF2; U13)**
- Do: the next day, approve both.
- Expect: the carousel is live with its slides in order, and its address in the run update.
- [ ] Pass  [ ] Fail

**L6. A real skip and a real silence (should)**
- Do: over the next days, skip one card and ignore another.
- Expect: nothing posts. Each gets one feed line, the ignored one by 18:10.
- [ ] Pass  [ ] Fail

**L7. Real emails and app PRDs (should)**
- Expect, once research is running: feed lines in #outreach-sent and #app-factory as in Parts E and A. An approved app PRD goes to Dispatch, which builds it on its own branch; its release comes back to you as a card.
- [ ] Pass  [ ] Fail

## Sign-off

| Part | Must steps passed | Notes |
|---|---|---|
| P | /2 | |
| S | /9 | |
| E | /4 | |
| A | /2 | |
| C | /2 | |
| L | /5 | L1 to L5 |

Parts P to C can be done before merge, and merging is your acceptance of them. Part L can only happen after, so a fail there is fixed forward, or set back with `publish_mode: draft` and a `git revert` of the merge.

Accepted by: ________________  Date: ____________

When accepted, the PRD moves to `prd/done/` with its ship date at the top.
