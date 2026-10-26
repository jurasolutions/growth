# Mission control and browser publishing: user acceptance script

*For Ting Yu. Written 2026-10-25 by the functional lead against
`jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md` (MC) and
`jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md` (BP). Revised 2026-10-27 by
the QA lead for your 2026-10-26 amendment (the note before MC §6): every decision is made in
`#approvals` through Dispatch, and no step approves or skips in Terminal. The outreach steps follow
ticket 06: requests only for emails due today, within today's quota, and live mode only with
`approvals.discord_buttons` on. AC numbers are the PRDs' own (AC-M… and AC-P…); U and R numbers
are the manual steps in `reviews/test-strategy-v3.md` §7.*

This replaces the earlier script for the local web page, which was dropped.

## How this script is laid out

| Part | What it checks | When you can run it | Touches anything real? |
|---|---|---|---|
| A | One-pager, run updates, cards, the email gate, the app factory, and that Terminal can't decide | after tickets 01 to 11 and mission-control#14 (Dispatch over SSH), with the UAT route below | No. A temp folder, the Resend stub and a test Discord server |
| B | Control from your phone, buttons, the asleep Mac | after mission-control#14, and for buttons #15's steps 1 to 3 | The test Discord server only |
| C | Publish queue, approvals and limits, with no browser | after BP-02a, BP-02b and Part A's set-up | No |
| D | Real posts and joins through Chrome | after BP-03 to BP-06, one platform at a time | **Yes**: test posts on Jura's real accounts and test groups |
| E | The first live outreach week, and whether the approval load is livable | after mission-control#15 (buttons checked, then live) | **Yes**: real emails |

Tick each step **Pass** or **Fail** and note any fail. A fail on a step marked **(must)** means the
work isn't accepted yet.

**How you decide, everywhere in this script.** In `#approvals`, tap Approve or Skip on the card
once buttons are on (Part B, step B2). Until then, type `/growth approve A-nnnn` or
`/growth skip A-nnnn` in `#approvals` or `#control`. A `group-rules` card never has buttons; type
`/growth approve A-nnnn promo_days=… post_days=…`. Nothing typed in Terminal decides anything.

---

## Before you start (once)

Only you can do these steps. Each one touches your accounts or your Mac.

1. **A test Discord server.** Create a server called "Jura HQ UAT" with these channels:
   `daily-digest`, `scout-leads`, `outreach-sent`, `outreach-replies`, `app-factory`,
   `social-drafts`, `community`, `alerts`, `mission-control`, `approvals`, `control`. Make a webhook
   for each one. Set `#approvals` to notify on all messages on your phone.
2. **A UAT env file**, outside the repo: `~/jura-uat/uat.env`. Put the eleven
   `DISCORD_WEBHOOK_<CHANNEL>` lines in it, plus:
   ```
   CONTROL_DISCORD_USER_ID=<your Discord user id>
   RESEND_API_KEY_OUTREACH=re_uat_9Xq7Lm2Pz
   UNSUBSCRIBE_SECRET=uat-unsubscribe-secret
   ```
   The Resend key is a fake planted value. It is used to check masking, and it must never work.
   Don't copy anything from the real `.env`.
