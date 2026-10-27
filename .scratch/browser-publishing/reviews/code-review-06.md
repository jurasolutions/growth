# Code review 06: BP-06, group joins as the Jura Page

- **Branch:** `crew/browser-publishing-06-joins-as-the-page` at adc6adc (dc05893, 3cc8967, 0776434, f31dc23, adc6adc), compared with its merge-base b4f0895 on `crew/mission-control`. `git merge-tree` against `crew/mission-control` is clean. It conflicts with 04 in `prompts/publish.md`, `tests/test_publish_prompt.py` and `docs/social.md`, and with 07 in `scope.py` and `job.py`.
- **Ticket:** `.scratch/browser-publishing/issues/06-joins-as-the-page.md`. **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md` (SC4, AC-P5.1 line 4, §4.2, §4.3, §4.5 to §4.7, §5.4 to §5.9). **Tests:** test strategy v3, the BP-06 rows. **Lessons:** code reviews 02b, 03 and 04 (B1: audit against the claimed item's own hosts).
- **Reviewed:** 2026-10-27. I read every changed file: the 17 files in `docs/`, `jura_growth/agents/community/`, `jura_growth/agents/publish/`, `prompts/` and `tests/`. For context I also read `group_kinds.py`, `claim._join_cap`, `items.proposals_in_week`, `hosts.py`, `paths.guard`, `headless.install` and `privacy.for_discord`, plus the 04 and 07 diffs to `scope.py` and `job.py`.

## Round 2 (fix round 1): approve

- **Branch:** `crew/browser-publishing-06-joins-as-the-page` at c2ad54b, rebased onto e204292 (`crew/mission-control`, with BP-04 and BP-07 merged). It holds 12 commits, ba14c30..c2ad54b. The fixes are:

  | Commit | Fixes |
  |---|---|
  | 60c1b16 | B1 and S1 |
  | fc763e1 | S2 |
  | fed88a7 | S3 |
  | e14855b | S4 and R3 |
  | a271100 | S6 and the nits |
  | 90fac4b | S5 |
  | c2ad54b | the fixture site's group paths |

  `git merge-tree` against `crew/mission-control` is clean.
- **Reviewed:** 2026-10-27. I read the whole fix diff `66c3b27..c2ad54b`: `audit.py`, `hosts.py`, `job.py`, `outcomes.py`, `commands.py`, `group_kinds.py`, `groups.py`, `group_rules.py`, `publish/__init__.py`, `run_update.py`, `prompts/publish.md` and the five changed test files. I also re-read `community.groups.validate`, which sets what a group's `target_url` can be.

### Verdict

**Approve.** B1 is fixed and reproduced as fixed. Every round-1 should-fix is resolved.

There is one new should-fix (S7) and two new nits. None of them blocks:

- **S7:** the group-path rule is only as narrow as the register's URL, and `add-group` accepts URLs that aren't one group's address.
- **N10, N11:** two nits.

S7 needs a register URL that is visibly wrong on the join card Ting Yu approves. It can go in this ticket or as a follow-up.

### Evidence (round 2)

- **Full suite** in the developer worktree at c2ad54b. Same setup as round 1. `uv run --frozen pytest -p no:cacheprovider -o addopts="" -q -rs` printed **3230 passed in 130.74s**, 0 skipped. The worktree is still clean afterwards.
- **Pyright** on the three join test files plus `outcomes.py`, `hosts.py`, `audit.py` and `run_update.py`: **0 errors**. S5 is fixed.
- **Blocked paths:** `git diff --name-only e204292...` shows nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **Repros**, from a scratch copy of `tests/` (`test_zz_review_06.py`, `test_zz_review_06b.py`): 22 passed, all as expected below.

  | Row | Case | Round 2 |
  |---|---|---|
  | R5 | Join for group A approved; Join clicked in another group, then `--outcome requested` | **`failed`, paused** ("the audit of run 1 failed") |
  | R1 | Approved answers typed and posted on the Jura Page timeline, then `--outcome member` | **`failed`, paused** (the questions run before it, held in the group, passes) |
  | R2 | Confirmed rules seen again with only a blank line and a trailing space added | Confirmation kept: `rules_confirmed=1`, `promo_days=sat` |
  | R3 / R12 | A join recorded `declined` | Not in `join_room` candidates. `create_join` refuses it ("declined the Jura Page's join"), and no request is raised |
  | R4 | `--file` outside the run's folders, and `.env` | Still refused (exit 2) |
  | R6 | Tab at `/groups/1234567` and at `/groups/12345` against `/groups/123456` | **fail** (whole-segment match) |
  | R6 | `/groups/123456?ref=share&x=/groups/654321`, `/groups/123456/`, `/groups/123456#/groups/654321`, `/GROUPS/123456` | pass. The query and fragment are ignored, and the case is folded |
  | R6 | `/groups/123456%2F..%2F654321`, `/groups/123456;/654321`, `/groups/654321` | **fail** |
  | R6 | A tab *reported* at `/groups/123456/../654321` | pass (N10). Chrome reports normalised addresses, so this can't be reached; see R7 |
  | R7 | `navigate` to `/groups/123456/../654321`, with the tab context reporting `/groups/654321` | **fail** |
  | R8 | A click in the group, then the tab reports another group (a redirect) | **fail** |
  | R10 | Fixture site with group `/groups/rehearsal-1`: tabs at `/groups/rehearsal-10`, `/groups/rehearsal-1-other`, `/groups/rehearsal-2` | all **fail**. `/groups/rehearsal-1/about` passes |
  | R11 | `publish done --outcome requested --url` set to another group, or to the group's address plus "0" | refused. The group's own address with `/?ref=x` is accepted |
  | R9 | Register URL `https://www.facebook.com/groups/` (another group's tab), or `https://www.facebook.com/jura-test-page?/groups/` (the Page timeline) | `validate()` accepts both, and **the audit passes** (S7) |

### Round-1 findings

| Finding | Status |
|---|---|
| **B1** | **Fixed.** `job._audit` passes `places` (the claimed group items' `target_url`) to `audit.audit`. Every page-tool tab and `navigate` must be on the item's own platform hosts and, by whole path segments, inside the group (`hosts.within`). A denied `navigate` out of the group fails too. `--outcome --url` must be the group's own address (`hosts.same_place`). The check also runs on the fixture site. Fake-claude runs cover R1 and R5. |
| **S1** | **Fixed.** The audit takes hosts from the claimed item's platform (`scope.browser_hosts(own)`, from 04). A group item with its tab on Instagram fails (`test_the_audit_takes_its_hosts_from_the_claimed_item_never_every_enabled_platform`). The domain rules stay the enabled union before the claim, as accepted in review 04. |
| **S2** | **Fixed.** The optional `run_update_channel` hook sends a group item's update to `#community`. A failing hook logs and falls back to `#social-drafts` (tested). |
| **S3** | **Fixed.** `note_seen` compares the rules with whitespace collapsed and stores the text as seen (R2). |
| **S4** | **Fixed** as the conductor decided. A `declined` group is never proposed again and takes no slot (R12). The prompt now separates `declined` (an admin turned the request down) from `pages-not-allowed` (the screen refuses Pages). |
| **S5** | **Fixed.** 0 pyright errors. |
| **S6** | **Fixed.** `groups._write` and `groups._joined_as` are the one writer. `record_join` and `pages_not_allowed` pass `run_id`. |
| N1 to N5 | **Fixed.** `outcomes.WORDS` is the one table. `PROFILES_ONLY` is renamed. `Recorded.raised` is removed. The `--file` checks are split. The local `done` is renamed. The `type: ignore`s are gone. |
| N6 to N9 | Open, unchanged. Answer order, ticked answers, AC-P4.3's coverage of answers items, and `pages_allowed = yes` on `requested`. All are still nits. |

### New findings

#### Should fix

- **S7. The group-path rule is only as narrow as the register's URL, and `add-group` doesn't hold that URL to one group's address.**
  - **Where:** `community/groups.py:127` accepts any `facebook.com` URL that contains `/groups/` anywhere, the query included. `hosts.within` (`hosts.py:73`) then uses the path as it stands.
  - `https://www.facebook.com/groups/` gives the place `/groups`, which contains every group. `https://www.facebook.com/jura-test-page?/groups/` gives `/jura-test-page`, the Page timeline (R9). With either URL approved, R5 and R1 pass the audit again.
  - **How it gets there:** the community research run writes these URLs from web search results, which an injection can reach. Ting Yu's join card shows the URL, so he would have to approve a visibly odd address. That is why this isn't blocking.
  - **Rules it breaks:** SC4 (approval "for that group") and the B1 fix's intent.
  - **Fix:**
    1. Accept a Facebook group URL only as `https://<facebook host>/groups/<one segment>`, with an optional trailing slash and nothing after it: in `validate`, in `create_join` and `read_join` (or `group_kinds.gone`), and in `hosts.within`.
    2. For a place that isn't of that shape, `within` should fail closed.
    3. Add R9's two URLs as refused rows.

#### Nits

- **N10. Dot segments.** `hosts.within` doesn't resolve `..`, so a tab *reported* at `/groups/<id>/../<other>` would pass. Chrome reports normalised addresses, and R7 shows the real path (a `navigate` with `..`) fails on the tab context. For defence in depth, refuse a URL whose path has a `.` or `..` segment.
- **N11. An audit-failed join still has its outcome recorded.** In R1 and R5, the outcome the run recorded stands after the audit fails: `joined_as = page` or `join_status = requested` on the approved group. `publish` is paused and `#alerts` says the audit failed, but not that the group's join record may be wrong. A community post there still needs a `group-rules` decision and a resume. Consider naming the group in the audit-failure alert ("check group N's join record"), or setting the join record back to its prior state on an audit failure.

### Security (round 2)

The same method as round 1, by hand on `e204292...c2ad54b`. The fan-out stayed within the brief's two agents, and there were none in round 2.

- **A join only with approval of that group:** now enforced by the audit, by path segment and on the fixture site. The run fails and `publish` pauses (R1, R5, R7, R8, R10, R11). The remaining gap is S7.
- **Profile joins:** unchanged; prompt-only, as round 1 says.
- **Weekly cap, `note-rules`, file guard, SQL:** unchanged, and still hold.
  - `groups._write` builds its `SET` from fixed keys only. Its callers pass literal keys, or `SETTABLE`-checked ones through `set_parsed`.
  - `run_update._channel_for` returns a fixed string, and a failing hook falls back.

---

## Round 1

### Verdict (round 1): changes-requested

One finding blocks: **B1**. The publish run's audit accepts a group item acted on anywhere on Facebook. So a run that claimed Ting Yu's approved join for group A can join group B instead, record A as `requested`, and finish `ok` with no alert and no pause. A run can also post approved membership answers on the Jura Page's own timeline and record the group as joined as the Page. This is the BP-04 B1 lesson, one level down: an approval binds a destination, and the run's only code backstop, the audit, doesn't check the destination.

The rest is sound:

- The outcome handlers, the answers step, the weekly cap, `pages-not-allowed` for every kind and `note-rules` all do what the spec says.
- `note-rules` can't confirm rules or set days.
- Every file option goes through `paths.guard`.

### Evidence

- **Full suite** in the developer worktree at adc6adc. `JURA_ROOT` set, temp data and outputs folders, the fake `claude`, the Discord double, no Chrome. `uv run --frozen pytest -p no:cacheprovider -o addopts="" -q -rs` printed **2996 passed in 128.56s**, 0 skipped. The worktree is still clean afterwards.
- **Blocked paths:** `git diff --name-only b4f0895...` shows nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **Pyright** (from the standards reviewer): the production files add no errors. The three new test files add 57 (S5).
- **`test_zz_review_06.py`** runs from a scratch copy of `tests/`, so the worktree is untouched. The R1 and R5 rows are whole runs through `runner.run("publish")` with the fake `claude`.

  | Row | Case | Result |
  |---|---|---|
  | R5 | Join for group A approved and claimed. The run opens `https://www.facebook.com/groups/some-other-group`, clicks Join there, then runs `publish done --outcome requested` | **`status=ok`**, A's `join_status=requested`, not paused, no alert |
  | R1 | Answers approved and claimed. The run opens the Jura Page (`t.PAGE`), clicks Create post, types the approved answer, clicks Post, then runs `publish done --outcome member` | **`status=ok`**, group `joined_as=page`, not paused |
  | R2 | Group confirmed with "Be kind.\nPromotion only on Saturdays." `note-rules` sees the same words with one extra blank line and a trailing space | `rules_confirmed=0`, `promo_days_confirmed=None`: the confirmation is cleared (S3) |
  | R3 | A join recorded as `declined` | The group is back in `join_room()["candidates"]` (S4) |
  | R4 | With `JURA_GROWTH_JOB=publish`: `note-rules --file` outside the run's folders, `done --outcome questions --file` outside them, and `note-rules --file <.env>` | All three refused with exit 2 by `paths.guard`, and no request raised |

  The repo's own clean answers run (`test_publish_join_run.answers_run`) shows the same gap as R1. `t.typed()` reports the tab at the Jura Page URL, not the group's, and the test passes.

### Standards

#### Should fix

- **S5. 57 new pyright errors** in `tests/test_publish_joins.py` (43), `tests/test_publish_join_run.py` (12) and `tests/test_community_joins.py` (2). This breaks `docs/agents/crew.md`: "don't add new errors in files you touch".
  - Nearly all are Optional access, the same pattern as review 04's N2.
  - One looks like a real error: `test_publish_joins.py:399` reads `superseded_note` from an `ApprovalKind`, and pyright says that type has no such attribute.
  - **Fix:** add `assert x is not None` where needed, and type the kind lookup.
- **S6. Possible Duplicated Code: `groups.record_join` (`groups.py:328`).**
  - It repeats the tail of `set_parsed` (`:281-291`): the `updates` dict, `updated_at`, and the f-string `UPDATE`. It also writes `joined_as_set` and `joined`, so two functions now maintain the `joined_as` invariant.
  - It logs without `run_id`, while `note_seen` passes one.
  - **Fix:** route it through one writer, or share the update helper, and pass `run_id`.

#### Nits

- **N1. Outcome words live in four places:** `outcomes.OUTCOMES`, `groups.JOIN_STATUSES`, `job.OUTCOME_LINES` and `job.OUTCOME_NOUNS` (`job.py:35-43`). The two dicts in `job.py` are parallel maps over the same keys. One table in `outcomes.py` would hold them all (possible Shotgun Surgery).
- **N2. One name, two meanings.** `outcomes.PAGES_NOT_ALLOWED` is an outcome key and `groups.PAGES_NOT_ALLOWED` is a reason text. Both appear in `outcomes.record`.
- **N3. Unused field.** `Recorded.raised` is set but never read (possible Speculative Generality).
- **N4. Readability.**
  - `commands.py:238`, `(answers_file is None) != (outcome != outcomes.QUESTIONS)`, is hard to read, and `outcomes.record` checks part of it again.
  - The local `done` in `_done_outcome` shadows the `done` command.
- **N5. Suppressed instead of fixed.** The new `# type: ignore[return-value]` at `groups.py:342` and `:356` hides the Optional return. An assert would fix it (see S5).

### Spec

#### Blocking

- **B1. A group item's run can act in any group, or on the Page's timeline, and the audit passes it.**
  - **Where:** `job.py:195` audits every tab against `scope.browser_hosts()`, which is a host check only. For a join or an answers item, nothing ties the tab to the claimed item's `target_url`.
  - **What is left:**
    - A join item has no approved text, so a join run can't type anything without failing. Clicks aren't audited, though, and a click is all a join takes (R5).
    - An answers item's approved text can be typed into any Facebook field (R1).
    - `record_join` then writes `join_status` and, on `member`, `joined_as = page` for the approved group. That unlocks community posts there under BP-05, so a run that joined the wrong group leaves a record that lets posts go to the right one.
  - **Where it starts:**
    - A prompt injection on the group page, such as "this group has moved, join /groups/…".
    - Model confusion.
    - `navigate` is the only route to a new page. The prompt limits it to `target_url`, but the code doesn't.
  - **Rules it breaks:**
    - SC4: "Joining a group needs Ting Yu's approval for that group, joining as the Jura Facebook Page".
    - §4.2: "Any change to the text, images, destination, posting identity … makes a new item that needs a new approval".
    - AC-P4.2: "submit exactly those answers".
    - AC-P9.3: the audit fails "a foreign URL".
    - The brief's check: "a join can't happen without an approval of its exact answers and identity".
  - **Why it blocks here:** this ticket brings the first group items into a live run. It also opens Facebook while the Page's own posts stay in `draft` (`scope.py:36`), so in that configuration the Page timeline is reachable only because a group item can be claimed.
  - **Fix:**
    1. Pass the claimed items' targets into `audit.audit`.
    2. For a group item, fail any page-tool tab or `navigate` whose URL isn't on the target's host and under its `/groups/<id or slug>` path. Allow the run's blank new tab. Compare after trimming the query string and the trailing slash.
    3. Make `publish done --outcome --url` equal the item's `target_url`, instead of any Facebook URL (`commands.py:207`).
    4. Add R1 and R5 as fake-claude runs that must fail and pause, and an audit row for a group item with its tab at `www.facebook.com/<page>`.
    5. If Facebook redirects a vanity group address to its numeric id, R5 rehearsal will show it. Until then the run stops as `unidentified`, which fails closed.
  - **Related, already on the branch:** a Facebook Page post from 03 has the same gap within `facebook.com`. It could be posted into a group. Decide whether the same path check (the Page's own path) goes in now.

#### Should fix

- **S1. The `scope.py` change and BP-04's B1.**
  - On this branch, `hosts.BROWSER_PLATFORMS` is `("facebook",)`. So the enabled union equals a group item's own hosts, and Chrome reaches no platform that the item doesn't need. Nothing is widened across platforms today.
  - Once 04 merges, that changes. Take a setup with `community.browser` on, Instagram in `browser` mode and the Facebook Page in `draft`. An Instagram run then gets Facebook's domain rules, and the audit (still the union) accepts Facebook tabs. That is B1 again, through a new door.
  - **Fix:** 04's B1 fix must take the audit's hosts from the claimed item's platform. Group items carry `platform = facebook`, so that mapping works.
    - Add a merge test with `community.browser` on and an Instagram item claimed whose tab is on `www.facebook.com`. It must fail.
    - Better still, narrow the domain rules before the claim to the platforms of the approved, ready items, the way `next_has_image` already reads `claim.approved_ready`.
  - 07 conflicts with this change in `scope.py` and `job.py`. Its fixture override must still replace every host, group items included.
- **S2. Run updates for group items go to `#social-drafts`.**
  - §5.9 says: "Every run that claims an item posts one update to the item's channel (`#social-drafts` or `#community`)".
  - `publish/__init__.py:39` fixes `RUN_UPDATE_DISCORD_CHANNEL = "social-drafts"`, and the tests lock it in at `test_publish_join_run.py:89` and `:130`.
  - Joins are the first group items, so this ticket is the first one this affects.
  - **Fix:** choose the channel per claimed item. That needs a small hook in `run_update`. Or record it as a known gap for 05.
- **S3. `note-rules` clears a confirmation on a whitespace difference (R2).**
  - **Where:** `group_rules.py:180-183` compares after NFC and `strip()` only.
  - Two copies of the same rules taken from a page will differ in line breaks and spacing. In BP-05, a post run in a confirmed group that records the rules again would clear `rules_confirmed` and both day fields, and refuse every later post until Ting Yu decides again.
  - **Fix:** compare with whitespace collapsed (the audit's `_normal`), keep the stored text as seen, and add R2 as a test.
- **S4. `declined` overlaps `pages-not-allowed`, and a declined group comes back every week.**
  - `prompts/publish.md:141` says to record `declined` "when the group says the Page can't join". That is close to AC-P4.3's "offers no way to act as the Jura Page".
  - `group_kinds.problem` blocks only `member`, and `requested` for the join step, so a declined group is a candidate again the next Monday (R3), using a cap slot each time.
  - §4.5 is literal ("not already joined as the Page or requested") and says nothing about a decline. See Questions.
  - **Fix the prompt:** a screen that refuses Pages is `pages-not-allowed`; `declined` is an admin turning the request down.
  - Answers that fail the brand gate twice leave the group a candidate the same way. That fits "failing answers raise nothing", and the run update says "no answers were raised".

#### Nits

- **N6. Answer order isn't checked.** The audit accepts each typed field as any approved answer, so answer 1 typed into question 2's field passes.
- **N7. Ticked answers aren't checked.** The prompt's rule that a "Yes." answer is clicked, not typed (`publish.md:148`), is the model's reading. A tick or a choice isn't auditable.
- **N8. AC-P4.3 test coverage is narrow.** The test that superseding covers "every pending item for that group" uses community posts only (`test_publish_joins.py:385`). The handler is generic, through `items.sync`. Add a waiting answers item to the row.
- **N9. Unrequested state change.** `record_join` sets `pages_allowed = yes` on `requested` and `member`, which §5.6 doesn't ask for. It's a sound inference: record it in the PRD's §5.6 or the ticket.

### Security

The `security-review` skill took its diff from the wrong base: the checkout's `crew/mission-control` against `main`, the same failure as review 04. The two review axes had used the brief's two-agent fan-out, so I worked through its method by hand on `b4f0895...crew/browser-publishing-06-joins-as-the-page`, with the repros above.

| Check | Result |
|---|---|
| A join only with an approval of that group | **Not enforced by code** (B1, an authorisation bypass of the per-item approval). Confidence 9: reproduced end to end (R5). |
| Answers only as approved | Typed text must be an approved answer (`_approved_texts`), and typing on a join before the answers are approved fails the run (tested). Where the answers are typed isn't checked (B1, R1). Order isn't checked (N6). |
| Joining as Ting Yu's personal profile impossible | **Prompt-only, and can't be made impossible in code.** The dedicated Chrome profile is signed in to the Facebook account that administers the Page, which is Ting Yu's own profile, so a join as him is physically possible. The safeguards are step 6 and the join section's identity check (both before any click that joins), the never-switch rule, `wrong-identity` (tested through S10), then rehearsals R5 and R6 and live step U15. Two failure modes: a profile join recorded as `member` would set `joined_as = page` on the run's word; a misread screen recorded as `pages-not-allowed` skips a good group for good, with no alert. The second fails safe. |
| Weekly cap | Proposals count skipped and expired ones (`proposals_in_week`), claims count a fourth join in the week (`claim._join_cap`), and `join_room().left` drives the Monday prompt. A fourth join never starts a run (S10 test). The answers don't count again. Config only lowers it (`limits.community_joins_per_week`). |
| `note-rules` can't confirm | `note_seen` writes only `promo_rules` through `set_parsed` without `by_decision`, so `rules_confirmed=yes` and the days stay gated. It raises one deduplicated request, only from a run that claimed an item in that group (run id from the runner's environment; refused in Terminal and in later runs). It can *clear* a confirmation (S3): that fails closed. |
| Files the CLI reads | `--file` on `done` and `note-rules` goes through `paths.guard` (`headless.install`): secrets files and anything outside the run's folders are refused inside a run (R4). |
| Page text reaching Discord | The rules card quotes page text to Ting Yu in #approvals, as X10 intends. It goes through `privacy.for_discord`, with no mentions allowed and split at 2000 characters. Run updates name the group by register id, and the questions never appear in the update (tested). |
| SQL | `record_join` builds its `SET` from fixed keys, and every value is a parameter. `claimed_in_group` uses placeholders. |
| `community` research job | Gains only `propose-join`. Its Facebook fetch denies and `test_community_fetch_block.py` are unchanged and pass. No browser tools. |

### Blocked paths

None. The diff touches only `docs/`, `jura_growth/`, `prompts/` and `tests/`.

### Questions for Ting Yu

1. **A group that declines the Page's join (S4).** As built, it is proposed again the next Monday and uses one of the week's three. *Recommended:* never propose a declined group again on its own. `join_status` isn't settable through `community set` today, so trying again would need a small `community set` addition. And tell the run that a screen refusing Pages is `pages-not-allowed`, not `declined`.
2. **Answers that fail the brand gate twice.** The group comes back as a candidate the next week. *Recommended:* keep it. The gate failing twice is rare, and a fresh week gets fresh answers.
