# Mission control: technical review

Tech lead, 2026-10-25. Reviews `jurasolutions/prd/pending/prd-jura-mission-control-2026-10-25.md`
against the code on `crew/growth-blocker-fixes` (at `4a7859e`) and my round 2 decisions
(`reviews/round-2-decisions.md`). Terms follow `CONTEXT.md`; design terms follow mattpocock
`codebase-design` (module, interface, depth, seam, adapter).

## Verdict

The approach is sound. A read-only stdlib server, a deep read model behind one seam, a pure slot
classifier, and the browser enforcing isolation are all the right shape for one user on
loopback. Before sign-off, the PRD needs four changes (B1 to B4 below), and each has a fix. None of
them changes the scope.

The PRD carries C1 to C6 and Q8 to Q13 faithfully, with three exceptions. One is my own error in
round 2 (B1). One comes from a commit that landed after round 2 (B2). The third is a wording slip
that would cause a bug (B3).

Evidence for this review:

- `uv run pytest` on `crew/growth-blocker-fixes`: 693 passed in 25.5s. `git status` showed only
  the untracked crew files afterwards.
- A scratch probe outside the repo with SQLite 3.53.1 (Python 3.12.14) settled the stale-journal
  case that round 2 left untested:
  - `file:…?mode=ro` against a hot journal raises
    `OperationalError: attempt to write a readonly database`, with
    `sqlite_errorname == "SQLITE_READONLY_ROLLBACK"`. Both `hot.db` and `hot.db-journal` were
    byte-identical afterwards.
  - A missing file raises `SQLITE_CANTOPEN` and creates nothing.
  - The §5.3 recipe for building a hot journal works: copy the db and its journal while a
    `BEGIN IMMEDIATE` write is open.
  - So C1 holds as written. No prototype is needed.

## Fidelity check: PRD against the round 2 decisions

| Decision | In the PRD | Note |
|---|---|---|
| Q8 on demand, fixed port | SC1, §3, §5.1 | Faithful |
| Q9 meta refresh | SC11, §5.2 | Faithful |
| Q10 fonts in the shell CSP only | §4.5 | Faithful; the full shell CSP is now spelled out, which is good |
| Q11 markdown-it-py | SC7, §4.6 | Faithful, and stronger: it adds `<img onerror>` to the test |
| Q12 redaction through `config.redact()` | SC8 | Not faithful any more because of `11c95b0`, see B2 |
| C1 read-only open | §4.2 | Faithful; the probe confirms it |
| C2 launchd and setup gaps | §4.3 | The file allowlist includes `data/growth/transcripts`, which contradicts SC8, see B1 |
| C3 missed versus quiet | §4.4 | "Reads the `runs` and `events` tables as well as the mirror" double-counts, see B3 |
| C4 email isolation | §4.5 | Faithful |
| C5 dependencies | §4.7 | The status is stale, see B4 |
| C6 seam | §4.8 | Faithful; sharpened under Seams below |

## Blocking findings

### B1. The raw file route serves transcripts unredacted

§4.3 copies the scout card's file roots, including `data/growth/transcripts`. I carried that list
into C2 without checking it against Q12. A file route serves bytes as they are, so a transcript
from before ticket 01 would reach the browser with its secrets intact. That breaks SC8.

**Fix (PRD §4.3 and §5.2 routes):**

- No route serves text from disk raw. Transcripts, digests, plans and Discord outbox files are
  read by the read model, passed through `config.redact()`, then escaped or rendered as markdown.
- The raw file route serves an extension allowlist only:
  - `.png`, `.jpg`, `.jpeg` and `.webp` from `outputs/growth/{social,community}`;
  - `styles.css`, `tokens/*.css` and `assets/*.svg` from `design-system/`.
- Every raw response carries the sandbox CSP, `nosniff` and `no-referrer`.
- Add a test that a planted secret in a transcript never appears in any response. The test should
  request the transcript through every route, including a guessed `/files/transcripts/...` URL,
  which must return 404.

### B2. Keychain secrets aren't masked in the server process

Commit `11c95b0` ("Look up Keychain secrets only when a command reads them") changed
`config.secret_values()` (`config.py:162`). It now masks a `keychain:` value only once this
process has read it through `secret()`. That reasoning holds for CLI output: a process can't print
a value it never read. Mission control is different, because it shows text that other processes
wrote: transcripts, event payloads and email bodies. Any secret stored in Keychain therefore passes
through `redact()` untouched unless the server reads it first.

