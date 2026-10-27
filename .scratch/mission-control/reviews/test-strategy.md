# Mission control: test strategy

QA lead, 2026-10-25. Spec: `jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md`
(pending sign-off). Constraints and the tests they require: `reviews/round-2-decisions.md`. Test
tooling: `scout/` (no Playwright; headless Chrome through the `agents/social/render.py`
pattern). Terms follow `CONTEXT.md`.

## Seams

There is no `reviews/technical.md` yet. This strategy uses the seams the tech lead named in
round 2 (C6) and the PRD (§4.8, §5.2). When `technical.md` is written, any seam that differs from
the list below becomes a question rather than a silent change to this file.

| Seam | What it is | Tests reach it by |
|---|---|---|
| S1 classifier | `classify(schedule, records, now) -> slot statuses`. Pure | Calling it with literal records. No database, no files |
| S2 read model | `jura_growth/mission.py`: read-only connection, data folder, clock in; plain dataclasses out | Calling it against a temp `growth.db` built by the normal migrations |
| S3 handler | `jura_growth/mission_server.py` on `ThreadingHTTPServer` | `http.client` against the server on port 0 in a thread, same process, so the conftest write guard sees every write |
| S4 health | `jura_growth/health.py`: `setup_gaps()`, install state, strip items | Calling it directly, and through `jura-growth status` with click's `CliRunner` |
| S5 markdown | `jura_growth/markdown.py`, the one `MarkdownIt("js-default")` | Calling its render function |
| S6 runner | `runner._run_locked` early return | `runner.run()` in-process on a fake quiet command job in a temp config, the way `tests/test_core.py` already does. Never `jura-growth run` |
| S7 browser | Headless Chrome via the `render.py` `_chrome()` pattern, with `--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"` and a temp profile | A subprocess pointed at the S3 server on loopback |
| S8 command | `jura-growth mission-control` as a real subprocess | `uv run jura-growth mission-control --no-open` with every data, outputs, config and launchd variable pointed at temp folders |

Proposed test files: `tests/test_mission_slots.py` (S1), `tests/test_mission_read.py` (S2),
`tests/test_mission_server.py` (S3), `tests/test_mission_health.py` (S4),
`tests/test_markdown.py` (S5), the runner cases in `tests/test_core.py` or
`tests/test_runner_quiet.py` (S6), `tests/test_mission_browser.py` (S7) and
`tests/test_mission_cli.py` (S8). Shared fixture builders live in one helper module, for example
`tests/mission_world.py`.

## Test data

Every dataset is built inside the test's `tmp_path` by the autouse `isolated` fixture's temp
folders. None of them is ever copied from, or pointed at, the live `jurasolutions/data/growth/`.

