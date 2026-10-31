# Quality gate: approvals first, feeds after, social depth

*QA lead, 2026-11-01. Checked against `reviews/test-strategy.md` §7.*

**Decision: GO WITH CONDITIONS**

**Branch:** `crew/approvals-first-social-depth` @ `a43e36a`, pushed. `origin/main` is `019133d`, and the branch holds it. `a43e36a` adds only records under `.scratch/` after `bee9118`, so review 13's approval covers the code at the tip.

**Why this decision, in four sentences.** The suite is green on a fresh run: 5967 passed, none failed or skipped. No open defect is critical or major by the strategy's definitions. X5, X6 and X13 aren't met as worded, and in each case the wording, not the behaviour, is what fails, so I record corrected wording below for Ting Yu to accept or refuse. It is a go only if he accepts those amendments, confirms that `inputs/icp.md` is his, and answers X15 at G4.

**The PRD is still unsigned (§7), and Ting Yu hasn't read it.** G4 is the first point at which any of this reaches him.

## Exit criteria

| # | Verdict | Evidence |
|---|---|---|
| X1 | **Met** | Fresh run: 5967 passed, 0 failed, 0 errors, no `SKIPPED` line, in 365 s. The floor is 3980. See "Fresh run" for how and where |
| X2 | **Met** | 108 distinct test names in `qa-final.md` "Trace" and "Classes", read against my junit. 107 passed. The other is `test_every_platform_ships_in_draft_mode`, the old name QA listed beside its new one. See "Trace" |
| X3 | **Met, two changes listed** | Appendix A against `origin/main`: `same` 22 times. `CHANGED test_hashtag_limits_and_position`: Instagram's cap 8 to 5, the same assertions at the new number (technical N9, PRD amendment). `CHANGED test_digest_figures`: the diff is the `monkeypatch` argument and one `pw.social_config(monkeypatch, browser=())` line, with no assertion touched (AF5, A13). Both are listed in `qa-final.md` |
| X4 | **Met** | All 16 Class A and B functions named in `qa-final.md`, twins included, parse identically at `f0db1e5`, where QA read them, and at the tip |
| X5 | **Not met as worded. Met as amended (A1).** No rule moved | See "Ruling on X5" |
| X6 | **Not met as worded. Met as amended (A2).** No rule lowered. Two rules moved, both tighter | See "Ruling on X6" |
| X7 | **Met for the branch. One file outside it rests on inference, and C2 closes it** | See "Ruling on X7" |
| X8 | **Met** | The PC3 file: 62 cases passed, none skipped. A literal `grep -c 'offline=True'` on it gives 0, because every render goes through `card_probe.probe`, whose default is `offline=True`, and the file has no `offline=False`. `test_a_render_in_the_suite_cannot_reach_the_network` passed. Amendment A4 fixes the check. Fresh matrix: 34 of 34, listed under "Pictures" |
| X9 | **Met. No waiver needed** | Fresh render with `offline=False` at the tip: 34 of 34, listed under "Pictures". The web fonts did load: `headline-only` at 1200×630 fits at 1.0, against 0.72 on fallback fonts |
| X10 | **Met** | `crew-log.md` at G2 and G3 records every B and S decision. The B1 to B6 and S cases in `qa-final.md` "Trace" passed in my junit, for example `test_a_card_is_decided_by_1700_and_used_by_1800` and `test_the_1805_digest_closes_an_unanswered_card_and_counts_it` |
| X11 | **Met** | `test_social_prompt.py`: 64 passed. The grep over `prompts/social.md` and `docs/social.md` prints nothing |
| X12 | **Met: 0 critical, 0 major, 13 minor, each with an owner** | See "Ruling on X12" |
| X13 | **Not met as worded. Met as amended (A3).** The chain counts | See "Ruling on X13" |
| X14 | **Met** | `qa-final.md` lists its commands, and none is `jura-growth run`, `schedule install`, `schedule render` or a real send. `uat.md` was dry-run and corrected, last at `27efa99`, and `test_uat_seed_script.py` passed at the tip. My commands are under "Fresh run". The incidents are weighed below, because X14's check reads only QA reports |
| X15 | **Open: listed as a waiver for G4** | Ting Yu has not run Parts P to C. It is his to run or to waive, and I am not granting it. The PR body must also open with "What merging switches on" and name the parts not run. No PR exists yet, so that half is checked at release |

