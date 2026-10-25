# 04 — BP-04 Instagram and LinkedIn

Status: ready-for-agent
Blocked by: 03
PRD ticket: BP-04 in `prd-jura-browser-publishing-2026-10-25.md` §5.12
Covers: SC1, SC7, SC9 and SC11 for the Jura Instagram account and the Jura LinkedIn company page

## What to build

The same approved-item flow that 03 proved on the Facebook Page, for the Jura Instagram account and the Jura LinkedIn company page: their hosts in the domain rules, their stop signals, their identity checks and their own live URL hosts, including Instagram's carousel days. LinkedIn goes last because it is the strictest about automation (BP §5.1).

## What to change

- Hosts for both platforms in the plug-in's explicit list, using what 01's U18 found about subdomains.
- Stop signals and identity checks for both, in their own sections of `prompts/publish.md`.
- Instagram carousel days: every image in order, as the item's content covers image bytes in order.
- `docs/social.md` for the two platforms.

## Question for Ting Yu before either platform moves to `browser`

BP §6 Q1 was accepted for while only the Facebook Page is in `browser` mode, and is to be decided again here. `config/social.yaml` has `weekends: true`, so with all three platforms in `browser` mode you get up to three approval cards on Saturday and on Sunday. *Recommended:* keep weekends on, and turn `weekends: false` (drafts stop on weekends for every platform) if three weekend cards prove too many. A per-platform weekend rule would be new scope.

## Acceptance criteria

- [ ] **AC-P1.1 (owned by 02) per platform.** With `publish_mode: browser` for Instagram, then for LinkedIn, `social submit` raises exactly one `social-post` request for that platform, with its account and URL, and its `#social-drafts` message points at the card.
- [ ] **AC-P1.3 (owned by 02), the carousel row.** On an Instagram carousel day, a change in any image's bytes or in their order supersedes the request.
- [ ] **AC-P5.1 line 1 (owned by 02) per platform.** A second item for the same platform and day is refused.
- [ ] **AC-P7.2 (owned by 02) for the new hosts.** `www.instagram.com` and `www.linkedin.com` are accepted for their own items, and the look-alikes are refused.
- [ ] **AC-P9.2 (owned by 03) for the new hosts.** One `ClaudeInChromeDomain(<host>)` rule per host of each newly enabled platform, and never a Discord host.
- [ ] **AC-P11.1 (owned by 03) for both identities.** The run checks that the page shows the Jura Instagram account or the Jura LinkedIn company page before any typing, and calls `publish stopped <id> --reason wrong-identity` on a mismatch.
- [ ] AC-M15.1 (owned by mission-control#01) still holds.

## Done when

The agent's part is done when every criterion above passes, `uv run pytest` passes, and the report is in. The ticket closes after Ting Yu's rehearsal R1, R2 and R6 on the fixture site for each new platform and live step U13 (one approved post on each, including an Instagram carousel day), recorded in `reviews/qa-04.md`. Then wait for go-ahead.

## Pointers

- PRD: BP §4.3, §4.7, §5.1 (Q5 first platform), §6 Q1
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.2 (AC-P1.3, AC-P7.2, AC-P9.2, AC-P11.1), §7 (rehearsal per platform, U13), §3 (D11 social), §11.2 row BP-04
- Code: `jura_growth/agents/publish/`, `prompts/publish.md`, `config/social.yaml`
