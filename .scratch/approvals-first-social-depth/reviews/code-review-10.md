# Code review 10: merge main, and close the final review and QA

Reviewed `crew/approvals-first-social-depth-10-final-fixes` at `27efa99` in worktree `agent-a0a4177a4a7a04532`. The merge `ac12db7` was read against both parents (`78c9799` and `c11eb61`), then `ac12db7..27efa99`. File references are at `27efa99`. "Reproduced" means I ran it on temp data against the Discord double, in a throwaway probe in the session scratchpad. The probes are not on the branch.

## Verdict: changes-requested

One finding blocks.

- **A typed approval of a social post whose card never went out still goes through, and the post is handed to the browser (B1).** Ticket 09 closed this for a card the sweep refused. The same words, unread, still pass when the card simply hasn't been posted.

Everything else the ticket asked for holds, apart from the should-fix items below. The merge is right, main's schedule is intact, no test was lost or loosened, and no blocked path changed. The developer's suite figure reproduces: 5653 passed, none failed or skipped.

## Spec

### Blocking

**B1. A typed approval reaches a post nobody has seen on a card.** `jura_growth/agents/publish/kinds.py:258`.

- **Rules broken:**
  - PRD amendment (line 84): "an approval card always shows exactly what would post."
  - PRD AF2: "Approving a card posts it", and AF1, under which #social-drafts no longer holds the post text.
  - `docs/social.md:322`: "he never approves words he couldn't read."
  - The reasoning in `on_approve` itself: approving a post with no card "would be a yes to words he hasn't read."
  - Ticket 09's own severity reasoning, whose stated failure is "A post nobody saw on a card is handed to the browser."
- **Cause:** `on_approve` only checks a request with `posted_at` unset for a sweep refusal or a `card_problem`. A card that Discord hasn't taken yet has neither, so `on_approve` returns and the approval stands. Once approved, the request can never get a card, because `approvals.unposted` only returns pending requests.
- **Reproduced:** on `social_day`, with the double answering 500 for `submit_tip` and the sweep, and no contact teaching any word:
  - `posted_at None, refusal None`
  - `pw.decide` gives `recorded, A-0001 approved.`
  - At a publish run, `next_item` gives `P-0001, A-0001`, with `used_at` set and `posted_at` still `None`.
- **Why he could reach it:** the one-pager names the id ("Not posted to #approvals yet: A-0001", `health.py:189`), and `/growth approvals` lists it by title only (`approvals_cli.py:132`). Before this branch the post text was also in #social-drafts. After AF1 the card is the only place to read it, so this feature is what makes the gap matter.
- **Severity:** major, by the same reasoning as ticket 09. The hash still binds and a person has to type it, so it isn't critical. X12 allows no open major, and section 7 of the test strategy gives no waiver for one.
- **Fix:** have `SocialPost.on_approve` refuse whenever `latest.posted_at is None`, with a skip still allowed. This stays inside the kind, as ticket 09 did, so X6 still holds and `decide()` is unchanged.
- **The cost of the fix is in the tests, not the code.** With that change alone in a throwaway copy, the full suite gives 186 failed and 47 errors. The failures I listed are in 16 files, led by `test_publish_queue.py` (59) and `test_publish_instagram_linkedin.py` (58), and they include `test_approval_gates.py` (12); the errors weren't itemised. I read the cause as fixtures deciding without a sweep, but I didn't read each failure. If so, one change in the shared helpers should clear most of them. `gate_adapter_*` can only gain lines under X6.
- **If the conductor wants typed approval kept as a route for a Discord outage,** that is a change to the PRD's promise and needs Ting Yu's word and a PRD line. I recommend refusing, because the heartbeat already re-posts the card and the post can wait for it.

### Should fix

**S1. Stale times are left in the UAT seed.** Ticket 10: "re-check every place this branch states a time". The developer moved `drift` and `late_wake`, but not these.

