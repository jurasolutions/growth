## Summary

This fixes the nine blocking findings from the 2026-10-24 crew audit of the growth engine against its PRDs (foundation, scout, community scout). There is no new scope. Each fix brings the code in line with a requirement a PRD already states. The spec, tickets, audit and every review are in `.scratch/growth-blocker-fixes/`.

| Ticket | What changes |
|---|---|
| 01 | A headless run can't read `.env` or any other secret file, can't print a secret value, and can run only its own job's `jura-growth` commands. The allowlist is enforced twice, in the Claude Code rules and again in code. Terminal use is unchanged, except that every file option now refuses secret files. |
| 02 | The community job can't fetch any Facebook host. Each blocked domain gets an apex and a `*.` WebFetch denial, built from the one list in `config/community.yaml`. |
| 03 | An agent still pauses itself after three failed runs when Discord can't be reached. Undelivered posts go to the outbox, and `jura-growth run` exits with the run's own status instead of a traceback. |
| 04 | The numbers rule treats a figure written as words ("forty per cent", "twelve businesses") like a figure in digits. "One" and "a" on their own still pass. |
| 05 | Every complaint in the website's D1 log pauses outreach, including one that arrives after an unsubscribe. Config can delay the warm-up but never shorten it, live sends are at least 10 clock minutes apart, and two `send-due` calls can't both send. |
| 06 | A contact address must belong to the business: on the company's own domain or a subdomain, or at one of six free-mail providers and published on the company's own site. |
| 07 | No community group is planned until you confirm its days with `community set <id> promo_days=... post_days=...`. The rules parser only gives a hint. |
| 08 | Tests and frozen-clock runs never write to the repo, live data or live outputs. |
| 09 | The #community summary, `community set --help` and the headless preamble name only commands that work, and two duplicated helpers are shared. |

How a headless run is fenced in now:

```text
jura-growth run <job>
  runner.claude_command(job)
    headless.permissions(job)          # 01: the job's own commands, NEVER list, Read denials for secret files
    community.permissions()            # 02: WebFetch(domain:d) and WebFetch(domain:*.d) per blocked domain
  every file option -> paths.guard()   # 01: secret files, symlinks and hard links refused; in a run only work/<job> and outputs/growth
  config.redacted_output()             # 01: secret values masked in stdout, stderr and tracebacks
  _run_locked
    discord.post fails -> outbox       # 03: transport errors become DiscordError
    finally: check_auto_pause          # 03: the third failure pauses the agent whatever happened to the alert
```

Two new migrations. Both add, neither drops or rewrites data:

```diff
 jura_growth/migrations/
   0001_core.sql
+  0002_sync_cursors.sql              # sync_cursors: the last D1 suppression event id processed
 jura_growth/agents/community/migrations/
   0001_community.sql
+  0002_confirmed_days.sql            # community_groups.promo_days_confirmed, post_days_confirmed
```

One commit sits outside the tickets: 9ee2d89 sets the repo up for the crew (the "Agent skills" section in `CLAUDE.md` and `docs/agents/`).

## Evidence

- **Before:** on `main` (6eabfe7), `uv run pytest` gives 515 passed, and the audit reproductions in `.scratch/growth-blocker-fixes/audit/repro/` pass, which means each defect is present.
  **After:** on this branch (db218a0), `uv run pytest` gives 987 passed in 21.82s, with `JURA_ROOT` set and temp data and outputs folders. Each reproduction is now a regression test under `tests/` that fails against `main`'s code.

```text
                                             main                          this branch
check --file .env                            prints webhook URL and key    refused, exit 2
community job fetches m.facebook.com         allowed (6 exact hosts)       denied (apex and *. for 7 domains)
Discord down, job fails three times          traceback, no pause           agent paused, alert in the outbox
"Jura has served forty clients"              passes                        fails [numbers]
complaint after an unsubscribe               outreach keeps going          outreach paused
info@someoneelse.sg on a partners page       accepted as a contact         rejected
"No promotion on weekends."                  promotion Sat and Sun only    no day until you confirm
JURA_GROWTH_NOW=... against live data        runs, writes test rows        refused, exit 1
```

- **Upgrade path.** The final review built a database at `main`, opened it with this branch, and saw `core/0002_sync_cursors.sql` and `community/0002_confirmed_days.sql` each applied once, with the rows intact. A second open applied nothing, and `main`'s code still runs on the migrated database.
- **Reviews.** Every ticket was reviewed, and the final review of the merged branch approves with no blocking finding on either axis, security included. Tickets 04 and 07 ended with their last fix rounds verified by the conductor rather than a further reviewer round. Ticket 07's design was settled by your "always confirm day rules" decision.

## Release notes

1. **Community groups you've already confirmed get no posts after this upgrade** until you run `jura-growth community set <id> promo_days=... post_days=...` for each one. `community groups --joined` still shows them as "rules confirmed", next to "no post until Ting Yu confirms the open days".
2. **Change the website before you set the D1 credentials in growth.** The D1 suppression sync now reads by event id. Switch the website's `suppression` table to the append-only contract in `docs/scout.md` (an `id INTEGER PRIMARY KEY AUTOINCREMENT` column, plain inserts, rows never updated or deleted) in the landing-page repo (`migrations/0001_toolbox.sql`, `server/suppression.js`) first. If the D1 settings are set before that, the sync query fails and outreach pauses itself.
3. **The first D1 sync replays every event from id 0.** An old complaint in the table would pause outreach again. That is harmless today, with no live sends and no leads recorded, but start the site's table empty rather than copying old rows into it.
4. **No new jobs or times.** `uv sync` is enough; you don't need to reinstall the schedule.

## Follow-ups outside this change

- `prompts/social.md` still has the stale "were/well/wed" sentence.
- The numbers rule doesn't yet treat ordinals ("our fortieth client") as figures.
- The Discord outbox stores message text unredacted (audit S8).
- The digest counts complaints by local suppression reason, so a complaint after an unsubscribe shows as 0.
- A frozen clock doesn't refuse to run when Discord webhooks are set, so a frozen-clock run can still post for real.
- Final review ST2: `headless.py` builds a log record by hand instead of calling `log.event(None, ...)`.
- Final review ST4: `images = []` inside `community/plan.py` `publish()` shadows the `images` module.
- Final review ST5: the `FREE_MAIL_CONTACTS` ceiling lives in `scout/contact.py`, not `caps.py`, and is copied by hand into `prompts/scout.md` and `docs/scout.md`.
- Scout contact rule: a directory's home page with a free-mail address, or another party's free-mail address on the company's site, can still pass (`issues/06` Comments). Watch the domains in #scout-leads during the shadow trial and decide a name-to-domain rule before `mode: live`.

## Merge danger

**Door:** two-way

Reverting the merge commit restores the old behaviour. The two migrations stay in `growth.db`, but they only add a table and two nullable columns, and `main`'s code ignores them. Nothing in this change sends email, and outreach is still in shadow mode.

**Blast radius:** operator

Everything that changes is on your Mac and in your Terminal. Confirmed community groups go quiet until you set their days. The numbers rule now fails some ordinary sentences, such as "We'll send you two options.", the same way it already failed "2 options". Every file option refuses `.env.example`, because it matches `.env*`. Headless runs that relied on a command outside their job's allowlist are now refused, and that shows up as a permission denial in the transcript.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
