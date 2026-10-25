# 02 — BP-02a the publish queue for social posts, with no browser yet

Status: ready-for-agent
Blocked by: mission-control#01, mission-control#04b (and the blocker fixes on `main`, including 02 and 07)
PRD ticket: BP-02 in `prd-jura-browser-publishing-2026-10-25.md` §5.12, first half: social posts (split by the ticket review; community items are 02b)
Covers: SC1, SC2, SC3 (posts), SC5, SC7, SC10 (headless half), SC6 (command half), SC8 (the digest)

## What to build

Every social variant on a platform in `browser` mode that passes the brand gate becomes one publish item with frozen content and one `social-post` approval request in `#approvals`. `publish next` hands out at most one approved item, after every cap, kill switch and claim-time check, and claims its approval in the same transaction. `publish done`, `stopped`, `queue` and `resolve` record what happened. No browser is involved: the commands are driven from tests and Terminal, so the queue is provable before Chrome touches anything.

## What to change

- A new `publish` plug-in (`jura_growth/agents/publish/`) with its own migration for `publish_items` (BP §5.6; no approval state, A2). Laid out by module: the claim checks in `agents/publish/claim.py`, exposing `claimable(conn, now)` for 03's read-only precheck; the job hooks in `agents/publish/job.py`, which 03 fills in. The publish plug-in declares all three browser-publishing kinds; the community plug-in declares only `group-rules`.
- The `social-post` kind against MC §4.6, with the content, deadlines and actions in BP §5.5; item creation from `social submit` for each platform in `browser` mode. The `#social-drafts` message points at the card.
- `publish next [--json]` (copies the item's images into the run's scratch folder), `publish done --url`, `publish stopped`, `publish queue [--json]` and `publish resolve`, as in BP §5.7.
- `caps.py`: all six constants (`BROWSER_JOBS`, `COMMUNITY_POSTS_PER_DAY`, `COMMUNITY_JOINS_PER_WEEK`, `PUBLISH_ITEMS_PER_RUN`, `PUBLISH_MINUTES_BETWEEN_ACTIONS`, `PUBLISH_WINDOW`); config may only tighten them (`config/publish.yaml`). No existing value is raised.
- `publish_mode` in `config/social.yaml` becomes `draft` or `browser`; `auto` is removed, as one expand and contract inside this ticket (every platform is `draft` today).
- `after_run` for the publish plug-in settles an unclosed claim as `unknown`, pauses `publish` and alerts.
- `publish resolve` in `headless.NEVER`. `may_use` and `claude_rules` match `NEVER` entries as a leading run of command words, not only `split()[0]`; this ticket owns that change in `headless.py` and its test, and mission-control#01's generated test keeps passing.
- The digest gains the day's posted, skipped, expired and stopped counts. `docs/social.md` follows BP §3.3.
- `tests/gate_adapter_social_post.py` ("went out" means `publish next` handed the item out). Call mission-control#02's `assert_clean` over publish cards.

## Acceptance criteria

- [ ] **AC-P1.1** Given `publish_mode: browser` for Facebook only, when `social submit` passes on
  2026-11-10, then exactly one `social-post` request posts to `#approvals` with the A-nnnn id, the
  Jura Page and its URL, the day, the exact text, the image, any link in the text, the brand-gate
  result and "decide by Tue 10 Nov, 18:00 SGT". LinkedIn and Instagram get no request, and the
  `#social-drafts` message for Facebook points at the card instead of repeating it.
- [ ] **AC-P1.2** Given a variant that fails the brand gate, then no item and no request are created.
- [ ] **AC-P1.3** Given a published item's content (text, image bytes in order, destination, posting
  identity, day, answers), when any one field changes, then the item's `content()` no longer matches,
  its request is superseded and a new item and request are raised.
