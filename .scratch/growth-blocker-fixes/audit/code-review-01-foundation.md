# Code review 01: growth foundation core against its PRD

**Verdict: changes-requested.** Three blocking findings (B1 to B3 below). Each one breaks a PRD success criterion, and I reproduced each one.

- **Repo:** `jurasolutions/repos/growth`, branch `main`, HEAD `6eabfe7`, working tree clean.
- **Spec:** `jurasolutions/prd/pending/prd-jura-growth-foundation-2026-10-24.md`.
- **Point of comparison:** the whole tree at HEAD. This is a review outside a feature, so there is no branch diff. I ran the standards, spec and security passes myself instead of through the diff-based skills, because those skills need a diff to point at.
- **Scope:** `jura_growth/` minus `agents/<name>/`, plus `agents/__init__.py`, `migrations/`, `launchd/`, the five named config files, `tests/test_core.py`, `tests/test_brand_check.py`, and the setup guides `outputs/growth/setup/discord.md` and `morning-brief.md`. I read every file in scope in full.
- **How I got the evidence:** I made no changes to the repo and touched nothing under `data/growth/`. Every reproduction below ran with `JURA_GROWTH_DATA_DIR`, `JURA_GROWTH_ENV_FILE`, `JURA_GROWTH_PAUSE_FILE` and `JURA_GROWTH_CONFIG_DIR` pointed at a scratch folder, and with a fake `.env`. I never read the real `.env`, and none exists yet.

Evidence commands:

- `.venv/bin/python -m pytest -o addopts="" -q -p no:cacheprovider tests/test_core.py tests/test_brand_check.py -k "not plist and not claude"` printed **120 passed, 4 deselected**. I deselected four tests because they write into the repo tree (see N5). The conductor's full-suite baseline was 515 passed.
- `jura-growth check "<text>"` probes, shown under each finding.
- `jura-growth schedule list` printed the nine jobs, matching the PRD §5.4 times plus the heartbeat at 12:00 and the backup at 23:30.
- `claude --help` (2.1.286) lists every flag the runner uses, including `--permission-mode dontAsk`, `--max-budget-usd`, `--no-session-persistence`, `--strict-mcp-config` and `--setting-sources`.

---

## Spec coverage table

Status values: **implemented**, **partial**, **missing**, **deviates**. Finding IDs refer to the next section.

### §2 Success criteria

| # | Criterion | Status | Evidence | Notes |
|---|---|---|---|---|
| 1 | "Jura HQ" gets posts from every agent in the right channel | implemented (not live) | `config/settings.yaml:9-19`, `discord.py:39-50`, `discord.py:82-126` | The eight channels match §5.2. No `.env` exists yet, so every post goes to `discord-outbox/`. Block 0's done-when is still open. |
| 2 | Every run and event goes to SQLite, is mirrored to JSONL, and is backed up nightly with 14 days kept | partial | `log.py:31-58`, `migrations/0001_core.sql`, `backup.py:13-40` | The headless-run events `claude.start`, `claude.result` (which carries the permission denials) and `claude.unprefixed` go to JSONL only. A failed DB write also loses the JSONL line (S10). |
| 3 | Fixed SGT schedule. A missed run fires on wake without breaking send windows | partial | `schedule.py:45-109`, `runner.py:139-146`, `agents/outreach/send.py:122-132` | Sending re-checks the window and is safe. A missed 17:30 digest summarises the wrong day (S5). |
| 4 | All outgoing text passes a brand checker enforcing DS §3 | partial | `brand_check.py:109-143`, `gate.py:39-80` | Spelled-out figures pass the numbers rule (B3). Buzzword inflections, curly-apostrophe urgency and bare domains also pass (S1 to S3). `check` is an uncounted oracle (S4). |
| 5 | One command pauses an agent or all agents. Agents pause themselves after repeated failure | partial | `cli.py:221-241`, `pause.py:28-82`, `runner.py:133-135` | Auto-pause is defeated when Discord is unreachable (B2). A single failure re-pauses straight after a resume (S6). |
| 6 | Morning brief line, plus a 17:30 digest | partial / deviates | `digest.py:20-112`, `setup/morning-brief.md:5-18` | The digest is complete. The brief line is a manual paste into Cowork, because `toolbox/morning-brief.md` does not exist. |
| 7 | Secrets never appear in the repo, logs or Discord | partial | `.gitignore:6-9`, `config.py:128-153`, `discord.py:166-168` | A headless run can print `.env` through `jura-growth` (B1). Discord content and the outbox are not redacted (S8). |

