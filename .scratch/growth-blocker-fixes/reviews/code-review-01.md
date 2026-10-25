# Code review 01: headless runs can't read secrets or run human-only commands

- **Branch:** `crew/growth-blocker-fixes-01-headless-secrets` (7 commits, 77cb487..4a1d809)
- **Fixed point:** 01ce0e9 (merge-base with `main`); diff `git diff 01ce0e9...crew/growth-blocker-fixes-01-headless-secrets`
- **Spec:** `issues/01-headless-runs-keep-secrets-and-human-steps.md`
- **Reviewer run:** 2026-10-25, in the developer worktree with `JURA_ROOT` exported and temp data and outputs folders. Fake secrets only. No real `.env` was read, and nothing was posted or sent.

## Verdict: approve

There are no blocking findings. Every acceptance criterion is met and has a test. The three audit repros it targets now fail, which means the bugs they demonstrated are fixed. The Claude Code layer refused every bypass I tried against the real `claude` binary. The should-fix items below are hardening and tidy-up, and none of them opens a path for a headless run.

## Evidence

| Check | Result |
|---|---|
| `uv run pytest` (worktree, 4a1d809) | 563 passed |
| `uv run pytest` on the merge of this branch into `crew/growth-blocker-fixes` (347179f + 06), tree `d170925` extracted to scratch | 605 passed |
| `git merge-tree --write-tree crew/growth-blocker-fixes crew/growth-blocker-fixes-01-headless-secrets` | clean, no conflicts. Ticket 03's `runner.py` and `discord.py` changes merge without conflict. `test_every_command_a_prompt_uses_is_declared` still passes with ticket 06's `prompts/scout.md` |
| Audit repros `test_f9_check_file_echoes_secret_urls`, `test_image_path_can_be_any_file`, `test_headless_run_can_mark_groups_joined` against the branch | all three now fail at the point where the bug used to show. For example, `refused: a community run may not use jura-growth community set` |
| `pyright --pythonpath .venv/bin/python jura_growth` | 84 errors, the same as the baseline |
| `runner.claude_command` argv for app-factory, social, scout-research and community | each carries only its own commands (bare and `:*`), the group `--help` rules, a deny for every other leaf command, `NEVER`, and the four secret `Read` denies under `JURA_ROOT` |

### Attack probes, code layer (CliRunner with `JURA_GROWTH_JOB` set)

| Probe | Result |
|---|---|
| `check --file work/community/../../../secrets/.env` | refused (secrets file) |
| `..` to an ordinary file outside the run folders | refused (outside run folders) |
| A symlink inside `work/community/` pointing outside | refused (the guard checks the resolved path) |
| Subcommand abbreviation `community se`, option abbreviation `check --fi` | click rejects both (no prefix matching) |
| `community set --help` and `community --help` in a community run | help only, no callback runs |
| `discord post` in any run | refused (`NEVER`) |
| scout-research running `outreach send-due`, `requeue-shadow`, `unsubscribe-link`, `sync`, `suppress` | all refused, exit 2 |
| `JURA_GROWTH_JOB=scout-send` running `community set` | refused. The command job may run only `outreach send-due` |

### Attack probes, Claude Code layer

I ran Claude Code 2.1.310 in `dontAsk` mode with the runner's flag pattern, a fake `jura-growth` on PATH and canary files in scratch. Results:

| Probe | Result |
|---|---|
| `Read .ENV` (wrong case, on case-insensitive APFS) | denied |
| `Read .env` | denied |
| `Read .DEV.VARS` | denied |
| `jura-growth check - < .env` (input redirect) | denied |
| `JURA_GROWTH_OUTPUTS_DIR=/ jura-growth check hi` | denied |
| `JURA_GROWTH_JOB= jura-growth …` | denied |
| `env JURA_GROWTH_JOB= jura-growth …` | denied |
| `jura-growth check "$(cat .env)"` | denied |
| `check hi && community set …` | denied |
| `check-copy` | denied |
| Plain `jura-growth check hi` | ran, with `JURA_GROWTH_JOB` inherited |
| Ordinary files under the denied tree | still readable, so the `**/.env*` deny is not over-broad |

### Conductor's accepted deviation

Outside a run there is no `JURA_ROOT` limit. In-run behaviour is tight enough that this doesn't matter. With `JURA_GROWTH_JOB` set, `guard` accepts only `work/<job>/` and `outputs/growth/`, both inside `JURA_ROOT`, and it checks paths after resolving them. The run cannot clear or change the env variables that guard relies on, because the Claude layer refuses every env-prefixed command (see the table above).

## Standards

**Blocking:** none.

**Should fix**

- **S1. Duplicates `social.render.png_size`.** `jura_growth/agents/community/plan.py:638-652` (`PNG_SIGNATURE`, `image_problem`) repeats the PNG header check in `jura_growth/agents/social/render.py:293-299`. The audit fix for C-S2 named `render.png_size` as the thing to reuse. Importing across plug-ins is new, so the better move is to put one `png_size` or `is_png` helper in the core and call it from both. The rule broken is reuse: new code must not duplicate an existing helper.
- **S2. The secret-file patterns are defined three times.** They appear in `paths.is_secret_file` (`paths.py:75-78`), `headless.secret_read_rules` (`headless.py:99-108`) and the README. A new pattern means three edits (shotgun surgery). Derive the Read globs from one tuple of patterns kept next to `is_secret_file`.

**Nits**

