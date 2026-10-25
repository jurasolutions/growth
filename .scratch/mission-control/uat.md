# Mission control and browser publishing: user acceptance script

*For Ting Yu. Written 2026-10-25 by the functional lead against
`jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md` (MC) and
`jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md` (BP). The AC numbers point at
section 10 of `reviews/functional.md`. Where a step depends on a finding you haven't accepted yet
(B1 to B5, S1 to S17), it says so. If you rejected that finding, skip the step and note it.*

This replaces the earlier script for the local web page, which was dropped.

## How this script is laid out

| Part | What it checks | When you can run it | Touches anything real? |
|---|---|---|---|
| A | One-pager, run updates, approvals, the email gate, app factory: decided from Terminal | after MC blocks 0 to 5 | No. A temp folder and a test Discord server |
| B | Control from Discord through Dispatch | after MC block 6 and Dispatch D1 to D5 | The test Discord server only |
| C | Publish queue, approvals and limits, with no browser | after BP block 1 | No |
| D | Real posts and joins through Chrome | after BP blocks 2 to 5, one platform at a time | **Yes**: test posts on Jura's real accounts and test groups |
| E | The first live outreach day, and whether the approval load is livable | at go-live | **Yes**: real emails |

Tick each step **Pass** or **Fail** and note any fail. A fail on a step marked **(must)** means the
work isn't accepted yet.

---

## Before you start (once)

Only you can do these steps. Each one touches your accounts.

1. **A test Discord server.** Create a server called "Jura HQ UAT" with the same channels as Jura HQ,
   plus three new ones: `daily-digest`, `scout-leads`, `outreach-sent`, `outreach-replies`,
   `app-factory`, `social-drafts`, `community`, `alerts`, `mission-control`, `approvals`, `control`.
   Make a webhook for each one. Set `#approvals` to notify on all messages on your phone.
2. **A UAT env file**, outside the repo: `~/jura-uat/uat.env`. Put the eleven
   `DISCORD_WEBHOOK_<CHANNEL>` lines in it, plus:
   ```
   CONTROL_DISCORD_USER_ID=<your Discord user id>
   RESEND_API_KEY_OUTREACH=re_uat_9Xq7Lm2Pz
   UNSUBSCRIBE_SECRET=uat-unsubscribe-secret
   ```
   The Resend key is a fake planted value. It is used to check masking, and it must never work.
   Don't copy anything from the real `.env`.
3. **A second Discord account**, or a friend willing to tap one button, for the "someone else taps
   Approve" check (B4 in Part B).
4. **The build's UAT harness** (functional S15). This script assumes
   `uv run python -m tests.mission_seed <folder> [--scenario <name>]` and a local Resend stub started
   with `uv run python -m tests.resend_stub`. If the block reports name them differently, use their
   names.

### The window for Parts A and C

Run every Part A and Part C command in one Terminal window with these set:

```bash
cd /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth
export UAT="$(mktemp -d)"
export JURA_GROWTH_DATA_DIR="$UAT/data"
export JURA_GROWTH_OUTPUTS_DIR="$UAT/outputs"
export JURA_PRD_DIR="$UAT/prd"
export JURA_GROWTH_CONFIG_DIR="$UAT/config"
export JURA_GROWTH_PAUSE_FILE="$UAT/PAUSE"
export JURA_GROWTH_ENV_FILE="$HOME/jura-uat/uat.env"
export JURA_GROWTH_NOW="2026-11-10T08:00:00+08:00"
uv run python -m tests.mission_seed "$UAT"
```

You change `JURA_GROWTH_NOW` from step to step, as each step says. A frozen clock refuses to run
against the live folders, so nothing here can touch `jurasolutions/data/` or your real `.env`. Don't
run `schedule install` or `schedule render` in this window.

### Seed data

The dates: Fri 2026-11-06 and Tue 2026-11-10 are business days. Sun 2026-11-08 is Deepavali and Mon
2026-11-09 is its observed holiday.