### §5 Proposed plan

| Item | PRD line | Status | Evidence | Notes |
|---|---|---|---|---|
| Layout | §5.1 | implemented | repo tree, `paths.py:17-65` | Extras: `gate.py`, `runner.py`, `transcripts.py`, `locks/`, `work/`, `discord-outbox/`. |
| Channels | §5.2 | implemented | `settings.yaml:9-19`, `setup/discord.md:17-28` | |
| Tables: runs, events, discord_posts, suppression, pause_flags, schema_migrations | §5.3 | implemented | `migrations/0001_core.sql:3-71`, `db.py:62-83` | Events are append-only through triggers (`0001_core.sql:29-32`). Extra columns: `job`, `cost_usd`, `agent`, `delivered`, `email_hash`. Extra table: `qa_attempts`. |
| Events mirrored to `runs/YYYY-MM-DD.jsonl` | §5.3 | partial | `log.py:45-58` | S10 |
| Headless `claude -p` with a prompt file and an allowlist | §5.4 | implemented | `runner.py:218-256`, `runner.py:276-323` | The allowlist is passed as CLI flags, not a project settings file. Same effect. |
| Permission mode | brief | implemented | `runner.py:245` (`dontAsk`) | Valid in the installed CLI 2.1.286. |
| Allowed tools | brief | implemented | `runner.py:226-231` | `Bash(jura-growth:*)`, plus Write and Edit in `work/<job>/**` only, plus each job's own tools. |
| Refused tools | brief | partial | `runner.py:232-238` | `Read(.env)`, `jura-growth run`, `resume` and `schedule` are refused, and so is facebook.com for community. The `.env` refusal can be bypassed (B1). |
| No MCP | brief | implemented | `runner.py:246-247` | `--strict-mcp-config` with no `--mcp-config`, plus `dontAsk` with no `mcp__` tool allowed. One human check is listed below. |
| Budget cap | brief | implemented | `runner.py:239`, `settings.yaml:26`, `settings.yaml:66` | US$3 per run, US$5 for scout research. No hard ceiling in `caps.py` (N12). |
| Transcripts | brief | implemented | `runner.py:279-299` | Full stream-json is kept. Pruned at 30 days, which keeps 31 (N4). Transcripts are not redacted (B1). |
| Check how the morning brief is scheduled | §5.4 | implemented | `README.md` "Why launchd", `PRD-ting-yu-ai-os.md:513` | The AI OS PRD says block 4.2 is run by Cowork. |
| Business days and holidays skipped for sending | §5.4 | implemented | `runner.py:139-146`, `holidays.py:28-37`, `outreach/send.py:124` | Fails open when a year is missing from the holidays file (S9). |
| Missed calendar job runs on wake | §5.4 | implemented | `schedule.py:104`, `schedule.py:107` | launchd coalesces missed slots into one run. A Mac that is off or logged out misses the run, as documented. |
| Unsent email rolls to the next business day | §5.4 | implemented (agent) | `outreach/store.py:57`, `outreach/send.py:132` | Agent scope, noted only. |
| Holidays file, refreshed each December | §5.4 | implemented | `config/sg-public-holidays.yaml`, `holidays.py:50-58`, `digest.py:66` | Covers 2026 and 2027. The December reminder shows in `status` and the digest. |
| `.env` (mode 600) or Keychain | §5.5 | partial | `config.py:66-99`, `config.py:115-125` | `keychain:<service>` works. Mode 600 is only warned about, not enforced (N3). |
| Secret names | §5.5 | implemented | `.env.example:10-34` | Adds `UNSUBSCRIBE_SECRET`, which the PRD does not list. |
| Gate: block, log, #alerts, regenerate once, then drop | §5.6 | implemented | `gate.py:17-80` | Agents use stable item keys (outreach, social, community, apps). The `check` CLI bypasses the count (S4). |
| Rule 1: exclamation marks | §5.6 | implemented | `brand_check.py:211-215` | `‼` passes (N1). |
| Rule 2: emoji and emoticons | §5.6 | implemented | `brand_check.py:220-245` | `Thanks:)` with no leading space passes (N2). |
| Rule 3: buzzwords | §5.6 | partial | `brand_check.py:251-268`, `buzzwords.txt` | The seed list matches the PRD. Inflections pass (S1). |
| Rule 4: urgency | §5.6 | partial | `brand_check.py:273-302` | Curly apostrophes pass (S2). |
| Rule 5: questions as headings or subjects | §5.6 | implemented | `brand_check.py:308-315` | |
| Rule 6: em dashes and "this, not that" | §5.6 | implemented | `brand_check.py:320-343` | |
| Rule 7: numbers | §5.6 | partial | `brand_check.py:346-494`, `approved_claims.yaml` | Both seed claims are present. Spelled-out figures pass (B3). |
| Rule 8: sentence case | §5.6 | implemented | `brand_check.py:510-557` | False positive on headings that start with a digit (S11). |
| Rule 9: links | §5.6 | partial | `brand_check.py:148-185`, `brand_check.py:570-582` | Bare domains outside a 21-TLD list pass (S3). |
| Rule 10: channel hook | §5.6 | implemented | `brand_check.py:86-94`, `brand_check.py:139-142` | |
| Unit tests, passing and failing, for each rule | §5.6 | implemented | `tests/test_brand_check.py:25-272` | Rules 1 to 9 have both. Rule 10 is tested in the agent tests. |
| Digest writes json, posts, keeps an md copy | §5.7 | implemented | `digest.py:102-112` | Figures come from the plug-ins: sent, replies and unsubscribes (`outreach/__init__.py:38-50`), app PRD (`apps/__init__.py:52-61`), drafts waiting (`social/__init__.py`), pauses (`digest.py:36-38`). |
| Morning brief line in `toolbox/morning-brief.md` | §5.7 | deviates | `setup/morning-brief.md:5-9` | The file does not exist on disk. The guide asks for a manual paste into Cowork. |
| `pause` / `resume <agent\|all>` | §5.8 | implemented | `cli.py:221-241`, `pause.py:47-64` | `all` leaves digest and backup running (`settings.yaml:38`, `pause.py:40-43`). Documented, but the PRD doesn't say so. |
| `PAUSE` file, even with a broken DB | §5.8 | implemented (at start) | `runner.py:80-83`, `pause.py:30-32` | Checked before the DB opens. Not checked during a run (S7). |
| Auto-pause after 3 failures, posted to #alerts | §5.8 | partial | `pause.py:71-82`, `runner.py:133-135` | B2, S6 |
| Overlap lock and stale-run sweep | extra | implemented | `runner.py:59-73`, `runner.py:149-177` | |
| Nightly backup, 14 days kept | §2, Block 1 | implemented | `backup.py:13-40`, `settings.yaml:102-106` | Keeps today plus 13 days. Uses SQLite's online backup. The DB stays in rollback-journal mode for OneDrive (`db.py:24`). |

