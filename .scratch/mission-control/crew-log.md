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

## 2026-10-27T02:22+0800 conductor (ticket 10 review; UAT decisions)
status:    done
persona:   conductor
ticket:    10, 17
artifacts: reviews/code-review-10.md; merged crew/mission-control-qa-uat-discord-only (uat.md, issues/17)
decisions: 10 changes-requested (B1 handoff SHA read after claim); apps/0003 safe; skips legit but break E3 -> fixed in 10; sent as fix round 1
decisions: UAT reaches its folder through a UAT-only SSH key whose forced command fixes the UAT folder variables, removed after UAT; seed-scenario lines added to mc 05, 10 and bp 02, 02b
questions: -
evidence:  reviewer: 1842 passed 10 skipped; main-built db migrates, rows equal

## 2026-10-27T02:24+0800 reviewer (06, round 1) via conductor
status:    done
persona:   reviewer
ticket:    06
artifacts: reviews/code-review-06.md
decisions: changes-requested; B1 email built before the claim, sent bytes never compared to content_hash; Sp1 unbounded claimed retries past Resend 24h idempotency; Sec2 NFC normalisation lets different bytes hash equal; every other attack held
decisions: conductor: sent as fix round 1 (B1, Sp1, Sec2)
questions: -
evidence:  1932 passed; reviewer repros demonstrate both gaps; E14 holds

## 2026-10-27T02:33+0800 conductor (merge mc 10 and 06; wave 5)
status:    done
persona:   conductor
ticket:    10, 06, 05, 09, 10b, 17, bp-02
artifacts: crew/mission-control at ebec138 (merges of 10 and 06)
decisions: 10 fix round verified (handoff carries the approved hash, refuses on mismatch; 0 skipped); 06 fix round verified (email built and hashed inside the claim; 23h retry window then uncertain plus alert; exact-byte hash); merged and pushed
decisions: E14 holds: discord_buttons false, scout mode shadow
decisions: wave 5 dispatched: mc 05, 09, 10b, 17 and bp 02 (publish queue, no browser)
questions: -
evidence:  merged branch pytest -rs -> 2176 passed, 0 skipped

## 2026-10-27T02:53+0800 conductor (merge mc 17; ticket 18)
status:    done
persona:   conductor
ticket:    17, 18
artifacts: merge of 17 (tests/uat only); issues/18-uat-d1-stub.md
decisions: 17 is test-only, verified by the conductor (diff limited to tests/) and merged without a separate review
decisions: crew recommendations adopted: new ticket 18 (loopback-only D1 stub for UAT); QA lead amends uat.md (JURA_GROWTH_RESEND_BASE_URL, JURA_INPUTS_DIR, A4 wording)
questions: -
evidence:  dev: 2207 passed, 0 skipped; seed refuses Saturday and live data

## 2026-10-27T02:54+0800 qa-lead (uat.md: UAT environment and A4 fix after ticket 17)
status:    done
persona:   qa-lead
ticket:    -
artifacts: .scratch/mission-control/uat.md
decisions: environment block and the UAT forced-command entry gain JURA_INPUTS_DIR="$UAT/inputs" and JURA_GROWTH_RESEND_BASE_URL=http://127.0.0.1:8025 (the stub's port); JURA_GROWTH_D1_BASE_URL left commented until ticket 18
decisions: A4's waiting count read from send-due's answer ("5 waiting for a decision, 12 waiting for a request slot"), not queue-list
decisions: new "Before you start" step 6 and an A4 note: live-mode steps need ticket 18's loopback D1 stub; the Resend stub runs in a second window with the same variables
questions: -
evidence:  uv run pytest tests/test_uat_seed_outreach.py -> passed; its assertion matches the 5/12 text now in A4

## 2026-10-27T03:10+0800 reviewer (code review 09)
status:    done
persona:   reviewer
ticket:    09
artifacts: .scratch/mission-control/reviews/code-review-09.md
decisions: verdict approve: no blocking findings; no blocked path touched; merges cleanly into crew/mission-control
decisions: S-1 grid PNGs never pruned (~74 KB/day in OneDrive); recommend retention.one_pager_days: 14, pruned by backup
decisions: S-2 test_remote.py:187 row passes on "not posted to …"; S-3 DEFAULT_CHROME duplicated (images.py:22, social/settings.py:19); S-4 README layout lacks one-pager/
decisions: dismissed the spec reviewer's §4.3 masking claim: mission.read loads Keychain masking at mission.py:155
questions: S-5 exit 0 when Discord refuses vs dispatch-contract "exit 1 = problem of its own"? Recommended: keep 0 (heartbeat precedent), state it in the contract row
evidence:  uv run pytest -q (worktree, temp data) -> exit 0, 2213 collected, no failures
evidence:  ticket tests with real Chrome -> 41 passed, 0 skipped; test_social_render.py diff empty
evidence:  git merge-tree vs fec69b8 -> clean; real grid PNG chunks -> IHDR/IDAT/IEND only