- `tests/uat/seed.py:288,290`: today's `app-factory` is at 06:31 and `social` at 07:00, against main's 07:00 and 07:30. Pinned at `tests/test_uat_seed.py:165` and `tests/test_uat_seed_outreach.py:85,90`.
- `tests/uat/seed.py:365`: `scout-research` is at 09:00:30, against main's 06:30.
- `tests/uat/seed.py:40`: "decide by 18:00", against the PRD's 17:00.
- **Reproduced:** after `base` at 10:00, today's `app-factory`, `social` and `scout-research` slots all read `due`, although the seed says S2 holds today's runs. No false Fix line results, and no UAT step I read depends on it, so this is a harness defect only. It would mislead whoever reads those rows in the UAT.
- `reviews/functional.md:103,104,118,129` also keep older times (from the Spec pass, not re-read). It is a record, so correct it only if the gate wants it true.

**S2. X3's record is short for `test_digest_figures`.** Test strategy X3: "Any `CHANGED` line must be listed in a QA report with its functional decision's id." `reviews/qa-final.md:352` gives the reasoning and no id. Add AF5 and A13. The change itself is fair; see "Answers to the brief".

**S3. ST-S2 stays open.** `CLAUDE.md:17` still says "Only the phrases in `config/approved_claims.yaml`", and the allowance is a comment in that file. The developer logged this as Ting Yu's change to make, with suggested words. I agree, and the gate should carry it.

### Nits

- `agents/social/__init__.py:137` counts an approved post in `social_drafts_waiting`, where the final review said a post "waits only while its request is pending". The same fix text says an approved one "says it is waiting on a publish run", and `docs/social.md:478` documents this. It is a defensible reading, and the 18:05 digest has lapsed those by then.
- `card.css:260,378`: UI-S1 fixed the case. `visuals.py:32` still allows a 60-character caption that takes two lines of mono, where `design-system/README.md:111` says "never for reading". The developer viewed both at their limit and nothing clips.
- SP-S1's "put them in the PR body" belongs to the release step. The PRD amendments are done.
- Tickets 05 to 10 all still say `Status: ready-for-agent`.

## Standards

No blocking findings.

### Should fix

**St1. A regression test that can't fail.** `tests/test_qa_final_defects.py:234`, `test_the_live_engine_writing_its_run_log_does_not_fail_the_refusal_test`. Rule: ticket 08's Expected, "still fails if the seed writes anything". `untouched_snapshot` now reads only the config folder, so writing a run log into `LIVE_DATA` can't change it. The real cover is in `test_uat_seed_outreach.py`, and it is good (see "Answers to the brief"). Delete this test or point it at the watcher.

**St2. Reuse.** Rule: new code duplicating an existing helper is a should-fix.

- `agents/social/__init__.py:116-136` (`_place`) repeats the clock reading in `mission._request` (`mission.py:528-541`): pending against decide-by, approved against use-by. Two readings of one request can drift. Extract it so both call one function.
- `agents/publish/group_kinds.py:270-272` copies `kinds.py:179-181`: the `decided` line and the `last_run_on` check. It belongs in `items`.
- `agents/publish/kinds.py:178` `off[:1].upper()...` duplicates `picture._sentence` (`picture.py:161`).
- `tests/uat/seed.py:98` `WEBHOOK_PREFIX` duplicates the literal in `discord.env_name` (`discord.py:58`).
- `agents/social/plan.py:69` restates the rule at `submit.py:210-211`, and its own comment says so ("as `submit` makes them"). Possible Shotgun Surgery.

**St3. The learn half of ticket 09 has no test.** See "Test gap" under "Answers to the brief".

### Nits and judgement calls

- `kinds.py:262`: the answer reads "...so its card can't show the exact text, so it can't be approved". Two "so"s.
- `group_kinds.py:266`: a feed line opening in lower case with a config key, knowingly, per its comment. `kinds.py:178` capitalises the same hook's text. Design system §3, low severity.
- `agents/social/__init__.py:95-98`: "expired" where `CONTEXT.md` "Request reading" says "lapsed". The final review asked for "expired" and the Publishing line uses it, so I don't rank this as a breach.
- Possible Primitive Obsession: `social/__init__.py:95-98,116`, display strings double as identity and feed a figure.
- Possible Shotgun Surgery: `except brand_check.BuzzwordListMissing` at `cli.py:105` and `social/commands.py:83`, with other Click paths not catching it. They fail closed, as a traceback.
- Possible Mysterious Name: `browser` is a set at `social/__init__.py:101` and a bool at `:116`. `test_qa_final_defects.py` names a process stage, not a behaviour.
- Possible Feature Envy: `seed.py:181,196` reach into `uat_stub._UNSAFE` and `config._parse_env`.

