# Functional review: mission control and browser publishing

*Functional lead, 2026-10-25. This replaces the earlier review of the local-page draft, which the
scope change of 2026-10-25 17:03 made obsolete.*

*Specs reviewed together, because they share one approval mechanism:*

- *`jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md`, cited as `MC:<line>`*
- *`jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md`, cited as `BP:<line>`*

*Decisions checked against `.scratch/mission-control/crew-log.md` (scope change 17:03, approvals
correction 17:05, email approval correction 17:06), `.scratch/browser-publishing/crew-log.md`,
`.scratch/browser-publishing/spike-headless-chrome.md`, `CONTEXT.md`, `README.md`, `docs/*.md`,
`config/*.yaml` and `jura_growth/caps.py` on `crew/growth-blocker-fixes-07-community-negated-days`.
The live `growth.db` and `.env` were not opened. Glossary proposals are in section 6; `CONTEXT.md`
was not edited.*

**Verdict.** Both PRDs cover everything Ting Yu asked for: the one-pager, run updates from scout,
social, community and app-factory, approval in Discord for every email, social post, community
post, group join and app build, a preview before production, and control from Discord through
Dispatch. They are not ready for G2. There are **5 blocking findings**. Two are rules that strand
real work: approved emails expire behind the send caps, and community posts can never become
claimable. Two are app-factory handoffs nobody owns. One is that the two PRDs disagree on the
approval contract they share. There are also 17 should-fix findings and 11 notes.

---

## 1. The process, end to end

### 1.1 A business day as Ting Yu will live it

Assumes both PRDs are built, outreach is live, Dispatch is deployed with buttons (D1 to D5), and all
three social platforms are in `browser` mode.

| SGT | What happens | Who acts | What Ting Yu sees in Discord |
|---|---|---|---|
| 06:30 | app-factory files one app PRD and raises an `app-build` request (MC:536-538) | engine | `#app-factory` run update, `#approvals` card with the PRD attached |
| 07:00 | social drafts three posts. `social submit` creates three publish items and three `social-post` requests (BP:234) | engine | `#social-drafts` drafts and a run update, then three `#approvals` cards |
| 07:30 Mon | community writes the week's plan: up to 3 `community-post` requests, up to 3 `group-join` requests (BP:235-238) | engine | `#community` plan and run update, then up to six cards |
| 08:00 | one-pager (MC:55-58) | engine | `#mission-control` |
| 08:00-09:00 | Ting Yu taps Approve or Skip on the morning cards | Ting Yu, through Dispatch | Dispatch's reply under each card |
| 09:00 | scout-research adds up to 15 leads and queues 15 first emails, plus follow-ups due. Each raises an `outreach-email` request (MC:489) | engine | `#scout-leads` and a run update, then 15 or more cards |
| 09:00-18:00 | `publish` runs every 15 minutes and claims at most one approved item, 20 minutes apart (BP:146-148) | engine | a run update per claimed item, in `#social-drafts` or `#community` |
| 09:30-16:30 | scout-send sends approved emails inside the caps and warm-up (MC:517-522) | engine | `#outreach-sent` per email |
| 12:00 | heartbeat runs `expire_due()` (MC:509) | engine | expired cards (how they show is S8) |
| 16:30 | email requests from the previous business day expire and their emails are cancelled (MC:489) | engine | nothing, unless S8 is fixed |
| 16:45 | scout-sync. Replies, bounces and unsubscribes cancel queued emails and supersede their requests (MC:526-527) | engine | `#outreach-replies` |
| 17:30 | digest | engine | `#daily-digest` |
| 18:00 | social and community requests for today expire (BP:39-40). Nothing applies the expiry until the next read or decide | engine | stale cards until then (S2, S8) |
| any time | Dispatch builds an approved app, then calls `apps built`, which raises `app-release` (MC:543-544) | Dispatch | `#approvals` card with the preview link |
| any time | Production promotion after an approved release. Not in Dispatch v1 (MC:290), so Ting Yu merges by hand (MC:697-698) | Ting Yu | nothing; he then runs `apps released` |

### 1.2 Handoffs nobody owns

1. **An approved app build before D6 ships, or approved from Terminal.** No one builds it (B4).
2. **Promotion to production.** It is a hand merge with no check against the approval (B3).
3. **Rules seen inside a group** (`publish note-rules`, BP:318) don't raise the `group-rules` request
   that is supposed to confirm them (MC:492), and nothing confirms open days (B5).
4. **An `unknown` publish item** asks Ting Yu to run `publish resolve` in Terminal (BP:323-325),
   which breaks "all communication through Discord" (S6).
5. **Expired and superseded cards** stay in `#approvals` looking answerable (S8).

### 1.3 Exceptions walked

| Exception | Covered? | Where |
|---|---|---|
| Ting Yu misses an email card | yes: cancelled at 16:30 on the next business day | MC:489 |
| Ting Yu approves 15 emails in warm-up week 1 (cap 5 a day) | **no**: 10 approved emails expire unsent and are cancelled for good | B1 |
| Ting Yu approves, then changes his mind | **conflict**: MC allows decisions only on pending requests, BP says a skip wins until claimed | B2, S5 |
| A double tap, or Dispatch retries | **conflict**: BP dedupes on `source_ref`, MC has no `source_ref` | B2 |
| A lead replies or unsubscribes while its email waits for approval | yes: superseded | MC:526-527 |
| A social draft is posted or skipped by hand while its card is pending | **no**: the card stays live; the claim is refused only at `publish next` | S4 |
| The Mac is asleep when Ting Yu taps Approve | **conflict**: MC says Dispatch replies "unreachable" (MC:286), BP says Dispatch retries until it gets an answer (BP:285-286) | B2 |
| Someone else in Jura HQ taps Approve | yes: refused unless the user id matches | MC:246-248, BP:274 |
| A content change after approval | yes: the hash no longer matches, a new request is raised | MC:232-235, BP:126-127 |
| An app idea is never answered | expires after 7 days and counts as a skip, so it is gone forever | S9 |
| A crash after the browser clicks Post | yes: `unknown`, never retried, agent paused | BP:323-325 |
| A login wall, CAPTCHA or warning | yes: stop, pause, alert | BP:167-176 |
| Data from before the change | partly: pending factory PRDs and already-confirmed groups are stranded | S10 |

