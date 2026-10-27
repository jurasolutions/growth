# 01 — BP-01 Ting Yu: the dedicated Chrome profile, and the spike's open checks

Status: ready-for-human
Blocked by: - (needs nothing on `main`; it touches no code and can start now)
PRD ticket: BP-01 in `prd-jura-browser-publishing-2026-10-25.md` §5.12
Covers: TY4, §4.7, §4.9, §5.1 ("Still open"); test strategy v3 §7 U9 to U11 and U18

## What to do

The publish job drives whatever Chrome profile the extension last connected to, and no code can pin it, so the profile, its sign-ins and the spike's open checks are Ting Yu's. An agent can draft the guide in step 1 when he asks; the sign-ins and checks are his. Steps marked (cost) run real Claude and spend a little.

1. The guide, drafted as `.scratch/browser-publishing/setup/browser-publishing.md` and copied to `jurasolutions/outputs/growth/setup/` by the release persona: the dedicated Chrome profile (TY4), signed in only to the Facebook account that administers the Jura Page, the Jura Instagram account and the LinkedIn account that administers the Jura company page; the Claude in Chrome extension enabled only in this profile, signed in to the same claude.ai account and organisation as Claude Code; picked once in `/chrome` → "Select browser…"; energy settings so the Mac stays logged in and awake from 09:00 to 18:00.
2. Run the four checks below and record each as pass or fail, with a note, in BP PRD §5.1 (under "The spike's answer") and in `.scratch/browser-publishing/reviews/qa-01.md`.

## Checks

- [ ] **U9.** The dedicated profile is the one picked in `/chrome`.
- [ ] **U10 (cost).** The profile is signed in to nothing beyond the three Jura accounts: not Discord, Gmail, or any TaskWise or ZenexFlow account. The spike's harmless probe with `ClaudeInChromeDomain(example.com)` and a prompt that also opens `example.org`: `example.org` is denied.
- [ ] **U11 (cost).** The locked-screen run works, and the Chrome-closed run ends `SKIP:` without hanging and claims nothing (spike setup items 1 and 2).
- [ ] **U18 (cost).** How `ClaudeInChromeDomain(<host>)` treats subdomains is recorded (for example whether a rule for `www.facebook.com` covers `m.facebook.com` and the image CDN hosts), so browser-publishing#03 can list the hosts the rule really needs.

## Pointers

- PRD: BP §4.7, §4.9, §5.1, §5.12
- `.scratch/browser-publishing/spike-headless-chrome.md` (setup items 1 and 2, the open items)
- `.scratch/mission-control/reviews/tickets-technical.md`: N3, N4
- `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U9 to U11, U18)
- `.scratch/mission-control/uat.md` Part D

## Comments

### 2026-10-27T05:59+0800 conductor

After Ting Yu records the Facebook permalink shape at R1, add it to hosts.post_problem so Facebook done-URLs are checked by path shape too (crew recommendation adopted).
