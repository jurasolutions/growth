# crew-log — growth-blocker-fixes

## 2026-10-24T22:20+08:00 conductor
status:    done
persona:   conductor
ticket:    -
artifacts: spec.md, issues/01-08, audit/
decisions: route bug, G0 given by the user ("yes" to fixing the nine blockers as one bug-route delivery)
decisions: no separate QA repro phase: the audit reviewers already reproduced every blocker (audit/repro/); developers start test-first from those
decisions: tickets grouped by the code they touch so parallel worktrees rarely collide; 02 waits on 01 (both change runner.claude_command)
questions: -
evidence:  uv run pytest on main 6eabfe7 -> 515 passed

## 2026-10-24T22:30+08:00 conductor (G2)
status:    done
persona:   conductor
ticket:    -
artifacts: issues/01-08
decisions: G2 opened by the user: approve tickets 01-08 (08 test hygiene included)
decisions: ticket 06: accept the company's own domain or a subdomain, or a fixed free-mail list (gmail.com, outlook.com, hotmail.com, yahoo.com, icloud.com, singnet.com.sg) published on the company's own site
decisions: ticket 04: flag number words two and above when they count a following noun; "one" and "a" on their own pass
questions: -
evidence:  -

## 2026-10-24T22:50+08:00 developer (03)
status:    done
persona:   developer
ticket:    03
artifacts: branch crew/growth-blocker-fixes-03-auto-pause-without-discord (49060e4, 5fe3755); jura_growth/discord.py, jura_growth/runner.py (_run_locked), README.md, tests/test_discord_down.py
decisions: _send turns httpx transport errors into DiscordError quoting only the error type (messages can carry the webhook URL); every undelivered post goes to the outbox (delivered=0), no retries on transport errors; check_auto_pause in a finally after the alert
questions: -
evidence:  new tests fail on old code; mutation quoting str(error) -> 3 URL-leak tests fail; uv run pytest -> 522 passed; pyright touched files -> no new errors

## 2026-10-24T22:52+08:00 developer (06)
status:    done
persona:   developer
ticket:    06
artifacts: branch crew/growth-blocker-fixes-06-contact-domain (b9485ea rule+config+tests, 869a76d docs+prompt only); scout contact.py, leads.py, settings.py, config/scout.yaml, tests/test_scout_leads.py, docs/scout.md, prompts/scout.md
decisions: address passes when its domain is the site domain or a subdomain, or one of the six G2 free-mail providers; check runs before the page fetch; refusal goes through the normal contact-rejection path
decisions: FREE_MAIL_CONTACTS ceiling in contact.py (not caps.py, to avoid ticket 05); scout.yaml free_mail_contacts may shorten or set []; added providers ignored
decisions: outreach/queue.py doesn't re-check ownership (0 leads recorded so far)
questions: -
evidence:  uv run pytest -> 534 passed; check disabled -> 11 rejection tests fail incl. F4/F4b; pyright touched files -> no new errors

## 2026-10-24T23:00+08:00 developer (04)
status:    done
persona:   developer
ticket:    04
artifacts: branch crew/growth-blocker-fixes-04-numbers-rule-words (06d7b12); jura_growth/brand_check.py, tests/test_brand_check.py
decisions: number words read to their value and go through the digit path (two to nineteen, tens, compounds, "a dozen", "a hundred and fifty", "two thousand"); counted only when a noun follows; "one", lone "a", "one or two", "the two you picked" pass; hyphenated compounds pass like "2-step"
questions: Q1 "We'll send you two options." now fails, as digits already do -> conductor: consistent with the G2 rule, keep. Q2 prompts' numbers bullets mention digits only -> conductor: sent back to the developer to add on this branch
evidence:  uv run pytest -> 541 passed; old vs new on prompt examples, approved claims, app PRDs 001-003 -> 18 cases, 0 changed; pyright touched files -> 0 errors

## 2026-10-24T23:05+08:00 developer (07)
status:    done
persona:   developer
ticket:    07
artifacts: branch crew/growth-blocker-fixes-07-community-negated-days (e35ddd7); jura_growth/agents/community/rules.py, tests/test_community.py
decisions: rules.py only (__init__.py and plan.py read rules.parse); a weekend links ban narrows promotion to Mon-Fri; a clause that both permits and bans days sets parsed=False; bare "not" counts only in clauses naming days; NEG_RE gains can't/cannot/may not/must not/should not ("You cannot share links" now reads as no links); two bans in one comma clause come back unparsed (conservative)
questions: -
evidence:  uv run pytest -> 537 passed; 22 new cases fail on old rules.py; pyright rules.py 8 -> 4 errors, none on changed lines