| Id | Dataset | Contents |
|---|---|---|
| D1 | **Fortnight** | Clock frozen at `JURA_GROWTH_NOW=2026-11-11T10:05:00+08:00` (a Wednesday). The 14 days from 2026-10-29 hold two weekends, Deepavali on Sunday 2026-11-08 and its observed Monday 2026-11-09, from `config/sg-public-holidays.yaml`. Jobs get their first record on different days, so earlier slots are "not installed". Contains ok, failed and running runs; a `log.skip_run` skip row; quiet `run.skipped` and `run.quiet` events; a PAUSE-file skip and a "previous run still going" skip in the JSONL mirror only; a Mac-slept-through-three-scout-send-slots gap with a late run after wake; an app-factory 06:30 slot whose run started at 08:10; a backup 23:30 run that finished after midnight; a scout-send Friday 16:30 slot whose window runs over the weekend to Monday; a community weekly slot; costs and permission denials; a run on 2026-04-25 whose transcript is gone (pruned) and a recent run whose transcript is present |
| D2 | **Secrets** | A configured value for `RESEND_API_KEY_OUTREACH` and `DISCORD_WEBHOOK_ALERTS` set through the temp `JURA_GROWTH_ENV_FILE`. One value contains `&`, `<` and `"` so its HTML-escaped and URL-encoded forms differ from the raw form. One token-shaped string per `config._SECRET_VALUES` pattern (`re_…`, `sk-ant-…`, `whsec_…`, `Bearer …`, a Discord webhook URL). One `keychain:jura-mc-test-service` value, plus a fake Keychain-resolved value added to the resolved set. Planted, by raw SQL so `log.event`'s own redaction is bypassed (as in data written before ticket 01), in: `runs.summary`, `runs.error`, `events.payload`, a JSONL mirror line, a transcript file, `outreach_messages` subject, `body_text` and `body_html`, a `leads` field, `social_posts`, `community_posts`, an app PRD under the temp `JURA_PRD_DIR`, a digest, and a `discord-outbox/` file |
| D3 | **Hostile** | `<script>` and `"><img src=x onerror=…>` in a run summary, an event payload, a job error and a lead name. An email `body_html` that sets `data-ran="yes"` on `<body>` from a script, carries a visible `<p id="mc-loaded">` marker, and also holds `<img src="/beacon-img">`, `<link rel="stylesheet" href="/beacon-css">`, `<meta http-equiv="refresh" content="0;url=/beacon-nav">` and `<form action="/beacon-form">`. A PRD with `<script>…</script>`, `<img src=x onerror=…>`, `[x](javascript:alert(1))`, `[x](JaVaScRiPt:…)`, `[x](&#106;avascript:…)`, `[x](vbscript:…)`, `[x](data:text/html,…)`, `<javascript:alert(1)>`, a raw `<iframe>`, and a GFM table. Allowlisted roots containing `..` names, a symlink to a temp `.env`, a file named `.env`, a `.dev.vars`, and a design-system path outside the allowlist (`README.md`, `_ds_bundle.js`, a `ui-kit/` page) |
| D4 | **Stale journal** | A `growth.db` and `growth.db-journal` pair copied while a write transaction is open on another connection, with the cache shrunk (`PRAGMA cache_size = 1`) and enough rows written that pages spill to the database file before commit. The fixture proves itself hot: a throwaway copy opened read-write by plain `sqlite3` rolls back and removes its journal. If that self-check fails, the fixture errors and the dependent tests fail; they never pass vacuously |
| D5 | **Empty and part-migrated** | No `growth.db` at all; and a `growth.db` with only the core migrations, so plug-in tables (`outreach_messages`, `social_posts`, `community_posts`, `leads`) and their `schema_migrations` rows are absent |
| D6 | **launchd** | A temp `JURA_GROWTH_LAUNCH_AGENTS` folder holding a current plist for one job, an out-of-date plist (different hour) for another, and none for a third. `schedule._launchctl` is monkeypatched to answer `print` with exit 0 or 113 per job and to fail the test on any other verb. `schedule.render` and `schedule.install` are monkeypatched to fail the test if called |

## Coverage map

One or more rows per success criterion in PRD §2. "Seam" refers to the table above.

