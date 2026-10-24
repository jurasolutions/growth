# Growth blocker fixes

Fix the blocking findings from the 2026-10-24 crew audit of the growth engine against its PRDs. The
fixes bring the code in line with requirements the PRDs already state; there is no new scope.

- PRDs: `jurasolutions/prd/pending/prd-jura-growth-foundation-2026-10-24.md`, `prd-jura-scout-2026-10-24.md`, `prd-jura-community-scout-2026-10-24.md`
- Audit reviews: `audit/code-review-01-foundation.md`, `audit/code-review-02-scout.md`, `audit/code-review-03-social-community.md`; machine state in `audit/infra.md`
- Reproductions: `audit/repro/` (they assert the defects; each fix turns its repro into a passing regression test under `tests/`)
- Tickets: `issues/`