### §5.9 Build blocks

| Block | Status | Evidence | Done-when |
|---|---|---|---|
| 0: Discord guide | implemented | `outputs/growth/setup/discord.md` | **Open.** Needs Ting Yu to create the webhooks, then run `jura-growth discord test`. |
| 1: package, DB, logging | implemented | `cli.py`, `db.py`, `log.py`, `backup.py` | Met by `test_log_test_writes_both_stores` (`test_core.py:52`) and `test_backup_keeps_fourteen_days` (`test_core.py:306`). |
| 2: brand checker | implemented with gaps | `brand_check.py`, `cli.py:49-83` | `check` prints pass or fail with reasons. Tests pass. The gaps are B3 and S1 to S3. |
| 3: scheduler, kill switches, digest | implemented with gaps | `schedule.py`, `pause.py`, `digest.py`, `cli.py:335-356` | **Open.** Needs `schedule install`, a 12:00 heartbeat seen in #daily-digest, and the Cowork paste. |

---

## Findings, ranked

### Blocking

**B1. A headless run can read and print `.env` through `jura-growth`, which gets around the `Read(.env)` refusal.** This breaks SC7 and the §5.4 rule that a headless run cannot read `.env`.

How it happens:

- The sandbox allows `Bash(jura-growth:*)` and refuses only `Read(//<repo>/.env)` (`runner.py:226-238`).
- `jura-growth check --file` accepts any existing path (`cli.py:51`, `cli.py:61-62`).
- `check` prints each failing excerpt (`cli.py:79-82`). The link rule quotes the whole URL (`brand_check.py:577`), and the numbers rule quotes the whole line (`brand_check.py:482`).