### Checked, no finding

Every commit subject is a sentence-case imperative. No new limit bypasses `caps.py`. The core imports no agent by name (`cards` is core, and `mission` imports it inside the function). ST-S1, ST-S3, SP-S2 and SP-S3 are closed.

## Security

No high-severity finding in product code. The approval gap is B1 above, ranked under Spec.

### Should fix

**SEC1. The UAT seed's live-webhook check is an exact string compare, so SEC-S1's "must never" doesn't hold.** `tests/uat/seed.py:196-199`, `:97`. Rule: ticket 10, "The UAT seed must never be able to reach live webhooks", and PRD §4, "Nothing here is run against the live system".

- **What holds:** the final review's failure is closed. A missing `JURA_GROWTH_ENV_FILE`, a file inside the repo or `jurasolutions/`, a `DISCORD_WEBHOOK_*` in the shell, a look-alike host and an exact copy of a live URL are each refused, and the value is never printed. Each has a test.
- **What doesn't, reproduced:** with one live URL planted in `LIVE_ENV_FILES`, a UAT env file holding that webhook in any of these forms gets `refusal() == None`:
  - a trailing slash
  - `?wait=true`
  - `/api/v10/webhooks/<id>/<token>`
  - a `ptb.discord.com` host
  - a `discordapp.com` host
  - `keychain:<name>`, which `config.secret` resolves after the compare
- **Also reproduced:** in a worktree with `JURA_ROOT` unset, `paths.JURA_ROOT` is `.../growth/.claude`. Neither `LIVE_ENV_FILES` path exists there, so nothing is compared, and the live `repos/growth/.env` is outside both `is_within` checks. `uat.md:75` exports `JURA_ROOT`, and nothing enforces it.
- **Limits:** each case needs someone to put a live webhook in the UAT file. I did not test whether Discord accepts each spelling, and sent nothing. The consequence is real, though: UAT cards in live #approvals, whose buttons could decide a live request with the same number.
- **Fix:** compare by parsed webhook id, refuse `keychain:` values in the UAT file, and refuse when no live env file is found to compare against.

**SEC2. Other kinds still approve what the card doesn't show, and one sends with no card.** These predate this branch (main has neither hook) and sit outside PRD §3's social scope, so they don't block. They answer the brief's question, though, and Ting Yu should know.

- **Masked card, reproduced:** a contact `marta.most@other.example.sg` teaches "Most". An outreach card then shows "> [name removed] delivery firms sign on paper.", the approval is recorded, and the send double takes one email. A community-post card behaves the same way ("[name removed] invoice chasing follows...", claimed by the run). Neither kind has `card_problem` or `own_copy`. He does see the marker, so he isn't misled silently, but he approves words he couldn't read. I didn't read the sent email's body.
- **No card, reproduced:** an outreach request with `posted_at None` is approved and sent. `config/scout.yaml:18` is `mode: live`, so this path is live on main today. `config/community.yaml:16` is `browser: false`, so community isn't reachable yet.
- **Fix:** a follow-up ticket applying B1's rule and `card_problem` to those kinds, before community's `browser` is turned on.

### Checked, nothing to report

From the security pass, and I rechecked the first two by probe or by reading.

