# The growth and Dispatch contract

How Discord Dispatch sends control commands to the growth engine on Ting Yu's Mac, and what comes
back. This is the one interface another system calls, so it is versioned: every `--json` answer
carries `"contract": 1`. Fields are only ever added. A field never changes its meaning, and an
answer never changes its exit code.

Sources: `prd-jura-mission-control-2026-10-25.md` §4.6 to §4.8 and §5.10, ADR 0004, and the code
in `jura_growth/remote.py` and `bin/growth-remote`. Tests in `tests/test_remote.py` check that the
two tables below match the code.

## Transport

- Dispatch reaches the Mac only over SSH, with a forced command, over Tailscale. Dispatch never
  runs on the Mac.
- The Mac has Remote Login on, limited to Ting Yu's user, with key authentication only. Its
  `authorized_keys` holds one entry, for Dispatch's key:

  ```
  restrict,command="<repo>/bin/growth-remote",from="<dispatch tailnet address>" ssh-ed25519 AAAA… dispatch-growth
  ```

- On Dispatch's machine, the private key is readable only by the gateway's user. The `run_as` user
  that Dispatch's Claude tasks run as can never read it (D9).
- Dispatch builds the command line with Python's `shlex.join`: the options, then `--`, then Ting
  Yu's text split on whitespace, each word quoted. `bin/growth-remote` undoes that with
  `shlex.split`, which only parses quotes and runs nothing. No shell sees the words, so a note with
  `;`, `$(…)`, backticks or an apostrophe arrives exactly as typed.

  ```python
  words = ["--actor", f"discord:{user_id}", "--ref", f"{message_id}:{delivery_id}", "--json", "--", *text.split()]
  subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "growth-mac", shlex.join(words)],
                 capture_output=True, text=True, timeout=60)
  ```

- Dispatch passes Ting Yu's text verbatim. No model rewrites a control command (Dispatch hard rule
  6, "original words win").
- If `ssh` can't connect (the Mac is asleep or off), Dispatch answers "the growth Mac is
  unreachable" straight away. It never holds a decision for later. It may retry within its
  60-second window with the same `--ref`, which makes the retry safe.

## Grammar

```
jura-growth remote --actor discord:<id> [--ref <message id>:<delivery id>] [--json] -- <command…>
```

- `--actor` is the Discord user who sent the command. It is attribution, recorded on every
  decision and every `remote.command` event. It must be `discord:<CONTROL_DISCORD_USER_ID>`, or the
  command is refused. That check is for consistency only: the guard is the SSH key, the forced
  command and Dispatch's own user allowlist (SEC-1).
- `--ref` is Dispatch's delivery reference, the Discord message id and Dispatch's delivery id. Send
  it on every `approve` and `skip`. The same ref twice records the decision once, and the second
  call answers exactly what the first did, with exit 0. It is recorded on every other command's
  event too.
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
| `apps built <APP-NNN> --task <T-nnnn> --branch <branch> --sha <sha> --preview <url>` | `apps built` | Dispatch calls it when a build task ships (D6): the task, its branch based on `main`, the branch's full head SHA and its Cloudflare Pages preview. Raises an `app-release` request in `#approvals` bound to that SHA. Each option once, as `--task T-0031` or `--task=T-0031`, in any order. Exit 1 for a build that wasn't handed off, or a value it can't bind (a short SHA, a preview outside the landing page's Pages project) |
| `apps handoffs` | `apps handoffs` | What Dispatch polls (D6). `--json` adds `handoff`, below. A handoff stays listed until `apps built` reports it |
| `apps release-plan <APP-NNN>` | `apps release-plan` | Claims the approved `app-release` request, then answers with the merge of exactly the approved SHA into `main`, for Ting Yu to run (later Dispatch D7). Exit 1, with nothing to run, when no approved release is waiting. A second call never gives the merge again |
| `apps released <APP-NNN> --task <T-nnnn>` | `apps released` | Records the release once `main` of the landing-page repository holds the claimed SHA, and moves the PRD to `prd/done/apps/`. Exit 1 while the release isn't claimed or `main` lacks the SHA |
| `community removed <group-id>` | `community removed` | |
| `one-pager` | `one-pager` | Posts the one-pager to `#mission-control` with the 14-day grid, dedupe off: asked twice, it posts twice. Exit 0 and `recorded` either way, like `heartbeat`: the text says "posted to #mission-control", or "not posted to #mission-control: <why>" when Discord didn't take it and it waits in the outbox, which the next one-pager lists under Needs you. Read the text, not the exit code, to tell them apart |
| `outreach requeue-shadow [--since YYYY-MM-DD] [--dry-run]` | `outreach requeue-shadow` | Live mode only; each requeued email raises its own approval request. Exit 1 in shadow mode |
| `pause <agent\|all> [reason]` | `pause` | The rest of the words are the reason; "paused from Discord" without one |
| `resume <agent\|all>` | `resume` | With a PAUSE file present, the answer says it can only be removed on the Mac |
| `skip <A-nnnn> [note]` | `skip` | Answers from the enum below. Allowed until the request is claimed |
| `social skip <date> <platform>` | `social skip` | Today or tomorrow |
| `status` | `status` | |

