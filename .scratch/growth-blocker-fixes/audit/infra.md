# Infra review: turning the Jura growth engine on, on this Mac

*Read-only review, 2026-10-24 21:10–21:25 SGT. Repo `jurasolutions/repos/growth` at `6eabfe7` (main, clean).
Every state below was checked on this machine; the command that showed it is given with each item.
Nothing was installed, rendered, sent or written in either repo or under `jurasolutions/`. The
database was inspected only through copies in the scratchpad.*

## Summary

The code and toolchain are ready. What the machine is missing is the human setup: no `.env`, no
secrets in the Keychain, no Discord webhooks, no launchd jobs installed, no `inputs/icp.md` or
`inputs/do-not-contact.csv`, and power settings that let the Mac sleep after one idle minute.

Three findings need a decision before the first scheduled run:

1. **The live website does not have any of the pages outreach emails link to.** `/unsubscribe`,
   `/api/resend-webhook`, `/privacy` and `/apps` exist only on the website repo's local `toolbox`
   branch, six commits ahead of `main` and not pushed. Production returns the single-page app's
   fallback HTML for all of them. Live sending must wait for that deploy. The code's live-mode
   checks (`send.py:69-97`) don't test for it.
2. **`growth.db` has a stale rollback journal** from a write at 21:00:19 that never committed.
   The only process holding the files is a Virtualization.framework VM. The next `jura-growth`
   command run on the Mac rolls it back automatically. The lesson matters more than the file:
   `jura-growth` must run only on the Mac itself, never from Cowork or a sandboxed session (A5).
3. **A build test run with a frozen clock left three social drafts dated Monday 2026-10-26** in
   the real database, so Monday's real 07:00 social run will skip (A6).

## Checklist

