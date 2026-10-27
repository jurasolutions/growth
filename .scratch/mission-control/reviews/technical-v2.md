# Mission control and browser publishing: technical review (v2)

Tech lead, 2026-10-25. This review covers two coupled PRDs:

- **MC**: `jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md` (the Discord rewrite)
- **BP**: `jurasolutions/prd/pending/prd-jura-browser-publishing-2026-10-25.md`

I read them against the code on `crew/growth-blocker-fixes` at `dacf740`, the Chrome spike
(`.scratch/browser-publishing/spike-headless-chrome.md`), my v1 review (`reviews/technical.md`),
and the Dispatch PRD (`~/projects/discord-automation/prd/pending/prd-discord-dispatch-2026-09-19.md`).
Terms follow `CONTEXT.md`. Design terms follow mattpocock `codebase-design`: module, interface,
depth, seam, adapter.

## Verdict

Both approaches are sound. Approvals as a core module that plug-ins declare kinds against, one
inbound entry point, the read-only read model, and `--chrome` for a single job are all the right
shape. Before sign-off the two PRDs need eight changes (B1 to B8). Three of them are
contradictions between the PRDs, and one would stop the 08:00 one-pager from ever running. Each
finding has a fix, and none of them changes the scope Ting Yu asked for.

The central change is B1. "Use the approval in the same transaction as the action" can't hold
when the action is a Resend call, a click in Chrome or a Dispatch build. The approval has to be
used, meaning claimed, at the point of no return, before the outward effect.

## Evidence

- `uv run pytest` was run against a `git archive` of `crew/growth-blocker-fixes` in the
  scratchpad, with the repo's `.venv` and `PYTHONPATH` pointed at the archive: **975 passed in
  21.28s**. `git status` in the repo was unchanged afterwards apart from the untracked crew
  files.
- A probe on the same archive showed that a command job is refused its own command once that
  command is in `NEVER`. `may_use("heartbeat", "heartbeat")` returns `True`, then `False` after
  `heartbeat` is added to `NEVER`. That is B6.
- `git log --merges crew/growth-blocker-fixes` shows all eight blocker fixes merged, with 07 as
  `dacf740`. None of them is on `main`, which is at `6eabfe7`.
- The Dispatch PRD says Dispatch runs on Linux or WSL2 under systemd (§5, SEC-3). Its tasks run
  `claude -p --permission-mode auto --permission-prompts none` (FR-E3). Merging `dev` into
  `main` is a v1 non-goal (§3).

## What carries over from v1

| v1 item | Status under the Discord scope |
|---|---|
| B1 raw file route | Moot (no web page) |
| B2 Keychain masking | Carried faithfully as `config.load_secrets_for_masking()` (MC §4.3) |
| B3 one source per record kind | Carried faithfully (MC §4.5) |
| B4 dependency status | Still stale, see N11 |
| N2 real start stamp, N3 holiday skips, N4 never take a lock | Carried faithfully (MC §4.5) |
| N5 install-state adapter, N6 plug-in setup gaps, N13 `digest.spend()` | Carried (MC §5.2) |
| N15 `NEVER` gains the viewer command | Mis-carried: it now names `one-pager`, a scheduled job (B6) |
| ADR 0001 and 0002 | Still right. Text below, unchanged |

## Blocking findings

### B1. Use the approval before the outward effect, not after it

