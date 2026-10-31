# 01: `/growth help` and `/growth pending`

Route S. Ting Yu asked for these on 2026-10-31 after approving A-0004 (the release of APP-005) and
hearing nothing further. The approval only records the decision: the release still needs
`apps release-plan`, a hand merge and `apps released`, and nothing in Discord said so. That same
night he also sent `app idea`, `apps idea` and `apps released` with the wrong words, and each was
refused. He can't see what he can send, or what is still open.

Both are new control commands in `remote.ALLOWLIST`. Dispatch passes `/growth` text through
unfiltered (Dispatch PRD AC-D2.1 and AC-D2.2), so Dispatch needs no change. A real top-level
`/help` would be a Dispatch change, and is out of scope.

## `help`

`jura-growth help`, and `help` in the allowlist. It lists every control command, built from
`remote.ALLOWLIST` so the list can't go stale.

- Give each `Entry` a one-line `summary` in plain words. Each line of output is the usage in
  backticks, then the summary. Mark the two commands only Dispatch sends (`apps built`,
  `apps handoffs`) as such in their summaries.
- Start with one line saying each is sent as `/growth <command>`, or as a plain message in
  `#control`.
- The whole text must fit `remote.TEXT_LIMIT` (1,900 characters) with no cut. `help` is itself on
  the list.

## `pending`

`jura-growth pending`, and `pending` in the allowlist. It lists growth's unfinished work, grouped
by who holds the next step, most urgent first, and says exactly what to send next.

**Waiting for you**

- Approval requests still waiting for a decision, soonest to lapse first: id, title and decide-by.
  At most 5, then "and N more: send `/growth approvals`".
- Apps approved for release that aren't released yet, each with the next step as a `/growth` command:
  - approved, not claimed: "send `/growth apps release-plan APP-005` for the merge", with the date
    the approval runs out;
  - claimed, `main` doesn't hold it: run the merge, then `/growth apps released APP-005 --task T-0001`;
  - left on the preview by a skip, an expiry or a lapse: say which, and give the preview link.
- Builds to do by hand, when `dispatch_builds` is off.
- Publish items whose outcome is `unknown`: `/growth publish resolve …`.

**Growth is on it**

- Builds handed to Dispatch and not yet reported built: app, approval, and how long ago.
- Publish items in `ready` or `claimed`: label, platform and day, capped at 5 with "and N more".
- Counts, where more than zero: outreach emails queued, social drafts for today onward, community
  posts planned for today onward.
- Ting Yu's own ideas waiting in the backlog for the app factory: how many, and the name of the next.

If nothing is open, say so plainly. Say "nothing pending" only when every source was read. A source
that couldn't be read gets its own line saying so, never a silent gap or a guessed zero (the rule in
`picture.py` and ADR 0002).

### Seams

- Add an optional plug-in hook `pending(conn) -> list[...]`, documented in `agents/__init__.py`,
  found with `getattr` like `health(conn)`, so the core never imports an agent by name. Each item
  carries who holds it and its text. One plug-in's exception becomes one line, as in
  `mission._plugin_lines`; a lock error is reported as unreadable, not as nothing pending.
- `conn` is the read model's read-only connection (`mission.open_read_only`). The command writes
  nothing to `growth.db`, and lapses by the clock without writing (ADR 0002). Only `remote`'s own
  `remote.command` event is written.
- App release states must come from one classification shared with `releases.health_lines`, so
  `pending` and the one-pager can't disagree. A request still waiting is in the approvals section, so
  don't list it twice. Reuse rather than reword where you can, but `pending` says `/growth …`,
  since it is read in Discord.
- Reading the backlog must not take its lock or write the file.
- The answer goes through `remote`'s masking and `_cut`. Order the text so the urgent part survives a
  cut, and test a long list.
- Neither command goes in a plug-in's permissions, so no scheduled run can send them. `headless`
  already refuses what isn't declared. Check that this holds, and add to `NEVER` only if it doesn't.

## Docs

- `docs/dispatch-contract.md`: rows for `help` and `pending` in allowlist order, plus the "Ticket NN
  added" note (`tests/test_remote.py` checks the rows against the code).
- `CONTEXT.md`: a glossary entry for pending work.
- `README.md`, wherever commands are listed.

## Acceptance criteria

1. `/growth help` lists every allowlisted command with a summary, under 1,900 characters after
   masking. A test fails if an entry has no summary or the text would be cut.
2. On a world matching tonight (APP-005 `built`, A-0004 approved and unclaimed), `/growth pending`
   names APP-005, A-0004, the date the approval runs out and `/growth apps release-plan APP-005`,
   under Waiting for you.
3. Each app state has a test: handed off; request waiting (approvals section only, once); approved;
   claimed and waiting for `main`; skipped; expired; lapsed; released (not listed).
4. Publish `unknown`, `ready` and `claimed`, the outreach, social and community counts, and the ideas
   line each have a test. So do the cap lines.
5. Nothing open answers plainly. A missing database, a missing table and a plug-in raising an
   exception each say what couldn't be read, and don't say "nothing pending".
6. The live state isn't changed: a test shows `pending` writes no row, and holds no backlog lock.
7. Both answer exit 0 and `recorded` through `remote --json`, in the contract's shape, and write one
   `remote.command` event. Extra words after either are refused with exit 2.
8. Scheduled runs can't send either command.
9. The full suite is green, and the voice rules hold: plain sentences, no emoji, no exclamation marks.

Do not start a third thing. The approve reply, the card wording and Dispatch's D7 promotion stay as
they are.

## Decisions

2026-11-01, after code review 01: a publish item in `claimed` whose run has ended, or that no run
claimed, is listed under Waiting for you with `/growth publish resolve`, not under Growth is on it as
this ticket lists `claimed`. No run will finish it, and `publish resolve` already accepts it.
