## What you need to do, in order

Ting Yu, these are yours, and nothing changes on the Mac until you do them.

1. **Merge approvals-first first, if it's ready.** That is `crew/approvals-first-social-depth`. As this was written it isn't: it has no open PR and no quality gate. If it becomes ready before you merge this one, stop and have the crew rebase this branch on it. That rebase carries four fixes (M1 to M4 in `code-review-final.md`) and needs the full suite run again. If it isn't ready, go on to step 2. This branch works without it, but then nothing warns you if the 9-hour error in step 4 is still there.
2. **`git pull` and `uv sync`**, on `main` in `jurasolutions/repos/growth`. The jobs run from that checkout, so this is what brings the change to the Mac.
3. **`uv run jura-growth schedule install`.** Times moved and there is a new job. Until you do this, the jobs keep their old times and Fix says they're out of date.
4. **Restart the Mac once and log in, or 09:00 fires at midnight.** launchd fires every job about 9 hours early: social's 07:00 ran at 22:00, and publish's 09:00 to 17:40 ran from 00:00 to 08:40. The most likely cause is that its calendar agent kept the time zone it started with. That agent had been up since 28 September, and the Mac's zone moved to Singapore on 1 October. This is not proved, so the restart is the cure we expect and not one we've seen work. Check the first morning: if the picture arrives at midnight, the cause is something else, and the crew needs to look again. Reinstalling alone doesn't cure it. The login matters because the jobs load into your login session.
5. **Put the ICP in `jurasolutions/inputs/icp.md`**, from the draft at `jurasolutions/outputs/growth/setup/icp-draft.md`. Until that file exists, scout research stops before it writes a lead or an email, and Fix says so every morning. Outreach is in live mode, so this step is what starts new emails. Each one still waits for your Approve in #approvals.
6. **Copy the two guides.** They are the last text on the old times. From `repos/growth`:

   ```bash
   cp .scratch/mission-control/setup/discord.md .scratch/mission-control/setup/morning-brief.md ../../outputs/growth/setup/
   ```

## Summary

You asked for a clear picture of what you need to know, and for the agents to draft early so that it's all ready at 09:00. Both are here.

**The morning picture.** `#mission-control` now gets one message with one picture at 09:00 SGT, in place of the long list and the 14-day grid.

- **The first line is a verdict in words,** such as "2 to decide, 1 to fix." It also counts drafts to post by hand and replies to read. "Nothing needs you right now." appears only when all four counts are 0.
- **The sections follow the order you act on them:** Decide, Fix, This morning, Yesterday, Later today.
- **A figure the engine can't read shows a dash,** never a guessed zero.
- **A job that left no trace this morning becomes a Fix line,** so the verdict can't clear you falsely on that account.
- **The message alone is enough on a phone.** It holds the verdict, the counts, the soonest decide-by and up to four Fix lines.
- **The page is saved as `.html` beside the PNG,** in `data/growth/one-pager/`, to open on the Mac. Both are pruned after 14 days.
- **If the picture can't be drawn,** the old long text goes out and says why.
- **The grid is no longer posted.** `jura-growth one-pager --grid` draws it to a file and prints the path.
- **A long database lock no longer stops the post.** It goes out with "Not available" in place of what it couldn't read.

**The morning order.** The agents now run before the picture, so their drafts and cards are waiting for you.

| Job | Days | Was | Now |
|---|---|---|---|
| `scout-research` | Business days | 09:00 | **06:30** |
| `app-factory` | Daily | 06:30 | **07:00** |
| `social` | Daily | 07:00 | **07:30** |
| `community` | Mondays | 07:30 | **08:00** |
| `outreach-requests` | Business days | New | **08:30** |
| `one-pager` | Daily | 08:00 | **09:00** |

All times are SGT, and nothing else moves. `publish` stays at 09:00 to 17:40 and `scout-send` at 09:30 to 16:30. `outreach-requests` runs a new command, `outreach raise-due`, which raises requests for emails queued on an earlier day and posts their cards. It sends nothing, and it does nothing in shadow mode or while outreach is paused.

