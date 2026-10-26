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
| `social` | 07:00 daily | headless Claude |
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
- `--max-budget-usd` per run (US$3 by default, US$5 for scout research).
- The full transcript is kept in `data/growth/transcripts/`, and permission denials are logged.

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
| `precheck(job, conn)` | A reason to skip a scheduled run before it starts, or `None`. Return `agents.NothingToDo("nothing due")` instead of a plain string when the run simply has nothing to do: the runner writes a `run.quiet` event with that reason and no run row (ADR 0001) |
| `permissions(job)` | For a `claude` job the agent runs: `headless.Permissions` with the `jura-growth` commands its prompt uses (and any extra Claude Code deny rules), or `None`. A job with no declaration may run no commands |
| `after_run(conn, job, run_id, outcome)` | Called after the job body of a run that started, before its run row is finished. Return a `runner.Outcome` to replace the outcome (the row, `#alerts` and auto-pause all see it), or `None` to keep it. An exception is logged as `run.after_run_error` and the outcome stands |
| `RUN_UPDATE_DISCORD_CHANNEL` | The Discord channel the agent's run updates go to, for example `social-drafts` |
| `run_update(conn, run)` | The "Produced:" items of the agent's run update (`["3 drafts", "3 images"]`; `[]` reads "nothing"), or `None` to post no update for this run. `run` is a `run_update.Run`. Asked only when there is a database connection; an exception is logged as `run.after_run_error` and the update posts without the line |
| `approval_kinds()` | `{name: approvals.ApprovalKind}`, the approval kinds the agent owns (below). A kind that two plug-ins declare, or whose plug-in failed to load, fails closed |
| `privacy_terms(conn)` | `{"named_addresses": [], "companies": [], "owner_addresses": [], "kept_names": []}`: addresses that name a person (their names stay out of Discord), company names (never read as a person's name), Ting Yu's own addresses (removed outside Jura's own email) and names that are not a prospect's (Ting Yu's) |
| `REQUIRED_SETTINGS` | The `.env` settings the agent needs, by name. Each one not set is a setup gap in `jura-growth status` and the one-pager |
| `setup_gaps()` | `[health.Gap(name, ok=...)]` in place of `REQUIRED_SETTINGS`: names and booleans only, never a value |
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
| `content(conn, subject)` | The canonical bytes of what would go out now (UTF-8, NFC-normalised, JSON with sorted keys), or `None` when the item is gone |
| `preview(conn, subject)` | An `approvals.Preview`: title, text as it will go out, reason, at most ten files |
| `deadlines(conn, subject, now)` | An `approvals.Deadlines`: asked at request time for the decide-by and at approval time for the use-by (`None` for a kind applied on decide). `caps.APPROVAL_DEADLINE_MAX_DAYS` caps both |
| `decision_args` | Optional. The `key=value` arguments an approve must carry, such as `("promo_days", "post_days")` |
| `args_help` | Optional. The refusal text when one of them is missing |
| `on_approve(conn, subject, args)` | Optional. Applies the change inside the decision's transaction, after `approved` is written. Raise `approvals.BadArgs(text)` to refuse with that text; a `NotApproved` from a claim inside it also refuses. A returned string is appended to the answer |
| `switched_off(conn, subject)` | Optional. The kind's own switch (outreach in shadow mode, a platform in draft): a reason makes `use()` refuse without claiming |
| `on_skip`, `on_expire`, `on_lapse` | Optional, `(conn, subject)`. What a skip, an unanswered decide-by and an unclaimed use-by do to the item |
| `superseded_note(conn, subject)` | Optional. Why the item changed or went away, in Ting Yu's words ("lead unsubscribed"), for the card's edited first line; `None` keeps the core's reason |
| `used_word` | Optional. How the answer to a decision on a used request names the use ("already sent at 10:40"); "used" by default |

The outreach plug-in's `outreach-email` kind (`agents/outreach/approval.py`) is the worked example:
requests are raised only in live mode, only for emails due today and only up to today's remaining
quota (MC §4.6 A14), and `send-due` claims before it calls Resend.

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
