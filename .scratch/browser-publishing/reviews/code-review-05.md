# Code review 05: BP-05, community posts as the Jura Page

- **Branch:** `crew/browser-publishing-05-community-posts-as-the-page` at 540372a (5237529, 64ad81e, 8734395, 540372a). It is compared with its merge-base 82df0bc. `git merge-tree` against `crew/mission-control` (6f38c67) is clean.
- **Ticket:** `.scratch/browser-publishing/issues/05-community-posts-as-the-page.md`.
- **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md`. The parts that apply are SC4, SC5, SC6 and SC11, §3.3, §4.3, §4.5 to §4.7, §5.5 and §5.6, and AC-P4.3, AC-P5.1 lines 8 to 10, AC-P6.2 and AC-P11.1.
- **Tests:** the BP-05 rows of test strategy v3.
- **Lessons applied:** code reviews 02, 02b, 03, 04, 06 and 07.
- **Reviewed:** 2026-10-27.
- **What I read:** every changed file (all 14) in `config/`, `docs/`, `jura_growth/agents/community/`, `jura_growth/agents/publish/`, `prompts/` and `tests/`. For context I also read:
  - `hosts.py` in full, `outcomes.py` in full and `job.py` in full
  - `group_kinds.py`, and the community parts of `claim.py`
  - `items.create_community_post` and `items.sync`
  - `groups.remove`, `plan.mark_posted`, and the header and `places` check of `audit.py`

## Verdict: approve

No finding blocks. The approval binds the destination in two independent places:

- **`publish done` and `publish resolve`** accept only one post's own address inside the claimed item's group.
- **The transcript audit** (from 06) holds every tab and `navigate` to that group's path.

So posting in another group or on the Page timeline fails the run and pauses `publish` (R1, R4, and the branch's own end-to-end test). The other protections hold:

- Unapproved bytes or extra text fail the audit (R7).
- A closed day, unconfirmed days and the one-a-day cap all keep the item from being claimed (the branch's run test, and R5).
- AC-P6.2 runs `groups.remove` and `items.sync` in the stop's own transaction (R3 and the branch's tests).
- No page text reaches the row, `#alerts` or `#community`, including after an `after_run` crash (R2, R9, R10).

There are two should-fixes:

- **S1:** an audit-failed post keeps its "posted" record without saying so.
- **S2:** the address rule is unproven against Facebook's real addresses.

Neither lets something unapproved go out. S1 can go in this ticket or in a short follow-up. S2 is a check to add to U14.

## Evidence

- **Full suite** in the developer worktree at 540372a, with `JURA_ROOT` set, temporary data and outputs folders, the fake `claude`, the Discord double and no Chrome. `uv run --frozen pytest -p no:cacheprovider -o addopts="" -q -rs` printed **3292 passed in 137.52s**, with 0 skipped. The worktree is still clean afterwards.
- **Pyright** (from the standards reviewer): no new errors. Two fewer than at the merge-base. The new test files have 0.
- **Blocked paths:** `git diff --name-only 82df0bc...` shows nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **No UI files changed**, so there was no web design review.
- **Repros:** `test_zz_review_05.py` runs from a scratch copy of `tests/`, so the worktree is untouched. It printed 10 passed. Every row behaved as listed below.

  | Row | Case | Result |
  |---|---|---|
  | R1 | `hosts.group_post_problem` on 22 addresses: the group's own `/posts/<n>/` and `/permalink/<n>/`, with or without a query or fragment | accepted |
  | R1 | The same check on another group's post, the group page, `/posts/` with no number, `/about/`, the Page timeline's post, `/groups/<own>0/…` and `/groups/<own>-x/…` | refused |
  | R1 | The same check on `..` segments, `%2F`, a non-numeric id, an extra segment, a look-alike host, `http://`, a user name, a port, a backslash, another group with the own path in the query, and `javascript:` | refused |
  | R1 | `publish done --url` with another group's post | refused, and the refusal doesn't name the path. The item stays `claimed` |
  | R2 | `done` whose live text has a name and a phone number added | recorded with `live_text_matches=0`. Publishing pauses and an alert goes out, and the alert quotes neither the name nor the number |
  | R3 | `publish stopped --reason admin-warning` on a group join item | the group is `removed=1` (AC-P6.2 "in a group" covers joins too) |
  | R4 | `publish resolve posted` with another group's post | refused. The own group's post is accepted, and the planned post becomes `posted` |
  | R5 | Two approved posts in two groups on the same day, the first one done | the second gets "nothing due" from `publish next`, giving the per-day cap as the reason |
  | R6 | Full run: the run types and posts on the Page timeline, then runs `done` with an own-group post address | the run fails and publishing pauses, **but** the item stays `done/posted`, the plan row stays `posted` with `posted_via=browser`, and `last_posted_at` is set. The summary still reads "posted · <url>" (S1) |
  | R7 | Full run with " Call us today" typed after the approved text | the run fails and publishing pauses. The error doesn't quote the typed text |
  | R8 | Full run where the composer shows "Posting as Ting Yu" and the run posts anyway | `status=ok`. The identity check is in the prompt only, as reviews 03 and 06 found (see Security) |
  | R9 | Full run where `job._audit` raises with page text in the exception | `failed_closed` runs: the run fails and publishing pauses. No page text reaches the run row, `#alerts` or `#community` |
  | R10 | Held for admin approval, stopped as `unidentified`, with page text holding a phone number | the item is `stopped`, the plan row stays `planned` and publishing pauses. No second card can be raised over the same post (`create_community_post` finds the item that already exists). The number doesn't appear in any alert |

