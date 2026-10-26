# Code review 06: BP-06, group joins as the Jura Page

- **Branch:** `crew/browser-publishing-06-joins-as-the-page` at adc6adc (dc05893, 3cc8967, 0776434, f31dc23, adc6adc), compared with its merge-base b4f0895 on `crew/mission-control`. `git merge-tree` against `crew/mission-control` is clean. It conflicts with 04 in `prompts/publish.md`, `tests/test_publish_prompt.py` and `docs/social.md`, and with 07 in `scope.py` and `job.py`.
- **Ticket:** `.scratch/browser-publishing/issues/06-joins-as-the-page.md`. **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md` (SC4, AC-P5.1 line 4, §4.2, §4.3, §4.5 to §4.7, §5.4 to §5.9). **Tests:** test strategy v3, the BP-06 rows. **Lessons:** code reviews 02b, 03 and 04 (B1: audit against the claimed item's own hosts).
- **Reviewed:** 2026-10-27. I read every changed file: the 17 files in `docs/`, `jura_growth/agents/community/`, `jura_growth/agents/publish/`, `prompts/` and `tests/`. For context I also read `group_kinds.py`, `claim._join_cap`, `items.proposals_in_week`, `hosts.py`, `paths.guard`, `headless.install` and `privacy.for_discord`, plus the 04 and 07 diffs to `scope.py` and `job.py`.

## Verdict: changes-requested

One finding blocks: **B1**. The publish run's audit accepts a group item acted on anywhere on Facebook. So a run that claimed Ting Yu's approved join for group A can join group B instead, record A as `requested`, and finish `ok` with no alert and no pause. A run can also post approved membership answers on the Jura Page's own timeline and record the group as joined as the Page. This is the BP-04 B1 lesson, one level down: an approval binds a destination, and the run's only code backstop, the audit, doesn't check the destination.

The rest is sound:

- The outcome handlers, the answers step, the weekly cap, `pages-not-allowed` for every kind and `note-rules` all do what the spec says.
- `note-rules` can't confirm rules or set days.
- Every file option goes through `paths.guard`.

## Evidence

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

## Standards

### Should fix

- **S5. 57 new pyright errors** in `tests/test_publish_joins.py` (43), `tests/test_publish_join_run.py` (12) and `tests/test_community_joins.py` (2). This breaks `docs/agents/crew.md`: "don't add new errors in files you touch".
  - Nearly all are Optional access, the same pattern as review 04's N2.
  - One looks like a real error: `test_publish_joins.py:399` reads `superseded_note` from an `ApprovalKind`, and pyright says that type has no such attribute.
  - **Fix:** add `assert x is not None` where needed, and type the kind lookup.
- **S6. Possible Duplicated Code: `groups.record_join` (`groups.py:328`).**
  - It repeats the tail of `set_parsed` (`:281-291`): the `updates` dict, `updated_at`, and the f-string `UPDATE`. It also writes `joined_as_set` and `joined`, so two functions now maintain the `joined_as` invariant.
  - It logs without `run_id`, while `note_seen` passes one.
  - **Fix:** route it through one writer, or share the update helper, and pass `run_id`.

### Nits

- **N1. Outcome words live in four places:** `outcomes.OUTCOMES`, `groups.JOIN_STATUSES`, `job.OUTCOME_LINES` and `job.OUTCOME_NOUNS` (`job.py:35-43`). The two dicts in `job.py` are parallel maps over the same keys. One table in `outcomes.py` would hold them all (possible Shotgun Surgery).
- **N2. One name, two meanings.** `outcomes.PAGES_NOT_ALLOWED` is an outcome key and `groups.PAGES_NOT_ALLOWED` is a reason text. Both appear in `outcomes.record`.
- **N3. Unused field.** `Recorded.raised` is set but never read (possible Speculative Generality).
- **N4. Readability.**
  - `commands.py:238`, `(answers_file is None) != (outcome != outcomes.QUESTIONS)`, is hard to read, and `outcomes.record` checks part of it again.
  - The local `done` in `_done_outcome` shadows the `done` command.
- **N5. Suppressed instead of fixed.** The new `# type: ignore[return-value]` at `groups.py:342` and `:356` hides the Optional return. An assert would fix it (see S5).

## Spec

### Blocking

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

### Should fix

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

### Nits

- **N6. Answer order isn't checked.** The audit accepts each typed field as any approved answer, so answer 1 typed into question 2's field passes.
- **N7. Ticked answers aren't checked.** The prompt's rule that a "Yes." answer is clicked, not typed (`publish.md:148`), is the model's reading. A tick or a choice isn't auditable.
- **N8. AC-P4.3 test coverage is narrow.** The test that superseding covers "every pending item for that group" uses community posts only (`test_publish_joins.py:385`). The handler is generic, through `items.sync`. Add a waiting answers item to the row.
- **N9. Unrequested state change.** `record_join` sets `pages_allowed = yes` on `requested` and `member`, which §5.6 doesn't ask for. It's a sound inference: record it in the PRD's §5.6 or the ticket.

## Security

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

## Blocked paths

None. The diff touches only `docs/`, `jura_growth/`, `prompts/` and `tests/`.

## Questions for Ting Yu

1. **A group that declines the Page's join (S4).** As built, it is proposed again the next Monday and uses one of the week's three. *Recommended:* never propose a declined group again on its own. `join_status` isn't settable through `community set` today, so trying again would need a small `community set` addition. And tell the run that a screen refusing Pages is `pages-not-allowed`, not `declined`.
2. **Answers that fail the brand gate twice.** The group comes back as a candidate the next week. *Recommended:* keep it. The gate failing twice is rare, and a fresh week gets fresh answers.
