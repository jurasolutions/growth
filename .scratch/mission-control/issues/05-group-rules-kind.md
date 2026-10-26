# 05 — MC-05 the `group-rules` kind, with the open days typed in the decision

Status: ready-for-agent
Blocked by: 04b, 11
PRD ticket: MC-05 in `prd-jura-mission-control-2026-10-25.md` §5.12 (11 added as an edge by the ticket review)
Covers: SC10 (AC-M10.6, through remote; amended 2026-10-26: no Terminal decisions), SC4 (the `group-rules` row); MC §5.7 `group-rules` row

## What to build

Confirming a group's rules and its open days becomes an approval. Ting Yu answers in `#approvals` with the days typed in the decision (`/growth approve A-nnnn promo_days=… post_days=…`), which reaches growth through Dispatch over SSH, and that sets `rules_confirmed` and both days fields through `groups.set_fields`. This keeps blocker ticket 07's rule that rules can't be confirmed without confirmed days. *Amended 2026-10-26:* decisions come only from Dispatch over SSH. `community set … rules_confirmed=yes` from Terminal no longer confirms anything itself: it raises a `group-rules` request that Ting Yu decides in `#approvals`. Requests are raised only for rules seen inside the group or set by Ting Yu, never for researched rules.

## What to change

- The `group-rules` kind in the community plug-in: `content()` covers the group id and the rules text; decide-by 14 days; `decision_args = ("promo_days", "post_days")`; `on_approve` (from 04) applies the days through `groups.set_fields` and raises `BadArgs("say the days: promo_days=… post_days=…")` when they're missing or invalid. The card shows the rules text only and the typed form, with no button (MC §5.6).
- `community set <id> rules=…` raises a request. (`publish note-rules` raises one too, in browser-publishing#06.)
- *Amended 2026-10-26.* `community set … rules_confirmed=yes` raises a `group-rules` request over the rules text now recorded (raising nothing new if one is already live for that group), and answers with the A-id and "decide it in #approvals with promo_days=… post_days=…". It never sets `rules_confirmed` or the days itself. If no rules text is recorded, it refuses with "set the rules first: community set <id> rules=…". `promo_days` or `post_days` given in the same command are refused with the same pointer, so days are never set outside a decision.
- Existing confirmations stand, and each is recorded once as an event, by a one-off, idempotent pass in code. No community migration here; browser-publishing#02b takes the next community migration number.
- `tests/gate_adapter_group_rules.py` ("went out" means `rules_confirmed` changed). Call 02's `assert_clean` over the `group-rules` cards.

## Acceptance criteria

- [ ] **AC-M10.6** Given a `group-rules` request, when `approve A-0412` arrives without days, then it
  is refused ("say the days: promo_days=… post_days=…"); with `promo_days=sat,sun post_days=any`
  it is recorded and the group's days are set through `groups.set_fields`.
  *Owned here: through `jura-growth remote` (amended 2026-10-26; Terminal `approve` refuses and points to `#approvals`, ticket 04b).*
- [ ] **MC §5.7, `group-rules` row.** Raised by `publish note-rules` and `community set … rules=`; content covers the group id and rules text; decide-by 14 days; applied on decide; approve needs typed `promo_days` and `post_days` and sets `rules_confirmed` and both days fields through `groups.set_fields`; skip leaves the rules unconfirmed, and posts there carry no link (as today); on expire, as skip.
- [ ] **X9** *(amended 2026-10-26)*. `community set … rules_confirmed=yes` raises a `group-rules` request decided in `#approvals` and leaves `rules_confirmed` and the days unchanged until that decision is recorded through `remote`; with days in the same command, or no rules text recorded, it refuses with a pointer; existing confirmations stand and are recorded once as an event; researched rules never raise a request.
- [ ] AC-M4.1 to AC-M4.7 (owned by 04) hold for `group-rules` through its adapter file.
- [ ] **X2 for this kind.** The `group-rules` deadlines (decide-by 14 days; applied on decide) hold at the reference dates under `TZ` set to `Asia/Singapore`, `UTC` and `America/New_York`.
- [ ] The sweep in `tests/sweep.py` passes over this ticket's messages (the `group-rules` cards): no planted secret or personal data reaches the Discord double or the outbox (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC §5.1 ("Group rules"), §5.6, §5.7, §5.3 (`agents/community/__init__.py`, `groups.py`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T2, T4, T7, N9
- `.scratch/mission-control/reviews/technical-v2.md`: B7; `.scratch/mission-control/reviews/functional.md`: B5
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M10.6), §4.3 (X9), §5, §3 (D10 community), §11.2 row MC-05
- Blocker ticket `.scratch/growth-blocker-fixes/issues/07-community-negated-day-rules.md`
- Code: `jura_growth/agents/community/__init__.py`, `groups.py`, `rules.py` (`day_problem`)

## Comments

### 2026-10-26 developer: from ticket 04b's fix round

- Posting cards: every command that raises a request (A11) calls `cards.sweep_safely(conn)` as its last step, after its own transaction commits, so the cards go out (A12). There is no decorator; `approvals.raises_requests` was removed (code review 04b, Sp2). Test that the card posts when the command ends.
- Decisions come only from Dispatch over SSH (ADR 0004 as amended 2026-10-26). There is no Terminal origin, cards carry no code, and tests decide with `aw.dispatch()` and actor `aw.CONTROL`.
- **Resolved 2026-10-26 (business analyst, per the conductor):** X9 now says `rules_confirmed=yes` raises the request, decided in `#approvals`. Was: X9 says `community set … rules_confirmed=yes` from Terminal "creates and decides a `group-rules` approval with the Terminal origin in one step". That origin no longer exists. The recommendation is that `rules_confirmed=yes` from Terminal raises the `group-rules` request, and Ting Yu decides it in `#approvals` with the typed days.
- A kind may fill the optional `superseded_note(conn, subject)` hook to word the card's "Superseded:" line in its own terms (code review 04b, Sp1).
