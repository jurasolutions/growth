# 03 — BP-03 the browser job, posting to the Jura Facebook Page

Status: ready-for-agent
Blocked by: 01, 02, mission-control#03, mission-control#08, mission-control#11
PRD ticket: BP-03 in `prd-jura-browser-publishing-2026-10-25.md` §5.12 (mission-control#08 added as an edge by the ticket review)
Covers: SC6, SC8, SC9, SC10 (from Discord), SC11 (Facebook Page); ADR 0005

## What to build

A scheduled `publish` job, every 20 minutes from 09:00 to 17:40 SGT, that drives the dedicated Chrome profile through Claude in Chrome to post one approved Facebook Page item, read the live post back and record its URL. A code precheck skips without starting Claude when nothing is claimable. The run checks the browser and the posting identity before claiming or typing, stops on any stop signal, and is audited afterwards for every host it saw and every character it typed, and the audit can fail the run. Only this job ever gets `--chrome`. Ting Yu can settle an `unknown` item and resume publishing from Discord.

## What to change

- `runner.claude_command` appends `--chrome` only for jobs in `caps.BROWSER_JOBS`, and raises `JobError` if any other job sets `browser: true`. This is the second and last `runner.py` change in both features (after mission-control#01).
- The publish argv as AC-P9.2: page tools only through `ClaudeInChromeDomain(<host>)` rules for the enabled platforms' hosts, listed in the plug-in, using what 01's U18 found about subdomains; named denies; no `--add-dir`; Bash only for `publish next`, `done`, `stopped` and `note-rules`.
- `precheck(job, conn)` in `agents/publish/job.py`, reusing 02's `claimable()` read-only: it returns `NothingToDo("nothing due")` (mission-control#01), which the runner records as `run.quiet`; when `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` is set it returns a plain skip string with the reason, because that is a problem Ting Yu should see.
- The publish plug-in's `setup_gaps()` hook (mission-control#08) lists the auth variable, so `jura-growth status` shows it.
- `prompts/publish.md` as BP §5.8, with one heading per item kind and platform, the ones not yet enabled marked as such; 04, 05 and 06 each fill only their own section.
- The publish plug-in's `after_run` (mission-control#01's hook, before `finish_run`): the host and typed-text audit over every tool result through `transcripts.read()`, returning a failed `Outcome` when it fails so the run row, the alert and auto-pause see it; recognise the no-browser outcome and alert once a day; the run update only when an item was claimed (`run_update: claimed-only`).
- Publish transcripts kept 7 days, not 30, and run updates never quote page text.
- The job in `config/settings.yaml`, directly after `community`: kind `claude`, `quiet: true`, `browser: true`, the 20-minute daily schedule.
- `publish queue` and `publish resolve` on mission control's sorted remote allowlist, with their rows in `docs/dispatch-contract.md`.
- ADR 0005 moves to accepted.
- The fixture site under `tests/fixtures/publish-site/` and the fake `claude` scenarios (test strategy v3 §2, datasets T and F).

## Acceptance criteria

- [ ] **AC-P8.1** Given a claimed item, then one run update posts in `#social-drafts` or `#community`
  with the A-nnnn id, the platform or group, the outcome, and the URL or stop reason. Stops,
  mismatches and `unknown` items also go to `#alerts`.
- [ ] **AC-P8.2** Given nothing claimable, when the slot fires, then the plug-in's `precheck()` skips
  with "nothing due", no `claude -p` starts, a quiet skip is recorded, and nothing posts.
- [ ] **AC-P9.1** Given the argv built for every job in `settings.yaml`, and for a fake job that sets
  `browser: true` but isn't in `caps.BROWSER_JOBS`, then only `publish` gains `--chrome`; the fake
  job raises `JobError`; no other argv contains `mcp__claude-in-chrome__*` or `ClaudeInChromeDomain`;
  and `community` keeps its Facebook `WebFetch` denies.
- [ ] **AC-P9.2** Given the `publish` argv, then it keeps `--strict-mcp-config`, `--permission-mode
  dontAsk` and `--setting-sources project`; has no `--add-dir`; allows by name only the tab tools
  (`tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp`, `list_connected_browsers`), plus one
  `ClaudeInChromeDomain(<host>)` rule per host of the enabled platforms (never a Discord host); and
  denies by name `javascript_tool`, `read_network_requests`, `read_console_messages`,
  `shortcuts_execute`, `shortcuts_list`, `gif_creator`, `switch_browser`, `select_browser`,
  `browser_batch`, `resize_window`, `WebSearch` and `WebFetch`, and `file_upload` on an item with no
  image.
  *Owned here for the Facebook Page hosts. 04 adds the Instagram and LinkedIn hosts.*
- [ ] **AC-P9.3** Given a publish transcript with a `navigate` to `https://example.com`, a foreign URL
  shown only in a later tool result's tab URL, a Discord host, a tool call on a tab this run didn't
  create, or typed text that isn't part of the approved content, then the audit fails the run and
  pauses `publish`. A tab left open is a warning in the run update.
- [ ] **AC-P9.4** Given "No browsers are connected" on the first browser call, then the run ends
  `SKIP:` without claiming anything (the browser check comes before `publish next`), the item stays
  approved until its deadline, and one alert a day says so.
- [ ] **AC-P9.5** Given `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` in the environment, then
  `precheck()` skips with that reason and `jura-growth status` lists it as a setup gap.
- [ ] **AC-P11.1** Given the prompt's first steps, then the run checks the connected browser and that
  the page shows the expected posting identity (the Jura Page, the Jura Instagram account, the Jura
  LinkedIn company page, or the Jura Page as the group identity) before any typing; on a mismatch
  it calls `publish stopped <id> --reason wrong-identity`.
  *Owned here for the Jura Facebook Page. 04 proves the Instagram account and the LinkedIn company page; 05 the Page as the group identity.*
- [ ] **Run-side halves of 02's criteria.** In a fake-`claude` run: AC-P2.1 and AC-P2.2 (nothing due, and the claim before any browser call); AC-P5.3 (the fake `claude` binary never starts for any of the switches); AC-P6.1 (the run calls `publish stopped --reason login` on the login page); AC-P10.1 (the `#alerts` text names the two `/growth publish resolve` forms).
- [ ] **From Discord.** AC-P6.3 (`/growth resume publish` works) and AC-P10.2 (an `unknown` item settled through `jura-growth remote`); AC-M10.1 and AC-M7.7 (owned in mission control) hold for the `publish` commands and job.
- [ ] **X4, X5 and X8 (argv).** The job's settings and schedule; publish transcripts kept 7 days and others 30; no `--add-dir` in the argv.
- [ ] The sweep in `tests/sweep.py` passes over this ticket's messages (the publish run updates and the `#alerts` posts for stops, mismatches and `unknown` items): no planted secret or personal data reaches the Discord double or the outbox (AC-M11.1 and AC-M12.1, owned by mission-control#02).
- [ ] `--chrome` appears nowhere in `jura_growth/` except the single `BROWSER_JOBS` branch in `runner.claude_command`, and `tests/test_community_fetch_block.py` passes unchanged (ticket 02 stands).
- [ ] `docs/adr/0005-browser-automation-runs-only-in-the-publish-job.md` says accepted.
- [ ] AC-M15.1 (owned by mission-control#01) still holds; no automated test opens a real social site or real Chrome.

## Done when

The agent's part is done when every criterion above passes, `security-review` has run on `agents/publish/` and the `runner.py` change, `uv run pytest` passes, and the report is in. The ticket closes after Ting Yu's rehearsal on the fixture site and live step U12, each recorded in `reviews/qa-03.md`. The rehearsal steps, all before U12 (test strategy v3 E13): R1 (an approved fixture post, end to end); R2 (each stop page: login wall, CAPTCHA, checkpoint, rate limit, removal notice, admin warning; the run calls `publish stopped` with the right reason and clicks nothing further); R3 (the page linking to `example.org`: no navigation there, and if attempted it is denied and the audit fails the run); R4 (the injection page); R6 (a different identity: `publish stopped --reason wrong-identity` before any typing). U12: one approved post goes live on the Jura Facebook Page through a scheduled run with its URL recorded; a skipped and an expired item don't post; a forced login wall stops the run, pauses the agent and alerts. Rehearsal needs 01 passed. Then wait for go-ahead.

## Pointers

- PRD: BP §4.6, §4.7, §4.9, §5.3, §5.8, §5.9, §5.13; MC §5.10 (the `publish` rows)
- `.scratch/mission-control/reviews/tickets-technical.md`: T3, T5, N8, Q1
- `.scratch/mission-control/reviews/technical-v2.md`: B8, N8, N9, N10, N15; ADR drafts
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §2 (fake `claude`, fixture site), §3 (T, F), §4.2 (AC-P rows by id), §4.3 (X4, X5, X8), §7 (R1 to R4, R6, U12), §11.2 row BP-03
- `.scratch/browser-publishing/spike-headless-chrome.md`; `docs/adr/0005-…`
- Code: `jura_growth/runner.py` (`claude_command`), `caps.py`, `transcripts.py`, `headless.py`, `agents/publish/job.py`, `config/settings.yaml`
