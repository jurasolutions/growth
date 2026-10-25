# Code review: final (growth-blocker-fixes)

Branch `crew/growth-blocker-fixes` at 9c2611b, reviewed against its merge-base with `main` (6eabfe7).
This review covers the whole merged branch: tickets 01 to 08 together, after each was reviewed on
its own (`code-review-01.md` to `code-review-08.md`). It looks for what the per-ticket reviews could
not see: how the tickets interact, the migration path from a database built at `main`, whether the
docs match the code, and what changes for Ting Yu in Terminal.

## Verdict: approve

No finding is blocking. Every acceptance criterion holds on the merged tree, the security pass
found nothing exploitable, and the diff touches no blocked path. The should-fix items below are
small. Two of them are stale command hints that Ting Yu would follow by hand (Spec S1, S2), so they
are worth fixing before merge, but none of them breaks a requirement.

## Evidence

- `uv run pytest` with temp `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`: 975 passed. Run again
  without those exports: 975 passed in 23.45s. Afterwards `git status` was unchanged, and the
  modification times of the 71 files under `jurasolutions/data/growth` and `outputs/growth` were
  unchanged.
- **Migration from `main`.** I built a database at `main` in a throwaway worktree with temp folders,
  using two joined groups with confirmed rules (one of them "No promotion on weekends.") and one
  suppression row. Then I opened it with the branch.
  - `core/0002_sync_cursors.sql` and `community/0002_confirmed_days.sql` each applied once. The
    `owner/file` migration ids keep core 0002, community 0002 and the existing outreach 0002
    apart, so the shared number does no harm.
  - The rows are intact, and a second open applied nothing (9 migrations recorded).
  - The `main` code still runs against the migrated database and ignores the new columns.
  - Behaviour on that database:
    - At `main`, the weekend-ban group was offered only Sat/Sun with a closing line. That is the
      original bug.
    - On the branch, both groups had no open day until Ting Yu set their days.
    - After `community set 1 promo_days=mon-fri post_days=any` the closing line moved to Mon to Fri.
  - The throwaway worktree has been removed.
- **Security probes in a real CLI process** (not CliRunner), against a fake env file:
  - `check --file fake.env` is refused with exit 2.
  - A symlink `link.md -> fake.env` is refused.
  - Secret values in an ordinary file show as `[redacted]` in the output.
- **Spec-axis probes** (scripts in the session scratchpad, `spec-agent/`):
  - The argv for all four claude jobs, compared with `main`: each carries its allowlist and the four
    Read denials. Community gains apex and `*.` WebFetch denials for 7 domains. The other jobs'
    WebFetch rules are unchanged.
  - Every command each prompt names is declared by its plug-in and exists as a CLI leaf.
  - A command job refused by the allowlist, with Discord on a refused port, ran as failed, failed,
    failed, then skipped. It auto-paused and left 1 file in the outbox.
  - `JURA_GROWTH_NOW=... jura-growth status` against the live data folder exits 1 with a clear
    refusal.
- Typecheck (advisory): `uvx pyright` reports 76 errors, under the 84 baseline. None are new in the
  touched files.
- Blocked paths: `git diff --name-only main...` matches nothing under `inputs/` or `design-system/`,
  no `.env*` file, nothing under `data/growth` and no `_ds_bundle.js`.

## Standards

### Blocking
None.

### Should fix
- **ST1. `jura_growth/runner.py:156-166`, `_lock_held`: duplicated code across tickets 01 and 05.**
  Ticket 05 moved the lock into `locks.held`. This function still rebuilds the lock path and the
  `flock(LOCK_EX | LOCK_NB)` probe from `locks.py:19-22`, and it is the only reason
  `import fcntl` is still in `runner.py:20`. It breaks the reuse rule. Move the probe into `locks`
  (for example `locks.is_held(name)`).
- **ST2. `jura_growth/headless.py:174-177` builds a log record by hand with `log.mirror({...})`.**
  `log.event(None, "command.refused", {...}, level="warning")` (`log.py:31`) already takes
  `conn=None`, and it adds `run_id` and applies `config.redact`. This breaks the reuse rule.