**Fix:**

- Add one public function to `config`, the module that owns secrets. For example,
  `config.load_secrets_for_masking()`, which calls `secret()` for every secret-named setting whose
  value starts with `keychain:`.
- `mission-control` calls it once at start, before `serve_forever`, so request threads only ever
  read the module globals.
- This also answers §6 Q8, which can no longer wait for ticket 01: 01 has landed.
- Test: stub `config._keychain`, put a `keychain:` setting in the temp env file, plant the
  resolved value in a transcript, and assert it is masked in the response.

### B3. One source per record kind for the classifier

`log.event(conn, …)` writes the `events` row and the JSONL mirror line with the same `ts`. That
covers the quiet skip at `runner.py:97` and the new `run.quiet`. The mirror therefore already holds
every `run.skipped` and `run.quiet` record, plus the two mirror-only skips (`runner.py:69` and
`:74`). Reading both `events` and the mirror, as §4.4 and §5.2 say, counts each quiet skip twice.
The counts in the scout-send day cell would then be wrong.

**Fix (PRD §4.4 and the §5.2 classifier row):**

- Runs, including the skip rows of jobs that aren't quiet, come from the `runs` table.
- `run.skipped` and `run.quiet` come from the JSONL mirror only.
- If the builder prefers to read both sources, the dedupe key is exactly `(kind, ts, job, reason)`.
- A table test plants the same quiet skip in both sources and expects one record.

### B4. The dependency status is stale, and the start of the build needs a decision

Tickets 01, 03, 04, 05, 06, 07 and 08 are all merged on `crew/growth-blocker-fixes`
(`4a7859e` is "Merge ticket 01"). None has reached `main`. §4.7 still says 01 is "in its first fix
round".

**Fix:**

- Update §4.7 to say that all blocker fixes are merged on `crew/growth-blocker-fixes`, that
  mission control waits for that branch's release gate (G4) to land in `main`, and that
  `crew/mission-control` then branches from `main`.
- If Ting Yu would rather start sooner, the build could stack on `crew/growth-blocker-fixes`. That
  choice is a question for him, listed below.

## Non-blocking findings

Each finding has a proposed fix. The builder applies them in the block named.

- **N1. Denials, the transcript path and unprefixed summaries are in the mirror only (Block 2).**
  - `claude.start`, `claude.result` and `claude.unprefixed` are written with `conn=None`
    (`runner.py:275`, `:304`, `:322`), so they never reach `events`.
  - The run page should take denials from the transcript's `result.permission_denials`. Once the
    transcript is pruned, it falls back to the mirror's `claude.result`.
  - The run page reads the mirror files for the run's start day and finish day, because a run can
    cross midnight. Cost comes from `runs.cost_usd`.
- **N2. A quiet run that did some work records its finish time as its start (Block 1, with the
  runner change).**
  - `runner.py:117` calls `log.start_run` after the job has finished, so `started_at` holds the
    finish time and the duration shows as zero.
  - A scout-send run longer than 10 minutes would also land in the next slot's window, and the
    slot that really ran would show as missed.
  - This also breaks the answer to §6 Q6, which matches emails to runs by their `sent_at` window.
  - Fix: capture the start stamp before the job runs. Add an optional `started_at=` keyword to
    `log.start_run` (`log.py:61`), which is additive, and put the same stamp in the `run.quiet`
    payload: `{"job", "started_at"}`.
- **N3. Records on days with no slots (Block 1, classifier).**
  - launchd still fires business-day jobs on public holidays, and the runner records "not a
    business day" skips.
  - Under the window rule, those skips fall into the previous business day's last window, so a
    real miss there would show as skipped.
  - Rule: a skip whose reason starts "not a business day" counts for no slot. The day page lists
    it under "outside the schedule".
  - Within one window, the latest run wins over any skip; skips count only when there is no run.
  - Add both rules as table rows.
- **N4. Never touch a job lock (Block 1).**
  - `runner._lock_held` (`runner.py:156`) and `locks.held` both take an `flock`. If the server took
    one even for an instant, a launchd run starting at that moment would skip with "previous run
    still going".
  - The server judges a long-running run by `started_at` age alone: still `running`, labelled
    "past its timeout" after `timeout_minutes + 15`.
  - A quiet run in progress has no row yet, so its slot shows as due. That is acceptable.