| # | Criterion (PRD §2) | Level | Seam / location | Data | Automated? |
|---|---|---|---|---|---|
| 1a | Command binds `127.0.0.1:<mission_control.port>` from `settings.yaml` and nothing else; prints its URL through `redacted_output()` | end to end | S8: subprocess with a temp `JURA_GROWTH_CONFIG_DIR` whose port is a free port the test picked; assert the printed URL, a GET on it, and `server_address[0] == "127.0.0.1"` in the in-process S3 case | D1 | yes |
| 1b | Opens the browser unless `--no-open` | unit | S8 command function with `webbrowser.open` monkeypatched: called once with the URL without the flag, never with it | none | yes |
| 1c | Stops when the terminal closes | end to end | S8: send SIGHUP, then SIGINT in a second case; the process exits within 5 s and the port is free again | D1 | yes |
| 1d | Port taken: exits with a clear message and never picks another port (PRD §6 Q1, if accepted at G2) | end to end | S8 with the port held by a test socket | none | yes |
| 1e | No login | manual UAT | U1 | live | recorded manual |
| 2a | Every page load reads fresh through a read-only connection | integration | S3: change a row between two GETs, second response shows it. S2: monkeypatch `db.connect`, `db.session` and `paths.writable` to fail the test, then hit every route | D1 | yes |
| 2b | **Never writes**: snapshot of file list, sizes and mtimes of the temp data, outputs, PRD, LaunchAgents and plist folders before and after every route, including HEAD | integration | S3, parametrised over the route list (one case per route the router knows; a test fails if a route is added without a case) | D1, D2, D3, D5 | yes |
| 2c | Stale journal: page and strip show "growth.db has an unfinished write. Run `jura-growth status` once in Terminal."; folder unchanged, journal included | integration | S3 home, day and run routes, plus S2 directly | D4 | yes |
| 2d | `database is locked` shows the same message, not a 500 | integration | S3 while another connection holds `BEGIN EXCLUSIVE`; response arrives within 4 s | D1 | yes |
| 2e | The connection closes before rendering | integration | S3 with the render step wrapped so it first runs `BEGIN EXCLUSIVE; ROLLBACK` on a second connection with `timeout=0`; that must succeed | D1 | yes |
| 3a | Home page has a today board and a 14-day job-by-day grid; scout-send is one row per day, and its cell follows the G2 answer to §6 Q2 (recommended: worst status wins, counts per status on hover text and the day page) | integration | S2 grid data; S3 checks one row per job per day in the markup | D1 | yes |
| 3b | Drill day → slots → run, across full history | integration | S3: follow links from `/` to `/day/2026-11-06` to a `/run/<id>`; `/day/2026-04-25` reaches the old run | D1 | yes |
| 3c | Unknown run id, malformed date or a future date: 404 with an escaped page, never a 500 | integration | S3 | D1, D3 | yes |
| 4a | Classifier: one table row per slot status (ok, failed, skipped with each reason, running, missed, upcoming, not installed, and **due** if §6 Q3 is accepted) | unit | S1 table test | literal records | yes |
| 4b | A quiet run (`run.quiet`) is ok, never missed | unit | S1 | literal | yes |
| 4c | Mac slept through three slots: the earlier two missed, the last ok | unit | S1 | literal | yes |
| 4d | A late run after wake counts for its slot; a run after the next slot has passed belongs to the next slot | unit | S1 | literal | yes |
| 4e | Slots before a job's first run, skip or quiet trace are not installed | unit | S1 | literal | yes |
| 4f | A business-day job has no slots on a weekend or a public holiday, including an observed Monday | unit | S1, using the real `holidays.is_business_day()` | D1 dates | yes |
| 4g | Window edges: backup 23:30 run finishing after midnight; Friday 16:30 scout-send window running to Monday 09:30; weekly community window; a slot exactly at `now` is upcoming, not missed | unit | S1 | literal | yes |
| 4h | Skips found only in the JSONL mirror (PAUSE file, "previous run still going") show as skipped with their reason; a truncated last JSONL line or a missing day file is ignored, not a crash | integration | S2 reading `runs/YYYY-MM-DD.jsonl` | D1 | yes |
| 4i | Same statuses whatever the Mac's own timezone | unit | S1 and S2 parametrised over `TZ` in `Asia/Singapore`, `UTC`, `America/New_York` (with `time.tzset()`) | D1 | yes |
| 4j | Unloaded job with history (§6 Q7): past slots follow the normal rules, upcoming ones show not installed | unit | S1 with an install-state input | literal | yes |
| 5a | Run page shows status, error, duration, cost, permission denials, events, readable transcript, artifacts | integration | S2 per field, S3 for presence in markup | D1 | yes |
| 5b | "transcript pruned" for a run past the 30-day retention; a recent run with a missing transcript says something different | integration | S2 and S3 | D1 | yes |
| 5c | Run pages read only the transcript they need; the home and day pages read none | integration | S3 with an audit-hook spy recording `open` calls under `data/growth/transcripts` | D1 | yes |
| 5d | Emails, Posts and PRDs lists exist, and link emails to runs as decided at G2 (§6 Q5, Q6; recommended: Posts = `social_posts` + `community_posts`, emails by `leads.run_id` or the `sent_at` window) | integration | S2 and S3 | D1 | yes |
| 5e | Absent plug-in tables show "not migrated yet" on their panel; no `growth.db` says so; the server never migrates (`schema_migrations` unchanged) | integration | S2 and S3 | D5 | yes |
| 6a | Email body route sends exactly `Content-Security-Policy: sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` | integration | S3 | D3 | yes |
| 6b | The shell embeds the body only as `<iframe sandbox src=…>`, with an empty `sandbox` value and no `allow-` token anywhere in any response | integration | S3, parsing the markup with `html.parser` | D3 | yes |
| 6c | **Browser sandbox**: loading the body route, Chrome shows the `mc-loaded` marker (page loaded) and `<body>` has no `data-ran` attribute; matched on the rendered element, not the script source | end to end | S7 `--dump-dom` | D3 | yes |
| 6d | No request from the email body reaches the server: the S3 access log has no `/beacon-*` hit after the S7 load of the shell page and of the body route | end to end | S7 against S3 | D3 | yes |
| 6e | The plain-text body sits beside the frame, escaped | integration | S3 | D3 | yes |
| 7a | PRDs and digests render as markdown, tables included | integration | S5 and S3 `/prds/<id>`, `/digests/<date>` | D3 table | yes |
| 7b | Every hostile construct in D3 comes out inert: no `<script`, no `<iframe`, no `on…=` attribute, no `href` or `src` beginning with a script or `data:text/html` scheme after HTML-unescaping and lowercasing | unit | S5, table test, one row per construct | D3 | yes |
| 7c | One instance only: exactly one `MarkdownIt(` in `jura_growth/`, constructed with `"js-default"`, no `.use(`, no `linkify`, no `validateLink` assignment; markdown output never reaches the email-body route | unit | a source-scanning test over `jura_growth/` | none | yes |
| 7d | `markdown-it-py==4.2.0` pinned in `pyproject.toml`; `uv.lock` has 4.2.0 and `mdurl` 0.1.2 with hashes | unit | a test reading `pyproject.toml` and `uv.lock` | none | yes |
| 7e | Redaction runs before parsing | integration | S5 with a D2 value split across a markdown emphasis boundary, so masking after parsing would miss it | D2 | yes |
| 8a | **No secret reaches a page**: every D2 value, in raw, HTML-escaped and URL-encoded form, is absent from every response body and header on every route, including file routes and error pages | integration | S3 sweep, parametrised over the route list as in 2b | D2 | yes |
| 8b | File routes that serve text from transcripts and digests redact too | integration | S3 `/files/data/growth/transcripts/…` and `/files/…/digests/…` | D2 | yes |
| 8c | Setup gaps show only names and booleans: each gap line matches `NAME: set`, `NAME: not set` or `Discord: n of 8 webhooks`; no value, no first four characters of a value, no `keychain:` service name | unit | S4 | D2 | yes |
| 8d | A Keychain-resolved value is masked; Keychain is never read just to mask (per §6 Q8) | unit | S4 and S2 with a fake resolved secret; `security` is monkeypatched to fail the test if called | D2 | yes |
| 9a | Strip item per kind: PAUSE file, paused agents, recent failures, missed slots (windows per G2 answer to §6 Q4), undelivered Discord posts (`delivered = 0` rows plus `discord-outbox/` files), jobs not installed, jobs installed but out of date, setup gaps, today's spend, unfinished write | integration | S4 and S2, table test with one row per item, present and absent | D1, D4, D6 | yes |
| 9b | Out-of-date compares `plistlib.load()` with in-memory `schedule.plist()`; never calls `render()` or `install()`; `launchd/generated/` is never created; `launchctl print` called once per job per request | integration | S4 | D6 | yes |
| 9c | `jura-growth status` and the strip list the same gaps from one fixture | integration | S4: the gap lines from `CliRunner` output equal the strip's gap items | D2, D6 | yes |
| 9d | `jura-growth status` output is unchanged apart from reading through the shared function | integration | S4 golden test: the output on the D1+D6 fixture, with temp paths normalised, matches a golden file captured from `main` before the change | D1, D6 | yes |
| 9e | Today's spend is the sum of today's recorded `cost_usd` in SGT, never a projection | unit | S2, with runs either side of SGT midnight | D1 | yes |
| 10a | GET and HEAD only: POST, PUT, DELETE, PATCH, OPTIONS and an unknown verb each get 405 on every route; HEAD has no body | integration | S3 | D1 | yes |
| 10b | Own Host only: `127.0.0.1:<port>` and `localhost:<port>` accepted; a foreign host, a wrong port, a bare `127.0.0.1`, an absent Host and a duplicated Host each get 421 | integration | S3 with raw request lines | none | yes |
| 10c | No route serves the repo root, `.env*`, `.dev.vars`, `..`, percent-encoded or double-encoded `..`, an absolute path, a symlink leaving its root, or a design-system file outside `styles.css`, `tokens/*.css`, `assets/*.svg`; all get 404 or 403 with no file content | integration | S3, table test | D3 | yes |
| 10d | Served SVG carries the sandbox CSP; the shell CSP is exactly the PRD §4.5 string, with font hosts only there | integration | S3 | none | yes |
| 10e | Actions are text only: no `<form`, `<button` or `<script` in any response; every command shown parses as a real `jura-growth` command (each is resolved with click's `make_context` without being invoked) | integration | S3 sweep plus a click resolution test | D1, D6 | yes |
| 10f | No response references `unpkg.com`, `@latest` or a remote script | integration | S3 sweep | D1 | yes |
| 11a | `<meta http-equiv="refresh" content="60">` on home, today's day page, and a run whose status is `running` | integration | S3 with the frozen clock | D1 | yes |
| 11b | No refresh on past days, finished runs, lists, PRDs, emails or the body route | integration | S3 sweep | D1 | yes |
| 12a | At 360px, no horizontal page scroll; the 14-day grid scrolls inside its own container | end to end | S7: the test fetches the real page over HTTP, writes it to a temp file with one appended measuring script and absolute CSS URLs to the S3 server, loads it with `--dump-dom --window-size=360,800`, and reads `documentElement.scrollWidth <= innerWidth` from an attribute the script sets. The test asserts the script ran before reading the result. The served pages themselves never carry a script | D1 | yes |
| 12b | Interactive targets are at least 44 by 44 px at 360px | end to end | S7, same harness, measuring every `a` and `summary` | D1 | yes |
| 12c | Design-system tokens only: mission control's own CSS has no hex, `rgb(`, `hsl(` or named colour literals outside `var(--…)`; it links `design-system/styles.css` through `/ds/` | unit | a source-scanning test over the mission control stylesheet | none | yes |
| 12d | Slot status is never colour alone: each grid and board cell carries its status word as text or `title` | integration | S3 | D1 | yes |
| 12e | Desktop layout, white first, green used sparingly, reads like the design system | manual UAT | U5, plus `crew:web-design-review` at code review | live | recorded manual |
| 13a | `uv run pytest` passes | gate | full suite | all | yes |
| 13b | The suite leaves `git status` and the live `jurasolutions/data/` and `outputs/` unchanged | gate | the conftest write guard (ticket 08) fails any test that writes there; the gate also compares a stat-only snapshot of the live folders, taken without opening any file, before and after the run | none | yes |

### Runner change (PRD §4.4, the one write)

| # | Case | Level | Seam | Automated? |
|---|---|---|---|---|
| R1 | A quiet job that succeeds with nothing to do writes exactly one `run.quiet` event with payload `{"job": <name>}`, no `runs` row, no `discord_posts` row and no outbox file; `schema_migrations` unchanged | integration | S6 | yes |
| R2 | A quiet job that succeeds with a summary writes a run row and no `run.quiet` | integration | S6 | yes |
| R3 | A quiet job that fails writes a run row, alerts as today, and no `run.quiet` | integration | S6 | yes |
| R4 | A quiet job skipped by precheck or schedule writes `run.skipped`, not `run.quiet` | integration | S6 | yes |
| R5 | A non-quiet job never writes `run.quiet` | integration | S6 | yes |
| R6 | The existing outreach send, sync and core tests still pass unchanged (scout-send is the quiet job and it sends email) | integration | existing suite | yes |
| R7 | A `run.quiet` written by R1 is classified ok for its slot, end to end from runner to classifier | integration | S6 then S2 | yes |

## Risk-based depth

Riskiest first. Each has negative cases and at least one end-to-end path.

1. **Damaging `growth.db` (data loss).** A writable open would roll back a hot journal and could
   race scout-send. Negative cases: 2b on every route, 2c with a self-verifying hot journal, 2d,
   2e, 5e (never migrates), and the monkeypatched `db.connect`/`db.session`/`paths.writable`
   in 2a. End to end: S8 subprocess against D4, then the snapshot.
2. **A secret on screen.** Transcripts written before ticket 01 can hold raw keys. Negative
   cases: 8a in three encodings on every route, 8b file routes, 8c shapes, 8d Keychain, 7e
   redact before parse. End to end: the S7 dump of the run page and email page for D2 contains
   no D2 value.
3. **Untrusted HTML running script.** Email bodies are model-written; summaries and lead names
   come from the web. Negative cases: 6a, 6b, 7b, 7c, the D3 escaping cases in 3c, and
   `<script>` in every stored field. End to end: 6c and 6d in Chrome.
4. **Serving a file it shouldn't.** Negative cases: the whole 10c table. End to end: S8 GET of
   `/files/../.env` returns no content.
5. **Reachable beyond this Mac, or changing state.** Negative cases: 10a, 10b, 10e. End to end:
   S8 checks the bound address.
6. **The runner change breaking scout-send.** It is the only write and it sits on the job that
   sends email. Negative cases: R2 to R5. End to end: R7, plus R6.
7. **Misreading the engine.** A quiet run shown as missed, or two weeks of red, leads Ting Yu
   to chase ghosts. Negative cases: 4a to 4j. End to end: 3b drill on D1, and U2 on live data.
8. **`jura-growth status` drifting.** Negative cases: 9c, 9d. End to end: U4.

## Non-functional

- **Performance (implied by "reads stay short").** Measured deterministically, not by timing:
  one connection per request, closed before rendering (2e); no transcript opened by home or day
  pages and one by a run page (5c); the locked case answers within the 2 s busy timeout plus
  margin (2d). Wall-clock times on a large database are recorded in U3, not gated.
- **Security.** Covered by risks 1 to 5. `security-review` runs on `mission.py`,
  `mission_server.py`, `health.py` and `markdown.py` at code review.
- **Accessibility (WCAG AA for an internal page).** 44px targets (12b), status not by colour
  alone (12d), tokens only so contrast comes from the design system (12c). Keyboard focus
  visibility is checked in U5 and by `crew:web-design-review`.
- **Browser matrix.** Google Chrome headless only, automated. Ting Yu's everyday browser is
  checked in U6. See the gap below.
- **Concurrency.** One S3 case fires ten simultaneous GETs at `ThreadingHTTPServer` and expects
  ten 200s and an unchanged snapshot.
- **Migration and rollback.** No migration is added. R1 asserts `schema_migrations` is unchanged.
  Rollback is reverting the merge; an older checkout ignores `run.quiet` events.

## Manual UAT script (Ting Yu, on this Mac, live data)

Mission control is read-only, so these steps are safe on live data. Record each as pass or fail
with a note in `reviews/qa-NN.md`.

- **U1.** Run `uv run jura-growth mission-control`. The browser opens at
  `http://127.0.0.1:<port>`, with no login. Bookmark it. Close the terminal tab; the bookmark
  no longer loads.
- **U2.** Compare this week's today board and grid with what you know ran, and with
  `jura-growth status`. A scout-send day with nothing to send shows ok, not missed.
- **U3.** During business hours, leave the home page open for 30 minutes while scout-send runs.
  Afterwards, no scout-send run in that window failed with `database is locked`. Note how long
  the home page takes to load.
- **U4.** Run `jura-growth status`. Its setup gaps match the health strip.
- **U5.** Open yesterday's scout-research run and one outreach email. Narrow the window to about
  360px. Tab through the page and check focus is always visible. Judge the look against the
  design system.
- **U6.** If your everyday browser is not Chrome, open one outreach email and one PRD in it.

## Not tested, and why

| Gap | Why | Risk accepted by |
|---|---|---|
| Real `launchctl` and real installed plists | Tests must not depend on, or touch, the Mac's launchd. Monkeypatched in D6; U1, U2 and U4 see the real state | Ting Yu at G4 |
| Real Keychain reads | Tests never call `security`. A fake resolved value stands in (8d) | Ting Yu at G4 |
| Browsers other than Chrome (Safari in particular) | Only Chrome is scriptable here without Playwright, which the scout rejected. Two independent layers protect the email body (the `sandbox` CSP header and the `sandbox` iframe attribute), and both are long supported in Safari. U6 is a visual check only; it does not plant a script | Ting Yu at G4 |
| Google Fonts actually loading | Browser tests block all hosts except loopback. Fallback fonts are used in S7; U5 sees the real fonts | QA lead |
| Real DNS rebinding | The Host allowlist is the control and 10b tests it; a real rebinding attack needs external DNS | QA lead |
| Visual fidelity beyond tokens and layout measures | Not mechanically checkable; U5 and `crew:web-design-review` cover it | Ting Yu at G4 |
| Wall-clock performance on the live database | Timing tests flake; deterministic proxies gate it instead (see Non-functional) | QA lead |
| Holidays after 2027 | `config/sg-public-holidays.yaml` covers 2026 and 2027; the existing `holidays.coverage_warning()` flags the gap | existing behaviour |

## Severity

- **Critical:** any write to `growth.db`, its journal, the live data or outputs folders, the
  repo, `inputs/` or `design-system/` by the server or a test; any D2 value in a response; a
  script running in a served page or the email frame; a file outside the allowlist served; a
  non-loopback bind or a foreign Host answered; any route that changes state.
- **Major:** any coverage-map row failing that is not critical; a 500 on any route; a wrong slot
  status; the R2 to R6 runner regressions; `status` and the strip disagreeing.
- **Minor:** copy, spacing or visual issues that keep every row passing.

## Exit criteria

The quality gate applies these to `crew/mission-control` at its head commit. Each is checkable
without judgement.

1. **Dependencies landed.** `git merge-base --is-ancestor <sha> main` succeeds for the merge
   commits of blocker tickets 01, 03 and 08, and the same holds for `main`'s commit at the
   branch point of `crew/mission-control`.
2. **Every row traced.** Every row in the coverage map and the runner table (1a to 13b, R1 to
   R7) names at least one passing test node id, or, for 1e and 12e, a passed UAT step, recorded
   in a `reviews/qa-NN.md`. A row with no case is a failed criterion.
3. **Fresh suite.** `uv run pytest -rs` run by the gate: 0 failed, 0 errors, more than 693
   passed (the 2026-10-25 baseline on `crew/growth-blocker-fixes`), and **0 skipped** among
   `tests/test_mission_*.py` and `tests/test_markdown.py`. A browser test skipped because Chrome
   was not found counts as not run.
4. **Fixtures prove themselves.** The D4 hot-journal self-check and the S7 "page loaded" and
   "measuring script ran" assertions exist in the code and pass (named in the QA report).
5. **Nothing touched.** `git status --short` is identical before and after the gate's suite run.
   A stat-only snapshot (path, size, mtime, by `find … -exec stat`, opening no file) of
   `jurasolutions/data/growth/` and `jurasolutions/outputs/growth/` is identical before and
   after. The gate runs the suite in a window where no job has a slot (outside 06:20 to 07:40,
   08:50 to 16:55 on business days, 11:50 to 12:10, 17:20 to 17:40 and 23:20 to 23:40 SGT), and
   `pgrep -f "jura-growth run"` prints nothing both before and after, so no live job can explain
   a change.
6. **Structure holds.** Each of these greps, over `jura_growth/mission.py`,
   `jura_growth/mission_server.py`, `jura_growth/health.py` and `jura_growth/markdown.py`,
   returns no hits: `db.connect`, `db.session`, `paths.writable`, `immutable=1`,
   `journal_mode`, `schedule.render`, `schedule.install`, `SimpleHTTPRequestHandler`,
   `taskwise`, `zenexflow`. `grep -rn "MarkdownIt(" jura_growth` returns exactly one line, and it
   contains `"js-default"`. No mission control template or stylesheet contains `<script`,
   `unpkg` or `@latest`.
7. **One new runtime dependency.** The diff of `[project].dependencies` in `pyproject.toml`
   against `main` adds only `markdown-it-py==4.2.0`; `uv.lock` lists `markdown-it-py` 4.2.0 and
   `mdurl` 0.1.2 with hashes; neither `playwright`, `pytest-playwright`, `jinja2`, `markupsafe`,
   `nh3` nor `bleach` appears in `uv.lock`.
8. **Defects.** Zero open critical or major defects under `issues/`. Each open minor one is listed
   in the gate with an owner.
9. **Code review.** Every `reviews/code-review-NN.md` for the feature's tickets ends in an approve
   verdict with no open blocking finding, and the reviews include a `security-review` pass on
   the four modules in criterion 6 and a `crew:web-design-review` pass on the templates and
   stylesheet.
10. **Typecheck (advisory, per the operating card).** `pyright --pythonpath .venv/bin/python`
    reports 0 errors in the new modules, and no more errors in total than on `main` at the branch
    point.
11. **UAT.** U1 to U6 recorded as passed in a `reviews/qa-NN.md`, or explicitly waived by Ting Yu
    at G4.

## Depends on G2

These rows encode the PRD §6 recommendations. If Ting Yu answers differently at G2, the row's
expected values change and this file is updated before tickets are cut: 1d (§6 Q1), 3a (Q2), 4a
the **due** status (Q3), 9a windows (Q4), 5d (Q5, Q6), 4j (Q7), 8d (Q8).