---

## 2. Every outward action: one approval path, no bypass?

| Outward action | Approval kind | The one code path that acts | Bypass or gap |
|---|---|---|---|
| Outreach email (first, follow-up, requeued shadow) | `outreach-email` | `outreach send-due` (MC:517-522) | No bypass: `send-due` is the only Resend caller, from launchd or Terminal. But `use` runs after Resend accepts (S1), and approved emails expire behind the caps (B1). |
| Social post | `social-post` | `publish next` then `publish done` (BP:315-316) | No code bypass. Posting by hand stays allowed (BP:96), which is fine, but it doesn't supersede the pending card (S4). |
| Community group post | `community-post`, plus confirmed rules and days | `publish next` (BP:161-163) | No code bypass. As written, nothing can ever be claimed, because nothing confirms days (B5). Reply ideas stay manual and have no gate (N2). |
| Group join, and its membership answers | `group-join` (twice when there are questions) | `publish next` (BP:245-252) | Not a bypass, but the second approval's kind, hash and expiry are undefined (S16). |
| App build and push to preview | `app-build` | Growth writes a handoff row; Dispatch builds (MC:539-542) | The gate binds only growth's handoff row. Dispatch, or Claude Code in `landing-page`, can build any PRD without it. Until D6 there is no builder at all (B4). The preview URL is public (S11). |
| App release to jurasolutions.sg | `app-release` | Dispatch promotes (D7, not built). Meanwhile Ting Yu merges by hand (MC:697-698) | **Bypass**: a hand merge of `dev` into `main` ships every app built on `dev`, approved for release or not, and nothing checks it (B3). |
| Confirming a group's rules (internal, but it unlocks links) | `group-rules` | `community` code (MC:492) | `community set ... rules_confirmed=yes` from Terminal still works. That's fine as a human path, but two rule sources feed one flag (B5). |

There is exactly one decision record per action (MC:226-238). There are two ways to decide, Discord
and Terminal (MC:680-682), and BP:130-132 forbids the Terminal one. Section 3 B2 covers that.

---

## 3. Approval load for one person

Counted at today's caps and config. `daily_target` is 15 (`config/scout.yaml`), the code ceiling
is 30. Follow-ups run only with IMAP set, at most one per company, 5 business days after the first
email.

| Kind | Raised | Tue to Fri | Monday | Sat, Sun |
|---|---|---|---|---|
| `outreach-email` | 09:00, at queue time | 15 first emails, plus up to 15 follow-ups once they start: **15 to 30** | 15 to 30 | 0 |
| `social-post` | about 07:05 | 3 (1 during BP block 2) | 3 | 3 (`weekends: true`) |
| `community-post` | Monday 07:30 | 0 | up to 3 | 0 |
| `group-join` and answers | Monday, then after a run sees questions | 0 to 1 | up to 3 | 0 to 1 |
| `group-rules` | when rules are recorded | 0 to 1 | up to 3 | 0 |
| `app-build` | 06:30 | 1 | 1 | 1 |
| `app-release` | when a build lands | 0 to 1 | 0 to 1 | 0 to 1 |
| **Total** | | **19 to 37** | **25 to 44** | **4 to 6** |

Roughly 120 to 200 decisions a week. Most of them are emails, each up to 120 words to read before
tapping. With buttons (D5) that's 10 to 15 minutes a day across two bursts (07:00 and 09:00). With
typed `/growth approve A-nnnn` on a phone it is two to three times that. From Terminal it breaks
the Discord-only rule.

The load itself is workable with buttons. The mismatch is not (B1). During warm-up the engine sends
5 a day in week 1 and 10 a day in week 2 (`caps.OUTREACH_WARMUP`), while research raises 15 requests
a day. The queue hits `max_queue: 40` in about four days, so Ting Yu keeps approving emails that can't
go out before their approval lapses. A `requeue-shadow` run after the trial raises every requeued
email's request in one burst, 30 to 60 at once (MC:529-530).

---

## 4. Blocking

### B1. Approved emails expire behind the send caps and are cancelled for good
*MC:489 (expiry: 16:30 on the next business day), MC:236-238 (`use` refuses an expired record),
MC:239-241, MC:76-80, MC:517-522; `caps.OUTREACH_WARMUP`, `config/scout.yaml` `daily_target: 15`.*