States: **done**, **partly**, **not done**, **unverified** (can't be checked read-only from here).

### A. Before any job runs

These cover the jobs that need nothing external: heartbeat, digest, backup, app factory, social
and community. Scout research skips each day, without failing, until B1 is done.

**A1. Decide where secrets live.**
- What: choose `.env` only, or `.env` holding `keychain:<service>` pointers. Foundation PRD §6 Q2
  is still open.
- Why: `config.py:90-123` reads the environment, then `.env`, and resolves `keychain:` values with
  `security find-generic-password -s <service> -w`.
- How: `.env.example` header; `outputs/growth/setup/discord.md` §4.
- Recommended: keep the Discord webhook URLs in `.env`. Put `RESEND_API_KEY_OUTREACH`,
  `CLOUDFLARE_API_TOKEN`, `UNSUBSCRIBE_SECRET` and `OUTREACH_IMAP_PASSWORD` in the Keychain, created
  with `security add-generic-password` so `/usr/bin/security` is already trusted and launchd
  never sees a prompt.
- State: **not done**. `security find-generic-password -s jura-growth-resend` and
  `-s jura-discord-alerts` both return absent; `security dump-keychain | grep 'svce.*jura'` returns
  nothing.

**A2. Create `.env`, mode 600.**
- Why: `README.md:15`; `paths.py:55-56`; `config.py:68-75` warns when group or others can read it.
- How: `discord.md` §4 (`cp .env.example .env && chmod 600 .env`).
- State: **not done**. `[ -e .env ]` reports missing; only `.env.example` (mode 644, no values) exists.

**A3. Discord server "Jura HQ", eight channels, one webhook each.**
- Why: foundation PRD §5.2; `discord.py:48-50` sends every message to the outbox when a webhook
  is missing.
- How: `outputs/growth/setup/discord.md`. Ting Yu then runs `jura-growth discord test`.
- State: **not done**. `jura-growth status`, run against a scratch copy of the database, prints
  `discord 0 of 8 channel webhooks set`. Eleven messages wait in `data/growth/discord-outbox/`
  (six from 2026-10-24, five dated 2026-10-26). There is no command to replay them; that's fine,
  because they came from build test runs.

**A4. Keep the Mac awake and logged in for the schedule.**
- Why: `README.md:93-97`; `schedule.py:7-9`; foundation PRD §4. The send queue needs the Mac awake
  from 09:30 to 16:30 on business days.
- How: no guide.
- State: **partly**.
  - `pmset -g` shows `sleep 1`: the system sleeps after one idle minute on AC.
  - It stays awake today only because a bare `caffeinate` has been running in a zsh tab since
    2 Oct (PID 74527, per `ps`), plus the Claude app's own assertion. Closing that tab or
    restarting ends it.
  - `pmset -g sched` shows no repeating wake; `autorestart 0`.
  - `fdesetup status` shows FileVault is on. After any restart, including an overnight macOS
    update, no LaunchAgent runs until Ting Yu logs in.
  - The machine is a Mac16,10 (Mac mini) on AC. Its zone is Asia/Singapore (+0800), so the plists
    need no time conversion.
- Recommended (Ting Yu, needs sudo):
  - `sudo pmset -c sleep 0` (the display still sleeps after 10 minutes);
  - `sudo pmset repeat wakeorpoweron MTWRFSU 06:15:00` as a backstop;
  - `sudo pmset -c autorestart 1`, and log in after any restart.
  - The 12:00 heartbeat in `#daily-digest` is the signal that the Mac was up.

**A5. Run `jura-growth` only on the Mac itself; clear the stale journal.**
- Why: `db.py:20-25`. Every connection runs `PRAGMA journal_mode = DELETE` and the migrations, so
  the first open rolls back a hot journal.
- State: **not done**.
  - `data/growth/growth.db-journal` (mode 600, 29,240 bytes) has sat unchanged since 21:00:20.
  - On scratch copies: the main file alone has migration `outreach/0002_requeue_shadow.sql`,
    applied at `2026-10-24T21:00:19+08:00`. The copy opened with its journal rolls that back to
    six migrations. `PRAGMA integrity_check` returns `ok` on both.
  - `lsof` shows only `com.apple.Virtualization.VirtualMachine` (PID 86255, started 23 Oct 22:49)
    holding both files, read-only. No host process holds a lock.
  - The likeliest cause is a `jura-growth` process inside a VM or sandbox that could write the
    database but not delete the journal. That was not verified.
- Effect: rolling back a migration is harmless, because it is re-applied straight away. The same
  failure on an outreach send would roll back the record that an email went out. Resend's
  `Idempotency-Key` (`send.py:234`) only blocks a duplicate within Resend's idempotency window.
- How: no guide. Ting Yu runs `.venv/bin/jura-growth status` once from Terminal on the Mac. That
  rolls the journal back and re-applies 0002. Then confirm `growth.db-journal` is gone.

**A6. Decide about the frozen-clock test rows.**
- Why: `agents/social/__init__.py:79-93` and `submit.py:74-86`. A day that already has drafts is
  skipped.
- State: **not done**.
  - `social_posts` holds three `draft` rows dated 2026-10-26 (`ai-this-week`).
  - `runs` row 5 reads `social ok 2026-10-26T07:00:00+08:00`.
  - `outputs/growth/social/2026-10-26/` exists.
  - Monday's real 07:00 run would skip with "today's drafts are already in #social-drafts". These
    rows, and the 2026-10-24 test drafts, also count toward the 14-day no-repeat history.
- How: no command exists; it needs a `sqlite3` delete on the Mac, or simply accepting the skip.

**A7. Install the launchd jobs, in stages.**
- Why: `README.md:93`; `schedule.py:83-147`.
- How: README "Schedule" section (one line, no step-by-step guide). Run it from Terminal in the
  logged-in desktop session, not over SSH: install uses `launchctl bootstrap gui/<uid>`.
- Recommended order:
  1. `jura-growth schedule install heartbeat digest backup`, then watch one 12:00 heartbeat;
  2. `app-factory social community`;
  3. `scout-research scout-send scout-sync`, once B1 and B2 are done (shadow mode).
- State: **not done**.
  - `ls ~/Library/LaunchAgents | grep -i jura` and `launchctl list | grep jurasolutions` return
    nothing. `jura-growth status` shows `installed no` for all nine jobs.
  - The two plists in `launchd/generated/` were written by the test suite at 21:07. Their log
    paths point into a pytest temp folder. `tests/test_core.py:276-277` calls `schedule.render()`,
    which writes to the real repo (`schedule.py:116`, no override). This contradicts
    `README.md:157`. Don't copy those plists by hand; `install` renders fresh ones.

**A8. Toolchain.**
- Why: `pyproject.toml`; `runner.py:240-253, 283`; `schedule.py:87-98`; `social.yaml` `render.chrome`.
- State: **done**.
  - `uv --version` reports 0.12.21 (`~/.local/bin/uv`). `.venv` has CPython 3.12, managed by uv,
    with click 8.5.0, pyyaml 6.0.3, httpx 0.28.1 and dnspython 2.9.0.
  - `uv sync --locked --dry-run` reports "Would make no changes".
  - `uv run pytest` in a scratch clone: 515 passed.
  - `claude` 2.1.286 lives at `~/.local/bin/claude`, which is on the plist PATH.
    `env -i HOME=… PATH=<plist PATH> sh -c 'command -v claude jura-growth'` resolves both.
  - Every flag the runner passes appears in `claude --help`.
  - Google Chrome 156.0.8078.47 is at the configured path. Earlier renders produced PNGs in
    `outputs/growth/social/2026-10-24/`.

**A9. Keep Claude Code signed in on this Mac.**
- Why: `runner.py:240-256`. Headless runs use the subscription login (`--setting-sources
  project`, no API key).
- How: no guide.
- State: **done**.
  - `claude auth status --text` reports "Claude Max account", also from a minimal launchd-like
    environment.
  - `security find-generic-password -s "Claude Code-credentials"` returns present.
  - The five earlier transcripts show `apiKeySource: none`, zero MCP servers, `success`, and
    US$0.27–1.00 per run.
- Note: these runs draw on the same Max limits as Ting Yu's own sessions (see Risks).

**A10. Paste the morning brief line into Cowork.**
- Why: foundation PRD §5.7.
- How: `outputs/growth/setup/morning-brief.md`.
- State: **unverified**, since it lives in the Cowork UI. `data/growth/daily-summary.json` doesn't
  exist yet because the digest has never run.

**A11. App factory inputs.**
- Why: `agents/apps/__init__.py:44-49`; `catalog.py:59-60, 208-217`.
- State: **done**. `prd/templates/prd-app-template.md` and `data/growth/app-backlog.yaml` exist.
  Three PRDs wait in `prd/pending/apps/`, under the limit of 7. See C5.

### B. Before scout outreach sends live

B1–B2 are needed before the shadow trial as well.

**B1. Move the ICP into `inputs/`.**
- Why: `agents/scout/__init__.py:32-34` (research skips without it); `icp.py:23-37`; scout PRD §5.1.
- How: `outputs/growth/setup/icp-draft.md` (edit it, then `mv` it to `inputs/icp.md`).
- State: **not done**. `ls jurasolutions/inputs/` shows only `services.md`, which the growth code
  never reads.

**B2. Create `inputs/do-not-contact.csv`.**
- Why: `send.py:93-94` (live mode refuses without it); `dnc.py:43-48`; `leads.py:118`. Without the
  file the list is empty, so shadow research would queue companies Ting Yu means to exclude.
  Scout PRD §6 Q4.
- How: `outputs/growth/setup/do-not-contact.example.csv` (copy it, then add rows).
- State: **not done**. The file is missing; `jura-growth outreach status` reports
  `do-not-contact missing`.

**B3. Shadow trial, three business days.**
- Why: scout PRD block 3.
- How: README and PRD only.
- State: **not started**. `outreach status` shows `sent (shadow) today 0, 30 days 0`, `queued 0`;
  the `leads` table holds 0 rows.

**B4. Merge and deploy the website's `toolbox` branch.**
- Why: every email links `https://jurasolutions.sg/unsubscribe?t=…` and `/privacy`
  (`compose.py:13-18, 41-43`; `scout/settings.py:20-21`), plus `/apps` and a tool. Scout PRD §5.9.
- How: no guide for the merge and deploy. `toolbox-ai.md` step 8 assumes the code is already deployed.
- State: **not done**.
  - In `landing-page`, `git log main..toolbox` lists six commits, none pushed: the toolbox shell,
    APP-001, the limiter with APP-002, and unsubscribe with the webhook and privacy notice.
    `git grep -iE 'privacy|/apps|unsubscrib' main -- src functions` finds nothing.
  - Live, `curl https://jurasolutions.sg/api/resend-webhook` returns `200 text/html`, 1,863 bytes
    (the app fallback, not the JSON health check). `/unsubscribe` returns 200 HTML instead of
    a 303, so the Functions are not deployed.
  - The contract itself holds:
    - With a dummy secret, `server/unsubscribe.js` and `compose.unsubscribe_token` produce an
      identical token.
    - The D1 `suppression` columns (email_hash, email, reason, source, resend_email_id,
      created_at) match `suppression.py:86-89`.
    - `app_usage(day, app_slug, opens, completions)` matches `registry.py:67` and
      `apps/inputs.py:24-27`.

**B5. Create the D1 database and its tables, and bind them as `DB`.**
- Why: `cloudflare.py:1-6`; toolbox PRD §5.5; scout PRD §5.9.
- How: `toolbox-ai.md` §1–3.
- State: **unverified**. Calling the Cloudflare API was out of scope. The code that would use the
  database isn't deployed (B4).

**B6. `UNSUBSCRIBE_SECRET`, the same value in Pages and in the growth CLI.**
- Why: `send.py:91-92`; `compose.py:76-80`. Without it, links carry an `UNSUBSCRIBE_SECRET-not-set`
  signature that won't verify.
- How: `toolbox-ai.md` §6–7 covers the Pages side; the growth side has only the `.env.example`
  line. Never change the value after the first live email.
- State: **not done** on the growth side (no `.env`). Pages side **unverified**.

**B7. Resend webhook, with `RESEND_WEBHOOK_SECRET` in Pages.**
- Why: scout PRD §5.5; `sync.py:76-111` (bounces and complaints drive auto-pause).
- How: `toolbox-ai.md` §9.
- State: **unverified**; the endpoint isn't deployed (B4).
- Smoke check: `curl https://jurasolutions.sg/api/resend-webhook` returns `"canVerify":true,
  "canStore":true`.

**B8. A Cloudflare API token for the growth CLI, plus `CLOUDFLARE_ACCOUNT_ID` and `D1_DATABASE_ID`.**
- Why: `cloudflare.py:22-29`; `send.py:95-96` (live mode refuses without them); `sync.py:40-55`
  (a failed sync pauses outreach).
- How: **no guide**. `toolbox-ai.md` covers the site's side only.
- Note: Cloudflare scopes D1 permissions to the whole account, not one database. The code only
  runs `SELECT`. Try D1 read access first and check whether the `/query` endpoint accepts it.
  Set an expiry and note it in D3.
- State: **not done**.

**B9. Choose the sending domain and confirm it is verified in Resend.**
- Why: `scout.yaml:26` (`sending_domain: null`); `send.py:81-88`; scout PRD §6 Q2.
- How: no guide.
- State: **partly**. DNS for `jurasolutions.sg`, from `dig`:
  - NS on Cloudflare (`keaton`, `mariah`).
  - MX `mx.zoho.com`, `mx2.zoho.com`, `mx3.zoho.com`.
  - Root SPF `v=spf1 include:zohomail.com ~all`.
  - `resend._domainkey` TXT (DKIM) **present**.
  - `send.jurasolutions.sg` MX `feedback-smtp.ap-northeast-1.amazonses.com` and TXT
    `v=spf1 include:amazonses.com ~all`, both **present**.
  - `_dmarc` reads `p=quarantine; adkim=r; aspf=r; rua=mailto:info@jurasolutions.sg`.
  - With relaxed alignment, Resend mail from `jurasolutions.sg` passes DMARC.
  - `hello.jurasolutions.sg` returns NXDOMAIN for the A record, DKIM, `send.hello` MX and TXT,
    and `_dmarc`. A subdomain would need Resend Pro and a full new record set.
  - `www.jurasolutions.sg` returns NXDOMAIN. Minor: emails link the bare domain.
  - The verified status in the Resend dashboard was not checked (no Resend calls).

**B10. A sending-only Resend key for outreach.**
- Why: `send.py:89-90, 227-235`; foundation PRD §5.5.
- How: no guide. In Resend, use "Sending access" restricted to the sending domain, separate from
  the website's `RESEND_API_KEY`.
- State: **not done**.

**B11. A mailbox or alias for the From address.**
- Why: From is `tingyu@<sending_domain>` (`scout.yaml:27`, `send.py:64-66`); Reply-To is
  `info@jurasolutions.sg` (`scout/settings.py:18`). Replies that ignore Reply-To go to From.
- How: no guide. Create `tingyu@` in Zoho, or an alias of info@. On a subdomain with no MX, those
  replies would bounce.
- State: **unverified**.

**B12. Legal view on the Spam Control Act's address-harvesting provision, then
`legal_review_done: true`.**
- Why: `scout.yaml:21`; `send.py:76-80`; scout PRD §4 and §6 Q1. The same conversation can settle
  §6 Q5 (whether to show the UEN in the footer).
- How: human only.
- State: **not done** (`legal_review_done: false`).

**B13. Reply and opt-out handling.**
- Why: `replies.py:52-58, 111-120` (IMAP, `INBOX` opened read-only); `sync.py:117-126`
  (follow-ups need it); `compose.py:83-87` (the `List-Unsubscribe` header's mailto goes to info@).
- How: no guide.
- State: **not done**.
- What the DNS answers: info@ is hosted on **Zoho Mail** (scout PRD §6 Q3). IMAP has to be
  switched on in Zoho Mail settings, an app-specific password is needed if 2FA is on, and the host
  is the one Zoho's IMAP settings page shows. Zoho's free plan has not always included IMAP, so
  check the plan.
- Without IMAP: no follow-ups, and every "unsubscribe" reply or mailto opt-out lands in Zoho for
  Ting Yu to record by hand with `jura-growth outreach suppress`, inside the Act's 10 business
  days.

**B14. Go live.**
- Why: `send.py:69-97`; scout PRD block 4.
- How: set `mode: live` (`scout.yaml:17`), optionally `send.warmup_start` (`scout.yaml:61`), and run
  `jura-growth outreach requeue-shadow` if the shadow emails should go out.
- State: **not done**. `jura-growth outreach status` lists seven "live mode would refuse" reasons:
  mode, legal review, sending domain, Resend key, unsubscribe secret, do-not-contact file and D1.
  Done means that list is empty and B4 and B7 pass their smoke checks.

### C. Before social, community and the app factory are useful

**C1. Social accounts.**
- Why: social PRD §5.5, §6 Q1.
- How: `outputs/growth/setup/social-accounts.md`.
- State: **unverified**, since it lives on the platforms. The profile and cover images are
  **done**: four PNGs in `outputs/growth/setup/social-images/`.

**C2. Weekend posts.**
- Why: `social.yaml:10` (`weekends: true`, the default); social PRD §6 Q2.
- State: defaulted, waiting on Ting Yu to confirm.

**C3. Community groups: join them and record them.**
- Why: community PRD §5.1 step 4, §5.2. The weekly plan only uses groups that are joined and a
  good fit.
- How: no guide beyond the PRD. Run
  `jura-growth community set <id> joined=yes rules="…"` for each group joined.
- State: **not done**. The register holds 14 groups (1 good fit, 10 possible, 3 skip), none joined.
  `post_as` is defaulted at `community.yaml:24`; community PRD §6 Q1 is still open.

**C4. Keep the website checkout on the deployed branch.**
- Why: the growth code reads `src/apps/registry.json` from the local `landing-page` working tree
  (`scout/registry.py:23`, `social/toolbox.py:46`, `apps/catalog.py:64`, `community/plan.py:108`),
  not from production.
- State: **partly**. The checkout is on `toolbox`, where `quote-builder` is `live` and
  `receipt-reader` is `draft`. Production doesn't serve `/apps` (B4). Wednesday social posts and
  community closing lines would link a page that isn't live. Deploy first.

**C5. Move shipped app PRDs to `prd/done/apps/`.**
- Why: `catalog.py:108-109, 216-217`. Every file in `prd/pending/apps/` counts toward the waiting
  limit of 7.
- State: **not done**. APP-001 and APP-002 are built on `toolbox` but still pending. At one PRD a
  day, the factory stops after four more.

**C6. Usage counts for tool choice and the digest (optional).**
- Why: `apps/inputs.py:18-31`; `scout/registry.py:61-78`. Both fall back quietly to "not configured".
- State: waits on B5 and B8.

### D. Later or yearly

- **D1. Refresh public holidays each December** (`config/sg-public-holidays.yaml`;
  `holidays.py:50-58` warns in December). It covers 2026–2027 now, so the next refresh is
  December 2027.
- **D2. An off-machine copy of `data/growth/`.** It is **not done**:
  - `tmutil destinationinfo` reports "No destinations configured".
  - `~/Library/CloudStorage` is empty and the OneDrive client isn't running, so this "OneDrive"
    folder is a plain local folder on this Mac.
  - The 14 nightly backups sit on the same disk as the database.
  - The code is safe: `origin/main` matches `main` at `6eabfe7`.
  - How: no guide.
- **D3. Secret hygiene.**
  - Rotate the Cloudflare token before it expires.
  - If a Discord webhook leaks, delete it and make a new one (`discord.md` §3).
  - Revoke the Resend outreach key if outreach stops for good.
  - Never rotate `UNSUBSCRIBE_SECRET` once emails have gone out (`toolbox-ai.md` §6).
- **D4. Reinstall the schedule after travel** (`schedule.py:182-186`) and after any change to
  `settings.yaml` `jobs`.
- **D5. Social block 3 (auto-publishing).** It needs a Meta app with a Page token and LinkedIn
  Community Management API approval. It is not built and not signed off (`social-accounts.md` §7).
- **D6. Developer ticket.** Make `schedule.render()` honour a test override so tests stop writing
  into `launchd/generated/`, or correct `README.md:157`.

## Touchpoints

| Touchpoint | Change | Environments | Owner | Status |
|---|---|---|---|---|
| uv, Python 3.12 `.venv`, dependencies | none | Mac | code | done |
| `claude` CLI and its login | none | Mac, launchd | Ting Yu | done |
| Google Chrome (card rendering) | none | Mac | Ting Yu | done |
| launchd agents `sg.jurasolutions.growth.*` | install 9 | Mac (gui session) | Ting Yu | not done |
| Power and wake (`pmset`), FileVault login | change settings | Mac | Ting Yu | partly |
| `repos/growth/.env` and Keychain items | create | Mac | Ting Yu | not done |
| `data/growth/growth.db` | stale journal to clear | Mac | Ting Yu | not done |
| Discord "Jura HQ", 8 webhooks | create | Discord | Ting Yu | not done |
| `inputs/icp.md`, `inputs/do-not-contact.csv` | create | Mac | Ting Yu | not done |
| Website `toolbox` branch | merge, push, deploy | GitHub, Cloudflare Pages | Ting Yu (website repo) | not done |
| D1 `jura-toolbox` and its `DB` binding | create, migrate | Cloudflare | Ting Yu | unverified |
| Pages variables (`UNSUBSCRIBE_SECRET`, `RESEND_WEBHOOK_SECRET`, …) | set, redeploy | Cloudflare Pages (prod and preview) | Ting Yu | unverified |
| Cloudflare API token for the growth CLI | create | Cloudflare | Ting Yu | not done |
| Resend domain (`jurasolutions.sg` DNS) | choose, verify | Resend, Cloudflare DNS | Ting Yu | partly (DNS present) |
| Resend outreach key and webhook endpoint | create | Resend | Ting Yu | not done |
| Zoho IMAP for info@ (optional) | enable, app password | Zoho Mail | Ting Yu | not done |
| Cowork morning brief line | paste | Cowork | Ting Yu | unverified |
| Social accounts, community groups | create, join | LinkedIn, Meta | Ting Yu | not done / unverified |
| CI | none (no `.github/`; tests run locally) | none | none | not applicable |

## Secrets

No values appear here. "Growth" means `repos/growth/.env` (mode 600), or a Keychain item named in
`.env` as `keychain:<service>`.

| Secret | Where it lives | Created by | Status |
|---|---|---|---|
| `DISCORD_WEBHOOK_<8 channels>` | growth | Ting Yu (Discord) | not set |
| `RESEND_API_KEY_OUTREACH` | growth (Keychain recommended) | Ting Yu (Resend, sending-only) | not set |
| `UNSUBSCRIBE_SECRET` | growth **and** Pages (prod and preview), identical | Ting Yu (`openssl rand -base64 48`) | not set (growth); unverified (Pages) |
| `CLOUDFLARE_API_TOKEN` | growth (Keychain recommended) | Ting Yu (Cloudflare) | not set |
| `CLOUDFLARE_ACCOUNT_ID`, `D1_DATABASE_ID` | growth (identifiers, not secret) | Ting Yu (dashboard) | not set |
| `OUTREACH_IMAP_HOST`, `_PORT`, `_USER`, `_PASSWORD` | growth (password in Keychain) | Ting Yu (Zoho) | not set (optional) |
| `RESEND_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`, `TURNSTILE_SECRET`, `VISITOR_SALT`, `RESEND_API_KEY` | Pages only, never growth | Ting Yu | unverified |
| Claude Code login | macOS login Keychain ("Claude Code-credentials") | Ting Yu (`claude auth login`) | present |

Headless runs can't read `.env` (`runner.py:233`), and secrets are never exported to their
environment (`config.py:90-100` reads them in-process). No wizard script was generated: the
sending-domain and Keychain decisions change what it would walk through.

## Deploy plan

1. **Pre-deploy.**
   - Growth migrations apply forward on the first connection (`db.py:20-25`). There are no down
     migrations; the rollback for the database is a copy from `data/growth/backups/`.
   - Clear the stale journal from the Mac (A5).
   - Decide on the 2026-10-26 rows (A6).
   - For stage B: D1 `0001_toolbox.sql` (`toolbox-ai.md` §2), the Pages variables, then the
     website deploy.
   - Feature flags: `scout.yaml` `mode` and `legal_review_done`; `social.yaml` `publish_mode`.
2. **Deploy.** Ting Yu triggers every step from Terminal on the Mac. Stage A7: system jobs, then
   the content jobs, then the scout jobs in shadow. Stage B: deploy the website, run the smoke
   checks in step 3, the three-day shadow trial, then `mode: live`.
3. **Smoke checks.**
   - `jura-growth status` shows `installed yes` for each installed job and `8 of 8` webhooks.
   - `launchctl print gui/$(id -u)/sg.jurasolutions.growth.heartbeat` shows the job.
   - A heartbeat appears in `#daily-digest` at 12:00.
   - At 17:30, `data/growth/daily-summary.json` and `outputs/growth/digests/<date>.md` appear.
   - Stage B: `curl https://jurasolutions.sg/api/resend-webhook` returns JSON with
     `canVerify` and `canStore` true.
   - Stage B: open the link from `jura-growth outreach unsubscribe-link <a test address you own>`,
     land on `/unsubscribed`, then `jura-growth outreach sync` reports 1 new suppression.
   - Stage B: `jura-growth outreach status` prints no "would refuse" lines.
4. **Watch.**
   - Sources: `#alerts`; `data/growth/launchd/<job>.log`; `jura-growth log events`;
     `data/growth/transcripts/`; Resend's bounce and complaint figures.
   - Roll back on any complaint or a bounce rate above 3% over 50 sends (the code auto-pauses).
   - Also roll back on three failed runs in a row (auto-pause) or a missing 12:00 heartbeat.
5. **Rollback.**
   - `touch repos/growth/PAUSE` stops everything at once; `jura-growth pause all` stops the agents.
   - `jura-growth schedule uninstall` removes the jobs. Set `mode: shadow`.
   - Restore `growth.db` from `backups/` if it is damaged. Revoke the outreach key and the webhooks
     if needed.
   - A rollback doesn't undo emails already sent, Discord posts, app PRDs written to
     `prd/pending/apps/`, posts Ting Yu made by hand, or D1 suppression rows (keep those).

## Risks

| Risk | Mitigation |
|---|---|
| The Mac sleeps, restarts or sits at the FileVault screen, and runs are late or missed | A4 settings; log in after restarts; the noon heartbeat as the check |
| SQLite written from a VM or sandbox leaves a hot journal, and a later open undoes a commit (seen today) | Run `jura-growth` only on the Mac; never from Cowork or a sandboxed agent; check for `growth.db-journal` after setup |
| Emails link pages production doesn't serve | B4 before B14; add a site check to `live_problems()` (developer ticket) |
| Claude Max usage limits are shared with interactive work; a 09:00 scout run can fail on a limit and three failures auto-pause | Budgets are already capped at US$3 and US$5 per run; watch `#alerts`; avoid heavy sessions around 06:30–09:30 |
| Resend free plan (100 a day, 3,000 a month, one domain) is shared with the enquiry form; outreach complaints affect enquiry mail too | Caps of 20 a day and 600 per 30 days in code; scout PRD §6 Q2 decides on a subdomain with Pro |
| No reply detection, so opt-outs by reply depend on Ting Yu reading info@ | B13: Zoho IMAP, or a daily habit of checking info@ |
| The Cloudflare token is account-wide on D1 | Shortest practical permission and an expiry; Keychain storage |
| Database and backups live on one disk | D2 |
| Registry drift between the local checkout and production | C4 |
| Test runs writing frozen-clock rows into the live database | Run build tests against a copy (`JURA_GROWTH_DATA_DIR`); see A6 |
