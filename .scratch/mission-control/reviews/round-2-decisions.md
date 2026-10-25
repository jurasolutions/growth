# Mission control: interview round 2 decisions

Tech lead, 2026-10-25. Ting Yu delegated Q8 to Q13 to the crew. Round 1 (`crew-log.md`) stands
and is not reopened. Terms follow `CONTEXT.md`.

## Decisions

**Q8. How the server runs: (a) on demand only in v1, with a fixed port.**
`jura-growth mission-control` binds `127.0.0.1:<mission_control.port>` from `settings.yaml`, opens
the browser (`--no-open` skips that), and stops when the terminal closes. An always-on KeepAlive
job does not fit `schedule.py`, which only knows calendar jobs, and `heartbeat` would count it as a
job. It would also be a long-lived process that resolves Keychain secrets for redaction. If Ting Yu
finds the command a chore, adding (b) later is one small ticket.

**Q9. Refresh: agreed.**
The home page, today's day page and any run still `running` reload every 60 seconds with
`<meta http-equiv="refresh" content="60">`. That needs no JavaScript, so `script-src 'none'`
stays. Finished run pages and past days never reload.

**Q10. Fonts: agreed.**
The shell CSP adds `https://fonts.googleapis.com` to `style-src` and `https://fonts.gstatic.com`
to `font-src`. The email-body route and any served SVG keep the sandbox CSP with no font hosts.
`Referrer-Policy: no-referrer` means Google never sees a mission control path.

**Q11. App PRDs: (a), markdown-it-py 4.2.0, under every condition on the scout card.**
Pin it exactly (`==4.2.0`, hashes in `uv.lock`), construct it only as `MarkdownIt("js-default")`,
and use no plugins and no linkify. Redact before parsing, and render digests the same way. A test
proves that a PRD containing `<script>` and a `javascript:` link comes out inert.

**Q12. Redaction: agreed, using ticket 01's `config.redact()` and nothing new.**
Every string read from `growth.db`, the JSONL mirror, transcripts, email bodies, PRDs and digests
goes through `config.redact()` before it is escaped or rendered. On the ticket 01 branch that
covers configured secret values (`secret_values()`) as well as token shapes. Mission control
never writes a redacted copy back to disk.

**Q13. Width: agreed.**
Lay it out for a desktop window, and keep it usable down to 360px with no horizontal page scroll.
Wide tables, such as the 14-day grid, scroll inside their own container. It uses 44px targets,
design-system tokens only, white first and green sparingly.

## Constraints for the PRD

### 1. Opening growth.db without ever writing to it

- **Never call `db.connect()` or `db.session()`.** Both go through `paths.writable()`, which runs
  mkdir, then set `PRAGMA journal_mode = DELETE` and run `migrate()`. The infra audit (A5) found
  that the first such open rolls back a hot journal.
- **Use one helper with one shape:**
  `sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)`, then `PRAGMA query_only = ON`.
  Open one connection per request, fetch everything into plain data, and close it before
  rendering. Never use `immutable=1`. Never issue a `journal_mode` pragma.
- **A stale journal is an error to show, never one to fix.** A read-only connection cannot roll
  back a hot journal; SQLite refuses with `SQLITE_READONLY_ROLLBACK`. The server catches that and
  `database is locked`, and serves a page and a health strip item: "growth.db has an unfinished
  write. Run `jura-growth status` once in Terminal." It never deletes or touches
  `growth.db-journal`.
- **A missing database or table is not a crash.** If `growth.db` doesn't exist, the page says so.
  If a table or migration the code expects is absent (check `schema_migrations`), that panel
  shows "not migrated yet" and the server does not migrate.
- **Readers block writers in rollback mode, so reads stay short.** `scout-send` writes every 10
  minutes. Keep the busy timeout short and use no long-running queries. Read only the transcript
  files a page needs.
- **A test proves the server never writes.** It snapshots the temp database folder (file list,
  sizes, mtimes) before and after every route, including the stale-journal case.

### 2. Reading launchd install state and setup gaps without exposing secrets

- **Install state** comes from `schedule.installed()`: the exit code of `launchctl print`, with
  its output thrown away. Call it once per job per request.
- **"Installed but out of date"** compares `plistlib.load()` of
  `~/Library/LaunchAgents/<label>.plist` with the in-memory `schedule.plist(job, spec)`. Never
  call `render()` or `install()`: `render()` writes into `launchd/generated/`.