**Where:** MC §4.6 ("in the same transaction as the action's own write"), §5.4 step 4, §5.5
("`approvals.use` runs in the transaction that marks the message sent, after Resend accepts
it"). BP §5.5 (claim).

**Problem.**

- Resend, Chrome and Dispatch are outside SQLite, so no transaction can contain them. In the
  order MC §5.5 gives, Resend accepts the email first and `use()` runs afterwards. If `use()`
  then refuses, the email has already gone out with no valid approval and SC4 is false. It can
  refuse because the request expired at 16:30 while the slot ran, because it was revoked, or
  because the hash doesn't match.
- There is also no transaction to join today. `db.connect()` opens with
  `isolation_level=None`, and `_send_one` and `_mark_sent` are separate autocommit statements.
- BP already has the right model, because a claim counts against the cap whatever happens next.
  MC doesn't.

**Fix (MC §4.6, §5.4, §5.5; BP §5.4, §5.5):**

- `approvals.use(conn, kind, subject, run_id)` is **the claim**. It runs inside a
  `db.transaction(conn)` (`BEGIN IMMEDIATE`) before the outward effect. In that transaction it
  re-reads the record and recomputes the item's current content hash through the kind (N3). It
  refuses unless the record is approved, unexpired, unused and matching, then sets `used_at` and
  `used_by_run`. The caller writes its in-flight marker in the same transaction:
  `publish_items.state = 'claimed'`, or `outreach_messages.attempts`.
- The outward call comes next. The completion write (mark sent, `publish done`) is its own
  transaction keyed on the same subject. It never re-checks expiry, because the claim already
  decided.
- **One approval authorises one action instance (one subject).** A retry of that same instance
  is not a second use:
  - Outreach retries the same message id under the existing `Idempotency-Key:
    jura-outreach-<id>`, so a crash between Resend and `_mark_sent` resolves itself next slot.
  - Publish never retries. A claim with no close becomes `unknown` (BP §5.5, unchanged).
- **Handoff kinds** (`app-build`, `app-release`): the gated write is the handoff row, so `use()`
  runs in the transaction that writes it. Only that transaction's answer is returned to Dispatch
  (N5).
- ADR 0003 below records this.

### B2. A decision needs a human origin, not just an unset variable

**Where:** MC §4.6 ("refuses them whenever `JURA_GROWTH_JOB` is set"; the
`CONTROL_DISCORD_USER_ID` check), §4.7. BP §4.2.

**Problem.**

- `JURA_GROWTH_JOB` is a label that the runner sets. Any agent process on the Mac runs without
  it:
  - an interactive Claude Code session in `repos/growth`, crew agents included;
  - Dispatch's own `--permission-mode auto` tasks, if Dispatch is ever co-located (B3);
  - a headless run that gets past its Bash rules.
- `--actor discord:<id>` is asserted by the caller, so matching it against
  `CONTROL_DISCORD_USER_ID` proves nothing about who is calling.
- The injection path is credible. Publish reads Facebook pages, and app-factory writes PRDs from
  web research that then become Dispatch briefs. A process that can run
  `jura-growth remote --actor discord:<Ting Yu> -- approve A-0412` approves its own item.
- Ticket 01's allowlist and `NEVER` are still needed, but they are only the first two layers.

**Fix (MC §4.6, §4.7, ADR 0004):**

- Add one adapter, `origin.py`, which returns `Origin.terminal`, `Origin.ssh` or
  `Origin.refused(reason)`. `decide()` and `remote` take it as an injectable parameter, so tests
  pass a fake.
  - **Terminal** (`approve`, `skip`): stdin and stdout are TTYs, and Ting Yu types the first six
    hex characters of the request's content hash, shown in the card and by `approvals`. Claude
    Code's Bash tool has no TTY, so no agent session can decide, headless or interactive.
  - **Remote** (`jura-growth remote`): the process descends from `sshd`, `SSH_ORIGINAL_COMMAND`
    is set, and it is reached through the forced-command wrapper (B3). No process on the Mac can
    give itself an `sshd` ancestor. The private key lives only on Dispatch's machine.
  - Both refuse if any ancestor process is `claude`. This is cheap (`ps -o ppid=,comm=`
    walked up), and it closes the case where Ting Yu runs `! jura-growth approve` inside a Claude
    session.
- Keep `NEVER` (`approve`, `skip`, `approvals`, `remote`) and the `JURA_GROWTH_JOB` refusal as
  layers 1 and 2.
- Treat the Discord user id as **attribution**, recorded in `decided_by`. Authentication is the
  SSH key plus Dispatch's SEC-1 allowlist. Keep the `CONTROL_DISCORD_USER_ID` comparison as a
  cheap consistency check, and say in the PRD that it is not the guard.
- Tests: decide refuses for each fake origin that isn't allowed, with `JURA_GROWTH_JOB` set, and
  with a fake `claude` ancestor. It succeeds for a TTY with the right code and for an ssh origin.

### B3. The two PRDs give different transports; pick SSH

**Where:** MC §6 Q14 recommends SSH forced command from Dispatch's always-on machine. BP §5.3
item 5 and §6 Q3 recommend running Dispatch's approval handler on the Mac.

**Problem.**

- Dispatch is built for Linux or WSL2 with systemd and a dedicated sandbox user (Dispatch §5,
  SEC-3).
- Its tasks are autonomous Claude sessions in `auto` permission mode. Putting Dispatch on the
  Mac puts those sessions next to `jura-growth`, which is exactly the B2 hole.
- The D6 app build would run on the Mac too, with the factory's model-written PRD as its brief.

**Fix:**

- Both PRDs adopt MC Q14, hardened:
  - The `authorized_keys` entry is
    `restrict,command="<repo>/bin/growth-remote",from="<dispatch host>" ssh-ed25519 …`.
  - `bin/growth-remote` passes `SSH_ORIGINAL_COMMAND` to `jura-growth remote` as one argument
    and never through a shell.
  - Key authentication only. Remote Login is limited to Ting Yu's user.
  - The Mac and Dispatch's machine reach each other over Tailscale, or another private link, not
    the open internet.
- On Dispatch's machine the private key is readable only by the gateway's user, never by the
  `run_as` user its Claude tasks run as (a Dispatch SEC-3 extension, new item D9).
- BP §5.3 item 5 and §6 Q3 change to "through the MC transport".
- If the Mac is asleep, `ssh` fails with a connection timeout. Dispatch then answers "the growth
  Mac is unreachable" (D3) and retries decisions idempotently by `source_ref` (B4).

### B4. One approval model across both PRDs

**Where:** BP §5.2 (`P-0042` ids), §5.3 (decision fields, "a skip after an approval wins if no
run has claimed the item"), §5.4 (`publish_items.state` includes `awaiting`, `approved`,
`skipped`, `expired`, and the `publish_decisions` fallback), §5.8 (approver id in
`config/publish.yaml`). MC §4.6 (decide only when pending), §5.4.

**Problem.** As drafted there are two state machines for the same decision, two ids for Ting Yu
to type, two places the approver id is configured, and two contradictory rules on skipping after
an approval. Duplicated state drifts, and drift here means a post goes out on a stale yes.

**Fix:**

- **Approval state lives only in `approvals`.** `publish_items` keeps only the item's lifecycle:
  `ready`, `claimed`, `posted`, `stopped`, `unknown`, `withdrawn`. "Awaiting", "approved",
  "skipped" and "expired" are read from its approval (subject `publish_item:<id>`). Drop
  `publish_decisions`.
- **Ting Yu types only `A-nnnn`.** `P-nnnn` can stay as an internal label in `publish queue`,
  but it never appears in a command.
- **Revocation (adopt BP's rule in MC).** `skip` is allowed on an approved record until `use()`
  claims it. The MC §4.6 trigger allows `approved -> skipped` only while `used_at IS NULL`, and
  refuses any change once `used_at` is set.
- **Idempotent delivery (adopt BP's `source_ref` in MC).** `decide()` takes
  `source_ref` (the Discord message id and the Dispatch delivery id). A unique index on
  `(approval_id, source_ref)` means a retried delivery returns the first answer. `remote` gains
  `--ref`.
- **Answers are an enum.** `recorded`, `expired`, `superseded`, `already-decided`,
  `already-used`, `unknown-id`, `refused`. `--json` returns it, and `docs/dispatch-contract.md`
  lists one exit code for each.
- **One approver id:** `CONTROL_DISCORD_USER_ID` (MC). Remove it from BP §5.8.

### B5. Email approvals expire before the caps let them go

**Where:** MC §5.3 (`outreach-email` expiry: 16:30 on the next business day after the request),
§5.5, §6 Q9 and Q11.

**Problem.**

- **Warm-up.** Week 1 allows 5 emails a day (`caps.warmup_cap`). If Ting Yu approves 20, 15 of
  them expire and are cancelled.
- **`requeue-shadow`.** It creates every requeued email at once, with `send_after` today (see
  `requeue.py:111`). Each raises a request, so a trial of a few dozen shadow emails floods
  `#approvals`, and most of those requests expire.
- **Follow-ups.** They are queued with `send_after` several business days ahead (`queue.py:195`).
  A request raised at queue time expires before the email is ever due.
- **Random spacing.** `send.py:280` sets the probability from `len(due())`. If unapproved emails
  are counted, the day's sends bunch up and approved ones get crowded out.
- **The approved but unsent case is undefined.** MC's expiry action is written for pending
  requests. A yes that the caps never got to fall into a gap: `use()` refuses it and nothing
  cancels the message.

**Fix (MC §5.3, §5.5; the specific numbers are a question for Ting Yu, below):**

- **Raise requests only for emails due today** (`send_after <= today`), and only up to today's
  remaining live quota (`send.quota()`), counting pending and approved-but-unused requests
  already open. The first `send-due` of the day tops the pile up, and so do `queue()` and
  `requeue-shadow`. Everything else stays queued with no request until its day.
- **Two clocks:**
  - `decide_by`: a pending request expires at 16:30 on the next business day, and the message is
    cancelled ("not approved in time").
  - `use_by`: an approved request stays usable until 16:30 on the third business day after it
    was approved. After that the message is cancelled ("approved but the limits didn't reach
    it"), and the one-pager lists it.
- **`due(conn, approved_only=True)` in live mode** feeds both "nothing queued" and the spacing
  probability, so spacing spreads only what can actually go out.
- **Shadow mode** raises nothing and uses nothing. An approved message that is shadow-sent
  (because the mode was switched back) keeps its approval unused, and `use_by` retires it.
- **The live-mode guard moves into the prefactor.** "approval gate not installed" in
  `live_problems()` lands in the first ticket, not the outreach-gate ticket. That way both `live`
  and `requeue-shadow` refuse from the day the PRD is signed off (`requeue.py:85` already calls
  `live_problems()`).

### B6. `one-pager` in `NEVER` refuses the 08:00 job

**Where:** MC §5.2 table, `headless.py` row ("NEVER gains … `one-pager` (N15)"), and the
`one-pager` job (command kind, 08:00).

**Problem.** `_run_command` sets `JURA_GROWTH_JOB`, and `may_use()` checks `NEVER` before the
job's own command (`headless.py:69`; probed above). The scheduled one-pager would exit with
"refused" every morning, which breaks SC1. My v1 N15 was about the web server command, which no
job ran.

**Fix:** leave `one-pager` out of `NEVER`. It reads, then posts only to `#mission-control`,
which is harmless. Claude jobs still can't call it, because default-deny covers them. `NEVER`
gains `approve`, `skip`, `approvals` and `remote` only. Add a test that every scheduled command
job's own command passes `may_use`, so this mistake can't recur.

### B7. The `group-rules` kind conflicts with ticket 07

**Where:** MC §5.3 (`group-rules`: hash over group id and rules text; Approve sets
`rules_confirmed = yes`), §5.2 previews ("the parsed days (`rules.parse(...).summary()`)").

**Problem.**

- After ticket 07, setting `rules_confirmed=1` raises unless `promo_days_confirmed` and
  `post_days_confirmed` are both set (`groups._check_days_confirmed`). Its docstring says "code
  never reads days out of the rules text". A one-tap Approve carries no days, so it either
  fails, or it reintroduces code-read days, which 07 removed on purpose.
- `community set <id> rules_confirmed=yes` from Terminal stays a second path that bypasses the
  kind. SC4's "a test per approval kind proves the refusal" can't pass while it exists.

**Fix:**

- The `group-rules` decision takes required arguments: `approve A-nnnn promo_days=<days>
  post_days=<days>`, parsed with `rules.read_days()`. The `remote` grammar accepts them, and
  this kind gets no button (D5).
- The hash covers the group id and the rules text. The days are part of the decision record and
  are written by the approve action through `groups.set_fields`.
- The preview shows the rules text only. Showing parsed days would invite approving the code's
  reading.
- `community set … rules_confirmed=yes` creates and decides a `group-rules` approval in one step
  with the Terminal origin (B2), so every confirmation has an approval record and the audit holds.

### B8. Scope the Chrome tools by domain, and give `--chrome` to one job only

**Where:** BP §5.6. Spike §1 and §4.

**Problem.**

- BP §5.6 allows `navigate`, `find`, `read_page`, `get_page_text`, `computer`, `form_input`,
  `file_upload` and `upload_image` **by tool name**. A tool-name allow permits that tool on every
  site.
- The spike showed that `ClaudeInChromeDomain(<host>)` alone allows the page tools on that host.
  The domain rule is the scope, and adding tool-name allows widens it to the whole web,
  including the Gmail or bank tabs of whichever profile is connected.
- BP doesn't mention `browser_batch` or `resize_window`, which the spike found in the tool list.
- BP still offers "an `--mcp-config` file … or Claude Code's own Chrome flag". The spike settled
  it: only `--chrome` works for `-p`.
- Nothing stops another job from setting `browser: true` in `settings.yaml`.

**Fix (BP §5.6, §5.9 block 0 and block 2):**

- `--allowedTools` for the publish job gets the tab tools by name (`tabs_context_mcp`,
  `tabs_create_mcp`, `tabs_close_mcp`, `list_connected_browsers`) and
  `ClaudeInChromeDomain(<host>)` for each host in the plug-in's host list. No page tool is
  allowed by name.
- Deny these by name: `javascript_tool`, `read_network_requests`, `read_console_messages`,
  `shortcuts_execute`, `shortcuts_list`, `gif_creator`, `switch_browser`, `select_browser` and
  `browser_batch`. Deny `file_upload` on days with no image.
- `runner.claude_command` appends `--chrome` only when the job's name is in a code constant,
  `caps.BROWSER_JOBS = frozenset({"publish"})`. It raises `JobError` if any other job sets
  `browser: true`. Tests check that every job's argv except `publish` lacks `--chrome` and
  contains no `ClaudeInChromeDomain` rule.
- **Gate block 2 on three checks by Ting Yu** (spike setup items 1 to 3):
  - an unlisted domain is denied;
  - the locked-screen run works;
  - the Chrome-closed run ends without hanging.

  Record the results in BP §6 Q1 before any social host goes into a rule.
- Domain rule coverage of subdomains (`www.`, `m.`, `business.facebook.com`, `static.xx.fbcdn.net`
  for images) is unverified. The same check confirms it, and the host list names each host
  explicitly until then.

## Non-blocking findings

Each one is applied in the ticket named in the build order.

- **N1. Expiry and the read-only read model (MC-08).** MC §5.4 says `expire_due()` runs "on
  every read". The one-pager's read model is `mode=ro` (MC §4.2), so it can't write.
  - The read model shows a pending request past `decide_by` as "expired" without writing.
  - The real transition runs in `decide`, `use`, the noon heartbeat, and the one-pager job's own
    writable connection before it builds. `use()` refuses an expired record whether or not the
    transition has run.
- **N2. Post requests after commit, by a sweep (MC-04).**
  - `approvals` gains `posted_at`. `approvals.post_unposted(conn)` runs at the end of every
    command that raised requests, and again at the heartbeat.
  - A crash between commit and post never loses a card. The one-pager lists unposted requests.
  - This matches the post-after-commit pattern of `49e365c`.
- **N3. Let the kind compute the hash, and supersede lazily (MC-04).**
  - The `ApprovalKind` method `content(conn, subject) -> bytes | None` returns the canonical
    bytes of what would go out now: UTF-8, NFC-normalised, as JSON with sorted keys. `None`
    means the item is gone.
  - `request`, `use` and every read compare that hash with the record's hash. On a mismatch or
    `None` they mark the record superseded. This replaces hooking every cancellation call site
    (`store.cancel_queued`, `send._skip`, `sync`, `replies`).
  - The outreach content is the recipient address of the contact row the send will use
    (`queue.recipient()`), the subject and `draft_body`.
  - An unknown kind fails closed. `agents.plugins()` skips a plug-in that fails to import, and
    then `use()` refuses and `expire_due()` leaves the record alone.
- **N4. Outreach details (MC-06).**
  - **Skip:** the message is cancelled and the lead is set to a new final status,
    `declined_by_ty`, added to `FINAL_LEAD_STATUSES`.
  - **Expiry:** the message is cancelled and the lead stays re-queueable only after
    `config/scout.yaml`'s cool-off. That stops the same company being offered every morning.
  - The preview masks a named-person recipient (MC §4.4), but the hash covers the full address.
- **N5. Handoff kinds (MC-10).**
  - The `app-release` hash must cover the **commit SHA** being promoted, not just the task id
    and preview URL. Otherwise commits pushed to `dev` after approval ride along. D7 promotes
    exactly that SHA, and refuses if it isn't on `dev`.
  - The handoff `--json` carries the PRD text and its sha256, not just a path. Dispatch's machine
    can't read the Mac's OneDrive path.
  - The 1,900-character cap applies to `text` only. The JSON payload has its own limit, for
    example 64 KB.
- **N6. Buttons need an application-owned webhook (MC-11, D5); verify this.** As I understand
  Discord's rules, interactive buttons can't go on messages posted through an ordinary channel
  webhook. They need a webhook created by the Dispatch application, and the clicks are delivered
  to that application.
  - If that holds, Dispatch creates the `#approvals` webhook and Ting Yu stores it as
    `DISCORD_WEBHOOK_APPROVALS`.
  - `discord._send` gains an optional `components` payload (`?with_components=true`).
  - Until then, typed commands only, as MC Q7 already allows.
- **N7. Run updates (MC-01, MC-03).**
  - No run update for a PAUSE-file skip (`runner.py:67`). The PAUSE file is the brake that needs
    no network, and the one-pager shows it.
  - The `run_update` hook may return `None` to post nothing. Publish uses that and posts only
    when it claimed an item (BP §5.7).
  - Introduce **one** runner post-run hook in the prefactor: `after_run(conn, job, run_id,
    outcome) -> Outcome`, called after `finish_run` and wrapped so its errors never change auto-pause. Run updates
    use it (MC), and so do publish's settle-unclosed-claims and host audit (BP). That way
    `runner.py` changes once.
- **N8. The publish job must not start Claude to find nothing (BP-03).**
  - At 09:00 to 18:00 every 15 minutes, that is 36 `claude -p` starts a day. The spike's empty
    probe cost about US$0.08, so roughly US$2.80 a day goes on "nothing due".
  - The publish plug-in's `precheck()` runs the claim query read-only and skips with "nothing
    due". The run then leaves a quiet `run.skipped` event.
  - The prompt checks the browser (`tabs_context_mcp`) **before** `publish next`. A closed Chrome
    then ends `SKIP:` without a claim, instead of leaving an `unknown` item and pausing.
  - `after_run` recognises the no-browser outcome and alerts once a day (BP §4.9).
- **N9. What the publish run can read and record (BP-03).**
  - Drop `--add-dir JURA_ROOT` for the browser job. `publish next` copies the item's images into
    the scratch folder, so a prompt injected through a group page can't read and then type out
    other Jura files.
  - The host audit reads the tab URL in every tool result through `transcripts.read()`, not only
    the inputs of `navigate`, because a click can change the page without a `navigate`.
  - Publish transcripts hold third-party page text (members' names and posts). Keep them 7 days,
    not 30, and never quote page text in run updates.
- **N10. Auth condition (BP-03).** The publish `precheck()` skips with a clear reason when
  `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` is in the environment. Without that, the
  Chrome tools would vanish silently (spike §1).
- **N11. Dependency text is stale (both PRDs).** All eight blocker fixes are merged on
  `crew/growth-blocker-fixes` (`dacf740`, ticket 07 last). MC §4.8 omits 02 and cites `4a7859e`.
  BP §5.9's "02 and 07 merged" is now true on the branch, but not on `main`.
- **N12. Discord details (MC-02, MC-09).**
  - `discord.post()` redacts the content before `content_hash()`, so dedupe sees what was sent.
  - The on-request one-pager posts with `dedupe=False`. Otherwise a second request with the same
    text is answered "posted" and nothing appears.
- **N13. Personal names in email previews (MC §4.4, Q4).** The rule says "never a prospect's
  personal name", but it also allows "the text of Jura's own outgoing emails". A draft that
  greets a person by name breaks one rule or the other. Recommended: the preview shows the draft
  as it will go out, and the scout prompt keeps greetings to the company, so the conflict never
  arises. A test plants a greeting name and asserts it is masked.
- **N14. "Marked expired in Discord" (BP §5.1).** Growth only posts through webhooks. Either
  store the message id (`?wait=true`) and edit the card, or post a one-line follow-up.
  Recommended: post a follow-up, which keeps growth write-only.
- **N15. Gap against schedule (BP Q12).** A 20-minute floor between browser actions with
  15-minute slots means every other slot finds the gap closed. Schedule the job every 20 minutes
  instead.

## Seams

**One new seam: the `approvals` module's interface.** It is a deep module. Callers name a kind
and a subject. The module owns the hash, the state machine, expiry, the audit events, posting
and supersede, and callers never pass a hash they computed themselves.

```python
class ApprovalKind(Protocol):            # declared by plug-ins via approval_kinds()
    name: str
    def content(self, conn, subject: str) -> bytes | None: ...   # what would go out now; None = gone
    def preview(self, conn, subject: str) -> Preview: ...         # text, files (max 10), title, reason
    def deadlines(self, conn, subject: str, now: datetime) -> Deadlines: ...  # decide_by, use_by
    def on_skip(self, conn, subject: str) -> None: ...
    def on_expire(self, conn, subject: str) -> None: ...
    decision_args: tuple[str, ...] = ()   # ("promo_days", "post_days") for group-rules

request(conn, kind, subject, *, reason, run_id) -> Approval        # dedupes / supersedes
decide(conn, approval_id, decision, *, actor, origin, source_ref, args) -> Answer
use(conn, kind, subject, *, run_id) -> Approval                    # inside caller's BEGIN IMMEDIATE; raises NotApproved
expire_due(conn, now) -> list[Approval]
post_unposted(conn) -> int
pending(conn) -> list[Approval]; get(conn, approval_id) -> Approval | None
```

Tests cross this seam directly, against a temp database from `db.migrate` and a fake kind. One
test per real kind proves the gated action refuses without a used approval.

Existing seams that are extended, with no new seam:

- **The plug-in protocol** (`agents/__init__.py`) gains `approval_kinds()`, `run_update()` and
  `after_run()`, discovered with `getattr` the way `digest()` and `permissions()` are.
- **The read model** (`mission.py`), carried from v1, serves only the one-pager now.

Adapters, each with a real and a fake implementation:

- **`origin.py`** (B2). The real version checks the TTY and the process ancestry. Tests pass
  fixed origins.
- **`jura-growth remote`** is a thin adapter over the CLI. It is tested with click's
  `CliRunner`, a fake origin, and the 1,900-character cap.
- **The fake `claude` binary.** `settings.claude.binary` already lets a test point the runner at
  a script that writes a canned stream-json transcript. The publish job's unknown-claim, host
  audit and no-browser paths are tested through it with no Chrome. Only Ting Yu's block 2 check
  touches real Chrome.

The existing seams carry the rest: Discord off writes to the outbox (`JURA_GROWTH_DISCORD=off`);
`send.resend_client()` and `send.chance()`; `JURA_GROWTH_NOW`; `config._keychain`; the
`conftest.py` path overrides and `WriteGuard`; `runner.claude_command` argv tests; and
`transcripts.read()`.

## Blast radius

| Area | Change | PRD |
|---|---|---|
| `jura_growth/approvals.py`, `origin.py`, `privacy.py`, `remote.py`, `run_update.py` | New | MC |
| `jura_growth/mission.py`, `slots.py`, `health.py`, `one_pager.py` | New (read model and one-pager) | MC |
| `jura_growth/migrations/0003_approvals.sql` | New core table, indexes, transition trigger, unique `(approval_id, source_ref)` | MC |
| `jura_growth/runner.py` | `run.quiet` and the real start stamp; one `after_run` hook (MC). `--chrome` for `BROWSER_JOBS` only (BP) | both |
| `jura_growth/headless.py` | `NEVER` gains `approve`, `skip`, `approvals`, `remote` | MC |
| `jura_growth/caps.py` | `BROWSER_JOBS`, `COMMUNITY_POSTS_PER_DAY`, `COMMUNITY_JOINS_PER_WEEK`, `PUBLISH_ITEMS_PER_RUN`, `PUBLISH_MINUTES_BETWEEN_ACTIONS`, `PUBLISH_WINDOW` | BP |
| `jura_growth/config.py`, `log.py`, `digest.py`, `discord.py`, `cli.py` | Additive: masking loader, `start_run(started_at=)`, `spend()`, redact before hashing (and later `components`), new commands, heartbeat calls `expire_due` and `post_unposted` | MC |
| `jura_growth/agents/__init__.py` | Docstring for the three new optional hooks | MC |
| `agents/outreach/queue.py`, `send.py`, `requeue.py`, `store.py` | Kind, quota-bounded requests, claim before Resend, `due(approved_only=)`, `live_problems` guard, new final lead status | MC |
| `agents/apps/*` (plus a plug-in migration for `app_builds`) | `app-build` and `app-release` kinds, handoff, `apps built`, `apps released`, `prd/skipped/apps/` | MC |
| `agents/community/__init__.py`, `groups.py` | `group-rules` kind with days; `set rules_confirmed` goes through approvals; `propose-join` added to the run's permissions | MC, BP |
| `agents/social/settings.py`, `submit.py` | `publish_mode` takes `draft` or `browser` (`auto` removed); `submit` creates publish items | BP |
| `agents/publish/` (new plug-in and migration `publish_items`) | Items, the three kinds, `publish *` commands, precheck, `after_run` settle and audit | BP |
| `config/settings.yaml`, `social.yaml`, `community.yaml`, `scout.yaml` | Channels `mission-control` and `approvals`; jobs `one-pager` and `publish`; `run_update` flags; expiry settings (lower only) | both |
| `prompts/publish.md`, `docs/dispatch-contract.md`, `bin/growth-remote` | New | both |
| `docs/social.md`, `docs/community.md`, `docs/adr/0001`–`0005`, `CONTEXT.md` | Updated or new | both |
| `outputs/growth/setup/discord.md`, `morning-brief.md`, `browser-publishing.md` | Setup guides | both |
| Data | New tables only. `events` gains the kinds `run.quiet`, `approval.*` and `remote.command`; existing readers filter by kind (v1). No column is dropped | both |
| Outside the repo (Ting Yu and Dispatch) | Remote Login and `authorized_keys` on the Mac; Tailscale; Dispatch D1 to D9; a dedicated Chrome profile; `landing-page` `dev` branch | both |

**No wide refactor.** Supersede-by-content (N3) avoids touching every cancellation site. The new
`due()` keyword has two call sites in one file. Removing `publish_mode: auto` is one expand and
contract inside one ticket, because every platform is set to `draft` today
(`config/social.yaml:83,92,102`).

## Risks

| Risk | Mitigation |
|---|---|
| A self-approval by an agent process | B2's origin guard on top of `NEVER` and `JURA_GROWTH_JOB`; SSH-only remote (B3) |
| A send or post on a stale yes | Claim at the point of no return, recomputing the hash inside `BEGIN IMMEDIATE` (B1, N3) |
| Rollback re-enables unapproved sending: reverting the outreach-gate merge restores a `send.py` with no gate | Release checklist: set `mode: shadow` before any rollback past MC-06. The guard ticket MC-01 stays, so a partial revert still refuses live |
| SQLite contention: an SSH `remote` decision against scout-send's claim | Both use `BEGIN IMMEDIATE` with a 30s busy timeout; remote holds a short connection; Dispatch has 60 seconds (D3) |
| Remote Login opens `sshd` on the Mac | Key only, `restrict` and forced command, `from=`, Tailscale; the wrapper never invokes a shell |
| A prompt injection from a page the publish run reads | Domain rules only (B8), no `--add-dir` (N9), the live-text match, the host audit over tool results, and stop signals that pause the agent |
| The wrong Chrome profile: `--chrome` auto-connects to "the last-picked extension", which Ting Yu's own interactive use can change | A dedicated profile; the prompt's first step checks `list_connected_browsers` and the page identity; question 5 below. No code-level pin exists |
| Account restriction on Meta or LinkedIn | Accepted by Ting Yu (BP §4.1); caps and gaps in `caps.py`; any stop signal pauses publishing |
| Cost of empty publish runs | Code precheck (N8) |
| Discord buttons may need an app-owned webhook | Typed commands from day one (N6) |
| A broken plug-in drops its kinds | Unknown kinds fail closed (N3) |
| Personal data in Discord and transcripts | `privacy.for_discord`; shorter publish transcript retention (N9) |

## Build order across both PRDs

The precondition for everything: the blocker fixes reach `main` through their G4 (MC Q20).
Tickets are cut so that each fits one context window. **MC-nn** and **BP-nn** are proposed ticket
ids. Every edge listed is a real blocking edge.

| Ticket | Contents | Blocked by |
|---|---|---|
| **MC-01** prefactor: runner and guards | `run.quiet` with the real start (v1 N2); `log.start_run(started_at=)`; the `after_run` hook (N7); `NEVER` additions (B6); the `live_problems()` guard "approval gate not installed" (B5); the test that scheduled jobs pass `may_use` | main |
| **MC-02** prefactor: redaction | `config.load_secrets_for_masking()`; `privacy.for_discord()`; redact inside `discord.post()` before hashing (N12) | main |
| **MC-03** run updates | `run_update.py` through `after_run`, the four plug-ins, the skip rules (N7) | MC-01, MC-02 |
| **MC-04** approvals core | `0003_approvals.sql`, `approvals.py`, `origin.py`, Terminal `approvals`/`approve`/`skip` with the typed code, revocation, `source_ref`, `posted_at` sweep, heartbeat expiry, `#approvals` channel | MC-01, MC-02 |
| **MC-05** `group-rules` kind | Days in the decision; `community set` through approvals (B7) | MC-04 |
| **MC-06** outreach gate | The kind, quota-bounded requests, `decide_by`/`use_by`, claim before Resend, `due(approved_only=)`, requeue, removal of the guard (B5, N4) | MC-04 |
| **MC-07** slot classifier | Pure `slots.classify` and its table tests (v1 B3, N3) | MC-01 |
| **MC-08** read model and one-pager text | `mission.py`, `health.py`, the one-pager text, approvals section (N1) | MC-07, MC-04 |
| **MC-09** one-pager PNG, job and guides | The grid PNG, the 08:00 job, the setup guides, retiring the morning-brief line | MC-08 |
| **MC-10** app-factory kinds | `app-build`, `app-release`, `app_builds`, handoff JSON, `apps built`/`released`, `prd/skipped/apps/` (N5) | MC-04 |
| **MC-11a** `remote` core | `remote.py`, `bin/growth-remote`, the allowlist, `--json`, `--ref`, `docs/dispatch-contract.md` | MC-04 |
| **MC-11b** `remote` apps commands | `apps built`/`released` in the allowlist | MC-11a, MC-10 |
| **BP-01** setup and checks | `outputs/growth/setup/browser-publishing.md`; Ting Yu runs spike items 1 to 4 (B8) | none (human) |
| **BP-02** publish queue, no browser | `agents/publish/`, `publish_items`, item creation, the three kinds, `publish next/done/stopped/queue/resolve`, caps, kill switches, `unknown` via `after_run` | MC-04, MC-01 |
| **BP-03** browser job, Facebook Page | `--chrome` for `BROWSER_JOBS`, domain rules, precheck, prompt, host audit, run updates (B8, N8 to N10) | BP-02, BP-01, MC-03 |
| **BP-04** Instagram and LinkedIn | Including carousel days | BP-03 |
| **BP-05** community posts | Confirmed days only | BP-03, MC-05 |
| **BP-06** joins | `propose-join`, two-step questions, `note-rules` | BP-03, MC-05 |

**Parallel lanes:**

- MC-01 and MC-02 run together.
- After them, MC-03, MC-04 and MC-07 run together.
- After MC-04, these four can run in parallel: MC-05, MC-06, MC-10 and BP-02. They touch
  outreach, apps, community and the new publish plug-in plus social submit, so they share no
  files.
- `runner.py` changes only in MC-01 and BP-03, in that order, so there are no merge fights.

**Mapping to the PRDs' blocks:**

- MC block 0 becomes MC-01 and MC-02.
- MC block 2 is now cut as MC-07 to MC-09 and needs MC-04 for its approvals section. This is a
  change to MC §5.8, which says block 2 needs block 0 only.
- BP blocks 1 to 5 become BP-02 to BP-06.

**Live from the phone** needs MC-11a plus Dispatch D1 to D5 and D9. Until then every kind is
approved from Terminal (MC Q8), and outreach stays in shadow mode until MC-06.

## Answers to MC §6

1. **When the one-pager posts.** Agree: 08:00, and the 17:30 digest stays. The 08:00 job must
   not be in `NEVER` (B6).
2. **Text or embeds.** Agree: text plus one PNG.
3. **Channels.** Agree: `#mission-control` and `#approvals`. Dispatch's `#control` is Dispatch's
   own channel; growth never posts there.
4. **Personal data.** Agree with the §4.4 rule, plus N13 (greetings) and N9 (publish
   transcripts).
5. **scout-send and scout-sync run updates.** Agree: none.
6. **Run updates for skips.** Agree for the four agents, except a PAUSE-file skip (N7).
7. **Buttons or typed commands.** Typed first. Buttons probably need a Dispatch-owned webhook
   (N6), and `group-rules` never gets one (B7).
8. **Approving from Terminal.** Yes, recorded as `terminal:<user>`, with a TTY and the typed hash
   code (B2).
9. **Expiry per kind.** Change emails to the two clocks and the quota bound in B5. Apps 7 days and
   group rules 14 days: agree.
10. **Batch approval.** Agree: no in v1. B5 holds the pile to one day's quota (20 at most), so
    one decision per email stays manageable.
11. **Shadow mode.** Agree. The live guard moves into MC-01 (B5).
12. **Where an approved app is pushed.** Agree: to `dev` as a preview, with production a second
    approval. The release hash binds the commit SHA, and D7 promotes exactly that SHA (N5). Ting
    Yu merges by hand until Dispatch is amended.
13. **Skipped app PRDs.** Agree with `prd/skipped/apps/`. It adds a folder that the
    `jurasolutions/CLAUDE.md` PRD workflow doesn't list, so the business analyst updates that
    file's folder map at sign-off.
14. **Transport.** Agree: SSH forced command, hardened as in B3. BP Q3 is withdrawn.
15. **Where the control channel lives.** Agree: the Dispatch bot joins Jura HQ, and `#approvals`
    and `#control` are bound to company `jura`.
16. **Slot status "due".** Agree.
17. **The scout-send cell.** Agree; it is the order from v1.
18. **An unloaded job with history.** Agree.
19. **Removing PAUSE from Discord.** Agree: no.
20. **Wait for main or stack.** Wait. All eight fixes are now merged on the branch (`dacf740`),
    so its G4 is the only gate left.
21. **Notifications.** Agree: notify on every message in `#approvals`; no mentions.

## Answers to BP §6

1. **Can `claude -p` drive Chrome?** Yes, with conditions (the spike): `--chrome`, an OAuth
   login, Chrome running, one chosen profile. Block 2 waits for Ting Yu's three checks (B8).
2. **Who owns approvals.** MC, entirely. `publish_items` holds no approval state, and
   `publish_decisions` is dropped (B4).
3. **Transport.** Not Dispatch on the Mac. Use MC's SSH forced command (B3).
4. **Expiry.** Agree: 18:00 on the item's day. The claim is the last moment expiry is checked
   (B1), so a claim at 17:59 completes.
5. **First platform.** Agree: the Facebook Page.
6. **Joins per week.** Agree: 3, as `caps.COMMUNITY_JOINS_PER_WEEK`.
7. **Other platforms.** Agree: none in this build.
8. **Editing from Discord.** Agree: approve or skip only.
9. **Batch approval.** Agree: no.
10. **Identity in groups.** Agree: Ting Yu personally. This is functional, and the account risk
    falls on his personal profile (BP §4.1).
11. **`join_status = member` sets `joined`.** Agree, but only from `publish done` on a join item
    whose page showed membership. A pending request sets `requested`.
12. **Window and gap.** 09:00 to 18:00 and one item per run: agree. Schedule every 20 minutes to
    match the gap (N15).
13. **Glossary.** `CONTEXT.md` already has Approval request, Approval kind and Gated action. Add
    **Publish item** and **Stop signal**, and add **Claim** ("using an approval at the point of
    no return"). A separate "Approval" entry isn't needed.

## ADR drafts

`docs/adr/` doesn't exist yet. The builder creates it in MC-01, and each ADR is written in the
ticket named.

**`0001-quiet-runs-leave-an-event-not-a-run-row.md`** (MC-01). Unchanged from v1.

**`0002-the-read-model-never-repairs-growth-db.md`** (MC-08). Unchanged from v1, with "page" read
as "one-pager".

**`0003-an-approval-binds-to-content-and-is-claimed-once.md`** (MC-04)

> # An approval binds to content and is claimed once, before the effect
>
> Every outward action (an email, a post, a group join, an app build or release) needs an
> approval record whose content hash matches what will go out now, as computed by the kind's
> own `content()`. The gated action claims the approval with `approvals.use()` inside a
> `BEGIN IMMEDIATE` transaction **before** the effect, because Resend, Chrome and Dispatch sit
> outside SQLite. The claim is the point of no return: a skip is allowed until then, and expiry
> is never re-checked after it. One approval covers one action instance. Its own retries (the
> same outreach message under the same idempotency key) aren't a second use. Approval state
> lives only in the `approvals` table, so plug-in tables hold their item's lifecycle and never a
> copy of the decision. Don't loosen this to "approved for this lead" or "approved today", and
> don't move the claim after the effect.

**`0004-decisions-come-only-from-a-human-origin.md`** (MC-11a, and referenced from MC-04)

> # Decisions and control commands come only from a human origin
>
> Approvals and control commands enter in two ways only. One is `jura-growth approve|skip` in a
> real terminal, with the request's hash code typed. The other is `jura-growth remote`, reached
> through an SSH forced command whose key lives only with Dispatch's gateway. `JURA_GROWTH_JOB`
> and `headless.NEVER` refuse headless runs, but an environment variable is a label, not a
> credential. Interactive Claude sessions, crew agents and Dispatch tasks have no such label.
> So the code also checks the origin: a TTY, or an `sshd` ancestor, and never a `claude`
> ancestor. The Discord user id is attribution, not authentication. Dispatch never runs on the
> growth Mac, and no model rewrites a command between Ting Yu and `remote`.

**`0005-browser-automation-runs-only-in-the-publish-job.md`** (BP-03)

> # Browser automation runs only in the publish job, scoped by domain
>
> `claude -p` gets the Claude in Chrome tools only with `--chrome`. The runner adds it only for
> jobs in `caps.BROWSER_JOBS` (`publish`), so a settings change can't give it to another job.
> Page tools are allowed only through `ClaudeInChromeDomain(<host>)` rules for the platforms'
> own hosts, never by tool name, because a tool-name allow covers every site. The run has no
> `--add-dir`, no web search or fetch, and only its `publish` commands. Its transcript is
> audited for every host a tool result showed. The research jobs never get browser tools
> (ticket 02). Rollback is removing the job from `BROWSER_JOBS`.

## Specialist guidance

- **`crew:api-and-interface-design`** applies to the growth and Dispatch contract, which is the
  one interface another system calls:
  - Version it (`"contract": 1` in every `--json` answer).
  - Make every mutating command idempotent by `--ref` (B4).
  - Use a closed answer enum with stable exit codes.
  - Never change a field's meaning; add new ones.
- **`crew:supabase-postgres-best-practices`** and **`crew:vercel-react-best-practices`** don't
  apply. This is SQLite and Python with no React.
- On the SQLite side, the transition trigger and the unique index on `(approval_id, source_ref)`
  belong in the migration, not in Python. A partial unique index on `approvals (kind, subject)
  WHERE status IN ('pending', 'approved') AND used_at IS NULL` enforces one live request per
  subject.

## Questions for Ting Yu

1. **Email approval timing (B5).** Should requests be raised only for emails due today, within
   the day's remaining quota, with a pending request expiring at 16:30 on the next business day
   and an approved one usable for three business days? *Recommended:* yes.
2. **Skip after approve (B4).** May you revoke an approval until the engine claims it?
   *Recommended:* yes, in both PRDs.
3. **Transport (B3).** Should the Mac accept Dispatch only over SSH with a forced command, which
   means turning on Remote Login and a private link such as Tailscale, with Dispatch never running
   on the Mac? *Recommended:* yes.
4. **Group rules (B7).** Should confirming a group's rules from Discord be a typed command with
   the open days (`approve A-0412 promo_days=sat,sun post_days=any`), with no button?
   *Recommended:* yes.
5. **Chrome profile.** Should publishing use a dedicated Chrome profile signed in only to the
   Jura accounts, with Claude in Chrome turned off in your other profiles while any platform is
   in `browser` mode? *Recommended:* yes. No code can pin the profile.
6. **Terminal approvals (B2).** Do you accept typing a six-character code from the card when you
   approve in Terminal, and being unable to approve from inside a Claude Code session?
   *Recommended:* yes.