## Standards

There are no hard violations. Pyright and the voice rules pass, and the earlier lessons hold:

- The host is named, never the path (`hosts.py:122`).
- The group appears by its register id only (`commands.py:277`).
- Removal goes through the one writer, `groups.remove`, which now takes `run_id`.

### Nits

All of these are judgement calls.

- **N1. Possible Duplicated Code.**
  - The phrase `where = f"in run {run_id}" if run_id is not None else "outside a run"` appears at both `commands.py:275` and `outcomes.py:209`.
  - The group segment pattern `([A-Za-z0-9._-]+)` appears at both `hosts.py:76` and `hosts.py:106`.
  - The `match.group(1) in (".", "..")` test at `hosts.py:121` is redundant, because `within()` already refuses dot segments.
- **N2. Possible Repeated Switches.** `found.kind == items.COMMUNITY_POST_ITEM` is now tested at `_host_problem` (`commands.py:77`) and at `_mark_published` (`commands.py:94`), beside `POSTS` and `STEPS`. A per-kind table like `STEPS` would keep a third post kind to one edit.
- **N3. One fact in two places.** `post_as` is in `config/community.yaml:37`, and the same string is the code default at `plan.py:606`.
- **N4. Copied test helpers.** `group_of` and `post_row` are copied in both `test_publish_community_posts.py` and `test_publish_community_run.py`. `group_of` is also in the 06 join tests. They belong in `tests/publish_world.py` (review 04, N3).
- **N5. Wording.**
  - `POSTS_ONLY` ("a join is recorded with --outcome") is reused in `resolve` (`commands.py:373`), where `--outcome` doesn't apply.
  - The refusal at `commands.py:378` says "on {found.platform}". For a community post it should say "in its group".
- **N6. Two address rules.** `group_post_problem` accepts a query or fragment, so `?comment_id=` is accepted. `group_url_problem` (`hosts.py:99`) refuses one. This is harmless, because the path still binds the post, but the address recorded may be a comment's link. Consider dropping the query and fragment before storing.

## Spec

### Should fix

