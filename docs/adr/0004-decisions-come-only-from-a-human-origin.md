# Decisions and control commands come only from a human origin

Status: accepted (2026-10-26, ticket MC-11a of `prd-jura-mission-control-2026-10-25.md`). Proposed
2026-10-25 and amended 2026-10-26 by Ting Yu's decision to turn Terminal decisions off. Referenced
from ticket MC-04.

Decisions come only from Dispatch over SSH. Terminal decisions are disabled until a Touch ID ticket
exists.

A decision or control command reaches the growth Mac in one way only: `jura-growth remote`, reached
through an SSH forced command (`restrict`, `from=`, over Tailscale) whose key lives only with
Dispatch's gateway user. Ting Yu decides in `#approvals` from his own Discord account; Dispatch
carries the decision and his Discord user id. `remote` checks the origin before it decides
(`origin.detect_ssh()`):

- `SSH_ORIGINAL_COMMAND` is set;
- an `sshd` process running as root is an ancestor, and no ancestor is `claude`;
- none of Claude Code's environment markers (`CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_PID`)
  is set.

Root matters. A process name is only a file name: during ticket MC-11a, an orphaned shell run from
inside a Claude session through a symlink called `sshd`, with `SSH_ORIGINAL_COMMAND` set, passed a
check that looked only at names. The real daemon's privileged monitor runs as root above every
session, and no process running as Ting Yu's user can start a root one. That probe is a regression
test too (`tests/test_origin_processes.py`).

Those variables can only refuse an origin, never grant one. `approvals.decide()` accepts no other
origin. The Discord user id is attribution, checked against `CONTROL_DISCORD_USER_ID` for
consistency; the SSH key and Dispatch's own allowlist are the guard. Dispatch never runs on the
growth Mac (Ting Yu, 2026-10-25), and no model rewrites a command between Ting Yu and `remote`.

`jura-growth approve` and `skip` typed in Terminal refuse and point to `#approvals`. Nothing is
recorded. They decide only when `remote` passes its origin to them in process. `headless.NEVER`
and a check for `JURA_GROWTH_JOB` still refuse all of them to every scheduled run.

## Why Terminal decisions are off

The first design let Ting Yu decide in Terminal: a real TTY, no `claude` ancestor, and the first six
hex characters of the content hash typed. Crew code review 04b showed that this can't tell Ting Yu
from another process running as his macOS user.

1. A process started from an interactive Claude session can leave the session's process tree (a
   double fork, `nohup … &`, `launchctl submit`, `tmux`, a new Terminal window through `open` or
   `osascript`).
2. It can give itself a terminal (`expect`, `script`, Python's `pty`).
3. It can then type the code, which is not a secret: the card, the listing and `growth.db` all
   showed it.

From inside a Claude session the review recorded Terminal decisions with an orphaned
`/usr/bin/expect`. That probe is now a regression test (`tests/test_origin_processes.py`), refused
with the Claude markers set and with them stripped.

Only proof of presence that no process can produce would close this, such as Touch ID or the login
password through macOS LocalAuthentication. That needs a new helper or dependency, so it would come
as its own ticket. Until then the card carries no code, and Terminal can only list requests.

## The remaining limit

A real SSH login to the Mac is still a real `sshd` origin. So the Mac's `authorized_keys` holds only
Dispatch's entry, restricted to the forced command and to Dispatch's tailnet address (`restrict`,
`command=`, `from=`), and Remote Login takes keys only. Another key in that file, or password login,
would let any process that can read the matching secret run `ssh localhost jura-growth remote …`.
The setup guide (`outputs/growth/setup/remote-control.md`) has the steps and the checks.

Anything that can write `growth.db` directly can forge a decision with raw SQL. The `approvals`
trigger refuses the transitions A7 doesn't allow, but no trigger can tell who wrote a row. Headless
runs reach the database only through `jura-growth` commands (`Bash(jura-growth …)` rules). An
interactive session on the Mac is outside these guards. So don't open `growth.db` for writing from
one, and don't let one run shell commands without asking (auto mode,
`--dangerously-skip-permissions`) while it reads content from outside.

The audit trail has a known gap too. A decision's `approval.*` events are rows in `growth.db`,
committed with the decision, and lines in the JSONL mirror, written only after that commit. So a
decision or claim that rolls back leaves no trace in either. A crash between the commit and the
mirror write loses those lines while the rows stay. We accept that: `growth.db` is the log of
record, and the opposite order would leave the append-only mirror holding a decision or a claim
that never happened (`jura_growth/log.py`).