## 2026-10-27T03:03+0800 conductor (09 review; 10b done)
status:    done
persona:   conductor
ticket:    09, 10b
artifacts: reviews/code-review-09.md
decisions: 09 approved; crew recommendations adopted: retention.one_pager_days 14 pruned by backup; fix the can-not-fail remote test; one Chrome path constant; README layout; keep exit 0 when Discord refuses and document it; sent as fix round 1
decisions: 10b done (2238 passed, 0 skipped); sent to review
questions: -
evidence:  09: real grid PNG IHDR/IDAT/IEND only; Chrome opens file:// only

## 2026-10-27T03:13+0800 conductor (merge mc 09; 05 review; bp 02 done)
status:    done
persona:   conductor
ticket:    09, 05, bp-02
artifacts: merge of 09; reviews/code-review-05.md
decisions: 09 fix round verified (14-day grid retention pruned by backup, failing-capable remote test, shared Chrome path, exit 0 documented); merged
decisions: 05 changes-requested (B1 quoted rules_confirmed bypass); crew recommendation adopted for S5 (re-request on a confirmed group is how days change; skip keeps the old confirmation); sent as fix round 1 with rebase
decisions: bp 02 (publish queue) done, 2310 passed; sent to review
questions: -
evidence:  merged branch pytest -rs -> 2246 passed, 0 skipped

## 2026-10-27T03:17+0800 reviewer (10b) via conductor
status:    done
persona:   reviewer
ticket:    10b
artifacts: reviews/code-review-10b.md
decisions: changes-requested; B1 --preview accepts Markdown so a masked link to any domain renders on the release card; release needs a separate claimed approval of the exact SHA, SHA unspoofable, plan merges only the approved SHA; should fix S1-S8
decisions: conductor: sent as fix round 1 with rebase onto abe16b0
questions: -
evidence:  2238 passed; trial merge 2308 passed; probes reproduce B1, S1, S2, S3

## 2026-10-27T03:21+0800 business-analyst (PRD clarification: group-rules over researched rules, re-confirming)
status:    done
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md (§5.1 "Group rules" bullet and header line, marked "Amended 2026-10-27")
decisions: "never for researched rules" means the engine never raises a request from research on its own. Ting Yu's community set <id> rules_confirmed=yes may raise one over researched text such as "not stated", because unknown-rules groups need confirmed days to get any open day
decisions: re-confirming a confirmed group raises a new card. Approve replaces the days; skip or expiry keeps the days already confirmed. No AC ids changed
questions: -
evidence:  AC count 80 unchanged; "Amended 2026-10-27" 2 hits; closing line intact

## 2026-10-27T03:23+0800 reviewer (bp 02) via conductor
status:    done
persona:   reviewer
ticket:    bp-02
artifacts: .scratch/browser-publishing/reviews/code-review-02.md
decisions: changes-requested; B1 content change re-raises on the same item with the old day deadline (never posts) and sync can withdraw without a new card; B2 claim checks images against a second read, not content_hash (image swap after use() handed out)
decisions: conductor: fix round 1 with rebase; exact-bytes hashing for publish too (BA amends A3 and ADR 0003)
questions: -
evidence:  2310 passed; repros r1-r5 prove the gaps; caps.py additions only

## 2026-10-27T03:23+0800 business-analyst (amendment: content hash covers exact bytes)
status:    done
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md (§4.6 A3 and header, "Amended 2026-10-27"); docs/adr/0003-an-approval-binds-to-content-and-is-claimed-once.md
decisions: A3 and ADR 0003: the content hash covers the exact bytes handed out (text and every attachment, UTF-8 JSON with sorted keys), with no Unicode normalisation, as code reviews 06 (Sec2) and BP-02 established. NFC-only matching on live text read back (BP AC-P7.3) is a separate rule and is unchanged
questions: -
evidence:  grep A3 -> "no Unicode normalisation" present, "NFC-normalised" gone; AC count unchanged; ADR diff one paragraph added

## 2026-10-27T03:23+0800 reviewer (18) via conductor; ADR 0003 merged
status:    done
persona:   reviewer
ticket:    18
artifacts: reviews/code-review-18.md; merged crew/mission-control-adr-0003-exact-bytes (A3 and ADR 0003: exact bytes, no normalisation)
decisions: 18 approved; SEC-1 (D1 stub with real Resend) must be fixed before UAT, plus uat.md conflict resolution and ST-1..3; sent as fix round 1
questions: -
evidence:  18 URL bypass probes all hit loopback, real token never sent; live and symlinked data folders refused; 2223 passed

## 2026-10-27T03:29+0800 conductor (merge mc 05 and 10b)
status:    done
persona:   conductor
ticket:    05, 10b
artifacts: merges of 05 (round 2 approved) and 10b (fix round)
decisions: 05 review round 2 approve (40 bypass probes refused; re-confirm works; empty rules refused only); merged
decisions: 10b fix round verified by the conductor: all 5 reviewer probes now fail on their bug assertions (preview swap, masked link, any pages.dev, SHA on main, tag main); merged
decisions: setup item: Ting Yu sets config/apps.yaml pages_project to the landing page Cloudflare Pages project before ticket 16 (UAT A5 uses example)
questions: -
evidence:  merged branch pytest -rs -> see next commit

