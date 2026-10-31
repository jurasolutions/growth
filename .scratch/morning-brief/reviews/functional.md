# Functional review: morning brief

PRD: `jurasolutions/prd/pending/prd-jura-morning-brief-2026-10-31.md` (lines cited as L). Read against the draft code and the 31 October render. Nothing was run. Every decision below is taken under the standing instruction, and §2 replaces the PRD's wording where they differ.

The morning order fits what Ting Yu asked for. The real gap is the verdict: the one line he reads first can say he is clear when he isn't.

## 1. Blocking

**B1. "Nothing needs you right now" can be false (MB1, L31).** The verdict counts only waiting requests and the health strip. Three things that need him reach neither:

- **A morning job that left no trace.** It reads `due` until its next slot (`slots._status`), and `health._missed` counts only `missed`. A daily job reaches Fix a day late. A missed Monday community run never does: its next slot is a week on, and by then the look-back starts the previous business day.
- **Social drafts to post by hand.** L61 keeps them in #social-drafts until the other PRD merges. They raise no request.
- **A reply from a prospect.** It is only a tile in Yesterday.

Decision: a job that didn't run becomes a Fix line. The verdict gains "N to post by hand" (drafts waiting, less waiting `social-post` requests) and "N replies to read". See MB1 and MB6 below.

**B2. The picture can state untrue figures on a bad day (MB7, L37).** MB7 covers only an unreadable figure, and these routes get past it:

- A plug-in whose digest raises loses its figures (`digest.py` L57–59), and `figures.get(key, 0)` then prints 0 (`brief.py` L84–97, L189–191).
- `snapshot.morning` being None gives "0 new leads kept".
- Empty `snapshot.slots` (a locked or unreadable database) gives "Not today, No run today" on all five rows (`brief.py` L148–149).
- With the IMAP settings unset, reply detection is off (`replies.py` L4), yet the tile says 0 replies.

Decision: see MB7 below. Reply detection off needs its own figure, because the digest can't tell it from zero.

## 2. Criteria

**Testable as written:** MB4 (every slot status has a word; no hex colour in the CSS), MB8 (a reason of `<img src=x>` shows as text; an address in a reason shows masked), MB12, MB13 (a spy on `content()` and `preview()` records no calls), SC1 (assert the job table), SC3, SC5.

| Id | Reworded |
|---|---|
| MB1 | Given 2 waiting requests and 1 Fix item, the first text on the picture is "2 to decide, 1 to fix." Given 1 draft to post by hand and 1 reply yesterday, it adds "1 to post by hand, 1 reply to read". "Nothing needs you right now." appears only when all four counts are 0. |
| MB2 | Every `font-size` on the page is at least 21 px and the PNG is 1200 px wide. Inline reading is a desktop target. On a phone, the message (MB10) is the surface and the picture is tap to zoom. |
| MB3 | The sections appear in the PRD's order. A Fix item is one list row of at most 3 rendered lines, and its instruction is not cut (see S1). A missed-slot line holds a count and no time. Requests with the same decide-by sort by id. Yesterday adds "N lapsed unanswered" when any lapsed since the last one-pager. |
| MB5 | With 0 requests and 0 fixes, the page has no gap over 100 px above the footer. With 50 requests and 20 fixes, it shows 4 of each plus "and 46 more" and "and 16 more", nothing is clipped, and the height is at most 1600 px (about 1500 is needed by my estimate from the CSS). |
| MB6 | Given a 07:30 slot with no trace at 09:00, the row reads "Didn't run", "No trace of its 07:30 run", and Fix gains a line. Within 5 minutes of its slot, it reads "Due now". With no slot today, it reads "Not today" and has no second line. |
| MB7 | A plug-in's digest raises: that row and its tiles show "–". The slots can't be read: all five rows read "Not available". Reply detection is off: replies shows "–". Yesterday can't be read: four dashes and no warning line. A recorded 0 still shows 0. |
| MB9 | After `one-pager`, `brief-<day>.png` and `.html` exist. Opened in a 1200×700 window, the page scrolls to its footer. After `backup`, files older than `one_pager_days` are gone. The draft fails both: `overflow: hidden` (`brief.py` L205) and a prune that matches only `grid-*.png` (`backup.py` L39). |
| MB10 | The message is at most 2,000 characters and holds the header, the verdict, the counts per kind, the soonest id and decide-by, and up to 4 Fix lines in full. |
| MB11 | Given a bad Chrome path, `one-pager` posts the long text ending "(The picture couldn't be drawn: …)" and logs `one_pager.brief_failed`. `--no-post` prints the long text and leaves the folder and database unchanged. |
| SC2 | Live mode, 3 emails queued, room 2: 2 requests and 2 cards, no Resend call, and a rerun adds none. Shadow mode or paused: no request, and the row reads "Ran" or "Skipped", never "Not installed". |
| SC4 | Each slot in SC1 is at least `claude.timeout_minutes` after the one before, on a Monday and on any other day. A Mac that wakes late is out of scope and reads "Still running". |
| SC6 | Saturday, `inputs/icp.md` absent: Fix names the file and what to do. File present: no such line. |
| SC7 | A search of docs, prompts and config for each job's old time finds no reference to these jobs. `CONTEXT.md` has no "14-day grid as an image" and no "08:00" for the one-pager. |