## Ruling on X5

**A true "no rule moved".** The first grep prints the 5 lines QA and the developer reported. I read each one, and every one is a pytest parameter called `words` that holds expected text, not the config key:

- `tests/test_approvals_first.py:253`
- `tests/test_card_readability.py:23` and `:33`
- `tests/test_schedule_drift.py:85`
- `tests/test_uat_seed_script.py:47`

**The wording was wrong.** `words=` and `"words"` match any parameter of that name, and X5 is about config. Its second half has the same fault: read literally, "no `+` line adds `skip`" prints dozens of lines, because `skip` is the product's own word for a decision.

**What I checked instead.** Pytest's own skip and xfail spellings: 0 added lines. Junit: 0 skipped. Added test lines that override `themes`, `min_items`, `needs_visual`, `min_sources`, `hashtags_max` or `chars_max`: none. Two added lines read `themes`, and neither sets it.

## Ruling on X6

The literal check prints `approvals.py` (+9, -4) and `caps.py` (+3, -2), and `tests/gate_adapter_social_post.py` shows 3 added and 4 deleted. Each file is ruled on its own.

| File | Is it a true "no rule moved"? | Evidence |
|---|---|---|
| `jura_growth/approvals.py` | **Yes** | With the 3 new constants inlined, it parses to the same syntax tree as `origin/main`. `decide()`, `use()` and the hash are as they were |
| `jura_growth/caps.py` | **Yes** | It parses to the same syntax tree as `origin/main`. Only a comment changed, and no limit moved |
| `tests/gate_adapter_social_post.py` | **No: it follows the one rule that moved on purpose** | The record calls these clock literals, and they aren't. The 4 deleted lines are a docstring phrase, an import, and two lines reading the window's end, replaced by `limits.decide_by_on(day)`. The adapter now raises items against the 17:00 decide-by, which PRD amendment 2026-10-31 and `[B2]` ask for. It asserts nothing, so no assertion was lost |

`tests/test_approval_gates.py` and `tests/test_terminal_refusal_every_kind.py` have no diff, and 169 and 236 cases passed. `approvals_cli.py`, `origin.py`, `claim.py` and ADRs 0003 and 0004 have no diff.

**"No rule moved" is true of the files X6 names, and not of the system.** Two rules moved, outside X6's list, and both are tighter:

1. **The decide-by for `social-post` is 17:00, where it was 18:00.** The use-by stays 18:00. A claim's replacement raised after 17:00 keeps until 18:00, the same as main gave it, so nothing is loosened.
2. **`SocialPost.on_approve` and `OutreachEmail.on_approve` now refuse a typed approval when the card hasn't gone out.** This does change how an approval is decided, in plain English, even though `decide()` is untouched. PRD §3 puts "any change to how an approval is decided" out of scope, and the amendment's line "It changes no decision, claim or binding rule" reads more generously than I would. It is recorded in the PRD and it is stricter, so it isn't a defect. It must be named in the PR body, because it removes typed approval as a route during a Discord outage, including for live outreach.

**Was the wording wrong for what the PRD asked?** In part.

- **`caps.py`:** wrong. The old comment said a post's decide-by is the window's end, which `[B2]` makes false, so "prints nothing" asked for a stale comment.
- **The adapter:** wrong. "Clock literal" didn't foresee `[B2]` reading the deadline through a helper.
- **`approvals.py`:** the wording was fine for the PRD. A byte-for-byte proxy is stricter than the PRD, and the branch broke it with a refactor the PRD didn't need. The syntax tree proves it harmless. It could be reverted in one commit if Ting Yu would rather keep that file clean.

## Ruling on X7

**The branch is clean.** `git diff --name-only origin/main...HEAD` lists 222 files, none under `data/`, `inputs/`, `design-system/`, `.github/` or `launchd/`, and not `.env`.

**The `find` prints one file:** `inputs/icp.md`, 2,527 bytes, modified 2026-11-01 01:38:12. The check allows this only for a file Ting Yu changed himself, named in a QA report. It is named in `qa-final.md`. That he changed it is an inference, and here is what it rests on.

