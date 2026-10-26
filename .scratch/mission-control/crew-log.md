# crew-log — mission-control

## 2026-10-24T22:05+08:00 skill-scout
status:    done
persona:   skill-scout
ticket:    -
artifacts: scout/markdown-it-py.md, scout/jinja2.md, scout/pytest-playwright.md, scout/baseline-and-rejected.md
decisions: markdown-it-py 4.2.0 recommend with conditions (Medium; MarkdownIt("js-default") only); Jinja2 3.1.6 don't recommend (High floor, repo already escapes with html.escape); pytest-playwright 0.10.0 don't recommend (High; reuse render.py headless Chrome); stdlib baseline for serving, templating, email isolation (sandbox CSP + iframe), tests
questions: allow Google Fonts in the shell CSP? rec yes, never on the email route; add markdown-it-py as the one new runtime dependency? rec yes, with the card's conditions
evidence:  scan.mjs -> markdown-it-py Medium, mdurl Low, Jinja2/MarkupSafe/playwright High; wheels sha256 match PyPI; OSV clean for pinned versions; Chrome probe -> sandbox CSP blocks script; foreign Host -> 421

## 2026-10-24T22:35+08:00 conductor (G0, interview round 1)
status:    done
persona:   conductor / business-analyst
ticket:    -
artifacts: CONTEXT.md (Agent, Job, Slot, Run, Quiet run, Slot status, Artifact, Transcript, Mission control, Health strip)
decisions: G0: size M, route M (user confirmed)
decisions: Q1 live local server via a `jura-growth` command, reads growth.db fresh on every load
decisions: Q2 view-only in v1; show the CLI command to copy where an action applies
decisions: Q3 127.0.0.1 only; no login
decisions: Q4 slot status vocabulary as in CONTEXT.md; scout-send collapsed to one row per day; record a quiet-run trace so ran-with-nothing-due differs from missed
decisions: Q5 home = today board + 14-day job-by-day grid; drill to day, then run; full DB history; "transcript pruned" after 30 days
decisions: Q6 run pages show status, error, duration, cost, denials, events, readable transcript, and every artifact type; plus cross-run Emails, Posts and PRDs lists; HTML email bodies sandboxed
decisions: Q7 health strip as listed, sharing logic with `jura-growth status`
questions: round 2 pending (lifecycle, refresh, fonts, markdown dependency, transcript redaction, width)
evidence:  -

## 2026-10-24T22:57+0800 conductor (note)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: conductor headings before this entry carry estimated times, some ahead of the real clock; from here on they come from the system clock
questions: -
evidence:  date -> 2026-10-24T22:57+0800

## 2026-10-25T01:43+0800 tech-lead (interview round 2, delegated by Ting Yu)
status:    done
persona:   tech-lead
ticket:    -
artifacts: reviews/round-2-decisions.md
decisions: Q8 on demand only in v1, fixed port in settings.yaml; always-on can follow as one ticket. Q9 meta refresh 60s (script-src 'none' stays). Q10 Google Fonts in shell CSP only. Q11 markdown-it-py==4.2.0 js-default, redact before parsing. Q12 reuse ticket 01 config.redact()/secret_values(). Q13 desktop layout, works at 360px
decisions: PRD carries one runner write (run.quiet event); classifier reads the JSONL mirror for PAUSE and lock skips; branch only after blocker fixes 01, 03, 08 merge
questions: -
evidence:  code read db.py:20-28, runner.py:79-83,111-114, schedule.py; mode=ro vs hot journal per SQLite docs, untested -> PRD test must cover the stale-journal case

## 2026-10-25T15:00+0800 conductor (G1)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: G1 opened by Ting Yu: requirements ready, write the PRD, tech lead's round 2 decisions stand (Q8 on demand only in v1)
questions: -
evidence:  -

## 2026-10-25T15:05+0800 business-analyst (spec draft)
status:    needs-human
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md; .scratch/mission-control/spec.md (pointer); CONTEXT.md (Install state, Setup gap; "not installed" widened per C3; health strip items aligned)
decisions: PRD in foundation-PRD format; 13 success criteria each traced to Q1-Q13 or C1-C6; constraints C1-C6 carried in full (§4.2-4.8); 3 tracer blocks: slots end to end, runs and artifacts, health strip
decisions: dependency state recorded: 03 and 08 merged on crew/growth-blocker-fixes, 01 in fix round 1, none on main, so mission control stays blocked per C5
questions: PRD §6, each with a recommendation: port (8765, no fallback); scout-send day cell (worst status wins); new slot status "due" for a past slot whose window is still open; health-strip windows; "Posts" = social_posts + community_posts; email-to-run link via leads.run_id / sent_at window, no migration; slots of an unloaded job that has history; Keychain resolved once at server start
evidence:  grep sections -> Problem..Sign-off present, closing line last; python check -> 13/13 criteria traced, 19/19 stories with actor, benefit, trace; git status -> only .scratch/mission-control/ and CONTEXT.md touched in repo

