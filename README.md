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
  discord-outbox/             messages for channels with no webhook yet
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
| `jura-growth status` | Pauses, last runs, schedule and Discord setup |
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
- Allowed: reading under `jurasolutions/`, `Bash(jura-growth:*)`, writing only in
  `data/growth/work/<job>/`, plus the job's own tools (web search and fetch).
- Refused: reading `.env`, `jura-growth run`, `resume` and `schedule`, and anything the job
  lists in `disallowed_tools` (the community job can't fetch facebook.com).
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
| `precheck(job, conn)` | A reason to skip a scheduled run before it starts, or `None` |

Its prompt goes in `prompts/<job>.md`, its settings in `config/<name>.yaml`, and its hard limits
in `caps.py`.

## Tests

```bash
uv run pytest
```

Tests never touch `jurasolutions/data/`, Discord, launchd or the network. `conftest.py` points
every path at a temporary folder.