| Evidence | What it shows |
|---|---|
| The file's birth time, 2026-10-24 01:18:57, is the draft's birth time to the second | A copy that kept its dates, not a file written fresh |
| The draft was last opened at 01:35:48, `inputs/` changed at 01:37:09, `icp.md` was opened at 01:37:12, and it was saved at 01:38:12 | Opened from the desktop, by the `com.apple.lastuseddate#PS` attribute on both files, then saved a minute later. That is a person's pace. An `open` from a shell could set the same attribute, so this leans and doesn't prove |
| The diff against the draft removes only "(draft)" from the title and the block telling him how to use it | Exactly what the draft's own instruction says to do. The ICP's content is the draft's, not customised |
| In 149 Jura transcripts active since 02:00 on 2026-10-31, no tool call names `icp.md` between 00:00 and 02:06. The first reads after it are at 02:06 and 02:20:25, and the second matches the file's access time | No recorded agent did it. This repeats the conductor's search more widely |
| The live run log from 01:20 to 01:40 holds only `run.quiet` and a Dispatch `apps handoffs` poll every 5 minutes | One poll fell at 01:38:11, a second before the save. It keeps its 5-minute beat and that command writes no input, so I read it as coincidence |
| `paths.writable` refuses `inputs/`, and no code on the tip writes that file | The engine doesn't write it |

**Limits of that evidence.** Headless job runs use `--no-session-persistence`, so they leave no transcript. I scanned only project folders with `jurasolutions` in the name, to keep to the company boundary. So this is a strong inference and not proof.

**Ruling: X7 holds on the evidence, and Ting Yu closes it with one line at G4 (C2).** If he says it wasn't him, this is a write to `inputs/` by something unknown, which is critical by the strategy's definition. The decision then becomes no-go until it is explained.

**Two things follow whoever wrote it.**

- `uat.md` L1 step 4 and PRD §5 still tell him to move the draft into place after merge. Run now, that overwrites his file and brings the draft's header back. He should skip it (C6).
- With the ICP in place, scout research on `main` no longer stops for it, and `config/scout.yaml` is `mode: live`. Real outreach cards can now reach #approvals whether or not this branch merges, which makes the first item under X12 reachable today.

## Ruling on X12

**Open defects: 0 critical, 0 major, 13 minor.**

**None of these is a major this release must not carry.** The strategy's ladder has no rung for a human gate weaker than it should be outside the §2 criteria. "Minor" reads oddly for the first few, and I'm not calling them trivial. I tested each against the two definitions that could apply:

- **Critical: can it post or send without approval of that exact content?** No. Approval stays bound to the hash, and a person has decided.
- **Major: does a §2 criterion fail?** No. AF1's "exact text" and the 2026-11-01 amendment's "no card, no approval" cover `social-post` and `outreach-email`, and the amendment carves out the rest.

| # | Defect | Severity | Owner | Blocks? |
|---|---|---|---|---|
| 1 | **Ticket 12: a masked outreach card can be approved.** Fresh probe: the card reads `> [name removed] delivery firms sign on paper.`, the approval is recorded, and one email goes out holding the real words "Most delivery firms" and no marker. So the ticket's open question is answered: the prospect gets the real word | Minor, first in line | Ting Yu schedules, developer | No, for the reasons below |
| 2 | Ticket 12: a masked `community-post` card. Not reachable: `community.yaml` is `browser: false` | Minor | As above | No, while that switch stays off (C5) |
| 3 | Ticket 12: `app-release` accepts a typed approval with no card. Fresh probe: recorded, and `release-plan` prints the merge, which he then runs by hand | Minor | As above | No |
| 4 | Ticket 12: `app-build` accepts a typed approval with no card. Fresh probe: recorded, "Handed to Dispatch". It builds on its own branch, and its release has its own approval | Minor | As above | No |
| 5 | Ticket 12: `group-rules` accepts a typed approval with no card. Fresh probe: recorded. It unlocks community posts, which have their own gate | Minor | As above | No |
| 6 | Ticket 12: `community-post` and `group-join` accept a typed approval with no card. Not reachable, as in row 2 | Minor | As above | No, while that switch stays off (C5) |
| 7 | **Review 13's F1: a loose env file hides each refusal's reason.** Fresh probe: at 0644 the reply is `refused: the command was not understood`, status `pending`. At 0600 the full reason arrives. At 0644 a skip's reply carries the file's path and the `chmod` line, and no value | Minor, with a mandatory check (C3) | Ting Yu for the mode, developer for ticket 12 | No, for the reasons below |
| 8 | Review 13's F2: `BadArgs` needs its `refused:` prefix, and only the README enforces it. All have it today | Minor | Developer, ticket 12 | No |
| 9 | Review 11's S2: a request approved with no card before this merge can still go out | Minor, with a read-only check (C4) | Ting Yu | No |
| 10 | ST-S2: `CLAUDE.md`'s numbers rule doesn't mention the "30-minute call" allowance | Minor | Ting Yu | No |
| 11 | "Growth is on it" lists a refused card's `P-nnnn` until it lapses (review 13's nit) | Minor | Developer, ticket 12 | No |
| 12 | `uat.md` L1 step 4 and PRD §5 are stale, since the ICP is in. `uat.md` Part L and PRD §5 don't yet hold the file-mode check or S2's check | Minor | Conductor, before the PR | No, but do it before G4 |
| 13 | Tickets 01 to 04 still say `ready-for-agent`. `docs/agents/crew.md` is stale on suite size, Python and pyright | Minor | Conductor | No |