Reproduced with a fake `.env` in scratch:

```
$ jura-growth check --file <scratch>/.env
fail
  - [numbers] "1234" needs a source: "RESEND_API_KEY_OUTREACH=re_FAKEFAKEFAKEFAKEFAKE1234"
  - [numbers] "1234567890" needs a source: "CLOUDFLARE_API_TOKEN=FAKEcfTOKENabcdef1234567890"
  - [numbers] "123" needs a source: "UNSUBSCRIBE_SECRET=fakesecretvalue123"
  - [links] Links only to jurasolutions.sg on this channel: "https://discord.com/api/webhooks/111/FAKEFAKEFAKE"
```

Why it matters:

- **The transcript keeps the secrets.** Whatever the command prints lands in the model's context and in the transcript, which is written unredacted (`runner.py:288-293`) and kept for 30 days.
- **A second way out.** `jura-growth discord post <ch> <text> --file <path>` uploads any readable file to Discord (`cli.py:201-209`).
- **A way to the internet.** Four jobs allow WebFetch to any host (`settings.yaml:51`, `58`, `65`, `92`). A prompt injection in a fetched page could chain the steps: print the secrets with `check --file`, then fetch an attacker URL that carries them.
- **Other repos are exposed too.** `--add-dir <jurasolutions>` (`runner.py:249`) leaves any future `repos/*/.env` or `.dev.vars` open to the Read tool, because only the growth `.env` is denied.
- **Nothing has leaked yet.** No `.env` exists in `repos/growth` yet.

Fix:

1. Add one path guard in `paths.py` and use it for every CLI option that takes a file. It should refuse `.env*`, `.dev.vars` and anything outside `JURA_ROOT`. Inside a run (`JURA_GROWTH_RUN_ID` set), it should allow only the job's `work/` folder.
2. Refuse `Bash(jura-growth discord post:*)` in headless runs.
3. Widen the Read deny rule to `Read(//<JURA_ROOT>/**/.env*)`.
4. Redact the actual secret values (loaded from `.env` and Keychain) from CLI output.

**B2. Auto-pause never fires when Discord can't be reached, and `jura-growth run` crashes.** This breaks SC5 and §5.8.

How it happens:

- After a failed run, the runner posts the alert before it checks auto-pause (`runner.py:133-135`).
- `_send` doesn't catch `httpx.HTTPError` (`discord.py:151-170`).
- `post()` catches only `DiscordError` (`discord.py:117`).
- So a refused connection, a DNS failure or a timeout escapes, and `check_auto_pause` never runs.

Reproduced with `DISCORD_WEBHOOK_ALERTS=http://127.0.0.1:9/x` and a job that always fails:

```
0..3 RAISED ConnectError [Errno 61] Connection refused
runs [failed, failed, failed, failed]   pause_flags []
control (Discord off): failed, failed, failed, skipped   pause_flags [('boomer', 1, '3 failed runs in a row')]
```

This is a likely failure mode. A Mac waking from sleep or on flaky Wi-Fi is exactly when runs fail and Discord is unreachable.

Fix:

1. Wrap `httpx.HTTPError` in `DiscordError` inside `_send`, and fall back to the outbox when delivery fails.
2. Run `check_auto_pause` before the alert, or in a `finally`.

**B3. The numbers rule lets spelled-out figures through in claims about Jura.** This breaks §5.6 rule 7, SC4, and the domain rule that is called non-negotiable.

How it happens: `FIGURE_RE` needs a digit (`brand_check.py:387-390`). `WORD_FIGURE_RE` knows only dozens, hundreds, thousands, millions, billions, twice, double, triple, tenfold and half (`brand_check.py:391-393`).

Reproduced:

- `"We have helped twelve businesses go live."` printed `pass`.
- `"Jura has served forty clients across Singapore."` printed `pass`.

Fix: add the cardinal number words (one to twenty, the tens, "a dozen", "a hundred") to `WORD_FIGURE_RE`, or normalise them to digits before the checks run. Add failing tests for both sentences above.

### Should fix

**S1. Buzzword inflections pass the brand check.**