## 2026-10-25T16:56+0800 qa-lead (test strategy)
status:    done
persona:   qa-lead
ticket:    -
artifacts: reviews/test-strategy.md
decisions: 13 criteria -> 62 coverage rows + 7 runner rows, six test datasets, 11 judgement-free exit criteria, manual checks U1-U6; seams S1-S8 from round-2 C6 / PRD 4.8 (technical.md pending); hot-journal fixture must prove it's hot; browser tests assert the page loaded; redaction swept per route raw, escaped and URL-encoded; Chrome-missing skips count as not run
questions: Ting Yu's everyday browser? rec: if not Chrome, run U6 in it and accept the Safari gap at G4
evidence:  uv run pytest -rs on crew/growth-blocker-fixes -> 693 passed, 0 skipped

## 2026-10-25T17:03+0800 conductor (scope change from Ting Yu)
status:    done
persona:   conductor
ticket:    -
artifacts: reviews/technical.md (tech lead, written against the local-page PRD; its B1-B4 are moot under the new scope)
decisions: Ting Yu: all communication between the automation and him goes through the Discord app
decisions: mission control is Discord only: a one-pager posted to Discord, plus scout, social, community and app-factory posting a status update to Discord on every run; the local web page is dropped (round 1 Q1-Q3, Q5 and round 2 Q8-Q13 superseded where they assume a local page)
decisions: inbound (Ting Yu -> automation) reuses Discord Dispatch rather than a Jura bot
decisions: social and community posting goes out fully automatically through the Chrome extension (Claude in Chrome) on Ting Yu's logged-in accounts; Ting Yu was told Meta and LinkedIn terms prohibit unapproved automation and that account restriction is a risk he accepts
decisions: functional review of the local-page PRD stopped as obsolete; PRD to be rewritten; browser posting gets its own PRD; a read-only spike checks whether a scheduled claude -p run can drive Claude in Chrome
questions: -
evidence:  -

## 2026-10-25T17:05+0800 conductor (approvals correction from Ting Yu)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: supersedes "fully automatic" posting: every social post, community post and community group join is sent to Discord and happens through Chrome only after Ting Yu approves that item
decisions: app factory sends the app idea to Discord; only on approval is it developed and pushed to the landing page (where it is pushed is an open question; rec a branch/dev preview, production as a separate approval)
decisions: outreach email sending needs no approval (unchanged)
decisions: both PRD drafters told; mission-control PRD owns the general Discord approval mechanism via Dispatch, browser-publishing PRD references it
questions: -
evidence:  -

## 2026-10-25T17:06+0800 conductor (email approval correction from Ting Yu)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: supersedes "emails need no approval": outreach emails also wait for Ting Yu's approval in Discord; send-due sends only approved, unexpired emails, with all code caps still applying; supersedes scout PRD §1, SC2, §5.3 automatic sending
questions: -
evidence:  -

## 2026-10-25T17:13+0800 business-analyst (PRD rewrite, Discord scope)
status:    needs-human
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md (rewritten in place); CONTEXT.md (Mission control and Health strip redefined; One-pager, Run update, Approval request, Approval kind, Gated action, Control command added)
decisions: local page dropped; kept classifier, quiet-run trace (B3, N2-N4), read-only read model, redaction plus Keychain masking (B2), names-only setup gaps
decisions: approvals are core: A-nnnn record bound to a content hash, used once in the gated action's own transaction, per-kind expiry, append-only events; plug-ins declare kinds; headless runs can never decide
decisions: Ting Yu addition logged: social posts, community posts, group joins and app builds need approval; browser-publishing PRD registers its three kinds against §5.4
decisions: Ting Yu correction logged: outreach emails need approval too; scout PRD §1, SC2, §5.3 superseded; shadow needs none; live mode refuses until the gate ships; unapproved email cancelled at 16:30 next business day
decisions: inbound only through `jura-growth remote` allowlist; Dispatch dependencies D1-D8 listed, not designed
questions: 21 in PRD §6, each with a recommendation. Key ones: Q12 app builds go to landing-page `dev` preview, production a second approval, and who promotes (Dispatch v1 excludes it); Q14 SSH forced-command transport to the Mac; Q8 Terminal fallback for approvals (yes)
evidence:  grep "^## " -> sections 1-7 present, closing line last; python check -> 26 stories with actor and benefit, 14 criteria, each traced (TY/Q/C/brief/Dispatch); git status -> only .scratch/ and CONTEXT.md in repo