**Why row 1 doesn't block, as the closest call.**

- He sees the marker, so he isn't misled silently.
- The card names `jura-growth outreach preview <id> --html`. My probe of `preview` shows the real words, so he can read them.
- The real text has already passed the email's checks. Discord's mask hides a word from him; it doesn't let an unchecked word through.
- It predates this branch and lives on `main` today. Merging closes outreach's no-card route and adds its feed line, so holding the release keeps the defect and also keeps that route open.

**Against that, his own words in PRD §1 were "Same for everything, like scout drafts", and he hasn't read the carve-out.** That is why it is in C5 for him to accept. If he wants exact text as a rule for outreach too, it becomes a §2 criterion, this row becomes major, and ticket 12 goes first. My recommendation is to carry it, and to make ticket 12 the next job, since the ICP means these cards can now appear.

**Why row 7 doesn't block, though review 11's B2 did.** B2 hit every no-card refusal, with no way around it. F1 needs a loose file, and one command clears it. It fails safe: nothing is approved on the first call. `pending` exits 0, so by reading the code its "no card yet" should still arrive after the warning. I didn't walk that. But if the file is loose, the retry hazard is live, so C3 isn't optional. **I did not check the live file's mode, and only Ting Yu may.**

### A limit the brief didn't list: the numbers rule

The strategy's critical list includes "an unevidenced figure passes the gate". Three forms still pass, and read literally that wording catches them. Fresh probe at the tip and on `origin/main`:

| Sentence, `social-card` channel | `origin/main` | Tip |
|---|---|---|
| `A 500-store chain.` | pass | pass |
| `The 2000 shops use it.` | pass | pass |
| `We help shops. 62 of them renew.` | fail, and passes with a source | the same |
| `We helped 62 marketing teams.` | **pass, and passes with a source** | **fail, and fails with a source** |
| `A 5,000-user rollout.` | fail, and passes with a source | the same |

**I don't rank these as open critical defects, and this is judgement, not the mechanical check.** The strategy's R2 table is covered by `test_social_figures.py`, which passed. None of these forms is new, and the branch is stricter than `main`. The 2026-11-01 amendment names them as known limits with his read of the card as the control, and AF1 now guarantees the card shows those words unmasked. **That control only counts if he knows it is his.** He hasn't read the amendment, so it is in C5. If he refuses it, these are critical, and no waiver covers a critical.

## Ruling on X13

**The chain counts.** A review file is a record of a moment, and rewriting it to approve later would falsify it. What X13 protects is that no blocker stays open, and I traced every one. I would not count a chain with a link nobody verified, so one link I checked myself.

