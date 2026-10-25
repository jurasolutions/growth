# Code review 03: an agent still pauses itself when Discord can't be reached

- **Branch:** `crew/growth-blocker-fixes-03-auto-pause-without-discord` (49060e4, 5fe3755)
- **Compared against:** `crew/growth-blocker-fixes` at 01ce0e9, the merge-base (`git diff crew/growth-blocker-fixes...crew/growth-blocker-fixes-03-auto-pause-without-discord`)
- **Spec:** `issues/03-auto-pause-without-discord.md`, which fixes `audit/code-review-01-foundation.md` B2
- **Reviewed:** 2026-10-24

## Verdict: approve

No axis has a blocking finding. Each acceptance criterion is met, and a test covers it. All seven new tests fail on the base code and pass on the branch. The full suite passes.

There are two should-fix findings:

- A Discord rate-limit answer with a non-JSON body still gets past the outbox (Spec 1).
- One test rebuilds a helper the suite already has (Standards 1).

Both are small. They can go in before the merge or as a follow-up.

## Files read

Changed:
- `README.md`: one line in "Where things go".
- `jura_growth/discord.py`: the whole file.
- `jura_growth/runner.py`: `run` and `_run_locked`.
- `tests/test_discord_down.py`: new.

Read for context, unchanged: `jura_growth/pause.py`, `jura_growth/cli.py` (`run`), `jura_growth/db.py` (`connect`), `jura_growth/config.py` (`secret`), `tests/conftest.py`, `tests/test_core.py` and `tests/test_scout_support.py`.

## Blocked paths

None were touched. The diff changes only the four files listed above. Nothing changed under `jurasolutions/inputs/`, `jurasolutions/design-system/` or `.env`. The live `jurasolutions/data/growth/` wasn't touched either: its outbox files were last changed at 01:23 and 01:25 today, before any review run.

## Standards

Sources: `CLAUDE.md`, `README.md`, `docs/agents/crew.md`, `docs/agents/domain.md` and the conventions of the surrounding code. The repo has no linter, and pyright is advisory.

### Should fix

1. **`tests/test_discord_down.py:63-64` and `:86-87` rebuild the outbox path and parse the JSONL by hand.**
   - **Rule:** reuse. The same job is done by `outbox(channel)` in `tests/test_scout_support.py:170`, which `test_outreach_send.py`, `test_outreach_sync.py` and `test_scout_leads.py` already import.
   - **Fix:** lines 63-65 become `assert [r["channel"] for r in outbox()] == ["alerts"]`, and line 87 becomes `assert outbox("alerts")[-1]["content"] == "hello"`.

### Nits

2. **`tests/test_discord_down.py:19-28` makes a real TCP connection.** That goes against the wording of `README.md` "Tests": "Tests never touch `jurasolutions/data/`, Discord, launchd or the network." The test frees a loopback port and then connects to it. There is also a small race: another process could take the port between the close and the post.
   - **Why it's only a nit:** the ticket's first acceptance criterion asks for exactly this reproduction ("pointing at a refused port"), and the connection never leaves the machine.
   - **If it ever flakes:** patch `discord.httpx.Client` with a `MockTransport` that raises `ConnectError`, which is the pattern `tests/test_core.py:114` uses.
3. **Possible Duplicated Code (judgement call), `jura_growth/discord.py:121-125`.** This block repeats the no-webhook branch at `:108-112`: `_outbox`, `_record(delivered=False)`, `log.event`, then `return PostResult(..., "...; saved to outbox")`. A small `_save_undelivered(...)` helper would remove both copies.
4. **`jura_growth/discord.py:14`** ("A failing run must still record itself and auto-pause when Discord is down") describes the runner, not this module. It fits better in the `runner.py` docstring, next to "Three failed runs in a row pause the agent".
5. **`tests/test_discord_down.py:31-41` (`failing_job`)** has the same shape as `_settings_with` in `tests/test_core.py:212-220`. That one is private to another test module, so this is a nit rather than a reuse finding.

### Checks that pass

- **Pyright:** HEAD has the same 3 errors as the base, and the new test file adds none (`docs/agents/crew.md`: "don't add new errors in files you touch").
- **Commits:** both subjects are sentence-case imperatives that match the history, and both carry the attribution trailer.
- **`except (httpx.HTTPError, httpx.InvalidURL)` isn't redundant.** In the installed httpx 0.28.1, `InvalidURL` subclasses `Exception` directly, not `HTTPError`.

## Spec

### Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| "three failed runs in a row pause the agent and the fourth run is skipped as paused" | met | `test_three_failures_pause_the_agent_when_discord_is_down` passes. On the base it fails with `assert None == '3 failed runs in a row'`. |
| "`jura-growth run` exits with the run's own status, not a Python traceback, when Discord is down" | met for the failures the ticket names (refused, DNS, timeout) | `test_cli_run_exits_with_the_runs_own_status_when_discord_is_down` passes. On the base, `httpx.ConnectError` escapes. Spec 1 below is a remaining gap. |
| "The undelivered alert lands in `data/growth/discord-outbox/`" | met | `test_undelivered_alert_lands_in_the_outbox` |
| "`uv run pytest` passes" | met | 522 passed |
| "Make the auto-pause check run whatever happens to the alert" | met | `runner.py:134-137` (try/finally) and `test_auto_pause_runs_whatever_happens_to_the_alert` |
| "Turn transport errors in `_send` into `DiscordError`" | met | `discord.py:158-168`, parametrised over `ConnectError`, `ConnectTimeout` and `ReadTimeout` |

