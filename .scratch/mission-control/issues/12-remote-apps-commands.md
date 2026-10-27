# 12 — MC-11b the `apps` commands on the remote allowlist

Status: ready-for-agent
Blocked by: 11, 10b
PRD ticket: MC-11b in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC10 and SC9 (through remote)

## What to build

Dispatch can poll for build handoffs and report a finished build, and Ting Yu can plan and record a release from Discord: `apps handoffs`, `apps built`, `apps release-plan` and `apps released` join the remote allowlist with the same guarantees as every other control command.

## What to change

- The four rows of MC §5.10 for `apps` on the sorted allowlist in `remote.py`, with `--json` carrying the `handoff` object Dispatch polls (D6).
- `docs/dispatch-contract.md` gains the four commands, in the same order, and the `handoff` shape.

## Acceptance criteria

- [ ] AC-M10.1 (owned by 11) holds for `apps handoffs`, `apps built`, `apps release-plan` and `apps released`: each exits with its own meaningful code and prints at most 1,900 characters of redacted text.
- [ ] AC-M10.2's generated test (owned by 11) still refuses every leaf not on the allowlist, and every command with a `click.Path` parameter.
- [ ] **Through remote:** AC-M9.2's `--json` handoff (owned by 10), and AC-M9.7, AC-M9.8 and AC-M9.9 (owned by 10b).
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC §5.9, §5.10, §4.8 (D6, D7)
- `.scratch/mission-control/reviews/technical-v2.md`: N5 (the handoff JSON and its limit)
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M9.7 to AC-M9.9, AC-M10.1, AC-M10.2), §11.2 row MC-11b
- Tickets 10, 10b and 11 in this folder