## 2026-10-25T17:24+0800 functional-lead (both PRDs)
status:    needs-human
persona:   functional-lead
ticket:    -
artifacts: reviews/functional.md (rewritten), uat.md (rewritten, both PRDs)
decisions: 5 blocking, 17 should-fix, 11 notes. B1 approved emails expire behind warm-up caps (split decide-by/use-by, throttle requests to send capacity); B2 the two PRDs disagree on the approval contract; B3 per-app release can't be gated on a shared dev branch; B4 approved app builds have no builder before Dispatch D6; B5 nothing confirms community open days from Discord, so no post is ever claimable
decisions: approval load at current caps: 19-37 decisions per business day, up to 44 Mondays, 4-6 weekend days; workable with buttons, not typed commands
questions: B1 split expiry and throttle? rec yes; S7 mask named recipients, no personal names in email bodies? rec yes; S17 hold live outreach until Dispatch buttons? rec yes; BP Q10 group identity: Ting Yu decides explicitly
evidence:  33 findings; UAT 25 steps; recommended answers to MC Q1-21 and BP Q1-13 in functional.md

## 2026-10-25T17:24+0800 qa-lead (test strategy v2, both PRDs)
status:    needs-human
persona:   qa-lead
ticket:    -
artifacts: reviews/test-strategy-v2.md
decisions: one strategy for both PRDs; 20-case approval-gate matrix across all 7 kinds; headless self-approval tested at 5 layers; network guard; Discord double on .invalid URLs; fake claude binary for the publish job; real Chrome only on localhost fixture pages as Ting Yu's manual rehearsal; exit criteria per block; suite floor 975
questions: Q1 tech lead re-reviews seams for Discord scope (rec yes); Q2 Ting Yu types A-nnnn ids; Q3 skip after an approval allowed until used; Q8 publish checks Chrome before claiming; Q4-Q16 in §12
evidence:  uv run pytest -rs @9c2611b -> 975 passed, 0 skipped

## 2026-10-25T17:54+0800 tech-lead (technical review v2, both PRDs) and conductor (Ting Yu's answers)
status:    needs-human
persona:   tech-lead / conductor
ticket:    -
artifacts: reviews/technical-v2.md
decisions: tech lead B1 approvals.use is a claim inside BEGIN IMMEDIATE before the outward effect; B2 decisions need a human origin (TTY + typed code, or sshd parent; never a claude ancestor); B3 transport SSH forced command; B4 approval state only in approvals, A-ids only, revoke until claim; B5 email requests only for emails due today within remaining quota, separate decide-by and use-by; B6 one-pager in NEVER refuses the 08:00 job; B7 group-rules approval vs ticket 07 typed days; B8 Chrome scope only via ClaudeInChromeDomain rules, --chrome limited by caps.BROWSER_JOBS; build order MC-01..MC-11b, BP-01..BP-06; ADRs 0001-0005
decisions: Ting Yu: community group posts as the Jura Facebook Page where groups allow Pages; skip groups that only allow personal profiles
decisions: Ting Yu: Dispatch reaches the Mac by SSH forced command (Remote Login + Tailscale); Dispatch never runs on the Mac
decisions: Ting Yu: outreach stays in shadow mode until Dispatch Approve/Skip buttons work
decisions: Ting Yu: the posting job drives a dedicated Chrome profile signed into only the Jura social accounts, extension enabled only there
questions: -
evidence:  tech lead: pytest @dacf740 -> 975 passed; probe may_use one-pager in NEVER -> refused (B6)

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

## 2026-10-25T18:54+0800 qa-lead (test strategy v3, both signed-off PRDs)
status:    done
persona:   qa-lead
ticket:    -
artifacts: .scratch/mission-control/reviews/test-strategy-v3.md
decisions: one row per AC (80 MC, 36 BP) with level, seam, data and ticket; 15 supporting rows from constraints (X1-X15)
decisions: gate matrix keyed to MC §4.6 A1-A17: G1-G36 (G4a/G4b two clocks, G17 skip wins until claimed, G12 consistency check, G21-G24 claim before effect, G13 layer 5 real-process origin tests)
decisions: seams agreed with technical-v2; added S13 real origin and S14 bin/growth-remote; fake origin in-process only (env/flag fake is critical)
decisions: exit criteria E1-E14 at every gate plus a per-ticket table MC-01..MC-11b, BP-01..BP-06; suite floor 987; E14 keeps live outreach off until U17
questions: tech lead Q1 precheck writes run.quiet (rec yes), Q6 approvals.dispatch_builds flag (rec yes), Q7 landing-page path override (rec yes); PM Q2 network guard in MC-01, Q3 trace cross-ticket rows at the later ticket, Q4 AC-M12.2 in MC-06, Q5 digest counts in BP-02; functional lead Q8 refresh uat.md. None need Ting Yu
evidence:  uv run pytest -rs @1662793 -> 987 passed, 0 skipped; git status --short unchanged before/after
evidence:  python AC check -> MC 80/80, BP 36/36 rows, sets equal to the PRDs; 37 matrix rows (G1-G36 with G4a/G4b)