## 3. Should fix

- **S1. Fix loses its instruction (MB3, L33).** The two-line clamp fits about 76 characters by my estimate. The render already cuts "handed to Dispatc…". The first morning after merge, "Run `jura-growth schedule install` again" would be cut the same way. Decision: clamp at 3 lines, and put the action first in the short wording.
- **S2. Merge order (L23, L81).** Until the Mac restarts, 09:00 posts at midnight, and only the other PRD detects it. Decision: merge that PRD first. Check that its restart line survives `fixes()`, which keeps only an item's first line.
- **S3. Acceptance comes before any real post (L95).** Merging is both the acceptance and the switch, and he hasn't read the PRD. Decision: the PR body opens with the four after-merge steps and attaches three rendered fixtures (full, quiet, bad day). §5 runs after merge, and a failure means reverting the merge.
- **S4. A new 09:00 collision (SC4, L50).** The one-pager moves into the same minute as publish's first slot, with a 2-second read timeout (`mission.BUSY_TIMEOUT`). I did not measure how long publish holds a write. A lock would post the bad-day picture. Decision: on a lock, retry the read for up to 60 seconds before drawing.
- **S5. Language.** "Morning brief" collides with the AI OS Morning Brief, which runs at 08:00 (root `CLAUDE.md`). Use "morning picture" for the image and keep "one-pager" for the job and the post. "Fix" is the picture's name for the health strip, so `CONTEXT.md` should say so. Replace "leftovers" (L48) with "queued emails with no request". Both PRDs have an SC1, so always name which one.

## 4. Notes and edges

- **Replies lag.** They are detected only at `scout-sync`, 16:45 on business days. A Friday evening reply first appears on Tuesday's picture. Left alone, since L47 moves nothing else; this is the next schedule change to make.
- **Monday's Yesterday is Sunday,** so its sends are normally 0. This is accepted because it is accurate.
- **Early notifications.** Cards and run updates arrive from 06:30. A decision before 09:00 simply lowers the count. Muting is his setting in Discord.
- **Discord's height limit is unverified.** MB2 assumes width sets the inline size. U1 checks it; if a tall picture shrinks, lower MB5's maximum.
- **Edges.**
  - Empty and maximum: MB5.
  - Concurrent: S4. A decision made after the picture is drawn is covered by "as of" and out of scope.
  - Out of order, late wake: SC4. Drafts that land after the picture don't trigger a repost; their cards reach #approvals.
  - Permission denied: channel access is unchanged, and an unwritable folder falls back through MB11.
  - Data from before the change: moving a slot earlier keeps old runs inside its window, so there are no false misses. `outreach-requests` reads "Not installed" until its first trace, which is correct. Until `schedule install`, Fix says out of date.

## 5. UAT script

Ting Yu runs this on live data after the L81 steps. Failing any scenario means reverting the merge or sending a fix.

| # | Scenario and data | Pass when |
|---|---|---|
| U1 | The first business day's 09:00 post, on Discord desktop | One message, one picture, the verdict first. You can read every word without opening the image. |
| U2 | The same post, as a notification on your phone | The message alone tells you what to decide and fix. Note whether the picture is usable after a tap. |
| U3 | A waiting card named under Decide (if none, the first one raised) | Approve or skip it, then send `/growth one-pager`. The count drops by one and the id is gone. |
| U4 | `/growth pause app-factory` the evening before | That morning its row reads "Skipped", Fix tells you how to resume, and the verdict counts it. Resume afterwards. This costs one PRD. |
| U5 | A Saturday, with the ICP still missing | Scout and Outreach read "Not today" once each, and Fix names `inputs/icp.md`. |
| U6 | Put the ICP in place, then the next business day | The Fix line is gone, Scout reads "Ran", and any queued email's card is in #approvals before 09:00. |
| U7 | On the Mac: open the day's `.html`, then run `jura-growth one-pager --grid` | The page scrolls to its footer. The command prints a path and nothing posts. |
