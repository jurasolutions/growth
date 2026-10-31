# Crew log: approvals-first-social-depth

## 2026-10-31T18:50+0800 conductor (G0, G1)
status:    done
persona:   conductor
ticket:    -
artifacts: .scratch/approvals-first-social-depth/; jurasolutions/prd/pending/prd-jura-approvals-first-social-depth-2026-10-31.md
decisions: size M. G0 and G1 decided under the standing instruction ("dont ask me questions, just make the decisions and push"), not on an explicit answer; Ting Yu then said "use crew where you can"
decisions: the interview is his message plus the code and live findings in PRD §1; no new domain terms beyond CONTEXT.md except "agent feed" and "visual"
decisions: pictures are diagrams, because design-system README §4 rules out stock illustration and drawn scenes
questions: -
evidence:  uv run pytest -> 3939 passed, 41 failed on the draft (fixtures and shipped-config tests to update in tickets)

## 2026-10-31T19:30+0800 conductor (G2, G3)
status:    done
persona:   conductor
ticket:    -
artifacts: PRD §2 "Amended 2026-10-31 after the spec reviews", §5; issues/01-04
decisions: G2 and G3 decided under the standing instruction, not on an explicit answer. Every blocker in reviews/functional.md and reviews/technical.md is taken
decisions: where they differ: fence-aware split (technical B2) with images on the first piece (functional B1); decide-by 17:00 (functional B2) over wording only (technical N10); no images no card on both platforms (functional B5) over Instagram only (technical B6)
decisions: scout: no tools recommended; hashtags_max lowered to 5
questions: -
evidence:  reviews/technical.md, reviews/functional.md, scout/ read in full

## 2026-10-31T19:40+0800 conductor (test strategy taken)
status:    done
persona:   conductor
ticket:    -
artifacts: reviews/test-strategy.md
decisions: a card's "carousel": false is refused on a carousel theme (qa-lead's question, technical N8)
decisions: its 11 approval and privacy guard rewrites stay strict; 26 fixture-only failures are fixed in one place
questions: -
evidence:  reviews/test-strategy.md read by the developers through their briefs

## 2026-10-31T20:40+0800 developer (ticket 03, appended by the conductor)
status:    done
persona:   developer
ticket:    03
artifacts: crew/approvals-first-social-depth-03-schedule-drift 19d6465 d33135a; jura_growth/health.py, jura_growth/mission.py, tests/test_schedule_drift.py
decisions: largest agreeing group; on time means within DRIFT_TOLERANCE; a bad stamp is dropped and never breaks the one-pager
questions: -
evidence:  target files -> 161 passed; uv run pytest -> 41 failed (same list as baseline), 4006 passed; pyright -> 0 errors

## 2026-10-31T20:41+0800 reviewer (ticket 03)
status:    done
persona:   reviewer
ticket:    03
artifacts: reviews/code-review-03.md
decisions: approve, four should-fixes, all applied in the fix round. Live rows through mission.read gave "about 9 hours off"; a simulated restart clears it
questions: -
evidence:  see reviews/code-review-03.md

## 2026-10-31T22:10+0800 developer (ticket 01, appended by the conductor)
status:    done
persona:   developer
ticket:    01
artifacts: crew/approvals-first-social-depth-01-depth-and-pictures, through bd78cac; reviews/samples/
decisions: every figure on a card and item source label is tied to the post and sources.md; subdomain counts as a second host
decisions: conductor's ruling, round 2: in a sentence naming Jura or we/our/us, any digit fails unless it is an approved claim or the channel's allowance. Dates and product names beside Jura fail too; a run rewrites them
questions: -
evidence:  uv run pytest -> 7 failed, 4508 passed; all 7 are ticket 02's
evidence:  real Chrome, offline, full matrix -> pass; web-font matrix not rerun after the ring fix, X9 stays open for QA

## 2026-10-31T22:11+0800 reviewer and conductor (ticket 01, three rounds)
status:    done
persona:   reviewer
ticket:    01
artifacts: reviews/code-review-01.md
decisions: round 1 and 2 blockers closed: numeric forms that skipped the numbers rule, including "We helped 62 marketing teams." and "We helped 2000 small shops.", which predate this branch
decisions: round 3 blocker "A 5,000-user rollout." fixed by the conductor as the reviewer specified, no round 4; red then green on the four named sentences. Conductor also took R3-S1 (a year's shape before "of")
decisions: left open, recorded for the PR: R3-S2 "A 500-store chain." skips the card tie and passes on main too; "The 2000 shops" pinned as a known limit; a claim split over two sentences with a small count ("We help shops. 62 of them renew." with a source) relies on Ting Yu's read of the card
questions: -
evidence:  tests/test_brand_check.py -> 5 red, then 336 passed with test_social_figures.py