- **Setup gaps are names and booleans only.** For example, "`RESEND_API_KEY_OUTREACH`: not set",
  "Discord: 3 of 8 webhooks". A value, a prefix, a length or a `keychain:` service name never
  reaches HTML.
- **One shared function.** Put this check in one function (for example `health.setup_gaps()`)
  that both `jura-growth status` and the health strip call, as Q7 settled.
- **What the server serves.** No route serves the repo root, `.env*` or `.dev.vars`. File routes
  take only the allowlisted roots on the scout card, through `resolve()` and `is_relative_to()`,
  and also pass ticket 01's path guard.

### 3. Telling a missed slot from a quiet run

- **Slots come from the existing code.** Expand them from `schedule.sgt_slots()` plus
  `holidays.is_business_day()`, in SGT. Use `timeutil.now_sgt()`, which honours `JURA_GROWTH_NOW`
  so tests can freeze the clock.
- **A slot owns the window from its own time up to the next slot of the same job.** It is
  missed only once that next slot has passed with nothing recorded in the window. A run launchd
  started late after a wake still counts for its slot. When the Mac slept through several slots,
  the earlier ones show as missed.
- **Today a quiet run leaves no trace at all, which makes it look missed.** When a quiet job
  succeeds with nothing to do, `runner._run_locked` returns without writing a row or an event.
  The PRD therefore carries one small runner change: write an append-only `run.quiet` event
  (`{"job": ...}`) to `events`, with no run row, no Discord post and no migration. This is the
  only write mission control adds, and it lives in the runner, not the server.
- **Two kinds of skip reach only the JSONL mirror.** The PAUSE-file skip and the
  "previous run still going" skip call `log.mirror()` and never touch the database (the PAUSE
  path is meant to skip it). The classifier therefore reads `runs/YYYY-MM-DD.jsonl` for the days
  it shows, as well as the `runs` and `events` tables.
- **Slots from before a job's first record show as "not installed", not "missed".** That covers
  any slot earlier than the job's first run, skip or quiet trace. It stops 14 days of red before
  the jobs were installed.
- **The classifier is pure.** It takes the schedule, the records and the clock, and returns slot
  statuses. It is the main test seam: table tests for each status, plus the
  slept-through-three-slots case.

### 4. Isolating HTML email bodies

- **Each `outreach_messages.body_html` is served at its own route** with
  `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:`
  plus `nosniff` and `no-referrer`. It is embedded only as `<iframe sandbox src=…>` with no
  `allow-*` token.
- **Redaction runs first,** and nothing else is done to the body: no sanitiser and no rewriting.
  Links inside the preview are inert by design. The plain-text body sits beside it, escaped.
- **The shell route is a separate page.** It keeps
  `script-src 'none'; frame-src 'self'; frame-ancestors 'none'; form-action 'none'`.
- **The server answers only its own Host.** Any Host other than `127.0.0.1:<port>` or
  `localhost:<port>` gets 421, and any method other than GET or HEAD gets 405.
- **A browser test proves the sandbox.** It runs headless Chrome via the `render.py` pattern with
  `MAP * ~NOTFOUND, EXCLUDE 127.0.0.1`. It first asserts the page loaded, then that a planted
  script did not run.

### 5. What mission control depends on from the blocker-fix branch

- **Ticket 01** (`crew/growth-blocker-fixes-01-headless-secrets`):
  - `config.redact()` with `secret_values()`, the masking of configured values. Without it, Q12
    masks only token shapes.
  - The path guard in `paths.py`, which refuses `.env*` and `.dev.vars`.
  - `redacted_output()`, if the `mission-control` command prints anything.
- **Ticket 03:**
  - `discord_posts.delivered = 0` now also means "Discord unreachable, saved to outbox". The
    "undelivered Discord posts" item counts those rows and the `discord-outbox/` files.
- **Ticket 08:**
  - The tests-never-touch-live-files rules apply to the new tests: temp data folders, and no
    `schedule.render()` into the repo.
- **Sequencing:** branch `crew/mission-control` from `main` only after the blocker fixes (at least
  01, 03 and 08) have merged. If they haven't, mission control is blocked rather than rebuilding
  the redaction itself.

### 6. Seam

There is one new deep module, a read model such as `jura_growth/mission.py`. It takes a
read-only connection, the data folder and the clock, and returns plain data for each page. The
HTTP handler is a thin adapter: routing, headers, escaping, templates. Tests call the read model
directly, and call the WSGI or handler app through `http.client` on port 0.