- **N5. Install state through one adapter (Block 3).**
  - `schedule.installed()` shells out to the real `launchctl`. A test that calls it reads the live
    launchd state and isn't deterministic.
  - `health` takes `installed: Callable[[str], bool] = schedule.installed`, and tests pass a fake.
  - `schedule.plist()` embeds `REPO_ROOT` and `paths.data_dir()`. Run from a worktree, or with
    `JURA_GROWTH_DATA_DIR` set, every job would read as out of date. The command prints a warning
    when the data folder isn't the default one.
- **N6. Setup gaps: who declares them, and when they're checked (Block 3).**
  - `cli.status` today reports only Discord webhooks. The other names live in plug-ins:
    `RESEND_API_KEY_OUTREACH`, `UNSUBSCRIBE_SECRET`, `OUTREACH_IMAP_*`, `CLOUDFLARE_API_TOKEN`,
    `CLOUDFLARE_ACCOUNT_ID` and `D1_DATABASE_ID`.
  - The core never imports an agent by name, so each plug-in should declare its own required
    settings as a module attribute, the way `MIGRATIONS` already works.
  - `config.secret()` may run `security` with a ten-second timeout per name. The server should
    compute gaps once at start, alongside B2, and label them "as of server start".
  - The Block 3 done-when, "`jura-growth status` output is unchanged", is wrong: status gains the
    new gap lines. Reword it to "unchanged apart from the setup-gap lines".
- **N7. Redaction and escaping start in Block 1, not Block 2.** Block 1's day page already shows
  run summaries, errors and skip reasons, and rows from before ticket 01 aren't redacted. Move
  "the read model redacts every string it returns", B2's start-up load and the planted-`<script>`
  escaping test into Block 1.
- **N8. Paths that come from the database go through the same resolver (Blocks 2 and 3).**
  - Affected: `app_prds.path` (stored as `prd/…` relative to `jurasolutions/`; resolve it against
    `paths.prd_dir()` so `JURA_PRD_DIR` works in tests), `social_posts.image_paths` and
    `community_posts.image_path`.
  - One resolver function serves both these values and the URL routes: allowlisted roots,
    `resolve()`, `is_relative_to()` and `paths.guard()`.
  - A PRD that has moved to `prd/done/apps/` is looked up there too.
- **N9. Two ways an artifact can be missing (Block 2).**
  - Show "transcript pruned" only when the run is older than `retention.transcripts_days`. A
    missing transcript for a younger run shows "transcript missing".
  - Outreach retention deletes leads after 24 months, and the delete cascades to
    `outreach_messages`. Old run pages say "removed by retention" rather than showing an empty
    list.
- **N10. Measure 360px instead of screenshotting it (Block 3).** A screenshot can't show
  horizontal overflow, and the page runs no script.
  - The test fetches the page over `http.client` and writes it to a temp file, with stylesheet
    URLs pointing at the test server and an injected script that writes
    `document.documentElement.scrollWidth` into the DOM.
  - It then runs `_chrome` with `--dump-dom --window-size=360,800` and the loopback-only resolver
    rules, and asserts the width is 360 or less.
  - Skip when Chrome is missing, as `tests/test_social_render.py:18` already does.
- **N11. Port binding (Block 1).**
  - `HTTPServer.allow_reuse_address` is 1 and `allow_reuse_port` is False on this Python (checked).
    Set `allow_reuse_port = False` explicitly so a second server can never share the port.
  - Catch `EADDRINUSE` and exit 1 with "port 8765 is in use. Is mission control already running?
    Change `mission_control.port` in settings.yaml."
  - Validate the port is between 1024 and 65535. Test that a second server on the same port fails
    cleanly.
- **N12. Two cheap headers (Block 1).**
  - Send `Cross-Origin-Resource-Policy: same-origin` on every response. A cross-site `<img>` or
    `<iframe>` request carries a valid `Host: 127.0.0.1:8765`, so the Host check doesn't stop it.
  - Add `frame-ancestors 'self'` to the email-body CSP. `frame-ancestors` doesn't fall back to
    `default-src`.
  - `Cache-Control: no-store` on pages is optional.
