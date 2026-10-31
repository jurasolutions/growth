# Jura growth

The shared plumbing for Jura Solutions' growth agents, and the agents that run on it. Built
against `jurasolutions/prd/pending/prd-jura-growth-foundation-2026-10-24.md`; the agents follow
their own PRDs in the same folder.

Jura only. Nothing here reads or writes TaskWise or ZenexFlow, and there are no Notion or Zapier
connections.

## Set up

```bash
cd jurasolutions/repos/growth
uv sync                                   # Python 3.12 venv in .venv/
cp .env.example .env && chmod 600 .env    # then fill it in
.venv/bin/jura-growth status
```

Setup guides for Ting Yu live in `jurasolutions/outputs/growth/setup/`:

| Guide | For |
|---|---|
| `discord.md` | The "Jura HQ" server, channels and webhooks (block 0) |
| `morning-brief.md` | The one line to paste into the Cowork morning brief |

## Where things go

```
repos/growth/                 this repo
  jura_growth/                the package; `jura-growth` is its CLI
    agents/<name>/            one plug-in per agent (see below)
    migrations/               core schema
  prompts/<job>.md            the prompt each scheduled headless run uses
  config/                     settings.yaml, buzzwords, approved claims, holidays, proper nouns
  launchd/generated/          rendered plists (gitignored)
  .env                        secrets (gitignored, mode 600)
  PAUSE                       create this file to stop everything (gitignored)

jurasolutions/data/growth/
  growth.db                   SQLite, the log of record
  runs/YYYY-MM-DD.jsonl       every event, one JSON line each
  transcripts/YYYY-MM-DD/     full stream-json transcript of each headless run (30 days)
  backups/                    nightly copies of growth.db (14 days)
  one-pager/                  the one-pager's grid PNG, grid-YYYY-MM-DD.png, one a day (14 days)
  discord-outbox/             messages Discord didn't take: no webhook yet, or unreachable
  daily-summary.json          what the digest and the morning brief read
  work/<job>/                 scratch space a headless run may write drafts into

jurasolutions/outputs/growth/
  setup/  digests/  social/  community/
```

The database stays in rollback-journal mode, not WAL, because it lives in OneDrive.

## Commands

