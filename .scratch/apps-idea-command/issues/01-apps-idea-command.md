# 01 — Send a toolbox app idea from Discord

Status: ready-for-agent
Route: S (gate G0 decided by the conductor 2026-10-31, under Ting Yu's standing "decide and push" instruction)

## What to change

Ting Yu has no way to hand the app factory an idea from Discord. Add a remote command,
`jura-growth remote apps idea <text>`, reachable as `/growth apps idea <text>` through Dispatch.

- It adds a row to `data/growth/app-backlog.yaml` with status `idea`, `source: ting-yu`, the text
  in `does`, a name and slug derived from the text, today's date and the actor.
- It refuses empty text, text over 500 characters, and a near-duplicate of anything in the
  registry, pending or built PRDs, the backlog or the database (the existing catalog checks).
- Its reply says the factory picks the idea at its next 06:30 run, and that the PRD comes to
  #approvals as an `app-build` card before anything is built.
- The command joins `ALLOWLIST` in `jura_growth/remote.py` and `docs/dispatch-contract.md`.
- `prompts/app-factory.md` §1: `source: ting-yu` rows are picked first, oldest first. Every check
  (rule confirmable from the official source, distance, guardrails) still applies. When one fails,
  the factory records why in the row's notes and in its OK/SKIP summary. They count against
  `prds_per_day`.

## Acceptance criteria

- [ ] `remote apps idea "<text>"` writes one `idea` row with `source: ting-yu` and replies with the
      next-run line.
- [ ] Empty, over-500-character and near-duplicate text is refused with a plain reason, and the
      backlog is unchanged.
- [ ] The text can't inject YAML, Discord mentions or extra arguments.
- [ ] The allowlist and the dispatch contract agree, and the existing allowlist parity test passes.
- [ ] The factory prompt states the priority, the unchanged checks and the failure reporting.
- [ ] The full suite passes.
- [ ] Dispatch's `/growth` passes the free text through, or the needed Dispatch change is written down.