| Review | Blocker | Closed by | Verified by |
|---|---|---|---|
| 01 | B1 | Round 2 commits | Round 2, same file |
| 01 | R2-B1 | `0dcd665` | Round 3, same file |
| 01 | R3-B1 | `bd78cac`, the conductor's fix. The reviewer allowed no round 4 | **This gate:** `A 5,000-user rollout.` fails, and its cases in `test_brand_check.py` and `test_social_figures.py` passed |
| 02 | SP-B1, SEC-B1, SEC-B2 | Round 2's fixes | Round 2 table, same file |
| 02 | R2-B1, R2-B2 | Fixes after round 2 | `code-review-final.md`: "Holds", except the typed-approval part, which became SP-B2 |
| final | SP-B1 | Ticket 05 | `code-review-10.md`; `test_cards_nobody_answered_are_not_called_no_card_or_waiting_at_the_1805_digest` passed |
| final | SP-B2 | Ticket 09 | `code-review-10.md`, its claims table |
| 10 | B1 | Ticket 11 | `code-review-11.md` §1 |
| 11 | B2 | Ticket 13 | `code-review-13.md` §1 |
| 03, 13 | None | - | Both approve |

**The last review of the code at the tip approves.** Review 13 was a narrow pass over its delta. The whole branch was last read at the final review, and reviews 10, 11 and 13 read each delta after it.

## Amendments for Ting Yu to see

Only X9 and X15 can be waived, and these aren't waivers. They correct what a check measures, and the reason is above. `test-strategy.md` itself is unedited. If he refuses one, that criterion reverts to its first wording and is not met, so the decision becomes no-go until the fix beside it is done.

| # | Criterion | Corrected wording | If refused |
|---|---|---|---|
| A1 | X5 | Added test lines outside the depth and visual files set no `min_items`, `needs_visual`, `min_sources`, `min_hosts` or a theme's `words` in config, read line by line: a pytest parameter named `words` doesn't count. `git diff` adds no match for `pytest\.skip\|mark\.skip\|skipif\|xfail\|importorskip`, and junit shows 0 skipped | Rename 5 parameters |
| A2 | X6 | `approvals.py`, `approvals_cli.py`, `origin.py`, `agents/publish/claim.py`, `caps.py` and ADRs 0003 and 0004 parse to the same syntax tree as main, once any new module-level string constant is inlined. `test_approval_gates.py` and `test_terminal_refusal_every_kind.py` have no diff. `gate_adapter_*` deletes no line, or each deleted line is listed in a QA report under `[B2]` as following the decide-by. Every tightening of a decision outside these files is named in a PRD amendment | Revert the constants and the comment. The adapter's lines can't revert while `[B2]` stands, so that half would need his ruling anyway |
| A3 | X13 | Every blocker in every `code-review-*.md` is traced to a later review, or to a check recorded in this gate, that closes it. The last review of the code at the tip approves, with no open blocker | Have the reviewer append an approving line to each of 5 files |
| A4 | X8 | Replace the `grep -c` with: the PC3 file has no `offline=False`, and `test_a_render_in_the_suite_cannot_reach_the_network` passes | None needed: the behaviour holds either way |

## Conditions

Each is for Ting Yu to do or accept at G4. With all of them, this is a go.

| # | Condition | What happens otherwise |
|---|---|---|
| C1 | **Accept A1 to A4,** or refuse any of them | Refused: no-go until the fix beside it is done |
| C2 | **Confirm that `inputs/icp.md` at 01:38 today was his own step.** One line | Not his: X7 fails as a critical, no-go until explained |
| C3 | **Check the live env file's mode himself,** preferably before merging: `stat -f '%Lp' repos/growth/.env` should print `600`. If it doesn't, `chmod 600 repos/growth/.env`. No agent may do this | While it stays loose, F1's retry hazard is live, so nothing should be approved by typing |
| C4 | **After merge, once, read-only:** `sqlite3 -readonly data/growth/growth.db "SELECT id, kind, decided_at FROM approvals WHERE status='approved' AND used_at IS NULL AND posted_at IS NULL"`, from `jurasolutions/`. Any row is a request approved with no card before this merge, and it can still go out, so skip it if he wants it stopped | S2's rare case goes out unnoticed |
| C5 | **Accept the carried items:** ticket 12's masked outreach cards and no-card kinds (X12 rows 1 to 6), the three known limits on the numbers rule, and keeping `community.browser` off until ticket 12 is done. Or hold the release for ticket 12 | Outreach masked cards refused: ticket 12 first. Number limits refused: critical, no-go |
| C6 | **Skip `uat.md` L1 step 4.** The ICP is already in, and moving the draft overwrites it | His file is replaced by the draft with its header |
| C7 | **X15: run Parts P to C of `uat.md`, or waive them at G4.** This is his waiver only | Not answered: no merge |