## 2026-10-27T03:32+0800 conductor (merge mc 18)
status:    done
persona:   conductor
ticket:    18
artifacts: merge of 18 (33ffd45 1054f37 591fd4d)
decisions: review approved; fix round verified (either stub URL alone refused; one resolver uat_stub.base()); seed.py import conflict with 05 resolved by keeping both import sets; merged and pushed
questions: -
evidence:  merged branch pytest -rs -> 2433 passed, 0 skipped

## 2026-10-27T03:40+0800 developer (bp 02, fix round 1) via conductor
status:    done
persona:   developer
ticket:    bp-02
artifacts: crew/browser-publishing-02-publish-queue rebased on d0b0119 (e5110e3 f74e3a5 cf4b5ac 26754fd)
decisions: B1 and B2 fixed; conductor adopts the crew recommendation to record sync() raising requests in A11 (BA amends); BP-03 precheck must run sync() first (note on issues/03); sent to the reviewer for round 2
questions: -
evidence:  2586 passed, 0 skipped

## 2026-10-27T03:40+0800 business-analyst (amendment: publish queue sync() raises replacement social-post requests)
status:    done
persona:   business-analyst
ticket:    -
artifacts: jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md (§4.6 A11, header); prd-jura-browser-publishing-2026-10-25.md (§5.4, §5.5 social-post row, header); all marked "Amended 2026-10-27"
decisions: the publish queue's sync() is a request raiser. When a queued social post's content changes, it raises a fresh social-post request for the new content and supersedes the old one, and it never withdraws an item without raising its replacement. No AC ids changed; no in-repo doc other than this log needed a change
questions: -
evidence:  grep "sync()" -> MC 2, BP 3; AC counts MC 80, BP 36 unchanged; closing lines intact

## 2026-10-27T03:41+0800 business-analyst (correction to the sync() amendment)
status:    needs-human
persona:   business-analyst
ticket:    -
artifacts: MC PRD §4.6 A11; BP PRD §5.4 social bullet and §5.5 social-post row (still marked "Amended 2026-10-27")
decisions: corrects the previous entry to match the code (BP-02a fix round 1, the G9 harness). sync() raises a fresh social-post request on the same item (subject publish_item:<id>) and supersedes that item's old request. It creates no new item and never leaves the item without a live request
questions: BP AC-P1.3 still says a content change raises "a new item and request". For a queued social post the code keeps the item. Reword AC-P1.3 to "a fresh request on the same item (social posts); a new item for other kinds", keeping its id? rec yes
evidence:  grep -> "fresh item" 0 in BP; same-item wording present in MC A11 and BP §5.4/§5.5

## 2026-10-27T03:41+0800 conductor (PRD sync amendment)
status:    done
persona:   conductor
ticket:    -
artifacts: merged crew/mission-control-prd-sync-raiser; BP PRD AC-P1.3 reworded
decisions: crew recommendation adopted: AC-P1.3 now says a fresh request on the same item for a queued social post, a new item and request otherwise (Amended 2026-10-27); AC ids unchanged
questions: -
evidence:  -

## 2026-10-27T03:44+0800 developer (mc 12) via conductor
status:    done
persona:   developer
ticket:    12
artifacts: crew/mission-control-12-remote-apps-commands (063c7ec)
decisions: remote handoff JSON for Dispatch; prd_text unmasked by design (hash), for the brief only; 64 KB spill; sent to review with focus on prd_text exposure
questions: -
evidence:  2448 passed, 0 skipped

## 2026-10-27T03:45+0800 reviewer (bp 02, round 2) via conductor
status:    done
persona:   reviewer
ticket:    bp-02
artifacts: .scratch/browser-publishing/reviews/code-review-02.md (round 2)
decisions: approve; B1, B2, S1-S7 fixed; probes p6, p7, p9, p10 hold; R2-S1 (moved-to-today post waits for the next heartbeat) and R2-N1 sent as fix round 2, conductor verifies
decisions: reviewer asked Ting Yu to confirm the exact-bytes amendment to A3 and ADR 0003; under Ting Yu standing instruction ("dont ask me questions, just make the decisions") the conductor confirms it (stricter than the signed-off text) and records it here
questions: -
evidence:  2586 passed; probes r1-r5, p6-p11 run

## 2026-10-27T03:51+0800 conductor (merge bp 02; next wave)
status:    done
persona:   conductor
ticket:    bp-02, bp-02b, bp-03
artifacts: merge of bp 02 (15ccdaf .. 94f02a9)
decisions: fix round 2 verified (p8 and p11 regressions fail before, pass after); merged and pushed
decisions: bp 01 (Chrome profile setup and checks) is Ting Yu's and gates live posting, not the build: bp 03 is built against the fake claude binary and localhost fixture pages; Ting Yu's rehearsal R1-R4, R6 and live step U12 follow
decisions: next wave dispatched: bp 02b (community items) and bp 03 (browser job, Facebook Page)
questions: -
evidence:  merged branch pytest -rs -> see commit