## 2026-10-25T18:55+0800 project-manager (tickets, both PRDs)
status:    needs-human
persona:   project-manager
ticket:    -
artifacts: mission-control/issues/01-16; browser-publishing/issues/01-06; both reviews/status.md; superseded-in-part notes in prd/pending scout, app-factory, growth-foundation, social-content, community-scout; jurasolutions/CLAUDE.md folder map (prd/skipped/)
decisions: tickets 01-12 = MC-01..MC-11b, BP 01-06 = BP-01..BP-06, PRD edges unchanged; cross-folder edges as mission-control#NN
decisions: 4 ready-for-human MC tickets (13 Discord channels + U1-U5, 14 SSH/Tailscale + U7, 15 buttons then live outreach, 16 previews + first app build)
decisions: every PRD AC copied verbatim by script (80 MC, 36 BP, none unplaced); split ACs say which ticket checks the rest
decisions: four order-independent pairs (03/04, 05/11, 08/10, 09/11): the second to land carries the shared test, so no new edges
decisions: foundation PRD noted too (MC §4.9 names it)
questions: G3 approve breakdown after QA v3 and tech-lead ticket review? rec yes; start BP-01 before main? rec yes; BP-04 weekend posts? rec keep weekends on
evidence:  render.py -> 80/80 MC, 36/36 BP ACs placed; grep -> 22 tickets with Status, Blocked by, Pointers; git status -> only .scratch/, CONTEXT.md, docs/adr/ untracked, no code diff

## 2026-10-25T19:08+0800 tech-lead (ticket review, both features)
status:    needs-human
persona:   tech-lead
ticket:    -
artifacts: .scratch/mission-control/reviews/tickets-technical.md
decisions: changes needed, then approve. Split 04 -> 04a core + 04b Terminal decisions and cards; split 10 -> 10 build + 10b release; split bp#02 -> 02a social + 02b community (each was over one context window)
decisions: add on_approve(conn, subject, args) to ApprovalKind in 04a; group-rules and app-build apply on decide, and 05 and 10 would otherwise collide in approvals.py
decisions: 01 runner hook: plug-in after_run runs before finish_run and may return an Outcome; a core run_update notification on every path but the PAUSE file (lock skip with conn=None); quiet claude jobs get a run id
decisions: the four either-order pairs become edges (03<-04a, 05<-11, 10<-08, 09<-11) with one test owner each; critical path unchanged; plus bp#03<-mc#08 (setup gaps), bp#05<-bp#06 (one pages-not-allowed owner)
decisions: QA Q1 precheck returns agents.NothingToDo -> run.quiet; Q6 approvals.dispatch_builds (04b owns the approvals: block, adds post_buttons for components); Q7 existing paths.site_repo()/JURA_SITE_REPO; Q2 guard in 01; Q3 by edges; Q4 06; Q5 bp#02a/02b/06
questions: G3: build both features on one integration branch crew/mission-control (ticket branches -NN and -bpNN), choosing at G4 whether to ship one PR or two? rec yes
evidence:  uv run pytest -rs @0ad538e -> 987 passed in 22.32s; git status --short unchanged before/after
evidence:  grep -> no jura_growth.agents. import in core; NEVER matched on split()[0]; CONTEXT.md, docs/adr/, both feature folders untracked

