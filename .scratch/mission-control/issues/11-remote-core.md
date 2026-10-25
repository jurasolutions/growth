# 11 — MC-11a `jura-growth remote`: control commands for Dispatch

Status: ready-for-agent
Blocked by: 04b
PRD ticket: MC-11a in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC10, SC7 (the SSH origin), SC6 (through remote); ADR 0004

## What to build

One entry point, `jura-growth remote`, reached only through an SSH forced command, lets Dispatch run status, pause and resume, list approvals, approve and skip, requeue shadow emails and settle stuck items for Ting Yu from Discord. It accepts only an allowlist, never runs a shell, records who sent each command, and answers with a closed enum Dispatch can read. A written contract tells Dispatch exactly what to send and what comes back, and a setup guide tells Ting Yu how to open the Mac to it safely.

## What to change

- `remote.py`: `jura-growth remote [--actor discord:<id>] [--ref <ref>] [--json] -- <command…>`. It checks the origin (MC §4.6 A8: `sshd` ancestor, `SSH_ORIGINAL_COMMAND`, never a `claude` ancestor), refuses whenever `JURA_GROWTH_JOB` is set, parses against its own allowlist (MC §5.10, without the `one-pager`, `apps` and `publish` rows), runs the command in-process with the SSH `Origin` in `ctx.obj["origin"]` (04b's plumbing), and prints at most 1,900 characters of redacted text with a meaningful exit code. Anything else exits 2 with "refused:". Each call writes one `remote.command` event with the actor and the words, never the output.
- The allowlist is sorted by command, one entry per line, so 09, 12 and browser-publishing#03 add rows in separate hunks; rows in `docs/dispatch-contract.md` keep the same order.
- `bin/growth-remote`: the forced-command wrapper. It splits `SSH_ORIGINAL_COMMAND` into words without a shell and passes them to `jura-growth remote`.
- `--json`: `{contract: 1, ok, answer, exit_code, text, approvals?, handoff?}` with a 64 KB limit; `answer` from the closed enum, each mapped to one exit code.
- The remote grammar for `key=value` decision arguments, tested with 04's fake kind (its `decision_args`). The real `group-rules` days are 05's.
- `docs/dispatch-contract.md`: the grammar, the answer enum and exit codes, the `--json` shape, `--ref`, the transport, and D1 to D9.
- The setup guide drafted as `.scratch/mission-control/setup/remote-control.md`: Remote Login limited to Ting Yu's user, key-only, the one `restrict,command=…,from=…` `authorized_keys` entry, and Tailscale. The release persona copies it to `jurasolutions/outputs/growth/setup/` after the merge. The key itself is Ting Yu's (ticket 14).
- `discord.py`: the optional `components` payload for Approve and Skip buttons, sent only when `approvals.post_buttons: true` (04b's block), never on `group-rules` cards.
- ADR 0004 moves to accepted.

## Acceptance criteria

- [ ] **AC-M10.1** Given an SSH origin and actor `discord:111`, then each allowlisted command (§5.10)
  exits with its own meaningful code and prints at most 1,900 characters of redacted text.
  *Owned here for the core commands. 09 adds `one-pager`, 12 the `apps` commands, browser-publishing#03 `publish queue` and `publish resolve`.*
- [ ] **AC-M10.2** When `jura-growth remote --actor discord:111 -- run social` runs, then it exits 2
  with a line starting "refused:". A generated test does this for every CLI leaf not on the
  allowlist and for every command with a `click.Path` parameter.
- [ ] **AC-M10.3** Given the words `;`, `&&`, `$(…)`, backticks and newlines, then they arrive as
  literal arguments and run nothing; `bin/growth-remote` never invokes a shell.
- [ ] **AC-M10.4** Then each call writes one `remote.command` event with the actor and the command
  words, and no output.
- [ ] **AC-M10.5** Given `--json`, then the answer is `{contract: 1, ok, answer, exit_code, text,
  approvals?, handoff?}`, `answer` is one of `recorded`, `expired`, `superseded`,
  `already-decided`, `already-used`, `unknown-id`, `refused`, and each maps to one exit code in
  `docs/dispatch-contract.md`.
- [ ] **AC-M10.7** When `resume all` runs with a PAUSE file present, then the agents resume and the
  answer says the PAUSE file can only be removed on the Mac.
- [ ] **AC-M7.5** Given `jura-growth remote` started without an `sshd` ancestor or without
  `SSH_ORIGINAL_COMMAND`, then it is refused.
- [ ] **The remote halves of earlier criteria.** AC-M7.1 for `remote` (exit 2 with "refused:" whenever `JURA_GROWTH_JOB` is set); AC-M6.1 and AC-M6.2 with the decision arriving through `jura-growth remote`; AC-M7.6 through remote; AC-M5.4 through `/growth approvals`; AC-M8.13 through `/growth outreach requeue-shadow`.
- [ ] `approve A-nnnn promo_days=… post_days=…` through remote reaches the fake kind's `on_approve` with both arguments, and is refused without them.
- [ ] **X11.** `components` is sent only when `approvals.post_buttons` is true, and never on a `group-rules` card.
- [ ] A real subprocess `uv run jura-growth remote …`, with every data variable pointed at temp folders, gives exit 0, 1 and 2 for the three classes.
- [ ] The sweep over remote output finds no planted secret or personal data (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] `docs/adr/0004-decisions-come-only-from-a-human-origin.md` says accepted.
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, `security-review` has run on `remote.py` and `bin/growth-remote`, `uv run pytest` passes, and the report is in. Opening the Mac to Dispatch is Ting Yu's ticket 14. Then wait for go-ahead.

## Pointers

- PRD: MC SC10, §4.6 A8 to A10, §4.7, §4.8 (D1 to D9), §5.10, §5.3 (`remote.py`, `bin/growth-remote`, `docs/dispatch-contract.md`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T1 (origin plumbing), T4, T10, N4, N8
- `.scratch/mission-control/reviews/technical-v2.md`: B2, B3, N6; Specialist guidance (`crew:api-and-interface-design` for the contract)
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M10.x, AC-M7.5), §4.3 (X11), §2 (Dispatch double), §11.2 row MC-11a
- `docs/adr/0004-…`; `CONTEXT.md` (Control command, Human origin)
- `~/projects/discord-automation/` (Dispatch's PRD: SEC-1, SEC-3, hard rule 6), read-only from here
- Code: `jura_growth/cli.py`, `headless.py` (`leaves`), `discord.py`, `origin.py`
