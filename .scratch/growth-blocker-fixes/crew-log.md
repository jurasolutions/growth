# crew-log — growth-blocker-fixes

## 2026-10-24T22:20+08:00 conductor
status:    done
persona:   conductor
ticket:    -
artifacts: spec.md, issues/01-08, audit/
decisions: route bug, G0 given by the user ("yes" to fixing the nine blockers as one bug-route delivery)
decisions: no separate QA repro phase: the audit reviewers already reproduced every blocker (audit/repro/); developers start test-first from those
decisions: tickets grouped by the code they touch so parallel worktrees rarely collide; 02 waits on 01 (both change runner.claude_command)
questions: -
evidence:  uv run pytest on main 6eabfe7 -> 515 passed

## 2026-10-24T22:30+08:00 conductor (G2)
status:    done
persona:   conductor
ticket:    -
artifacts: issues/01-08
decisions: G2 opened by the user: approve tickets 01-08 (08 test hygiene included)
decisions: ticket 06: accept the company's own domain or a subdomain, or a fixed free-mail list (gmail.com, outlook.com, hotmail.com, yahoo.com, icloud.com, singnet.com.sg) published on the company's own site
decisions: ticket 04: flag number words two and above when they count a following noun; "one" and "a" on their own pass
questions: -
evidence:  -
