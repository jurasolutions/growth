# Crew log: apps-idea-command

## 2026-10-31T20:40+08:00 conductor
status:    done
persona:   conductor
ticket:    01
artifacts: .scratch/apps-idea-command/{spec.md,issues/01-apps-idea-command.md}
decisions: G0 route S, decided under Ting Yu's standing "decide and push" instruction; the developer was already dispatched, so no second build
questions: -
evidence:  -

## 2026-10-31T21:20+08:00 developer
status:    done
persona:   developer
ticket:    01
artifacts: branch crew/apps-idea-command @ 8b34f3c; PR #17; new jura_growth/agents/apps/ideas.py, tests/test_apps_idea.py; changed remote.py, headless.py, apps/{__init__,backlog,factory}.py, prompts/app-factory.md, docs/dispatch-contract.md, docs/app-factory.md, tests/test_remote.py
decisions: refusals exit 2, duplicates exit 1; "apps idea" in headless.NEVER; added `apps hold-idea <slug> --reason` (so a failing idea stops being retried daily) and `submit-prd --idea <slug>` (so a renamed PRD still closes the row); reply counts older queued ideas
questions: -
evidence:  uv run pytest -> 4023 passed; tests/test_apps_idea.py -> 38 passed; pyright on touched modules -> 0 errors; Dispatch /growth passes free text through, no change needed

## 2026-10-31T21:55+08:00 reviewer
status:    done
persona:   reviewer
ticket:    01
artifacts: reviews/code-review-01.md (changes-requested)
decisions: B1 `submit-prd --idea` accepts any open row (renamed the invoice-builder seed row); S1 backlog writes unlocked and not atomic (rows lost under parallel calls); S2 missing YAML/mention tests; S3 ideas.clash copies backlog.find; S4 an idea failing at submit-prd is never held; nits: unused import, uncapped held_reason, colon in URL/time names, names over 60 chars, non-Latin refused, no undo for hold
questions: -
evidence:  full suite -> 4023 passed; probe tests -> 6 passed (B1 reproduced); race probe -> rows lost; security-review -> nothing at confidence 8

## 2026-10-31T22:00+08:00 conductor
status:    done
persona:   conductor
ticket:    01
artifacts: -
decisions: fix B1 and S1–S4, plus the nits: drop the import, cap held_reason, split the name only on a ": " separator, cap names at 60 chars; non-Latin text stays refused with a plain reason (slugs are ASCII); hold undo deferred as a follow-up (Ting Yu can re-add the idea)
questions: -
evidence:  -

## 2026-10-31T22:45+08:00 developer
status:    done
persona:   developer
ticket:    01 (round 2)
artifacts: crew/apps-idea-command @ 6b69230 (pushed, PR #17)
decisions: B1 --idea only for the queue head, and while the head is unheld no other PRD files; hold-idea only for the head; S1 locks.waiting around every backlog write, mkstemp + fsync + os.replace; empty --reason exits 2; held_reason truncated at 300
questions: -
evidence:  tests/test_apps_idea.py -> 71 passed; full suite -> 4056 passed (one earlier flake in test_uat_seed_outreach, which stats the live data/growth; passes alone)

## 2026-10-31T23:30+08:00 qa-engineer
status:    done
persona:   qa-engineer
ticket:    01
artifacts: reviews/qa-01.md; issues/02-defect-digest-double-full-stop.md; issues/03-defect-name-without-latin-letters.md; red tests on crew/apps-idea-command-qa01 @ c456973
decisions: drove the remote path per case as Dispatch splits it; D02 and D03 low
questions: -
evidence:  full suite -> 4056 passed; AC1–AC7 all pass; 12-way burst -> 12 rows kept; live backlog SHA unchanged; qa01 tests -> 4 red as intended

## 2026-10-31T23:45+08:00 reviewer
status:    done
persona:   reviewer
ticket:    01 (round 2)
artifacts: reviews/code-review-01.md ("Re-review 6b69230")
decisions: approve; R1 should fix (binding and hold read raw rows, context reads effective status, so a filed-but-unmarked row blocks every PRD); R2 should fix (lock timeout in mark_written after filing crashes submit-prd); nits R3–R9
questions: -
evidence:  full suite -> 4056 passed; race probes 12/20/30 -> every row kept; round-2 probes -> 8 passed, R1 reproduced; security-review -> nothing at 8+

## 2026-10-31T23:50+08:00 conductor
status:    done
persona:   conductor
ticket:    01
artifacts: -
decisions: one more developer round for QA D02 and D03 and review R1, R2, R3, R4, R6, R7, R8; R5: on a hold day `--idea` for the new head is accepted and binds, other PRDs still pass, and the PRD wording says so; R9 left (harmless untracked temp file)
questions: -
evidence:  -

## 2026-11-01T00:40+08:00 developer
status:    done
persona:   developer
ticket:    01 (round 3), 02, 03
artifacts: crew/apps-idea-command @ d4748a7 (pushed, PR #17)
decisions: D02 one full stop; D03 refused without Latin letters; R1 queue head from the effective view; R2 a lock timeout after filing answers "filed" and logs apps.backlog.mark_failed, which factory.mark_missed retries at the 06:30 precheck and the next submit-prd; R3 lock timeouts answer "refused: the backlog is busy", exit 1; R5 the new head binds first on a hold day; R6 old file mode kept; R9 left
questions: -
evidence:  tests/test_apps_idea.py -> 85 passed (13 new, red first); full suite -> 4070 passed; pyflakes and pyright on touched modules -> clean

## 2026-11-01T01:00+08:00 reviewer
status:    done
persona:   reviewer
ticket:    01 (round 3)
artifacts: reviews/code-review-01.md ("Re-review d4748a7")
decisions: changes-requested; R1–R8, D02, D03 fixed; B1 mark_missed re-marks a rested idea prd-pending for good; S1 a skip is overwritten; S2 dry run misses a pending renamed mark; S3 a slug-less hand row binds but mark_written adds a new row; N1–N3
questions: -
evidence:  full suite -> 4070 passed; B1, S1, S2, S3 reproduced by probes; security-review -> nothing at 8+

## 2026-11-01T01:05+08:00 conductor
status:    done
persona:   conductor
ticket:    01
artifacts: -
decisions: the round-3 recovery path (mark_failed / mark_missed) is the source of B1, S1, S2 and N1, N2, so remove it rather than patch it; instead submit-prd takes the backlog lock before it files anything and holds it through mark_written, so a busy backlog refuses the submit with nothing filed (exit 1) and the factory retries once in-run; fix S3 and N3. Findings converge on new code each round, so this is a decided fourth round, not a needs-human escalation
questions: -
evidence:  -

## 2026-11-01T01:50+08:00 developer
status:    done
persona:   developer
ticket:    01 (round 4)
artifacts: crew/apps-idea-command @ 725f272 (pushed, PR #17)
decisions: removed mark_failed / mark_missed; factory.submit takes backlog.locked() before filing and holds it through mark_written_held; lock timeout -> BUSY refusal, exit 1, nothing filed, no attempt used; prompt retries once then SKIP: backlog busy; S3 slug fallback; N3 _overview uses ideas.view
questions: -
evidence:  tests/test_apps_idea.py -> 90 passed (busy and slug-less tests red against d4748a7); full suite -> 4075 passed; pyflakes, pyright -> clean