## 2026-10-25T19:08+0800 conductor (ticket review)
status:    done
persona:   conductor
ticket:    -
artifacts: reviews/tickets-technical.md
decisions: tech lead: changes needed then approve (splits 04a/04b, 10/10b, bp 02a/02b; on_approve hook; either-order pairs become edges; new edges bp#03<-mc#08, bp#05<-bp#06); sent to the project manager to apply before G3
decisions: first commit on crew/mission-control must add CONTEXT.md, docs/adr/, .scratch/mission-control/ and .scratch/browser-publishing/ before any worktree
questions: one integration branch crew/mission-control for both features? -> put to Ting Yu at G3 (rec yes)
evidence:  tech lead: pytest @0ad538e -> 987 passed

## 2026-10-25T19:16+0800 project-manager (tickets revised for the tech lead's ticket review)
status:    needs-human
persona:   project-manager
ticket:    -
artifacts: mission-control/issues/01-16 plus 04b, 10b (18); browser-publishing/issues/01-06 plus 02b (7); both reviews/status.md
decisions: tickets-technical T1-T12 and N1-N10 applied, apart from T11's commit, which is the conductor's
decisions: splits: 04 into 04a core (keeps 04-) and 04b Terminal decisions and cards; 10 into 10 build and 10b release; bp 02 into 02a social and 02b community
decisions: on_approve and BadArgs in 04a; 01's hook runs before finish_run and may return an Outcome; core notification on every path except PAUSE; NothingToDo -> run.quiet
decisions: either-order pairs are now edges: 03<-04, 05<-11, 10<-08, 09<-11; each shared test has one owner; also bp03<-mc08, bp05<-bp06, bp06<-bp02b, 12<-10b, 13<-04b
decisions: each AC copied word for word exactly once; other tickets cite it by id and name its owner
questions: G3 approve? rec yes; one integration branch crew/mission-control for both features (T11)? rec yes
evidence:  render.py -> 80/80 MC, 36/36 BP placed, 0 duplicates, exit 0 both
evidence:  grep -> no v2, 975 or "second to land" left
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

## 2026-10-25T19:23+0800 business-analyst (clarification after sign-off, G3 follow-up)
status:    done
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md (header line, §4.6 code block and note, §5.3 runner and agents/__init__.py rows)
decisions: §4.6 gains the optional on_approve(conn, subject, args) -> str | None kind hook. decide() calls it inside its BEGIN IMMEDIATE after writing approved. BadArgs means refused and nothing is recorded. group-rules and app-build apply their change there. Per tickets-technical T2; contract unchanged
decisions: §5.3 gains agents.NothingToDo(str). A precheck that returns it writes run.quiet {job, started_at, reason} and no run row. Publish's auth skip stays a plain skip. Per T3
decisions: both marked "clarified after sign-off, 2026-10-25" in the header line and at each spot; sign-off line and closing line left as they were
questions: -
evidence:  grep -> on_approve 5, NothingToDo 3, "Clarified after sign-off, 2026-10-25" 3; tail -1 -> closing line intact; Signed off by line unchanged

## 2026-10-25T19:27+0800 conductor (build start)
status:    done
persona:   conductor
ticket:    01, 02
artifacts: crew/mission-control at 1acc1eb (tickets, CONTEXT.md, docs/adr, both feature folders)
decisions: PR #1 merged by Ting Yu (855e48c); live growth.db backed up to data/growth/backups/manual-before-blocker-fixes-*, then jura-growth status run once: stale journal rolled back, core/0002, community/0002 and outreach/0002 applied, integrity ok
decisions: wave 1 dispatched: mc 01 (runner and guards) and mc 02 (redaction) in parallel worktrees
questions: -
evidence:  sqlite3 mode=ro integrity_check -> ok; growth.db-journal gone

## 2026-10-25T19:29+0800 qa-lead (test strategy v3, ticket ids after the G3 ticket review)
status:    done
persona:   qa-lead
ticket:    -
artifacts: .scratch/mission-control/reviews/test-strategy-v3.md
decisions: Ticket columns, §7 and §11.2 follow the issue files: MC-04a/04b, MC-10/10b, BP-02a/02b, MC-11a = issues/11, MC-11b = issues/12, Ting Yu's mission-control#13-#16; "lands second" notes retired (T4 owners)
decisions: X11 now tests approvals.post_buttons; discord_buttons stays the live-outreach switch (AC-M8.11, E14)
decisions: Q1-Q7 marked settled from tickets-technical.md (NothingToDo -> run.quiet, network guard in MC-01, dispatch_builds, paths.site_repo, AC-M12.2 in MC-06, digest in BP-02a); on_approve kinds scoped in §5.2 and new case G37; E6 checks setup-guide drafts at ticket gates (N4)
questions: PM Q9: add the sweep line to MC-05, MC-09, MC-10b, BP-02a, BP-02b, BP-03, and X2 to MC-05 (rec yes); PM Q10: add R2 and R3 to BP-03 and AC-P11.1's join identity to BP-06 (rec yes); functional lead Q8 still open
evidence:  python check -> MC 80/80, BP 36/36 rows, sets equal to the PRDs; 38 matrix rows (G1-G37 with G4a/G4b)
evidence:  python check -> 21 ticket ids used, all with an issue file; bare MC-04/BP-02 only in the §0 split note; 25 issue files covered

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

## 2026-10-25T19:46+0800 reviewer (01) via conductor
status:    done
persona:   reviewer
ticket:    01
artifacts: reviews/code-review-01.md
decisions: approve; should fix (Standards) README NEVER list and hooks, "notification" naming, duplicated test helpers -> sent back as fix round 1, conductor verifies; Spec notes (NothingToDo summary, exception paths skip run_update) added to issues/03 Comments
questions: -
evidence:  worktree pytest -> 1042 passed, 0 skipped; live data and outputs unchanged; live send-due and requeue-shadow refuse before Resend

## 2026-10-25T19:51+0800 conductor (merge mc 01)
status:    done
persona:   conductor
ticket:    01
artifacts: crew/mission-control at 8bff848 (merge of 01)
decisions: fix round verified by the conductor (README, _run_update rename, shared helpers); merged
questions: -
evidence:  merged branch uv run pytest -> 1042 passed

## 2026-10-25T20:00+0800 reviewer (02, round 1) via conductor
status:    done
persona:   reviewer
ticket:    02
artifacts: reviews/code-review-02.md
decisions: changes-requested; B1 post() never learns named contacts (names leak in existing posts); B2 attachment bytes, file names and outbox paths unmasked; 9 should-fix
decisions: conductor ruling: Ting Yu sender address stays only in previews of Jura own outgoing email; his address and phone removed everywhere else; sent back as fix round 1 with rebase onto 8bff848
questions: -
evidence:  02 worktree pytest -> 1053 passed; trial merge onto 8bff848 -> README conflict only, 1108 passed; bypass script reproduces B1 and B2

## 2026-10-25T20:11+0800 reviewer (07, round 1) via conductor
status:    done
persona:   reviewer
ticket:    07
artifacts: reviews/code-review-07.md
decisions: approve; 9 should-fix incl. sqlite3.Row crash, day_cell KeyError on abandoned, S-1 holiday skip hides a miss, S-2 running quiet run reads missed
decisions: conductor accepts S-1 and S-2 as refinements of PRD 4.5 (within intent); sent back as fix round 1; S-5 added to issues/08 Comments
questions: -
evidence:  worktree pytest -> 1159 passed; probes reproduce

## 2026-10-25T20:19+0800 conductor (merge mc 07)
status:    done
persona:   conductor
ticket:    07
artifacts: merge of 07 (7db030f c8328cb 89aef7f)
decisions: fix round verified by the conductor (runner/schedule/locks changes are constant moves only); merged; worktree removed
questions: -
evidence:  merged branch pytest -> see commit log

## 2026-10-25T20:19+0800 reviewer (02, round 2) via conductor
status:    done
persona:   reviewer
ticket:    02
artifacts: reviews/code-review-02.md (round 2)
decisions: changes-requested on one blocker the fix introduced: own_copy disables single-name masking, so "Hi Jane," reached #outreach-sent; round-1 blockers fixed; S1 PNG ancillary chunks, S2 Ting Yu masked in own copy, nits
decisions: conductor: two rounds done but the fix is mechanical, so one final fix round (rebase onto 0981aa4) with conductor verification instead of escalating
questions: -
evidence:  1140 passed; merge-tree clean; bypass script and scratch send path reproduce

## 2026-10-25T20:25+0800 conductor (merge mc 02)
status:    done
persona:   conductor
ticket:    02
artifacts: merge of 02 (rebased on 0981aa4; through b6678a1)
decisions: fix round 2 verified by the conductor (learned names masked in own copy; PNG pixels only; learn(None) attaches growth.db with mode=ro); merged; worktree removed
questions: -
evidence:  merged branch pytest -> see next entry

## 2026-10-25T20:25+0800 conductor (wave 2)
status:    done
persona:   conductor
ticket:    04
artifacts: -
decisions: crew/mission-control at 2ce000d with 01, 02, 07 merged (1346 passed); mc 04 (approvals core) dispatched
questions: -
evidence:  uv run pytest -> 1346 passed

## 2026-10-25T20:58+0800 reviewer (04, round 1) via conductor
status:    done
persona:   reviewer
ticket:    04
artifacts: reviews/code-review-04.md
decisions: changes-requested; B1 a rolled-back claim still writes approval.used to the JSONL mirror; should fix S1 duplicate --ref, S2 non-BadArgs from on_approve escapes decide(), S3 trigger blocks posted_at on decided records, S4 matrix gaps G29 G32 G36 G5 G15, README row, _atomic into db.py
decisions: every brief attack held (reuse, race, content change, expiry, revoke, paused claim, env/TTY spoof, frozen clock); migration on a main-built db identical; sent back as fix round 1
questions: -
evidence:  worktree pytest -> 1454 passed; probe04.py reproduces B1, S1-S3

## 2026-10-25T21:10+0800 developer (04, fix round 1) via conductor
status:    done
persona:   developer
ticket:    04
artifacts: 84e6dc3 95b5aa4 f78b8eb 0e3a098 bbb6557
decisions: B1 fixed at the root: log.event mirror line waits for db.transaction commit (db.after_commit); S1-S3, S4 gaps, README, ADR 0004 note; notes N2 and N4 added to issues/04b Comments
questions: -
evidence:  pytest -> 1499 passed; probe04 P1-P5, P8 fixed, P6 accepted in ADR 0004 -> sent to the reviewer for round 2

## 2026-10-25T21:18+0800 conductor (merge mc 04)
status:    done
persona:   conductor
ticket:    04
artifacts: merge of 04 (2b06e4e .. d6cf244)
decisions: review round 2 approved; fix round 2 verified by the conductor with probe04r2 (Q1 immediate, Q2 no raise after commit, Q3 use() in a raw BEGIN refused); merged
questions: -
evidence:  merged branch pytest -> see commit

## 2026-10-25T21:18+0800 conductor (wave 3)
status:    done
persona:   conductor
ticket:    03, 04b, 08
artifacts: -
decisions: crew/mission-control at 8e3d9b4 (01, 02, 04, 07 merged; 1503 passed); mc 03, 04b and 08 dispatched in parallel
questions: -
evidence:  merged branch pytest -> 1503 passed

## 2026-10-26T01:11+0800 reviewer (03, round 1) via conductor
status:    done
persona:   reviewer
ticket:    03
artifacts: reviews/code-review-03.md
decisions: approve; gap: a precheck that raises leaves no run row, no #alerts post and no update; should-fix FINANCE_LINE_RE, clickable masked links, repeated claude error, scout digest duplicate, CONTEXT.md wording, AC-M3.5/3.6 test gaps
decisions: conductor ruling (Ting Yu: all communication via Discord, updates whenever agents run): a crash before recording counts as a failed run (run row, #alerts, auto-pause, run update); small runner.py change allowed in 03; sent back as fix round 1
questions: -
evidence:  1533 passed; probes mask names, emails, phone, secrets, mentions

## 2026-10-26T01:20+0800 conductor (merge mc 03)
status:    done
persona:   conductor
ticket:    03
artifacts: crew/mission-control at 54cbbdf (merge of 03)
decisions: fix round verified by the conductor (precheck exception becomes a failed run with row, alert, auto-pause and run update; after_run skipped on that path); merged
questions: -
evidence:  merged branch pytest -> 1540 passed

## 2026-10-26T21:02+0800 conductor (04b and 08 reviews; Discord-only decision)
status:    done
persona:   conductor
ticket:    04b, 08
artifacts: reviews/code-review-04b.md, code-review-08.md; PRD amendment note before §6; issues/13 Comment
decisions: 04b changes-requested (S1: a Claude session recorded Terminal decisions via an orphaned expect; code shown on cards). Ting Yu chose Discord only: Terminal decisions off, decisions only via Dispatch over SSH; Touch ID may come later as a ticket. Sent as fix round 1
decisions: 08 changes-requested (B-1 one-pager window of seconds at 08:00:05); conductor accepts S-1 (CONTROL_DISCORD_USER_ID core gap) and S-2 (digest lines name no day); Terminal note replaced by a pointer to #approvals; sent as fix round 1
questions: -
evidence:  04b: 1670 passed, orphaned expect recorded A-0001/A-0004; 08: 1575 passed, merged tree 1779, window_probe loses note and counts

## 2026-10-26T21:02+0800 conductor (standing instruction)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: Ting Yu: "dont ask me questions, just make the decisions and push". From here the conductor decides using the crew recommendations, logs each decision, pushes crew/mission-control after merges and opens the PR at the end
questions: -
evidence:  -

## 2026-10-26T21:11+0800 conductor (merge mc 08)
status:    done
persona:   conductor
ticket:    08
artifacts: merge of 08 (rebased on ed609a3)
decisions: fix round verified by the conductor with window_probe (08:00:05 -> previous day window, A-0160 listed, undelivered 1); merged and pushed
questions: -
evidence:  merged branch pytest -> see commit

## 2026-10-26T21:17+0800 conductor (merge mc 04b; wave 4)
status:    done
persona:   conductor
ticket:    04b, 06, 10, 11
artifacts: crew/mission-control at 722bcdc (merge of 04b)
decisions: 04b fix round verified (Terminal origin removed; orphaned-expect probe refused with and without markers); merged; Discord-only decisions in force
decisions: ticket 05 X9: setting rules_confirmed raises a group-rules request decided in #approvals (crew recommendation adopted)
decisions: wave 4 dispatched: 06 outreach gate, 10 app-factory kinds, 11 remote core
questions: -
evidence:  merged branch pytest -> 1803 passed

## 2026-10-26T21:21+0800 qa-lead (test strategy v3: Terminal decisions off)
status:    done
persona:   qa-lead
ticket:    -
artifacts: .scratch/mission-control/reviews/test-strategy-v3.md
decisions: AC-M6.4, AC-M7.2, AC-M7.3, AC-M7.4 now test the 2026-10-26 amendment: approve/skip in Terminal exit 2 with the #approvals pointer, ask no code and record nothing; decide() refuses every non-SSH origin; the orphaned-expect probe (ppid 1, Claude markers set and stripped) is AC-M7.3's regression case
decisions: new matrix case G38 (Terminal off, every state); G13 layer 5, S13, the fake origin, D7, D12, U1, X9 (raises a group-rules request decided in #approvals), AC-M10.6 (remote only), E6 (no Terminal origin) and §11.2 rows updated
questions: business analyst Q11: bring the PRD text (AC-M6.4, AC-M7.2-7.4, §4.6 A8, §4.8, §5.3, §5.12, §6 Q3, BP §4.2, §5.7) in line with the amendment, keeping AC ids (rec yes)
evidence:  python check -> MC 80/80, BP 36/36 rows, same AC ids as the PRDs; 39 matrix rows (G1-G38 with G4a/G4b); Q1-Q11
evidence:  uv run pytest tests/test_origin_processes.py tests/test_approvals_cli.py tests/test_origin.py @04a609e -> 90 passed; grep jura_growth for Origin.terminal / "terminal: -> no hits

## 2026-10-26T21:24+0800 business-analyst (amendment: Terminal decisions off)
status:    done
persona:   business-analyst
ticket:    05, 13 (issue text only)
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md; prd-jura-browser-publishing-2026-10-25.md; .scratch/mission-control/issues/05-group-rules-kind.md; 13-discord-channels-and-terminal-checks.md
decisions: MC brought in line with Ting Yu's 2026-10-26 amendment. Every AC id is kept and each changed spot is marked "Amended 2026-10-26": header, AC-M6.4, SC7 intro, AC-M7.2-7.4, A8 (remote is the only origin), A11, §4.8 (nothing decided for real before MC-11a + D1-D4), §5.1 Q8, §5.3 origin and community rows, §5.4, §5.6 (no code on cards), §5.7, §5.12 MC-04/MC-05/"Live from the phone", §5.14, §6 Q3 (answered)
decisions: BP header, §4.2 and §5.7 amended. publish queue and resolve stay in Terminal because they record no decision
decisions: 05 X9: rules_confirmed=yes raises a group-rules request decided in #approvals. It refuses days given in the same command, and refuses when no rules text is recorded. 13 U1 now checks that approve and skip refuse with a pointer to #approvals
questions: -
evidence:  grep -> AC-M6.4 and AC-M7.1-7.7 each 1; AC counts MC 80, BP 36 unchanged; "code 3f9a1c|Origin.terminal|terminal:<macOS" -> 0; closing lines intact

## 2026-10-27T02:21+0800 conductor (merge mc 11)
status:    done
persona:   conductor
ticket:    11
artifacts: merge of 11 (rebased on c2b468f; fixes d81d895 33ec43b 03bece3)
decisions: review approved; fix round verified by the conductor (shared waiting() helper, execv refusal, masking-degraded event); merged and pushed
questions: -
evidence:  merged branch pytest -> see commit
## 2026-10-27T02:20+0800 qa-lead (uat.md for Discord-only decisions; ticket 17)
status:    done
persona:   qa-lead
ticket:    17
artifacts: .scratch/mission-control/uat.md; .scratch/mission-control/issues/17-uat-seed-outreach.md
decisions: every decision step goes through #approvals via Dispatch (/growth approve|skip, buttons once post_buttons is on); Terminal approve/skip appear only as refusals (A3, A7); AC refs moved to the PRD's AC-M/AC-P ids
decisions: outreach steps follow ticket 06: live refused until approvals.discord_buttons (UAT config only), requests only for emails due today within the quota (5 open, rest wait for a slot, top-up after send/skip), decide-by and use-by lapses, declined_by_ty on skip
decisions: Parts A-C run on the real clock (decisions are stamped with it), seeded from --today; clock-jump steps last in each part
decisions: ticket 17 (blocked by 06): --today, outreach-live, requests via the first send-due, edit-draft --lead, shadow-trial; other kinds' scenarios left with tickets 10, 05, BP-02a, BP-02b
questions: tech lead: how does Dispatch reach the UAT folder? rec a UAT-only key whose authorized_keys forced command fixes the UAT folder variables, removed after UAT; Parts A-C wait on it
questions: PM: tickets 10, 05, BP-02a, BP-02b don't list their uat.md seed scenarios; rec add one line each
evidence:  grep uat.md for "jura-growth approve|skip" -> 2 hits, both refusal steps (A3 Terminal, A7 headless); jura-growth --help, outreach --help, log events --help -> the commands named in uat.md exist
