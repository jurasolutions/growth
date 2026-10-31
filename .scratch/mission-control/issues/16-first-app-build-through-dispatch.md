# 16 — Ting Yu: protect app previews and run the first app build through Dispatch

Status: ready-for-human
Blocked by: 12, 14; and, outside this repo, Dispatch D6 and D8, and the `toolbox` branch of `repos/landing-page` merged into its `main`
PRD source: MC SC9, §4.8 (D6, D8, the landing page), §6 Q4 (accepted at G2: Cloudflare Access on previews before the first app build); not a §5.12 ticket, because only Ting Yu can do it
Covers: test strategy v3 §7 U8
Amended 2026-10-31: Ting Yu reversed MC §6 Q4, so previews open for anyone with no sign-in. Step 2 and the private-window check below no longer apply. See `.scratch/public-app-previews/`.

## What to do

App builds assume the toolbox at `/apps` is on `main` of `repos/landing-page`, and a Cloudflare Pages preview is public to anyone with the link, so both are settled before the first build carrying the Jura name.

1. Merge the `toolbox` branch of `repos/landing-page` into its `main` (it was unpushed as of 2026-10-24).
2. Put Cloudflare Access (your login) in front of the `*.pages.dev` branch previews of `landing-page`, as part of Dispatch's D8 onboarding.
3. Confirm Dispatch polls `apps handoffs --json` and builds each handoff on its own `claude/T-nnnn-slug` branch from `main` (D6).
4. Once it does, set `approvals.dispatch_builds: true` in `config/settings.yaml`, so decision answers say the build was handed to Dispatch instead of "Build it: …".
5. Record the checks below in `.scratch/mission-control/reviews/qa-NN.md`.

## Checks

- [ ] A preview URL opened in a private window asks for your Cloudflare login.
- [ ] **U8.** Approve one app idea: Dispatch builds it to a `landing-page` preview and the `app-release` request appears. Approve the release only after checking the preview; merge the approved SHA with the command `apps release-plan` prints, then `apps released` moves the PRD to `prd/done/apps/`.

## Pointers

- PRD: MC §4.8, §5.9, §6 Q4
- `.scratch/mission-control/reviews/tickets-technical.md`: N10
- `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U8)
- `docs/dispatch-contract.md` (from 11 and 12)
