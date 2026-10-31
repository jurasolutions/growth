# Triage classifies and drafts, and can't reach anything

Status: ready-for-agent
Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md` (read §2 and "Amended 2026-10-31 after the spec reviews", which win over anything earlier)
Reviews: `reviews/technical.md` (seams, B and N numbers), `reviews/functional.md` (F and S numbers, and its Given/When/Then table), `reviews/test-strategy.md` (name tests `IW-<criterion>` and `IW-A<n>`)
Blocked by: 01

`caps.THIRD_PARTY_TEXT_JOBS`, the per-job timeout, `prompts/inbox-check.md` (with the customer engagement rules E1 to E6, S13, N3 of functional), `inbox pending`, `inbox submit --file`, brand channels `inbox-email` and `inbox-social`, `triage_attempts`. R1 moves to after triage, one per conversation (F8). `after_run` fails closed, rewrites the summary, and keeps a triage failure from counting toward auto-pause.

Accept: B4 (argv: scratch only, the denies, no `mcp__`), B5 rule 4, R3, F3 enforced against the model's class, S2, D8, D9, F8, F14, S15, E1 to E6 as prompt assertions and brand-channel tests, N1, N10, the opt-out class of F1. A poison item stops after 2 attempts while the next item is still handled. IW-A1, A2, A11.
