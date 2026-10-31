# Technical review: inbox watch

*Tech lead, 2026-10-31, against `main` at 1206360 and `origin/crew/approvals-first-social-depth` at 9374c14. Spec: `prd-jura-inbox-watch-2026-10-31.md`.*
*Ting Yu has said not to ask him questions, so each finding carries a decision.*

**Verdict: build it, with the eight blocking fixes below written into the tickets.** The plug-in shape is right, and no wide refactor is needed: every core change is an added keyword with a default. Four of the PRD's stated mechanisms don't work as written (S3's audit, §5's "a draft that `for_discord` would change is refused", S1's data denial, S5's lock check).
Evidence: baseline `uv run pytest` is 3982 passed. Probes (temp folders, nothing live) are quoted as P and A numbers below.

## Seams
The one new seam is `inbox.store.record(conn, Reaction) -> Recorded | Duplicate`, the deep module that both mail intake and `inbox observe` go through. W5, W6, W7, R2 and R3 are tested there. Everything else uses a seam that exists.

| Seam | Exists | Tests here |
|---|---|---|
| `runner.run(job)` with a fake `claude` (`tests/publish_fake.py`, made job-agnostic: its scratch folder and `{A}` capture hard-code `publish`) | yes, highest | every job end to end, the precheck, `after_run`, S2, S3, S4, S5, S6 |
| `replies.imap_factory` (the IMAP adapter) | yes | W1, W6, W7, W8; asserts `EXAMINE` and `BODY.PEEK` only |
| `store.record` | **new** | W5, R2, R3, the state machine, D5, D7 |
| Gate matrix: `tests/gate_adapter_email_reply.py`, `gate_adapter_social_reply.py` | yes | D2, and the Terminal refusal for free (`test_terminal_refusal_every_kind.py` collects adapters) |
| `audit.audit(transcript, …)`, pure, with `tests/publish_transcripts.py` | yes | S3, B1's new rules |
| `discord_double` and `sweep.assert_clean` | yes | R1, D1, S7; plant bodies in the *other* messages |
| `mission.read(Source)` then `one_pager.text(snapshot)` | yes | R4; read-only per ADR 0002 |
| `remote.handle` with `ctx.obj["origin"]` | yes | D6, `inbox list`, S6 |
| `send.resend_client`, `tests/resend_stub.py` | yes | D3 |
| `tests/d1_stub.py` | yes | W4 |

## Blast radius
- **New:** `agents/inbox/` (`store`, `mail`, `report`, `triage`, `kinds`, `send`, `one_pager`, `commands`, `migrations/0001_inbox.sql`), `agents/inbox_browser/` (`__init__`, `scope`, `job`, `kinds`), `config/inbox.yaml`, three prompts, ADR 0006, `tests/gate_adapter_*`, `.scratch/inbox-watch/setup/inbox-watch.md` (the release persona copies it to `outputs/growth/setup/`, as `test_mission_setup_guides.py` expects).
- **Core, small hunks:** `runner.py`, `caps.py`, `privacy.py`, `discord.py`, `cards.py`, `mission.py`, `one_pager.py`, `backup.py`, `remote.py`, `headless.py`, `agents/__init__.py`, `docs/dispatch-contract.md`, `config/settings.yaml`, `README.md`, `CONTEXT.md`, ADR 0005 (amendment).
- **Plug-ins:** `outreach/replies.py` (split read from record), `publish/audit.py` (keywords with defaults), `publish/scope.py` (`domain_rules(platforms=None)`).
- **Deliberately untouched:** `approvals.py`, `feed.py`, `health.py`, `schedule.py`, `slots.py`, `publish/job.py`, `claim.py`, `commands.py`.
- **Data:** three new tables, no change to existing rows. An older checkout runs against them. After a revert, open `email-reply` and `social-reply` requests fail closed (A15).
- **Other repos:** none needed. Dispatch passes `/growth` text verbatim (contract D2), but `text.split()` collapses whitespace: see N9.

