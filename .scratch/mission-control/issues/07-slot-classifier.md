# 07 — MC-07 the slot classifier

Status: ready-for-agent
Blocked by: 01
PRD ticket: MC-07 in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC2

## What to build

A pure function that gives every slot of every job one slot status, so the one-pager (08) can say what ran, what was quiet and what the Mac slept through. A quiet run is ok, never missed; a slot before a job's first record is not installed; a past slot whose window is still open is due. scout-send and publish collapse to one cell per day, worst status first, with counts.

## What to change

- `slots.py`: `classify(jobs, records, now, days) -> {(job, date): [SlotState]}` under MC §4.5. Slots from `schedule.sgt_slots()` and `holidays.is_business_day()`, in SGT through `timeutil.now_sgt()`. A slot owns the window up to the next slot of the same job; within one window the latest run wins over any skip; a skip whose reason starts "not a business day" counts for no slot.
- One source per record kind: runs and the skip rows of jobs that aren't quiet from the `runs` table; `run.skipped` and `run.quiet` from the JSONL mirror only; dedupe key `(kind, ts, job, reason)` when both are read. Publish's "nothing due" arrives as `run.quiet` (01's `NothingToDo`), so it needs no special case.
- The day cell for scout-send and publish: worst status wins in the order failed, missed, running, ok, skipped, due, upcoming, not installed, with counts per status.
- Table tests over literal records (test strategy D1 fortnight), run under `TZ` set to `Asia/Singapore`, `UTC` and `America/New_York`.

## Acceptance criteria

- [ ] **AC-M2.1** Given the clock frozen at 2026-11-10 11:05, when `slots.classify` runs over the
  fixture records, then each row holds:

| Job, slot | Records | Expected |
|---|---|---|
| scout-send 10:00 | `run.quiet` at 10:00:03 | ok |
| scout-send 10:00, 10:10, 10:20 | Mac asleep; one quiet run at 10:26 | missed, missed, ok |
| app-factory 06:30 | ok run started 08:42 | ok |
| scout-research 09:00 | none | due |
| scout-research 2026-11-09 09:00 | skip "not a business day (Deepavali)" | no slot |
| backup 2026-10-30 23:30 | first backup record is 2026-11-02 | not installed |
| publish 09:00 to 11:00 | precheck skips "nothing claimable" | ok, collapsed with counts |

- [ ] **AC-M2.2** Given the same quiet skip in `events` and in the JSONL mirror, when the classifier
  reads both, then it counts once.
  *Here: the classifier. 08 proves the read model feeds it each record once.*
- [ ] **AC-M2.3** Given scout-send or publish on a day with mixed slot statuses, when the day cell is
  built, then the worst status wins in the order failed, missed, running, ok, skipped, due,
  upcoming, not installed, with the counts per status beside it.
- [ ] **AC-M2.4** Given a job not loaded in launchd that has history, then its past slots follow the
  normal rules, its upcoming slots show not installed, and it is listed under jobs not installed.
  *Here: the slot statuses. The one-pager's "jobs not installed" list is 08's.*
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, the classifier imports nothing that touches the database or files, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC SC2, §4.5, §5.3 (`slots.py`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T3 (`NothingToDo`)
- `.scratch/mission-control/reviews/technical.md` (v1: C3, B3, N2 to N4, still standing) and `technical-v2.md` (what carries over)
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M2.1 to AC-M2.4), §3 (D1 fortnight), §8 (time zones), §11.2 row MC-07
- `docs/adr/0001-…`; `CONTEXT.md` (Slot, Slot status, Quiet run, Install state)
- Code: `jura_growth/schedule.py`, `holidays.py`, `timeutil.py`, `config/sg-public-holidays.yaml`