The expiry is a decide-by time, but §4.6 also applies it at `use`. An email Ting Yu approved at 08:30
on Tuesday, sitting behind a 5-a-day warm-up cap, is cancelled ("approval expired") at 16:30 on
Wednesday, even though he said yes. The skip action closes the lead (MC:489), but the expiry action
says nothing about the lead. Because `add-lead` dedupes by domain, the company can never be queued
again, so the lead is lost for good with no way to re-approve it. Story 15 ("silence never counts as
a yes") is about unanswered requests, not answered ones.

**Recommended fix (needs Ting Yu's yes, because it shapes his daily load):**

1. Split the two times. **Decide by** stays 16:30 on the next business day. **Use by**, for an
   approved email, is 16:30 on the 10th business day after approval. After that it is cancelled
   with "approved but not sent in time" and the lead goes back to `new`, not closed.
2. Throttle requests to capacity. `queue()` raises a request only while pending plus
   approved-but-unsent emails are fewer than the next two business days' send capacity (warm-up
   aware). Other queued emails wait with status "waiting for a request slot", and `send-due` raises
   their requests as room opens (MC:489 already lets `send-due` raise them). `requeue-shadow` follows
   the same throttle.
3. `send-due` sends approved emails in order of use-by time, oldest first.

Add to MC §5.7: "warm-up day 3, cap 5, 15 approved: 5 send today, 10 stay approved, none is
cancelled".

### B2. The two PRDs disagree on the approval contract they share
*MC:226-254, MC:495-510, MC:286, MC:246-248; BP:8, BP:128-132, BP:240-241, BP:256-292, BP:304-305,
BP:367, BP:422-425.*

| Point | Mission control | Browser publishing | Recommended single rule |
|---|---|---|---|
| The id Ting Yu types | `A-nnnn` (MC:226, MC:461) | `P-0042`, and replies such as "approved P-0042" (BP:240-241, BP:287) | Ting Yu only ever sees and types `A-nnnn`. `P-nnnn` is the internal subject (`publish_item:42`), shown on the card as a secondary reference. |
| Changing your mind | `decide` needs a pending request (MC:504) | A skip after an approval wins until the item is claimed (BP:276) | Allow approved to skipped until `used_at` is set, for every kind (S5). The trigger still refuses a return to pending. |
| Duplicate decisions | no `source_ref` | Same `source_ref` recorded once (BP:275) | Add an optional `--ref <discord message id>` to `approve` and `skip`. The same decision repeated is answered "already approved" with exit 0. |
| Who may decide | Discord id, or Terminal (MC:246-248, Q8) | Discord id only (BP:130-132, BP:266) | MC's rule, for every kind. Strike "only decisions from Ting Yu's Discord user id count" from BP:131-132. |
| Where the approver id lives | `CONTROL_DISCORD_USER_ID` in `.env` (MC:248) | `config/publish.yaml` (BP:367) | One place: `.env`, as MC says. Remove it from BP:367. |
| When the Mac can't be reached | Dispatch replies "the growth Mac is unreachable" (MC:286) | Dispatch retries until it gets an answer (BP:285-286) | MC's rule. A silent retry can land a decision hours later. The card stays pending and the one-pager lists it. |
| How Dispatch reaches the Mac | SSH forced command (MC:705-708) | Approval handler on the Mac (BP:422-425) | Decide once, in MC Q14. BP Q3 points at it. |
| Decision table | core `approvals` | "if it defines none, add `publish_decisions`" (BP:304-305) | Delete the fallback. MC defines it. |
| "If Dispatch is down, nothing posts" (BP:292) | Terminal fallback | | Terminal decisions work for publishing too. |

BP's header still says the mission-control PRD is "being rewritten for Discord" (BP:8). Amend BP
§4.2 and §5.3 to point at MC §4.6 and §5.4, keeping only what is specific to publishing: the kinds,
the previews, the hash fields, expiry, and the approve, skip and expiry actions (S4).

### B3. A release can't be approved per app on a shared `dev` branch, and the hand merge bypasses it
*MC:290, MC:491, MC:543-547, MC:694-698, story 21 (MC:376-377).*

Dispatch ships every task to the repo's `dev` branch. If APP-014 and APP-015 are both built, and only
APP-014's release is approved, merging `dev` into `main` ships both. The `app-release` hash covers
the task id and preview URL (MC:491), not the code, so commits pushed to the task after approval
still match. Until D7 the merge is by hand, and nothing checks it against an approval.

**Recommended fix:** each app builds on its own task branch (`claude/T-nnnn-slug`), which Cloudflare
Pages previews separately. A release approval covers that branch's head commit SHA. Promotion merges
only that branch into `main`. Until D7: `jura-growth apps release-plan <APP-NNN>` prints the exact
merge command for the approved SHA, and `apps released` refuses unless `main` contains that SHA and
the approval is approved and unused. Add an out-of-scope line: "Until Dispatch promotes (D7), the
production merge is a manual step outside the gate; `apps released` records it and checks the SHA."

### B4. Approved app builds have no builder until D6, or when approved from Terminal
*MC:539-542, MC:289, MC:680-682, MC:305-307 (the old "approved, build" path is superseded),
`docs/app-factory.md` "Building an app PRD".*

Block 5 ships before Dispatch is deployed (MC:278-280). From then on the factory stops posting the
"approved, build …" line, but the only consumer of the handoff is the `--json` answer Dispatch gets
when it relays the approve. A Terminal approval (Q8) produces a handoff row nobody reads. Ting Yu
asked that approving start the build (story 20). In the interim nothing starts it, and the waiting
pile fills to 7 and stops the factory.

**Recommended fix:** add `jura-growth apps handoffs [--json]`, which lists handed-off builds not yet
built, and put it on the remote allowlist. Dispatch polls it, rather than relying on the reply to
the approve. Until D6, the `app-build` approval reply and the one-pager say "Build it: open Claude Code
in `jurasolutions/` and say: build the approved PRD `<path>` (approval A-nnnn)". That keeps the old
manual path, now gated by the approval.

### B5. Community posts can never become claimable: two rule sources, and nothing confirms days
*BP:161-163 ("a group whose rules name days and whose days are not confirmed has no open day"),
BP:250-252, BP:318; MC:367-368, MC:492; `agents/community/groups.py` `SETTABLE` (there is a
`rules_confirmed` flag, no days flag).*

BP requires confirmed open days. No field, command or approval sets them: `group-rules` approve sets
only `rules_confirmed` (MC:492). MC raises `group-rules` "when the community run records rules", but
the community run never sees Facebook, so those rules are web-search hearsay. The real rules come
from `publish note-rules` inside the group (BP:318), and that command raises nothing. Story 18 asks
for links only in groups "whose rules I've checked". Approving hearsay is not checking.

**Recommended fix:** `group-rules` is raised by `publish note-rules` and by
`community set <id> rules="..."`, never by researched `promo_rules`. Its hash covers the rules text
and the parsed `promo_days` and `post_days`. Its preview shows both. Approve sets `rules_confirmed`
and a new `days_confirmed`. Add the AC: "an approved `community-post` for a group with
`rules_confirmed = 1, days_confirmed = 0` is refused by `publish next` with 'open days not
confirmed'".

---

## 5. Should fix

**S1. `use` runs after Resend accepts.** *MC:521-522.* If the record expired, or was skipped, in the
seconds between the filter and the send, the email is already out and `use` refuses. Re-check
`approved, unexpired, unused, hash matches` immediately before the Resend call, under the send lock.
Mark it used in the transaction that records the send. If that write still fails, record the email
`sent`, alert `#alerts`, and never resend.

**S2. The one-pager can't apply expiry, because its read model never writes.** *MC:94-95, MC:162,
MC:428, MC:509 ("expire_due runs on every read").* The 08:00 one-pager would list yesterday's
18:00-expired social cards as waiting. The read model must classify by `expires_at` against
`now_sgt()`, not by the stored status. The heartbeat and every decide still write the transition.
Also run `expire_due()` in the `publish` precheck at the first slot after 18:00 (or in the 23:30
backup job), so expiry actions don't wait for noon the next day.

**S3. The `publish` job doesn't fit mission control's run and slot rules.** *BP:329-331, BP:356-360,
BP:339-349 (every run starts Claude to call `publish next`); MC:81-84 ("every run ... posts exactly
one run update"), MC:433, MC:717-718.*
- Starting `claude -p` 37 times a day to learn that nothing is due costs about US$0.08 a time
  (spike probe 3), so about US$3 a day for nothing. Use the plug-in `precheck(job, conn)` hook
  (`README.md`) to skip before Claude starts when no item is claimable.
- Run updates: post only when an item is claimed, in the item's channel. Add the exception to MC
  SC3 and register `publish` with a `run_update` of "claimed only".
- One-pager: collapse `publish` into one row per day with counts, like scout-send (MC Q17).
- Add `publish` to the `CONTEXT.md` Agent list.

**S4. BP doesn't define its kinds' actions, and hand actions don't supersede cards.** *MC:493
("defined there"); BP:96, BP:157-160.* Write BP's row of MC §5.3. Approve: item `approved`. Skip:
item `skipped`, and for social also `social skip <date> <platform>`. Expiry: item `expired`, draft
unchanged. Superseded when `social published`, `social skip`, `community posted`, `community
removed` or a content change touches the item before a decision.

**S5. Revoking an approval.** *MC:503-506.* A wrong tap on a 120-word email needs an undo. Allow
`skip A-nnnn` on an approved, unused request, for every kind (B2). Once used, the answer is "already
sent at 10:40; can't be undone".

**S6. The remote allowlist misses what the alerts ask Ting Yu to do.** *MC:469-481, BP:319-325,
BP:177.* Add `publish queue`, `publish resolve <id> posted --url <url> | not-posted`,
`apps handoffs` (B4), `community removed <group-id>` and `social skip <date> <platform>`. None takes
a file path. Without them, an `unknown` item or a group warning sends him to Terminal.

**S7. "Exactly what goes out" conflicts with the personal-data rule.** *MC:71-73, MC:154-156,
MC:200-205, MC:464.* A named enquiry address shows masked (`j***@…`), and a draft body that opens
"Hi Jane" would be masked by `privacy.for_discord`, so the preview is no longer the email. Ting Yu
approves a recipient he can't fully see. **Recommended (ask Ting Yu):** keep the masking, show the
source page link so he can check it, and make the `email` brand channel refuse a personal name in
the body (the address line already names the company), so the body preview is exact.

**S8. Cards that are expired, superseded or decided must say so in place.** *MC:501, MC:527, BP:225.*
Webhook posts can be edited when posted with `?wait=true` and the message id stored. Edit the card's
first line ("Approved by Ting Yu, 10:02 SGT", "Expired", "Superseded: lead unsubscribed") and remove
Dispatch's buttons. Edits don't notify, which matters for a channel set to notify on every message
(MC:729-731). Store `discord_message_id` on the approval record.

**S9. An app idea that simply expires is lost forever.** *MC:490, MC:548-549, story 22.* Skip should
close an idea. Missing it during a busy week shouldn't. On expiry, move the PRD to
`prd/skipped/apps/` with "Expired unanswered on <date>", and put the backlog idea back to open so it
can be proposed again after 30 days.

**S10. Data from before the change.** *MC:489, MC:550-551; BP:161-163.*
- App PRDs already in `prd/pending/apps/` when block 5 ships have no request, count toward the
  waiting pile of 7, and can't be approved. Block 5 raises an `app-build` request for each factory
  PRD still pending (one-off, idempotent).
- Groups already set `rules_confirmed=yes` from Terminal have no days confirmation (B5). Treat a
  Terminal confirmation made before the migration as confirming its parsed days, or raise one
  `group-rules` request per such group.
- Live queued emails at block 4 are covered (MC:489). Social drafts from before a platform moves to
  `browser` get no item. Say so.

**S11. A preview is public before release.** *MC:545, MC:694-696.* Cloudflare Pages preview URLs are
reachable by anyone who has them. An unreleased app carrying the Jura name is effectively published.
Either protect previews with Cloudflare Access (Ting Yu's login) or record that risk as accepted.

**S12. The decision time that counts for expiry.** *BP:267 (Discord message time).* Use the time
growth records the decision. A tap at 17:59 that reaches the Mac at 18:02 is expired. That fails
closed and can be tested.

**S13. The approvals listing has a 1,900-character cap.** *MC:259-261, MC:477.* 30 pending emails
won't fit. List the oldest 15 by expiry, then "and 15 more: /growth approvals outreach-email".

**S14. BP §5.6 predates the spike.** *BP:333-342, BP:414-418; spike §1, §4.* Replace "an
`--mcp-config` file" with `--chrome`, added only for `browser: true` jobs. Scope sites with
`ClaudeInChromeDomain(<host>)` rules. Name-deny the tools the spike found that §5.6 doesn't list
(`browser_batch`, `list_connected_browsers`, `resize_window`, `shortcuts_list`). Make OAuth-only auth
a `status` setup gap: with `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` set, the browser tools
silently disappear. Make the chosen Chrome profile a setup step. Record Q1's answer as "feasible with
conditions", with the three checks still open: locked screen, Chrome closed, unlisted domain denied.

**S15. Ship a UAT harness.** The UAT script needs a seed command that builds a temp data folder with
the scenarios in `uat.md`. It also needs a way to run `send-due` in live mode against a stub Resend
endpoint, for example `JURA_GROWTH_RESEND_BASE_URL` pointing at a local recorder that refuses unless
`JURA_GROWTH_DATA_DIR` is a temp folder. Without these, the email gate can only be accepted on the
first live day.

**S16. Join requests have no "day", so their expiry is undefined.** *BP:39-40, BP:128-129,
BP:236-238, BP:245-252.* A join proposed on Monday would expire at 18:00 Monday under the "item's
day" rule. **Recommended:** a `group-join` request expires at 18:00 on the Sunday of the week it was
proposed. The membership-answers request is the same kind, with a new hash over the questions and
answers. Raising it doesn't supersede the used step-one approval. It expires 3 days after it is
raised.

**S17. Live outreach should wait for buttons.** *MC:278-280, MC:678-679, §3 above.* At 15 to 30
emails a business day, typed commands are not a realistic daily routine. Recommend (ask Ting Yu):
`outreach.mode: live` stays refused until D5 is confirmed, not only until block 4 ships. `outreach
status` reports "approval buttons not set up" as a live problem.

---

## 6. Notes

- **N1.** BP:8 is stale ("being rewritten for Discord").
- **N2.** Community reply ideas stay manual and ungated. Add an out-of-scope line to BP §3.2.
- **N3.** For a `browser` platform, `#social-drafts` and `#approvals` carry the same text and images.
  Shorten the `#social-drafts` message to a pointer to the card ("Waiting for you: A-0153").
- **N4.** MC:250-251 says requests are "never [raised] by a CLI the model calls", but the model calls
  `outreach queue` and `community propose-join`, which raise them. Reword it to "never by a generic
  request command; only as a side effect of a gated command's own checks".
- **N5.** Approving an app PRD in Discord is its PRD sign-off (MC:305-307). Write the approval id and
  date into the handoff row, not into the PRD file, or the PRD hash changes under the approval.
  Write the sign-off line when the PRD moves to `prd/done/apps/`.
- **N6.** `#approvals` set to notify on every message means 20 to 45 phone notifications a day.
  That's acceptable with S8's edits in place. Ting Yu may prefer a summary mention at 08:00 and 09:15.
- **N7.** `weekends: true` means three social approvals every Saturday and Sunday. Ting Yu can keep
  weekends in `draft` mode if he doesn't want them.
- **N8.** BP SC8 says "status update" (BP:51). Use **run update**, and MC's header format (BP:360).
- **N9.** BP Q10, which identity posts in groups, puts Ting Yu's personal Facebook account at risk
  (BP:117-120). It needs his explicit answer, not a default.
- **N10.** Ting Yu said "scout" for run updates. MC reads that as scout-research only, which is
  right: scout-send belongs to the outreach agent and `#outreach-sent` already reports each send.
- **N11.** Approving from Terminal (MC Q8) is a fallback, not a second home. The one-pager should
  show a line when a decision came from Terminal, so the Discord record stays complete.

---

## 7. Language

Proposed for `CONTEXT.md`. Not written, because this review is read-only.

| Term | Proposed meaning | Avoid |
|---|---|---|
| **Approval request** | As now (`A-nnnn`). The only id Ting Yu types. | "approval" for the record, `P-nnnn` in replies |
| **Decision** | Ting Yu's approve or skip on one approval request, with actor and time | "approval" for the act |
| **Decide-by** and **use-by** | When a pending request expires, and when an approved one lapses unused (B1) | "expiry" alone, for emails |
| **Publish item** | One browser action (a social post, a community post, a group join) with frozen content. It is the subject of one approval request | "item" alone (community plan items and checklist items are different) |
| **Posting window** | 09:00 to 18:00 SGT, when the publish job may act (`PUBLISH_WINDOW`) | "publish window" alongside "send window" |
| **Stop signal** | As BP §4.5 | "error" |
| **Skip** | Keep the word for the decision only. Use "skipped run" for the slot status, "dropped" for the brand gate, and keep the community fit `skip` as "fit: skip" | bare "skip" in mixed contexts |
| **Channel** | "Discord channel" and "brand channel" are different things. Always qualify | bare "channel" |
| **Agent** | Add `publish` | |

---

## 8. Recommended answers to mission control §6

| # | Question | Recommended answer |
|---|---|---|
| 1 | One-pager time; does the digest stay? | **Agree**: 08:00 daily, the 17:30 digest unchanged. |
| 2 | Text and image, or embeds? | **Agree**: text plus one PNG. |
| 3 | Which channels? | **Agree**: `#mission-control`, `#approvals`, plus `#control` from Q15. Publish run updates go in the item's channel (S3). |
| 4 | Personal data in Discord | **Agree, amended** (S7): masked named addresses with their source page, and no personal names in email bodies, so the preview stays exact. Ting Yu confirms. |
| 5 | Run updates for scout-send and scout-sync | **Agree**: none (N10). |
| 6 | Run updates for skipped runs | **Agree** for the four agents. `publish` posts only when it claims an item (S3). |
| 7 | Buttons or typed commands | **Agree**, and make buttons a condition of live outreach (S17). |
| 8 | Approve from Terminal | **Agree**, for every kind including browser publishing (B2), with B4's handoff listing so Terminal-approved builds aren't stranded. |
| 9 | Expiry per kind | **Amend**: emails decide-by 16:30 on the next business day, use-by 10 business days after approval (B1). App build 7 days, then "expired", not "skipped" (S9). App release 7 days. Group rules 14 days. |
| 10 | Batch approval of emails | **Agree, no batch in v1**, with B1's throttle so the number of open requests never runs ahead of what can send. Revisit after two weeks live. |
| 11 | Shadow mode and approvals | **Agree.** |
| 12 | Where is an approved app pushed? | **Amend** (B3): a per-app task branch with its own Pages preview, and release by merging that branch's approved SHA. Until D7, Ting Yu merges by hand and `apps released` checks the SHA. |
| 13 | Skipped app PRD | **Agree**: `prd/skipped/apps/` with a top line. Expired ones go there too, marked "Expired unanswered" (S9). |
| 14 | How Dispatch reaches the Mac | **Agree**: SSH forced command. Dispatch must reply "unreachable" rather than retry (B2). BP Q3 takes the same answer. |
| 15 | Where the control channel lives | **Agree**: Jura HQ, `#approvals` and `#control` bound to `jura`. |
| 16 | Slot status "due" | **Agree.** |
| 17 | scout-send day cell | **Agree.** Apply the same to `publish` (S3). |
| 18 | An unloaded job with history | **Agree.** |
| 19 | PAUSE file from Discord | **Agree**: no. |
| 20 | Wait for blocker fixes on `main` | **Agree.** |
| 21 | Phone notifications | **Agree**, with in-place card edits (S8, N6). |

## 9. Recommended answers to browser publishing §6

| # | Question | Recommended answer |
|---|---|---|
| 1 | Can a scheduled `claude -p` drive Claude in Chrome? | **Answered by the spike: feasible with conditions.** These are `--chrome` for this job only, claude.ai OAuth (never an API key or setup-token), Chrome running with the extension signed in to the same organisation, one chosen profile, the Mac logged in and awake, and `ClaudeInChromeDomain` scoping. Before block 1, Ting Yu runs the three open checks: locked screen, Chrome closed, unlisted domain denied. Fold these into §5.6 (S14). |
| 2 | Who owns the approvals table and the decision command? | **Agree**: mission control. Delete the `publish_decisions` fallback (B2). |
| 3 | Where Dispatch runs and how it reaches the Mac | **Defer to MC Q14** (SSH forced command, fail fast when unreachable). Remove the separate recommendation (B2). |
| 4 | When an approval expires | **Agree** for posts: 18:00 SGT on the item's day, judged at growth's record time (S12). Joins: the Sunday of the week proposed. Membership answers: 3 days (S16). |
| 5 | First platform in block 2 | **Agree**: Facebook Page, then Instagram, then LinkedIn. |
| 6 | Group joins a week | **Agree**: 3. |
| 7 | Other platforms | **Agree**: none in this build. |
| 8 | Edit from Discord? | **Agree**: approve or skip only. |
| 9 | Batch approval | **Agree**: no. |
| 10 | Which identity posts and joins in groups | **Needs Ting Yu's explicit answer** (N9). The default recommendation, Ting Yu personally, carries the account risk in §4.1 onto his personal profile. |
| 11 | Does a membership seen in Chrome set `joined=yes`? | **Agree**, from `join_status = member`. Rules and days still need a `group-rules` decision (B5). |
| 12 | Posting window and gap | **Agree**: 09:00 to 18:00, 20 minutes, one item per run. Skip runs in code when nothing is claimable (S3). |
| 13 | Glossary | **Agree**, using the terms in section 7. |

---

## 10. Acceptance criteria as Given / When / Then

Defaults: a seeded temp data folder; the clock frozen with `JURA_GROWTH_NOW`; the Discord test double
(or `JURA_GROWTH_DISCORD=off` and the outbox); `CONTROL_DISCORD_USER_ID=111` in the UAT env file.
Reference dates: Fri 2026-11-06 and Tue 2026-11-10 are business days. Sun 2026-11-08 is Deepavali and
Mon 2026-11-09 is its observed holiday.

### Mission control

**AC-M1. One-pager** (SC1, stories 1 to 4, 7)
1. Given 2026-11-10 08:00 and webhooks configured, when the `one-pager` job runs, then
   `#mission-control` receives one message, split only past 2,000 characters. Its sections run in
   this order: a header reading "Tue 10 Nov, as of 08:00 SGT", Needs you, Approvals waiting, Today,
   Yesterday, Ask me. One PNG rides on the last piece.
2. Given nothing in the health strip, then "Needs you" reads "Nothing needs you".
3. Given 4 pending `outreach-email` requests (the oldest is A-0101, decide-by 2026-11-10 16:30) and
   1 `social-post` request, then "Approvals waiting" shows "outreach-email 4, social-post 1", names
   A-0101 as the oldest, and lists all five as expiring before the next one-pager.
4. Given a `social-post` request whose 18:00 expiry passed yesterday and no write since, then it is
   not counted as waiting (S2).
5. When Ting Yu sends `/growth one-pager`, then the same message posts and Dispatch replies "posted to
   #mission-control" within 60 seconds.

**AC-M2. Slot statuses** (SC2, stories 5 and 6). Table tests with the clock frozen at 2026-11-10
11:05.

| Job, slot | Records | Expected |
|---|---|---|
| scout-send 10:00 | `run.quiet` at 10:00:03 | ok |
| scout-send 10:00, 10:10, 10:20 | Mac asleep; one quiet run at 10:26 | missed, missed, ok |
| app-factory 06:30 | ok run started 08:42 | ok |
| scout-research 09:00 | none | due |
| scout-research 2026-11-09 09:00 | skip "not a business day (Deepavali)" | no slot |
| backup 2026-10-30 23:30 | first backup record is 2026-11-02 | not installed |
| publish 09:00 to 11:00 | precheck skips "nothing claimable" | ok, collapsed with counts (S3) |

**AC-M3. Run updates** (SC3, stories 8 to 10)
1. Given a social run that is ok at 07:00, lasts 4 min 12 s, costs US$0.41 and raises A-0153 to
   A-0155, then `#social-drafts` gets exactly one message. Its first line is
   `**social** · ok · 07:00 SGT · 4m 12s · US$0.41 · run <id>`, then a quoted summary of at most 300
   characters, a "Produced:" line, and "Waiting for you: A-0153, A-0154, A-0155 (social posts)".
2. Given social paused by hand, when the 07:00 slot fires, then one message reads "skipped: paused by
   hand".
3. Given community fails with a timeout, then one run update gives the redacted error in one line,
   and `#alerts` gets its usual post.
4. Given the `#social-drafts` webhook returns 500, then the run's status and the auto-pause counter
   are the same as with Discord up, and the outbox gains the message.
5. Given a scout-send run that sends one email, then no run update posts.

**AC-M4. The gate, per kind** (SC4, stories 11 and 14). For each of `outreach-email`, `app-build`,
`app-release`, `group-rules`, `social-post`, `community-post` and `group-join`:
1. Given the request is pending, skipped, expired, superseded or already used, when the gated action
   runs, then it refuses and nothing outward happens (no Resend call, no handoff row, no flag change,
   no claim).
2. Given A-0412 is approved over hash H1, and the draft body changes so the hash is H2, then the
   action refuses, A-0412 becomes superseded, and A-0413 is raised over H2.
3. Given A-0412 is approved and used once, when the action runs again for the same subject, then it
   refuses.

**AC-M5. What a request shows** (SC5, story 12). Given lead 233 (Example Pte Ltd, logistics, score
78, `info@example.com.sg`) queued at Fri 2026-11-06 09:12, then `#approvals` shows "A-nnnn ·
outreach email · expires Tue 10 Nov, 16:30 SGT", the To line with company, industry and score, a Why
line naming the lead, run and source URL, the subject, the body as it will go out, and the Answer
line. The expiry skips the Mon 11-09 holiday.

**AC-M6. Audit** (SC6, story 16)
1. Given `approve A-0412` from actor `discord:111` at 10:02:15, then the record holds
   `decided_by = discord:111`, `decided_at = 2026-11-10T10:02:15+08:00` and the content hash. One
   `approval.approved` event carries the same three.
2. Given a direct SQL update setting a decided record back to pending, or changing its hash, then the
   trigger aborts it.
3. Given `approve A-0412` from Terminal, then `decided_by = terminal:<macOS user>`.

**AC-M7. Outreach** (SC7, stories 15 and 17; B1)
1. Given live mode at 10:00 on a business day, with A-0412 pending, when `send-due` runs, then
   nothing is sent and Resend is not called.
2. Given A-0412 is still pending at Tue 2026-11-10 16:31, then its message is `cancelled` ("approval
   expired"), the record is `expired`, and the lead stays `new`.
3. Given warm-up day 3 (cap 5) and 15 approved emails, when the day's slots run, then exactly 5
   send, each at least 10 minutes after the last and inside 09:30 to 16:30. The other 10 stay
   approved, and none is cancelled (B1).
4. Given approved A-0412, when a D1 unsubscribe for its address syncs at 16:45, then the message is
   cancelled and A-0412 becomes superseded, if unused.
5. Given block 4 isn't installed, when `outreach.mode: live` is set, then `outreach status` lists
   "approval gate not installed" and `send-due` sends nothing.

**AC-M8. App factory** (SC8, stories 19 to 22)
1. Given the 06:30 run files APP-014, then an `app-build` request posts with the PRD `.md` attached,
   the pitch, the tier and the lead types, and the "approved, build" line no longer appears.
2. When A-nnnn is approved, then an `app_builds` row exists with status `handed_off` and
   `prd_sha256` equal to the file's SHA-256. `--json` carries
   `handoff: {repo: "landing-page", prd_path, prd_sha256, approval}`, and `apps handoffs` lists it
   (B4).
3. When it is skipped, then the PRD moves to `prd/skipped/apps/` with "Skipped by Ting Yu on
   2026-11-10" at the top, and the next day's `apps context` doesn't offer the slug.
4. Given an approved build, when Dispatch sends
   `apps built APP-014 --task T-0031 --preview https://<branch>.<project>.pages.dev`, then an
   `app-release` request posts with the link. Given a build that wasn't approved, the same command
   exits 1.
5. Given no approved `app-release`, when `apps released APP-014 --task T-0031` runs, then it exits 1
   and the PRD stays in `pending/` (B3).

**AC-M9. Control commands** (SC9, stories 23 to 25)
1. Given actor `discord:111`, then each allowlisted command exits 0 (or its own meaningful code) and
   prints at most 1,900 characters.
2. When `jura-growth remote --actor discord:111 -- run social` runs, then it exits 2 with a line
   starting "refused:".
3. Given `JURA_GROWTH_JOB=social`, when any `remote`, `approve` or `skip` runs, then it exits 2.
4. Given actor `discord:999`, when `approve A-0412` runs, then it is refused and A-0412 stays pending.
5. Then each call writes a `remote.command` event with the actor and the command words, and no
   output.

**AC-M10 to AC-M14.** Secrets, privacy, read-only, brief retired, suite hygiene.
1. Given `RESEND_API_KEY_OUTREACH=re_uat_9Xq7Lm2Pz` and a Keychain stub value `kc_uat_44Lw`, planted
   in a summary, an error, a transcript and an email draft, then neither value, nor any 8-character
   piece of one, appears in any Discord payload. The setup-gap line for an unset key reads
   "`RESEND_API_KEY_OUTREACH`: not set".
2. Given `jane.tan@example.com.sg`, `+65 9123 4567` and the reply text "Please take us off your
   list", planted in the same places, then none appears. `j***@example.com.sg` appears with its
   source page.
3. Given a snapshot of the temp data folder, with and without a hot journal, when the one-pager is
   built, then nothing changed.
4. Then `outputs/growth/setup/morning-brief.md` tells Ting Yu to remove the line, and the 17:30
   digest still writes `daily-summary.json`.
5. After `uv run pytest`, `git status --porcelain` is empty and the live folders are unchanged.

### Browser publishing

**AC-P1. A request per item** (SC1). Given `publish_mode: browser` for Facebook only, when
`social submit` passes on 2026-11-10, then exactly one `social-post` request posts, with the target
Page URL, the day, the exact text, the image, the brand-gate result and "expires Tue 10 Nov, 18:00
SGT". LinkedIn and Instagram get no request.

**AC-P2. No approval, no post** (SC2). Given the item is pending, skipped, expired or superseded,
when `publish next` runs at 10:00, then it prints "nothing due" and nothing is claimed.

**AC-P3. Expiry** (SC3)
1. Given an approved item for 2026-11-10, when `publish next` runs at 18:01, or at 2026-11-11 09:00,
   then nothing is claimed and the item is `expired`.
2. Given `approve` recorded at 18:02 for that item, then the answer is "expired" and nothing changes.

**AC-P4. Joins** (SC4)
1. Given an approved join and a group with no questions, when the run clicks Join, then
   `join_status = requested` and no second request is raised.
2. Given a group that asks questions, then the run submits nothing, a second request with the
   questions and brand-gated answers posts, and only after it is approved does a later run submit
   exactly those answers.

**AC-P5. Limits** (SC5). Each line is one test. The clock is 2026-11-10.
1. A second Facebook item for the same day is refused.
2. A fourth group posted to in ISO week 46 is refused.
3. A second community post on the same day is refused.
4. An item done at 10:00: a claim at 10:15 is refused, a claim at 10:20 is allowed.
5. Claims at 08:59 and 18:00 are refused.
6. A community post on a day the confirmed rules close is refused.
7. A community post in a group with confirmed rules but unconfirmed days is refused (B5).
8. A claim whose run crashed still counts against the day's cap.
9. With `PAUSE`, `pause publish`, `pause all`, `publish_mode: draft` or `community.browser: false`,
   each in turn, nothing is claimed.

**AC-P6. Stop signals** (SC6). Given the Facebook login page appears after navigation, then the run
calls `publish stopped <id> --reason login`. The item becomes `stopped`, `publish` is paused, and
`#alerts` gets the reason and a screenshot path. The next slot claims nothing until
`resume publish`.

**AC-P7. URLs and live text** (SC7)
1. Given `publish done <id> --url https://www.facebook.com/<page>/posts/<n>` with matching live
   text, then the item, `social_posts.published_url` and the approval's `used_by_run` are all set.
2. Given a URL on another host, then the command exits 1.
3. Given live text that differs, then the item is `posted` with `live_text_matches = 0`, an alert
   posts, and `publish` is paused.

**AC-P8. Run updates** (SC8). Given a claimed item, then one run update posts in `#social-drafts` or
`#community` with the item, the outcome, and the URL or stop reason. Given nothing claimable, then no
Claude run starts and nothing posts (S3).

**AC-P9. Isolation** (SC9). The command built for `community` has no `--chrome` and keeps its
Facebook `WebFetch` denies. Only `publish` gains `--chrome`. Given a publish transcript with a
`navigate` to `https://example.com`, then the audit fails the run and pauses `publish`.

**AC-P10. Unknown** (BP:323-325). Given a claim with neither `done` nor `stopped` when the run ends,
then the item is `unknown`, it is never claimed again, `publish` is paused, and `#alerts` names
`/growth publish resolve <id>` (S6).