## Blocking findings, most serious first
### B1. `publish.audit` can't judge an inbox run (S3, D4, E6)
Probed with inbox-shaped transcripts:

| Probe | Run | Result | Problem |
|---|---|---|---|
| A2, A9 | clicks only, or a click after posting | **passes** | Clicks aren't judged. A watch run can Like, Hide, Delete or Block (E6) and pass |
| A3 | reply run claiming through `inbox reply-next`, typing the approved text | **fails** | `"publish next"` is hard-coded, so `claimed` never sets |
| A5 | approved text typed, Return in the middle | **passes** | Return reads as a space. In a DM each Return sends, so a fragment goes out |
| A6 | a newline inside the typed text | **passes** | Same |
| A10 | `places=[thread]` | fails, correctly closed | `hosts.within` accepts only `/groups/<x>`, so a thread never matches |

Two things already work: `approved=[]` fails any typing (A1), and the whole text then Return passes (A4).

**Fix, all keyword-only with defaults, so `test_publish_audit.py` doesn't change:** add `rules: AuditRules = PUBLISH_RULES` to `audit.audit`:
- `next_word`, `stopped_word`, `done_word` replace the three literals. The reply command prints the same `"due": true` that `_HANDED_OUT` reads.
- `read_only=True` (watch): any `form_input`, `file_upload` or `computer` action outside `LOOKS` fails.
- `one_line=True` (reply): a newline in typed text, `shift+return`, or Return before the field holds a whole approved text fails. Once it holds one, one send action (Return or a click) is allowed, and any later click, key or typing fails until `inbox reply-done`.
- `place_check=hosts.within` is the default; a DM passes `hosts.same_place`.
- `tool_word` stops findings saying "a publish run" in #alerts.

### B2. A transcript audit is after the fact: prevent the watch from acting at all (S3, W2)
The audit reports damage once it's done, and a watch run reads hostile text on every page with the accounts signed in. **Decision:** `inbox_browser.scope` denies `computer`, `form_input`, `file_upload` and `upload_image` by name for `inbox-watch`, on top of `publish.scope.DENIED_TOOLS`. The watch reads with `navigate`, `read_page`, `get_page_text` and `find`, opening threads by URL. A deny rule beats the domain allow, as `file_upload` already shows. `read_only` stays as the second layer.

The cost is that comments not loaded on first paint go unread, so a person could be missed. **Decision:** `inbox observe` records the page's comment count, and a count above the comments recorded reports "3 comments the watch couldn't read: check by hand" in R1 and R4. If the first-run check shows this is too thin, allow `computer` with `read_only` catching everything but looks: a one-line change, recorded in ADR 0006.

### B3. `privacy` blanks the card, and §5's draft rule refuses ordinary replies (S7, D1, D8)
- **`never_show` is process-wide and blanks conversation text.** P1: `They said: [removed]?`. Precheck, `after_run` and R1 share one process, so reusing `replies._batch` blanks every later post.
- **Learned names mask a greeting, even in `own_copy`.** P2: `Hi [name removed], thanks…`. Scout's `privacy_terms` holds every contact with a named address, so §5's rule refuses every "Hi Jane," to one: the draft fails twice and becomes `needs-you` (D8), against the `inbox-email` channel's "a greeting name allowed".
- **Ting Yu's own address reads `[removed]` outside `own_copy`.** P3.
- **An edit re-masks.** `cards._edit_changed` sends the stored `first_piece` through plain `discord.edit`, so a card's quote turns to `[name removed]` when it's decided.

**Fix.** `privacy.for_discord(text, *, own_copy=(), conversation=())`. A conversation piece is treated as `own_copy` *minus the name matcher*: no `_never`, no names, owner addresses kept, and phones, named addresses, secrets and the finance rule still masked. `_split` gets a third class. `discord.post` and `discord.edit` take `conversation=`. Intake may still call `never_show`, because the bypass makes it harmless. §5's refusal becomes `for_discord(draft, conversation=[draft]) != draft`.

