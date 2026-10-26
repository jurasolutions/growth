# Code review 02b: BP-02b, community posts and group joins in the publish queue (no browser), round 1

- **Branch:** `crew/browser-publishing-02b-community-items` (61da334, 21bbdf9, e764088, bf227c6, e2d4c1b), compared with its merge-base 9e4e970
- **Ticket:** `.scratch/browser-publishing/issues/02b-community-items.md`. **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md` §2 (SC1, SC3, SC4, SC5; AC-P1.3 as amended 2026-10-27), §4.2 to §4.5, §5.4 to §5.6, §5.10; MC §4.6 and ADR 0003 (exact bytes); test strategy v3, the BP-02b rows; lessons from `code-review-02.md`
- **Reviewed:** 2026-10-27. I read every changed file: `config/community.yaml`, `docs/community.md`, the community `__init__`, `groups.py`, `plan.py` and migration `0003_joined_as_the_page.sql`, the publish `__init__`, `claim.py`, `commands.py`, `group_kinds.py`, `items.py`, `kinds.py` and `limits.py`, the three gate adapters, `tests/publish_world.py`, `tests/test_publish_community.py`, `tests/test_uat_seed_community.py` and `tests/uat/seed.py`. For context I also read `approvals.request`, `community/rules.py` (`confirm_days`, `day_problem`, `read_days`) and `plan.prepare`.

## Verdict: changes-requested

Two blocking findings, both reproduced:

- **B1.** The claim lets a promotional post out in a group whose confirmed rules allow no promotion on any day, and a post with a link out in a group whose rules forbid links. That is AC-P5.1 line 8, which this ticket owns. The claim is the last gate before the browser (BP §4.5).
- **B2.** When `sync()` raises a fresh membership-answers request because the group's URL or the identity changed, the request keeps the old deadline, so it can be left with an hour. SC3 says an answers request is decided by "18:00 on the third day after it is raised". This is the brief's first BP-02a lesson: changed content gets a fresh request with new deadlines.

Everything else the brief asked about holds, and I checked each one:

- **Changed content gets a fresh request on the same item, with new deadlines, except for B2.**
  - For a community post, that holds for text, image bytes, group, destination, posting identity and day, whichever path sees the change first (`sync()` at the claim, `use()`, or the heartbeat). The deadline follows the new day.
  - For a join, it holds for destination and identity. The deadline stays the Sunday of the week it was proposed, as SC3 defines it.
  - For answers that change, `create_join_answers` resets the item's day. Probe p1: answers raised Tue 10 Nov (decide by Fri 13 Nov 18:00) and changed on Thu 12 Nov get a fresh request decided by **Sun 15 Nov 18:00**, and the old request is superseded.
  - The gap is answers whose group changed (B2).
- **The claim checks exact bytes.** `_hand_out` (`claim.py`) reads the item's content once through `kinds.read`, compares that hash with `approval.content_hash` and hands out those same bytes, for every kind.
- **No claim for a group without confirmed rules or days, not joined as the Page, not a good fit, removed or Page-less**, or for a changed identity (the identity is in the hash). Tests cover each (`test_line_9…`, `test_rules_not_confirmed…`, `test_line_10…`, `test_a_group_no_longer_a_good_fit…`).
- **Caps.** Three groups an ISO week (with the Sunday 23:59 and Monday 00:00 boundary), one community post a day (hand posts count), 14 days between posts in a group (13 refused, 14 allowed), three joins claimed a week, three joins proposed a week, and a join proposed after Sunday 18:00 counts in the next ISO week. `joins_per_week` goes through `caps.effective`, so config can only lower it.
- **`community.browser: false`.** Nothing is raised by `publish-plan` or `propose-join`, nothing is claimed, and the approval is not consumed (AC-P5.3, for all three item kinds). See S4 for one path that still raises a card.
- **X7.** The migration only adds columns, and `joined_as` is a virtual column. The test migrates a database at `0002` and compares every old column of every row; legacy `joined = 1` reads `profile`.

## Evidence

- `t.sh` (the developer worktree at e2d4c1b, clean; `JURA_ROOT` set, temp data and outputs folders, Discord double only, no browser) with the full suite printed **2733 passed in 99.23s**.
- The publish, community, gate and seed files (`test_publish_community`, `test_uat_seed_community`, `test_approval_gates`, `test_publish_queue`, `test_publish_items`, `test_publish_regressions`, `test_community`) printed **670 passed in 14.47s**.
- Reviewer probes in a scratch copy of `tests/` outside the repo (`<session scratchpad>/probe02b/tests/test_reviewer_probe_02b.py`) printed **7 passed**. Each one asserts what the code does today:
  - **p1:** changed answers get a fresh request with new deadlines (passes as it should).
  - **p2:** with `community.browser` off, a changed community post still gets a fresh card from `sync()` (S4).
  - **p3:** a promotional post in a group whose confirmed promotion days are `none` is **claimed** (B1).
  - **p3b:** `rules_for()` of that group reads `no_promo = True`, `promo_days = None`, and `day_problem(…, promotional=True)` returns None (B1's cause).
  - **p4:** a post with a link, in a group whose confirmed rules say "No links in posts." (`no_links = True`), is **claimed** (B1).
  - **p5:** answers raised Tue 10 Nov; the group's URL changes Fri 13 Nov at 17:00; `sync()` supersedes and raises a fresh answers request decided by **Fri 13 Nov 18:00**, one hour away (B2).
  - **p6:** a queued post moved to a group joined only as Ting Yu gets a fresh card. Approved, it is refused by every `publish next` ("its group isn't joined as the Jura Page") (S6).
- `git merge-tree --write-tree crew/mission-control crew/browser-publishing-02b-community-items` and the same against `crew/browser-publishing-03-browser-job`: both **clean**, no conflicts.
- Pyright, from the Standards sub-agent: 72 errors at base and on the branch, and every touched file has the same count as at base. **0 new.**
- Blocked paths: `git diff --name-only` shows nothing under `inputs/`, `design-system/`, `.env`, the live `data/growth/` or CI. **No finding.**

## Standards

### Blocking

None.

### Should fix

- **S1. The card's link list misses links the claim and the brand gate see.** `group_kinds.py:41` `_LINK` copies `kinds.py:37` and only matches `http(s)://`. `brand_check.find_links` (brand_check.py:160), which `plan.is_promotional` uses, also finds bare domains. For "See jurasolutions.sg for more." `find_links` returns `['jurasolutions.sg']` and `_LINK` returns `[]`, so the card says "Links in the text: none" for a post the claim treats as promotional. SC1 says the card shows "any link in the text". Use `brand_check.find_links` in the preview (`group_kinds.py:202`).
- **S2. Reuse: group eligibility is written four times, with four wordings.** `claim._group_problem` (claim.py:167), `items.join_problem` (items.py:260), `group_kinds._group_gone` (group_kinds.py:61) and `group_kinds.note` (group_kinds.py:253). A new disqualifier needs four edits, and B1's fix should land in one place. Also, the group lookup `SELECT * FROM community_groups WHERE id = ?` is repeated at claim.py:136, items.py:222, items.py:286 and `group_kinds._group`; `groups.get` (community/groups.py:324) already exists.
- **S3. Reuse: ISO-week arithmetic three times.** `claim._week` (claim.py:147), `items.proposals_in_week` (items.py:253) and the Sunday in `group_kinds.closes` (group_kinds.py:120). `plan.week_days(timeutil.iso_week(day))` (plan.py:82) already gives Monday to Sunday.