- **Cause:** the pattern adds endings to the whole word (`brand_check.py:255-258`), so words ending in -e or -y never match their inflected forms.
- **Docs are wrong:** `config/buzzwords.txt:2-3` says -ing endings are caught.
- **Reproduced:** each of these printed `pass`:
  - "leveraging AI"
  - "Our synergies"
  - "supercharging"
  - "revolutionising"
  - "game-changing"
  - "empowerment"
  - "disruptive"
- **Fix:** handle the stems (drop a trailing -e or -y before the suffix, and add -ment, -ion, -ive, -ies and -ness), or list the forms explicitly. Add tests.

**S2. Urgency phrases with a curly apostrophe pass.**

- **Cause:** the patterns use `'?`, which matches only a straight apostrophe (`brand_check.py:279`, `283`, `293`).
- **Reproduced:** "Don’t miss out on the grant.", "Don’t wait…" and "Before it’s too late…" all printed `pass`.
- **Fix:** use `['’]?`, or normalise quotes before running any rule.

**S3. Bare domains are only caught for 21 hard-coded TLDs.**

- **Cause:** a fixed TLD list (`brand_check.py:152-156`).
- **Reproduced:** "Read more at bit.ly/jura-x" and "evil.shop/offer" both printed `pass` on the general channel. Many platforms turn bare domains into links.
- **Fix:** match any TLD of two or more letters and guard against false positives, or use a public-suffix list.

**S4. `jura-growth check` is an uncounted oracle, so "regenerate once, then drop" doesn't limit attempts.**

- **Cause:** `check` calls `brand_check.check` directly, not `gate.gate` (`cli.py:49-83`).
- **Effect:** an agent can check as often as it likes before it submits, and `prompts/community.md:96-97` tells it to pre-check. The repo's `CLAUDE.md` describes `check` as the gate.
- **Fix, either way:**
  - Inside a run, make `check` take `--item <key>` and count attempts in `qa_attempts`.
  - Or document `check` as an uncounted preview and drop the pre-check instruction from the prompt.

**S5. A missed 17:30 digest summarises the wrong day.**

- **Cause:** `build()` uses today's date (`digest.py:21`). launchd fires a missed digest on wake.
- **Reproduced:**
  - Runs were recorded on 2026-10-25, and the digest ran at 07:05 on 2026-10-26.
  - It printed `Jura growth, 2026-10-26: no app PRD today; paused: boomer.` with `runs {}`.
  - The previous day's four failed runs never reach the 08:00 brief.
- **Fix:** when the digest runs before 17:30 and the previous day has no digest yet, summarise the previous day.

**S6. After a resume, a single failure re-pauses the agent.**

- **Cause:** `check_auto_pause` counts the last three finished runs, including the ones from before the resume (`pause.py:71-82`).
- **Reproduced:** `resume`, then one failed run, then `is_paused` returned `3 failed runs in a row`.
- **Fix:** count only runs that started after the pause flag's `set_at`.

**S7. The `PAUSE` file and pause flags are only checked when a run starts.**

- **Cause:** the checks happen at `runner.py:80` and `runner.py:101` only. A headless run already in progress keeps going for up to 30 minutes (`runner.py:299`).
- **Gaps:** the core side-effect commands never check (`discord post` at `cli.py:201-209`, `digest`, `heartbeat`).
- **Already safe:** email sending re-checks (`outreach/send.py:216`, `outreach/send.py:258`).
- **Fix:**
  - Poll for the `PAUSE` file during `_run_claude` and kill the process when it appears.
  - Refuse side-effect commands in the `cli` group callback when `JURA_GROWTH_RUN_ID` is set and the agent is paused.

**S8. Discord content and the outbox are not redacted.**

- **Cause:** alerts use the raw `outcome.error` (`runner.py:134`). `post()` sends and stores content as it is (`discord.py:105`, `discord.py:116`, `discord.py:190-200`). Only the `alert` event payload is redacted.
- **Reproduced:** an alert containing a webhook URL and a `Bearer` token was written raw to `discord-outbox/*.jsonl`. The event row was redacted.
- **Fix:** set `content = config.redact(content)` at the top of `post()`.

**S9. Holiday data fails open when a year is missing.**

- **Cause:** `is_business_day` treats a year with no entries as having no holidays (`holidays.py:28-30`). Missing data only raises a warning (`holidays.py:50-58`).
- **Effect:** if the December refresh is skipped, sending runs on 2028 public holidays.
- **Fix:** treat an uncovered year as "not a business day" for business-day jobs, and alert.