For cards, the kind sets `conversation_card = True`, and `cards` passes the whole card body (`[content]`, and `[rest[1]]` on edit) as conversation. `Preview` and `build()`'s return shape stay as they are (`test_outreach_cards.py` unpacks it). The card's frame is fixed text, so this widens nothing. Only cards and R1 use the class. **Decision:** R4's excerpt on the one-pager and `/growth inbox list` stays plain-masked. A masked name in a list line costs nothing, and it keeps `mission`, `one_pager` and `remote` out of the class, which matches the PRD's "exactly those strings and nothing else".

### B4. Triage can read everything (S1)
`runner.claude_command` adds `JURA_ROOT` for every non-browser job (confirmed by probe), so `growth.db`, transcripts, backups and `outputs/` are readable by the session holding hostile text. **Fix:**
- `caps.THIRD_PARTY_TEXT_JOBS = BROWSER_JOBS | {"inbox-check"}`. The runner's `--add-dir` is the scratch folder for those jobs. With `dontAsk`, cwd (`REPO_ROOT`) and scratch are then all it can read, as ADR 0005 established.
- Belt and braces from `inbox.permissions`: `Read` denies for `data/growth/{growth.db*,transcripts,backups,discord-outbox,runs,launchd,one-pager,work/publish,work/inbox-watch,work/inbox-reply}/**` and `outputs/growth/**`. Not a blanket `data/**`: a deny would hit its own scratch.
- E4 needs `inputs/services.md` and the toolbox, which sit outside. `inbox pending --json` prints them as `grounds`. Nothing is copied.
- `backup.prune_transcripts` and `prune_browser_work` use the same set, which gives §4's 7 days for triage too.
- Tools: no `tools:` in settings, and `WebSearch`, `WebFetch` and every `mcp__` denied; commands are `inbox pending` and `inbox submit` only.

### B5. Precheck IMAP is fine only under five rules (W1, W7, S6)
Network work in the precheck is acceptable: `publish` already syncs and posts there, the job lock is held, and pause and PAUSE are checked first. But:
1. **It must not raise for a network fault.** A raising precheck is a failed run, an alert and a count toward auto-pause, so three flaps (a Mac waking before Wi-Fi) pause mail for good. Catch `RepliesError`, log `inbox.mail_failed`, continue with triage. An auth failure, or no successful check for 2 hours, gives one alert a day and an `inbox.health` line.
2. **No transaction across the network.** Fetch first, then commit per message: `remote` decisions wait on SQLite's 30-second busy timeout inside Dispatch's 60.
3. **A budget.** 120 seconds of wall clock and `INBOX_BODIES_PER_CHECK` (50) body fetches, oldest first. The rest wait for the next check, and the last-success stamp moves only when a check finished.
4. **A poison item can't stop the mail.** `triage_attempts` is bumped at hand-out. After 2, the item becomes `needs-you` and reports. `INBOX_TRIAGE_PER_RUN` is 10. Otherwise one hostile message starts Claude every 15 minutes, fails three times, and auto-pause stops `inbox` (R3 and W1 both lost).
5. **A job timeout.** `spec.get("timeout_minutes")` in `_run_claude`, 10 for `inbox-check`: a 30-minute triage holds the lock, and intake with it, past W1's 15 minutes.

`inbox-send` shares the `inbox` flag and auto-pause count, so three Resend failures would stop mail watching. A failed send marks the item `failed`, alerts once and leaves the run `ok`; only a crash counts. Follow `send.classify` for `pause`, `retry` and `fail`.

### B6. S5 by "another's lock is held" needs a publish edit and races (S5)
`locks.is_held` *takes* the lock to look, so a probe landing as the other job starts makes that job skip with "previous run still going", which `slots` reads as running. It also forces a change in `publish/job.py`. **Fix: one shared lock in the runner.** After the job lock, `name in caps.BROWSER_JOBS` takes `locks.held("browser")`; not acquired means a `run.quiet` event ("another browser job is running") and no Claude. Atomic, no publish edit, and `_abandon_stale` and `settle_orphans` still see the job lock. The slots are 10 minutes apart, so a precheck's brief hold costs nothing.