### Nit

- **Repeated switches on item kind** across `kinds.read`, `kinds.closes`, `kinds.opens`, `kinds.skipped_by_hand`, `group_kinds.closes`, `group_kinds.opens`, `items.raise_request`, `claim._item_problem` and `commands.STEPS`. The kind classes (`SocialPost`, `CommunityPost`, `GroupJoin`) are the natural home for `read`, `closes`, `opens`, the request reason and the step. A judgement call; fine as a follow-up.
- `items._probe` (items.py:339) builds a 20-field `Item` positionally, so a new field silently shifts the arguments. Use keywords.
- items.py:324 writes its own `parent_item … state = 'ready'` query beside `_existing` (items.py:191).
- `limits.community_joins_per_week` reads `config/community.yaml` through `config.agent_config`, while `plan.groups_per_week` reads it through the community settings. Two ways to read one file.
- `_claimed_posts(…, but=)`: `excluding_item` says what it is.

## Spec

### Blocking

- **B1. A promotional post, or a post with a link, is claimed in a group whose confirmed rules forbid it on every day.** AC-P5.1 line 8: "A community post on a day the confirmed rules close is refused." BP §4.5: the item's day must be "open under the days he confirmed".
  - `_post_problem` (claim.py:177-211) relies on `rules_mod.day_problem` alone (claim.py:193). When Ting Yu confirms promotion days as `none`, `confirm_days` stores `promo_days = promo or None` (rules.py:243), that is **None**, with `no_promo = True`. `day_problem` then sees no promotion-day limit and passes a promotional post on any day. It never looks at `no_promo` or `no_links`.
  - **p3:** group with rules "No promotion.", promotion days `none`, post days `any`; a post with a Jura link, approved; `publish next` **claims it**.
  - **p4:** group with confirmed rules "No links in posts." (`no_links = True`); the same post; **claimed**.
  - `plan.prepare` does refuse these (`rules.no_promo`, `rules.no_links`, plan.py:372-382), but only at `plan-add`. The rules are often confirmed after the plan (a `group-rules` decision, or new rules text that clears and re-confirms). The claim is the only check after that, and the account risk in BP §4.1 is exactly an admin removal for promotion.
  - Fix: in `_post_problem`, refuse a promotional post when `rules.no_promo`, and a post with links when `rules.no_links` (or when `not rules.known`), in the one shared eligibility helper from S2. Add both cases to the line 8 table. Changing `day_problem` so `none` reads as an empty set would also cover the promotion case, but it is ticket 07's function and the plan reads it too, so keep the fix in the claim unless the tech lead prefers otherwise.