- **ST3. The "path is inside this folder" check is written three times:**
  `paths.py:125` in `guard`, `timeutil.py:38` in `frozen_clock_problem`, and `paths.writable`
  (`paths.py:136`). `Path.is_relative_to` from the standard library (Python 3.12) does the same.
  This breaks the reuse rule.
- **ST4. `jura_growth/agents/community/plan.py:665`, `images = []` inside `publish()`.**
  This local list has the same name as the `images` module imported at `plan.py:23`. Today it is
  harmless, but any later use of `images.png_size` inside `publish` would raise
  `UnboundLocalError`. Rename it, for example to `attachments` (Mysterious Name).
- **ST5. `jura_growth/agents/scout/contact.py:56`, `FREE_MAIL_CONTACTS`, is a hard ceiling kept
  outside `caps.py`.** This is a judgement call. `docs/agents/crew.md` says "Hard limits live in
  `jura_growth/caps.py`; a config value may lower a limit, never raise it." The developer put it in
  `contact.py` to avoid colliding with ticket 05, as recorded in `crew-log.md`. Now that both are
  merged, move it to `caps.py` or note the exception in `caps.py`. The list is also copied by hand
  into `prompts/scout.md:24` and `docs/scout.md:64`.

### Nits
- **N1.** `plan.py:388-393` and `plan.py:667-673` call `paths.guard()` again right after
  `image_problem()` has already guarded the same path. `image_problem` could return the resolved
  path instead.
- **N2.** `community/__init__.py:448` and `:454`: the `audit-run` verdict still says "a Facebook
  domain" and "other Facebook domains". Since ticket 02 the list also includes any domain in
  `blocked_fetch_domains`. The docstring was updated; these strings were not.
- **N3.** `runner.py:60`, `_lock = locks.held`, is a middle man. Its one outside caller is
  `tests/test_core.py:401`.
- **N4.** `cli.py:38-44` and `cli.py:58-63` both enter `config.redacted_output()`. The second entry
  does nothing, but a comment saying the outer one exists for the traceback path would help.
- **N5.** The four plug-in `permissions()` functions have no return annotation. The interface
  documents `-> headless.Permissions | None` (`agents/__init__.py:29`).
- **N6.** `send.py:231` puts the lock `outreach-send` in the same folder as the per-job locks.
  Nothing keeps the two kinds of name apart. They don't clash today.

## Spec

### Blocking
None. These acceptance criteria pass on the merged tree:

- 01: the `.env` refusal and masking; `community set` refused in a community run; the four outreach
  commands refused in a scout-research run; the `image_path` rejection; the argv assertions;
  Terminal use unchanged.
- 02: apex plus subdomain denials per domain; a new domain needs only the plug-in list; other jobs
  unchanged.
- 03: auto-pause when Discord can't be reached; no traceback; the alert goes to the outbox.
- 04: the number-word sentences fail; the approved claims and "Start with one process." pass.
- 05: the F1, F1b, F2 and F3 regression tests; each event applied once; shadow mode unchanged.
- 06: the F4 and F4b regression tests; the G2 free-mail list.
- 07: superseded by Ting Yu's "always confirm days" decision. Every group stays closed until its
  days are confirmed.
- 08: no writes to the repo or live folders; the frozen-clock refusal.

### Should fix
- **SP1. `jura_growth/agents/community/__init__.py:404`, `register_summary`, which is posted to
  #community, still tells Ting Yu to run**
  `community set <id> joined=yes rules="…" rules_confirmed=yes`.
  Since ticket 07 that exact command is refused with "missing: promo_days, post_days" and exit 1.
  `docs/community.md`, `prompts/community.md` and the README are correct; this Discord hint is the
  one place left. It breaks Ting Yu's decision in `crew-log.md` ("every group needs confirmed
  promo_days and post_days before planning"). Reproduced: `community add-group`, then
  `community summary --no-post`, then the printed command.
- **SP2. `community/__init__.py:198`: the `community set` help text is stale.** It still reads
  `joined=yes rules="..." [fit=...] [notes=...] [rules_confirmed=yes]`, with no `promo_days` or
  `post_days`. `community set --help` shows this.
