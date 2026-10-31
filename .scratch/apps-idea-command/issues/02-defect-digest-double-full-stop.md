# 02 — Defect: a held idea's digest line ends in two full stops

Status: ready-for-agent
Found by: QA 01, 2026-10-31, on `crew/apps-idea-command` at 6b69230
Severity: low (cosmetic, but it reaches Ting Yu every time the factory holds one of his ideas)

## What happens

When the app factory holds one of Ting Yu's ideas, the digest line reads
"App factory: your idea Site visit report wasn't picked first: A signed site visit report reads
as an official record, so it fails the no-official-documents check.."

The prompt asks the factory for the reason "in one plain sentence", so the reason will usually
end with a full stop. `digest` in `jura_growth/agents/apps/__init__.py` then adds another one.

## Steps

1. With the worktree exports and a temp data folder, add an idea:
   `jura-growth remote … -- apps idea Site visit report: write up a site visit with photos`.
2. Move to the next run's day (`JURA_GROWTH_NOW=2026-11-01T06:30:00+08:00`) and hold it:
   `jura-growth apps hold-idea site-visit-report --reason "A signed site visit report reads as an official record."`
3. Read `apps.digest(conn, "2026-11-01")["lines"]`.

## Expected

The line ends with one full stop: "…reads as an official record."

## Actual

It ends with two: "…reads as an official record.."

## Evidence

- `reviews/qa-01.md`, the factory-side case H5 and its digest output.
- Failing test: `tests/test_apps_idea_qa01.py::test_a_held_ideas_digest_line_ends_in_one_full_stop_when_the_reason_is_a_sentence`
  on branch `crew/apps-idea-command-qa01` (c456973), in the QA worktree
  `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/qa01-wt`.

## Suggested fix

Strip a closing full stop from the reason before adding one, either in `ideas._reason` (so the
stored `held_reason` and the `hold-idea` reply don't carry it) or in `digest` where the line is
built.
