# 03 — An agent still pauses itself when Discord can't be reached

Status: ready-for-agent
Blocked by: -
Covers: foundation B2

## Problem

After a failed run, the runner posts the alert to Discord before it checks auto-pause (`runner.py:133-135`). `discord._send` doesn't catch `httpx.HTTPError` (`discord.py:151-170`) and `post()` catches only `DiscordError`, so a refused connection, a DNS failure or a timeout escapes. `check_auto_pause` never runs and `jura-growth run` crashes. A Mac waking from sleep is exactly when runs fail and Discord is unreachable.

## What to change

- Turn transport errors in `_send` into `DiscordError`, and fall back to the outbox when delivery fails.
- Make the auto-pause check run whatever happens to the alert.

## Acceptance criteria

- With `DISCORD_WEBHOOK_ALERTS` pointing at a refused port and a job that always fails, three failed runs in a row pause the agent and the fourth run is skipped as paused (the reviewer's reproduction in `audit/code-review-01-foundation.md` B2, as a regression test).
- `jura-growth run` exits with the run's own status, not a Python traceback, when Discord is down.
- The undelivered alert lands in `data/growth/discord-outbox/`.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-01-foundation.md` B2
- `jura_growth/runner.py:127-136`, `jura_growth/discord.py:100-170`, `jura_growth/pause.py`