- **S2. The post-address rule is unproven against Facebook's real addresses.**
  - **Where:** `hosts.py:110-123`, used by `done` and `resolve`. The audit's `within` check has the same assumption.
  - **The assumption:** the permalink uses the same group segment as the register's URL. Facebook may show a group post under the group's number while the register holds its name in the address, or the other way round.
  - **What happens if it's wrong:** it fails safe, but badly:
    - `done` refuses the live post, so the item becomes `unknown` and publishing pauses.
    - `resolve posted` refuses the same address.
    - The audit fails the run when it opens the permalink.

    Ting Yu is left to record it with `community posted` and settle the item as `not-posted`, which reads wrongly.
  - **Fix:** add a step to U14's script (`reviews/qa-05.md`): use a test group whose register URL holds the form its permalinks don't, and record which form Facebook shows. If the forms differ, record the group's number alongside its name in the register, and accept either form.
  - **Rule:** AC-P7.1 and AC-P7.2 for a group post, and BP §5.6 (a post's own URL recorded).

### Nits

- **N7. Line 10 doesn't use the decision.** AC-P5.1 line 10 (`test_publish_community_run.py:157`) uses `pw.group`'s confirmed days written straight to the DB, not the `group-rules` decision the ticket names for lines 8 to 10. It also asserts `SUPERSEDED` from `group_kinds.gone`, not a refusal at `publish next`.
  - Line 9 (`:146`) can only be built directly, because AC-M10.6 refuses an approval with no days. A comment saying so would help.
  - The claim-time refusals are 02's, and its unit tests cover them.
- **N8. Two paths for one removal.** `community removed` (`community/__init__.py:273`) calls `groups.remove` without `items.sync`, while the stop runs both. The waiting cards are superseded either way, the hand command at the next sync, so the docs are accurate. Putting the sync inside one helper would keep the two paths the same.
- **N9. A held post records only by hand.** A post held for admin approval stops as `unidentified` (the conductor's decision, until U14). §4.6 reserves `unidentified` for something the run couldn't identify. The item ends `stopped`, which `resolve` doesn't settle, so `community posted` is the only way to record the post once it is approved. `docs/community.md` says so. Revisit after U14.
- **Scope beyond the ticket:** `resolve posted` for community posts (`commands.py:372-378`). It is the natural partner of `done` and holds to the same address rule (R4). Accepted.

## Security

Done by hand on `82df0bc...540372a`, with the repros above. The brief's fan-out limit of two went to the two review axes, so I didn't start a separate security-review agent. The diff has no SQL built from input, no secrets and no new file reads.

### Should fix

- **S1. An audit-failed community post keeps its "posted" record, and nothing says it may be wrong.**
  - **Where:** `job.after_run` (`job.py:84-104`) undoes a join on an audit failure (`undo_joins`, from review 06's N11), but leaves a post as it is.
  - **What R6 shows:** in a run that posted on the Page timeline and then gave its own group's address, the item is `done/posted`, `community_posts.status = posted` with a URL the run may have made up, and `last_posted_at` is set. The run summary, which becomes the `#community` line, still says "A-0001 · Facebook group N · posted · <url>". The alert says only that the audit failed.
  - **Why it isn't blocking:** publishing pauses, and the post went out only with an approval.
  - **Why it matters:** the record is the one Ting Yu trusts to know where his Page posted. A wrong `last_posted_at` also holds the group for 14 days.
  - **Rules it breaks:** the 06 N11 lesson (an audit failure must say which record to check), and BP §4.7 and AC-P9.3.
  - **Fix:** in `after_run`, when the audit fails, name each claimed post in the error, for example: "A-0001's posted record for group N may be wrong: check the group, and the Page's own timeline". Mark its summary line "· the audit failed". Don't set the plan row back to `planned`: the post may be live, and `planned` would invite a manual repost.

### Residual risk (not a new finding)

Posting as Ting Yu's profile is stopped by the prompt only (R8), as reviews 03 and 06 recorded. Nothing in the transcript can show the composer's identity. AC-P11.1 is a prompt-level criterion, and U14 is its live check.

### Checked and holding

- **Another group or the Page timeline:** blocked by `done` and `resolve` (R1, R4) and by the audit (the branch's run test). Look-alike hosts, user names, ports, backslashes, `..` and `%2F` are all refused.
- **Unapproved bytes or extra text:** blocked by the audit (R7). Live text that differs alerts and pauses (R2).
- **A closed day, unconfirmed days and the per-day cap:** enforced at the claim (the branch's run test, and R5).
- **Page text:** never reaches the row, the alerts or the updates. The removal reason is the code's own words (`outcomes.py:210`).
- **A crash in `after_run`:** fails closed (R9).
