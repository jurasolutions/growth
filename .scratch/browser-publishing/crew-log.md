# Crew log: browser-publishing

## 2026-10-25T17:09+0800 business-analyst (spec draft)
status:    needs-human
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md; .scratch/browser-publishing/spec.md (pointer); .scratch/browser-publishing/crew-log.md
decisions: supersedes the "fully automatic" posting decision in .scratch/mission-control/crew-log.md (2026-10-25T17:03): Ting Yu: "posting also requires approval... so ask me on discord i will provide approval then post... same for community joining". Every social post, community post and group join (with its membership answers) needs his per-item approval in Discord; an approval expires at the end of that day's posting window
decisions: approvals arrive through Discord Dispatch; the mission-control PRD owns the general inbound mechanism; this PRD states the contract publishing needs (item_id, decision, decided_by, decided_at, source_ref) and what Dispatch must provide
decisions: outreach email is out of scope here and gated by the same Discord approval mechanism in the mission-control PRD (Ting Yu's second correction)
decisions: hard limits in caps.py (1 post/platform/day, 3 groups/week, 1 item/run, 20-min gap, 09:00-18:00 window); a claim counts against the cap (fail closed); an unclosed claim becomes "unknown", never retried
decisions: ticket 02 stands: the publish job is separate, Chrome tools only, no WebFetch; only the browser job gets an MCP server
questions: PRD §6, 13 with recommendations; Q1 waits for the spike (block 0)
evidence:  grep -> Problem..Sign-off present, closing line last; git status -> only .scratch/browser-publishing/ added in repo
## 2026-10-25T17:15:00+08:00 infra

```
status:    needs-human
persona:   infra
ticket:    -
artifacts: .scratch/browser-publishing/spike-headless-chrome.md
decisions: Folded the infra touchpoints into the spike doc instead of reviews/infra.md; this is a read-only spike with no build yet.
           Probed with the runner's exact flags plus --chrome, example.com only, about US$0.33 total.
questions: Run the locked-screen and Chrome-closed checks (spike setup items 1 and 2)? Recommended: yes, before any build ticket.
           Which Chrome profile should the engine drive? Two extension instances are connected. Recommended: a dedicated profile, picked once in /chrome.
           Confirm that an unlisted domain is denied, using a second harmless domain. Recommended: yes, before any social site goes into a ClaudeInChromeDomain rule.
evidence:  claude -p (runner flags) without --chrome -> 0 Chrome tools; with --chrome -> claude-in-chrome connected (dynamic), 22 tools
           example.com probe -> TITLE=Example Domain CLOSED=yes, denials []
           unlisted computer tool -> denied "running in don't ask mode"; navigate(url:...) param deny -> denied
           ClaudeInChromeDomain(example.com) without navigate allow -> navigate and get_page_text allowed
```

## 2026-10-25T18:07+0800 business-analyst (PRD revision for G2: reviews v2 and Ting Yu's answers)
status:    needs-human
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md; jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md; CONTEXT.md; docs/adr/0001-0005 (proposed)
decisions: one approval contract, MC §4.6 A1-A17 (A-nnnn only, claim before effect in BEGIN IMMEDIATE, human origin, revoke until claimed, decide-by/use-by, email requests due today within quota, shadow/draft raise nothing); BP §4.2 references it
decisions: TY1-TY4 recorded as decisions (Page in groups, SSH over Tailscale, shadow until buttons, dedicated Chrome profile); all 13 blocking findings and QA Q1-Q16 traced (MC §5.14, BP §5.14)
decisions: review splits settled: email use-by 3 business days (T) with A14; cards edited in place (F-S8, edits don't notify); group-rules typed days (T-B7, ticket 07); app-release claimed in apps release-plan, before the hand merge
decisions: BP-03 also blocked by MC-11a so publish resolve is reachable from Discord when unknown items first appear
questions: MC Q1 email decision times (rec yes: decide-by next business day 16:30, use-by 3rd business day); Q2 personal-data rule, no names in email bodies (rec yes); Q3 typed code in Terminal, no approvals from Claude sessions (rec yes); Q4 protect Pages previews with Cloudflare Access (rec yes); BP Q1 weekend posts (rec keep while only Facebook is in browser mode)
evidence:  grep "^## " -> sections 1-7 in both, closing line last; OQ count MC 4, BP 1; 80 + 36 ACs in Given/When/Then form; traceability grep -> 14/14 finding rows; git status -> only .scratch/, CONTEXT.md, docs/adr/ untracked

## 2026-10-25T18:43+0800 conductor (G2)
status:    done
persona:   conductor
ticket:    -
artifacts: both PRDs: Status and Signed off by lines updated
decisions: G2 opened by Ting Yu: both PRDs signed off with every recommendation (MC1 decide by 16:30 next business day, use by 16:30 third business day; MC2 no personal names in email bodies, named recipients masked; MC3 six-character code for Terminal approvals, none from Claude sessions; MC4 Cloudflare Access on previews; BP1 weekend posts kept)
decisions: route now L: tickets by the project manager, test strategy v3 by the QA lead, then tech-lead ticket review, then G3; build branches only after the blocker fixes reach main
questions: -
evidence:  -

## 2026-10-25T18:55+0800 project-manager (tickets, both PRDs)
status:    needs-human
persona:   project-manager
ticket:    -
artifacts: browser-publishing/issues/01-06; reviews/status.md; superseded-in-part notes in prd-jura-social-content and prd-jura-community-scout (§3.3); mission-control tickets and log entry alongside
decisions: 01-06 = BP-01..BP-06 with PRD edges; cross-folder edges written mission-control#01, #03, #04, #05, #11
decisions: 01 ready-for-human, on the frontier now (no code, needs nothing on main); 03-06 close only after Ting Yu's rehearsal and live steps R1-R5, U12-U15
decisions: BP-02 carries the command halves of SC6 and SC10; 03 carries the run and Discord halves
decisions: BP §6 Q1 weekend posts re-asked inside 04, as the PRD says
questions: G3 approve breakdown? rec yes; start 01 now? rec yes; weekend posts at 04? rec keep weekends on, turn off globally if too many
evidence:  render.py -> 36/36 BP ACs placed; grep -> Status, Blocked by, Pointers in all 6; git status -> no code diff

## 2026-10-25T19:16+0800 project-manager (tickets revised for the tech lead's ticket review)
status:    needs-human
persona:   project-manager
ticket:    -
artifacts: browser-publishing/issues/01-06 plus 02b (7 tickets); reviews/status.md
decisions: 02 split into 02a social (keeps 02-) and 02b community items, blocked by 02
decisions: claim.py and job.py named; 02a owns the multi-word NEVER match
decisions: 03 gains mission-control#08 for its setup_gaps() hook; NothingToDo for "nothing due"; the audit returns a failed Outcome
decisions: 06 owns pages-not-allowed for every item kind; 05 adds only the composer branch and is blocked by 06 (numbers kept for stable BP ids); 06 also blocked by 02b
decisions: U18 in 01; the guide is drafted in .scratch/browser-publishing/setup/ and copied at release
questions: G3 approve? rec yes; build on crew/mission-control? rec yes; start 01 now? rec yes; weekend posts at 04? rec keep on
evidence:  render.py -> 36/36 BP ACs placed once, exit 0
evidence:  git status -> no code diff

## 2026-10-25T19:22+0800 conductor (G3)
status:    done
persona:   conductor
ticket:    -
artifacts: issues/ (25 tickets: mc 18, bp 7)
decisions: G3 opened by Ting Yu: breakdown approved as revised; both features build on one integration branch crew/mission-control (one PR or two decided at G4)
decisions: build waits for PR #1 to merge into main; first commit on crew/mission-control adds CONTEXT.md, docs/adr/ and both feature folders
questions: -
evidence:  -

## 2026-10-25T19:31+0800 project-manager (QA lead's Q9 and Q10 ticket edits)
status:    done
persona:   project-manager
ticket:    mc 05, 09, 10b; bp 02, 02b, 03, 06
artifacts: those 7 issue files; both reviews/status.md
decisions: Q9: a sweep criterion (tests/sweep.py over the ticket's own messages) added to mc 05, 09, 10b and bp 02a, 02b, 03; X2 added to mc 05
decisions: Q10: bp 03 lists R2 and R3 explicitly, before U12 (E13); bp 06 gains AC-P11.1's join identity (wrong-identity stop, distinct from pages-not-allowed)
decisions: mc 01 and 02 (in build) not touched; no edge or frontier changed
decisions: status files now show the precondition met, G3 answered, and 01 and 02 in flight
questions: -
evidence:  render.py to a temp folder -> MC 80/80, BP 36/36 placed once, exit 0
evidence:  cmp -> exactly the 7 named tickets differ
evidence:  git diff --stat -> 7 issue files, 11+/3-, no code