**S10. Permission denials and headless results reach JSONL but not SQLite. A database error also loses the JSONL line.**

- **JSONL-only events:** `runner.py:287`, `runner.py:314-320` and `runner.py:334` pass `conn=None`, so these events never reach the events table. SC2 says every event is in SQLite.
- **Lost lines:** `log.event` writes the database row before the JSONL line (`log.py:45-52`).
  - Reproduced: an event logged on a closed connection raised `ProgrammingError` and wrote 0 JSONL lines.
  - The docstring says the mirror survives a broken database.
- **Fix:**
  - Pass the connection, or reopen one after the subprocess exits.
  - Write the mirror line first, or write it in a `finally`.

**S11. Headings and subject lines that start with a digit fail sentence case.**

- **Cause:** the check takes the first alphabetic word as the first word (`brand_check.py:530-534`).
- **Reproduced:** subject `"3 ways to cut invoice admin"` was flagged "starts in lower case". So was heading `"5 tips for faster approvals"`.
- **Effect:** this causes needless regenerations and drops for list-style social cards.
- **Fix:** ignore a leading numeral when deciding which word starts the heading.

### Nits

- **N1.** `‼` (U+203C) and `⁉` (U+2049) pass rules 1 and 2 (`brand_check.py:211-229`).
- **N2.** Emoticons are only caught after whitespace, so `"Thanks:)"` passes (`brand_check.py:231`).
- **N3.** `.env` handling is loose (`config.py:71-86`).
  - A permissive file mode is only warned about. The PRD says mode 600.
  - The parser doesn't handle `export KEY=` lines or inline `# comments`.
- **N4.** Retention edges and unpruned folders.
  - Transcript pruning keeps 31 days, not 30 (`backup.py:45`, `backup.py:55`).
  - `work/` and `discord-outbox/` are never pruned.
  - The launchd log files are never rotated (`schedule.py:105-106`).
- **N5.** Tests write into the repo tree.
  - `test_plist_is_valid` renders into `launchd/generated/` (`test_core.py:276-283`). The checked-out `launchd/generated/sg.jurasolutions.growth.digest.plist` now has its `StandardOutPath` under `/private/var/folders/.../pytest-161/...`.
  - Three tests write `prompts/fake.md` (`test_core.py:226`, `239`, `256`), because `prompts_dir()` can't be overridden (`paths.py:47-48`).
  - The README says tests never touch launchd.
  - Fix: add a `JURA_GROWTH_PROMPTS_DIR` override and an output-folder argument for `render`.
- **N6.** A dead webhook never alerts. The heartbeat and the digest record `ok` even when Discord refused the post (`cli.py:341-343`, `digest.py:110`).
- **N7.** A timed-out run loses its cost and kills only `claude` itself, not its children (`runner.py:300-303`). Fix: `start_new_session=True` plus `os.killpg`.
- **N8.** Small CLI and config tidy-ups.
  - `resume <typo>` silently prints "resumed" (`cli.py:233-241`).
  - `Solutions` is listed twice in `proper_nouns.txt` (lines 4 and 47).
- **N9.** The `PAUSE` file also stops `backup` and `digest` (`runner.py:80-83` runs before any system-agent exemption).
  - A long pause therefore means no backups, and the brief falls back to "no digest yet".
  - That matches the PRD's wording ("pauses everything"), but letting backup run is safer.
- **N10.** The numbers rule flags list counts in headings that contain a results word ("5 tips for faster approvals"). This is a judgement call.
- **N11.** Hard limits can be raised from config.
  - The per-run budget and the auto-pause threshold have no hard ceiling (`settings.yaml:26`, `30`, `66`; `runner.py:239`; `pause.py:73`).
  - `settings.yaml:3-4` says config may only lower a limit.
  - Fix: add ceilings to `caps.py` and apply them through `caps.effective`.

---

## Human setup items

