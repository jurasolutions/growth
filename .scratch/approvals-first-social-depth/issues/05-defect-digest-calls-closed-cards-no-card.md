# 05: Defect: the digest and the morning brief call a closed card "no card" and "waiting"

Status: ready-for-agent
Severity: minor (wording; nothing posts and no card or feed line is wrong)
Owner: developer
Found by: QA at f0db1e5, `reviews/qa-final.md`. The final review found the same thing as its blocker SP-B1 (`reviews/code-review-final.md`), so it must be fixed before merge whatever its severity, and that review has the fix.
Failing test: `.scratch/approvals-first-social-depth/issues/test_qa_final_defects.py`, the two tests under "05"

## Steps

Run these with a temp data folder, a config copy and a frozen clock. `tests.uat.seed` is the UAT harness.

1. `uv run python -m tests.uat.seed "$UAT" --scenario base --today 2026-11-10`
2. `JURA_GROWTH_NOW=2026-11-10T10:00:00+08:00 uv run python -m tests.uat.seed "$UAT" --scenario social-day --theme ai-news --offline --today 2026-11-10`
3. `JURA_GROWTH_NOW=2026-11-10T18:05:00+08:00 uv run jura-growth digest`

## Expected

Both cards had a card, and both lapsed. The day's words say so: "Publishing: ... 2 expired" and no draft still waiting. The brief line that Ting Yu reads at 08:00 names nothing as waiting.

## Actual

The expiry itself is right: both cards read "Expired: not approved in time", two feed lines go out, and "Publishing: 0 posted, 0 skipped, 2 expired, 0 stopped" is true. In the same digest:

```
- Social: 2 drafts with no card (facebook, instagram), 0 skipped, 0 published
Jura growth, 2026-11-10: no app PRD today; community: 2 groups, 1 joined; 2 social drafts waiting.
```

- "With no card" is false: each had a card, and each card is still in #approvals.
- "2 social drafts waiting" is false, and `daily-summary.json` carries it into the next morning's brief. `figures.social_drafts_waiting` is 2. The one-pager's "Yesterday" repeats the same line.
- The same words appear in three more places:
  - An approved post claimed by a run and not yet recorded done reads "1 draft with no card (facebook)".
  - A post approved and never used reads the same.
  - A no-images day reads "2 social drafts waiting", which is false, though its "with no card" is true.

## Why

`agents/social/__init__.py` `digest()` counts every `social_posts` row with status `draft` as waiting. `_where_they_wait` then sorts them by `items.platforms_on_a_card`, whose docstring already admits the third bucket covers "a browser draft that got no card or whose card has closed".

## Note

`reviews/uat.md` S5 already records this as a known wording gap for the quality gate. This ticket gives it an owner and a test. Functional S11 and technical N11 asked the digest to say where a draft really is, and this case was left over.
