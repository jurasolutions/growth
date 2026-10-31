# He can see and steer it from Discord

Status: ready-for-agent
Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md` (read §2 and "Amended 2026-10-31 after the spec reviews", which win over anything earlier)
Reviews: `reviews/technical.md` (seams, B and N numbers), `reviews/functional.md` (F and S numbers, and its Given/When/Then table), `reviews/test-strategy.md` (name tests `IW-<criterion>` and `IW-A<n>`)
Blocked by: 03

A plug-in hook `one_pager_section(conn, since)` with the read-only connection; `Snapshot.plugin_sections`; the Replies waiting section; `COUNTED_JOBS`; `inbox list`, `redraft`, `reword`, `draft`, `done`, `unsuppress` in `remote.ALLOWLIST`, `headless.NEVER` and `docs/dispatch-contract.md`; the digest; W4 with S14; S12; retention with N6 and functional N7 (define "closes" for reported, noise and needs-you); S7's high-item alert and 24-hour repeat.

Accept: R4 between Needs you and Approvals waiting, D6 and S1 (each closes the old card and raises a new one; a claimed item refuses; a brand refusal leaves the card open), S2, R5, W4, N8, N9, S6 of the PRD. `mission.read` opens the database read-only and calls no `content()`. The contract tables match the code. R2 and S16, moved here from ticket 01 (code review 01, P-4): the one-pager shows the noise count and, for each, the sender's domain, and a Junk message's subject, from `store.noise_since`. Then CONTEXT.md's Noise entry says the one-pager lists it. `unsuppress` restores the lead's status as well as lifting the suppression, and triage's opt-out note names `/growth inbox unsuppress I-nnnn` (code review 02, SEC-2).