Ticket 09 added `one-pager` and ticket 12 the four `apps` commands. Browser publishing's ticket 03
adds `publish queue` and `publish resolve`, as rows of their own in this order.

## Answers and exit codes

Every answer is one of seven. For `approve` and `skip`, each answer has exactly one exit code.

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
  PRD's exact bytes as UTF-8: its SHA-256 is `prd_sha256`, which Dispatch may check. It is not
  masked, so it is for the task's brief, never for posting to Discord; `text` is what to post. An
  entry whose `handoff` is `null` carries a `problem` instead (the PRD changed after it was
  approved, can't be read, or is too large for one answer) and is not to be built. `more` counts
  handoffs that didn't fit in this answer; they come on a later poll, once the earlier ones are
  reported built. A handoff stays listed on every poll until `apps built` reports it, so Dispatch
  keys its tasks on `approval` and starts one task for each.

The whole answer is at most 64 KB. Listed requests are dropped from the end to keep it there, and
so are handoffs, each counted in `more`. A lone handoff too large to fit keeps its entry with
`handoff: null` and a `problem`.

## Buttons

When `approvals.post_buttons` is on, each card in `#approvals` carries two buttons, sent through a
webhook the Dispatch application owns (`DISCORD_WEBHOOK_APPROVALS`). Their `custom_id`s are
`growth:approve:A-nnnn` and `growth:skip:A-nnnn`. Dispatch turns a click into `approve A-nnnn` or
`skip A-nnnn`, with the clicking user as `--actor` and the interaction as `--ref`. Cards for kinds
that need typed arguments, such as `group-rules`, never carry buttons; Ting Yu types
`/growth approve A-nnnn promo_days=… post_days=…`. A card loses its buttons when it is decided,
lapses, is superseded or is claimed.

## What Dispatch provides

| # | Dispatch must provide |
| --- | --- |
| D1 | `#approvals` and a `#control` channel in Jura HQ, bound to company `jura` only, accepting Ting Yu's user only (SEC-1). Growth commands are never reachable from other companies' channels. Growth never posts in `#control` |
| D2 | A deterministic command path: `/growth <command…>` (or a plain message in `#control`) runs `jura-growth remote` with the text verbatim. No triage, no `claude -p`, no Ollama |
| D3 | The SSH transport above, answering within 60 seconds, and "the growth Mac is unreachable" when it can't connect |
| D4 | The acting Discord user id as `--actor discord:<id>`, and `--ref <message id>:<delivery id>` on every decision |
| D5 | Approve and Skip buttons on each card in `#approvals`, mapped as above, through a webhook the Dispatch application owns. Until then, typed `/growth approve A-nnnn` works |
| D6 | Build handoffs from `apps handoffs --json` (ticket 12), each a Dispatch task based on `main` with the approved PRD text as its brief, verbatim; `apps built …` when it ships |
| D7 | (Later, a Dispatch PRD amendment.) Promotion of exactly the SHA `apps release-plan --json` hands out, refusing if the branch head moved |
| D8 | Deployment: the always-on machine, the bot, Tailscale, and `landing-page` onboarded with Cloudflare Pages branch previews |
| D9 | The SSH private key readable only by the gateway's user, never by the `run_as` user its Claude tasks run as (a SEC-3 extension) |

## Examples

```
$ ssh growth-mac -- --actor discord:111 --ref 1234567890:dlv-77 --json -- approve A-0412
{"contract": 1, "ok": true, "answer": "recorded", "exit_code": 0, "text": "A-0412 approved."}

$ ssh growth-mac -- --actor discord:111 --json -- run social
{"contract": 1, "ok": false, "answer": "refused", "exit_code": 2, "text": "refused: `run social` isn't a control command. Send one of: …"}
```
