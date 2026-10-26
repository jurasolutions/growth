# Remote control: open the Mac to Dispatch over SSH

*Mission control, ticket 14. About 30 minutes. Drafted in ticket 11; the release copies it to
`outputs/growth/setup/remote-control.md`.*

Decisions and control commands reach the growth engine one way only: Dispatch, on its own always-on
machine, connects to this Mac over SSH with a key that can run one program, `bin/growth-remote`,
and nothing else. These steps change the Mac's own security settings, and the key belongs only to
Dispatch's gateway, so they are yours to do. The contract Dispatch follows is
`repos/growth/docs/dispatch-contract.md`.

Below, `<repo>` means the growth repo's full path on this Mac:
`/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth`.

## 1. Get the Mac ready

1. In `<repo>`, run `uv sync`. The forced command runs `<repo>/.venv/bin/jura-growth`, so the
   `.venv` folder must exist.
2. Check that macOS's own Python runs: `/usr/bin/python3 --version` prints 3.9 or later. If it
   offers to install the command line tools, let it.
3. Make sure `CONTROL_DISCORD_USER_ID` in the growth `.env` is your Discord user id (Discord →
   Settings → Advanced → Developer Mode, then right-click your name → Copy User ID). A command
   from any other Discord user is refused.

## 2. Join both machines to Tailscale

1. Install Tailscale on this Mac and on Dispatch's machine, and sign both in to the same tailnet.
2. Note Dispatch's tailnet address (`tailscale ip -4` on that machine, a `100.x.y.z` address), and
   this Mac's tailnet name or address. The SSH key below works only from Dispatch's address.

## 3. Turn on Remote Login, for your user only, keys only

1. System Settings → General → Sharing → **Remote Login** on. Click the **i** next to it, choose
   **Only these users**, and leave only your own user. Leave "Allow full disk access for remote
   users" **off**.
2. Turn off password logins. Create `/etc/ssh/sshd_config.d/100-jura-growth.conf` (you'll need
   `sudo`) with:

   ```
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   PermitRootLogin no
   AuthenticationMethods publickey
   ```

3. Turn Remote Login off and on again so the file is read.

## 4. Make Dispatch's key, on Dispatch's machine

As **the gateway's user** on Dispatch's machine (never the `run_as` user its Claude tasks run as):

```
ssh-keygen -t ed25519 -f ~/.ssh/growth_mac -C dispatch-growth -N ""
chmod 600 ~/.ssh/growth_mac
```

The private key `~/.ssh/growth_mac` never leaves that machine. Don't copy it into a file, a ticket
or a chat. Check that the `run_as` user can't read it (D9): as that user, `cat` the file should be
refused.

## 5. Add the one `authorized_keys` entry, on this Mac

Copy only the **public** key (`~/.ssh/growth_mac.pub` on Dispatch's machine) and add it to
`~/.ssh/authorized_keys` on this Mac as one line, with the options in front:

```
restrict,command="/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth/bin/growth-remote",from="100.x.y.z" ssh-ed25519 AAAA… dispatch-growth
```

- `restrict` turns off the terminal, port forwarding and agent forwarding.
- `command=` runs `bin/growth-remote` whatever Dispatch asks for. What it asked for arrives as
  `SSH_ORIGINAL_COMMAND` and is split into words without a shell.
- `from=` is Dispatch's tailnet address from step 2.

This entry must be the only one in the file. Any other key in it, including your own, would let a
program on this Mac that can read that key's secret log in to `localhost` and send control
commands (ADR 0004, "The remaining limit"). Then:

```
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

## 6. Point Dispatch at the Mac

In Dispatch's config, for company `jura` only: the host (this Mac's tailnet name), the user (yours)
and the key file (`~/.ssh/growth_mac`). Bind `#approvals` and `#control` in Jura HQ to `jura`,
accepting your user only (D1), with `/growth …` running `jura-growth remote` verbatim (D2) and
passing `--actor` and `--ref` (D4). `docs/dispatch-contract.md` has the exact command line.

## 7. Check it (U16)

From Dispatch's machine, as the gateway's user:

| Run | Expect |
| --- | --- |
| `ssh -i ~/.ssh/growth_mac <mac> -- --actor discord:<your id> --json -- status` | `"ok": true`, exit 0 |
| `ssh -i ~/.ssh/growth_mac <mac> -- --actor discord:<your id> -- run social` | `refused: …`, exit 2 |
| `ssh -i ~/.ssh/growth_mac <mac> -- --actor discord:999 -- status` | `refused: discord:999 isn't the control user.`, exit 2 |
| `ssh -i ~/.ssh/growth_mac <mac> '-- status; touch /tmp/growth-remote-probe'` | `refused: …`, and on the Mac `/tmp/growth-remote-probe` doesn't exist |
| `ssh -t -i ~/.ssh/growth_mac <mac>` | No shell: `refused: this key runs control commands only…` |

On this Mac:

| Run | Expect |
| --- | --- |
| `jura-growth remote --actor discord:<your id> -- status` in Terminal | `refused: decisions come only from Dispatch, through the SSH forced command.` |
| `ssh localhost` | Refused: no key of yours is accepted and passwords are off |
| `jura-growth log events --kind remote.command` | One event per call above, with the actor and the words |

Then U7 from your phone (ticket 14): `/growth status`, `/growth approvals`, approve one request and
skip another. Record each check as pass or fail in the ticket's QA file.

## Turning it off

Remove the line from `~/.ssh/authorized_keys`, or turn Remote Login off. Nothing else depends on
it: requests stay pending and the one-pager lists them.
