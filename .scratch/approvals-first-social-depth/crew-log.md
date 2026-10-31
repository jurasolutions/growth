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
