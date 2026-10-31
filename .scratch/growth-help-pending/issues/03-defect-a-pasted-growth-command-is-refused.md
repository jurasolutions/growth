# 03: defect: a command pasted with its `/growth` prefix is refused

**Closed by the conductor on 2026-11-01: not a defect.** Dispatch PRD AC-D2.2 says a first word that is
literally `/growth` is dropped from a plain message in `#control`, so this text can't reach growth. The
three red tests aren't brought over, and `remote.match` doesn't change.

Severity: minor. It costs one retry, and the refusal lists the right words. But it is the same failure
that prompted ticket 01, on the exact text `pending` tells Ting Yu to send.

Found by QA 01 at `d80d73f`. Red tests: `tests/test_pending_qa01.py` on branch
`crew/growth-help-pending-qa01` (commit `14f9fa6`), the three under "defect 03".

## Steps

1. `/growth pending` answers ``Send `/growth apps release-plan APP-005` for the merge.``
2. `help` says each command can also go "as a plain message in #control".
3. Copy the backticked text and paste it as a message in `#control`. Dispatch passes the text verbatim
   (`docs/dispatch-contract.md`, Transport), so growth receives
   `remote --actor discord:<id> --ref … --json -- /growth apps release-plan APP-005`.

## Expected

The command runs, the same as `apps release-plan APP-005`.

## Actual

Exit 2, on the copy of the live state:

```
refused: `/growth apps` isn't a control command. Send one of: approvals, approve, apps built, …
```

`/growth pending` and `/growth help` are refused the same way. On a phone, long-press copies the whole
message, so typing it again is the only other route.

## Not verified

Dispatch's code isn't in this repo. If Dispatch strips a leading `/growth` from plain messages, this
can't be reached in production, and the tests should go. The contract says it passes the text verbatim,
and ticket 01 says Dispatch needs no change, so the tests assert the fix at growth's seam, in
`remote.match`. The event's `words` should still record what was typed.

## Evidence

```
test_a_command_pasted_with_its_growth_prefix_runs[words0]: assert 2 == 0
test_a_command_pasted_with_its_growth_prefix_runs[words1]: assert 2 == 0
test_the_command_pending_prints_runs_when_pasted_whole: assert 2 == 0
```