## 2026-10-24T23:10+08:00 developer (04 follow-up)
status:    done
persona:   developer
ticket:    04
artifacts: branch crew/growth-blocker-fixes-04-numbers-rule-words now cb87ac6 (on 06d7b12); prompts/social.md, scout.md (§5, away from ticket 06), community.md, app-factory.md
decisions: one short line per prompt's numbers rule: a number word from two up is a figure
questions: stale "were/well/wed" sentence in prompts/social.md -> conductor: logged as a follow-up outside this delivery
evidence:  uv run pytest -> 541 passed; 4 files, 12+/9-

## 2026-10-24T23:15+08:00 developer (08)
status:    done
persona:   developer
ticket:    08
artifacts: branch crew/growth-blocker-fixes-08-tests-never-touch-live-files (035628b, 6851f96); schedule.py, timeutil.py, paths.py (1 line), cli.py (4 lines, root callback), tests/conftest.py, README.md, tests/test_isolation.py (new)
decisions: the 4 repo-writing tests were test_plist_is_valid and three test_claude_*; fixed with JURA_GROWTH_PLIST_DIR, JURA_GROWTH_PROMPTS_DIR and a per-test prompts copy
decisions: conftest audit-hook write guard fails any test writing into the repo or jurasolutions/, or opening SQLite there
decisions: frozen-clock refusal in the CLI root callback (status opens growth.db before reading the clock); refuses live data and live outputs
questions: frozen clock also refuse when Discord webhooks are set? -> conductor: logged as a follow-up outside this delivery
evidence:  pytest with and without data/outputs exports -> 530 passed; live mtime diff -> none; JURA_GROWTH_NOW=... jura-growth status -> refusal, exit 1; pyright touched files -> 0 errors

## 2026-10-24T23:20+08:00 developer (05)
status:    done
persona:   developer
ticket:    05
artifacts: branch crew/growth-blocker-fixes-05-outreach-complaints-warmup-spacing (e47b255 warm-up, b0e9f81 live-send gap, e40a969 D1 event cursor); caps.py, suppression.py, migrations/0002_sync_cursors.sql, outreach/send.py, outreach/sync.py, tests, docs/scout.md, config/scout.yaml (comment)
decisions: sync_cursors table holds the last D1 event id; local copy, apply_rows and cursor move commit in one transaction (Discord posts inside can repeat on a retried batch)
decisions: a weaker D1 event never overwrites complained/bounced on a lead; the 10-minute gap counts whole clock minutes
questions: website follow-up: landing-page migrations/0001_toolbox.sql and server/suppression.js must switch to plain inserts before D1 secrets are set in growth -> conductor: added to Ting Yu's setup list (website repo)
questions: digest counts complaints by local suppression reason (complaint after unsubscribe shows 0) -> conductor: logged as a follow-up
evidence:  uv run pytest -> 526 passed; F1, F1b, F2, F3 failed before each fix; removing the id filter or the transaction -> new tests fail; pyright changed files -> no new errors

## 2026-10-24T23:25+08:00 reviewer (06, round 1)
status:    done
persona:   reviewer
ticket:    06
artifacts: reviews/code-review-06.md
decisions: verdict approve; should fix: S1 directory hole stays open for free mail and a directory's own address (role-address swap); S2 prompts/scout.md:23-24 claims refusals the code doesn't make; Standards S1 on_mail_domain duplicates contact.on_domain; keep 869a76d once S2 is fixed
questions: B5 residual -> conductor: inside ticket 06's problem statement, so sent back as fix round 1 rather than a follow-up
evidence:  uv run --frozen pytest -> 534 passed; F4/F4b defect gone; reviewer repros r1-r6 reproduce; merge-tree with 04 and 05 clean

