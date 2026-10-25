# 09 — Tidy the messages and duplicates the final review found

Status: ready-for-agent
Blocked by: 01-08 (merged)
Covers: code-review-final SP1, SP2, SP3, ST1, ST3

## What to change

- SP1: `community/__init__.py:404`, the #community summary, prints `community set ... rules_confirmed=yes`, which is now refused. Print the command that works now (with promo_days and post_days).
- SP2: `community set --help` (`:198`) must document promo_days and post_days.
- SP3: `runner.py:255-256`, the headless preamble, points agents to Discord and to `<group> --help`, which the per-job allowlist refuses. Make it name only what the job may run.
- ST1: `runner._lock_held` duplicates `locks.py`; use `locks.py`.
- ST3: the within-folder check is written three times; share one helper using `Path.is_relative_to`.

## Acceptance criteria

- A test asserts the #community summary's command passes `community set`'s own validation.
- A test asserts every command the preamble names is in that job's allowlist.
- `uv run pytest` passes.

## Pointers

- `reviews/code-review-final.md`
