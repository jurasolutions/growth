# 07 — Group rules that forbid days are read as forbidding them

Status: ready-for-agent
Blocked by: -
Covers: community C-B1

## Problem

`rules.parse` turns any clause with a day into the set of allowed days, whatever the negation (`rules.py:142-145, 153-156, 162-163`):

- "No promotion on weekends." parses as promotion only on Saturday and Sunday.
- "No posts on Sundays." parses as posts only on Sunday.
- "Promotion allowed Monday to Friday. No links on weekends." parses as promotion on all seven days.

All three return `parsed = True`, so Ting Yu is never asked to confirm, and the plan offers exactly the forbidden days. The community PRD asks for no posts on a day a group's rules forbid (§5.2), and groups ban members who break them (§1).

## What to change

A negative clause without an "except" form makes its days forbidden. Mixed or ambiguous clauses come back `parsed = False`, so the existing `rules_ok` confirmation is required.

## Acceptance criteria

- The three sentences above parse to: promotion Monday to Friday; posts Monday to Saturday; promotion Monday to Friday with links not on weekends (or `parsed = False` for the third, if links can't be represented). Repro `test_negated_day_rules_are_inverted` in `audit/repro/test_verify_social_community.py` becomes a passing regression test.
- The existing table in `tests/test_community.py:133-147` still passes.
- The checklist's "Planned as" line and `days_open` follow the corrected result.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-03-social-community.md` C-B1
- `jura_growth/agents/community/rules.py`, `jura_growth/agents/community/__init__.py:222-233`, `jura_growth/agents/community/plan.py:615`