**For the conductor, before the PR:** correct `uat.md` L1 step 4 and PRD §5, and add C3 and C4 to the after-merge steps. The brief says the after-merge steps carry the file-mode check, but at this tip neither `uat.md` Part L nor PRD §5 holds it or S2's check. The PR body must open with "What merging switches on", and must name the parts of UAT not run, the end of typed approval during an outage for social and outreach, ticket 12, the number limits and the incidents below.

**Waivers Ting Yu may grant at G4:** X15. X9 is met, so it needs none.

**To turn this into a plain go:** C1, C2, C5 and C7 answered yes, and C3 reporting `600`. C4 and C6 are after-merge steps.

**To turn it into a no-go:** a refusal under C1 or C5's number limits, or "not mine" under C2.

## Incidents weighed

None changes a criterion above. All belong in the PR body, because he hasn't seen them.

| Incident | Weight |
|---|---|
| **The real `claude` started by a mutation test, about 2 minutes, ticket 02** | Real tokens on temp data, with Discord off and no `.env` in that worktree. The conductor's check was sound but indirect. The runner passes `--no-session-persistence`, so no transcript exists, and I found none, so nobody can say what that session read. If `JURA_ROOT` was exported, as the operating card says to, its `--add-dir` was the live root. Nothing shows it wrote anything, and the test now uses a stand-in. My run called the stand-in 0 times. The suite still has no in-process guard against a subprocess reaching a real `claude`, so keeping a stand-in first on `PATH` stays a rule for agents |
| **The commit script behind `5b5404c`** | A process breach: it skipped the harness's worktree guard. The content is `plan.py` and its test, with the right identity on the right branch, and review 10 read it. No effect on the code |
| **Live `.env`: a count-only grep by review 10's security pass** | A read of a blocked path, against the brief. Counts only, no value |
| **Live `.env`: opened by the suite through the seed's check, ticket 10's runs** | Read into memory and compared, never printed. Ticket 11 closed this. My run opened the canary 0 times, and all 22 `.env` opens were files tests planted themselves |
| **Live `.env`: stats during red runs, and one refused open with a `realpath`** | Metadata only, and the reviewer disclosed its own. The guard now uses `abspath`, and I couldn't show from the real tree that no stat remains, so I used a stand-in |

**Together, the `.env` touches are several breaches of the same rule, and no value leaked as far as I can check.** No write to it is recorded, and the strategy's critical line lists writes to `inputs/`, `design-system/` and live data, so they aren't defects. My scan for webhook-shaped values found none in the feature folder or the branch's diff. Three old probe files in the session scratchpad hold planted ones, whose tokens run 13 characters or fewer, where a real one is far longer. I see no reason to rotate on this evidence. That is his call.

**Not this feature:** `~/.claude/projects` holds real `claude` sessions in pytest temp folders, for `test_claude_p_waits_for_a_back...` and `test_a_handoff_prompt_starts_c...`. Neither test is in this repo at the tip or on main. They are the opt-in end-to-end tests behind `DISPATCH_E2E_CREW`, so don't count them against this branch.

## Fresh run

**Why a stand-in root.** Review 13 could not prove that a suite run from the real tree makes no `stat` on the live `.env`, because a stat isn't an audit event. So I built one as `reviews/code-review-11.md` describes: `git archive a43e36a` under `jurasolutions/repos/growth` in the session scratchpad, copies of `design-system/` and `prd/`, a canary `.env`, its own `uv sync --frozen` offline, `JURA_ROOT` unset, temp data and outputs folders, a stand-in `claude` first on `PATH`, and an audit hook in every Python process logging opens of files named `.env`.

