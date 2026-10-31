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

## 2026-10-31 developer (ticket 01, as reported)
status:    done
persona:   developer
ticket:    01
artifacts: crew/inbox-watch-01-see-mail, merged; jura_growth/agents/inbox/; config/inbox.yaml; tests/test_inbox_*.py
decisions: closed opt-out phrase list; `auth_servers` ships empty, so an enquiry reads as an unsigned stranger with a note until UAT pins the server id (it is still reported and answered, nothing is hidden)
questions: -
evidence:  uv run pytest -> 4380 passed, no skips

## 2026-10-31 conductor (ticket 01 merged)
status:    done
persona:   conductor
ticket:    01
artifacts: crew/inbox-watch
decisions: merged after two review rounds; round 3's narrow fixes (closed rule, R-4, R-5) are checked by the final review, not a third round
questions: -
evidence:  conductor read mail.py's unsigned path: reported with a note, not noise

## 2026-10-31 conductor (correction)
status:    done
persona:   conductor
ticket:    01
artifacts: issues/03, issues/04
decisions: my merge of ticket 01 stopped on a conflict in two ticket files, my script carried on, and commit 45c3b5e closed the merge with conflict markers still in them. Local only, never pushed. Resolved here, keeping the developer's wording, which already held mine, plus the frame fingerprint check
questions: -
evidence:  grep for conflict markers across the worktree -> none

## 2026-10-31 conductor (tickets 02 and 05)
status:    done
persona:   conductor
ticket:    02, 05
artifacts: crew/inbox-watch at cb42ff3; issues/07
decisions: ticket 02 merged after one fix round, with the final review checking the fixes. Developer's pushback confirmed: a contact's own opt-out words still suppress on a failed verdict, with the doubt shown
decisions: ticket 05 reconciles onto the merge. Its publish/job.py alert question is left as is: those findings name only tools, hosts and lengths
decisions: the clean working folder extends to both inbox browser jobs; publish and the web-reading jobs are follow-up ticket 07, and Ting Yu is told
questions: -
evidence:  developer: 4770 passed at 03a71e0 (02); 4739 passed (05, before the merge)