- The shell-variable check holds: `_cannot_leave_this_mac` refuses `@`, `\` and look-alike hosts.
- `discord.py` is the only sender, and `env_name` always adds the prefix.
- Refusals print names and paths, never a webhook.
- New SQL is parameterised. `mission` masks before it cuts.
- `picture.py` and `visuals.py` escape before rendering. `remote.py` is unchanged.
- The wider `NOT_NAMES` leaves a name part such as "Asia" visible alone, which its comment records as a choice.
- No secret or personal data is in the diff. A scan of the added lines finds only `tingyu@jurasolutions.sg` in tests and test tokens.

## Blocked paths

None changed. `git diff --name-only c11eb61...27efa99` and `78c9799..27efa99` hold nothing under `inputs/`, `design-system/`, `.env`, `.github/`, `launchd/` or `data/`. `find` over `inputs` and `design-system` newer than `78c9799` prints nothing. `.env` is untracked.

The seed now reads the live `.env` into memory to compare webhooks (`seed.py:196`), read-only and never printed. `uat.md` documents it.

## UI

`crew:web-design-review` on `jura_growth/agents/social/templates/card.css`. It renders to a fixed PNG, so the rules on interaction, focus, forms, motion, touch and hydration don't apply.

```text
## jura_growth/agents/social/templates/card.css

