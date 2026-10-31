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

## 2026-10-31T21:05+0800 developer and conductor
status:    done
persona:   developer, then conductor
ticket:    02
artifacts: branch crew/morning-brief-02-the-morning-order up to b08777e, merged into crew/morning-brief
decisions: conductor read the fix-round diff in place of a second review round: narrow, matches every requested change; the final review covers it again
decisions: S3 (glossary clause) and morning-brief.md:8 wait for ticket 01's merge; S4 waits for the rebase
questions: -
evidence:  full pytest -> 13 failed (ticket 01's), 4054 passed; pyright on slots.py, outreach/cli.py -> 0 errors

## 2026-10-31T21:25+0800 reviewer, then conductor
status:    done
persona:   reviewer, conductor
ticket:    01
artifacts: reviews/code-review-01.md
decisions: changes-requested, 6 blocking; all blockers go back to the developer, with S1-S7, S9 and the masked-link nit
decisions: conductor rulings: reply detection off with a count of 0 reads as 0 in the verdict, or he never gets an all-clear; the tile shows a dash. MB1 reads that way
decisions: MB10's "in full" allows the 360-character cut, which protects the 2,000-character limit; no real wording reaches it
decisions: S3: "to post by hand" counts today's drafts only, because a daily post from an earlier day shouldn't go out; match requests by date; say so in the docstring
decisions: the fix round starts by merging crew/morning-brief, so B1's install rule, the glossary, the ICP plant and test_morning_order.py are done on one tree
questions: -
evidence:  full pytest at 7ba3e5b -> 4181 passed, 0 skipped; reviewer's throwaway probes reproduced B1-B6

## 2026-10-31T22:10+0800 developer
status:    done
persona:   developer
ticket:    01
artifacts: crew/morning-brief-01-the-picture up to b0b7619, merged into crew/morning-brief; tests/test_morning_order.py
decisions: B1 stays picture-side, with Snapshot.installed_at telling a pre-install slot apart
decisions: B4: a plug-in line's first line goes on the picture; its detail stays in the message and long text
decisions: test_morning_order has two mornings, because queue tops up leftovers at 06:40, so the 08:30 job raises only when research queues nothing
questions: -
evidence:  pytest -> 4342 passed, 0 skipped; pyright 13 touched modules -> 0 errors; real fonts worst 1548 px; merge-tree with approvals-first -> conflicts only in health.py, mission.py

## 2026-10-31T23:10+0800 reviewer (final), qa-engineer, conductor
status:    done
persona:   reviewer, qa-engineer, conductor
ticket:    final
artifacts: reviews/code-review-final.md; reviews/qa-01.md; issues/03 to 08; tests/test_qa_01_defects.py (red on purpose)
decisions: all defects 03 to 08 and final B1, B2, S1 to S4, St1, St2 go to one fix round
decisions: E15: real items sort ahead of "no trace" lines, so the ICP line or a live-outreach blocker can't fall under "and N more"
decisions: S6 (copy the guides to outputs/growth/setup) goes in the after-merge steps; M1 to M4 are done at the rebase on approvals-first, whichever way the merge order falls
decisions: issue 03: the morning post must go out, or leave a clear trace, past a long lock. The developer chooses the smallest way, within Dispatch's 60-second window
questions: -
evidence:  pytest without the defect file -> 4342 passed, 0 skipped; with it -> 17 failed, 4342 passed; --live-fonts -> problems [] on 5 fixtures, all three fonts loaded; full.png and quiet.png read by the conductor