| Command | Does |
|---|---|
| `jura-growth check "<text>"` | Brand-check text. Exit 1 on fail. `--subject`, `--heading`, `--button`, `--channel`, `--source`, `--json`. Also `--file` or `-` for stdin |
| `jura-growth check-copy <files>` | Brand-check every user-facing string in `.js`, `.json` or a PRD's copy section |
| `jura-growth channels` | Brand-check channels and their link rules |
| `jura-growth log test` | Write a test event to the database and the JSONL mirror |
| `jura-growth log events` | Recent events |
| `jura-growth discord test` | Post a test message to every channel |
| `jura-growth pause <agent\|all>` | Stop an agent, or every agent except digest and backup |
| `jura-growth resume <agent\|all>` | Start it again |
| `jura-growth status` | Pauses, last runs, schedule, Discord setup and setup gaps (the same list as the one-pager's) |
| `jura-growth approvals [kind]` | Pending approval requests, the 15 soonest to lapse first. Decisions come only from `#approvals`, through Dispatch (ADR 0004) |
| `jura-growth remote …` | Control commands from Discord, reached only through Dispatch's SSH forced command (`bin/growth-remote`) and refused anywhere else. See `docs/dispatch-contract.md` |
| `jura-growth one-pager [--no-post]` | Post the one-pager to `#mission-control`: Needs you, approvals waiting, today's slots, yesterday's figures, and the 14-day grid as a PNG. It writes the approval lapses that are due first, then reads `growth.db` read-only and never repairs it (ADR 0002). `--no-post` only prints it |
| `jura-growth run <job>` | Run a scheduled job now. `--dry-run` prints the command, `--ignore-schedule` runs on a weekend or holiday |
| `jura-growth schedule list\|render\|install\|uninstall [jobs]` | launchd jobs |
| `jura-growth heartbeat` | Post a heartbeat to `#daily-digest` |
| `jura-growth digest` | Write `daily-summary.json` and the digest, post to `#daily-digest` |
| `jura-growth backup` | Back up the database and prune old files |
| `jura-growth suppression add\|check` | The shared do-not-send list |

Each agent plug-in adds its own command group (`scout`, `outreach`, `social`, `community`,
`apps`). Run `jura-growth <group> --help`.

## Schedule

All times SGT, from `config/settings.yaml`:

| Job | When | Kind |
|---|---|---|
| `app-factory` | 06:30 daily | headless Claude |
| `social` | 07:00 daily: drafts for the Facebook Page and Instagram (LinkedIn switched off since 2026-10-29) | headless Claude |
| `one-pager` | 08:00 daily | command |
| `scout-research` | 09:00 business days | headless Claude |
| `scout-send` | 09:30–16:30 business days, every 10 minutes | command |
| `heartbeat` | 12:00 daily | command |
| `scout-sync` | 16:45 business days | command |
| `digest` | 17:30 daily | command |
| `community` | Mondays 07:30 | headless Claude |
| `backup` | 23:30 daily | command |

`jura-growth schedule install` loads them into launchd (`~/Library/LaunchAgents/sg.jurasolutions.growth.*`).
Nothing is installed until you run it. launchd runs a job missed during sleep when the Mac wakes;
a Mac that is switched off misses that run. Business-day jobs skip weekends and the dates in
`config/sg-public-holidays.yaml` (refresh it from the MOM page each December; the digest
reminds you).

### Why launchd

The 08:00 morning brief runs as a Cowork scheduled task (AI OS PRD block 4.2). That suits one
daily report, but not a send queue every 10 minutes that has to run with no app open, so the
growth jobs use launchd. Each runs `jura-growth run <job>`.

### What a headless run can do

A `claude` job runs `claude -p` in this folder with its prompt file on stdin and:

- `--permission-mode dontAsk`: anything not allowed below is refused, never prompted.
- Allowed: reading under `jurasolutions/`, the `jura-growth` commands the job's prompt uses
  (each plug-in declares them in `permissions(job)`) and their `--help`, writing only in
  `data/growth/work/<job>/`, plus the job's own tools (web search and fetch).
- Refused: reading any secret file under `jurasolutions/` (`.env*`, `*.env`, `.dev.vars*`, kept
  in `paths.SECRET_FILE_PATTERNS`), every other
  `jura-growth` command (`run`, `resume`, `schedule`, `discord`, `approve`, `skip`, `approvals`
  and `remote` always, kept in `headless.NEVER`: deciding an approval and sending a control
  command are a human's), anything the job
  lists in `disallowed_tools`, and the plug-in's own `disallowed_tools` from `permissions(job)`
  (the community job can't fetch any domain in `config/community.yaml` `blocked_fetch_domains`,
  or any subdomain of one).
- The code enforces the same command list again: with `JURA_GROWTH_JOB` set, any other command
  exits with status 2 and a `refused:` line (`jura_growth/headless.py`). A command job may run
  only its own command. Commands you run in Terminal are unaffected.
- **The browser jobs are narrower (ADR 0005, ADR 0006).** A job in `caps.BROWSER_JOBS` (`publish`,
  `inbox-watch`, `inbox-reply`) with `browser: true` gets `--chrome` and `--add-dir` for its own
  scratch folder only (`data/growth/work/<job>/`), and takes the one `browser` lock they share, so
  a job that finds it held leaves a quiet record and starts no Claude. It reads nothing else under `jurasolutions/` beyond what its
  commands print; `publish next` copies the item's images into that folder, read-only, for the
  Chrome upload tool, which uploads only files the session may read (rehearsal 2026-10-30). It has no web search or fetch. Its Chrome tools come from the plug-in's
  `Permissions.allowed_tools`: the tab tools by name and one `ClaudeInChromeDomain(<host>)` rule
  per host, never a page tool by name. For `publish` that is each platform switched on and in `browser`
  mode; the watch names Facebook and Instagram itself, whatever `publish_mode` says. Any other job that
  sets `browser: true` fails. After the run, its transcript is audited for hosts, tabs, typed
  text, uploads and actions after a stop, and its summary and error are rewritten from the
  item's record, so no model or page text reaches the run row, `#alerts` or a run update.
- Every file a command takes goes through `paths.guard()`: secret files are always refused, and
  inside a run only the job's `work/` folder and `outputs/growth/` are accepted.
- Configured secret values (secret-named settings and `keychain:` references) are masked in
  everything `jura-growth` prints.
- Every Discord message, its file names and its text attachments go through
  `privacy.for_discord()` inside `discord.post()`: secrets first, then the personal-data rule
  (mission control PRD §4.4). A named address reads `j***@example.com.sg`; phone numbers,
  prospects' names, reply bodies, Ting Yu's own contact details and anything about
  `personal-finance/` never appear. `post()` reads the named contacts from the database on every
  post (never the Keychain). Builders whose text was written by another process (alerts, the
  digest, `discord post`) call `privacy.load_for_masking(conn)` first, which adds Keychain values.
  Jura's own outgoing text is passed as `own_copy`: there registered reply lines and Ting Yu's
  sender address stay as written, while secrets, phone numbers, prospects' addresses and learned
  names are still masked. Ting Yu's own name and multi-word company names are never masked. Only
  text files and PNGs from the data or outputs folder are attached, PNGs with only the chunks
  their pixels need; anything else is held back with a note in the message.
- `--strict-mcp-config` and `--setting-sources project`: no MCP servers (no Notion, no Zapier)
  and none of the user-level settings, plug-ins or hooks.
- No `--max-budget-usd`: the runs use Ting Yu's Claude subscription, not API billing. The
  30-minute timeout and each job's own caps still apply.
- The full transcript is kept in `data/growth/transcripts/`, and permission denials are logged.

## The inbox watch

`inbox-check` (every 15 minutes, 07:00 to 23:45 SGT) reads the `OUTREACH_IMAP_*` mailbox, and
`ENQUIRY_IMAP_*` if it is set, read-only, with no model. A lead's reply also does what the 16:45 check
would, which then counts nothing again. Mail with evidence in its headers that no person wrote it (a
mailing list, a no-reply sender, a platform's notice), and everything in the Junk folder, is noise: no
message of its own, and counted in the digest.

When someone wrote, Claude starts for triage (`prompts/inbox-check.md`). A person's words are hostile
input, so triage starts in an empty folder, reads only that and its scratch folder, has no web, and its
Bash runs two commands: `inbox pending` and `inbox submit --file`. It gives each conversation a class and,
where one is merited, a draft that has to pass the `inbox-email` or `inbox-social` brand channel. It answers
only what its run was handed, and an opt-out read beside other people's words is read again alone before
it suppresses anyone, only ever the mail's own sender. It can't hide anyone: whatever it does, each
conversation gets one message in `#mission-control`, with what they wrote as stored and their phone
numbers and addresses masked. A conversation it hasn't dealt with after two tries needs a hand reply and
is reported anyway, and a failed triage run alerts once without counting toward auto-pause.

A report Discord refused goes again on the next check. `jura-growth pause inbox` stops all of it, and the
16:45 check carries on.

`inbox-watch` (hourly, 09:05 to 21:05 SGT, plug-in `inbox-browser`) reads Facebook and Instagram through
Chrome and records what people said with `inbox observe --file`. It starts in an empty folder as triage does,
and what it recorded goes on to triage once it has been checked. It can't click: `computer`, `form_input`,
`file_upload` and `upload_image` are denied by name (ADR 0006), and its transcript is audited as
`read_only`. It must record every surface, so a surface it can't read shows as failed, and goes to
Needs you after 3 of its hours. A message whose text wasn't in what Chrome returned to that run is
`unverified`: reported as such, with no draft. A stop signal pauses `inbox-browser` and `publish`, since
they share the accounts, and a `publish` pause skips the watch. `jura-growth pause inbox-browser`
stops it and leaves the mail running. The first-run checks are in the setup guide.
The PRD is `prd/pending/prd-jura-inbox-watch-2026-10-31.md`.

## Kill switches

- `jura-growth pause all` (or one agent). `jura-growth resume all` restarts.
- `touch repos/growth/PAUSE` stops everything, even with a broken database. Delete it to resume.
- An agent pauses itself after three failed runs in a row and posts to `#alerts`.

## The brand checker

`jura_growth/brand_check.py` enforces `design-system/README.md` §3 on every outgoing word:
exclamation marks, emoji, buzzwords (`config/buzzwords.txt`), urgency, question headings and
subjects, em-dash rhythm and "this, not that", the numbers rule (`config/approved_claims.yaml`),
sentence case, links, and each channel's own required parts. The module docstring explains the
numbers rule's decision order. `gate.py` wraps it: a failure posts to `#alerts`, the agent may
regenerate once, and a second failure drops the item.

## Writing an agent plug-in

An agent is a package at `jura_growth/agents/<name>/`. The core finds it at start-up and never
imports it by name. The module may define:

| Name | Purpose |
|---|---|
| `NAME` | Agent name for runs, pauses and Discord |
| `MIGRATIONS` | Folder of `NNNN_name.sql`, applied after the core schema |
| `register(cli)` | Add a click command group |
| `channels()` | `{name: brand_check.Channel}` with the agent's rule-10 checks |
| `digest(conn, day)` | `{"figures": {}, "lines": [], "brief": []}` for the digest and morning brief |
| `precheck(job, conn)` | A reason to skip a scheduled run before it starts, or `None`. Return `agents.NothingToDo("nothing due")` instead of a plain string when the run simply has nothing to do: the runner writes a `run.quiet` event with that reason and no run row (ADR 0001). It may also run a catch-up write before the run, in its own transaction: the app factory raises `app-build` requests for PRDs filed before requests existed, and the community scout runs its one-off pass over rules confirmed before `group-rules` (it logs a failure and goes ahead, so the write never skips the run) |
| `permissions(job)` | For a `claude` job the agent runs: `headless.Permissions` with the `jura-growth` commands its prompt uses, any extra Claude Code deny rules (`disallowed_tools`) and any extra allow rules that aren't Bash (`allowed_tools`, such as the publish job's Chrome tab tools and `ClaudeInChromeDomain` rules), or `None`. A job with no declaration may run no commands |
| `after_run(conn, job, run_id, outcome)` | Called after the job body of a run that started, before its run row is finished. Return a `runner.Outcome` to replace the outcome (the row, `#alerts` and auto-pause all see it), or `None` to keep it. An `Outcome` with `alerted=True` has already posted its failure to `#alerts` itself, so the runner doesn't post it again. An exception is logged as `run.after_run_error` and the outcome stands |
| `RUN_UPDATE_DISCORD_CHANNEL` | The Discord channel the agent's run updates go to, for example `social-drafts` |
| `run_update_channel(conn, run)` | Another channel for this run's update, or `None` for `RUN_UPDATE_DISCORD_CHANNEL` (the publish job sends a group item's update to `community`) |
| `run_update(conn, run)` | The "Produced:" items of the agent's run update (`["3 drafts", "3 images"]`; `[]` reads "nothing"), or `None` to post no update for this run. `run` is a `run_update.Run`. Asked only when there is a database connection; an exception is logged as `run.after_run_error` and the update posts without the line |
| `approval_kinds()` | `{name: approvals.ApprovalKind}`, the approval kinds the agent owns (below). A kind that two plug-ins declare, or whose plug-in failed to load, fails closed |
| `privacy_terms(conn)` | `{"named_addresses": [], "companies": [], "owner_addresses": [], "kept_names": []}`: addresses that name a person (their names stay out of Discord), company names (never read as a person's name), Ting Yu's own addresses (removed outside Jura's own email) and names that are not a prospect's (Ting Yu's) |
| `REQUIRED_SETTINGS` | The `.env` settings the agent needs, by name. Each one not set is a setup gap in `jura-growth status` and the one-pager |
| `setup_gaps()` | `[health.Gap(name, ok=...)]` in place of `REQUIRED_SETTINGS`: names and booleans only, never a value. `Gap(name, ok=..., must_be_unset=True)` is a setting that must *not* be set (the publish job's `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN`), shown as "set, and must not be" |
| `health(conn)` | Extra "Needs you" lines for the one-pager. `conn` is the read model's read-only connection, so a write raises |

Every hook except `NAME` is optional and found with `getattr`. Its prompt goes in
`prompts/<job>.md`, its settings in `config/<name>.yaml`, and its hard limits in `caps.py`.

A quiet command job (`quiet: true`, such as `scout-send`) that finds nothing to do also leaves a
`run.quiet` event instead of a run row. `quiet` has no effect on a `claude` job, which always gets
its run row before Claude starts. Every run except a PAUSE-file skip ends with one call to
`run_update.after_run`, the core run update; the lock skip passes no database connection. A
precheck that raises (a typo in an agent's config) is a failed run, with its row, `#alerts`, auto-pause
and run update. A job with `run_update: true` in `config/settings.yaml` (scout-research, social,
community and app-factory) posts one run update to its agent's `RUN_UPDATE_DISCORD_CHANNEL`: status,
start, length, cost and run id, the error in one line for a failed run, the summary as a quote of at
most `caps.RUN_UPDATE_TEXT_CHARS` characters (without the lines the error already shows),
"Produced:" and the approval requests the run raised. A skip posts its reason, and a quiet run
"nothing to do". Any other exception out of the runner (a database or programming error) posts none.
A job with `run_update: claimed-only` (publish) posts only when its plug-in's `run_update()` gives
"Produced:" items, which the publish plug-in does only for a run that claimed an item: never for a
skip, a quiet run or the lock skip.

A job's keys in `config/settings.yaml`: `agent`, `kind` (`command` or `claude`), `command` or
`prompt`, `schedule` (the shapes in `jura_growth/schedule.py`, including `daily_every` for a
repeating daily slot), and optionally `tools`, `disallowed_tools`, `model`,
`quiet`, `run_update` (`true` or `claimed-only`) and `browser` (`true` only for a job in
`caps.BROWSER_JOBS`; any other job that sets it fails).

### Approval kinds

Every outward action (an email, a post, a group join, an app build or release) is a gated action:
it claims a matching approval with `approvals.use(conn, kind, subject, run_id=…)` inside its own
`db.transaction(conn)`, writes its in-flight marker in the same transaction, and makes the outward
call only after the commit (ADR 0003). `use()` raises `approvals.NotApproved` unless the request is
approved, before its use-by, unused and matching what the kind computes now, and while neither the
PAUSE file, the agent's pause flag nor the kind's own switch stops it. Catch it inside the `with`
block so the lapse or supersede it wrote is kept. A gated command raises its request with
`approvals.request(conn, kind, subject, reason=…, run_id=…)`; it never passes a hash.

A kind is an object with:

| Member | Purpose |
|---|---|
| `name` | The kind's name, the key in `approval_kinds()` |
| `content(conn, subject)` | The exact bytes of what would go out now, with no Unicode normalisation (UTF-8, JSON with sorted keys; ADR 0003), or `None` when the item is gone |
| `preview(conn, subject)` | An `approvals.Preview`: title, text as it will go out, reason, at most ten files |
| `deadlines(conn, subject, now)` | An `approvals.Deadlines`: asked at request time for the decide-by and at approval time for the use-by (`None` for a kind applied on decide). `caps.APPROVAL_DEADLINE_MAX_DAYS` caps both |
| `decision_args` | Optional. The `key=value` arguments an approve must carry, such as `("promo_days", "post_days")` |
| `args_help` | Optional. The refusal text when one of them is missing |
| `on_approve(conn, subject, args)` | Optional. Applies the change inside the decision's transaction, after `approved` is written. Raise `approvals.BadArgs(text)` to refuse with that text; a `NotApproved` from a claim inside it also refuses. A returned string is appended to the answer |
| `switched_off(conn, subject)` | Optional. The kind's own switch (outreach in shadow mode, a platform in draft or switched off): a reason makes `use()` refuse without claiming |
| `on_skip`, `on_expire`, `on_lapse` | Optional, `(conn, subject)`. What a skip, an unanswered decide-by and an unclaimed use-by do to the item |
| `superseded_note(conn, subject)` | Optional. Why the item changed or went away, in Ting Yu's words ("lead unsubscribed"), for the card's edited first line; `None` keeps the core's reason |
| `used_word` | Optional. How the answer to a decision on a used request names the use ("already sent at 10:40"); "used" by default |

The outreach plug-in's `outreach-email` kind (`agents/outreach/approval.py`) is the worked example:
requests are raised only in live mode, only for emails due today and only up to today's remaining
quota (MC §4.6 A14), and `send-due` claims before it calls Resend. The community plug-in's
`group-rules` kind (`agents/community/group_rules.py`) is the example of a kind applied on
decide: its approve takes `promo_days=` and `post_days=`, and `on_approve` claims the request and
sets the group's confirmation and days in the decision itself.

## Tests

```bash
uv run pytest
```

Tests never touch `jurasolutions/data/`, Discord, launchd or the network. `conftest.py` points
every path at a temporary folder, including rendered plists (`JURA_GROWTH_PLIST_DIR`) and a copy
of `prompts/` (`JURA_GROWTH_PROMPTS_DIR`). Its write guard is an audit hook that refuses, and
fails the test for, any write the test process makes into this repo or under `jurasolutions/`:
opening a file for writing, creating, removing, renaming or truncating it, changing its mode or
times, and opening a SQLite file there at all. It doesn't see writes made by subprocesses, or
operations relative to an open folder (`dir_fd`, as inside `shutil.rmtree`), and it allows
`__pycache__/` and `.pytest_cache/`.

A second audit hook, the network guard, refuses and fails the test for every DNS lookup
(`socket.getaddrinfo`) and connection (`socket.connect`) the test process makes outside loopback.
Unix sockets, `127.0.0.0/8`, `::1`, `localhost` and `*.localhost` are allowed. A test that
provokes either guard on purpose takes the `write_guard` or `network_guard` fixture and calls its
`take()`, so its own refusals don't fail it. Like the write guard, it doesn't see subprocesses.

A test that posts to Discord uses the Discord double (`tests/discord_double.py`): every webhook
points at `discord.invalid` and each request is recorded. A test that builds a Discord message
plants the secrets and personal data in `tests/sweep.py` where its builder reads, then calls
`assert_clean(double, outbox, planted)` from its own file.