- **N13. Reuse the existing read functions.** The read-only helper sets
  `row_factory = sqlite3.Row` so that `pause.flags`, `pause.is_paused` and the digest's spend query
  can be called on it unchanged. Extract `digest.spend(conn, day)` rather than copying the SQL.
- **N14. Transcript size.** stream-json transcripts can run to megabytes. The run page truncates
  each tool result (for example to 2,000 characters, with a note), and never offers the raw file
  (B1).
- **N15. Defence in depth for headless runs.** Add `"mission-control"` to `headless.NEVER`
  (`headless.py:43`). Default-deny already refuses it, but `NEVER` stops a plug-in from ever
  declaring it. Add one assertion in `tests/test_headless.py`.

## Seams

There is **one new seam**: the read model's interface (`jura_growth/mission.py`). It is a deep
module. Callers pass a small source, and get plain dataclasses per page:

```python
@dataclass(frozen=True)
class Source:
    db: Path            # paths.db_path()
    data: Path          # paths.data_dir()
    outputs: Path       # paths.outputs_dir()
    prd: Path           # paths.prd_dir()
    now: datetime       # timeutil.now_sgt()

home(src) -> Home; day(src, date) -> Day; run(src, run_id) -> Run | None
emails(src); email(src, id); email_body(src, id) -> str; posts(src); prds(src); prd(src, id); digest(src, date)
```

What sits behind the interface:

- the read-only open (one connection per call, closed before returning);
- the stale-journal (`SQLITE_READONLY_ROLLBACK`, `SQLITE_BUSY`), missing-database (`SQLITE_CANTOPEN`)
  and not-migrated cases, returned as values (a `DbProblem` on the page model), never raised to the
  adapter;
- mirror and transcript reading, redaction of every returned string, and the path resolver.

Tests cross this seam directly against a temp database built by `db.migrate`.

The rest are internal seams or adapters. None is a new external seam:

- **The slot classifier** is a pure function behind the read model:
  `classify(jobs, records, now, days) -> {(job, date): [SlotState]}`. Its table tests may call it
  directly because it has no I/O. It needs no adapter.
- **The HTTP handler** (`mission_server.py`) is a thin adapter at the read model's seam: Host and
  method checks, routing, headers, escaping and templates. It is tested through `http.client` on
  port 0 in a thread, and by Chrome for the sandbox.
- **The launchd adapter** is the `installed` callable passed into `health` (N5). It has two
  adapters, the real `schedule.installed` and the test fake, so it is a real seam.

Existing seams to use, with nothing new:

- the environment overrides in `tests/conftest.py`: `JURA_GROWTH_DATA_DIR`, `_OUTPUTS_DIR`,
  `_PAUSE_FILE`, `_ENV_FILE`, `_LAUNCH_AGENTS`, `_PLIST_DIR`, `JURA_PRD_DIR` and `JURA_GROWTH_NOW`;
- the session `WriteGuard`, which already refuses even a read-only `sqlite3.connect` under
  `jurasolutions/`, so the never-writes test gets that proof for free;
- `config._keychain`, monkeypatched for B2;
- `agents.social.render._chrome` and `chrome_path`, for the browser tests;
- `config.reset_caches()`.

## Blast radius

| Area | Change |
|---|---|
| `jura_growth/mission.py` | New: the read model and the read-only helper (with the classifier, or beside it in `slots.py`) |
| `jura_growth/health.py` | New: `setup_gaps()`, install state, health-strip items |
| `jura_growth/markdown.py` | New: the single `MarkdownIt("js-default")` instance |
| `jura_growth/mission_server.py` | New: the HTTP adapter |
| `jura_growth/runner.py` | Changed: `run.quiet` at line 116, and the real start stamp for quiet runs (N2) |
| `jura_growth/log.py` | Changed, additive: `start_run(..., started_at=None)` |
| `jura_growth/config.py` | Changed, additive: the masking loader (B2) |
| `jura_growth/headless.py` | Changed: `NEVER` gains `mission-control` (N15) |
| `jura_growth/digest.py` | Changed: `spend()` extracted (N13) |
| `jura_growth/cli.py` | Changed: the `mission-control` command; `status` calls `health.setup_gaps()` (one call site) |
| Agent plug-ins | Each declares its required settings (N6): outreach, scout, the Cloudflare sync owner |
| `config/settings.yaml` | Adds `mission_control.port` |
| `pyproject.toml`, `uv.lock` | Add `markdown-it-py==4.2.0` and `mdurl==0.1.2`. Neither is in the lock today |
| `CONTEXT.md` | Slot status gains **due**, if Ting Yu agrees (§6 Q3) |
| Schema | No migration. `events` gains a `run.quiet` kind, about 43 rows per business day. Existing `events` readers all filter by kind: `apps/factory.py:83`, `outreach/send.py:104`, `outreach/store.py:82,102`. `cli log events` lists every kind and has `--kind`. `check_auto_pause` reads only `runs`. Nothing breaks |
| Data read | `growth.db` (read-only), `data/growth/runs/*.jsonl`, `transcripts/`, `discord-outbox/`, `outputs/growth/`, `prd/{pending,done}/apps/`, `design-system/`, `~/Library/LaunchAgents/*.plist`, and `.env` through `config` only for masking and setup gaps |
| New surface | A loopback HTTP listener on one fixed port |