| # | What a person must do | Read at |
|---|---|---|
| 1 | Create the "Jura HQ" server, the eight channels and one webhook per channel. Put the URLs in `.env` (none exists yet). Then run `jura-growth discord test`. This is Block 0's done-when. | `discord.py:43-50`, `config.py:90-99`, `settings.yaml:9-19`, `.env.example:10-17`, `cli.py:182-198` |
| 2 | Create `.env`: `cp .env.example .env && chmod 600 .env`, or store the secrets in Keychain and write `keychain:<service>` in `.env`. | `config.py:66-99`, `config.py:115-125` |
| 3 | Create a sending-only Resend key for outreach. | `outreach/send.py:89`, `outreach/send.py:427` |
| 4 | Set `UNSUBSCRIBE_SECRET` to the same value as in the website's Cloudflare Pages env. | `outreach/compose.py:77`, `outreach/queue.py:103`, `outreach/send.py:91` |
| 5 | Create a Cloudflare API token, and find the account ID and D1 database ID. The docstring says the token needs D1 read **and edit**, because the `/query` endpoint needs edit even for SELECT. The PRD says "read". Confirm the scope you can actually grant. | `cloudflare.py:5-6`, `cloudflare.py:23-29` |
| 6 | Optional: `OUTREACH_IMAP_*` for detecting replies. | `outreach/replies.py:53`, `outreach/replies.py:111-119` |
| 7 | Run `uv sync` so that `.venv/bin/jura-growth` exists. | `schedule.py:133-134` |
| 8 | Run `jura-growth schedule install`. Nothing is loaded until you do. Jobs run only while you are logged in (gui domain), and the Mac should be on SGT. Reinstall after travel. | `schedule.py:128-147`, `schedule.py:182-186` |
| 9 | Keep Claude Code installed and logged in. It is found at `~/.local/bin/claude` (2.1.286), which is on the plist PATH. Inspect one real transcript's init record and confirm it lists no MCP servers, including claude.ai connectors. | `settings.yaml:23`, `schedule.py:87-98`, `runner.py:246` |
| 10 | Paste the brief block into the Jura section of the Cowork morning-brief task. | `setup/morning-brief.md:13-18`; the file is written at `digest.py:104-105` |
| 11 | Observe Block 3's done-when: the 12:00 heartbeat appears in #daily-digest, `pause heartbeat` stops it, and `resume heartbeat` restarts it. | `settings.yaml:41-45`, `cli.py:335-343` |
| 12 | **Every December:** refresh `sg-public-holidays.yaml` from MOM. Also confirm the 2027 entries (lines 29-40) against MOM's published list now, especially the observed days and Deepavali. | `holidays.py:15`, `holidays.py:50-58`, `digest.py:66` |
| 13 | Ongoing: add an approved claim only with evidence. Maintain the proper nouns and buzzwords lists. | `approved_claims.yaml:8`, `brand_check.py:423-431`, `brand_check.py:510-512`, `brand_check.py:252-256` |
| 14 | Confirm the budget defaults (US$3 per run, US$5 for scout research) and the 30-minute timeout. There is no daily total cap. | `settings.yaml:24-26`, `settings.yaml:66` |
| 15 | Website contract: the D1 suppression reasons must be unsubscribe, bounce, complaint or manual. Any other value aborts the sync part-way. | `suppression.py:57-58`, `suppression.py:93-99` |
| 16 | Be aware that `data/growth/` (the DB, backups and transcripts, which include lead details) syncs to OneDrive, and the backups sit in the same folder. | `paths.py:24`, `backup.py:14` |

There are no TODO, FIXME or placeholder markers in scope (I grepped for them). The only empty values are the blanks in `.env.example`.

---

## Open PRD questions

1. **§6 Q1, how the morning brief is scheduled.** The builder answered this: Cowork runs the brief as a scheduled task (AI OS PRD block 4.2, "Who: Cowork"), so the growth jobs use launchd. The PRD file still lists it as open. *Recommended:* Ting Yu confirms, and the answer is written into the PRD.
2. **§6 Q2, Keychain or `.env`.** Still unresolved. The code supports both. *Recommended:* Keychain for every secret, so no secret file is on disk for a headless run to reach. This reduces the B1 risk but does not replace the B1 fix.
3. **New:** §5.7 names `toolbox/morning-brief.md`, which does not exist. *Recommended:* change the PRD to say the line is pasted into the Cowork task.
4. **New:** should `pause all` exempt the digest and backup? The code does; the PRD doesn't say. *Recommended:* keep the exemption and write it into §5.8.
5. **New:** should the `PAUSE` file stop backups? *Recommended:* no. Let backup run under `PAUSE`, and say so in §5.8.