### Should fix

1. **A 429 with a non-JSON body still gets past the outbox (`jura_growth/discord.py:170`).** Spec line: "fall back to the outbox when delivery fails".
   - **Cause:** the 429 branch runs `float(response.json().get("retry_after", 1.0))` outside the new `try`. Two answers make `post()` raise:
     - a 429 whose body isn't JSON. Cloudflare's rate-limit page in front of Discord is HTML, so this can happen.
     - a 429 whose `retry_after` isn't a number.
   - **Reproduced** with a `MockTransport`, so no network was used (`/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/probe_429.py`):

     ```
     429 text/html       : RAISED JSONDecodeError: Expecting value: line 1 column 1 (char 0)
     429 application/json: RAISED ValueError: could not convert string to float: 'abc'
     503 text/html       : delivered=False reason='Discord answered 503; saved to outbox'
     404 application/json: delivered=False reason='Discord answered 404; saved to outbox'
     runner.run(boomer) x4 with Discord answering 429 HTML:
       0 RAISED JSONDecodeError / 1 RAISED JSONDecodeError / 2 RAISED JSONDecodeError / 3 status: skipped
       pause flag: 3 failed runs in a row
       outbox lines added by the runs: 0
     ```

   - **Effect:** auto-pause still holds, because the `finally` and the autocommit connection (`db.py:22`) write the pause flag before the failing notify alert. So the harm B2 describes doesn't come back. But `jura-growth run` prints a traceback, and that alert never reaches the outbox.
   - **Why should fix and not blocking:** the ticket's Problem and acceptance criteria name transport failures ("a refused connection, a DNS failure or a timeout"), and those are all handled. This is an older parse on the rate-limit path, and the exit code is 1 either way.
   - **Fix:** read `retry_after` defensively and fall back to 1.0 on `ValueError`, `TypeError` or `AttributeError` (`JSONDecodeError` is a `ValueError`). Add a `MockTransport` test for each of the two bodies above.

### Nits

2. **Split messages, `discord.py:118-125`.** When a long message is split and a later piece fails, the whole message goes to the outbox and is recorded as undelivered, even though the earlier pieces were posted. A `ReadTimeout` after Discord has already taken the message behaves the same way. Nothing replays the outbox today, so the only cost is that someone may read a few lines twice. One sentence in the module docstring would cover it.
3. **Not asked for, but defensible:**
   - `InvalidURL` is caught as well.
   - The error messages quote only the exception type.
   - 4xx answers, such as a deleted webhook, now go to the outbox too.
   - Nothing parses `PostResult.reason`, so the new "; saved to outbox" suffix is safe.
4. **Non-Discord exceptions, `runner.py:134-137`.** An exception from `alert()` that isn't a Discord error, such as a failed outbox write, still escapes as a traceback once auto-pause has run. `test_auto_pause_runs_whatever_happens_to_the_alert` asserts that it does. The ticket only rules out a traceback "when Discord is down", so this is fine as it stands.

Correctly left out of scope: audit S6 (resume counting) and S8 (redaction).

## Security

**Scope.** I reviewed the ticket-03 diff above. The `security-review` skill computed its own diff of the feature branch against `main`, which is the wrong diff for this ticket, so I applied its method to the correct diff by hand. I looked hardest at the webhook URL (which is the credential), data exposure, and the files and paths written.

**No high-confidence or medium-confidence vulnerabilities.**

- **Improvement, `discord.py:166-168`.** httpx errors become `DiscordError("Discord could not be reached (<Type>)")`, raised `from None`. Neither the message nor a printed traceback can quote the webhook URL, even though an `InvalidURL` message, for example, can include it. `test_unreachable_webhook_saves_to_outbox_without_quoting_the_url` checks both `PostResult.reason` and the `discord.error` event payload. The developer reports that the test fails if `str(error)` is quoted.
- **No path traversal.** The outbox path comes from a fixed channel list, and `post` raises on unknown channels at `discord.py:97-98`.
- **The tests can't reach a real webhook.** They post only to a closed loopback port or a `MockTransport`, and `tests/conftest.py` points `JURA_GROWTH_ENV_FILE` at a missing file, so no real webhook can be read or hit.
- **Nit: unredacted outbox text.** When Discord is down, alert text now goes unredacted into `discord-outbox/*.jsonl`. It's the same content that would otherwise have been posted to Discord, so this adds no new kind of exposure. This is audit S8 (`config.redact(content)` at the top of `post()`), and no ticket in this feature covers it. Worth a follow-up ticket.

## UI

There are no UI files in the diff, so no web design review was needed.

## Evidence

Every command ran in the developer's worktree with `JURA_ROOT` set and with `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` on fresh temp folders. `JURA_GROWTH_DISCORD=off` was set except where a test removes it itself.

| Command | Result |
|---|---|
| `uv run pytest -o addopts=""` | 522 passed in 21.87s |
| `uv run pytest tests/test_discord_down.py` | 7 passed |
| The base tree (`git archive` of 01ce0e9 into the scratchpad) plus the new test file, run against the base package | 7 failed: `httpx.ConnectError` escapes, and `assert None == '3 failed runs in a row'` |
| `probe_429.py` (MockTransport) | the output under Spec 1 |
| `git status` in the worktree after the runs | clean |

The Standards and Spec reviewers ran in parallel, each in its own context. Their reports appear above under their own headings and were not reranked against each other.