There is no wide refactor here. The `status` change and the `start_run` keyword each touch one
call site, so no expand–contract sequencing is needed.

## Risks

| Risk | Mitigation |
|---|---|
| Readers block writers in rollback-journal mode; scout-send commits every 10 minutes | One short connection per request, closed before rendering; `timeout=2`; no long queries. The writer's 30s busy timeout covers the overlap |
| A stale journal | The read-only open fails with `SQLITE_READONLY_ROLLBACK` and changes nothing (probed). Show the message; never touch the journal |
| Leaked secrets from before ticket 01 | `redact()` at the read model's interface, B2's start-up load, and no raw text routes (B1) |
| DNS rebinding and cross-site reads | Host allowlist (421), loopback bind, GET and HEAD only, CORP `same-origin` (N12), `frame-ancestors` |
| Untrusted HTML in email bodies and PRDs | The sandbox CSP route and `iframe sandbox`; markdown in `js-default` only; `script-src 'none'` on the shell |
| Path traversal and secret files | One resolver with allowlisted roots, an extension allowlist, `resolve`/`is_relative_to` and `paths.guard()` (B1, N8) |
| A headless run starting the server | Default-deny, plus `NEVER` (N15) |
| Concurrency inside the server | `ThreadingHTTPServer` with daemon threads; a connection per request per thread; secret and setup-gap globals filled before `serve_forever` |
| `launchctl print` costs about 9 subprocesses per home-page load | Only the pages with the health strip call it; measure in Block 3, and cache for one refresh interval if it exceeds about 300ms |
| Large transcripts | Truncate per tool result (N14) |
| Third parties | Google Fonts fetches once per load, with no referrer (Q10). markdown-it-py is pinned with hashes and re-vetted on upgrade. Browser tests skip when Chrome is missing |
| An irreversible data shape | `run.quiet` rows are append-only by trigger (ADR 0001 below) |

## Build-block order

The order stays 1 → 2 → 3, with these adjustments. Tickets come later from `to-tickets`; this is
the cut I recommend so each ticket fits one context window.

0. **Prefactor: the quiet-run trace (ticket 01, first).**
   - Changes: `run.quiet` with the real start stamp (N2), `log.start_run(started_at=)`, and
     `NEVER` gains `mission-control` (N15).
   - It changes no screens, and landing it first lets quiet-run history build up before the UI
     ships.
   - Done when the runner test passes (one `run.quiet`, no run row, a correct `started_at` on a
     quiet run that did work).
1. **Block 1, slots end to end (tickets 02 to 04).**
   - 02: the pure classifier and its table tests, including B3, N3, slept through three slots,
     not installed and due.
   - 03: the read-only helper, the read model for home and day pages, redaction (N7), and B2's
     masking loader.
   - 04: the server adapter and `mission-control` command (N11, N12, Host and method checks), the
     home and day pages, refresh, and the never-writes test with the stale journal.
2. **Block 2, runs and artifacts (tickets 05 and 06).**
   - 05: the run page and the Emails, Posts and PRDs lists, with N1, N8, N9 and N14.
   - 06: the email-body route with its browser test, the markdown module, the raw file route (B1),
     and the redaction sweep test.
3. **Block 3, health strip (tickets 07 and 08).**
   - 07 (prefactor first inside the block): plug-in setup-gap declarations and
     `health.setup_gaps()` shared with `status` (N6).
   - 08: install state through the adapter (N5), the strip items, copyable commands, and the
     360px measurement (N10).

