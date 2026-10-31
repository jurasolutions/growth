# 07: Defect: a missing config folder silently drops the buzzword check

Status: ready-for-agent
Severity: minor (shipped runs always have the folder, and the numbers rule still holds without it)
Owner: developer
Found by: ticket 04's developer (crew log, "open for the final review"); confirmed by QA at f0db1e5, `reviews/qa-final.md`
Failing test: `.scratch/approvals-first-social-depth/issues/test_qa_final_defects.py`, the test under "07"

## Steps

```bash
export JURA_GROWTH_DISCORD=off JURA_GROWTH_DATA_DIR="$(mktemp -d)" JURA_GROWTH_OUTPUTS_DIR="$(mktemp -d)"
JURA_GROWTH_CONFIG_DIR=/tmp/not-there uv run jura-growth check --channel social-card "Leverage the model"
uv run jura-growth check --channel social-card "Leverage the model"
```

## Expected

The first command fails, or stops and says the word list is missing. "No list" must not read as "no buzzwords" at a brand gate.

## Actual

The first command prints `pass`. The second, with the shipped config, prints `fail` with `[buzzword] Buzzword "leverage"`.

## How far it reaches

- `config.read_lines("buzzwords.txt")` returns nothing for a missing file, so `_buzzwords` finds nothing.
- The numbers rule still holds: with the folder missing, "Jura saved 62% of its clients 40 hours a week." still fails.
- `jura-growth check` and `social render` take the hole. `social submit` didn't reach the gate in my run: with no `social.yaml` its defaults still want `linkedin.md`, so it refuses first.
- Live runs use the repo's `config/`, which always has the file. So this needs a wrong `JURA_GROWTH_CONFIG_DIR`, as in a UAT window. That is why `uat.md` Part P runs `fresh base` first.
- It predates this branch: `main` reads the list the same way.
- `_buzzword_patterns` is cached for the life of the process, so the failing test clears that cache first. Without the clear, a test in the same process reads an earlier list and goes green for the wrong reason.