## 2026-10-27T03:52+0800 reviewer (mc 12) via conductor
status:    done
persona:   reviewer
ticket:    12
artifacts: reviews/code-review-12.md
decisions: approve; origin and control-user checks hold on all 4 commands; injection closed; prd_text stays out of Discord, events and plain output; should fix S1 trim order, S2 redacted prd_text keeps the approved hash, shared trim policy
decisions: conductor adopts Q1 recommendation: app PRDs the privacy filter would change are refused at factory submit; S2 as backstop; D6 says brief only, never Discord; sent as fix round 1
questions: -
evidence:  2448 passed; probes reproduce S1, S2; injection refused

## 2026-10-27T04:04+0800 conductor (merge mc 12; mission-control code complete)
status:    done
persona:   conductor
ticket:    12
artifacts: merge of 12 (2429947 ca5de35 cf1a096)
decisions: fix round verified (handoff_fit shared limit; redacted prd_text withheld; PRDs the privacy filter would change rejected at submit); merged and pushed; all mission-control code tickets (01-12, 04b, 10b, 17, 18) are merged; 13-16 are Ting Yu setup tickets
questions: -
evidence:  merged branch pytest -rs -> see commit

## 2026-10-27T04:18+0800 conductor (bp 02b done)
status:    done
persona:   conductor
ticket:    bp-02b
artifacts: crew/browser-publishing-02b-community-items (5 commits)
decisions: crew recommendation adopted: AC-P1.3 reworded to a fresh request on the same item for every queued kind (Amended 2026-10-27); bp 02b sent to review
questions: -
evidence:  2733 passed, 0 skipped; 63 gate cases pass for community-post and group-join

## 2026-10-27T04:26+0800 reviewer (bp 02b) via conductor
status:    done
persona:   reviewer
ticket:    bp-02b
artifacts: .scratch/browser-publishing/reviews/code-review-02b.md
decisions: changes-requested; B1 claim allows a promotional post where promo days are none and a link post where rules forbid links; B2 identity or URL change re-raises with the old deadline; should-fix list
decisions: conductor: skipped or expired join proposals count toward 3 a week (crew recommendation); sent as fix round 1
questions: -
evidence:  2733 passed; probes p3, p4 (B1) and p5 (B2) reproduce

## 2026-10-27T04:28+0800 conductor (bp 03 done; bp 07 added)
status:    done
persona:   conductor
ticket:    bp-03, bp-07
artifacts: crew/browser-publishing-03-browser-job (7 commits); issues/07-fixture-platform.md
decisions: crew recommendations adopted: new ticket bp 07 (loopback-only fixture platform for R1-R6); try a file_upload parameter allow rule at R1; Chrome scope stays Facebook hosts plus business.facebook.com, no CDN hosts, until U18
decisions: bp 03 sent to an adversarial review of Chrome scope
questions: -
evidence:  2742 passed, 0 skipped

## 2026-10-27T04:40+0800 conductor (merge bp 02b)
status:    done
persona:   conductor
ticket:    bp-02b
artifacts: merge of bp 02b (527b1ca .. b6ff275)
decisions: round-2 review approve (12 probes incl. rules changed after approval, days narrowed, answers changed twice); merged and pushed; bp 06 now needs only bp 03
questions: -
evidence:  merged branch pytest -rs -> see commit

## 2026-10-27T04:43+0800 reviewer (bp 03) via conductor
status:    done
persona:   reviewer
ticket:    bp-03
artifacts: .scratch/browser-publishing/reviews/code-review-03.md
decisions: changes-requested; B1 model or page text reaches the run row, #alerts and run updates; B2 fragmented or pre-claim typing passes the audit; should fix S-4, S-7, S-8, S-9 and drift; --chrome verified publish-only
decisions: conductor adopts the crew recommendation: no screenshot file; AC-P6.1 and the stop paragraph amended (reason and run id only); sent as fix round 1
questions: -
evidence:  2742 passed; repro_audit and fake-claude run reproduce B1 and B2

## 2026-10-27T05:12+0800 reviewer (bp 03, round 2) via conductor
status:    done
persona:   reviewer
ticket:    bp-03
artifacts: .scratch/browser-publishing/reviews/code-review-03.md (round 2)
decisions: changes-requested; round-1 findings all fixed; B3 new: nested JSON in page text raises RecursionError in the audit, after_run fails open (no audit, no pause, model text kept); S-10 planted page JSON passes the tab-address check; caps at commands.py:212 is fine
decisions: conductor (standing instruction: decide, do not ask): third round with a structural fail-closed fix at the publish after_run boundary instead of escalating; conductor verifies with the reviewer repros
questions: -
evidence:  2926 passed; repro_audit_r2 reproduces B3 and S-10

## 2026-10-27T05:23+0800 conductor (merge bp 03)
status:    done
persona:   conductor
ticket:    bp-03
artifacts: merge of bp 03 (through a87e79c)
decisions: fix round 2 verified by the conductor with the reviewer repros: repro_audit (fragments, whole typing, after-stop, upload secret, unparsed tab all fail) and repro_audit_r2 (extra text, two fields, planted tab fail; deep JSON no longer raises); merged and pushed
decisions: next wave: bp 04 (Instagram, LinkedIn), bp 06 (joins as the Page), bp 07 (fixture platform)
questions: -
evidence:  merged branch pytest -rs -> see commit

