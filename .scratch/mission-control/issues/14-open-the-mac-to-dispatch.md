# 14 — Ting Yu: open the Mac to Dispatch over SSH and check from the phone

Status: ready-for-human
Blocked by: 11; and, outside this repo, Discord Dispatch deployed with D1 to D4, D8 and D9 (`~/projects/discord-automation/`)
PRD source: MC §4.7 (the transport), §4.8 (D1 to D4, D8, D9), §5.12 ("Live from the phone"); not a §5.12 ticket, because only Ting Yu can do it
Covers: SC10 live; test strategy v3 §7 U16 and U7; `uat.md` Part B (typed commands)

## What to do

Remote Login, the restricted key and Tailscale change the Mac's own security settings, and the key belongs only to Dispatch's gateway, so these steps are Ting Yu's.

1. Follow `outputs/growth/setup/remote-control.md` (drafted in 11, copied there at release): Remote Login on, limited to your user, key authentication only.
2. Add the one `authorized_keys` entry, `restrict,command="<repo>/bin/growth-remote",from="<dispatch tailnet address>" ssh-ed25519 …`. The private key stays on Dispatch's machine, readable only by the gateway's user (D9). Never paste it into a file, a ticket or a chat.
3. Join both machines to Tailscale.
4. In Dispatch, bind `#approvals` and `#control` in Jura HQ to company `jura` only, accepting your user only (D1), with `/growth …` running `jura-growth remote` verbatim (D2) and passing `--actor` and `--ref` (D4).
5. Record each check below as pass or fail in `.scratch/mission-control/reviews/qa-NN.md`.

## Checks

- [ ] **U16.** From Dispatch's machine, a real SSH session through the forced command runs `jura-growth remote -- status`, and a command off the allowlist is refused.
- [ ] **U7.** From your phone: `/growth status`, `/growth approvals`, approve one request, skip another. Then have a second account send `/growth status` in the control channel, and send it yourself from a TaskWise or ZenexFlow channel. Both are refused.
- [ ] With the Mac asleep, `/growth status` answers "the growth Mac is unreachable" straight away, and the request stays pending (MC §4.7).

## Pointers

- PRD: MC §4.7, §4.8, ADR 0004
- `docs/dispatch-contract.md` (from 11)
- `.scratch/mission-control/uat.md` Part B; `.scratch/mission-control/reviews/test-strategy-v3.md` §7 (U16, U7)
