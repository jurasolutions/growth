# 04: Real Fix lines lose what to do to the three-line clamp

Status: ready-for-agent
Blocked by: none
Severity: major (test strategy criterion 8: a criterion failing; MB3). The same finding as `reviews/code-review-final.md` B1, reproduced here independently.

## What is wrong

MB3 says a Fix item is at most 3 rendered lines "and its instruction is not cut". A row holds about 114 characters. These real wordings don't fit:

- `outreach.health`: "Clear what stops live outreach, or no email is asked for: <problem>." All eight wordings of `send.live_problems()` that the test can reach run 129 characters or more, and all are cut. The row keeps the opening, which says nothing, and loses part or all of what to clear.
- `health._gap_lines`: "Set `A`, `B`, …" with four or more unset settings. The names past the cut are lost, and the names are the instruction.

`test_each_real_fix_wording_fits_its_row_whole` misses them because `PLUGIN_WORDINGS` in `tests/picture_world.py` doesn't list either line.

The message still carries each line, up to 360 characters, so a phone notification is unaffected unless the line is past the fourth. Today's committed config gets past the config-based wordings, so what can reach this in practice is a missing secret, a missing `do-not-contact.csv` or D1 settings.

## Steps

1. Render a page with `plugin_lines` holding `outreach.health`'s line, for example with `RESEND_API_KEY_OUTREACH` unset in live mode.
2. Run it through `picture_chrome.inspect`, or view the PNG.

## Expected

Each row is whole, or at least ends with what to do.

## Actual

Offline and with real fonts, the result is the same:

| Wording | Characters | Fix row |
|---|---|---|
| Buttons not set up | 294 | Cut at 3 lines |
| `legal_review_done` | 223 | Cut |
| `sending_domain` unset | 222 | Cut |
| `sending_domain` wrong | 132 | Cut |
| `RESEND_API_KEY_OUTREACH` | 129 | Cut, ends "is not set…" |
| `UNSUBSCRIBE_SECRET` | 159 | Cut |
| `do-not-contact.csv` missing | 193 | Cut, ends "/Users/tingy/OneDrive/Desktop/project…". Neither the file's name nor "create it" shows |
| D1 not configured | 168 | Cut |
| Six unset settings | 146 | Cut |

Not in this ticket, because the instruction survives: "Run `jura-growth schedule install` again. Out of date: <11 jobs>" is cut in its job list, and "Not posted to #approvals yet: <12 ids>" is cut in its ids.

## Evidence

- `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/2e83ea48-1f12-40ea-9c1c-3041ffd846ed/scratchpad/renders/outreach-fix-cut.png` (real fonts).
- `reviews/qa-01.md`, exploratory charter, E12.

## Failing tests

`tests/test_qa_01_defects.py` (uncommitted, in the feature worktree). The first builds each wording through the real `live_problems()` and `health()`:

- `test_each_real_line_about_live_outreach_fits_its_fix_row_whole` (8 cases)
- `test_every_unset_setting_is_named_on_its_fix_row`

## Comments