- [ ] **AC-P1.4** Given drafts written before a platform moved to `browser` mode, then they get no item.
- [ ] **AC-P2.1** Given the item's request is pending, skipped, expired or superseded, when `publish
  next` runs at 10:00, then it prints "nothing due" and nothing is claimed.
  *Here at the command. 03 proves it in a fake-`claude` run.*
- [ ] **AC-P2.2** Given an approved item, when `publish next` hands it out, then the approval is
  claimed (`used_at` set) and the item is `claimed` in one `BEGIN IMMEDIATE` transaction, before the
  run touches Chrome.
- [ ] **AC-P2.3** Given an approved, unclaimed item, when Ting Yu skips it, then the skip wins: the item
  is `withdrawn`, and for a social post `social skip <date> <platform>` is recorded. Given a claimed
  one, the answer is `already-used`.
- [ ] **AC-P3.1** Given an approved item for 2026-11-10, when `publish next` runs at 17:59:59, then it
  can claim it; at 18:00:00, or on 2026-11-11 at 09:00, nothing is claimed and the request is
  expired.
- [ ] **AC-P3.2** Given `approve` recorded by growth at 18:02 for that item, then the answer is
  `expired` and nothing changes, even if the Discord message was sent at 17:59.
- [ ] **AC-P3.3** Given a narrower window configured (10:00 to 16:00), then the deadlines move to 16:00,
  never later than 18:00.
- [ ] **AC-P5.1** Each line is one test at `publish next`:
  1. A second Facebook item for the same day is refused.
  2. A fourth group posted to in ISO week 46 (SGT, Monday to Sunday) is refused.
  3. A second community post on the same day is refused.
  4. A fourth join in the week is refused.
  5. A group posted to 13 days ago is refused; 14 days ago is allowed.
  6. An item claimed by a run that started at 10:00: a run starting 10:15 is refused, one starting
     10:20 is allowed.
  7. Claims at 08:59 and at 18:00 are refused.
  8. A community post on a day the confirmed rules close is refused.
  9. A community post in a group with `rules_confirmed = 1` but its days unconfirmed is refused
     ("open days not confirmed").
  10. A community post in a group not joined as the Jura Page is refused.
  11. A second `publish next` in the same run is refused.
  *Owned here for lines 1, 6, 7 and 11. Lines 2 to 5 and 8 to 10 are proved in 02b, against the community checks.*
- [ ] **AC-P5.2** Given a claim whose run crashed, then it still counts against the day's cap.
- [ ] **AC-P5.3** Given the PAUSE file, `pause publish`, `pause all`, auto-pause after three failures,
  `publish_mode: draft` or `community.browser: false`, each in turn, then nothing is claimed, the
  fake `claude` binary never starts, and the approval is not consumed.
  *Owned here for the social switches: nothing is claimed and the approval isn't consumed. 02b adds `community.browser: false`; 03 proves the fake `claude` binary never starts.*
- [ ] **AC-P5.4** Given a configured looser value for any limit, the window or the gap, then the hard
  value applies; a tighter one is honoured.
- [ ] **AC-P6.1** Given the Facebook login page appears after navigation, then the run calls `publish
  stopped <id> --reason login`. The item becomes `stopped`, `publish` is paused for every item, and
  `#alerts` gets the reason and a screenshot path. The next slot claims nothing until `resume
  publish`.
  *Here: `publish stopped <id> --reason login` marks the item, pauses `publish` and alerts. 03 proves the run noticing the login page.*
- [ ] **AC-P6.3** Given `resume publish` from a headless run, then it is refused; from `/growth resume
  publish` it works.
  *Here: refused from a headless run. 03 proves `/growth resume publish`.*
- [ ] **AC-P7.1** Given `publish done <id> --url https://www.facebook.com/<page>/posts/<n>` with matching
  live text, then the item, `social_posts.published_url` and `published_at`, and the approval's
  `used_by_run` are all set.
- [ ] **AC-P7.2** Given a URL on another host, or a look-alike (`facebook.com.evil.test`,
  `https://www.facebook.com@evil.test`, `javascript:`), then the command exits 1.
  *Here: the Facebook hosts and the look-alikes. 04 adds the Instagram and LinkedIn hosts.*
- [ ] **AC-P7.3** Given live text that differs from the approved text after Unicode NFC, collapsing
  whitespace and trimming, then the item is `done` with `live_text_matches = 0`, an alert posts, and
  `publish` is paused.
- [ ] **AC-P8.3** Then the digest gains the day's posted, skipped, expired and stopped counts.
- [ ] **AC-P10.1** Given a claim with neither `done` nor `stopped` when the run ends, then `after_run`
  marks the item `unknown`; it is never claimed again, `publish` is paused, and `#alerts` names
  `/growth publish resolve A-nnnn posted --url <url>` and `… not-posted`.
  *Here: `after_run` settles the claim, pauses and alerts. 03 checks the alert's text through a fake-`claude` run.*
- [ ] **AC-P10.2** Given `publish resolve` from a headless run, then it is refused; from Discord it
  settles the item.
  *Here: refused from a headless run, and settled from Terminal. 03 proves it from Discord.*
- [ ] AC-M4.1 to AC-M4.7 (owned by mission-control#04) hold for `social-post` through its adapter file, with the publish double asserting at call time that the record is already used.
- [ ] **X6.** A Saturday social draft on a `browser` platform raises a request (`weekends: true` kept).
- [ ] **X7 and X8 (copy).** The `publish_items` migration changes no existing row; `publish next` copies the item's images into the run's scratch folder.
- [ ] The sweep in `tests/sweep.py` passes over this ticket's messages (the `social-post` cards and the `#social-drafts` pointer): no planted secret or personal data reaches the Discord double or the outbox (AC-M11.1 and AC-M12.1, owned by mission-control#02).
- [ ] Two `publish next` calls racing for one item give one claim.
- [ ] AC-M15.1 (owned by mission-control#01) still holds.

## Done when

Every criterion above passes, `git diff main -- jura_growth/caps.py` raises no existing value, `uv run pytest` passes, and the report is in. Ting Yu can then run the social part of `uat.md` Part C. Then wait for go-ahead.

## Pointers

- PRD: BP §2, §4.2 to §4.6, §5.4 to §5.7, §5.10, §3.3 (social rows); MC §4.6 and §5.7
- `.scratch/mission-control/reviews/tickets-technical.md`: T7, T8, N7, Q5
- `.scratch/mission-control/reviews/technical-v2.md`: B1, B4, N3; blast radius
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.2 (AC-P rows by id), §4.3 (X6, X7, X8), §5, §3 (D11 social), §11.2 row BP-02
- `.scratch/mission-control/uat.md` Part C
- `CONTEXT.md` (Publish item, Posting identity, Posting window, Stop signal, Claim)
- Code: `jura_growth/caps.py`, `headless.py`, `agents/social/settings.py`, `submit.py`, `digest.py`, `config/social.yaml`