- `uv run --frozen pytest -rs -rfE -p no:cacheprovider -o addopts="" --tb=short --junitxml=...` -> **5967 passed in 365.62 s**. Junit: 5967 tests, 0 failures, 0 errors, 0 skipped. Real clock, 03:19 to 03:25 SGT, Python 3.14.7. I did not rerun the across-midnight case, which is the developer's record at `bee9118`.
- Stand-in `claude` -> its log was never created.
- Audit log -> 22 opens of a file named `.env`, all under `pytest-of-tingy/`. The canary: 0. The live path: 0.
- Appendix A -> `same` 22, `CHANGED` 2.
- X5's greps -> 5 lines, all parameters. The skip and xfail regex -> 0.
- X6's diffs -> as above. Syntax-tree compare -> `approvals.py` identical with constants inlined, `caps.py` identical.
- X7's `find` -> `inputs/icp.md` only. `git diff --name-only` -> nothing under a blocked path.
- X11's grep -> nothing.
- Probes in the stand-in only, at `tests/test_gate_probe.py` and `tests/test_gate_probe2.py` -> masked outreach, the env file at 0644 and 0600, five kinds with no card, the numbers forms. `origin/main`'s `brand_check` was compared from a separate `git archive`.
- Typecheck and build: the operating card lists neither as configured, so there is nothing to run. Pyright stays advisory.
- Worktree after all of this: `git status` clean, tip still `a43e36a`.

**Beyond the brief's list, and disclosed.**

- I ran the web-font matrix (X9), the one network touch the strategy allows: real Chrome fetching Google's public fonts, sending no Jura data. I ran it because the record after UI-S1 was one summary line from the developer, not the per-picture record X9 asks for.
- I read `inputs/icp.md`'s metadata and diffed it against the draft.
- I read the live `runs/2026-11-01.jsonl` for its times, event kinds and the first two words of `remote.command` rows between 01:20 and 01:40.
- I scanned transcripts in Jura project folders for tool calls naming `icp.md`.
- I did not read, grep, count or stat the live `.env`. Nothing sent email or posted to Discord, I ran no `jura-growth run` and no `schedule` command, and the main checkout is untouched.

**Not checked:** a real SSH call, how Discord renders anything, real Facebook and Instagram posts, and real launchd. Those stay with UAT, chiefly Part L.

**The scratchpad** at `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/cca8b0db-8a3b-468c-8d82-7104d24fe636/scratchpad/gate/` holds the run's junit, the PNGs and scripts, plus copies of `design-system/` and `prd/`. Delete it with the session.

## Trace

One named case per criterion, each passed in my junit. `qa-final.md` "Trace" has the rest.

| AC | Case | File | Passed |
|---|---|---|---|
| AF1 | `test_each_platform_gets_one_card_and_social_drafts_hears_nothing`; negative: `test_a_typed_approval_of_a_post_with_no_card_is_refused_and_can_be_skipped` | `test_approvals_first` | 1, 1 |
| AF2 | `test_both_approved_at_1659_both_go_out_before_1800` | `test_approvals_first` | 1 |
| AF3 | `test_no_page_url_gets_a_note_saying_so` | `test_approvals_first` | 1 |
| AF4 | `test_a_late_run_on_the_shipped_config_skips_before_claude_starts` | `test_approvals_first` | 1 |
| AF5 | `test_hand_posting_text_appears_only_for_a_platform_in_draft_mode` | `test_approvals_first` | 3 |
| FD1 | `test_a_skip_posts_one_line`, for each real kind | `test_feed_real_kinds` | 9 |
| FD2 | `test_a_request_superseded_with_a_successor_posts_no_line` | `test_feed` | 1 |
| FD3 | `test_further_sweeps_add_nothing` | `test_feed` | 1 |
| FD4 | `test_a_failing_feed_never_holds_up_the_sweep_or_the_decision` | `test_feed` | 3 |
| DP1 | `test_each_theme_has_its_own_word_range_on_each_platform` | `test_social_depth` | 16 |
| DP2 | `test_ai_news_with_two_sources_on_one_host_is_refused` | `test_social_depth` | 1 |
| DP3 | `test_on_a_tuesday_ai_news_goes_out_with_the_cover_first` | `test_social_depth` | 1 |
| DP4 | `test_the_prompt_asks_for_insight_in_four_parts`. Whether a post has insight is his judgement in UAT L3 | `test_social_prompt` | 7 |
| DP5 | `test_a_shortfall_then_a_word_miss_then_a_pass` | `test_social_depth` | 1 |
| PC1 | `test_a_headline_theme_needs_a_visual` | `test_social_visuals` | 1 |
| PC2 | `test_an_icon_off_the_list_is_refused` | `test_social_visuals` | 8 |
| PC3 | `test_nothing_overflows_at_either_size` | `test_social_cards_real_chrome` | 34 |
| SC1 | `test_two_jobs_steadily_nine_hours_early_are_flagged`. Real launchd: UAT L2 | `test_schedule_drift` | 1 |