3. **A second Discord account**, or a friend willing to tap one button, for B4.
4. **The UAT route through Dispatch.** Dispatch must reach the UAT folder, never the live one. Bind
   "Jura HQ UAT"'s `#approvals` and `#control` in Dispatch to a UAT-only SSH key whose
   `authorized_keys` entry runs `bin/growth-remote` with the UAT folder variables fixed in the entry
   itself (`JURA_GROWTH_DATA_DIR=/tmp/jura-uat/data`, `JURA_GROWTH_OUTPUTS_DIR=/tmp/jura-uat/outputs`,
   `JURA_PRD_DIR=/tmp/jura-uat/prd`, `JURA_GROWTH_CONFIG_DIR=/tmp/jura-uat/config`,
   `JURA_GROWTH_PAUSE_FILE=/tmp/jura-uat/PAUSE`, `JURA_GROWTH_ENV_FILE=~/jura-uat/uat.env`). Remove
   that key and binding when you finish. *The exact form of this entry is waiting on the tech lead
   (QA lead's question, crew-log 2026-10-27); until it is settled, Parts A to C can't be run.*
5. **The harness.** `uv run python -m tests.uat.seed <folder> [--scenario <name>] [--today <date>]`
   seeds the data, and `uv run python -m tests.resend_stub` records what would have gone to Resend.
   The scenarios each step needs are listed under "Seed data"; the ones still missing are in ticket
   17 and the tickets named there.

### The window for Parts A and C

Run Parts A and C on a real business day: decisions come through Dispatch on the real clock, so the
seed dates everything from today. Run every Terminal command in one window with these set:

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
rm -rf /tmp/jura-uat && mkdir /tmp/jura-uat
export UAT=/tmp/jura-uat
export JURA_GROWTH_DATA_DIR="$UAT/data"
export JURA_GROWTH_OUTPUTS_DIR="$UAT/outputs"
export JURA_PRD_DIR="$UAT/prd"
export JURA_GROWTH_CONFIG_DIR="$UAT/config"
export JURA_GROWTH_PAUSE_FILE="$UAT/PAUSE"
export JURA_GROWTH_ENV_FILE="$HOME/jura-uat/uat.env"
export TODAY="$(TZ=Asia/Singapore date +%Y-%m-%d)"
uv run python -m tests.uat.seed "$UAT" --today "$TODAY"
```

The seed refuses any folder that isn't a temporary one, so nothing here can touch
`jurasolutions/data/` or your real `.env`. Don't run `schedule install` or `schedule render` in this
window.

**The clock.** Steps run on the real clock unless they set `JURA_GROWTH_NOW` for one command. A step
that jumps the clock forward (to 16:31, or to a later day) comes last in its part, after every
decision in that part, because a decision is always stamped with the real time.

### Seed data

| Ref | What the seed holds | Scenario, and who adds it | Used in |
|---|---|---|---|
| S1 | Run history for every job from eight days before `--today`, with one business day's scout-send traces missing two slots and carrying a quiet run six minutes late | `base` (in `tests/uat/seed.py`; `--today` is ticket 17) | A1 |
| S2 | Today: app-factory ok at 06:31 (US$1.20, filed APP-014); social ok at 07:00 (4m 12s, US$0.41). Social in `browser` mode for Facebook only, in `$UAT/config` | `base` | A1, A2, C1 |
| S3 | `outreach.mode: live` with every live pre-condition met in `$UAT/config`, warm-up day 3 (cap 5), Resend pointed at the stub, and `approvals.discord_buttons: false` (A4 turns it on) | `outreach-live` (ticket 17) | A4 |
| S4 | Queued first emails: lead 233 (Example Pte Ltd, `info@example.com.sg`, queued the previous business day 09:12); leads 240 to 254 (15 emails, queued today 09:05); lead 260 (named address `jane.tan@example.com.sg`). Requests over them are raised by the outreach commands themselves, never by the seed | rows: `base`; requests: by the first `send-due` of the day once S3 is set (ticket 17 checks this works from the seed) | A3, A4 |
| S5 | The reply text "Please take us off your list" and the phone number `+65 9123 4567` planted in an outreach reply record and a transcript | `base` | A6 |
| S6 | `RESEND_API_KEY_OUTREACH`'s value planted in a run summary, an error, a transcript and an email draft | `base` | A6 |
| S7 | `$UAT/prd/pending/apps/prd-app-014-…md`, the factory PRD from S2 | `base` | A5 |
| S8 | Community groups G4 (joined, good fit, rules "promo Saturdays only", not confirmed) and G7 (good fit, not joined, asks membership questions) | `base` | C3 |
| S9 | Lead 240's queued email with its draft body changed after its request was raised | `edit-draft --lead 240` (ticket 17) | A4 |
| S10 | 40 shadow-trial emails for `requeue-shadow` | `shadow-trial` (ticket 17) | B6 |
| S11 | APP-015, a second factory PRD | `new-app-prd` (ticket 10) | A5 |
| S12 | A Facebook item approved for today, and one claimed with neither `done` nor `stopped` | `social-approved`, `claimed-not-closed` (BP-02a) | C2 |
| S13 | A planned G4 post for today that mentions Jura; G4's rules seen inside the group | `community-plan` (BP-02b), `note-rules --group 4` (ticket 05) | C3 |

---

## Part A: the engine, with every decision in #approvals

**A1. The morning one-pager (must, AC-M1.1 to AC-M1.3, AC-M2.1)**
- Do: `JURA_GROWTH_NOW="${TODAY}T08:00:00+08:00" uv run jura-growth one-pager`
- Expect, in `#mission-control` on your phone:
  - One message headed with today's date "as of 08:00 SGT", then Needs you, Approvals waiting,
    Today, Yesterday, Ask me, and the 14-day grid as an image.
  - Approvals waiting counts the app build. It points at `#approvals`, and says nothing about
    deciding in Terminal.
  - On the grid, the day with the missing scout-send traces shows "2 missed" in words, not only a
    red cell, and a public holiday in the fortnight shows no slots for the business-day jobs.
- Expect: you can read it without zooming on the phone.
- [ ] Pass  [ ] Fail

**A2. Run updates (must, AC-M3.1, AC-M3.2)**
- Expect: from the seed, `#app-factory` and `#social-drafts` each hold one run update for today. The
  social one starts `**social** · ok · 07:00 SGT · 4m 12s · US$0.41`, and its "Waiting for you"
  line lists the Facebook request.
- Do: `uv run jura-growth pause social`, then
  `JURA_GROWTH_NOW="${TODAY}T23:00:00+08:00" uv run jura-growth run social`. (This is a UAT folder
  with a paused agent, so no Claude run starts.)
- Expect: one message in `#social-drafts` reading "skipped: paused by hand".
- Do: `uv run jura-growth resume social`.
- [ ] Pass  [ ] Fail

**A3. Terminal can't decide (must, AC-M7.2, AC-M7.3; U1)**
- Do: `uv run jura-growth approvals`. Expect: it lists the pending requests.
- Do: `uv run jura-growth approve <APP-014's A-id>`, then `uv run jura-growth skip <APP-014's A-id>`.
- Expect: each answers "refused: decisions aren't taken in Terminal: approve or skip it in
  #approvals.", asks for no code, and `jura-growth approvals` still shows APP-014's request pending.
  Its card in `#approvals` hasn't changed and shows no code.
- [ ] Pass  [ ] Fail

**A4. The email gate (must, AC-M5.1, AC-M8.1 to AC-M8.9, AC-M8.11)**

Start the stub in a second window: `uv run python -m tests.resend_stub`. It prints every request it
receives. Then seed S3: `uv run python -m tests.uat.seed "$UAT" --scenario outreach-live --today
"$TODAY"`.

- *Live waits for the buttons switch.*
  Do: `uv run jura-growth status`, then `uv run jura-growth outreach send-due`.
  Expect: `status` lists "approval buttons not set up" under live problems, and `send-due` refuses.
  Do: set `approvals.discord_buttons: true` in `$UAT/config/settings.yaml` only (never in the real
  `config/`), and run `status` again. Expect: no live problems.
- *Requests only for what can go out today.*
  Do: `uv run jura-growth outreach send-due` (its first run of the day raises the requests).
  Expect: exactly 5 cards in `#approvals` (today's warm-up cap), and `uv run jura-growth outreach
  queue-list` shows the other emails "waiting for a request slot".
  Nothing reaches the stub, because nothing is approved yet.
- *A card says what, why and when.*
  Expect, on lead 233's card: "A-nnnn · outreach email · decide by <the next business day>, 16:30
  SGT" (a public holiday is skipped), the To line with company, industry and score, a Why line
  naming the lead, the run and the source page, the subject, the body exactly as it will go out,
  and how to answer. No code.
  Expect, if lead 260 is among the five: `j***@example.com.sg` with its source page, and no personal
  name in the body.
  Expect: you could decide from the card alone, without opening anything else.
- *Approve one; it sends once.*
  Do: in `#approvals`, `/growth approve <lead 233's A-id>`.
  Expect: the reply says recorded, and the card's first line now reads "Approved by Ting Yu, hh:mm
  SGT". Do: run `send-due` now, then again after 10 and 20 minutes (or at the next slots).
  Expect: one request at the stub, to `info@example.com.sg`, at the first slot the spacing allows,
  and no second send for that email.
- *A change after approval.*
  Do: approve lead 240's card in `#approvals`, then
  `uv run python -m tests.uat.seed "$UAT" --scenario edit-draft --lead 240 --today "$TODAY"`, then
  `send-due`.
  Expect: lead 240's card reads "Superseded", a new card appears for the edited text, and lead 240
  doesn't send.
- *Undo before it goes.*
  Do: approve another of the five in `#approvals`, then `/growth skip <its A-id>` before the next
  `send-due`.
  Expect: the card reads "Skipped", that email never sends, and the lead is `declined_by_ty`, a final status, so
  scout never queues it again.
- *The pile tops up.*
  Do: run `send-due` once more.
  Expect: new cards appear only to fill today's remaining quota (5, less what was sent, less what is
  still approved and waiting). The waiting count goes down by the same number.
- *Too late to undo.*
  Do: `/growth skip <lead 233's A-id>` after it sent.
  Expect: "already sent at hh:mm; can't be undone", and nothing changes.
- *Silence never counts as a yes (do this last).*
  Leave one card pending and one approved but unsent. Then run
  `JURA_GROWTH_NOW="<the next business day>T16:31:00+08:00" uv run jura-growth heartbeat` (or the
  harness's equivalent).
  Expect: the pending one reads "Expired: not approved in time", its email is cancelled, and its lead
  stays `new`. The approved one still reads "Approved" until 16:30 on the third business day after
  approval; run the same command at that time and it reads expired, with its email cancelled
  ("approved but the limits didn't reach it") and its lead `new`. The next one-pager lists it.
- *Audit.*
  Do: `uv run jura-growth log events --kind approval` (or the harness's equivalent).
  Expect: one event per transition above, each with `discord:<your id>`, origin `ssh`, the time and
  the content hash. None says `terminal`.
- [ ] Pass  [ ] Fail

**A5. App idea to preview to release (must, AC-M9.1 to AC-M9.9)**
- Expect: the APP-014 card in `#approvals` has the PRD file attached and shows the pitch, tier and
  lead types. `#app-factory` has no "approved, build …" line.
- Do: in `#approvals`, `/growth approve <APP-014's A-id>`.
- Expect: the reply carries "Build it: open Claude Code in `jurasolutions/` and say: build the
  approved PRD … (approval A-nnnn)", because Dispatch builds aren't on. In Terminal,
  `uv run jura-growth apps handoffs --json` lists APP-014 with `repo: "landing-page"`, `base:
  "main"`, the PRD text and its SHA-256.
- Do: `uv run jura-growth apps released APP-014 --task T-0031`.
- Expect: refused, because no release is approved.
- Do: `uv run jura-growth apps built APP-014 --task T-0031 --branch claude/T-0031-paynow-qr --sha
  <any sha> --preview https://uat.example.pages.dev`.
- Expect: an `app-release` card with the preview link and the short SHA.
- Do: in `#approvals`, `/growth skip <its A-id>`.
- Expect: APP-014 stays on preview, and the one-pager (re-run A1's command without the clock) lists
  it.
- Do: `uv run python -m tests.uat.seed "$UAT" --scenario new-app-prd --today "$TODAY"` (APP-015),
  then in `#approvals`, `/growth skip <APP-015's A-id>`.
- Expect: the PRD is now in `$UAT/prd/skipped/apps/` with "Skipped by Ting Yu on <today>" at the
  top, and `uv run jura-growth apps context --json` doesn't offer that idea.
- [ ] Pass  [ ] Fail

**A6. Nothing secret or personal reaches Discord (must, AC-M11.1, AC-M11.2, AC-M12.1)**
- Do: in the UAT server, search for `re_uat`, `9Xq7Lm2P`, `jane.tan`, `9123 4567` and
  `take us off`.
- Expect: no results. Where the values were planted, the messages show `[redacted]` or the masked
  form.
- Do: `uv run jura-growth status`.
- Expect: setup gaps by name only, with no value, prefix, length or Keychain service name.
- [ ] Pass  [ ] Fail

**A7. Headless runs can't decide (must, AC-M7.1)**
- Do: `JURA_GROWTH_JOB=social uv run jura-growth approve <any pending A-id>`
- Expect: exit status 2 with a `refused:` line, and the request is still pending.
- [ ] Pass  [ ] Fail

---

## Part B: from your phone, through Dispatch

Same UAT route and folder as Part A (reseed first if Part A is finished).

**B1. Check and steer the engine (must, AC-M1.6, AC-M10.1, AC-M10.7; U7)**
- Do, from your phone in `#control`: `/growth status`, then `/growth one-pager`, then
  `/growth pause social looking into it`, then `/growth resume social`.
- Expect: each answers within 60 seconds. The one-pager posts in `#mission-control` and the reply
  says so. The pause shows in the next `/growth status` and is gone after the resume.
- Do: `/growth resume all` while a `PAUSE` file exists (`touch "$UAT/PAUSE"` on the Mac first).
- Expect: the reply says the PAUSE file can only be removed on the Mac. Then `rm "$UAT/PAUSE"`.
- [ ] Pass  [ ] Fail

**B2. One tap per decision (must, AC-M5.3, AC-M6.1, AC-M6.2; U17)**
- Needs: mission-control#15 steps 1 and 2 done for the UAT server: Dispatch's own webhook stored for
  `#approvals` in `~/jura-uat/uat.env`, and `approvals.post_buttons: true` in `$UAT/config`.
- Do: run `uv run jura-growth outreach send-due` so today's cards post with buttons. Tap Approve on
  one email card and Skip on another.
- Expect: each card changes in place, to "Approved by Ting Yu, hh:mm SGT" or "Skipped", and the
  buttons go away. `uv run jura-growth approvals` on the Mac agrees, with
  `decided_by = discord:<your id>`.
- Do: tap Approve twice quickly on a third card.
- Expect: one decision recorded. The second tap answers "already decided".
- Expect: a `group-rules` card, if one is waiting, has no buttons.
- Time it: approve or skip ten cards, reading each one properly. Write down how long it took:
  ______ minutes.
- [ ] Pass  [ ] Fail

**B3. Commands that are not allowed (must, AC-M10.2)**
- Do: `/growth run social`, then `/growth schedule install`, then `/growth db`.
- Expect: each is refused, and nothing runs on the Mac.
- [ ] Pass  [ ] Fail

**B4. Only you, only in Jura's channel (must, story 27; U7)**
- Do: have your second account tap Approve on a pending card, and type `/growth status`.
- Expect: both refused. The card stays pending.
- Do: from a TaskWise channel that Dispatch serves, type `/growth status`.
- Expect: refused, or ignored. No growth command runs.
- [ ] Pass  [ ] Fail

**B5. The Mac is asleep (should, MC §4.7)**
- Do: close the Mac's lid. Two minutes later, tap Approve on a pending card.
- Expect: Dispatch replies "the growth Mac is unreachable", and the card stays pending. Open the lid
  and confirm nothing was recorded late.
- [ ] Pass  [ ] Fail

**B6. Requeue the shadow emails from Discord (should, AC-M8.13)**
- Do: `uv run python -m tests.uat.seed "$UAT" --scenario shadow-trial --today "$TODAY"`, then from
  `#control`: `/growth outreach requeue-shadow --dry-run`, then without `--dry-run`.
- Expect: a list first, then new cards only up to today's remaining quota; the rest wait for a
  request slot. Nothing sends until a card is approved in `#approvals`.
- [ ] Pass  [ ] Fail

---

## Part C: the publish queue, no browser yet

Same window, variables and UAT route as Part A.

**C1. A request per item, and nothing without approval (must, AC-P1.1, AC-P2.1, AC-P2.2, AC-P5.1)**
- Expect, from the seed: one `social-post` card for Facebook, "decide by <today>, 18:00 SGT", with
  the text, the image and the Page link. No card for LinkedIn or Instagram (still `draft`).
- Do: `uv run jura-growth publish next --json`
- Expect: "nothing due" (the card isn't approved).
- Do: approve the card in `#approvals`. Then run
  `JURA_GROWTH_NOW="${TODAY}T08:59:00+08:00" uv run jura-growth publish next --json`, then
  `uv run jura-growth publish next --json` on the real clock (inside 09:00 to 18:00).
- Expect: 08:59 gives nothing due (outside the window). The second claims the item and prints its
  exact text and image path.
- Do: run `publish next` again.
- Expect: nothing due (one item per platform per day, and one item per run).
- [ ] Pass  [ ] Fail

**C2. Expiry and the unknown state (must, AC-P3.1, AC-P10.1, AC-P10.2)**
- Do: reseed with `--scenario social-approved`. Run
  `JURA_GROWTH_NOW="${TODAY}T18:01:00+08:00" uv run jura-growth publish next --json` (do this last
  in the part).
- Expect: nothing claimed, and the item reads expired in `publish queue` and on its card.
- Do: reseed with `--scenario claimed-not-closed`.
- Expect: the item is `unknown`, publish is paused, `#alerts` asks you to settle it, and
  `/growth publish resolve <A-id> not-posted` in `#control` settles it.
- [ ] Pass  [ ] Fail

**C3. Community posts need confirmed rules and days (must, AC-P5.1 lines 8 and 9, AC-M10.6)**
- Do: reseed with `--scenario community-plan`, which plans a G4 post for today that mentions Jura.
  Approve its card in `#approvals`, then run `publish next`.
- Expect: refused. The rules aren't confirmed, and "promo Saturdays only" closes a weekday for a
  promotional post.
- Do: `uv run python -m tests.uat.seed "$UAT" --scenario note-rules --group 4 --today "$TODAY"`.
- Expect: a `group-rules` card showing the rules text, with no buttons.
- Do: in `#approvals`, `/growth approve <its A-id>` without days.
- Expect: refused: "say the days: promo_days=… post_days=…".
- Do: `/growth approve <its A-id> promo_days=sat post_days=any`.
- Expect: recorded. Today's item is still refused, and a Saturday item for G4 is claimable on
  Saturday inside the window.
- [ ] Pass  [ ] Fail

**C4. Kill switches (must, AC-P5.3)**
- Do: one at a time, `touch "$UAT/PAUSE"`; `uv run jura-growth pause publish`;
  `publish_mode: draft` for Facebook in `$UAT/config/social.yaml`. Run `publish next` after each,
  then undo it.
- Expect: nothing due each time, and the approved card is still approved afterwards.
- [ ] Pass  [ ] Fail

---

## Part D: real posts through Chrome (BP-03 to BP-06)

These post publicly on Jura's real accounts, as the PRD's own checks require. Use test text you're
happy to leave up, or delete it by hand afterwards. You need:

- BP-01 done: the engine's Chrome profile chosen in `/chrome`, signed in to the Jura Facebook Page,
  Instagram and LinkedIn company page, and nothing else;
- Dispatch bound to the real Jura HQ `#approvals` (mission-control#14), because these are real
  decisions;
- a **private Facebook test group** you set up, joined as the Jura Page, with written rules naming
  one open day;
- a **second test group** run by someone else that allows Pages and asks membership questions, for
  D5;
- the Mac awake and logged in from 09:00 to 18:00. Open a fresh Terminal without the UAT variables.

**D1. One approved post goes live (must, BP-03, AC-P7.1, AC-P8.1; U12)**
- Do: put Facebook in `browser` mode. The next morning, approve the Facebook card in `#approvals`.
- Expect: within 20 minutes of the first slot after you approve, a run update in `#social-drafts`
  with the live post URL. The post on the Page matches the card word for word, with the same image.
  `jura-growth social history` shows it published with that URL.
- Expect: your other Chrome tabs are untouched, and the run's tab is closed afterwards.
- [ ] Pass  [ ] Fail

**D2. Skip and silence don't post (must, AC-P2.3, AC-P3.1)**
- Do: on the next day, skip the Facebook card in `#approvals`. On the day after, don't answer it.
- Expect: nothing posts on either day. The second card reads expired after 18:00.
- [ ] Pass  [ ] Fail

**D3. A login wall stops everything (must, AC-P6.1)**
- Do: sign out of Facebook in the engine's profile, then approve that day's card.
- Expect: the run stops without typing anything. `#alerts` gives the reason and a screenshot path,
  and publish is paused. Nothing else is attempted until you sign back in and send
  `/growth resume publish`.
- [ ] Pass  [ ] Fail

**D4. The other platforms (must, BP-04; U13)**
- Before: answer BP §6 again (weekend posts once three platforms are in `browser` mode).
- Do: repeat D1 for Instagram, on a carousel day, and then for LinkedIn.
- Expect: each goes live with its URL recorded. The carousel's slides are in order.
- [ ] Pass  [ ] Fail

**D5. Community post and join, as the Jura Page (must, BP-05, BP-06; U14, U15)**
- Do: confirm the test group's rules through its `group-rules` card, typing the days in
  `#approvals`. Approve a planned post for the open day, and one for a closed day.
- Expect: the open-day post goes live in the test group as the Jura Page, with its URL in
  `#community`. The closed-day item is never claimed.
- Do: approve the join card for the second test group.
- Expect: the run joins as the Jura Page, sees the questions, submits nothing, and a second card
  shows the questions and drafted answers. Approve it. A later run submits exactly those answers.
  `jura-growth community groups` shows `requested`.
- [ ] Pass  [ ] Fail

---

## Part E: the first live outreach week

Only after mission-control#15: buttons checked (U17), then `approvals.discord_buttons: true`, then
`outreach.mode: live` in the real `config/`.

**E1. The real gate on real email (must, AC-M8.1, AC-M8.2, AC-M8.4, AC-M8.6; U6)**
- Expect, on the first live day: every email that goes out had a card you approved in `#approvals`.
  There are never more open email cards than the day's quota (5 in warm-up week 1), and
  `#outreach-sent` lists no more than that, spread across 09:30 to 16:30.
- Do: skip one card and leave one unanswered.
- Expect: neither sends. The unanswered one is cancelled at 16:30 on the next business day ("not
  approved in time"), and its lead stays `new`. The skipped one's lead is `declined_by_ty`.
- [ ] Pass  [ ] Fail

**E2. Is the load livable? (must, functional section 3)**
- For five business days, note how many cards you answered and how long it took:

| Day | Emails | Social | Community and joins | App | Minutes |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

- Pass if you'd keep doing it this way. If not, the levers are lowering `research.daily_target`,
  batch approval (MC §3 out of scope; revisit after two weeks), or fewer `browser` platforms.
- [ ] Pass  [ ] Fail

**E3. The morning brief line is gone (should, AC-M14.1; U4)**
- Expect: the Cowork morning brief no longer carries the growth line, and the one-pager arrives at
  08:00 each day.
- [ ] Pass  [ ] Fail

---

## Sign-off

| Part | Must steps passed | Notes |
|---|---|---|
| A | /7 | |
| B | /4 | |
| C | /4 | |
| D | /5 | |
| E | /2 | |

Accepted by: ________________  Date: ____________

When accepted and shipped, each PRD moves to `prd/done/` with its ship date at the top.

When you finish Parts A to C, close that window to drop the variables, stop the Resend stub, remove
the UAT key and Dispatch binding, and delete `/tmp/jura-uat`.