### B7. A report can be lost: the outbox is never replayed (R1)
`discord.post` saves a refused message to the outbox and nothing posts it again. "Every reaction posts one message" needs the cards' pattern: `inbox_items.reported_at` stays NULL until `delivered`, `report.report_due(conn)` runs in the precheck and in `after_run`, `dedupe=False`, no webhook means no attempt, and the one-pager counts unreported items. Tested with `test_discord_down.py`'s shape.

### B8. A long card splits away from its buttons and its draft (D1)
A 4,000-character message plus a 180-word draft is 3 or 4 pieces, depending on its line breaks (probe: 4). Buttons sit on the first, the draft on the last, and an edit only reaches the first. **Fix:** an inbox card is always one message. `report.card_quote` cuts what they said to fit (`2000 - frame - draft`, "(cut: the rest is in the mailbox or thread)") and never cuts the draft. A test asserts one piece and the draft's exact bytes at every length. This also makes approvals-first's fence-aware `split` moot here.

## Not blocking, but do them
| # | Finding | Decision |
|---|---|---|
| N1 | Hostile text on a command line: `inbox observe --text "…"` puts page text through Bash quoting | `inbox observe --file` and `inbox submit --file`, in scratch, through `GuardedPath`, as the repo's "write drafts in scratch" rule says. Validate source, URL (`hosts.problem`), length; `INBOX_OBSERVATIONS_PER_RUN` 40 bounds a flood |
| N2 | W5's hash is over the model's retelling, which varies ("See more", spacing, emoji), so a watch can re-record | Key on platform, kind, thread, author, and the first 120 alphanumerics after `normal()` and casefold. Fixture test with two tellings |
| N3 | R3 says the stored text isn't the model's retelling, but a social item's stored text *is* | `after_run` checks each observed text appears in that run's Chrome results. If not, the item is `unverified`: reported as such, no draft |
| N4 | Our BCC to Levi lands in the watched mailbox and would read as a reaction | Intake drops mail from the sending domain, except W8's `no_reply@`. Bounces and `mailer-daemon` count as R2 noise |
| N5 | A spoofed card: their text can hold `Answer: Approve`, fences or `[x](url)` | One builder, `report.quoted`: every line `> `, backticks neutralised, `remote._defuse`'s rule; `suppress_embeds=True` on R1 |
| N6 | Text outlives §4's 90 days in `approval_cards.first_piece` and `discord-outbox/*.jsonl` (never pruned) | Retention blanks `first_piece` for closed inbox kinds, `backup.prune_outbox` keeps 14 days (`retention.outbox_days`) |
| N7 | `replies.UNSUBSCRIBE_RE` suppresses on "remove" or "stop" anywhere ("could you remove the second page?") | Unchanged for W6, but R1 names the word and the rule, so Ting Yu can undo it. Not a blocker: it fails safe |
| N8 | `one_pager.COUNTED_JOBS` lists slots one by one otherwise: 202 a day | Add the four jobs. Without this the "Today" section alone passes 2,000 characters |
| N9 | Dispatch's `text.split()` collapses `reword`'s line breaks | `reword` makes one paragraph; a literal `\n\n` token becomes a paragraph break. The card shows the result, so nothing goes unseen |
| N10 | `run_id` is empty in precheck work, so `raised_by_run` is None for anything raised there | Raise only in `inbox submit` and `reword`, never in the precheck |
| N11 | `config/social.yaml` on `main` has `page_url: null` and `draft`, so `scope.enabled_platforms()` is empty | `inbox_browser` names `("facebook","instagram")` itself, independent of `publish_mode`, and `config/inbox.yaml` holds the two page addresses (`hosts.page_problem`). A test holds them equal to `social.yaml` when that is set |
| N12 | D4's thread can't be bound to Business Suite, whose thread is in the query | A DM's target must be `/messages/t/<id>` or `/direct/t/<id>/`, else no `social-reply` draft: it's reported as "answer by hand". A comment target is checked for host only, with the read-back |
| N13 | A claim left open by a killed reply run | `unknown`, `inbox-browser` pauses, R4 lists it for 7 days. **No resolve command:** an unknown item is never sent again, so one adds nothing. Tell him so in the alert |

