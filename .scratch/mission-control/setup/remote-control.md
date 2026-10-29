# Remote control: open this Mac to Dispatch over SSH

*Mission control, ticket 14. About 30 minutes, most of it in Dispatch's paste block. Drafted in
ticket 11; rewritten on 2026-10-30 for Dispatch on this Mac (Dispatch growth-control PRD §8). The
release copies it to `outputs/growth/setup/remote-control.md`.*

Decisions and control commands reach the growth engine one way only. Dispatch connects over SSH,
with a key that can run one program, `bin/growth-remote`, and nothing else. Since 2026-10-29
Dispatch runs on this same Mac, as its own hidden macOS user, `dispatch`, and connects to
`tingy@127.0.0.1`. There is no Tailscale and no second machine. These steps change the Mac's own
security settings and need your admin password, so they are yours to do. The contract Dispatch
follows is `repos/growth/docs/dispatch-contract.md`, and ADR 0004 explains why the route is built
this way.

Below, `<repo>` means the growth repo's full path on this Mac:
`/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth`.

## 1. Get the growth side ready

1. In `<repo>`, run `uv sync`. The forced command runs `<repo>/.venv/bin/jura-growth`, so the
   `.venv` folder must exist.
2. Check that macOS's own Python runs: `/usr/bin/python3 --version` prints 3.9 or later. If it
   offers to install the command line tools, let it.
3. Make sure `CONTROL_DISCORD_USER_ID` in the growth `.env` is your Discord user id (Discord →
   Settings → Advanced → Developer Mode, then right-click your name → Copy User ID). A command
   from any other Discord user is refused.

## 2. Run Dispatch's paste block

Everything that opens the Mac to Dispatch is in one paste block, kept in Dispatch's repo:
`/Users/tingy/discord-dispatch/deploy/SETUP.md`, section "macOS (this Mac)". It is the same block
as §8.9 of `discord-automation/prd/pending/prd-discord-dispatch-growth-control-2026-10-27.md`.
Run it at Dispatch's ticket GC-08, when that section's "Before you paste" is true. It asks for your
admin password once and stops four times along the way.

What it does on growth's side, so you know what to expect:

- It makes two hidden users. `dispatch` runs Dispatch's gateway and worker and holds every key,
  including the growth key, `/Users/dispatch/.dispatch-keys/growth_mac`. `claude-runner` runs
  Dispatch's Claude tasks and their checks. Neither can log in, and neither is an admin.
- It sets `/Users/tingy` to mode 700, so neither of them can read or write `growth.db` or the repo.
- Its step 5 turns on Remote Login for your user only, keys only, with
  `/etc/ssh/sshd_config.d/010-dispatch-growth.conf`. Among other settings, that file has sshd read
  your keys only from `/etc/ssh/authorized_keys.d/tingy`, owned by root, holding one line:

  ```
  restrict,command="/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth/bin/growth-remote",from="127.0.0.1,::1" ssh-ed25519 AAAA… dispatch-growth
  ```

  - `restrict` turns off the terminal, port forwarding and agent forwarding.
  - `command=` runs `bin/growth-remote` whatever Dispatch asks for. What it asked for arrives as
    `SSH_ORIGINAL_COMMAND` and is split into words without a shell.
  - `from=` limits the key to this Mac. Every local program connects from `127.0.0.1`, so here the
    real guard is that only `dispatch` can read the private key.
- It pins this Mac's own host key for Dispatch, so nothing is trusted on first use.
- It ends with `ok:` lines (neither `claude-runner` nor `tingy` can read the growth key) and
  `dispatch growth-check`.

Two things to know:

- sshd no longer reads `~/.ssh/authorized_keys`. That is deliberate: any program running as you
  could write that file and add a key of its own (ADR 0004, "The remaining limit"). If you used a
  key there to reach this Mac from elsewhere, it stops working. Never add a key of your own to
  `/etc/ssh/authorized_keys.d/tingy` either: a second line there would let a program that can read
  that key's secret send control commands.
- Dispatch's growth settings (`growth.ssh` with host `127.0.0.1`, user `tingy`, the key, the pinned
  host key and `/usr/bin/ssh`, and the `#approvals` and `#control` bindings of D1, D2 and D4) come
  from the `dispatcher.yaml` that Dispatch's GC-08 wizard writes. `docs/dispatch-contract.md` has
  the exact command line.

## 3. Check the Mac's side

```bash
ls -l /etc/ssh/authorized_keys.d/tingy
wc -l < /etc/ssh/authorized_keys.d/tingy
cut -c1-150 /etc/ssh/authorized_keys.d/tingy
sudo sshd -T | grep -Ei '^(authorizedkeysfile|passwordauthentication|kbdinteractiveauthentication|permituserenvironment|permittty|allowusers) '
stat -f %Lp /Users/tingy
```

Expect, in order:

