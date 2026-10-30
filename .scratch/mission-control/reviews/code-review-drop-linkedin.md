# Code review: drop LinkedIn (crew/drop-linkedin)

- **Branch:** `crew/drop-linkedin` at 6a9099d (PR jurasolutions/growth#4). Commits 29588a5 publish, 6f7b4b7 community, bae81e2 social and config, 6a9099d docs.
- **Compared against:** merge-base with `main`, 0c2fa3e.
- **Spec:** Ting Yu's decision of 2026-10-29, recorded as the amendment notes at the top of `jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md` and `prd-jura-social-content-2026-10-24.md`. LinkedIn is switched off (`platforms.linkedin.enabled: false`), not removed.
- **Reviewer:** crew reviewer, 2026-10-29.

## Verdict: approve

There are no blocking findings. Two should-fix findings are worth a small follow-up, and neither one lets a switched-off platform post, open a host, or get a new card.

## Evidence

- **Full test suite.** I ran it in a detached worktree of 6a9099d with `JURA_ROOT` set and temporary data and outputs folders, using `uv run pytest -rs -p no:cacheprovider -o addopts=""`. Result: **3672 passed, 0 skipped, in 167s**. That includes `tests/test_apps.py::test_existing_app_prds_pass_the_template`, now that the PRD has been fixed.
- **Live database.** I copied the live `growth.db` to a temporary folder with `sqlite3 -readonly .backup` and never touched the live file.
  - The copy holds 3 LinkedIn `social_posts` drafts (2026-10-27, 10-28, 10-29, all `draft`), 0 `publish_items`, 0 `approvals`, and 0 `community_groups` with channel `linkedin`. None of the 8 `other` groups is on linkedin.com.
- **main against the branch on that copy.** I ran `social.digest` for 10-27, 10-28 and 10-29 with each version of the code:
  - main reports "3 drafts waiting (facebook, instagram, linkedin)";
  - the branch reports "2 drafts waiting (facebook, instagram)";
  - no row is written or changed. The leftover LinkedIn drafts stay as they are.
- **Probes.** I ran three throwaway tests in the disposable worktree and deleted them afterwards. Their results are under S1, S2 and N1 below.
- **Blocked paths.** `git diff --name-only main...crew/drop-linkedin` touches nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.

## Focus questions

1. **Can a switched-off platform still produce a draft, render, publish item, approval card or host rule?** No, apart from the gaps below.
   - Drafts: `submit.active_platforms` and `plan.build` already used `enabled_platforms()`, and `drafts.load` reads only active platforms.
   - Renders: `render_setup` and the `social render` default sizes are now built from the enabled platforms.
   - Items and cards: `items.create_social` (`items.py:154`) and `Platform.browser` (`settings.py:68`) stop them.
   - Host rules: `scope.enabled_platforms` goes through `Platform.browser`.
   - An item approved before the switch: `SocialPost.switched_off` (`kinds.py:206`) makes `approvals.use()` refuse with `SWITCHED_OFF` before it claims anything. This is tested in `tests/test_publish_linkedin_off.py`, and my probe confirmed it.
   - Gaps: S1 (the upload deny) and N1 (a card raised before the switch stays live until it lapses).
2. **Does `Platform.browser` now requiring `enabled` weaken any Facebook or Instagram gate?** No.
   - Every caller of `.browser` narrows: `submit.py:319`, `items.py:156`, `kinds.py:208` and `scope.py:48`. No caller does less checking when it is False.
   - In `config/social.yaml`, Facebook and Instagram are still `enabled: true` and `publish_mode: draft`.
3. **Does anything act on existing live rows in a way that loses data or misreports?**
   - No data is lost. Nothing in the PR writes to the leftover LinkedIn drafts, and the database has no LinkedIn items, approvals or groups.
   - The one change in reporting is deliberate: the digest stops counting the three leftover LinkedIn drafts as waiting.
   - Those drafts stay `draft` in `social history`. `social skip <date> all` no longer touches them (N2).
4. **Are the docs and `uat.md` consistent?** Yes, with one stale ADR sentence (N5).
   - These all say LinkedIn is switched off: `docs/social.md`, `docs/community.md`, `README.md`, `CONTEXT.md`, the prompts, the browser-publishing setup guide, and `uat.md` C1, Part R and D4.
   - `tests/test_uat_seed_publish.py` asserts that the UAT seed has LinkedIn `enabled: false`.

## Standards

### Should fix

- **S1. A switched-off item still lifts the `file_upload` deny.**
  - Where: `jura_growth/agents/publish/scope.py:100`, which reads through `claim.approved_ready` (`claim.py:99`).
  - The problem: `next_has_image()` counts every approved, unused item that is ready today, without asking the kind's `switched_off`.
  - Reproduced: LinkedIn on and in `browser` mode; a LinkedIn item with an image is approved, and a text-only Facebook item is approved; then LinkedIn is switched off. Results:
    - `approved_ready` returns `['linkedin', 'facebook']`;
    - `next_has_image()` returns `True`;
    - `FILE_UPLOAD` is missing from `disallowed_tools`;
    - `next_item` claims the Facebook item.
  - Why it matters: the run gets an upload tool that the item it will be handed doesn't need.
  - Rule broken: the scope docstring says "`file_upload` unless the item `publish next` would hand out now has an image". It also misses focus 1's "including an item approved before the switch".
  - Why it isn't blocking:
    - the domain rules still confine page tools to the Facebook hosts;
    - the run audit checks uploads;
    - an item that is in draft mode has the same gap on `main`;
    - the live database has no LinkedIn items.
  - Fix: skip items where `kinds.switched_off(conn, item)` gives a reason, in `approved_ready` or in `next_has_image`.
- **S2. A LinkedIn group gets into the register under another channel.**
  - Where: `jura_growth/agents/community/groups.py:129`.
  - The problem: the refusal checks only `channel == "linkedin"`.
  - Reproduced: `validate()` with `channel: "other"` and `url: https://www.linkedin.com/groups/123456/`, while LinkedIn is off, returns `[]`.
  - Rule broken: the promise in the `config/social.yaml` comment (line 81, "no LinkedIn group in the community register") and in `docs/community.md:105`. Today only `prompts/community.md` enforces it.
  - Impact: low. The community plan only plans `facebook` groups.
  - Fix: also refuse a URL on a linkedin.com host while LinkedIn is off, the same way Facebook domains are already refused under other channels (`groups.py:144`).

### Nit

- **N3. `tests/publish_world.py:84` switches platforms on silently.** `social_config` turns on any platform named in `browser` when `enabled` is left out. The new switched-off tests pass `enabled=` explicitly, so they are sound. A later test that omits it would quietly exercise the switched-on path. Consider requiring `enabled` whenever LinkedIn is in `browser`.
- **N4. Docstrings point to a test file that doesn't exist.**
  - `tests/test_social.py:198` and `tests/test_social_render.py:85` cite `test_linkedin_off.py`.
  - The real files are `test_social_linkedin_off.py`, `test_publish_linkedin_off.py` and `test_community_linkedin_off.py`.
  - The render docstring also points elsewhere for the switched-on cover test, which is actually the next function in the same file.
- **N6. A small duplication and a hard-coded rule.**
  - `items.py:154` and `kinds.py:206` check `enabled` and then `browser`, which now includes `enabled`. That is fine for the message, but it is duplicate logic.
  - `groups._linkedin_on` (`groups.py:109`) hard-codes LinkedIn. A general rule ("a channel that names a social platform needs that platform on") would also cover S2.

## Spec

### Should fix

None beyond S1 and S2. They are listed under Standards, and both also fall short of the amendment's "no longer drafts for, publishes to or plans for LinkedIn".

### Nit

- **N1. A card raised before the switch stays live until it lapses.**
  - Where: `jura_growth/agents/publish/items.py:462-469`. While a kind is switched off, `sync()` keeps the live request.
  - Reproduced: after the switch, sync raises nothing, the old request is still `pending`, and approving it records "recorded". `use()` still refuses it, and it lapses at 18:00.
  - On top of that, the digest's `waiting` count now hides that draft (`social/__init__.py:49-53`).
  - This is consistent with how a platform in draft mode already behaves, and with the comment there. `docs/social.md` says "no approval card", which is true for new cards only.
  - No live LinkedIn card exists, because LinkedIn was in `draft` mode on `main`.
  - Optional: supersede live requests of a switched-off kind during sync.
- **N2. `social skip <date> all` now covers only the enabled platforms** (`commands.py:118`).
  - The three leftover LinkedIn drafts in the live database stay `draft` unless Ting Yu runs `social skip <date> linkedin`.
  - Nothing is lost or posted. The digest's `published` count likewise ignores a LinkedIn post recorded by hand (`social/__init__.py:58-63`). Both are as intended now that LinkedIn is dropped.
- **N5. One ADR sentence is stale.** `docs/adr/0005-browser-automation-runs-only-in-the-publish-job.md:17` still says "each platform … that is in `browser` mode", without "switched on". This is a historical ADR, so a one-line amendment is optional.

## Security

- **Blocking:** none. **Should fix:** none.
- I did the pass by hand over `0c2fa3e...crew/drop-linkedin`, because the skill picked up an empty diff from the `main` checkout.
- The changes are narrowing:
  - the platform switch only refuses more;
  - the new SQL in the digest is parameterised;
  - there is no new subprocess, deserialisation, file path from input, secret, or network call;
  - there are no blocked-path changes.
- S1 is the only permission-related item. It is defence in depth, contained by the domain rules and the upload audit.
