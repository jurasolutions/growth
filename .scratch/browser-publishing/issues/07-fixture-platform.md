# 07 — A fixture platform for the browser rehearsal

Status: ready-for-agent
Blocked by: 03

## Problem

Ting Yu's rehearsal steps R1 to R6 (before the first live post, U12) drive the real `publish` job against local fixture pages, but there is no platform switch for a fixture site (http, a local port, a `publish-fixture.localhost` host), so the rehearsal can't run.

## What to change

Add a fixture platform the publish job accepts only when it points at a loopback host and a temporary data folder (the same guard style as the UAT stubs in ticket 18), with its own ClaudeInChromeDomain rule. It must be impossible to enable in production data. Wire it into `uat.md` R1-R6 and the UAT seed.

## Acceptance criteria

- With the fixture platform configured on a temp data folder, the publish job targets only the fixture host; any other host is refused.
- With the live data folder, or a non-loopback host, the fixture platform is refused.
- At R1, try a parameter allow rule for file_upload paths (only `work/publish/`); record whether Claude Code honours it in the ticket's Comments.
- `uv run pytest -rs` passes with 0 skipped.

## Pointers

- `.scratch/browser-publishing/issues/03-browser-job-facebook-page.md` (BP-03 report in crew-log); `jura_growth/agents/publish/scope.py`; `jura_growth/uat_stub.py`; `.scratch/mission-control/uat.md` R1-R6

## Comments

### 2026-10-27 developer: built

The fixture platform is `JURA_GROWTH_PUBLISH_FIXTURE_URL` (`jura_growth/agents/publish/fixture.py`). It is a switch over the existing platforms, not a new platform name: while it is set, the fixture host replaces every platform's hosts, so the rehearsal drives Facebook's own prompt section and, for BP-04, each new platform's. Its guard takes only an `http://` URL on a loopback host with no user name or path (narrowed in fix round 1, below), and a temporary data folder (`uat_stub.temporary_data_problem`). A refused fixture fails the publish run in its precheck before Claude starts, the argv can't be built, and `publish next` claims nothing. It never falls back to the real hosts.

The rehearsal steps are in `uat.md` Part R. The UAT seed gains `fixture-post --page <page>` (R1 to R4, R6) and `fixture-join --page <page>` (R5).

**The `file_upload` parameter allow rule (R1): not yet tried.** It needs real Chrome and a real `claude -p`, so it is Ting Yu's step. `uat.md` Part R, R1b, gives the two probes and how to read them. Result: _to record here after R1._

### 2026-10-27 developer: fix round 1 (code review 07)

- **B1.** The guard now reads the URL the way a browser's WHATWG parser does. `uat_stub.loopback_url_ok` is the one loopback check for the UAT stubs and the fixture (ST-1). It refuses a backslash, `%`, `@`, whitespace, control characters and non-ASCII characters anywhere, a malformed port, and a host that isn't exactly one of the allowed names. For the fixture, those names are `publish-fixture.localhost`, `127.0.0.1` and `::1`: no longer `localhost` or any other `*.localhost` name, because a domain rule names a host, not a port (SEC-n1). The reviewer's `http://evil.com\.localhost:8765` and the other WHATWG tricks are regression cases in `tests/test_publish_fixture_platform.py`.
- **ST-2.** Page addresses on the fixture go through `hosts.url_problem`, which now takes a scheme and a port, and refuses a backslash anywhere.
- **SP-1.** `prompts/publish.md` step 8 and the Facebook permalink line now say the permalink is the address the post's timestamp links to, on the same host as the target URL. That is true on Facebook and on the fixture's `post.html?id=<n>`.
- **ST-n4.** A refused fixture in `publish done` and `publish resolve` now reads `refused: …`.

**AC3 stays open, and the ticket can't close until it is recorded.** Ting Yu runs R1b during R1. The two probe results, with their `permission_denials` lines, go in these Comments after R1 and before the ticket closes.

### 2026-10-30: conductor, rehearsal Part R in real Chrome (scheduled run, 09:07 to 09:46 SGT)

The real `publish` job ran with `--chrome` against the fixture site on 127.0.0.1:8765, from a detached worktree of main (0410a37), with a temp UAT folder (`/tmp/jura-uat`) and the extension in Ting Yu's Jura profile. No run touched a non-fixture host. Evidence: `jurasolutions/data/growth/uat/rehearsal-2026-10-30/`.

**R1b, recorded (the open question of this ticket).**
- **Probe 1** allowed only the parameter rules `navigate(url:<fixture>/page.html)` and `file_upload(paths:<work>/*)`, with no domain rule. Even the navigation was denied, so a parameter allow rule isn't honoured for the Chrome tools, and the probe can't speak to `file_upload`. `permission_denials`: `[{"tool_name": "mcp__claude-in-chrome__navigate", "tool_input": {"url": "http://publish-fixture.localhost:8765/page.html", "tabId": 354948134}}, {"tool_name": "mcp__claude-in-chrome__find", "tool_input": {"query": "image file input", "tabId": 354948134}}]`
- **Probe 2** added `ClaudeInChromeDomain(publish-fixture.localhost:8765)`. Both uploads were allowed, the claimed copy and `outside.png` alike. `permission_denials`: `[]`
- **So:** a parameter rule can't narrow `file_upload`. Under the domain rule, the upload limit is what the session may read.
- **Probes 3 and 4 (added):** a `Read` deny rule on a file makes `file_upload` refuse it ("Cannot upload … only files this session is allowed to read"). Probe 3, on a file named `.env`, was also refused by Claude Code's own server-side safety check. The publish argv already denies Read on `.env*`, `.dev.vars*` and the env file under `JURA_ROOT`, so secrets can't be uploaded. Other readable files could be uploaded, and the audit catches any upload that isn't one of the claimed copies.

**The fixture platform itself:** its domain rule had to name the port, `ClaudeInChromeDomain(publish-fixture.localhost:8765)`; the bare host denied `navigate`. Fixed in growth PR #6, with three more defects the run found (uploads, and the audit's reading of real tab context). Each one failed closed.

This ticket can close once PR #6 merges: AC3 has its answer, recorded above.
