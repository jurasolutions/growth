# Decisions and control commands come only from a human origin

Status: accepted (2026-10-26, ticket MC-11a of `prd-jura-mission-control-2026-10-25.md`). Proposed
2026-10-25 and amended 2026-10-26 by Ting Yu's decision to turn Terminal decisions off. Amended
again 2026-10-29 by his decision to run Dispatch on this Mac (see "Amendment 2026-10-29" at the
end). Referenced from ticket MC-04.

Decisions come only from Dispatch over SSH. Terminal decisions are disabled until a Touch ID ticket
exists.

A decision or control command reaches the growth Mac in one way only: `jura-growth remote`, reached
through an SSH forced command (`restrict`, `from=`) whose key lives only with Dispatch's gateway
user. Since 2026-10-29 that connection is to `127.0.0.1` on the same Mac, with no Tailscale. Ting
Yu decides in `#approvals` from his own Discord account; Dispatch carries the decision and his
Discord user id. `remote` checks the origin before it decides (`origin.detect_ssh()`):

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
consistency; the SSH key and Dispatch's own allowlist are the guard. Dispatch runs on the growth
Mac as its own hidden `dispatch` user (Ting Yu, 2026-10-29, reversing "Dispatch never runs on the
growth Mac" of 2026-10-25), and no model rewrites a command between Ting Yu and `remote`.

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

A real SSH login to the Mac is still a real `sshd` origin. So sshd reads Ting Yu's keys only from
the root-owned `/etc/ssh/authorized_keys.d/tingy`, which holds only Dispatch's entry, restricted to
the forced command and to loopback (`restrict`, `command=`, `from="127.0.0.1,::1"`), and Remote
Login takes keys only, for Ting Yu's user only. Another key in that file, or password login, would
let any process that can read the matching secret run `ssh tingy@127.0.0.1 …` and send control
commands. The setup guide (`outputs/growth/setup/remote-control.md`) has the steps and the checks.

Until 2026-10-29 the entry lived in `~/.ssh/authorized_keys`, which any process running as Ting
Yu's user can write. Such a process, a headless growth run or an interactive Claude session, could
append a key of its own and log in: a real root `sshd` origin, no `claude` ancestor, and Claude's
markers dropped by sshd. That route was open in the Tailscale design too, and this section named
only "another key in that file". The root-owned file closes it: sshd never reads
`~/.ssh/authorized_keys` now.

Anything that can write `growth.db` directly can forge a decision with raw SQL, and anything that
can edit `bin/growth-remote` changes the forced command itself. The `approvals` trigger refuses the
transitions A7 doesn't allow, but no trigger can tell who wrote a row. Headless runs reach the
database only through `jura-growth` commands (`Bash(jura-growth …)` rules). An interactive session
on the Mac is outside these guards. So don't open `growth.db` for writing from one, and don't let
one run shell commands without asking (auto mode, `--dangerously-skip-permissions`) while it reads
content from outside.

The audit trail has a known gap too. A decision's `approval.*` events are rows in `growth.db`,
committed with the decision, and lines in the JSONL mirror, written only after that commit. So a
decision or claim that rolls back leaves no trace in either. A crash between the commit and the
mirror write loses those lines while the rows stay. We accept that: `growth.db` is the log of
record, and the opposite order would leave the append-only mirror holding a decision or a claim
that never happened (`jura_growth/log.py`).

## Amendment 2026-10-29: Dispatch runs on this Mac

Ting Yu decided on 2026-10-29 to use only this Mac: "i want to only use my mac. i dont have that
windows laptop anymore." The plan is §8 of the Dispatch growth-control PRD
(`discord-automation/prd/pending/prd-discord-dispatch-growth-control-2026-10-27.md`), and the
mission-control PRD's TY2 carries a dated note. Only the hop changes. The forced command, `remote`,
`origin.detect_ssh()`, `approvals.decide()` and contract version 1 stay exactly as they were, and
no growth code changes.

### What changes

- Dispatch's gateway connects to `tingy@127.0.0.1`, port 22, with `/usr/bin/ssh`. The host key is
  pinned from the Mac's own `/etc/ssh/ssh_host_ed25519_key.pub`, so nothing is trusted on first
  use. There is no Tailscale and no second machine.
- Dispatch runs as `dispatch`, a hidden standard user with no usable password and no admin rights,
  started by two LaunchDaemons. Its home, `/Users/dispatch`, is mode 700, and the growth key is
  `/Users/dispatch/.dispatch-keys/growth_mac`, mode 600.
- Dispatch's Claude tasks and their checks run as a second hidden user, `claude-runner`, through
  `sudo -n -u claude-runner -- /usr/bin/env -i …`. That is the only sudo rule `dispatch` has, and
  `claude-runner` has none.
- An sshd drop-in, `/etc/ssh/sshd_config.d/010-dispatch-growth.conf`, sets keys only
  (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `AuthenticationMethods
  publickey`), `PermitRootLogin no`, `AllowUsers tingy`, `AuthorizedKeysFile
  /etc/ssh/authorized_keys.d/%u`, `PermitUserEnvironment no`, `DisableForwarding yes` and
  `PermitTTY no`. The `010-` prefix sorts it before macOS's own `100-macos.conf`, and sshd keeps the
  first value it reads.
- The one key line moves to `/etc/ssh/authorized_keys.d/tingy`, owned by root, mode 644:

  ```
  restrict,command="<repo>/bin/growth-remote",from="127.0.0.1,::1" ssh-ed25519 AAAA… dispatch-growth
  ```

- `/Users/tingy` becomes mode 700.

### Why `origin.detect_ssh()` still holds

Each of its checks sees the same thing on loopback as it did over Tailscale.

- `SSH_ORIGINAL_COMMAND` is set by sshd for the forced command.
- A root `sshd` is an ancestor. macOS starts sshd per connection from launchd
  (`com.openssh.sshd`). `jura-growth remote` runs under `bin/growth-remote`, under `sshd-session`
  as `tingy`, under the root `sshd-session` or `sshd` monitor, under launchd. `_is_sshd_named`
  matches `sshd-session` by its prefix.
- No `claude` ancestor. The server side's chain starts at launchd. Dispatch's `ssh` client is not
  in it, so even a Claude process acting as the client would not appear.
- None of Claude Code's markers is set. sshd builds a fresh environment and accepts only `LANG` and
  `LC_*` from the client. Dispatch sends none (`-F /dev/null`, no `SendEnv`), and
  `PermitUserEnvironment no` stops an `environment=` option.

The alternatives each fail it. The gateway running `jura-growth remote` itself through
`sudo -u tingy` has no `sshd` ancestor, so `detect_ssh()` refuses; accepting it would mean a new
origin and a new contract. A Unix socket served by a `tingy` process is new code and a new origin
too. Tailscale to the Mac's own tailnet address is a dependency that buys nothing on one machine.

### What changes in the threat model

- **A local process running as `tingy` can't add a key.** sshd reads only the root-owned file in
  `/etc`, so writing `~/.ssh/authorized_keys` does nothing. This closes the route described under
  "The remaining limit".
- **`from=` no longer tells Dispatch apart.** Every local process connects from `127.0.0.1`. The
  option still makes the key useless from any other machine. On this Mac the guard is possession
  of the private key, which only `dispatch` can read.
- **`tingy` can't read the key.** This is why the gateway doesn't run as Ting Yu's own user. If it
  did, growth's headless runs and his interactive Claude sessions, all running as `tingy`, could
  read the key and run `ssh -i … tingy@127.0.0.1 -- approve A-nnnn`: a root `sshd` origin, no
  `claude` ancestor, markers dropped. That is the forgery this ADR exists to stop.
- **`claude-runner` can't reach a decision.** It can't read the key (`/Users/dispatch` is 700,
  Claude's per-run settings deny it, and the checks' Seatbelt profile never allows it). It can't
  log in with a key of its own (the root-owned file, `AllowUsers tingy`, and
  `com.apple.access_ssh` holding only `tingy`). It can't write `growth.db` or growth's files
  (`/Users/tingy` is 700). It has no sudo rule and no Discord token, its sandbox network allowlist
  never holds a loopback name, and the checks profile denies TCP to `localhost:22`. The worker's
  only growth call is `apps built`, which records a build, never a decision.
- **What `dispatch` runs must not be writable by `tingy`.** Otherwise a `tingy` process could plant
  a program that runs as `dispatch` with the key in reach. So the LaunchDaemons' `PATH` leaves out
  Homebrew (owned by `tingy`), `growth.ssh.command` is `/usr/bin/ssh`, and Dispatch's
  `check-config` fails when that command, or any folder above it, is writable by anyone but root.
  Dispatch keeps this rule; growth relies on it.
- **Unchanged.** Anything running as `tingy` can still write `growth.db` directly or edit
  `bin/growth-remote`, as described above. Moving Dispatch onto the Mac doesn't widen that, and the
  `dispatch` user keeps the SSH route from becoming a second way in.
- **Network exposure is the same as before.** macOS's sshd listens on every interface through
  launchd's socket and advertises over Bonjour, as it did with Remote Login on in the Tailscale
  design. With passwords off and the only key bound to loopback, another device on the network
  can't log in. A pf rule limiting port 22 to `lo0` is a later item.
- **One machine fails as one.** When the Mac is off, Dispatch is off with it, and Discord shows its
  own "The application did not respond". "The growth Mac is unreachable" now means Remote Login is
  off or sshd is down. Either way nothing is held for later, requests stay pending, and the
  one-pager lists them.
