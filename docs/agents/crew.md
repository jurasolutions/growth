# Crew operating card

_Read by every crew persona before acting. Repo rules outrank crew defaults. Last verified: 2026-10-24._

## Commands

| Purpose | Command | Verified |
|---|---|---|
| Install dependencies | `uv sync` | verified 2026-10-24 (uv 0.12.21, Python 3.12 venv in `.venv/`) |
| Test, all | `uv run pytest` | verified 2026-10-24: 515 passed in 16s. `testpaths = ["tests"]` keeps `.claude/worktrees/` out |
| Test, one file | `uv run pytest tests/test_core.py` | verified 2026-10-24: 37 passed |
| Typecheck | none configured | unverified: no pyright or mypy config in the repo. `pyright --pythonpath .venv/bin/python jura_growth` reports 84 existing errors, so it is advisory only; don't add new errors in files you touch |
| Lint | none configured | unverified: no linter in `pyproject.toml` |
| Build | none | unverified: nothing is built or deployed; the package runs from `.venv/` |
| Run the app | `uv run jura-growth status` (any `jura-growth <command>`) | verified 2026-10-24: `jura-growth --help` lists every command group |

### Running inside a worktree

`jura_growth/paths.py` finds `jurasolutions/` as two folders above the repo, which is wrong inside
`.claude/worktrees/<name>/`. Before running tests or the CLI in a worktree:

```bash
export JURA_ROOT=/Users/tingy/OneDrive/Desktop/projects/jurasolutions
export JURA_GROWTH_DATA_DIR="$(mktemp -d)"      # never the live data/growth/growth.db
export JURA_GROWTH_OUTPUTS_DIR="$(mktemp -d)"
```

Tests already point data at a temp folder (`tests/conftest.py`); the CLI does not, so always set
the two data variables before running it by hand.

## Branches

- **Base branch for crew work:** `main`
- **Protected (crew never pushes or merges into these):** `main`
- **Ship path:** a GitHub PR from `crew/<feature>` into `main` on `github.com/jurasolutions/growth`, opened only after the user's G4 answer. Needs `gh auth login` on this Mac (not done as of 2026-10-24).

## Rules that gate the crew

- **PRD rule:** required. "PRD before build — explicit sign-off required before any code is written. PRD prompts must include: "Do not start building. This PRD requires explicit sign-off."" and "New PRDs are written to `prd/pending/` as `prd-{project-name}-YYYY-MM-DD.md`." (`jurasolutions/CLAUDE.md`). Sign-off is recorded in the PRD's Sign-off section; the PRD structure is Problem · Success Criteria · Scope (in/out) · Constraints · Proposed Plan · Open Questions · Sign-off. When the build ships and is accepted, the PRD moves to `prd/done/` with the ship date at the top.
- **Blocked paths (read-only):** `jurasolutions/inputs/`, `jurasolutions/design-system/` (including the generated `_ds_bundle.js`), `.env`, and the live `jurasolutions/data/growth/` (tests and worktree runs use temp folders). "`inputs/` and `design-system/` are read-only." (`repos/growth/CLAUDE.md`)
- **Design system:** `jurasolutions/design-system/`. Read `SKILL.md`, then `README.md`, then a component's `.prompt.md` before using it. It governs tokens, `styles.css`, components, brand assets and voice (§3). "Anything carrying the Jura name is built from the design system's tokens and components, never ad-hoc styles or a second icon/font set." (`jurasolutions/CLAUDE.md`)
- **Voice for human-facing text:** commits and PR bodies in plain sentence-case imperatives, matching the history (for example "Add the community scout and the daily app PRD factory"). Anything carrying the Jura name follows `design-system/README.md` §3: sentence case, second person, short declaratives, no buzzwords, no emoji, no exclamation marks, and the numbers rule.
- **Other repo rules:**
  - "Jura only. Never read `taskwise-*` or ZenexFlow folders. No Notion, no Zapier." (`repos/growth/CLAUDE.md`)
  - "Every side effect goes through `jura-growth`." (`repos/growth/CLAUDE.md`)
  - "The numbers rule. Never write a figure Jura can't evidence: no client counts, hours saved, ROI or results. Only the phrases in `config/approved_claims.yaml`." (`repos/growth/CLAUDE.md`)
  - Never run anything that sends email, posts to Discord, or calls Resend, Cloudflare or IMAP outside a test double. Never install, load or render launchd jobs (`jura-growth schedule install|render`) or run `jura-growth run`: those are the user's.
  - Hard limits live in `jura_growth/caps.py`; a config value may lower a limit, never raise it.

## Release

- **Versioning:** `version` in `pyproject.toml` (0.1.0). No release tags so far.
- **Changelog:** none yet. Release notes go in the PR body.
- **Deploy target and how:** none. The engine runs on Ting Yu's Mac from this checkout: after merge, `uv sync`, and `jura-growth schedule install` again if the job list or times changed.
- **Rollback:** revert the merge commit on `main`; `jura-growth pause <agent>` or `jura-growth schedule uninstall <job>` stops a job meanwhile. Migrations so far add tables, columns and indexes (`outreach/0002` replaces one index), and none drops data, but check a PR's migrations before assuming an older checkout runs against a newer `growth.db`.

## Tracker

Issues and feature folders: see `docs/agents/issue-tracker.md`. Domain glossary: `CONTEXT.md`. ADRs: `docs/adr/`.