- **B2. A fresh answers request raised by `sync()` keeps the old deadline.**
  - The spec says, in SC3: "A membership-answers request's are 18:00 on the third day after it is raised." AC-P1.3 adds that a change to any field raises a fresh request.
  - `refreeze` (items.py:388-394) keeps `item.day` when the content has no `day`, and answers content never has one. `group_kinds.closes` then gives `item.day + 3` (group_kinds.py:121-122), the first request's deadline.
  - **p5:** answers raised Tue 10 Nov. The group URL is corrected Fri 13 Nov at 17:00. The fresh card is decided by **Fri 18:00**: one hour for Ting Yu to read and approve membership answers.
  - `create_join_answers` resets the day for changed answers (items.py:329), so the two paths disagree.
  - Fix: when `sync()` raises a fresh request for an `ANSWERS_ITEM`, set the item's day to today first, as `create_join_answers` does. Add the group and identity cases to `test_a_changed_join_or_answers_item_gets_a_fresh_request`, asserting `decide_by`.

### Should fix

- **S4. A card is still raised while `community.browser` is off.** The ticket's config comment and the developer's note say "nothing is raised" while it is off, and BP A13 says a switched-off platform raises nothing. `items.sync()` calls `raise_request` for any ready item whose content changed, and `approvals.request` doesn't consult `switched_off`. **p2:** a community item raised while on; switch off; edit the text; `sync()` raises a fresh `community-post` card. It can't be claimed while off, so nothing unapproved goes out, but Ting Yu gets a card he can't act on. Skip raising in `sync()` while the kind is switched off (leave the old request to be superseded or lapse), or record that this is intended.
- **S5. The `#community` checklist still says "Post these yourself … Nothing here is posted automatically"** (plan.py:605) for every post, including those that now have a `community-post` card and go out through the browser. If Ting Yu posts one by hand and doesn't record `community posted`, the approved card can still be claimed, and the group gets the post twice. Mark the Page items on the checklist as "goes through #approvals; don't post by hand", or leave them off it.

- **S6. A planned post moved to a group not joined as the Page gets a card it can never use.** BP §5.4 says the item exists "for each planned post in a group joined as the Page". `read_post` (group_kinds.py:76-77) doesn't check `joined_as`, so `sync()` raises a fresh card after a group change. **p6:** Ting Yu approves it, and every `publish next` refuses it until it expires. Treat `joined_as != 'page'` as gone in `read_post`, so the request is superseded with no new card.

### Nit

- **§5.10 `post_as`** is unchanged (`config/community.yaml:35`). This is not a finding against this branch: ticket 05 owns that change (05-community-posts-as-the-page.md:16).
- **The weekly proposal cap counts withdrawn proposals.** `proposals_in_week` (items.py:251) counts every `community_join` item of the week, so a join Ting Yu skipped still uses one of the three. That fails closed, and it is defensible. But "up to the weekly join cap" doesn't say that skips count, so say so in `docs/community.md` (see the question below).
- `create_join_answers` doesn't check that the parent join was approved and claimed. BP-06 is its only caller and calls it from `publish done --outcome questions`, so record that precondition in its docstring or assert it there.

## Security

I ran the security pass on this diff only. **No findings at 8/10 confidence or higher.** I checked:

- **SQL.** Every query is parameterised. The one built string, `_existing`'s `state IN (…)`, only adds `?` placeholders.
- **Files.** `read_post` reads `community_posts.image_path`, which `plan.prepare` only accepts through `paths.guard` and `image_problem` (a PNG inside the run's folders, never a secrets file). Copies go to `work/publish/<A-id>/` through `paths.writable`, named by `Path(…).name`. Same pattern as the social path.
- **Authority.** `community set` (and with it `joined_as=page`) and `propose-join` are not in the community job's command list (`community/__init__.py` `permissions`), so a headless run can't mark a group as joined as the Page or propose a join. `publish-plan` can raise `community-post` requests, as BP §5.4 says, and only Ting Yu's decision approves them.
- **Discord.** Cards carry the group name, URL, rules, fit reason, text and, for answers, the group's questions: text from the register and from web research. `discord.py` posts with `allowed_mentions: {"parse": []}`, and `test_community_and_join_cards_carry_nothing_planted` runs `assert_clean` over the community, join and answers cards.
- **Integrity.** B1 is a gap in the gate, filed under Spec: it needs a rules change after the plan, not an attacker.

## Questions for Ting Yu

- **Do skipped or expired join proposals count against the three proposals a week?** *Recommended:* yes, as built. It fails closed and keeps the weekly pace you set. Record it in `docs/community.md`.
