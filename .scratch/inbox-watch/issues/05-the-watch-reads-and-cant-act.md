# The watch reads the platforms and can't act

Status: ready-for-agent
Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md` (read §2 and "Amended 2026-10-31 after the spec reviews", which win over anything earlier)
Reviews: `reviews/technical.md` (seams, B and N numbers), `reviews/functional.md` (F and S numbers, and its Given/When/Then table), `reviews/test-strategy.md` (name tests `IW-<criterion>` and `IW-A<n>`)
Blocked by: 01

Prefactors first: `AuditRules` on `publish.audit` (B1); the shared `browser` lock in the runner (B6); `scope.domain_rules(platforms=None)`.

Then `inbox_browser` (thin: NAME, permissions, precheck, after_run, approval_kinds, setup_gaps; no `register`, no MIGRATIONS), the `inbox-watch` job, `prompts/inbox-watch.md` with F5's surfaces, `inbox observe --file` (with per-surface records), `inbox watch-targets` (F6), `inbox stopped`, post stats, the social half of F12, ADR 0006 and ADR 0005's amendment, `caps.BROWSER_JOBS`.

Accept: W2, W3 as amended, W5 (N2's two tellings, F7), B1's table as audit tests, B2 (argv denies `computer`), B6 (a held `browser` lock means no Claude and a quiet record, `publish` too), S3, S4 (both flags, one alert), S6, N3, N11, F13, S8. `tests/test_publish_audit.py` unchanged and green. IW-A3, A10, A13.
