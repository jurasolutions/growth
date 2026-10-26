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
