# 10 — MC-10 app ideas wait for approval, and approval writes the build handoff

Status: ready-for-agent
Blocked by: 04b, 08
PRD ticket: MC-10 in `prd-jura-mission-control-2026-10-25.md` §5.12, first half: idea to handoff (split by the ticket review; the release is 10b; 08 added as an edge)
Covers: SC9 (idea to handoff), SC4 (the `app-build` row)

## What to build

The 06:30 app-factory run sends its idea and PRD to `#approvals` instead of posting "approved, build …". Approving it writes a build handoff in the same transaction, which Dispatch, or Ting Yu by hand until Dispatch can, builds on its own task branch from `main`. Until Dispatch polls the handoffs, the decision answer and the one-pager say how to build it by hand. A skipped idea never comes back; one left unanswered can return after 30 days.

## What to change

- The `app-build` kind (content: the PRD file's bytes; decide-by 7 days; use-by 1 day), with its `on_approve` (from 04) claiming the approval and writing the `handed_off` row in the decision's transaction, as in the MC §5.7 row.
- A plug-in migration for `app_builds` (app id, PRD path, PRD SHA-256, approval id and date, status). The approval id and date go in the row, never into the PRD file, so its hash stays valid.
- `apps submit-prd` raises the `app-build` request with the PRD attached and the pitch, tier and lead types.
- `apps handoffs [--json]` lists open handoffs with the PRD text and its SHA-256 (64 KB limit on the JSON).
- `approvals.dispatch_builds` (04b's block, read only here): with `false`, the decision answer and the one-pager carry the "Build it: …" line; with `true`, the answer says the build was handed to Dispatch, and the one-pager still lists open handoffs without the "Build it" text. Tests run both values.
- The apps plug-in's `health()` hook (from 08): "build handoffs waiting for a builder".
- Skip and expire move the PRD to `prd/skipped/apps/`; the waiting pile (7) counts PRDs waiting for an `app-build` decision.
- A one-off, idempotent pass that raises one `app-build` request for each factory PRD already in `prd/pending/apps/`.
- `prompts/app-factory.md` and `docs/` drop the "approved, build …" line.
- `tests/gate_adapter_app_build.py`, with the Dispatch double asserting at call time that the record is already used. Call 02's `assert_clean` over app cards. Tests use a temp `JURA_PRD_DIR`.

## Acceptance criteria

- [ ] **AC-M9.1** Given the 06:30 run files APP-014, then an `app-build` card posts with the PRD `.md`
  attached, the pitch, the tier and the lead types, and the "approved, build …" line no longer
  appears.
- [ ] **AC-M9.2** When A-nnnn is approved and the handoff runs, then the approval is used in the
  transaction that writes one `app_builds` row (`handed_off`, `prd_sha256` equal to the file's
  SHA-256, the approval id and date); `--json` carries `handoff: {repo: "landing-page", base:
  "main", prd_text, prd_sha256, approval}`; and `apps handoffs` lists it until it is built.
- [ ] **AC-M9.3** Given Dispatch D6 isn't set up, when the build is handed off, then the decision
  answer and the one-pager say "Build it: open Claude Code in `jurasolutions/` and say: build the
  approved PRD `<path>` (approval A-nnnn)".
  *Owned here: the decision answer and the one-pager line, through the apps `health()` hook.*
- [ ] **AC-M9.4** Given one byte of the PRD changed after approval, then no handoff is written, A-nnnn
  is superseded and a new request is raised.
- [ ] **AC-M9.5** When A-nnnn is skipped, then the PRD moves to `prd/skipped/apps/` with "Skipped by
  Ting Yu on 2026-11-10" at the top, the backlog row closes, and the next day's `apps context`
  doesn't offer the slug.
- [ ] **AC-M9.6** Given A-nnnn unanswered for 7 days, then the PRD moves to `prd/skipped/apps/` with
  "Expired unanswered on <date>", and the backlog idea reopens so it can be proposed again after
  30 days.
- [ ] **AC-M9.10** Given seven PRDs waiting for an `app-build` decision, then the factory stops, as the
  waiting pile does today.
- [ ] **AC-M9.11** Given factory PRDs already in `prd/pending/apps/` when MC-10 ships, then a one-off,
  idempotent pass raises one `app-build` request for each.
- [ ] AC-M4.1 to AC-M4.7 (owned by 04) hold for `app-build` through its adapter file.
- [ ] **X2, X3 and X7 for this kind.** The deadline table; a configured deadline may only shorten; the `app_builds` migration changes no existing row.
- [ ] The sweep over app cards finds no planted secret or personal data (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Ting Yu's first real app build (U8) is ticket 16. Then wait for go-ahead.

## Pointers

- PRD: MC SC9, §4.8 (D6, the landing page), §5.7 (`app-build` row), §5.9 steps 1, 2, 5 to 7, §5.3 (`agents/apps/*`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T2, T4, T5, T9, T10, Q6
- `.scratch/mission-control/reviews/technical-v2.md`: N5; `.scratch/mission-control/reviews/functional.md`: B4, S9, S10
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M9.1 to AC-M9.6, AC-M9.10, AC-M9.11), §4.3 (X2, X3, X7), §3 (D9 app factory), §11.2 row MC-10
- `jurasolutions/prd/pending/prd-jura-app-factory-2026-10-24.md` §5.6 (superseded in part by this PRD); `jurasolutions/CLAUDE.md` folder map (`prd/skipped/`)
- Code: `jura_growth/agents/apps/` (`prd.py`, `factory.py`, `backlog.py`), `prompts/app-factory.md`, `tests/test_apps.py`

## Comments

### 2026-10-26 developer: from ticket 04b's fix round

- Posting cards: `apps submit-prd` (and `apps built` in 10b) call `cards.sweep_safely(conn)` as their last step, after their own transaction commits, so the cards go out (A12). There is no decorator; `approvals.raises_requests` was removed (code review 04b, Sp2). Test that the card posts when the command ends.
- Decisions come only from Dispatch over SSH (ADR 0004 as amended 2026-10-26). AC-M9.2 "from Terminal" now means through `remote`'s in-process seam; there is no Terminal origin, cards carry no code, and tests decide with `aw.dispatch()` and actor `aw.CONTROL`.
- The deadline settings are read through `approval_settings.deadline("app-build", …)`, and `approval_settings.switch("dispatch_builds")` says whether Dispatch polls the handoffs.
- A kind may fill the optional `superseded_note(conn, subject)` hook to word the card's "Superseded:" line in its own terms (code review 04b, Sp1).