Considered and rejected: social replies as publish items. It would reuse the queue, but `PUBLISH_WINDOW` ends at 18:00, `caps` and `pause inbox-browser` would need carving out, and it deepens the overlap with approvals-first.

## The attack list, answered
The audit and Enter are B1, `claude_command`'s add-dir is B4, `never_show` is B3, precheck IMAP is B5, and the merge is below.

| Question | Answer |
|---|---|
| Two plug-ins for two flags? | **Yes, the right seam.** The pause flag, the run set, auto-pause and a kind's `agent` all key on a plug-in's `NAME`, and a job's agent must resolve through `agents.by_name` or it silently has no hooks (probe). Keep `inbox_browser` thin: `NAME`, `permissions`, `precheck`, `after_run`, `approval_kinds`, `setup_gaps`. It imports `inbox` at the top, so if `inbox` is broken both are, and closed |
| `inbox_browser` package, `inbox-browser` NAME? | **Works** (probe): `by_name`, `kinds()`, `_known_agents`, `pause`, `migration_sets`, and `_plugin_checks`' `INBOX_BROWSER_SETUP_CHECK`. **The trap:** a second `inbox` click group silently replaces the first (probe), so every `inbox …` command is registered by `inbox`, and `inbox_browser` has no `register` and no `MIGRATIONS` |
| Publish pause, both ways? | No publish edit. `inbox stopped` writes both flags and alerts with both resume commands. `publish stopped` writes its own, and `inbox_browser.precheck` and `social-reply.switched_off` read it |

## Existing tests and invariants this breaks
| Test | Change |
|---|---|
| `test_publish_limits.py::test_the_hard_values_are_in_caps` | `BROWSER_JOBS` is now the three jobs. Keep the exact-set assert |
| `test_publish_argv.py::test_only_publish_gains_chrome_and_browser_rules` | `if job in caps.BROWSER_JOBS`, and assert the job's own hosts. Rename it |
| `test_mission_slots.py::test_every_job_in_settings_gets_its_slots` | Add `inbox-check` 68, `inbox-send` 85, `inbox-watch` 13, `inbox-reply` 36; keep the `n == 1` rule for the rest. `test_a_fortnight_of_every_job_is_quick` must stay under 2 seconds |
| `test_no_generic_request_command.py` | `A11_COMMANDS` gains `inbox submit`, `inbox reword`; `RAISERS` gains `inbox.kinds.raise_request`. |
| `test_remote.py`, contract tables | Add `inbox list`, `inbox redraft`, `inbox reword` in sorted order, with rows in `dispatch-contract.md` (the contract's "fields only added" holds; version stays 1) |
| `test_headless.py` | Auto-covers new jobs. `NEVER` gains `inbox redraft`, `inbox reword`. Prompts may name only declared commands |
| `test_agent_decisions.py`, `test_publish_argv.py::ALL_CLAUDE_JOBS`, `test_core.py` | Auto-parametrised, and must pass as they are. Nothing to edit: a failure there is a real bug |
| `test_one_pager*.py`, `mission_world` | The new section and `ASK_ME` gain lines; a snapshot with no section renders as today |
| `test_privacy.py`, `test_outreach_privacy.py`, `tests/sweep.py` | **Must not change.** The old rule stands everywhere else, and that is the proof |

Invariants held: ADR 0003 (content includes the frame and BCC; claim before Resend or Chrome), ADR 0004 (no new origin), ADR 0002 (the one-pager hook gets the read-only connection and may not call `content()`), "the core never imports an agent by name" (`COUNTED_JOBS` names jobs, as today).

## Merging beside approvals-first
Its diff, and ticket 02's plan, touch `cards.py` (docstring, import, `_card_title`, `feed.announce` after the `UPDATE`), `discord.py` (`split`, `post`), `health.py`, `mission.py`, `feed.py`, and three kinds.

| File | Our hunk | Overlap |
|---|---|---|
| `cards.py` | Only the `discord.post(...)` call in `_post_unposted` and the `discord.edit(...)` line in `_edit_changed`, through one helper. No import change | Clean with today's diff. Ticket 02's images-on-first-piece may touch the post call: one line to reconcile |
| `discord.py` | A `conversation=` keyword last in `post` and `edit`, and the two `for_discord` lines | Their `split` changes don't overlap. A keyword added by both is a one-line reconcile |
| `mission.py` | `plugin_sections` right after `plugin_lines` (not after `spend_today`), `_plugin_sections` after `_plugin_lines`, one `facts[...]` beside `plugin_lines` | Clean: at least three unchanged lines from `drift` |
| `health.py`, `feed.py`, `social/*`, `publish/kinds.py` | None | None |
| `settings.yaml` | New jobs after `publish`, before `backup` | Ticket 02 moves `digest`: separate hunks |

**Order and the join.** Whichever is ready first merges; there's no real dependency. The second one rebases, then does three things: (1) both declare, so `email-reply` and `social-reply` carry `feed_channel = "mission-control"` and `feed_approved` from day one (`feed.py` reads them with `getattr`, so they're inert before it exists); (2) their "table test over the real kinds" gains our two rows; (3) our card's first line after the header is a non-personal title ("Email reply · enquiry"), because `feed._card_title` posts it through plain masking. Run the full suite on the merge before G4. No branch waits on the other.