The outreach half of "no card, no approval" is `test_a_typed_approval_of_an_email_whose_card_has_not_gone_out_is_refused_and_sends_nothing` in `test_outreach_cards`, which passed.

## Pictures (X8, X9)

Fresh at `a43e36a`, with the production arguments through `card_probe.probe`. "Pass" means nothing outside the card or above the footer's top, no text box wider than its client width, and a PNG of exactly the stated size.

**By eye.** I viewed three web-font PNGs, the worst cases for the uppercase captions and the smallest type: `figure-ring-full` at 1080×1350, `flow-4-full` at 1200×630, and `list-5-no-icons` at 1200×630. Nothing is clipped or overlapping. The other 31 rest on the oracle above, with QA's viewing at `f0db1e5` and the developer's of the two captions UI-S1 changed. `git diff 27efa99 a43e36a` shows no change to the templates, `visuals.py`, `render.py` or `picture.py`. These are stress cards at each field's limit, not real content: their words read as filler by design.

| Case | Size | PNG | Fit, fallback | Smallest | Result | Fit, web fonts | Smallest | Result |
|---|---|---|---|---|---|---|---|---|
| compare-2-full | 1080×1350 | 1080×1350 | 0.92 | 20 | pass | 0.92 | 20 | pass |
| compare-2-full | 1200×630 | 1200×630 | 0.88 | 14.96 | pass | 0.88 | 14.96 | pass |
| compare-2-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| compare-2-short | 1200×630 | 1200×630 | 1.0 | 17 | pass | 1.0 | 17 | pass |
| compare-3-full | 1080×1350 | 1080×1350 | 0.88 | 20 | pass | 0.88 | 20 | pass |
| compare-3-full | 1200×630 | 1200×630 | 0.88 | 14.96 | pass | 0.88 | 14.96 | pass |
| compare-3-long-word | 1080×1350 | 1080×1350 | 0.88 | 20 | pass | 0.92 | 20 | pass |
| compare-3-long-word | 1200×630 | 1200×630 | 0.88 | 14.96 | pass | 0.88 | 14.96 | pass |
| figure-no-ring-full | 1080×1350 | 1080×1350 | 0.88 | 20 | pass | 0.84 | 20 | pass |
| figure-no-ring-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| figure-ring-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| figure-ring-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| figure-ring-short | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| figure-ring-short | 1200×630 | 1200×630 | 1.0 | 15 | pass | 1.0 | 15 | pass |
| figure-ring-whole | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| figure-ring-whole | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| flow-3-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| flow-3-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| flow-3-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| flow-3-short | 1200×630 | 1200×630 | 1.0 | 17 | pass | 1.0 | 17 | pass |
| flow-4-full | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| flow-4-full | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| flow-4-long-word | 1080×1350 | 1080×1350 | 1.0 | 20 | pass | 1.0 | 20 | pass |
| flow-4-long-word | 1200×630 | 1200×630 | 0.88 | 15 | pass | 0.88 | 15 | pass |
| headline-only | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| headline-only | 1200×630 | 1200×630 | 0.72 | 17 | pass | 1.0 | 17 | pass |
| list-2-short | 1080×1350 | 1080×1350 | 1.0 | 22 | pass | 1.0 | 22 | pass |
| list-2-short | 1200×630 | 1200×630 | 1.0 | 17 | pass | 1.0 | 17 | pass |
| list-5-full | 1080×1350 | 1080×1350 | 0.76 | 22 | pass | 0.76 | 22 | pass |
| list-5-full | 1200×630 | 1200×630 | 0.68 | 15.64 | pass | 0.8 | 17 | pass |
| list-5-no-icons | 1080×1350 | 1080×1350 | 0.76 | 18.6 | pass | 0.76 | 18.6 | pass |
| list-5-no-icons | 1200×630 | 1200×630 | 0.68 | 12 | pass | 0.8 | 13.6 | pass |
| slide-full | 1080×1350 | 1080×1350 | 0.92 | 20 | pass | 0.96 | 20 | pass |
| slide-full | 1200×630 | 1200×630 | 1.0 | 15 | pass | 1.0 | 15 | pass |