Every edge above is a real blocking edge:

- 02 needs 01's record shape.
- 04 needs 02 and 03.
- 05 and 06 need 04's adapter.
- 08 needs 07.
- 05 and 06 can run in parallel.

## Answers to PRD §6

1. **Port.** I agree: 8765 in `settings.yaml`, no fallback, with the message and validation in
   N11.
2. **The scout-send day cell.** I agree that the worst status wins, but with skipped ranked below
   ok. The order is failed, then missed, then running, then ok, then skipped, then due, then
   upcoming, then not installed.
   - A skip has a stated reason and isn't a fault. One "previous run still going" among 42 ok
     slots shouldn't colour the day.
   - A paused day is all skips, so it still shows as skipped, and the pause is on the health strip.
   - Counts per status appear in the cell's title text and on the day page.
3. **"due".** I agree. A neutral status, never counted on the health strip. It goes into
   `CONTEXT.md`'s Slot status entry once Ting Yu agrees. That is a glossary edit, which the
   business analyst makes at sign-off.
4. **Health-strip windows.** I agree, made precise:
   - failures: a job whose latest run failed, plus any failed run in the last 24 hours;
   - missed: slots whose window closed since the start of the previous business day.
5. **Posts.** I agree: `social_posts` plus `community_posts`. Discord appears as delivery counts,
   and outbox files are rendered through the read model, redacted, not linked raw (B1).
6. **Linking emails to runs.** I agree, with no migration, on condition that N2 lands. Without the
   real start stamp, a quiet scout-send run's `sent_at` window is empty.
7. **An unloaded job that has history.** I agree. Note that install state is the state now: a
   job uninstalled for a week and reinstalled today shows that week as missed. That is
   acceptable.
8. **When Keychain secrets are read for redaction.** Once, at server start. This is now required,
   not deferred (B2). A changed secret needs a restart, and the page footer says so.

## ADR drafts

Two decisions meet all three tests (hard to reverse, surprising without context, a real
trade-off). `docs/adr/` doesn't exist yet. The builder creates it with these files in ticket 01 and
ticket 03. markdown-it-py, the on-demand server and the port are easy to reverse, so they get no
ADR.

**`docs/adr/0001-quiet-runs-leave-an-event-not-a-run-row.md`**

> # Quiet runs leave an event, not a run row
>
> scout-send runs about 43 times a business day and usually finds nothing to send. To tell those
> quiet runs apart from slots the Mac slept through, the runner writes an append-only `run.quiet`
> event (`{"job", "started_at"}`) instead of a `runs` row. Run rows would bury every other job in
> `runs`, in `jura-growth status` and in the digest counts, and would reset the failure streak
> `check_auto_pause` reads. Events are append-only by trigger, so these rows are permanent;
> changing the shape later means reading both.

**`docs/adr/0002-mission-control-never-repairs-growth-db.md`**

> # Mission control opens growth.db read-only and never repairs it
>
> Every other reader uses `db.connect()`, which creates folders, sets `journal_mode`, runs
> migrations and, on its first open, rolls back a stale journal. Mission control instead opens
> `file:…?mode=ro` with `PRAGMA query_only = ON`, one connection per request. A hot journal makes
> that open fail with `SQLITE_READONLY_ROLLBACK`, and the page tells Ting Yu to run
> `jura-growth status` rather than recovering itself. A viewing page must never be the process
> that decides what happens to an unfinished write. Don't "fix" this by switching to
> `db.connect()` or `immutable=1`.

## Specialist guidance

The stack is Python, SQLite and server-rendered HTML with no JavaScript, so the Postgres and React
guides don't apply. The one public interface is the read model's interface, designed above with
`codebase-design`; nothing outside the repo calls it, so `api-and-interface-design` adds nothing
here. Web interface quality goes to `crew:web-design-review` at code review.

## Questions for Ting Yu

1. **Wait for main, or stack the build?** Should mission control wait for the blocker fixes to
   reach `main` (their G4), or stack on `crew/growth-blocker-fixes` now? *Recommended:* wait. The
   PR stays small, and the blocker fixes ship on their own review.
2. **The scout-send day cell.** Do you accept skipped ranking below ok in the cell (§6 Q2 as
   amended above)? *Recommended:* yes.