## 2026-10-24T23:28+08:00 reviewer (03, round 1)
status:    done
persona:   reviewer
ticket:    03
artifacts: reviews/code-review-03.md
decisions: verdict approve; should fix: discord.py:170 still raises on a 429 with a non-JSON body or non-numeric retry_after (traceback, no outbox; auto-pause holds); test_discord_down.py rebuilds the outbox() helper from tests/test_scout_support.py
questions: follow-up for audit S8 (outbox text unredacted)? -> conductor: logged as a follow-up
evidence:  worktree uv run pytest -> 522 passed; test_discord_down.py 7 pass on branch, 7 fail on base; 429 HTML probe -> JSONDecodeError
decisions: conductor: the 429 case sits inside the ticket's "no traceback when Discord is down" criterion, so sent back as fix round 1; conductor verifies the small diff instead of a second full review

## 2026-10-24T23:40+08:00 conductor (merge 03)
status:    done
persona:   conductor
ticket:    03
artifacts: crew/growth-blocker-fixes at 347179f (merge of 03: 49060e4, 5fe3755, 6136c8e, 640bc08)
decisions: fix round 1 verified by the conductor (diff read: _retry_after falls back to 1s, cap 10s kept); no second full review
questions: -
evidence:  ticket worktree uv run pytest -> 528 passed; merged branch uv run pytest -> 528 passed

## 2026-10-24T22:56+08:00 reviewer (07, round 1)
status:    done
persona:   reviewer
ticket:    07
artifacts: reviews/code-review-07.md
decisions: verdict changes-requested; Spec B1 regression: _day_rule (rules.py:230-237) bans every named day when any negation is present, so "Promo on Saturdays, no links." opens every day but Sat with parsed=True (base read it right); Spec B2: isn't/aren't and except-words naming no day (rules.py:47-54, 233-234) still invert, inside the ticket's "What to change"; Spec S1 day-clause links ban dropped; Standards S1 _posts_only_on duplicates day_names; NEG_RE widening accepted (errs safe)
questions: -
evidence:  worktree uv run pytest -> 537 passed; test_community.py -> 80 passed; branch tests on base rules.py -> 22 failed; audit repro now fails at line 30 (bug gone); pyright rules.py 8 -> 4; B1/B2/S1 probes reproduced on base and branch

## 2026-10-24T22:57+0800 conductor (note)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: conductor headings before this entry carry estimated times, some ahead of the real clock; from here on they come from the system clock
questions: -
evidence:  date -> 2026-10-24T22:57+0800

## 2026-10-24T22:57+0800 conductor (07 review)
status:    done
persona:   conductor
ticket:    07
artifacts: -
decisions: reviewer 07 (changes-requested, entry above) -> sent back to the developer as fix round 1
questions: -
evidence:  -

## 2026-10-25T01:42+0800 developer (01)
status:    done
persona:   developer
ticket:    01
artifacts: branch crew/growth-blocker-fixes-01-headless-secrets (77cb487 de853d0 4833a60 38bb20a 7ab843d 0fbcee2 4a1d809); new jura_growth/headless.py, tests/test_headless.py, tests/test_community_images.py; paths.py, config.py, cli.py, runner.claude_command, community/plan.py, 4 plug-in __init__.py, prompts/community.md, README.md, agents/__init__.py
decisions: plug-in hook permissions(job) -> headless.Permissions(commands, disallowed_tools), for ticket 02 to reuse; guard applied to every click.Path param; in a run only work/<job> and outputs/growth; app-factory also gets scout insights
questions: Terminal use keeps any non-secret path (no JURA_ROOT limit)? -> conductor: accepted (ticket also requires Terminal use unchanged; in-run rule is the tighter one); reviewer to confirm
evidence:  uv run pytest -> 563 passed; audit repros f9, image_path, groups_joined now refused; pyright 84 (baseline)

## 2026-10-25T01:42+0800 reviewer (04, round 1)
status:    done
persona:   reviewer
ticket:    04
artifacts: reviews/code-review-04.md
decisions: changes-requested; B1 "per" in NOT_COUNTED (brand_check.py:426) lets "forty per cent" pass; should fix: hedged counts, vague scales, re.I lookalike KeyError, "the two of you" and number+verb false positives, duplicated <=12 ceiling; ordinals follow-up
questions: "one or two <noun>" pass? -> conductor: yes (G2 exempts "one")
evidence:  worktree pytest -> 541 passed; 92 probes old vs new reproduce B1/S1-S5
decisions: conductor: sent back as fix round 1 (B1 + in-scope should-fix); ordinals logged as follow-up