- N1. `headless.py:84` and `:119` import `jura_growth.cli` inside functions, while `cli.py:412` calls `headless.install(cli)`. That is a circular dependency between the core and the CLI. Pass `cli` in, or keep the root group in `install`.
- N2. `cli.py:43` (`_Cli.main`) and `cli.py:54` (`main()`) both enter `config.redacted_output()`. The `isinstance` guard makes the second one harmless, but one of them is enough. Keep `main()` only if it is there to catch tracebacks raised outside click.
- N3. The `secret_values` docstring (`config.py:157`) leaves out `authorization`, which `_SECRET_KEYS` matches. The `headless.py` module docstring leaves out the `*.env` rule.
- N4. The four plug-in `permissions(job)` functions have no return annotation, unlike their sibling `precheck` functions.
- N5. `test_community_images.py` imports fixtures from `test_community`. Elsewhere, shared fixtures live in `test_scout_support`-style modules.

## Spec

**Blocking:** none. Every acceptance criterion is met and tested, as listed in Evidence.

**Should fix**

- **P1. `paths.is_secret_file` matches case-sensitively, but macOS APFS isn't case-sensitive.** `paths.py:78` and `:106`. Spec: the guard "refuses `.env*`, `.dev.vars`". The docstring says "Always refused: secret files". I reproduced it: with no job set, `check --file <dir>/.ENV` opens the real `.env` and runs the brand rules over it. Redaction masked the values, but the numbers rule still printed the digit run `12345` taken from `re_FAKEKEY12345`. Inside a run, the folder rule refuses the path anyway, so this affects only callers with no `JURA_GROWTH_JOB`: Terminal, and any interactive or crew agent session in this repo. Fix: compare `name.lower()`, and compare the configured env file with `os.path.samefile`, not `==`.
- **P2. Every CLI process now resolves every `keychain:` setting.** `config.py:157-190` and `:179`. This was not asked for. It runs on the first write to stdout or stderr, so even `--help` triggers it, and a community `check` pulls the outreach Resend key and the Cloudflare token out of the Keychain. Each lookup is a `security` subprocess with a 10-second timeout, and under launchd a Keychain prompt could stall the run. Spec item 4 only needs the values masked. Suggest resolving Keychain values lazily: mask only the references this process has already read through `config.secret()`, plus the `.env` values.

**Nits**

- N6. `paths.run_folders` (`paths.py:81-89`) allows all of `outputs/growth/`. Spec: "its `work/` folder and the output folders its images come from". That covers more than the image folders: digests, plans and `setup/`. It does no harm today, because `discord` is always refused, images must be PNGs, and the Read tool can already see these files. But a community `social render --out` can write anywhere under `outputs/growth/`. Narrow the list per job, or record the choice in the docstring.
- N7. `image_problem` now requires a PNG in Terminal too (`plan.py:641`), which is a small behaviour change for Ting Yu. The audit asked for it, and the renderer only produces PNGs, so it is fine. A note in the PR body is enough.
- N8. `scout insights` is in app-factory's `--allowedTools` (`apps/__init__.py:44-51`) but its prompt doesn't use it. The code layer needs it, because `apps context` calls it in-process through `CliRunner`. The Claude layer doesn't. It is read-only.
- N9. `MIN_SECRET_LENGTH = 8` (`config.py:151`): shorter values are never masked. That is reasonable, and the comment says so.

## Security

The skill's automatic diff covered the checked-out feature branch, not this ticket, so I applied its method by hand to the fixed-point diff, without sub-agents (the fan-out budget went on the two axes). Areas covered: the path guard, the allowlist, redaction, the runner argv, subprocess calls and plan-field file reads.

**High-confidence vulnerabilities (8 or above): none.**

Checked and clean:

- Every `click.Path` parameter in the core and the plug-ins is swapped for `GuardedPath` at `install` time. None uses `click.File`. Card specs (`render.CardSpec`) have no path fields, and social images come only from the renderer.
- Aliases cannot get around the allowlist. Enforcement wraps each leaf command's callback, keyed by its canonical name, and no group has `invoke_without_command` or a custom `get_command`.
- Subprocess output is captured (`_keychain`, Chrome, `launchctl`), so nothing writes around the redacting streams. There is no `logging` module use.

Defence-in-depth notes (low, each relying on something the Claude layer refuses, verified above):

- **D1.** In a run, `check -` still reads stdin unguarded (`cli.py:79`). A secret from another repo, for example a `.dev.vars` key, would print in full, because only configured values are masked. Reaching stdin needs `<`, which Claude Code refuses. You could refuse `-` when `JURA_GROWTH_JOB` is set, if no prompt uses a heredoc with it.
- **D2.** `guard` and `_enforced` trust `JURA_GROWTH_OUTPUTS_DIR`, `JURA_GROWTH_DATA_DIR`, `JURA_GROWTH_ENV_FILE` and `JURA_GROWTH_JOB`. An empty job string means Terminal, and `OUTPUTS_DIR=/` accepts any non-secret file. The run can't set these, because Claude Code refuses env prefixes and `env`.
- **D3.** `_excerpt` (`brand_check.py:196`) shows 30 characters of context, and the numbers rule quotes digit runs. Either can print part of a secret that redaction can't recognise. This only matters if secret text reaches `check`, which the guard now prevents.

## Blocked paths

None touched. The diff changes `README.md`, `jura_growth/`, `prompts/community.md` and `tests/` only. Nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`. My runs used temp folders and the scratchpad only.

## Merge note

Merging into `crew/growth-blocker-fixes` is clean, and the merged tree passes 605 tests. Ticket 03's outbox works through `discord.post` in code, not through a CLI command, so the `discord` entry in `NEVER` doesn't affect it.
