# 03 — Defect: a name with no Latin letters is accepted

Status: ready-for-agent
Found by: QA 01, 2026-10-31, on `crew/apps-idea-command` at 6b69230
Severity: low (the factory may rename the idea, but the row, its slug and the reply break the documented rule)

## What happens

`docs/dispatch-contract.md` says `apps idea` exits 2 for "no Latin letters in the name", and PRD
§5.6 (amended 2026-10-31) says the name is "in Latin letters". The code only refuses a name whose
slug comes out empty, so a name made of digits, or a Discord mention, is added:

- `/growth apps idea 2026: a planner for next year` adds the name "2026" with the slug `2026`.
- `/growth apps idea <@123>: ping the owner` adds the name "<@123>" with the slug `123`.
- `/growth apps idea 123 456` adds the name "123 456" with the slug `123-456`.

The mention is defused in the reply, and the digest posts with no mentions allowed, so nobody is
pinged. The problem is the rule, not a ping.

## Steps

1. With the worktree exports, a temp data folder and the live backlog copied into it, send
   `jura-growth remote --actor discord:<control id> --json -- apps idea 2026: a planner for next year`
   (the SSH origin passed in process, as in `tests/test_remote.py`).
2. Read the reply and the backlog.

## Expected

Exit 2, a reply starting `refused:` that says the name needs Latin letters, and the backlog unchanged.

## Actual

Exit 0, "Added to the app backlog", and a new row named "2026" with the slug `2026`.

## Evidence

- `reviews/qa-01.md`, exploratory cases R7, R11 and the transcript under them.
- Failing test: `tests/test_apps_idea_qa01.py::test_a_name_with_no_latin_letters_is_refused_as_the_contract_says`
  (three cases) on branch `crew/apps-idea-command-qa01` (c456973), in the QA worktree
  `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/qa01-wt`.

## Suggested fix

In `ideas.add`, refuse when the name has no character in `[A-Za-z]`, with the existing "the name
needs Latin letters" reply. If digits-only names should stay allowed, change the contract and
PRD wording instead; that is the developer's call to raise.