## ADR 0006 outline: reading inboxes through the browser, and what may reach Discord
- **Status:** proposed; accepted when ticket 05 lands. Amends ADR 0005 (browser jobs), MC §4.4, Scout §5.5.
- **Context:** Ting Yu's request of 2026-10-31. A person's reaction goes unseen, and he can't judge a draft without what it answers.
- **Decision 1, reading:** browser, not the Graph API; two jobs (`inbox-watch` reads, `inbox-reply` types); `caps.BROWSER_JOBS` grows; one shared `browser` lock.
- **Decision 2, a watch can't act:** denied by name, then audited as `read_only` (B1, B2).
- **Decision 3, the conversation class:** what it masks and what it doesn't; only cards and R1; a stored 4,000-character body with 90-day retention, and every other place text lands.
- **Decision 4, triage is scratch-only:** `THIRD_PARTY_TEXT_JOBS`, hostile text is input and a draft is the only output.
- **Decision 5, two plug-ins, one registers commands;** a publish pause stops the browser jobs by reading the flag.
- **Consequences and limits:** BP §4.1 grows and isn't compliant; "Seen" receipts; unread comments are counted, not lost; `unverified` items; Business Suite threads can't be bound.
- **Reversal:** remove the jobs from `BROWSER_JOBS` and `schedule uninstall`; reopen Graph API on an account warning; allow `computer` if the first-run check shows reads too thin.

**Prototype.** Whether read-only tools see enough of Meta's pages, and whether permalinks hold, can't be settled on paper. The PRD forbids live runs during the build, and he asked not to be asked, so this is a first-run check in the setup guide, not a question. The fixture proves the code; the guide's check proves Meta.

## Proposed tickets
Six tracer-bullet slices, each ending green with live behaviour off until G4. Edges: 01 → 02 → 03 → 04; 01 → 05; 03, 04 and 05 → 06. So 05 can run beside 02 to 04.

### 01: See mail and report it, with no model
**Blocked by:** none. **Prefactors first:** split `replies.py` into a mailbox read and `apply_reply` (its tests unchanged); add `privacy` and `discord` `conversation=`.
Then the `inbox` plug-in, migration, `caps`, `config/inbox.yaml`, the `inbox-check` job and precheck, `store.record`, the noise filter, `report_due`, R1 (every item reports on record for now), `quoted`.
**Accept:** W1, W5, W6, W7, W8, R2, R5's counts, B3's class tests, B5 rules 1 to 3, B7, N4, N5, N7. `EXAMINE` and `BODY.PEEK` only. A 16:45 `scout-sync` counts nothing again. `test_privacy.py` and `test_outreach_privacy.py` untouched and green.

