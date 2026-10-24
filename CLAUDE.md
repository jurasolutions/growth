# CLAUDE.md — repos/growth

The Jura Solutions growth engine. Headless runs (`jura-growth run <job>`) start Claude Code in
this folder, so these rules load for every scheduled agent as well as for interactive work.

## Standing rules for every agent run

- **Jura only.** Never read `taskwise-*` or ZenexFlow folders. No Notion, no Zapier.
- **Every side effect goes through `jura-growth`.** Database rows, Discord posts, PRD files,
  outreach emails, output folders. Write drafts only in your run's scratch folder
  (`data/growth/work/<job>/`), then hand them to the matching `jura-growth` command.
- **`inputs/` and `design-system/` are read-only.**
- **The brand checker is the gate.** `jura-growth check` enforces `design-system/README.md` §3.
  If an item fails, fix every reason in one regeneration. A second failure drops the item;
  don't try a third time.
- **The numbers rule.** Never write a figure Jura can't evidence: no client counts, hours saved,
  ROI or results. Only the phrases in `config/approved_claims.yaml`.
- **Never invent facts** about a company, a group, a news story or a government scheme. Record
  the source URL for everything you state.
- Finish with a one to three line summary starting `OK:`, `SKIP:` or `FAIL:`.

## For people working on the code

`README.md` covers layout, commands, tests and the plug-in interface. Agents live in
`jura_growth/agents/<name>/`; the core never imports them by name.

## Agent skills

For development work on this repo, not for scheduled runs.

Crew operating card: docs/agents/crew.md

### Issue tracker

Local markdown under `.scratch/<feature>/`; PRDs stay in `jurasolutions/prd/pending/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default roles, each label equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