## 2026-10-25T01:43+0800 conductor (merge 06)
status:    done
persona:   conductor
ticket:    06
artifacts: crew/growth-blocker-fixes merge of 06 (b9485ea 869a76d b0b13f1 323f6fc 16d909c c7924c1)
decisions: fix round 1 verified by the conductor (diff read: is_site_root rejects listing pages; swap only from the company's domain; duplicate removed); no second full review
questions: residual (directory home page + free mail, another party's free mail on the site) recorded in issues/06 Comments -> added to Ting Yu's setup list: watch #scout-leads domains in the shadow trial and decide a name-to-domain rule before mode: live
evidence:  ticket worktree pytest -> 544 passed; merged branch pytest -> see next line

## 2026-10-25T01:44+0800 conductor (merged branch check, reviews 05 and 08)
status:    done
persona:   conductor
ticket:    05, 08
artifacts: reviews/code-review-05.md, reviews/code-review-08.md
decisions: merged branch after 06 -> uv run pytest 557 passed
decisions: reviewer 08 approve; S1 schedule.render() skips paths.writable() (JURA_GROWTH_PLIST_DIR could target inputs/); S2 README overclaims the guard -> sent back as fix round 1
decisions: reviewer 05 approve; S1 parallel send-due both send live (no lock around check, Resend call, record); S2 cursor ahead of a recreated site table skips a complaint silently (fail closed); R1/ST1 Discord posts inside the sync write lock -> sent back as fix round 1
questions: landing-page follow-up (plain inserts, AUTOINCREMENT) in the PR body as a pre-live prerequisite? -> conductor: yes
evidence:  reviewer 05: pytest 526, repros R1-R4 reproduce; reviewer 08: pytest 530 with and without exports, live mtimes unchanged

## 2026-10-25T15:00+0800 conductor (merge 08; reviews 01; fix rounds 04, 05, 07)
status:    done
persona:   conductor
ticket:    01, 04, 05, 07, 08
artifacts: crew/growth-blocker-fixes at c9460c8 (merge of 08: 035628b 6851f96 24f0440 e22839a)
decisions: 08 fix round verified by the conductor (render() now goes through paths.writable()); merged
decisions: reviewer 01 approve; should fix P1 case-sensitive is_secret_file on APFS (.ENV), P2 keychain resolved on every CLI process, S1 duplicate PNG check, S2 secret patterns defined 3 times -> sent back as fix round 1; deviation (no JURA_ROOT limit outside a run) confirmed harmless
decisions: fix rounds done for 04 (62c7ae5, 6f348e9), 07 (fe35657), 05 (6df5385 235b0aa 49e365c 4977f57) -> each back to its reviewer for round 2
questions: 05: S2 pause recovery is a manual sqlite3 cursor reset -> conductor: acceptable for now, reviewer to confirm
evidence:  08 worktree pytest -> 531 passed; merged branch -> 573 passed; reviewer 01 merged tree -> 605 passed, merge-tree clean, 11 dontAsk bypass probes denied

## 2026-10-25T15:03+08:00 reviewer (07, round 2)
status:    done
persona:   reviewer
ticket:    07
artifacts: reviews/code-review-07.md (round 2 section added above round 1)
decisions: verdict changes-requested; round-1 B1, B2, S1, Standards S1, N1-N4 all fixed and re-probed
decisions: R2-B1 blocking: a negation about something else before a day permission still bans that day (rules.py:166-175); "No links, promo on Fridays." and "No selling, but promo thread every Sunday." open every other day with parsed=True; base right; present since e35ddd7, missed in round 1
decisions: R2-S1 apostrophe-less isnt/arent/wont; R2-S2 avoid/refrain/promo-free; R2-N1 "no promotion on weekdays only"
questions: -
evidence:  worktree uv run pytest -> 565 passed; test_community.py -> 108 passed; pyright rules.py 4 errors, pre-existing lines 100 and 284; round-1 probes re-run plus 30 new inputs

## 2026-10-25T16:50+0800 conductor (merge 05, 04, 01; 07 decision)
status:    done
persona:   conductor
ticket:    01, 04, 05, 07
artifacts: crew/growth-blocker-fixes: merges of 05 (round 2 approved), 04 (fix round 2 f8eb442, verified by the conductor), 01 (fix round d6c6e6a 11c95b0 695aba1, verified by the conductor)
decisions: runner.py import conflict between 05 (locks) and 01 (headless) resolved by keeping both
decisions: 07 round 2 changes-requested after two rounds -> needs-human; Ting Yu chose "always confirm day rules": any rule naming a day is parsed=False and needs rules_ok; sent to the developer as fix round 2
questions: -
evidence:  merged branch uv run pytest -> 693 passed

## 2026-10-25T17:03+0800 conductor (02 and 07 done; Ting Yu's new direction)
status:    done
persona:   conductor
ticket:    02, 07
artifacts: crew/growth-blocker-fixes-02-community-blocks-facebook (e35c1e5); crew/growth-blocker-fixes-07-community-negated-days (14614a8)
decisions: 02: Claude Code 2.1.310 treats *.d as subdomains only, so each domain gets WebFetch(domain:d) and WebFetch(domain:*.d), built in the community plug-in's permissions(); probes on .invalid hosts confirm; pytest 707
decisions: 07: any day-naming rule is parsed=False; Ting Yu confirms with community set <id> promo_days= post_days=; migration 0002_confirmed_days; no suggested days shown; pytest 601, trial merge 779
decisions: Ting Yu kept ticket 02 (research stays search-only) although posting will move to Chrome
questions: -
evidence:  -> both sent to review

## 2026-10-25T17:09+0800 reviewer (02, round 1)
status:    done
persona:   reviewer
ticket:    02
artifacts: reviews/code-review-02.md
decisions: approve; should fix SP1 URL/path/port entries make dead deny rules (fail loudly), SP2 stale audit docstring, ST1 duplicated test helper -> conductor: sent back as fix round 1, conductor verifies
questions: -
evidence:  worktree pytest -> 707 passed; argv diff: other jobs identical, community gains apex + *. rules for 7 domains; dontAsk probe on .invalid confirms both rule forms needed

## 2026-10-25T17:10+08:00 reviewer (07, round 3)
status:    done
persona:   reviewer
ticket:    07
artifacts: reviews/code-review-07.md (round 3 section added above rounds 2 and 1)
decisions: verdict changes-requested; the design holds: all 179 day-naming inputs from both rounds and the probes are closed until confirmed; migration safe; no-day rules parse; merge-tree clean
decisions: R3-B1 blocking: the day detector misses #SelfPromoSaturday, wknds/wkends, weeknights, "week days"; these parse as promotion allowed every day, parsed=True, and confirmation is never asked (rules.py:36-38, 204); fix: looser names_days detector
decisions: R3-S1 "once a week"/"1st of month"/"public holidays only" read as a blanket permission; nits R3-N1, R3-N2; release note: confirmed day-rule groups close until Ting Yu sets days
questions: -
evidence:  worktree pytest -> 601 passed; test_community.py -> 144 passed; merge-tree vs 4a7859e clean (7a4f327), its pytest -> 779 passed; 4a7859e-built db migrated by 14614a8 code: rows intact, applied once; pyright no new errors

## 2026-10-25T17:10+0800 conductor (07 round 3)
status:    done
persona:   conductor
ticket:    07
artifacts: -
decisions: reviewer 07 round 3 changes-requested (detector misses hashtags, abbreviations, frequency and holiday rules); design otherwise holds (179 inputs closed, migration safe, merge clean)
decisions: conductor applies Ting Yu's "always confirm day rules" strictly: every group needs confirmed promo_days and post_days before planning, whatever its rules say; the detector becomes a hint only; sent as fix round 3, conductor verifies (each community post also needs Ting Yu's Discord approval under the new browser-publishing PRD)
questions: -
evidence:  reviewer: worktree pytest 601, merged tree 779

## 2026-10-25T17:13+0800 conductor (merge 02)
status:    done
persona:   conductor
ticket:    02
artifacts: crew/growth-blocker-fixes at bc86a15 (merge of 02: e35c1e5, f7fd32d)
decisions: fix round verified by the conductor (non-bare entries raise BlockedDomainError; fetch_denials() builds both rule forms); merged
questions: -
evidence:  merged branch uv run pytest -> 714 passed

## 2026-10-25T17:17+0800 conductor (merge 07; all tickets merged)
status:    done
persona:   conductor
ticket:    07
artifacts: crew/growth-blocker-fixes at dacf740 (merge of 07: e35ddd7 fe35657 14614a8 a8e33b1); tickets 01-08 all merged
decisions: fix round 3 verified by the conductor (confirm_days required for every group; detector is a hint only); merged
questions: -
evidence:  merged branch uv run pytest -> 975 passed

## 2026-10-25T17:30+0800 reviewer (final)
status:    done
persona:   reviewer
ticket:    final
artifacts: reviews/code-review-final.md
decisions: verdict approve; no blocking finding on either axis, security or blocked paths
decisions: should fix Spec SP1 #community summary hint and SP2 set --help omit promo_days/post_days (refused as printed); SP3 runner preamble invites refused discord/<group> --help calls
decisions: should fix Standards ST1 runner _lock_held duplicates locks; ST2 hand-built log record; ST3 path-within check x3 (Path.is_relative_to); ST4 publish() shadows images module; ST5 FREE_MAIL_CONTACTS ceiling outside caps.py
questions: release notes: confirmed groups closed until days set; website D1 append-only before D1 secrets; first sync replays from id 0 -> conductor: put all three in the PR body
evidence:  uv run pytest -> 975 passed (with and without temp exports); git status and live mtimes unchanged
evidence:  main-built db opened by branch -> core/0002 and community/0002 applied once, rows intact; main code still runs on migrated db
evidence:  real-process probes -> .env and symlink refused (exit 2), secrets masked; pyright 76 (baseline 84)

## 2026-10-25T17:54+0800 conductor (final review)
status:    done
persona:   conductor
ticket:    final
artifacts: reviews/code-review-final.md
decisions: final review approve; should-fix SP1-SP3 (user-facing messages) and ST1/ST3 sent to a developer as ticket 09 on the feature branch; ST2, ST4, ST5 left as follow-ups; the three release notes go in the PR body
questions: -
evidence:  reviewer: pytest 975 with and without exports; db built at main upgrades cleanly; .env and symlink refused by a real CLI process

## 2026-10-25T18:01+0800 conductor (merge 09)
status:    done
persona:   conductor
ticket:    09
artifacts: merge of 09 (d9f0066 5f41e18 06e26e6 55ba563)
decisions: verified by the conductor; merged; worktree removed
questions: -
evidence:  merged branch uv run pytest -> see commit

## 2026-10-25T18:07+0800 release-manager
status:    needs-human
persona:   release-manager
ticket:    -
artifacts: reviews/release.md, pr-body.md (both uncommitted; commit command in release.md)
decisions: no version bump: 0.1.0 never bumped, no tags, nothing reads it; release notes in the PR body (no CHANGELOG)
decisions: merge with a merge commit, so rollback is git revert -m 1 <merge sha>
decisions: no down migrations: both additive and ignored by main (final review); manual down SQL written anyway
questions: G4: open a PR, merge locally, keep the branch, or discard? -> recommend open a PR (commands in release.md)
questions: waive the missing quality gate, and the conductor-verified final rounds of 04 and 07 (last written verdict changes-requested; final review approves)? -> recommend waive
questions: 3 frozen-clock social drafts dated 2026-10-26 still in live growth.db (infra A6) -> recommend delete them before installing launchd jobs, or accept one skipped Monday
evidence:  uv run --frozen pytest at db218a0, temp data/outputs -> 987 passed in 21.82s
evidence:  git ls-remote origin -> main 6eabfe7 = merge-base; branch not on the remote
evidence:  git diff main... blocked-path and secret greps -> only fake fixtures; gh auth status -> not logged in

## 2026-10-25T18:39+0800 conductor (G4)
status:    done
persona:   conductor
ticket:    -
artifacts: -
decisions: G4 opened by Ting Yu: open a PR into main; waivers accepted as recommended (conductor-verified final rounds of 04, 07, 09; final review approved the merged tree)
questions: gh login is Ting Yu's step
evidence:  -

## 2026-10-25T18:46+0800 conductor (close)
status:    done
persona:   conductor
ticket:    -
artifacts: PR https://github.com/jurasolutions/growth/pull/1 (crew/growth-blocker-fixes -> main)
decisions: G4 carried out: branch pushed, PR opened with pr-body.md; Ting Yu merges on GitHub; no crew worktrees remain
questions: -
evidence:  git worktree list -> main checkout only; uv run pytest at db218a0 -> 987 passed