### 02: Triage classifies and drafts, and can't reach anything
**Blocked by:** 01.
`THIRD_PARTY_TEXT_JOBS`, per-job timeout, `prompts/inbox-check.md`, `inbox pending`, `inbox submit --file`, brand channels, `triage_attempts`. R1 moves to after triage. `after_run` fails closed and rewrites the summary.
**Accept:** B4 (argv: scratch only, the denies, no `mcp__`), B5 rule 4, R3 (a contact and every social item are reported whatever the model says; only non-contact mail may be `noise`), S2 (a model's `FAIL:` line reaches no run row or alert), D8, D9, E1 to E6 as prompt assertions and brand-channel tests, N1, N10. A poison item stops after 2 attempts while the next item is still handled.

### 03: Approve an email reply and it goes out threaded
**Blocked by:** 02.
`email-reply` kind, the card (`conversation_card`, `card_quote`), `inbox send-due`, `inbox-send`.
**Accept:** the gate matrix and Terminal refusal pass for `email-reply`; D1, D2, D3 (`In-Reply-To`, `References`, `Re:`, BCC, sent 08:00 to 22:00), D5, D7, E2. Content covers the frame and BCC (ADR 0003). B3's greeting case: "Hi Jane," reaches the card unchanged. B8: one piece at every length. A retry under the same claim uses one idempotency key and stops at 23 hours. A failed send doesn't count toward auto-pause.

### 04: He can see and steer it from Discord
**Blocked by:** 03.
Plug-in hook `one_pager_section(conn, since)` with the read-only connection; `Snapshot.plugin_sections`; Replies waiting; `COUNTED_JOBS`; `inbox list`, `inbox redraft`, `inbox reword` in `remote` and `NEVER`; digest; W4; retention.
**Accept:** R4 with the section between Needs you and Approvals waiting, D6 (each closes the old card and raises a new one; a claimed item refuses), R5, W4 (D1 down is one warning a day), N6, N8, N9, S6. `mission.read` opens the database read-only and calls no `content()`. Contract tables match the code.

### 05: The watch reads the platforms and can't act
**Blocked by:** 01. **Prefactors first:** `AuditRules`; the shared `browser` lock in the runner; `scope.domain_rules(platforms=None)`.
Then `inbox_browser`, `inbox-watch`, `prompts/inbox-watch.md`, `inbox observe --file`, `inbox watch-targets`, `inbox stopped`, stats, ADR 0006, ADR 0005's amendment.
**Accept:** W2, W3, W5 (N2's two tellings), B1's table as audit tests, B2 (argv denies `computer`), B6 (a held `browser` lock means no Claude and a quiet record; `publish` too), S3, S4 (both flags, one alert), S6, N3, N11; the uncounted-comment line; an observed post is one Jura published (`publish_items` done, 14 days, at most 8). `test_publish_audit.py` unchanged and green.

### 06: Approve a social reply and it posts, once, in the right place
**Blocked by:** 03, 04, 05 (04 only because the guide and UAT script describe it).
`social-reply` kind, `inbox reply-next`, `inbox reply-done`, `inbox-reply`, `prompts/inbox-reply.md`, the fixture's inbox pages, `.scratch/inbox-watch/setup/inbox-watch.md`, the UAT script.
**Accept:** the gate matrix and Terminal refusal for `social-reply`, including its switch reading the `publish` flag; D4 (comment under the comment, DM in the thread, one per run, read-back); `inbox-social` refuses a line break; `one_line` end to end (A5 and A6 fail the run and pause `inbox-browser`); N12, N13; a watch that finds the Page already answered closes the item and still reports it. `uv run pytest` green across the suite on the branch.
