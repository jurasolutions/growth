# 04 — The numbers rule catches figures written as words

Status: ready-for-agent
Blocked by: -
Covers: foundation B3

## Problem

`FIGURE_RE` needs a digit (`brand_check.py:387-390`), and `WORD_FIGURE_RE` knows only dozens, hundreds, thousands, millions, billions, twice, double, triple, tenfold and half (`brand_check.py:391-393`). So "We have helped twelve businesses go live." and "Jura has served forty clients across Singapore." both pass. The numbers rule is the one the domain calls non-negotiable.

## What to change

Teach the numbers rule the cardinal number words, so a spelled-out figure is treated like a digit figure: it needs a source or an approved claim. The rule must stay usable for ordinary copy, so it applies to number words that count something, not to every use of "one".

The exact boundary is decided at the gate (see `crew-log.md`). Default unless the gate says otherwise: flag **two and above** (two to twenty, the tens, compounds like "forty-five", "a dozen", "a hundred") when they quantify a following noun; never flag "one" or "a" on their own.

## Acceptance criteria

- Both sentences above fail with a `[numbers]` issue.
- "Most first automations go live within weeks." and every phrase in `config/approved_claims.yaml` still pass.
- "Start with one process." passes.
- The example copy in `prompts/*.md` and the existing brand-check tests still pass, or any that now fail are listed in the PR body with the reason.
- `uv run pytest` passes.

## Pointers

- `audit/code-review-01-foundation.md` B3
- `jura_growth/brand_check.py:380-490`, `tests/test_brand_check.py`, `config/approved_claims.yaml`
