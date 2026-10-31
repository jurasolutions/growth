## Summary

Ting Yu can now send a toolbox app idea from Discord, and the app factory picks it before any other candidate at its next 06:30 run. Before this, the factory only chose from its own seed backlog and the scout's leads.

### The command

Type it in Discord, in the control channel:

```
/growth apps idea <text>
```

For example:

```
/growth apps idea Site visit report: write up a site visit with photos and a signature, and save it as a PDF
```

The reply reads:

```
Added to the app backlog:
  name    Site visit report
  slug    site-visit-report
  status  idea (source: ting-yu, added 2026-11-01 by discord:<id>)
  does    Site visit report: write up a site visit with photos and a signature, and save it as a PDF
The app factory picks it at its next run (06:30 SGT).
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

When older ideas of his are still waiting, the second line says how many come first instead.

- The name is the text before the first ": " (a colon and a space), or else its first few words, at most 60 characters. It needs Latin letters, because it becomes the tool's web address. The text itself is kept word for word in the row's `does`.
- The command refuses empty text, more than 500 characters, a name with no Latin letters, and any word that reads as an option, such as `--source` (exit 2). It also refuses a name or slug that clashes with anything live, pending, built or already in the backlog, and the reply names the clash (exit 1).
- If another command is writing the backlog for 30 seconds, it answers "refused: the backlog is busy" and writes nothing. Send it again.
- It is not a decision and needs no approval. It writes one backlog row and nothing else. No scheduled run can send it (`headless.NEVER`).

### What the factory does with an idea

```text
/growth apps idea <text>                    (Dispatch -> bin/growth-remote -> remote.py ALLOWLIST)
  apps idea -> app-backlog.yaml row          status: idea, source: ting-yu, under the backlog lock

06:30 app-factory run
  apps context --json                        ting_yu_ideas, oldest first
  take the first idea, before weighing anything else
    checks still apply                       official rule confirmed today, no near-duplicate, no excluded kind
    passes -> write the PRD, maybe under a plainer name
      submit-prd --idea <slug>               files the PRD, marks his row, raises the app-build card
    fails  -> apps hold-idea <slug> --reason "…"
      the reason goes in the row's notes, the digest and the run's OK or SKIP line
      the idea stops coming first; the factory falls back to the normal pick
```

- While his oldest idea waits unheld, `submit-prd` refuses any other PRD, so the factory can't quietly pass over it.
- A real `submit-prd` takes the backlog lock before it files anything and holds it until his row is marked. If the backlog stays busy, nothing is filed and no attempt is used. The factory retries once, then finishes with `SKIP: backlog busy`.
- His ideas count against the one PRD a day like any other.

### What stays gated

- **The PRD card.** Every idea still becomes a PRD that comes to #approvals as an `app-build` request. Nothing is built until Ting Yu approves it there.
- **The build approval.** A handed-off build still raises an `app-release` request, bound to its commit, before anything reaches the site.

This follows the amendment of 2026-10-31 to `prd/pending/prd-jura-app-factory-2026-10-24.md` §5.6.

### Dispatch

No change is needed. `/growth` passes Ting Yu's text through unfiltered, and Dispatch splits it on whitespace after `--`. Growth's `ALLOWLIST` is the gate. If Dispatch keeps its own copy of the command list for help text, adding `apps idea` to it is optional.

## Evidence

- **Before:** `/growth apps idea …` answered "refused: `apps idea` isn't a control command" (exit 2), and the factory had no way to tell Ting Yu's ideas from its own.
  **After:** the command adds the row and the factory takes it first.
- `tests/test_apps_idea.py`: 90 tests. They cover the row's shape, how the name is made, the 500 and 501 character limits, the refusals, duplicates, YAML and mention text, 12 parallel senders with no row lost, the queue head and `--idea` binding, holds and the digest line, the busy-backlog refusal, and the prompt contract.
- `tests/test_remote.py`: the allowlist and `docs/dispatch-contract.md` agree, row for row.
- Full suite, with this branch merged with current `main` (f9a9ad6), without committing the merge: **4075 passed** in 334s (`uv run pytest -q -rs -p no:cacheprovider -o addopts=""`, worktree exports, temp data and outputs).
- QA drove every case the way Dispatch does (`shlex.join`, then `shlex.split`, a fresh process each time) and the real `bin/growth-remote`. Every acceptance criterion passed, and the live backlog was unchanged. The two low defects QA found, a doubled full stop in the digest and digit-only names, are fixed.
- Code review took four rounds. The feature folder is in `.scratch/apps-idea-command/`.

## Merge Danger

**Door:** two-way

Revert the merge commit. The command and the factory's priority go with it.

**Blast Radius:** app-factory

The change touches only the app factory's backlog, its prompt and the remote allowlist. There are no migrations, no config changes and no new environment variables. A revert leaves behind what was already written:

- Rows added with `source: ting-yu`, including any `held` and `held_reason` fields, stay in `data/growth/app-backlog.yaml`. The older code reads them as ordinary ideas. Delete one by hand if you don't want it.
- PRDs already filed from his ideas, and their `app-build` cards, stay. Skip a card in #approvals as usual.
- The `apps.idea.added` and `apps.idea.held` events stay in `growth.db`, which is append-only.
- `data/growth/locks/app-backlog.lock` stays. It is harmless.

To stop the factory meanwhile, without a revert: `jura-growth pause app-factory`.

## After merge

On the Mac, in `jurasolutions/repos/growth`, outside the 06:30 run:

```
git switch main
git pull --ff-only
uv sync
```

The job list and the times are unchanged, so `jura-growth schedule install` isn't needed. The next 06:30 run uses the new prompt.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
