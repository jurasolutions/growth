# crew-log: inbox-watch

## 2026-10-31T19:15+0800 conductor (G0, G1, G2)
status:    done
persona:   conductor
ticket:    -
artifacts: .scratch/inbox-watch/; jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md
decisions: size L, route L. Gates decided by the conductor under Ting Yu's words: "come up with a plan, implement it, and do not ask me questions", then "use crew for this". G4 stays his
decisions: the interview is his message plus the code read; PRD §6 records each decision taken for him
decisions: reactions from people go to #mission-control with their text and display name; phones and addresses stay masked (amends MC §4.4)
decisions: browser reading over Graph API, in separate read and type jobs; a new agent `inbox-browser` so a Facebook stop doesn't halt the mail
decisions: built from main in a worktree; approvals-first is in flight on its own branch and must merge beside this
questions: -
evidence:  code read: replies.py, publish/*, approvals.py, cards.py, privacy.py, remote.py, runner.py, one_pager.py

## 2026-10-31T20:05+0800 conductor (spec reviews taken, G2, G3)
status:    done
persona:   conductor
ticket:    -
artifacts: PRD "Amended 2026-10-31 after the spec reviews"; issues/01 to 06
decisions: G2 and G3 decided by the conductor under Ting Yu's instruction. Every blocker in reviews/functional.md and reviews/technical.md is taken
decisions: where they differ: F1's narrower opt-out rule over technical N7, since a real question must not suppress someone; "unsubscribe" anywhere still suppresses
decisions: B2 over QA's "computer stays allowed": the watch cannot click at all. Thinner reads are accepted, counted and reported, and checked at first run
decisions: N12 widened so Messenger replies stay possible through Business Suite's selected_item_id, guarded by F9's author check
decisions: tech lead's edges kept: 01 -> 02 -> 03 -> 04; 01 -> 05; 03, 04, 05 -> 06
questions: -
evidence:  reviews/functional.md, technical.md, test-strategy.md read in full; base suite 3982 passed (tech lead, qa lead)

## 2026-10-31 conductor (ticket 01, review rounds 1 and 2)
status:    done
persona:   conductor
ticket:    01
artifacts: reviews/code-review-01.md; issues/03, 04
decisions: opt-outs end in one closed phrase list. Any reply already cancels follow-ups, so a miss isn't chased and triage can still class it; precision wins over recall. This replaces "suppress when in doubt"
decisions: Message-ID on outreach sends goes in ticket 03, UAT confirming Resend keeps it
questions: -
evidence:  developer: 4330 passed at 92c6157; reviewer round 2: 3 blocking
