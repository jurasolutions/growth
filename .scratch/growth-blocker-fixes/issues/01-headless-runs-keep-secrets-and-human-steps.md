# 01 — Headless runs can't read secrets or run human-only commands

Status: ready-for-agent
Blocked by: -
Covers: foundation B1, scout B3 (command part) and B4, community C-S1 and C-S2

## Problem

A scheduled `claude -p` run is allowed `Bash(jura-growth:*)`. Through that it can:

- print `.env` with `jura-growth check --file .env` (the numbers and links rules quote the secret lines);
- upload any file to Discord with `jura-growth discord post --file`, or through a community plan item's `image_path`;
- run commands that belong to Ting Yu or to another job: `outreach send-due`, `requeue-shadow`, `unsubscribe-link`, `sync`; `community set`, `posted`, `removed`; `social skip`, `published`, `submit`.

A prompt injection on any fetched web page could chain these: print the secrets, then fetch an attacker URL that carries them.

## What to change

1. **One path guard** in `jura_growth/paths.py`, used by every CLI option or plan field that takes a file path (at least `check --file`, `check-copy`, `discord post --file`, community `plan-add` `image_path`; find any others). It refuses `.env*`, `.dev.vars` and anything outside `JURA_ROOT`. Inside a run (`JURA_GROWTH_JOB` set), it allows only the folders that job legitimately reads: its `work/` folder and the output folders its images come from. List them in the guard's docstring.
2. **A per-job command allowlist.** Each `claude` job may run only the `jura-growth` subcommands its prompt uses (`prompts/<job>.md` is the source). Enforce it twice: in the runner's `--allowedTools` and `--disallowedTools`, and in code, so a refused command exits non-zero when `JURA_GROWTH_JOB` names a job that isn't allowed it. The core must not import agents by name; let each plug-in declare its job's commands.
3. **Widen the Read deny** to every `.env*` and `.dev.vars` under `JURA_ROOT`, not just the growth `.env`.
4. **Redact configured secret values** (from `.env` and Keychain references) from anything the CLI prints.

## Acceptance criteria

- `jura-growth check --file <a fake .env>` is refused, and no configured secret value appears in any CLI output (turn `audit/repro/test_review_repro_secrets.py::test_f9_check_file_echoes_secret_urls` into a passing regression test).
- With `JURA_GROWTH_JOB=community`, `jura-growth community set <id> joined=yes` is refused (repro `test_headless_run_can_mark_groups_joined`).
- With `JURA_GROWTH_JOB=scout-research`, `outreach send-due`, `requeue-shadow`, `unsubscribe-link` and `sync` are refused.
- A plan item whose `image_path` points outside the allowed folders is rejected before anything is uploaded (repro `test_image_path_can_be_any_file`).
- The argv from `runner.claude_command` for every claude job carries the job's allowlist and the widened `.env*` deny; a test asserts it.
- Ting Yu's own use from Terminal (no `JURA_GROWTH_JOB`) is unchanged.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-01-foundation.md` B1; `audit/code-review-02-scout.md` B3, B4; `audit/code-review-03-social-community.md` C-S1, C-S2 and Security
- `jura_growth/runner.py:218-256`, `jura_growth/cli.py:51-83, 201-209`, `jura_growth/agents/community/plan.py:388-389, 644`