1. `-rw-r--r--  1 root  wheel`: the key file belongs to root, so no program running as you can
   change it.
2. `1`: one line, Dispatch's.
3. A line starting `restrict,command="<repo>/bin/growth-remote",from="127.0.0.1,::1" ssh-ed25519`.
4. `authorizedkeysfile /etc/ssh/authorized_keys.d/%u`, `passwordauthentication no`,
   `kbdinteractiveauthentication no`, `permituserenvironment no`, `permittty no` and
   `allowusers tingy`, in whatever order sshd prints them.
5. `700`.

## 4. Check the route (U16)

Run these in Terminal as yourself. Each call goes out as `dispatch`, with the same options
Dispatch uses, so paste this helper first (it asks for your password once):

```bash
G() { sudo -u dispatch -H /usr/bin/ssh -T -F /dev/null -i /Users/dispatch/.dispatch-keys/growth_mac \
  -o IdentitiesOnly=yes -o IdentityAgent=none -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/Users/dispatch/.dispatch-keys/growth_known_hosts \
  -o GlobalKnownHostsFile=/dev/null -- tingy@127.0.0.1 "$@"; echo "exit $?"; }
```

| Run | Expect |
| --- | --- |
| `G '--actor discord:<your id> --json -- status'` | `"ok": true`, exit 0 |
| `G '--actor discord:<your id> -- run social'` | `refused: …`, exit 2 |
| `G '--actor discord:999 -- status'` | `refused: discord:999 isn't the control user.`, exit 2 |
| `G '-- status; touch /tmp/growth-remote-probe'` | `refused: …`, and `/tmp/growth-remote-probe` doesn't exist |
| `G` (no command) | No shell: `refused: this key runs control commands only…` |

While one call runs, a root `sshd` should sit above `jura-growth remote`. To see it, paste this,
which waits for the next call and prints its ancestry, then run `G '--actor discord:<your id> --
status'` straight after:

```bash
( while ! P=$(pgrep -f 'jura-growth remote' | head -1); do sleep 0.05; done
  while [ "${P:-1}" -gt 1 ]; do ps -o user=,pid=,comm= -p "$P"; P=$(ps -o ppid= -p "$P" | tr -d ' '); done ) &
```

Expect a line owned by `root` whose command ends in `sshd` or `sshd-session` above the `tingy`
lines, and no `claude` anywhere.

Now check that nobody else gets in:

| Run | Expect |
| --- | --- |
| `<repo>/.venv/bin/jura-growth remote --actor discord:<your id> -- status` | `refused: decisions come only from Dispatch, through the SSH forced command.` |
| `ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null tingy@127.0.0.1 true` | `Permission denied (publickey)`: no key of yours is accepted and passwords are off |
| `sudo -u claude-runner -H /usr/bin/ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null tingy@127.0.0.1 true` | `Permission denied (publickey)` |
| `sudo -u claude-runner cat /Users/dispatch/.dispatch-keys/growth_mac` and `cat /Users/dispatch/.dispatch-keys/growth_mac` | `Permission denied`, both times |
| The key you add yourself, below | `Permission denied (publickey)` |

A key you add to `~/.ssh/authorized_keys` must be refused. This adds one, tries it, and puts the
file back as it was:

```bash
mkdir -p -m 700 ~/.ssh && touch ~/.ssh/authorized_keys && cp -p ~/.ssh/authorized_keys /tmp/ak.bak
ssh-keygen -q -t ed25519 -N "" -C probe -f /tmp/probe-key && cat /tmp/probe-key.pub >> ~/.ssh/authorized_keys
ssh -F /dev/null -i /tmp/probe-key -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null -- tingy@127.0.0.1 '--actor discord:<your id> -- status'
cp -p /tmp/ak.bak ~/.ssh/authorized_keys && rm -f /tmp/ak.bak /tmp/probe-key /tmp/probe-key.pub
```

Last, `uv run jura-growth log events --kind remote.command` in `<repo>` should show one event for
each call that reached `jura-growth remote`, with the actor, the words and the answer: every `G`
call with a command, and the one typed in Terminal. `G` with no command, and the logins sshd
refused, never reach it, so they leave none.

Then U7 from your phone (ticket 14): `/growth status`, `/growth approvals`, approve one request and
skip another. Then turn Remote Login off (System Settings → General → Sharing), send
`/growth status`, and expect "The growth Mac is unreachable." straight away, with nothing recorded
later. Turn it back on and check that **Only these users** still lists only you. Record each check
as pass or fail in the ticket's QA file.

## Turning it off

Turn Remote Login off, or remove the key line with
`sudo rm /etc/ssh/authorized_keys.d/tingy`. Nothing else depends on it: Dispatch answers that the
growth Mac is unreachable, requests stay pending, and the one-pager lists them. Dispatch's own
services stop with `sudo launchctl bootout system/local.dispatch.gateway` and
`sudo launchctl bootout system/local.dispatch.worker`.