## 2026-10-27T05:44+0800 reviewer (bp 04) via conductor
status:    done
persona:   reviewer
ticket:    bp-04
artifacts: .scratch/browser-publishing/reviews/code-review-04.md
decisions: changes-requested; B1 audit uses all enabled platform hosts, not the claimed item platform (cross-platform post ends ok); should fix S1 failed upload counted, S3 native upload buttons, S4 done URL shape, S5 LinkedIn /in/ accepted, S2 docs; hosts exact; round-3 protections hold
decisions: conductor: weekends stay on with three platforms (crew recommendation), weekends:false documented; sent as fix round 1
questions: -
evidence:  3015 passed; repro_04 and fake-claude B1b/S1 reproduce

## 2026-10-27T05:46+0800 reviewer (bp 07) via conductor
status:    done
persona:   reviewer
ticket:    bp-07
artifacts: .scratch/browser-publishing/reviews/code-review-07.md
decisions: changes-requested; B1 fixture URL with a backslash (http://evil.com\\.localhost:8765) parses as host evil.com in a browser; should fix ST-1..3, SP-1; live, symlinked and ../ data folders refused; no fallback; mixed real and fixture refused
decisions: conductor: WHATWG-style host validation; AC3 stays Ting Yu R1 step, recorded before close; sent as fix round 1
questions: -
evidence:  2989 passed; WHATWG parse reproduces B1

## 2026-10-27T05:56+0800 reviewer (bp 06) via conductor
status:    done
persona:   reviewer
ticket:    bp-06
artifacts: .scratch/browser-publishing/reviews/code-review-06.md
decisions: changes-requested; B1 audit is host-only: a claimed join for group A can join group B or post answers on the Page timeline and end ok; S1 merge guard with bp 04 B1; cap holds; note-rules only clears confirmations
decisions: known limit recorded for Ting Yu: personal-profile joins cannot be made impossible in code (the Chrome profile is his own account administering the Page); guarded by the prompt identity check, never-switch rule, wrong-identity stop, rehearsals R5/R6 and live step U15
decisions: conductor (crew recommendation): declined groups never re-proposed automatically and take no cap slot; refused Page recorded as pages-not-allowed; sent as fix round 1
questions: -
evidence:  2996 passed; repros R1-R5 reproduce

## 2026-10-27T05:59+0800 conductor (merge bp 04)
status:    done
persona:   conductor
ticket:    bp-04
artifacts: merge of bp 04 (through ae4e3dc)
decisions: fix round verified by the developer repro output (cross-platform cases fail; errored/denied upload counted as missing); merged and pushed; weekends stay on (already decided); Facebook permalink shape check after R1 noted on bp 01; bp 06 and 07 to rebase onto this merge and resolve overlaps
questions: -
evidence:  merged branch pytest -rs -> see commit

## 2026-10-27T05:59+0800 reviewer (bp 07, round 2) via conductor
status:    done
persona:   reviewer
ticket:    bp-07
artifacts: .scratch/browser-publishing/reviews/code-review-07.md (round 2)
decisions: approve; 60 WHATWG probes, every accepted URL is loopback; M1 at merge: 04 browser_hosts must not bring real domain rules back while the fixture is on; sent to the developer as a rebase task with a regression test
decisions: AC3 (R1b file_upload) stays open for Ting Yu; ticket 07 stays open after the code merges
questions: -
evidence:  3016 passed, 0 skipped

## 2026-10-27T06:08+0800 conductor (merge bp 07 code)
status:    done
persona:   conductor
ticket:    bp-07
artifacts: merge of bp 07 (59c4106 06bc555 8156f61 e737c4b)
decisions: round-2 review approved; M1 resolved in the rebase (fixture override first; dry-run with the fixture on shows only publish-fixture.localhost; guard test fails without the override); code merged and pushed; ticket stays open until Ting Yu records R1b (AC3)
questions: -
evidence:  merged branch pytest -rs -> see commit

## 2026-10-27T06:18+0800 reviewer (bp 06, round 2) via conductor
status:    done
persona:   reviewer
ticket:    bp-06
artifacts: .scratch/browser-publishing/reviews/code-review-06.md (round 2)
decisions: approve; B1 fixed (22 path probes); S7 groups.validate accepts any facebook URL containing /groups/, widening the path check if a bad address is approved; N10, N11
decisions: conductor: S7, N10, N11 fixed before merge in a short fix round 2
questions: -
evidence:  3230 passed, 0 skipped

## 2026-10-27T06:30+0800 conductor (merge bp 06; last code ticket)
status:    done
persona:   conductor
ticket:    bp-06, bp-05
artifacts: merge of bp 06 (through 65c4035)
decisions: fix round 2 verified (group_url_problem accepts only /groups/<one segment>, no query, fragment or dot segment; old rows fail closed); merged and pushed
decisions: bp 05 (community posts as the Page) dispatched: the last code ticket
questions: -
evidence:  merged branch pytest -rs -> 3253 passed, 0 skipped

## 2026-10-27T06:31+0800 conductor (incident: removed a live worktree)
status:    done
persona:   conductor
ticket:    bp-05
artifacts: -
decisions: the worktree cleanup removed the just-started bp 05 developer's worktree (its placeholder branch sat at the merge base, so it looked merged); the agent had only read its brief, so no work was lost; it was stopped and relaunched fresh
decisions: cleanup rule from now on: remove only worktrees whose branch starts with crew/, is merged, and whose agent has reported done; never a worktree-agent-* branch of a running agent
questions: -
evidence:  git status clean; no bp 05 branch existed

## 2026-10-27T06:51+0800 developer (bp 05) via conductor
status:    done
persona:   developer
ticket:    bp-05
artifacts: crew/browser-publishing-05-community-posts-as-the-page (4 commits)
decisions: removal or admin warning removes the group in the stop transaction; done URLs limited to the own group post path; conductor adopts the crew recommendation: posts held for admin approval stop as unidentified (publish pauses) until U14 shows how often, then add a pending outcome; sent to review
questions: -
evidence:  3292 passed, 0 skipped

## 2026-10-27T06:56+0800 reviewer (bp 05) via conductor
status:    done
persona:   reviewer
ticket:    bp-05
artifacts: .scratch/browser-publishing/reviews/code-review-05.md
decisions: Approve; S1 (audit-failed post keeps posted record unflagged) and S2 (permalink group segment unproven, add to U14) should-fix; conductor sends S1, S2 and N8 to the developer as fix round 1; other nits left
questions: -
evidence:  3292 passed, 0 skipped; repro probes R1-R10 10 passed; no blocked paths; merge-tree clean

## 2026-10-27T07:08+0800 conductor (bp 05 merge)
status:    done
persona:   conductor
ticket:    bp-05
artifacts: merge b185969 (fix round b72ef32 S1, ba3d2c8 N8, 7727a25 S2)
decisions: fix round verified by the conductor (audit-failed post kept and named, never reset; one removal helper; U14 permalink-form step); merged
questions: -
evidence:  3295 passed, 0 skipped on crew/mission-control after the merge

## 2026-10-27T07:18+0800 reviewer (final pre-release review)
status:    done
persona:   reviewer
ticket:    final
artifacts: .scratch/mission-control/reviews/code-review-final.md
decisions: verdict approve-with-follow-ups: no blocker; every outward action claims an approval over exact bytes, decisions only via the SSH forced command, no blocked path touched
decisions: Sp1 (killed publish run not paused before next claim, AC-P10.1) and Sp2 (one-pager posts FAIL: text unescaped, MC §4.3) recommended fixed on-branch before G4
decisions: St1 NFC wording vs ADR 0003, St2 .env.example missing APPROVALS/MISSION_CONTROL webhooks, St3 duplicated _normal; Sp3 release-plan answer not re-fetchable; nits St4-St8, Sp4-Sp5
questions: fix Sp1+Sp2 before merge or ship as follow-ups? Recommended: fix before merge (small, test-first)
evidence:  uv run pytest -rs -p no:cacheprovider -o addopts="" (temp data/outputs) -> 3295 passed, 0 skipped, 147s
evidence:  live growth.db mtime unchanged; git status clean; blocked-path grep on diff -> none
evidence:  same-process second flock blocks -> is_held(job) True inside the run (Sp1 mechanism)

## 2026-10-27T07:18+0800 conductor (final review)
status:    done
persona:   conductor
ticket:    final
artifacts: .scratch/mission-control/reviews/code-review-final.md
decisions: adopt the reviewer recommendation: fix on the branch before the PR. One developer fix round for Sp1 (orphaned claim settles and pauses), Sp2 (one-pager escapes model FAIL lines), Sp3 (release-plan answer re-fetchable), St1 (no-NFC wording; drop NFC in releases and group_rules), St2 (.env.example webhooks), St3 (one _normal), St8 (operating card count). Nits St4-St7, Sp4 left as follow-ups; Sp5 PRD text at move to done
questions: -
evidence:  3295 passed, 0 skipped

## 2026-10-27T07:44+0800 conductor (final-review fix merge)
status:    done
persona:   conductor
ticket:    final
artifacts: merge 8d6640e (45987b3 Sp1, 459bcaf Sp2, 6133d10 Sp3, 450822c St1, 6dccdc0 St2, 01bc4ff St3, 47b83fb St8)
decisions: verified by the conductor: orphaned claims settle unknown, pause and alert under the job lock, three test fixtures corrected to record their claims (not weakened); one untrusted_line escape for run updates and the one-pager; merged. Sp5 already resolved by the 2026-10-27 AC-P1.3 amendment. Next: quality gate and release prep, then the PR
questions: -
evidence:  3305 passed, 0 skipped after the merge

## 2026-10-27T08:10+0800 release-manager (release prep)
status:    needs-human
persona:   release-manager
ticket:    -
artifacts: .scratch/mission-control/reviews/release.md, .scratch/mission-control/pr-body.md, .scratch/mission-control/release-notes.md
decisions: no version bump or CHANGELOG (repo convention: none; release notes in the PR body)
decisions: setup guides not copied to outputs/growth/setup/ (outside the repo); listed as an after-acceptance step
decisions: nine ticket reviews ending changes-requested (conductor-verified fix rounds) listed as a waiver; final review approves
decisions: gaps flagged: bp 01's browser-publishing setup guide never drafted; uat.md UAT authorized_keys line unwritten
questions: G4: open the PR and merge with a merge commit after quality-gate GO? Recommended: yes
evidence:  uv run pytest -rs (temp data/outputs) -> 3305 passed, 0 skipped, 146s; live growth.db mtime unchanged; tree clean
evidence:  merge-base HEAD origin/main = origin/main 855e48c; blocked-path grep -> none; secret-shape scan -> fixtures only
evidence:  db built by main, migrated by branch (16 ids), reopened by main: status, community groups, outreach status OK
evidence:  jura-growth approve in Terminal -> refused exit 2; JURA_GROWTH_JOB=social approve -> refused exit 2

## 2026-10-27T08:12+0800 qa-lead (quality gate, merge into main)
status:    done
persona:   qa-lead
ticket:    -
artifacts: .scratch/mission-control/reviews/quality-gate.md; .scratch/mission-control/reviews/qa-release.md (first row-to-node trace)
decisions: NO-GO at 0354503 on strategy v3 §11.1: E1 (BP-01 clause), E2 (G34 no test, G38 narrow, manual parts), E5 (ran 07:48 SGT, outside window), E6 (setup copies stale, browser-publishing.md never drafted), E10 (8 reviews end changes-requested), E13 (no U/R step) not met
decisions: met: E3, E4, E7, E8, E9 (0 crit, 0 major, 7 minor), E11, E12, E14; code is clean, the gaps are procedural or live-only
decisions: live-only: E13, E2 manual (U16, U17, U4, U11, R6), E1 BP-01; recommend Ting Yu defers them at G4 to the go-live gates
questions: Ting Yu at G4: defer the live steps, waive E10 and the E5 timing clause in your own words? rec yes; crew adds the G34/G38 tests and drafts browser-publishing.md first
evidence:  uv run pytest -rs -p no:cacheprovider -o addopts="" (temp data/outputs) -> 3305 passed, 0 skipped, 137.6s; rerun with junit -> 3305/3305 passed, 140.1s
evidence:  E5 snapshot (122 live paths, git status, pgrep) identical before/after; no growth launchd job loaded; main collects 987; pyright 70 vs 76 on main, 0 in new modules

## 2026-10-27T08:01+0800 conductor (gate response)
status:    done
persona:   conductor
ticket:    release
artifacts: reviews/quality-gate.md, reviews/qa-release.md, reviews/release.md, pr-body.md, release-notes.md
decisions: quality gate NO-GO at 0354503. Crew closes what it can rather than waive: developer adds G34 and G38 tests, drafts docs/setup browser-publishing guide, writes the UAT authorized_keys line in uat.md; reviewer re-verifies the eight changes-requested fix rounds (E10). E5 timing: no growth job is loaded in launchd, so a run inside a window would change nothing; recorded, not re-run. E6 copies to outputs/growth/setup/ happen after merge so the copies match main. Live steps (E1 BP-01 clause, E2 manual parts, E13) cannot happen before merge: deferred to the go-live gates, stated in the PR so the merge is the acceptance
questions: -
evidence:  3305 passed, 0 skipped

## 2026-10-27T08:10+0800 reviewer (E10 fix-round re-verification)
status:    done
persona:   reviewer
ticket:    02, 04b, 06, 08, 10, 10b, bp-03, bp-04
artifacts: .scratch/mission-control/reviews/code-review-fix-rounds.md
decisions: all eight reviews close on approve: every blocking finding fixed at 6e341c9, pinned by a passing test, original probes re-run and refused
decisions: open should-fix (not blocking, follow-up tickets): mc 08 ST-2 vocabulary, ST-3 db_state switch twice, S-4 collapse by slot count; partial: mc 06 Sp1 use-by on retry, bp 03 S-10 trailing-block assumption (R1), bp 04 S4 Facebook permalink (deferred)
decisions: closing round kept in one file per the brief; the eight review files are not edited
questions: QA lead: accept code-review-fix-rounds.md as the closing approve of each of the eight for E10's wording? Recommended: yes
evidence:  uv run pytest -rs -p no:cacheprovider -o addopts="" (temp data/outputs) -> 3305 passed, 0 skipped, 139.19s
evidence:  named regression tests -> 18 + 48 + 89 cases passed; orphaned-expect probe ppid=1 refused from a Claude session; mc 08 grace=0 mutation fails its test
evidence:  git status clean; blocked-path grep on main...HEAD -> none

## 2026-10-27T08:09+0800 conductor (E10 closed)
status:    done
persona:   conductor
ticket:    release
artifacts: .scratch/mission-control/reviews/code-review-fix-rounds.md
decisions: accept the fix-rounds file as the closing approve of reviews mc 02, 04b, 06, 08, 10, 10b and bp 03, 04 (E10 met). Seven non-blocking should-fixes become follow-ups: mc 06 Sp1 retry not bounded by use-by (same approved email, same idempotency key, claimed before use-by: at most one delivery), mc 08 ST-1/ST-2/ST-3/S-4, bp 03 S-10 and bp 04 S4 (both wait on R1)
questions: -
evidence:  3305 passed, 0 skipped; 155 regression cases passed; blocker probes refused at HEAD

## 2026-10-27T08:22+0800 conductor (gate gaps merged, PR)
status:    done
persona:   conductor
ticket:    release
artifacts: merge 310cb97 (f8edc8d G34, f44bd12 G38, 9161672 UAT key line, 22e08f6 browser-publishing guide); pr-body.md and release-notes.md updated
decisions: verified by the conductor (UAT entry keeps restrict, from= and the forced command; the guide defers live UI detail to R1); merged. Crew-side exit criteria closed (E2 tests, E6 guide and key line, E10). Live-only criteria (E1 BP-01 clause, E2 manual parts, E13) deferred to the go-live gates; the PR says merging accepts that. Opening the PR into main; Ting Yu merges
questions: -
evidence:  3624 passed, 0 skipped after the merge

## 2026-10-27T09:27+0800 business-analyst (Dispatch growth-control PRD amendment)
status:    needs-human
persona:   business-analyst
ticket:    -
artifacts: ~/projects/discord-automation/prd/pending/prd-discord-dispatch-growth-control-2026-10-27.md
decisions: growth block only under companies.jura; Jura HQ joined as a second, growth-only server; /growth registered there only
decisions: retry-safe set (approve, skip by --ref, read-only and idempotent commands); everything else not retried; one SSH call at a time
decisions: only the gateway runs ssh; the worker reaches growth through a growth_calls queue (D9, SEC-11)
decisions: handoff tasks cut from main, push only their claude/ branch, new BUILT state, apps built re-reported after follow-ups; no preview polling
decisions: tickets GC-00 to GC-08; D7 out
questions: Q1 source of truth: Windows build, private repo under the personal GitHub account; retire the Mac copy (recommended)
questions: Q2 machine: dedicated Ubuntu mini PC; WSL2 laptop for first checks only (recommended)
questions: Q3 D5 needs a Dispatch-owned webhook: yes (recommended)
questions: Q4 Jura HQ as a second server: yes, two channels only (recommended)
evidence:  grep sections and ACs -> 7 sections, ACs for D1-D6, D8, D9; sign-off line present; no real Discord ids
evidence:  Mac copy: 124 files all 2026-09-28 00:38, no hidden files, no .git

## 2026-10-29T00:00+0800 reviewer (drop LinkedIn, PR #4)
status:    done
persona:   reviewer
ticket:    drop-linkedin
artifacts: .scratch/mission-control/reviews/code-review-drop-linkedin.md
decisions: approve: no blocking findings; S1 (switched-off approved item lifts file_upload deny, scope.py:100) and S2 (LinkedIn group via channel other, groups.py:129) are follow-ups
questions: -
evidence:  pytest in detached worktree of 6a9099d (temp data/outputs) -> 3672 passed, 0 skipped
evidence:  .backup copy of live growth.db -> 3 LinkedIn drafts, 0 items/approvals/linkedin groups; branch digest drops them from waiting, writes nothing
evidence:  probes -> S1, S2, N1 reproduced; blocked-path grep -> none

## 2026-10-29T22:44+0800 tech-lead (Dispatch on the Mac) via conductor
status:    done
persona:   tech-lead
ticket:    -
artifacts: discord-automation/prd/pending/prd-discord-dispatch-growth-control-2026-10-27.md §8 (and §6 Q1/Q2, SC-D8, SC-D9, §5.6); MC PRD TY2 note
decisions: Ting Yu 2026-10-29: Mac only, no Windows laptop. Dispatch runs on this Mac: SSH forced command to 127.0.0.1, root-owned authorized_keys; hidden dispatch (gateway, worker, keys) and claude-runner (tasks) users; Seatbelt checks sandbox; LaunchDaemons; GC-0M macOS port before GC-01; GC-08 deploys on this Mac with one paste block. Conductor adopts the recommendation on claude-runner sign-in: allow a setup token readable only by claude-runner if the Keychain sign-in fails under launchd
questions: -
evidence:  dispatch tests on macOS 156 passed, 20 failed (all bwrap); sandbox-exec probe ok

## 2026-10-30T09:56+0800 conductor (rehearsal Part R, real Chrome)
status:    done
persona:   conductor
ticket:    bp-01, bp-07
artifacts: growth PR #6 (crew/fixture-port-rule: 3226e97, c2dbd58, 5952eea, 1729f8e); bp 01 and bp 07 comments; evidence data/growth/uat/rehearsal-2026-10-30/
decisions: four fail-closed defects found and fixed (fixture port in domain rule; publish --add-dir own scratch folder for file_upload; audit strips quotes from real tab lines; audit ignores a trailing system-reminder and counts a new tab as blank, closing CR03 S-10). Instagram rehearsal scenario and composer added. R1b recorded: parameter rules do not narrow Chrome tools; Read denies do block uploads.
questions: -
evidence:  Facebook R1, R2 x6, R3, R4, R5a, R5b, R6 pass; Instagram R1, R2 x6, R6 pass; 3698 passed, 0 skipped
