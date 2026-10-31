# The growth and Dispatch contract

How Discord Dispatch sends control commands to the growth engine on Ting Yu's Mac, and what comes
back. This is the one interface another system calls, so it is versioned: every `--json` answer
carries `"contract": 1`. Fields are only ever added. A field never changes its meaning, and an
answer never changes its exit code.

Sources: `prd-jura-mission-control-2026-10-25.md` §4.6 to §4.8 and §5.10, §8 of the Dispatch
growth-control PRD (Dispatch on this Mac, 2026-10-29), ADR 0004, and the code in
`jura_growth/remote.py` and `bin/growth-remote`. Tests in `tests/test_remote.py` check that the two
tables below match the code.

## Transport

- Dispatch runs on the same Mac, as its own hidden macOS user, `dispatch` (Ting Yu, 2026-10-29;
  §8 of the Dispatch growth-control PRD). It reaches growth only over SSH to `127.0.0.1`, with a
  forced command. There is no Tailscale and no second machine. Only the hop changed, so the
  contract version did not.
- The Mac has Remote Login on, limited to Ting Yu's user (`AllowUsers tingy`), with key
  authentication only. sshd reads his keys only from `/etc/ssh/authorized_keys.d/tingy`, owned by
  root, never from `~/.ssh/authorized_keys`. That file holds one entry, for Dispatch's key:

  ```
  restrict,command="<repo>/bin/growth-remote",from="127.0.0.1,::1" ssh-ed25519 AAAA… dispatch-growth
  ```

- The private key is `/Users/dispatch/.dispatch-keys/growth_mac`, readable only by `dispatch`. The
  `run_as` user that Dispatch's Claude tasks and checks run as, `claude-runner`, can never read it
  (D9), and neither can Ting Yu's own user, `tingy`, which the growth engine and his Claude
  sessions run as. The host key is pinned from the Mac's own `/etc/ssh/ssh_host_ed25519_key.pub`.
- Dispatch builds the command line with Python's `shlex.join`: the options, then `--`, then Ting
  Yu's text split on whitespace, each word quoted. `bin/growth-remote` undoes that with
  `shlex.split`, which only parses quotes and runs nothing. No shell sees the words, so a note with
  `;`, `$(…)`, backticks or an apostrophe arrives exactly as typed. The exact `ssh` argv is AC-D3.1
  of the Dispatch PRD, as amended 2026-10-30; it ends `-- tingy@127.0.0.1 <shlex.join(words)>`, so
  ssh can never read Ting Yu's words as its own options.

  ```python
  words = ["--actor", f"discord:{user_id}", "--ref", f"{source_id}:{delivery_id}", "--json", "--", *text.split()]
  argv = ["/usr/bin/ssh", "-T", "-F", "/dev/null", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
          "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=yes",
          "-o", f"UserKnownHostsFile={pinned}", "-o", "GlobalKnownHostsFile=/dev/null",
          "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes", "-p", "22",
          "--", "tingy@127.0.0.1", shlex.join(words)]
  subprocess.run(argv, capture_output=True, text=True, timeout=60, env=only_path_home_and_locale)
  ```

- Dispatch passes Ting Yu's text verbatim. No model rewrites a control command (Dispatch hard rule
  6, "original words win").
- If `ssh` can't connect (Remote Login is off, or sshd is down), Dispatch answers "the growth Mac
  is unreachable" straight away. It never holds a decision for later. It may retry within its
  60-second window with the same `--ref`, which makes the retry safe. When the Mac itself is off,
  Dispatch is off with it, and Discord shows its own "The application did not respond".

## Grammar

```
jura-growth remote --actor discord:<id> [--ref <source id>:<delivery id>] [--json] -- <command…>
```

- `--actor` is the Discord user who sent the command. It is attribution, recorded on every
  decision and every `remote.command` event. It must be `discord:<CONTROL_DISCORD_USER_ID>`, or the
  command is refused. That check is for consistency only: the guard is the SSH key, the forced
  command and Dispatch's own user allowlist (SEC-1).
- `--ref` is Dispatch's delivery reference, `<source id>:<delivery id>`. The source is the Discord
  message id for a plain message in `#control`, the interaction id for a `/growth` slash command,
  and the card's message id for a button click. The delivery id is Dispatch's own row id for that
  delivery, unchanged across its retries. Polls send `poll:<delivery id>`, and `apps built` sends
  `built:<task id>:<delivery id>`. Growth reads it as opaque text. Send it on every `approve` and
  `skip`. The same ref twice records the decision once, and the second call answers exactly what
  the first did, with exit 0. It is recorded on every other command's event too.
- `--json` asks for the JSON answer below instead of plain text. The exit code is the same either
  way.
- Everything after `--` is the command, as Ting Yu typed it. Options after the first command word
  belong to the command, never to `remote`.
