# 14 — Ting Yu: open the Mac to Dispatch over SSH and check from the phone

Status: ready-for-human
Blocked by: 11; and, outside this repo, Discord Dispatch deployed with D1 to D4, D8 and D9 (`~/projects/discord-automation/`)
PRD source: MC §4.7 (the transport), §4.8 (D1 to D4, D8, D9), §5.12 ("Live from the phone"); not a §5.12 ticket, because only Ting Yu can do it
Covers: SC10 live; test strategy v3 §7 U16 and U7; `uat.md` Part B (typed commands)

## What to do

*Revised 2026-10-30: Dispatch runs on this Mac as its own hidden `dispatch` user and connects to
`tingy@127.0.0.1` (Ting Yu, 2026-10-29; Dispatch growth-control PRD §8). No Tailscale, no second
machine.*

Remote Login, the restricted key and the two new macOS users change the Mac's own security
settings and need the admin password, so these steps are Ting Yu's.

1. Follow `outputs/growth/setup/remote-control.md` (drafted in 11, rewritten for this Mac on
   2026-10-30, copied there at release). Its §2 points to Dispatch's one paste block
   (`/Users/tingy/discord-dispatch/deploy/SETUP.md`, "macOS (this Mac)"), run at Dispatch's
   ticket GC-08. The block turns on Remote Login for your user only, keys only, and writes the one
   root-owned key line, `restrict,command="<repo>/bin/growth-remote",from="127.0.0.1,::1"
   ssh-ed25519 …`, to `/etc/ssh/authorized_keys.d/tingy`. The private key stays in
   `/Users/dispatch/.dispatch-keys/`, readable only by `dispatch` (D9). Never paste it into a file,
   a ticket or a chat.
2. In Dispatch, bind `#approvals` and `#control` in Jura HQ to company `jura` only, accepting your
   user only (D1), with `/growth …` running `jura-growth remote` verbatim (D2) and passing
   `--actor` and `--ref` (D4). Dispatch's GC-08 wizard writes these into `dispatcher.yaml`.
3. Record each check below as pass or fail in `.scratch/mission-control/reviews/qa-NN.md`.

## Checks

- [ ] **U16.** As `dispatch`, a real SSH session to `127.0.0.1` through the forced command runs
  `jura-growth remote -- status`, and a command off the allowlist is refused (`remote-control.md`
  §3 and §4).
- [ ] **U7.** From your phone: `/growth status`, `/growth approvals`, approve one request, skip another. Then have a second account send `/growth status` in the control channel, and send it yourself from a TaskWise or ZenexFlow channel. Both are refused.
- [ ] With Remote Login off, `/growth status` answers "The growth Mac is unreachable." straight away, and the request stays pending (MC §4.7). This replaces the asleep-Mac check: this Mac never sleeps, and when it is off Dispatch is off with it.

## Pointers

- PRD: MC §4.7, §4.8, ADR 0004
- `docs/dispatch-contract.md` (from 11)
- `.scratch/mission-control/uat.md` Part B; `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U16, U7)