| Ref | What the seed holds | Used in |
|---|---|---|
| S1 | Run history from 2026-11-02 for every job. A quiet scout-send trace in every 11-10 slot before 08:00 is impossible, so 11-06 carries them, with 10:00 and 10:10 missing and a quiet run at 10:26 | A1 |
| S2 | On 11-10: app-factory ok at 06:31 (US$1.20, filed APP-014); social ok at 07:00 (4m 12s, US$0.41). Social is in `browser` mode for Facebook only, in `$UAT/config` | A1, A2, C1 |
| S3 | `outreach.mode: live` with every live pre-condition met in `$UAT/config`, warm-up day 3 (cap 5), and Resend pointed at the stub | A4 |
| S4 | Live queued emails, each with a pending `outreach-email` request: lead 233 (Example Pte Ltd, `info@example.com.sg`, queued Fri 11-06 09:12); leads 240 to 254 (15 emails, queued Tue 11-10 09:05); lead 260 (named address `jane.tan@example.com.sg`, enquiry contact) | A3, A4 |
| S5 | The reply text "Please take us off your list" and the phone number `+65 9123 4567` planted in an outreach reply record and a transcript | A6 |
| S6 | `RESEND_API_KEY_OUTREACH`'s value (from `uat.env`) planted in a run summary, an error, a transcript and an email draft | A6 |
| S7 | `$UAT/prd/pending/apps/prd-app-014-…-2026-11-10.md`, the factory PRD from S2 | A5 |
| S8 | Community groups G4 (joined, good fit, rules "promo Saturdays only", not confirmed) and G7 (good fit, not joined, asks membership questions) | C3, C4 |

---

## Part A: the engine, decided from Terminal

**A1. The morning one-pager (must, AC-M1, AC-M2)**
- Do: `JURA_GROWTH_NOW=2026-11-10T08:00:00+08:00 uv run jura-growth one-pager`
- Expect, in `#mission-control` on your phone:
  - One message headed "Tue 10 Nov, as of 08:00 SGT", then Needs you, Approvals waiting, Today,
    Yesterday, Ask me, and the 14-day grid as an image.
  - Approvals waiting counts the S4 emails and the app build, and names A-nnnn for lead 233 as the
    oldest (decide-by today, 16:30).
  - On the grid, 11-06 shows scout-send with "2 missed" in words, not a red row, and 11-09 shows no
    slots for the business-day jobs.
- Expect: you can read it without zooming on the phone.
- [ ] Pass  [ ] Fail

**A2. Run updates (must, AC-M3)**
- Expect: from the seed, `#app-factory` and `#social-drafts` each hold one run update for today. The
  social one starts `**social** · ok · 07:00 SGT · 4m 12s · US$0.41`, and its "Waiting for you"
  line lists the Facebook request.
- Do: `uv run jura-growth pause social`, then
  `JURA_GROWTH_NOW=2026-11-11T07:00:00+08:00 uv run jura-growth run social`.
- Expect: one message in `#social-drafts` reading "skipped: paused by hand", and no Claude run.
- Do: `uv run jura-growth resume social`.
- [ ] Pass  [ ] Fail

**A3. An approval card says what, why and when (must, AC-M5)**
- Expect, in `#approvals`, the card for lead 233: "outreach email · expires Tue 10 Nov, 16:30 SGT"
  (the expiry skips the holiday), the To line with company, industry and score, a Why line with the
  source page, the subject, the body exactly as it will go out, and how to answer.
- Expect: the card for lead 260 shows `j***@example.com.sg` with its source page, and the body has
  no personal name (functional S7).
- Expect: you could decide from the card alone, without opening anything else.
- [ ] Pass  [ ] Fail

**A4. The email gate (must, AC-M4, AC-M6, AC-M7)**
- Start the stub in a second window: `uv run python -m tests.resend_stub`. It prints every request it
  receives.
- *Unapproved emails don't send.*
  Do: `JURA_GROWTH_NOW=2026-11-10T10:00:00+08:00 uv run jura-growth outreach send-due`.
  Expect: nothing sent, the stub prints nothing.
- *Approve one.*
  Do: `uv run jura-growth approvals outreach-email`, then `uv run jura-growth approve <lead 233's
  A-id>`.
  Expect: the reply names it approved by `terminal:<your user>`. The card in `#approvals` now reads
  "Approved" (functional S8).