✓ pass (the two caption rules use --tracking-overline, uppercase and the caption size)
```

**Design system note:** see the `card.css` nit under Spec.

## Answers to the brief

### The developer's claims

| Claim | Finding |
|---|---|
| Suite 5653 passed, none failed or skipped | **Holds at the tip.** I ran it once: 5653 passed, 0 failed, 0 errors, 0 skipped, no `SKIPPED` line, in 472 s. I did not rerun the two clock runs or the last-code-commit run |
| 09: a typed approval of a refused card is refused in a new process, and `publish next` finds nothing | **Holds for a refused card.** Removing `cards.refusal` fails `test_a_card_the_sweep_refused_stays_refused...`. A probe with a learned name and no sweep ever run, in a new process, is also refused. B1 is the gap beside it |
| "Learn first; sweep's refusal also stands" | **Both work, and the learn half has no test.** See "Test gap" below |
| 08: no race with the live engine | **Holds.** `test_every_scenario_refuses_the_live_folders_without_opening_them` stops the seed at its first touch through an audit hook, and the planted-folder test compares every file. `test_those_two_checks_would_catch_a_seed_that_got_in` proves both can fail. St1 is one leftover |
| `test_digest_figures` pins draft mode | **Fair, not a weakening.** Main's by-hand count of 3 is a draft-mode claim, the branch ships Facebook and Instagram in browser mode, and the merge met the two. Only the pin and the `monkeypatch` argument changed, and every assertion is as on main. It isn't on the strategy's loosening list. Browser mode's figure is pinned at `test_picture_read.py:443`, and a platform moved back to draft with an approved post at `test_qa_final_defects.py:121`. It only lacks the id (S2) |
| SEC-S1 | **The original failure is closed; the claim as worded doesn't hold** (SEC1). Loopback and `.invalid` are allowed as described |
| `mission._failures` | **Holds.** `mission.py:390`, `_clean(row["error"] or "")[:300] or None`. Main's order, not the branch's old one |

**Test gap (St3).** Rule: ticket 09's Fix, "Add a test with a `contacts` row and `config.reset_caches()` before the decision", and test-first delivery. Deleting `privacy.learn(conn)` from `card_problem` leaves the **full suite at 5653 passed**. `test_a_typed_approval_of_a_card_refused_for_a_learned_name_is_refused_in_a_new_process` sweeps first, so the refusal event answers and `learn` is never what decides. Add its twin with no sweep before the decision. The probe above is that test.

### 1. Approval

What goes out is what was approved: `use()` compares the hash and the claim's path is unchanged. `decide()`, `claim.py`, `origin.py` and the ADRs show no diff. The gap is in what he has seen when he approves: B1 for social posts, SEC2 for the other kinds.

### 2. Tests removed, weakened or moved

I compared the parsed form of every test at `78c9799`, `c11eb61`, `ac12db7` and `27efa99`.

- **The merge dropped nothing from one side only:** 0 tests differ from both parents, and no test held by only one parent was changed.
- **15 names are gone since the base or main:**
  - Main itself deleted 7: six grid tests in `test_one_pager_post.py` and `test_an_idea_over_500...`.
  - This branch renamed or replaced 7 before this ticket. Three have clear successors (`test_the_1805_digest_still_writes...`, `test_the_deadlines_follow_the_end...`, `..._refused_for_outreach_and_seeds_nothing`), and the rest are in QA's class tables or were replaced before this ticket.
  - This ticket replaced 1: the racing refusal test, by two stricter ones.
- **`d692887`** removes only the ticket folder's copy. All 7 of QA's tests live on in `tests/test_qa_final_defects.py` with their assertions, moved or tightened: the buzzword test now requires a raise, and test 09 runs in a real second process. St1 is the one that lost its force.
- **`ac12db7..27efa99`:** 12 test bodies changed, and I read each. They are time values (M3, M4), wider fakes, and one new assertion set. `test_only_a_draft_on_a_draft_mode_platform_is_to_post_by_hand` changes `waiting` from 1 to `by_hand`, which follows ticket 05 for a draft with no card.
- `git diff c11eb61...27efa99 -- tests` also changes `test_r1_...`, `test_p8_...` and `test_social_post_seeds_...` by one clock literal each, 18:00 to 17:00. These are B2 and predate this ticket.

### 3. Schedule

**Kept.** `git diff c11eb61 27efa99 -- config/settings.yaml` is one line: the digest to 18:05. App-factory 07:00, social 07:30, scout-research 06:30, outreach-requests 08:30, one-pager 09:00 and community Mon 08:00 all stand. `test_morning_schedule.py` pins them, and `picture.LATER` reads its time from the slots. No "17:30" is left in code, config, docs or prompts. S1 lists what the seed still holds.

### Merge

Each conflict hunk reads correctly: `discord.py` (the branch's `split`, main's `shortened` and `_noted`), `health.py` (main's `worded`, then drift and the refused lines), `mission.py` (all the fields, mask-then-cut), and `CONTEXT.md`, `README.md`, `docs/scout.md`. M1 to M4 are closed. M2's filter compares aware times, because `timeutil.parse` gives naive stamps SGT.

### `5b5404c`

The content is right: `plan.py` and its test, nothing else. It is on this branch, with the same identity as every commit here (`jurasolutions <levijurasolutions@gmail.com>`), and its message carries the attribution lines. The method isn't re-raised.

## Evidence

- `pytest -rs -rfE -p no:cacheprovider -o addopts="" --tb=short`, with `.venv/bin/python` (3.14), temp data and outputs folders, and a stand-in `claude` first on `PATH`: 5653 passed. Junit: 5653 tests, 0 failures, 0 errors, 0 skipped.
- Stand-in `claude`: its call log was never created, across every run here. The worktree's `git status` is clean afterwards, and its tip is still `27efa99`.
- Mutations, in throwaway copies of `27efa99` under the scratchpad, full suite:
  - no `privacy.learn` in `card_problem`: 5653 passed
  - refuse any unposted `social-post`: 186 failed, 5420 passed, 47 errors
- Mutation, `test_qa_final_defects.py` and `test_approvals_first.py` only: no `cards.refusal`, 1 failed, 73 passed.
- Probes, on the Discord double and temp data: B1, the no-sweep new-process case, S1, SEC1's URL forms and `JURA_ROOT`, SEC2's four cases. In `decide`, each uses `Origin.ssh()` directly, not a real SSH call, for the reason ticket 09 gives.
- AST comparison of test names and bodies across four revisions, in the scratchpad.
- Sub-reviews: Standards, Spec and the security pass ran as separate read-only agents. `security-review` was first pointed at the main checkout's empty diff, so I reran its pass against this diff. I confirmed St2, S1, SEC1 and ST-S2 by probe or by reading. The "checked, nothing to report" list and the `functional.md` lines rest on those agents' reads.
- The security pass reports a count of the webhooks in the live `.env`. No value appears in its report, and I ran no command on that file myself, other than the seed's own read during the suite.
- `mission.Source.here` read launchd's state in one probe, as QA's walk did. Nothing was installed, loaded or rendered. Nothing was posted or sent, and no `jura-growth run` was used. The main checkout was not touched.
- **Not checked:** a real SSH call, how Discord renders anything, whether Discord accepts SEC1's alternate spellings, the real-font matrix after UI-S1 (the developer's record), and the two clock runs.
