# 05 — MC-05 the `group-rules` kind, with the open days typed in the decision

Status: ready-for-agent
Blocked by: 04b, 11
PRD ticket: MC-05 in `prd-jura-mission-control-2026-10-25.md` §5.12 (11 added as an edge by the ticket review)
Covers: SC10 (AC-M10.6, from Terminal and through remote), SC4 (the `group-rules` row); MC §5.7 `group-rules` row

## What to build

Confirming a group's rules and its open days becomes an approval. Ting Yu answers with the days typed in the decision (`approve A-nnnn promo_days=… post_days=…`), from Terminal or from Discord, and that sets `rules_confirmed` and both days fields through `groups.set_fields`, which keeps blocker ticket 07's rule that rules can't be confirmed without confirmed days. Confirming from Terminal with `community set … rules_confirmed=yes` goes through the same path. Requests are raised only for rules seen inside the group or set by Ting Yu, never for researched rules.

## What to change

- The `group-rules` kind in the community plug-in: `content()` covers the group id and the rules text; decide-by 14 days; `decision_args = ("promo_days", "post_days")`; `on_approve` (from 04) applies the days through `groups.set_fields` and raises `BadArgs("say the days: promo_days=… post_days=…")` when they're missing or invalid. The card shows the rules text only and the typed form, with no button (MC §5.6).
- `community set <id> rules=…` raises a request. (`publish note-rules` raises one too, in browser-publishing#06.)
- `community set … rules_confirmed=yes` from Terminal creates and decides a `group-rules` approval in one step with the Terminal origin.
- Existing confirmations stand, and each is recorded once as an event, by a one-off, idempotent pass in code. No community migration here; browser-publishing#02b takes the next community migration number.
- `tests/gate_adapter_group_rules.py` ("went out" means `rules_confirmed` changed).

## Acceptance criteria

- [ ] **AC-M10.6** Given a `group-rules` request, when `approve A-0412` arrives without days, then it
  is refused ("say the days: promo_days=… post_days=…"); with `promo_days=sat,sun post_days=any`
  it is recorded and the group's days are set through `groups.set_fields`.
  *Owned here: from Terminal `approve` and through `jura-growth remote`.*
- [ ] **MC §5.7, `group-rules` row.** Raised by `publish note-rules` and `community set … rules=`; content covers the group id and rules text; decide-by 14 days; applied on decide; approve needs typed `promo_days` and `post_days` and sets `rules_confirmed` and both days fields through `groups.set_fields`; skip leaves the rules unconfirmed, and posts there carry no link (as today); on expire, as skip.
- [ ] **X9.** `community set … rules_confirmed=yes` from Terminal creates and decides a `group-rules` approval with the Terminal origin in one step; existing confirmations stand and are recorded once as an event; researched rules never raise a request.
- [ ] AC-M4.1 to AC-M4.7 (owned by 04) hold for `group-rules` through its adapter file.
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