- The origin is checked before anything runs: `SSH_ORIGINAL_COMMAND` is set, a root `sshd` process
  is an ancestor, and no ancestor is Claude Code and none of its environment markers is set. The
  process also refuses whenever a scheduled run's `JURA_GROWTH_JOB` is set.

## Commands

The allowlist, in the same order as `ALLOWLIST` in `jura_growth/remote.py`. Anything else exits 2
with a line starting `refused:`. That includes `run`, `schedule`, `discord`, `db`, `backup`,
`check`, `suppression`, `social render` and every command that takes a file path. Words in angle
brackets are required; words in square brackets are optional.

| Command | Runs | Notes |
| --- | --- | --- |
| `approvals [kind]` | `approvals` | The 15 soonest to lapse, then "and N more". `--json` adds `approvals` |
| `approve <A-nnnn> [key=value …] [note]` | `approve` | Answers from the enum below. Leading `key=value` words are the kind's arguments (`group-rules`: `promo_days=… post_days=…`); the rest is a note |
| `apps built <APP-NNN> --task <T-nnnn> --branch <b> --sha <sha> --preview <url>` | `apps built` | Dispatch calls it when a build task ships (D6): the task, its branch based on `main`, the branch's full head SHA and its Cloudflare Pages preview. Raises an `app-release` request in `#approvals` bound to that SHA. Each option once, as `--task T-0031` or `--task=T-0031`, in any order. Exit 1 for a build that wasn't handed off, or a value it can't bind (a short SHA, a preview outside the landing page's Pages project) |
| `apps handoffs` | `apps handoffs` | What Dispatch polls (D6). `--json` adds `handoff`, below. A handoff stays listed until `apps built` reports it |
| `apps idea <text>` | `apps idea` | Adds Ting Yu's own toolbox idea to the app backlog, the text verbatim, with `source: ting-yu`; the app factory picks his ideas before any other, oldest first. The name is the text before a first `: ` (a colon and a space), else its first few words, at most 60 characters; it needs Latin letters, since it becomes the tool's web address. No approval: it writes only the backlog row, and the PRD and both build decisions still apply. The answer shows the text, or its first 1,000 characters and its length when it is longer, so it never needs cutting. Exit 2 for no text, more than 2,000 characters (a Discord message's own limit), no Latin letters in the name or a word that reads as an option (`--source`, `-x`); exit 1, with the text starting `not added:` and naming the clash, when the name or slug matches anything live, pending, built or already in the backlog. Exit 1, with the text starting `refused: the backlog is busy`, when another writer holds the backlog for 30 seconds; nothing is written, so send it again. Not retry-safe: a resend that did land answers exit 1 as a duplicate. No scheduled run can send it |
| `apps release-plan <APP-NNN>` | `apps release-plan` | Claims the approved `app-release` request, then answers with the merge of exactly the approved SHA into `main`, for Ting Yu to run on the Mac. The claim is spent once it runs. A retry while the build is still the claimed commit and preview answers with the same merge and makes no new claim, so a lost answer can be fetched again; the merge names a fixed SHA, so it releases nothing new. Exit 1, with nothing to run, when no approved release is waiting, or when the build moved on from the claimed commit |
| `apps released <APP-NNN> --task <T-nnnn>` | `apps released` | Records the release once `main` of the landing-page repository holds the claimed SHA, and moves the PRD to `prd/done/apps/`. Exit 1 while the release isn't claimed or `main` lacks the SHA |
| `community removed <group-id>` | `community removed` | |
| `help` | `help` | Lists every command on this allowlist, built from `ALLOWLIST`, each with its usage and a one-line summary. Always fits the 1,900 characters with no cut. Exit 2 for any word after it. No scheduled run can send it |
| `one-pager` | `one-pager` | Posts the morning picture to `#mission-control` with a short message, dedupe off: asked twice, it posts twice. Exit 0 and `recorded` either way, like `heartbeat`: the text says "posted to #mission-control", or "not posted to #mission-control: <why>" when Discord didn't take it and it waits in the outbox, which the next one-pager lists under Needs you. Read the text, not the exit code, to tell them apart |
| `outreach requeue-shadow [--since YYYY-MM-DD] [--dry-run]` | `outreach requeue-shadow` | Live mode only; each requeued email raises its own approval request. Exit 1 in shadow mode |
| `pause <agent\|all> [reason]` | `pause` | The rest of the words are the reason; "paused from Discord" without one |
| `pending` | `pending` | Growth's unfinished work under "Waiting for you" and "Growth is on it", most urgent first, each with what to send next. Read-only: it writes no row but its own `remote.command` event, and takes no lock. Exit 0 and `recorded` even when something couldn't be read: the text then starts with "Couldn't be read" and never says "Nothing pending", so read the text, as for `one-pager`. A long answer is cut from the end, so what growth holds gives way first. Exit 2 for any word after it. No scheduled run can send it |
| `publish queue` | `publish queue` | Every publish item with its `P-nnnn` label, its A-id, platform, day and state |
| `publish resolve <A-nnnn> posted --url <url> \| not-posted` | `publish resolve` | Settles an item whose outcome is `unknown`. `posted` needs the live post's URL (`--url <url>` or `--url=<url>`) on the platform's own host, or exits 1. It records no decision. A scheduled run can never send it |
| `resume <agent\|all>` | `resume` | With a PAUSE file present, the answer says it can only be removed on the Mac |
| `skip <A-nnnn> [note]` | `skip` | Answers from the enum below. Allowed until the request is claimed |
| `social skip <date> <platform>` | `social skip` | Today or tomorrow |
| `status` | `status` | |

Ticket 09 added `one-pager` and ticket 12 the four `apps` commands. Browser publishing's ticket 03
adds `publish queue` and `publish resolve`, as rows of their own in this order. `apps idea` came
on 2026-10-31; Dispatch passes `/growth` text through unfiltered, so it needs no change to send
it. The growth-help-pending feature's ticket 01 added `help` and `pending` the same way, on the same
date, and Dispatch needs no change for them either.

## Answers and exit codes

Every answer is one of seven. For `approve` and `skip`, each answer has exactly one exit code, with
one exception: `refused` with exit 1, below.

| Answer | Exit code | Meaning |
| --- | --- | --- |
| `recorded` | 0 | The decision is recorded, or the command ran |
| `expired` | 3 | The request passed its decide-by (or, approved, its use-by) before this arrived. Growth's own clock decides, not Discord's |
| `superseded` | 4 | What would go out changed or went away; the text names the request that replaced it, if any |
| `already-decided` | 5 | Ting Yu already approved or skipped it |
| `already-used` | 6 | It was approved and claimed; nothing can undo it |
| `unknown-id` | 7 | No request has that id. Only `A-nnnn` names a request |
| `refused` | 2 | Nothing was done: not the Dispatch origin, not the control user, not on the allowlist, missing `key=value` arguments, or a command growth didn't understand |

Commands other than `approve` and `skip` answer `recorded` with exit 0 when they ran, and
`refused` with exit 2 when `remote` refused them (`one-pager` answers exit 0 even when Discord
didn't take the post; see its row). Exit 1 means the command ran and reported a problem of its
own (for example `outreach requeue-shadow` before live sending is ready, `community removed`
for a group that doesn't exist, or `apps release-plan` with no approved release). Its answer is
`refused` and `ok` is false. Read `exit_code` to tell the two refusals apart.

An `approve` or `skip` can also answer `refused` with exit 1. It means growth failed while running
the decision, for example an unexpected error inside the command, whose text starts `failed:` and
names it. That is a valid answer, not a malformed one. Dispatch posts growth's `text`, masked and
defused like any other, and doesn't retry it. The decision may have been recorded before the
failure, so check `/growth approvals` before sending it again. A resend carries a new `--ref`, so
if the first attempt did record the decision, the resend answers `already-decided`. For `approve`
and `skip`, any other answer with exit 1 is malformed. This is how growth has always behaved
(`jura_growth/remote.py`, `handle`); it is written down here after Dispatch's code review GC-03,
and the contract version is unchanged.

## The JSON answer

```json
{"contract": 1, "ok": true, "answer": "recorded", "exit_code": 0, "text": "A-0412 approved.", "approvals": [ … ]}
```

- `contract`: always 1 for this version.
- `ok`: true exactly when `exit_code` is 0.
- `answer`: one of the seven above.
- `exit_code`: the process's exit code.
- `text`: what to post back to Ting Yu, at most 1,900 characters, with secrets and personal data
  masked and mentions defused. A longer answer is cut at a line, with a "(cut: N more lines)" note.
- `approvals` (only from `approvals`): the requests listed, each
  `{"id": "A-0412", "kind": "outreach-email", "decide_by": "2026-11-10T16:30:00+08:00", "title": "…", "args": []}`.
  A request whose `args` is not empty needs them typed (`group-rules`), so it gets no buttons.
- `handoff` (only from `apps handoffs`): the build handoffs waiting for a builder, oldest first,
  as `jura-growth apps handoffs --json` prints them on the Mac (Dispatch sends `--json` to
  `remote`, never to `apps handoffs`):

  ```json
  {"contract": 1, "more": 0, "handoffs": [
    {"app_id": "APP-014", "name": "PayNow QR maker", "prd_path": "prd/pending/apps/prd-app-014-paynow-qr-2026-11-09.md",
     "approval": "A-0412", "approval_at": "2026-11-10T10:02:15+08:00", "handed_off_at": "2026-11-10T10:02:15+08:00",
     "handoff": {"repo": "landing-page", "base": "main", "prd_text": "…", "prd_sha256": "…", "approval": "A-0412"}}]}
  ```

  Dispatch starts one task per entry, against `handoff.repo` on its own branch based on
  `handoff.base`, with `handoff.prd_text` as the brief, verbatim (D6). `prd_text` is the approved
  PRD's exact bytes as UTF-8, and its SHA-256 is always `prd_sha256`: growth checks that before it
  answers. It is not masked, so it is for the task's brief only, never for posting to Discord;
  `text` is what to post. The factory refuses a PRD that holds anything the privacy filter would
  mask, so none should reach a brief.

  An entry whose `handoff` is `null` carries a `problem` instead and is not to be built: the PRD
  changed after it was approved, can't be read, holds a secret-looking value (printing would mask
  it, so the text wouldn't be the approved bytes), or is too large for one answer. Such an entry
  holds up no other. `more` counts handoffs that didn't fit beside the ones in this answer; they
  come on a later poll, once the earlier ones are reported built. A handoff stays listed on every
  poll until `apps built` reports it, so Dispatch keys its tasks on `approval` and starts one task
  for each.

The whole answer is at most 64 KB, measured as compact JSON in UTF-8. Listed requests are dropped
from the end to keep it there. `apps handoffs --json` on the Mac keeps its handoffs within 52 KB,
leaving 12 KB for this answer's other fields, so what it hands out always fits here.

## Buttons

When `approvals.post_buttons` is on, each card in `#approvals` carries two buttons, sent through a
webhook the Dispatch application owns (`DISCORD_WEBHOOK_APPROVALS`). Their `custom_id`s are
`growth:approve:A-nnnn` and `growth:skip:A-nnnn`. Dispatch turns a click into `approve A-nnnn` or
`skip A-nnnn`, with the clicking user as `--actor` and `<card message id>:<delivery id>` as `--ref`:
the source is the card's message id, not the interaction's (Dispatch AC-D4.2 and AC-D5.2). Each
click is its own delivery, so a second click on the same card carries a new ref and answers
`already-decided`. Cards for kinds
that need typed arguments, such as `group-rules`, never carry buttons; Ting Yu types
`/growth approve A-nnnn promo_days=… post_days=…`. A card loses its buttons when it is decided,
lapses, is superseded or is claimed.

## What Dispatch provides

| # | Dispatch must provide |
| --- | --- |
| D1 | `#approvals` and a `#control` channel in Jura HQ, bound to company `jura` only, accepting Ting Yu's user only (SEC-1). Growth commands are never reachable from other companies' channels. Growth never posts in `#control` |
| D2 | A deterministic command path: `/growth <command…>` (or a plain message in `#control`) runs `jura-growth remote` with the text verbatim. No triage, no `claude -p`, no Ollama |
| D3 | The SSH transport above, to `127.0.0.1`, answering within 60 seconds, and "the growth Mac is unreachable" when it can't connect |
| D4 | The acting Discord user id as `--actor discord:<id>`, and `--ref <source id>:<delivery id>` on every call, as under Grammar |
| D5 | Approve and Skip buttons on each card in `#approvals`, mapped as above, through a webhook the Dispatch application owns. Until then, typed `/growth approve A-nnnn` works |
| D6 | Build handoffs from `apps handoffs` with `--json` (ticket 12), each a Dispatch task based on `main` with the approved PRD text as its brief, verbatim. `prd_text` is for the brief only, never posted to Discord. `apps built …` when it ships |
| D7 | (Later, a Dispatch PRD amendment.) Promotion of exactly the SHA `apps release-plan --json` hands out, refusing if the branch head moved |
| D8 | Deployment on this Mac as the `dispatch` user (two LaunchDaemons), the bot, the loopback SSH transport, and `landing-page` onboarded with Cloudflare Pages branch previews (Dispatch PRD §8, amended 2026-10-29) |
| D9 | The SSH private key readable only by the gateway's user (`dispatch`), never by the `run_as` user its Claude tasks run as (`claude-runner`), nor by Ting Yu's own user (`tingy`) (a SEC-3 extension) |

## Examples

```
$ ssh <Dispatch's options> -- tingy@127.0.0.1 '--actor discord:111 --ref 1234567890:dlv-77 --json -- approve A-0412'
{"contract": 1, "ok": true, "answer": "recorded", "exit_code": 0, "text": "A-0412 approved."}

$ ssh <Dispatch's options> -- tingy@127.0.0.1 '--actor discord:111 --json -- run social'
{"contract": 1, "ok": false, "answer": "refused", "exit_code": 2, "text": "refused: `run social` isn't a control command. Send one of: …"}
```