- **SP3. `runner.py:255-256`: the headless preamble doesn't match ticket 01's allowlist.**
  It tells every run "Every side effect (database, Discord, …) goes through `jura-growth`. Run
  `jura-growth --help` and `jura-growth <group> --help`." `discord` is in `NEVER`, and Claude Code
  refuses `<group> --help` for any group the job doesn't declare (`discord` and `suppression` for
  every job, `outreach` for community). The prompts carry the real command lists, so no run
  breaks. But the preamble invites refused calls that show up as permission denials in the
  transcript. List the job's own commands from `headless.permissions(job)` instead.

### Nits and accepted deviations
- **Accepted:** ticket 01 says the guard refuses "anything outside `JURA_ROOT`". Outside a run it
  accepts any non-secret path (`paths.py:118-129`). The conductor accepted this so Terminal use
  stays unchanged, and reviewer 01 confirmed it. The in-run folder rule is tighter.
- **N7.** The frozen-clock refusal is broader than ticket 08 asks. It also fires when only the
  outputs folder is live, and on `--help`. Both err on the safe side.
- **N8.** The app-factory allowlist adds `scout insights`, which its prompt never names. It is
  needed because `apps context` calls it in-process (`apps/inputs.py:54`). It's a harmless read.
- **N9.** The 10-minute live-send gap counts whole clock minutes (`send.py:173-181`), so two sends
  can be 9m01s apart. The developer logged this as a decision for ticket 05, but the ticket says
  "a hard minimum gap … (10 minutes)". If the gap must truly be a floor, count real seconds.
- **N10.** `.env.example` is now refused by every path option, because it matches `.env*`. That is
  harmless, and on the safe side.
- **N11.** Commit 9ee2d89 (the crew setup: the `CLAUDE.md` "Agent skills" section and
  `docs/agents/*`) is not part of any ticket. That `CLAUDE.md` loads into every headless run; the
  new section says it is for development work only.

## Security

Nothing high or medium. I traced every new attack surface:

- **The command allowlist** (`headless.py`). It is enforced twice, in the Claude Code rules and
  again in the code. Command jobs run in-process with `JURA_GROWTH_JOB` set, and are restored
  after. An unknown job gets no commands, and `NEVER` always wins. Reviewer 01's Claude Code
  probes found that an env-prefixed command (`JURA_GROWTH_JOB= jura-growth …`, `env …`) is denied,
  so a run can't clear the variable.
- **The path guard** (`paths.guard`). It resolves symlinks before checking, matches secret-file
  names in any case, and catches hard links to the configured env file. In a run it accepts only
  `work/<job>` and `outputs/growth`. Community images are re-checked at publish time and must be
  PNGs, so a file swapped in after `plan-add` is never uploaded.
- **Output masking** (`config.redacted_output`). It covers stdout and stderr, tracebacks included,
  and hides `.buffer` so nothing can write around it. A Keychain value is masked only once the
  process has read it. That's acceptable, because a value never read can't be printed by the CLI.
- **SQL.** `set_fields` takes column names only from the `SETTABLE` and `DAY_COLUMNS` allowlists.
  The suppression sync and `_mark_leads` use bound parameters, and only the `?` placeholders are
  built in Python.
- **Discord transport errors** quote only the error type, never the webhook URL.

Pre-existing, already logged as follow-ups and not new: the outbox stores message text unredacted
(audit S8), and a frozen clock doesn't stop real Discord posts.

## Blocked paths

None touched.

## Release notes for Ting Yu (from the migration check)

1. **Community groups you already confirmed will get no posts after this upgrade** until you run
   `jura-growth community set <id> promo_days=... post_days=...` for each one. `community groups
   --joined` still shows them as "rules confirmed", next to "no post until Ting Yu confirms the
   open days".
2. **Change the website before you set the D1 credentials.** The D1 suppression sync now reads by
   event `id`. Switch the website's `suppression` table to the append-only contract in
   `docs/scout.md` (an `id INTEGER PRIMARY KEY AUTOINCREMENT` column, plain inserts) before you set
   the D1 settings in growth. If you set them first, the sync query fails and outreach pauses
   itself.
3. **The first sync replays every D1 event once.** It starts from cursor 0, so an old complaint
   would pause outreach again. That is harmless today (no live sends, and 0 leads in the audit)
   but worth knowing.
4. **No new jobs or times, so you don't need to reinstall the schedule.** The runner builds each
   job's permissions when it runs. `uv sync` is enough.
