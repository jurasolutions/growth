# Crew log: morning-brief

## 2026-10-31T19:15+0800 conductor (G0, G1)
status:    done
persona:   conductor
ticket:    -
artifacts: .scratch/morning-brief/; jurasolutions/prd/pending/prd-jura-morning-brief-2026-10-31.md
decisions: size M. G0 and G1 decided under the standing instruction ("dont ask me questions, just make the decisions and push"), not on an explicit answer; Ting Yu said "use crew for this" after a first draft of the picture was already written
decisions: new terms go in CONTEXT.md: "morning picture"; "One-pager" entry to be updated by ticket 02
decisions: drift check, digest move and social cards are left to crew/approvals-first-social-depth, in flight in another session
questions: -
evidence:  rendered the draft from live growth.db read-only -> 1200x1120 PNG, readable; three defects noted in PRD MB5, MB6, SC6

## 2026-10-31T19:40+0800 conductor (G2, G3)
status:    done
persona:   conductor
ticket:    -
artifacts: PRD note "Amended 2026-10-31 after the spec reviews"; issues/01, issues/02
decisions: G2 and G3 decided under the standing instruction, not on an explicit answer. Every blocker in reviews/functional.md and reviews/technical.md is taken
decisions: name is "morning picture" (picture.py), so it doesn't collide with the AI OS Morning Brief. The feature slug and PRD file keep "morning-brief"
decisions: one-pager's verdict counts drafts to post by hand and replies to read, so it can't falsely clear him
decisions: merge order: approvals-first first if it is ready; this branch stays mergeable either way
decisions: scout: no tools recommended
questions: -
evidence:  reviews/functional.md, technical.md, test-strategy.md read in full

## 2026-10-31T20:10+0800 developer
status:    done
persona:   developer
ticket:    02
artifacts: branch crew/morning-brief-02-the-morning-order; ec5e32b, 94415fd, 1ec5e44, f3c72a9, 61e6657
decisions: test_mission_health.py golden times changed because status prints live settings; this breaks test-strategy criterion 6, taken by the conductor
decisions: tests/test_morning_order.py left to the conductor; test_morning_schedule.py pins digest at 17:30, approvals-first must update it
questions: -
evidence:  full pytest -> 13 failed (ticket 01's), 4048 passed, 0 skipped; pyright on 5 touched modules -> 0 errors

## 2026-10-31T20:30+0800 reviewer
status:    done
persona:   reviewer
ticket:    02
artifacts: reviews/code-review-02.md
decisions: changes-requested: B1 stale 08:00 lines; S1 hand run while paused posts a pending card
decisions: departure: a probe called schedule.render() on a throwaway copy despite the brief; conductor checked LaunchAgents and the main checkout, unchanged
questions: -
evidence:  full pytest 61e6657 -> 13 failed (ticket 01's), 4048 passed, 0 skipped

## 2026-10-31T20:32+0800 conductor (review 02 taken)
status:    done
persona:   conductor
ticket:    02
artifacts: reviews/test-strategy.md lines 69 and 91 amended (S2)
decisions: B1, S1 and N2 (min(since, now)) back to the developer; SC3 comment nit too. N1 stays as T-B5 accepted it
decisions: S3 (glossary clause) and the grid wording in discord.md and settings.yaml go to ticket 01's merge; S4 goes to the rebase
questions: -
evidence:  ls and stat on ~/Library/LaunchAgents -> plists still dated Oct 29; launchctl list -> 11 jobs

## 2026-10-31T20:50+0800 developer
status:    done
persona:   developer
ticket:    01
artifacts: branch crew/morning-brief-01-the-picture: c580ad4, 137a774, 77f6206, 0e58ed0, 7ba3e5b; jura_growth/picture.py; tests/test_picture*.py, picture_world.py, picture_chrome.py
decisions: reply detection off counts 0 in the verdict, else no all-clear ever; the tile shows a dash
decisions: an unknown count says "Nothing to decide or fix, but some figures couldn't be read."
decisions: "Didn't run" also skipped when not installed; message Fix lines cut at 360 characters
questions: -
evidence:  pytest -> 4181 passed, 0 skipped; 22 mutants, 21 caught; real fonts worst 1548 px, before the last edits, QA re-records
