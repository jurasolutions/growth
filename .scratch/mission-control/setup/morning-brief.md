# Morning brief: remove the Jura growth line

*Mission control SC14, ticket 09. One manual edit in Cowork, about two minutes. Drafted in ticket
09; the release copies it to `outputs/growth/setup/morning-brief.md`, replacing the guide that
added the line.*

The one-pager now tells you how the growth engine is doing, every morning at 09:00 SGT in
`#mission-control` on Discord: what needs you, approvals waiting, today's runs, yesterday's figures
and spend, and the 14-day grid. The Jura growth line in the Cowork morning brief says less, a day
later, so it goes. All growth communication is now in Discord.

## Before you start

Check that the one-pager reaches `#mission-control`: run `.venv/bin/jura-growth one-pager` in
`repos/growth`, or wait for the 09:00 post. If `#mission-control` doesn't exist yet, do
`discord.md` first. Until the one-pager arrives, keep the line.

## Remove the Jura growth line

1. In Cowork, open the morning brief scheduled task and its instructions.
2. Find the Jura section, and in it the block that starts **Jura growth (one line).** It tells the
   brief to read `jurasolutions/data/growth/daily-summary.json` and print its `brief_line`.
3. Delete that whole block, up to and including "do not merge these figures into any other
   company's section."
4. Leave the rest of the Jura section as it is, and leave the TaskWise and ZenexFlow sections
   alone.
5. Save.

## What doesn't change

- The 17:30 digest still runs, still posts to `#daily-digest`, and still writes
  `data/growth/daily-summary.json`. Nothing reads that file once the line is gone, and leaving it
  costs nothing. If you ever want the line back, the old block is in this guide's history.
- The one-pager's Yesterday section repeats the digest's figure lines for the day before.

**Done when:** the next morning brief has no Jura growth line, and `#mission-control` had the
one-pager at 09:00.
