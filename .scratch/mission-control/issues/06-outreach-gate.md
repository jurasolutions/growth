# 06 — MC-06 the outreach gate: no live email without a claimed approval

Status: ready-for-agent
Blocked by: 04b
PRD ticket: MC-06 in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC8, SC5 (AC-M5.1), SC12 (AC-M12.2), SC4 (the `outreach-email` row)

## What to build

In live mode, `outreach send-due` sends only emails it has claimed an approval for, and every existing limit still applies on top. Requests are raised only for emails due today and only up to today's remaining quota, so Ting Yu is never asked about more emails than the warm-up can send. Shadow mode raises and claims nothing. Live mode stays refused until the Discord buttons work: this ticket swaps 01's "approval gate not installed" for "approval buttons not set up".

## What to change

- The `outreach-email` kind: `content()` covers the recipient address of the contact row the send will use (`queue.recipient()`), the subject and `draft_body`, not the footer. Decide-by 16:30 on the next business day; use-by 16:30 on the third business day after approval (Ting Yu's G2 answer to MC §6 Q1). Skip, expire and lapse as in the MC §5.7 row.
- A14 in `queue()`, `send-due` (the first run of the day, and after each send or skip) and `requeue-shadow`: requests only for emails with `send_after <= today`, up to `send.quota()`, counting pending and approved, unused requests already open.
- `send-due` considers only `due(conn, approved_only=True)` in live mode (which also feeds the spacing probability), applies every existing check in today's order, then claims the approval and increments `attempts` in one `BEGIN IMMEDIATE` transaction, then calls Resend under the existing `Idempotency-Key: jura-outreach-<id>`, then marks the message sent.
- `declined_by_ty` joins `FINAL_LEAD_STATUSES`.
- `send.live_problems()`: "approval buttons not set up" replaces "approval gate not installed", and clears only when `approvals.discord_buttons: true` (04b's block, read only here). That switch is Ting Yu's, in ticket 15.
- `JURA_GROWTH_RESEND_BASE_URL`: points Resend at a local recorder for the UAT harness, refused unless the data folder is a temp folder.
- The email card (MC §5.6): the full draft as it will go out; a named-person recipient masked, with the hash still covering the full address. The `email` brand channel drops a draft that greets a person by name.
- `tests/gate_adapter_outreach_email.py` ("went out" means the Resend double received a request). Call 02's `assert_clean` over email drafts and cards.
- Release note for this ticket: set `outreach.mode: shadow` before any rollback past this merge (MC §5.8).

## Acceptance criteria

- [ ] **AC-M5.1** Given lead 233 (Example Pte Ltd, logistics, score 78, `info@example.com.sg`) whose
  first email is due Fri 2026-11-06 and raised at 09:12, when the card posts, then it shows
  "A-nnnn · outreach email · decide by Tue 10 Nov, 16:30 SGT", the To line with company, industry
  and score, a Why line naming the lead, run and source URL, the subject, the body as it will go
  out, and the Answer line. The decide-by skips the Mon 11-09 holiday.
- [ ] **AC-M8.1** Given live mode at 10:00 on a business day and A-0412 pending, when `send-due` runs,
  then nothing is sent and Resend is not called.
- [ ] **AC-M8.2** Given warm-up day 3 (cap 5), nothing sent today, and 15 first emails due today, when
  `queue` and the first `send-due` run, then exactly 5 requests are raised and the other 10 stay
  queued with no request ("waiting for a request slot"). When 3 of the 5 are sent and 2 skipped,
  then the next `send-due` raises 2 more.
- [ ] **AC-M8.3** Given a follow-up queued with `send_after` five business days ahead, then no request
  is raised until its day.
- [ ] **AC-M8.4** Given A-0412 raised Fri 2026-11-06 and still pending at Tue 2026-11-10 16:31, then
  the message is `cancelled` ("not approved in time"), the record is `expired`, and the lead stays
  `new`.
- [ ] **AC-M8.5** Given A-0412 approved Tue 2026-11-10 10:00 and not sent because the limits never
  reached it, then at Fri 2026-11-13 16:31 the message is `cancelled` ("approved but the limits
  didn't reach it"), the record is `expired` with `used_at` empty, the lead stays `new`, and the
  next one-pager lists it.
  *Here: the message, record and lead states. The one-pager's line is 08's.*
- [ ] **AC-M8.6** Given A-0412 skipped, then the message is `cancelled` ("skipped by Ting Yu") and the
  lead becomes `declined_by_ty`, a final status, so it is never queued again.
- [ ] **AC-M8.7** Given A-0412 approved and unused, when Ting Yu skips it, then the skip wins as in
  AC-M8.6. Given it was already used, then the answer is "already sent at 10:40; can't be undone".
- [ ] **AC-M8.8** Given an approved, unused A-0412, when a D1 unsubscribe for its address syncs at
  16:45, then at the next read or claim the kind's `content()` returns nothing and A-0412 becomes
  superseded.
- [ ] **AC-M8.9** Given a new unsubscribe token in the footer, then A-0412 still matches; given one
  character changed in the recipient, subject or `draft_body`, then it doesn't.
- [ ] **AC-M8.10** Given shadow mode, then no request is raised, nothing is claimed and shadow
  recording works as today. Given an approved message shadow-sent after a switch back to shadow,
  then its approval stays unused and lapses at its use-by.
- [ ] **AC-M8.11** Before MC-06 lands, `live_problems()` lists "approval gate not installed"; from
  MC-06 until `approvals.discord_buttons: true` is set in `config/settings.yaml`, it lists "approval
  buttons not set up". While either line shows, `outreach.mode: live`, `send-due` in live mode and
  `requeue-shadow` refuse.
  *Owned here: from MC-06 on, "approval buttons not set up" and the three refusals. 01 delivered the first line.*
- [ ] **AC-M8.12** Given approved emails, when the existing live tests in `tests/test_outreach_send.py`
  run with an approval fixture, then window, cap, warm-up, gap, spacing, rolling caps, suppression
  sync, per-message suppression, do-not-contact, contacted domains, the per-company rule and the
  send-time brand gate each still hold, and the spacing probability counts approved emails only.
- [ ] **AC-M8.13** Given `requeue-shadow` in live mode with 40 shadow emails, then it raises requests
  only up to today's remaining quota, like AC-M8.2.
  *Here: from Terminal. Through remote in 11.*
- [ ] **AC-M12.2** Given an email draft that greets a person by name, when the `email` brand channel
  checks it, then it is dropped, so the approval card's body is the email as it
  will go out.
  *The ticket review dropped "(subject to §6 Q2)": Ting Yu accepted that question at G2.*
- [ ] AC-M4.1 to AC-M4.7 (owned by 04) hold for `outreach-email` through its adapter file, with the Resend double asserting at call time that the record is already used (AC-M4.3) and a retry under the same idempotency key not counting as a second use (AC-M4.5).
- [ ] **X2, X3 and X13 for this kind.** The deadline table at the reference dates under three `TZ` values; a configured deadline may shorten and never lengthen; the Resend stub refuses a non-temp data folder.
- [ ] The sweep over email drafts and cards finds no planted secret or personal data (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `security-review` has run on the `send.py` change, `uv run pytest` passes, and the report is in. Live outreach itself waits for ticket 15. Then wait for go-ahead.

## Pointers

- PRD: MC SC8, §4.4, §4.6 A5, A13, A14, §5.7 (`outreach-email` row), §5.8, §6 Q1 and Q2 (accepted at G2)
- `.scratch/mission-control/reviews/tickets-technical.md`: T7, T10, N5
- `.scratch/mission-control/reviews/technical-v2.md`: B1, B5, N3, N4, N13; Risks (rollback)
- `.scratch/mission-control/reviews/functional.md`: B1, S1, S17
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M5.1, AC-M8.x, AC-M12.2), §4.3 (X2, X3, X13), §5, §3 (D8 outreach live), §9 (the Resend crash gap), §11.2 row MC-06
- `.scratch/mission-control/uat.md` Parts A and E
- Code: `jura_growth/agents/outreach/queue.py`, `send.py`, `requeue.py`, `store.py`; `jura_growth/gate.py`; `tests/test_outreach_send.py`, `tests/test_scout_support.py` (`fake_resend`)
