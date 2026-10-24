# 08 — Tests and build runs never write to the repo or live data

Status: ready-for-agent
Blocked by: -
Covers: infra A6, A7 and D6; foundation review "4 repo-writing tests"

## Problem

`tests/test_core.py:276-277` calls `schedule.render()`, which writes plists into the real `launchd/generated/` (`schedule.py:116`, no override). That's how the two plists there were made, and it contradicts `README.md:157`. Separately, a frozen-clock build run left social drafts dated 2026-10-26 in the live `growth.db`, which will make Monday's real social run skip.

## What to change

- Give `schedule.render()` an output-folder override (an environment variable in the same style as `JURA_GROWTH_DATA_DIR`), and point it at a temp folder in `tests/conftest.py`.
- Find the other tests that write into the repo or the real `jurasolutions/` folders, and point them at temp folders.
- Make `JURA_GROWTH_NOW` (the frozen clock) refuse to run against the live data folder, so a frozen-clock run must use a temp `JURA_GROWTH_DATA_DIR`.

Don't touch the live database. Removing the existing 2026-10-26 rows is Ting Yu's step.

## Acceptance criteria

- After `uv run pytest`, `git status` shows no change and nothing under `jurasolutions/data/` or `jurasolutions/outputs/` has changed (compare modification times before and after).
- `JURA_GROWTH_NOW=2026-10-26T07:00:00+08:00 jura-growth status` with no `JURA_GROWTH_DATA_DIR` exits with a clear refusal.
- `uv run pytest` passes.

## Pointers

- `audit/infra.md` A6, A7, D6, Risks; `audit/code-review-01-foundation.md` Evidence
- `jura_growth/schedule.py:112-121`, `jura_growth/timeutil.py`, `jura_growth/paths.py`, `tests/conftest.py`, `tests/test_core.py:270-280`