- *It sends once.*
  Do: run `send-due` at 10:00 again, then at 10:05 and 10:10.
  Expect: one request at the stub, to `info@example.com.sg`, at the first slot that the spacing
  allows. No second send for that email at any slot.
- *A change after approval.*
  Do: approve lead 240's request, then
  `uv run python -m tests.mission_seed "$UAT" --scenario edit-draft --lead 240`.
  Expect: lead 240's old request reads "Superseded", a new card appears for the edited text, and
  `send-due` doesn't send lead 240.
- *Undo.*
  Do: approve lead 241, then `uv run jura-growth skip <its A-id> "wrong one"`.
  Expect: it reads "Skipped" and lead 241 never sends (functional S5).
- *Approving more than the warm-up can send (needs B1).*
  Do: approve leads 242 to 254 (13 emails), then run `send-due` at each slot from 10:20 to 16:30
  (`for t in $(seq …)` or the harness's `--run-day` option).
  Expect: 5 sent in total today (the warm-up cap), at least 10 minutes apart, none after 16:30. The
  other approved emails still read "Approved", not "Cancelled".
- *Silence never counts as a yes.*
  Do: leave one of leads 242 to 254 pending, then run
  `JURA_GROWTH_NOW=2026-11-10T16:31:00+08:00 uv run jura-growth approvals`.
  Expect: it reads "Expired", its email is cancelled ("approval expired"), and the lead isn't
  closed.
- *Audit.*
  Do: `uv run jura-growth log events --kind approval` (or the harness's equivalent).
  Expect: one event per transition above, each with who, when and the content hash.
- [ ] Pass  [ ] Fail

**A5. App idea to preview to release (must, AC-M8)**
- Expect: the APP-014 card in `#approvals` has the PRD file attached and shows the pitch, tier and
  lead types. `#app-factory` has no "approved, build …" line.
- Do: `uv run jura-growth approve <APP-014's A-id> --json`.
- Expect: the JSON carries `handoff` with `repo: "landing-page"`, the PRD path and its SHA-256.
  `uv run jura-growth apps handoffs` lists APP-014 (needs B4). Until D6, the reply tells you how to
  start the build by hand.
- Do: `uv run jura-growth apps released APP-014 --task T-0031`.
- Expect: refused, because there is no approved release (needs B3).
- Do: `uv run jura-growth apps built APP-014 --task T-0031 --preview https://uat.example.pages.dev`.
- Expect: an `app-release` card with the preview link.
- Do: skip it with `uv run jura-growth skip <its A-id>`.
- Expect: APP-014 stays on preview, and the one-pager (re-run A1's command) lists it.
- Do: `uv run python -m tests.mission_seed "$UAT" --scenario new-app-prd` (APP-015), then
  `uv run jura-growth skip <APP-015's A-id>`.
- Expect: the PRD is now in `$UAT/prd/skipped/apps/` with "Skipped by Ting Yu on 2026-11-10" at the
  top, and `uv run jura-growth apps context --json` doesn't offer that idea.
- [ ] Pass  [ ] Fail

**A6. Nothing secret or personal reaches Discord (must, AC-M10, AC-M11)**
- Do: in the UAT server, search for `re_uat`, `9Xq7Lm2P`, `jane.tan`, `9123 4567` and
  `take us off`.
- Expect: no results. Where the values were planted, the messages show `[redacted]` or the masked
  form.
- Do: `uv run jura-growth status`.
- Expect: setup gaps by name only, with no value, prefix, length or Keychain service name.
- [ ] Pass  [ ] Fail

**A7. Headless runs can't decide (must, AC-M9.3)**
- Do: `JURA_GROWTH_JOB=social uv run jura-growth approve <any pending A-id>`
- Expect: exit status 2 with a `refused:` line, and the request is still pending.
- [ ] Pass  [ ] Fail

---

## Part B: from your phone, through Dispatch

This part needs Dispatch deployed with D1 to D5, and the bot in Jura HQ UAT bound to company `jura`.
Point Dispatch at the Part A folder, or reseed it, as its setup notes say.

**B1. Check and steer the engine (must, AC-M9)**
- Do, from your phone in `#control`: `/growth status`, then `/growth one-pager`, then
  `/growth pause social looking into it`, then `/growth resume social`.
- Expect: each answers within 60 seconds. The one-pager posts in `#mission-control` and the reply
  says so. The pause shows in the next `/growth status` and is gone after the resume.
- Do: `/growth resume all` while a `PAUSE` file exists (`touch "$UAT/PAUSE"` on the Mac first).
- Expect: the reply says the PAUSE file can't be removed from Discord. Then
  `rm "$UAT/PAUSE"`.
- [ ] Pass  [ ] Fail

**B2. One tap per decision (must, AC-M4, AC-M6)**
- Do: reseed (`--scenario morning`) so the morning cards post. Tap Approve on one email card and
  Skip on another.
- Expect: each card changes in place, to "Approved by Ting Yu, hh:mm SGT" or "Skipped", and the
  buttons go away. `uv run jura-growth approvals` on the Mac agrees, with
  `decided_by = discord:<your id>`.
- Do: tap Approve twice quickly on a third card.
- Expect: one decision recorded. The second tap answers "already approved".
- Time it: approve or skip ten email cards, reading each one properly. Write down how long it took:
  ______ minutes.
- [ ] Pass  [ ] Fail

**B3. Commands that are not allowed (must, AC-M9.2)**
- Do: `/growth run social`, then `/growth schedule install`, then `/growth db`.
- Expect: each is refused, and nothing runs on the Mac.
- [ ] Pass  [ ] Fail

**B4. Only you, only in Jura's channel (must, story 25)**
- Do: have your second account tap Approve on a pending card, and type `/growth status`.
- Expect: both refused. The card stays pending.
- Do: from a TaskWise channel that Dispatch serves, type `/growth status`.
- Expect: refused, or ignored. No growth command runs.
- [ ] Pass  [ ] Fail

**B5. The Mac is asleep (should, MC D3, functional B2)**
- Do: close the Mac's lid. Two minutes later, tap Approve on a pending card.
- Expect: Dispatch replies "the growth Mac is unreachable", and the card stays pending. Open the lid
  and confirm nothing was recorded late.
- [ ] Pass  [ ] Fail

**B6. Requeue the shadow emails from Discord (should, story 24)**
- Do: `/growth outreach requeue-shadow --dry-run`, then without `--dry-run`.
- Expect: a list first, then new cards, one per requeued email, and no more open cards than the next
  two business days can send (needs B1). Nothing sends until each card is approved.
- [ ] Pass  [ ] Fail

---

## Part C: the publish queue, no browser yet

Same window and variables as Part A.

**C1. A request per item, and nothing without approval (must, AC-P1, AC-P2)**
- Expect, from the seed: one `social-post` card for Facebook, "expires Tue 10 Nov, 18:00 SGT", with
  the text, the image and the Page link. No card for LinkedIn or Instagram (still `draft`).
- Do: `JURA_GROWTH_NOW=2026-11-10T10:00:00+08:00 uv run jura-growth publish next --json`
- Expect: "nothing due".
- Do: approve the card, then run `publish next` at 08:59, then at 10:00.
- Expect: 08:59 gives nothing due (outside the window). 10:00 claims the item and prints its exact
  text and image path.
- Do: run `publish next` again at 10:15.
- Expect: nothing due (one item per platform per day, and the 20-minute gap).
- [ ] Pass  [ ] Fail

**C2. Expiry and the unknown state (must, AC-P3, AC-P10)**
- Do: reseed with `--scenario social-approved`. Run `publish next` at 18:01.
- Expect: nothing claimed, and the item reads "Expired" in `publish queue` and on its card.
- Do: reseed with `--scenario claimed-not-closed`.
- Expect: the item is `unknown`, publish is paused, `#alerts` asks you to settle it, and
  `/growth publish resolve <id> not-posted` (or the Terminal form) settles it (needs S6).
- [ ] Pass  [ ] Fail

**C3. Community posts need confirmed rules and days (must, AC-P5.6, AC-P5.7, functional B5)**
- Do: reseed with `--scenario community-plan`, which plans a G4 post for Tue 11-10 that mentions
  Jura. Approve its card, then run `publish next` at 10:00.
- Expect: refused. The rules aren't confirmed, and "promo Saturdays only" closes Tuesday for a
  promotional post.
- Do: `uv run python -m tests.mission_seed "$UAT" --scenario note-rules --group 4`.
- Expect: a `group-rules` card showing the rules text and the parsed days ("promotion only on
  Saturday"). Approve it.
- Expect: the Tuesday item is still refused, and a Saturday item for G4 is claimable on Saturday at
  10:00.
- [ ] Pass  [ ] Fail

**C4. Kill switches (must, AC-P5.9)**
- Do: one at a time, `touch "$UAT/PAUSE"`; `uv run jura-growth pause publish`;
  `publish_mode: draft` for Facebook in `$UAT/config/social.yaml`. Run `publish next` at 10:00 after
  each, then undo it.
- Expect: nothing due each time.
- [ ] Pass  [ ] Fail

---

## Part D: real posts through Chrome (blocks 2 to 5)

These post publicly on Jura's real accounts, as the PRD's own block checks require. Use test text
you're happy to leave up, or delete it by hand afterwards. You need:

- the engine's Chrome profile chosen in `/chrome`, signed in to Jura's Facebook Page, Instagram and
  LinkedIn page, and nothing else;
- a **private Facebook test group** you set up, joined as the posting identity you chose for BP open
  question 10, with written rules naming one open day;
- a **second test group** run by someone else that asks membership questions, for D5;
- the Mac awake and logged in from 09:00 to 18:00, without the frozen-clock variables. Open a fresh
  Terminal.

**D1. One approved post goes live (must, BP block 2, AC-P7, AC-P8)**
- Do: put Facebook in `browser` mode. The next morning, approve the Facebook card in `#approvals`.
- Expect: within 30 minutes after 09:00, a run update in `#social-drafts` with the live post URL.
  The post on the Page matches the card word for word, with the same image. `jura-growth social
  history` shows it published with that URL.
- Expect: your other Chrome tabs are untouched, and the run's tab is closed afterwards.
- [ ] Pass  [ ] Fail

**D2. Skip and silence don't post (must, AC-P2, AC-P3)**
- Do: on the next day, skip the Facebook card. On the day after, don't answer it.
- Expect: nothing posts on either day. The second card reads "Expired" after 18:00.
- [ ] Pass  [ ] Fail

**D3. A login wall stops everything (must, AC-P6)**
- Do: sign out of Facebook in the engine's profile, then approve that day's card.
- Expect: the run stops without typing anything. `#alerts` gives the reason and a screenshot path,
  and publish is paused. Nothing else is attempted until you sign back in and send
  `/growth resume publish`.
- [ ] Pass  [ ] Fail

**D4. The other platforms (must, BP block 3)**
- Do: repeat D1 for Instagram, on a Monday or Thursday so a carousel is tested, and then for
  LinkedIn.
- Expect: each goes live with its URL recorded. The carousel's slides are in order.
- [ ] Pass  [ ] Fail

**D5. Community post and join (must, BP blocks 4 and 5)**
- Do: confirm the test group's rules through its `group-rules` card. Approve a planned post for the
  open day, and one for a closed day.
- Expect: the open-day post goes live in the test group, with its URL in `#community`. The closed-day
  item is never claimed.
- Do: approve the join card for the second test group.
- Expect: the run clicks Join, sees the questions, submits nothing, and a second card shows the
  questions and drafted answers. Approve it. A later run submits exactly those answers.
  `jura-growth community groups` shows `requested`.
- [ ] Pass  [ ] Fail

---

## Part E: the first live outreach week

**E1. The real gate on real email (must)**
- Expect, on the first live day: every email that goes out had a card you approved. `#outreach-sent`
  lists no more than the warm-up cap (5), spread across 09:30 to 16:30.
- Do: skip one card and leave one unanswered.
- Expect: neither sends. The unanswered one is cancelled at 16:30 on the next business day.
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
  batch approval (MC open question 10), or fewer `browser` platforms.
- [ ] Pass  [ ] Fail

**E3. The morning brief line is gone (should, MC SC13)**
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

When you finish Parts A and C, close that window to drop the variables, stop the Resend stub, and
delete the `$UAT` folder.
