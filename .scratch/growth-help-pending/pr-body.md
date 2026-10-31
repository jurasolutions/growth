## Summary

You approved A-0004 on 31 October and heard nothing further, because an approval only records the decision. Three commands sent that night with the wrong words were refused, and nothing in Discord showed what you could send or what was still open. This adds two read-only control commands.

- `/growth help` lists every control command, built from the allowlist so the list can't go stale.
- `/growth pending` lists growth's unfinished work, under "Waiting for you" and "Growth is on it", most urgent first, with what to send next.

```text
/growth pending
  remote: origin check, allowlist
    pending.read: growth.db opened read-only
      approval requests, soonest to lapse first
      each plug-in's pending(conn) hook: apps, publish, outreach, social, community
      a source it can't read gets its own line, never a guessed zero
    growth.db missing, empty or mid-write: left closed
    mask the answer, then cut from the end, so what growth holds gives way first
    write one remote.command event
```

It says "Nothing pending" only when every source was read. App release states come from one classification shared with the one-pager, so the two can't disagree. The ticket, the reviews and QA are in `.scratch/growth-help-pending/`.

## Evidence

- **Before:** on `main`, `jura-growth pending` gives `No such command 'pending'`, and nothing lists what you can send.
  **After:** on a copy of the live state, QA drove `/growth pending` through `remote --json`, with exit 0 and `recorded`:

```text
**Waiting for you**
- APP-005 Invoice builder is approved (A-0004), until Sat 14 Nov, 23:04 SGT. Send `/growth apps release-plan APP-005` for the merge.
```

  Doing what it said on that copy worked: the claim printed the merge, and `pending` then moved to the next step.

- **Suite.** On this branch at `1095412`, 4755 passed with none skipped, on Python 3.12.14, the version the engine runs, and on 3.14.7.
- **Review.** The first review asked for changes at `83b912c`, with three blocking findings. The re-reviews approved `d80d73f` and `d7d3211`. The code at the tip is the code approved at `d7d3211`.
- **QA.** QA ran at `d80d73f`, not at `d7d3211`. Its defect 02 was fixed in `d7d3211`, and the re-review covered that diff. QA's four tests for defect 02 now pass on the tip.
- **No quality gate.** This is route S, so QA and the final re-review are the evidence.

## What isn't verified

- **The real SSH hop, and how Discord renders the answers.** The origin check rightly refuses a Claude session, so QA drove `remote` in process with an SSH origin, and read the text against Discord's Markdown rules. Your first `/growth help` after the merge checks both.
- **A command pasted with its `/growth` prefix as a plain message in `#control`.** Defect 03 was closed because Dispatch PRD AC-D2.2 drops that word, but nobody has run it. Paste `/growth pending` there once. If it is refused, reopen the defect. The cost is one refused message, and the refusal lists the right words.

## After you merge

The engine runs from the main checkout, so pull there:

```bash
git pull --ff-only
uv sync
.venv/bin/python --version    # should still say 3.12
```

- There is no schedule change, since no job changed. Dispatch needs no change.
- Send `/growth help`, then `/growth pending`, then the paste above. `pending` should name APP-005 and the 14 November date.
- The next morning's one-pager should read as it did.

The full list of what to watch is in `.scratch/growth-help-pending/reviews/release.md`.

## Follow-ups outside this change

These stay open, from the reviews and QA.

- The approve reply still gives no next step. `pending` answers it when asked.
- Capitalised commands are refused, and a phone keyboard capitalises the first word of a plain message.
- While a writer is simply running, a held lock is worded as damage: "growth.db has an unfinished write. Send /growth status to clear it." It clears by itself.
- Markdown in a scraped or hand-edited name still renders. Mentions, addresses and numbers are defused or masked.
- A non-empty database file with no tables still migrates, and a second `pending` then says "Nothing pending". It takes dropped tables to get there.
- D7, Dispatch's promotion of the exact SHA `apps release-plan` hands out, stays later, so the merge is by hand until then.
- A fresh worktree's `uv sync` picks Python 3.14, since the repo has no version pin. The engine runs on 3.12.

## Merge danger

**Door:** two-way

Revert the merge commit, then `git pull --ff-only` and `uv sync` in the main checkout. There are no migrations, new settings or job changes, and the older code ran on a database made by this branch, and the reverse, with the schema unchanged. A revert leaves only the `remote.command` events for these two commands, and the review found no code that reads those events.

**Blast radius:** control path

The new commands do nothing until sent, and no scheduled run can send them. The risk is in what they share: `remote.py`'s wrapper runs for every control command, including Dispatch's poll, and the one-pager's release lines now share a classification with `pending`. Every other command still opens the database as before, and the reviewer found the one-pager's lines byte for byte equal on eleven states. If the wrapper were wrong, control commands from Discord would fail until a revert. The first poll after the pull shows that within five minutes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_019XQAhguGu7p5LYsdaiChDb