**A missing ICP now shows in Fix every day,** through the scout plug-in.

**Two fixes from the merge with main.** The apps idea command (#17) landed while this branch was waiting, and it merged without a conflict but still broke in two places. Its refusal of an option crashed, because this branch had changed a helper it calls, and its reply gave the app factory's old 06:30. Both are fixed in `4b926fc`. Your `/growth apps idea` reply now says 07:00.

## Evidence

**Before:** the grid was drawn with 12 to 13 px text at 1200 px, so Discord's roughly 550 px display made the words about 6 px. The action items sat among lists of timestamps.

**After:** these three renders are committed files, drawn from synthetic data with real fonts. The picture's code hasn't changed since they were drawn. The repo is private, so if a link won't open, find the file on this branch by its path.

| Render | What it shows | Size | Path |
|---|---|---|---|
| [Full](https://raw.githubusercontent.com/jurasolutions/growth/crew/morning-brief/.scratch/morning-brief/renders/full.png) | The worst case: 50 to decide, 20 to fix, the longest text | 1200×1548 | `.scratch/morning-brief/renders/full.png` |
| [Quiet](https://raw.githubusercontent.com/jurasolutions/growth/crew/morning-brief/.scratch/morning-brief/renders/quiet.png) | Nothing needs you | 1200×894 | `.scratch/morning-brief/renders/quiet.png` |
| [Bad day](https://raw.githubusercontent.com/jurasolutions/growth/crew/morning-brief/.scratch/morning-brief/renders/bad-day.png) | The database is locked: dashes and "Not available", no zeros | 1200×943 | `.scratch/morning-brief/renders/bad-day.png` |

**Tests:** the full suite gives 4481 passed, none skipped, on this branch merged with `main` at `68a1911`, on Python 3.14 and on 3.12, the version the live checkout uses. `uv run pytest -rs -q -p no:cacheprovider -o addopts=""`, temp folders only. The one commit on top of that run adds only `reviews/pr-body.md` and `reviews/release.md`.

**The real command on temp data, at the gate:**

| Case | Result |
|---|---|
| `one-pager`, normal | One message of 587 characters and one 1200 px PNG, with the `.html` beside it |
| `one-pager`, real exclusive lock held for 90 seconds | Posted, exit 0, in 48 seconds |
| `one-pager`, wrong Chrome path | The long text went out, ending "(The picture couldn't be drawn: …)" |
| `outreach raise-due`, shadow mode | Raised nothing and changed no file |

The full record is in `.scratch/morning-brief/reviews/quality-gate.md`.

## Merge Danger

**Door:** two-way, with exceptions listed under "If it goes wrong". There are no migrations, so an older checkout runs against the same `growth.db`.

**Blast Radius:** schedule.

Every morning job moves, a new job can post cards to #approvals, and your daily post changes shape. If the restart doesn't cure the 9-hour error, 09:00 keeps firing at midnight and scout research fires in the previous evening. Sending and posting windows are checked in code, so emails still can't send outside their window.

If this merges before approvals-first, M1 to M4 pass to that branch's merge, and it now conflicts with this one in seven files.

### What you accept by merging

**You have not signed any of this.** The PRD reads "not signed". The gates G0 to G3 and the quality gate's trades were ruled by the crew's conductor under your standing instruction, "dont ask me questions, just make the decisions and push". Merging is your acceptance of the PRD and of these rulings, and it is what switches the live behaviour on.

- **Sf2, a rare false "failed" line.** If a lock lands just after the post is delivered and lasts past 30 seconds, the run is left unfinished and later reads as failed. The next morning shows "Check `one-pager`: it failed", although the post went out, and adds one to the count. The alternative was risking a double post. The gate graded this minor because it errs toward looking and can't falsely clear you. A stricter reader would call it a false verdict, which is major and a no-go.
- **The pause trade under an exclusive lock.** While an `EXCLUSIVE` lock is held, the pause flag can't be read, so a paused `digest` still posts to your own channel. That covers `pause digest` and the auto-pause after three failures. The PAUSE file is checked before any lock and still stops it. An ordinary write lock no longer has this problem.
- **G1, a Fix line that can drop out.** Under a real lock with four or more other Fix lines, the lock's own line, "Send `/growth status` to clear it", falls under "and N more". The picture still says it under Decide.
- **A wording exception at the gate.** Two comment lines in `tests/test_mission_health.py` are outside the letter of criterion 6, which allows only time values. They change no assertion.
- **Two commits with no reviewer's approval.** The last approval was at `00b0ab4`. `b953955` (the pause read and wording fixes) was read in full at the gate, and `4b926fc` (the two merge fixes) was read by the conductor, with the test suite behind it.

Smaller open items, for after release: two tests weaker than their names (T1), and a misaligned row in `jura-growth status` (N1).

### Not verified

- **The picture's inline height on Discord (UAT U1).** The picture is built to stay readable at 550 px wide, on the assumption that width sets its inline size. A tall one might display smaller. No test touches Discord.
- **A real upload's time inside Dispatch's 60 seconds.** A long lock and a Discord rate limit together could pass 60, and Dispatch would then report a failure on a post that went out. This doesn't affect the scheduled job.
- **launchd firing on time,** which only the first morning after step 4 can show.
- **`outreach raise-due` in live mode through the real command.** Test doubles cover it.

### After merge: your acceptance run

UAT runs after merge, on live data, because no test can stand in for it. It doesn't gate the merge, so **a failure means revert**.

| # | Scenario | Pass when |
|---|---|---|
| U1 | The first business day's 09:00 post, on Discord desktop | One message, one picture, the verdict first, and you can read every word without opening the image |
| U2 | The same post as a phone notification | The message alone tells you what to decide and fix |
| U3 | Approve or skip a waiting card, then send `/growth one-pager` | The count drops by one and the id is gone |
| U4 | `/growth pause app-factory` the evening before | Its row reads "Skipped", Fix says how to resume, and the verdict counts it. Resume afterwards. This costs one PRD |
| U5 | A Saturday with the ICP still missing | Scout and Outreach each read "Not today", and Fix names `inputs/icp.md`. If you've already done step 5, skip this one |
| U6 | The next business day with the ICP in place | The Fix line is gone, Scout reads "Ran", and any queued email's card is in #approvals before 09:00 |
| U7 | On the Mac, open the day's `.html`, then run `jura-growth one-pager --grid` | The page scrolls to its footer, the command prints a path, and nothing posts |

### If it goes wrong

To stop one job in the meantime, use `jura-growth pause <agent>` or `jura-growth schedule uninstall <job>`.

To undo it all, revert this PR on GitHub, then on the Mac, from `repos/growth`:

```bash
uv run jura-growth schedule uninstall outreach-requests
git pull && uv sync
uv run jura-growth schedule install
cp .scratch/mission-control/setup/discord.md .scratch/mission-control/setup/morning-brief.md ../../outputs/growth/setup/
```

The first line matters. A plain `schedule install` doesn't remove a job that left the list, so `outreach-requests` would otherwise fail at 08:30 every business day. The last line puts the guides back on the old times.

A revert doesn't undo these:

- **Cards and requests already raised** stay in #approvals. They lapse or get decided as usual, and an email you approved and that was sent stays sent.
- **Posts already in Discord** stay there.
- **`picture-*.png` and `picture-*.html`** in `data/growth/one-pager/` stay, and the old backup prunes only `grid-*.png`. Delete them by hand.
- **`inputs/icp.md`** stays, so scout research keeps running. Remove the file if you want research to stop.
- **The restart** stays done, and that's harmless.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_019XQAhfz95CH5m2uYv2FLrn
