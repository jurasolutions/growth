# Code review 09: the one-pager PNG, the 08:00 job and the setup guides (MC-09)

- **Branch:** `crew/mission-control-09-one-pager-png-job-and-guides` at `51949f2` (commits `ba023f0`, `2c115b9`, `2b295eb`, `0da6ca7`, `51949f2`). Reviewed against the fixed point `4cc477e` with `git diff 4cc477e...crew/mission-control-09-one-pager-png-job-and-guides`.
- **Changed files (17):** `.scratch/mission-control/setup/discord.md` (new), `.scratch/mission-control/setup/morning-brief.md` (new), `README.md`, `config/settings.yaml`, `docs/dispatch-contract.md`, `jura_growth/agents/social/render.py`, `cli.py`, `images.py`, `mission.py`, `one_pager.py`, `remote.py`, `tests/test_approval_lapses.py`, `tests/test_mission_setup_guides.py` (new), `tests/test_one_pager.py`, `tests/test_one_pager_grid.py` (new), `tests/test_one_pager_post.py` (new) and `tests/test_remote.py`. I read every one.
- **Spec:** `issues/09-one-pager-png-job-and-guides.md`. PRD SC1, SC14, §4.1, §4.2, §4.3, §4.6 A17, §5.4 and §5.10, plus the 2026-10-26 amendment. Test strategy v3: the MC-09 rows, X12, X14 and §11.2.
- **Date:** 2026-10-27

## Verdict: approve

There are no blocking findings.

- **No blocked path is touched.** The diff changes nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **Tests pass.** The full suite passes and the ticket's own tests pass with real headless Chrome.
- **It merges cleanly** into `crew/mission-control` at `fec69b8`.
- **Every acceptance criterion is met and tested at the level the strategy asks for.**

Five *should fix* items remain:

- grid PNGs that are never pruned (S-1)
- a `remote` table row that can't fail (S-2)
- a duplicated Chrome path (S-3)
- the README data layout (S-4)
- one exit-code line in the Dispatch contract (S-5)

None of them changes what Ting Yu sees on 10 Nov. They can be fixed on this branch before merge, or in a follow-up.

## Evidence

All commands ran in the developer worktree `.claude/worktrees/agent-a76eead1ab8f4fee8`. `JURA_ROOT` was set, and the data and outputs variables pointed at `mktemp -d` folders. The live `growth.db` was never opened, and nothing reached Discord except the test double.

| Command | Result |
|---|---|
| `uv run pytest -q -p no:cacheprovider` (full suite, run twice) | exit 0, 2,213 tests collected, no failures |
| `uv run pytest tests/test_one_pager_grid.py tests/test_one_pager_post.py tests/test_mission_setup_guides.py tests/test_social_render.py --basetemp=<scratchpad>` | 41 passed. Chrome is installed, so nothing was skipped |
| `git diff 4cc477e...branch -- tests/test_social_render.py` | empty, so the file is unchanged |
| `git merge-tree --write-tree crew/mission-control crew/mission-control-09-…` | clean (`11e0f19`), exit 0 |
| `git diff --name-only` checked against `inputs/`, `design-system/`, `.env` and `data/growth` | no hits |
| `git status --short` in the worktree after the runs | empty |
| PNG chunks of the real 08:00 grid (`grid-2026-11-10.png`, 74,166 bytes, 1200 wide) | `IDAT`, `IEND` and `IHDR` only |
| I viewed that rendered grid | one cell per job per day, with a word in each cell and a legend; scout-send collapses to "Miss 43" / "OK 7" |

## Standards

### Should fix

- **S-3 (reuse): the Chrome path is duplicated.**
  - **Where:** `jura_growth/images.py:22` adds `DEFAULT_CHROME = "/Applications/Google Chrome.app/…"`, the same literal as `jura_growth/agents/social/settings.py:19` `DEFAULT_CHROME`.
  - **Effect:** `one_pager.grid_png` (`one_pager.py:250`) uses the core constant and ignores `config/social.yaml:146 render.chrome`. If that setting is ever changed, the social cards and the grid run different Chromes, and only `JURA_GROWTH_CHROME` reaches both.
  - **Fix:** have `agents/social/settings.py` take its default from `images.DEFAULT_CHROME`, so the literal lives once. The agent can depend on the core; the reverse is the forbidden direction.
- **S-4: the README data layout is stale.**
  - **Rule:** `repos/growth/CLAUDE.md` says "`README.md` covers layout".
  - **Gap:** the `jurasolutions/data/growth/` tree at `README.md:39-47` has no `one-pager/` line, but the job now writes `data/growth/one-pager/grid-<day>.png` there (`one_pager.py:247`).
  - **Fix:** add the line with its retention (see S-1).

### Nit

- **Stale docstring.** `one_pager.py:5` still says "`messages()` is what goes to Discord". `post()` now sends `text()` through `discord.post`, which does its own masking and splitting, and `messages()` serves only `--no-post`.
- **Possible Middle Man.** The shims in `agents/social/render.py:54-55` and `:285-305` (`RenderError`, `design_system`, `chrome_path`, `png_size`, `_chrome`, `screenshot`) only delegate. The ticket wanted an expand and contract, but `test_social_render.py` has to pass unchanged and still calls them, so they stay for now. A later ticket can drop them.
- **Hidden test seam.** `one_pager.OFFLINE` (`one_pager.py:242`) is a mutable module global, and the tests monkeypatch it. `render_grid` already takes `chrome` and `offline`. Passing them through `grid_png` and `post` would remove the global, and the tests' patching of `images.DEFAULT_CHROME` with it.
- **Grid sizes kept twice.** The pixel sizes live in Python (`_PAD, _TITLE, …` at `one_pager.py:144`) and again in the CSS (`padding: 32px`, `height: 20px`, `56px` …). Changing one without the other fails the exact-size check at render time, which is loud but avoidable.
- **Font sizes and padding are raw pixels.** `12px`, `13px` and `32px` in `_GRID_CSS` equal `--text-overline`, `--text-caption` and `--space-6`. Colours, font families, weights and radii are all real tokens; the Standards reviewer checked all 25. This is a soft breach of the `jurasolutions/CLAUDE.md` rule "built from the design system's tokens"; the comment's reason ("a fixed-size image") doesn't stop the tokens being used.

## Spec

### Should fix

- **S-2: the AC-M10.1 row for `one-pager` can't fail.**
  - **Where:** `tests/test_remote.py:187` adds `(["one-pager"], 0, "posted to #mission-control")`, and the table checks `phrase in body["text"]`.
  - **Problem:** with Discord off (the row's own comment says so), the answer is "not posted to #mission-control: DISCORD_WEBHOOK_MISSION_CONTROL not set; saved to outbox", which contains the phrase. The row passes whether or not anything posted.
  - **Fix:** expect `"not posted to #mission-control"` there, which is what actually happens. AC-M1.6 itself is properly covered by exact `==` assertions in `tests/test_one_pager_post.py:137` and `:153`.
- **S-5: the exit code when Discord refuses doesn't match the contract.**
  - **Contract:** `docs/dispatch-contract.md:101-104` says "Exit 1 means the command ran and reported a problem of its own".
  - **What happens:** `one-pager` exits 0 with `ok: true` / `recorded` when the post went to the outbox (`cli.py:414-417`).
  - **Why it's defensible:** the developer chose this on purpose to match `heartbeat`. Exit 1 would mark the 08:00 run failed and raise an alert on top of the outbox item that Needs you already lists.
  - **Still to settle:** AC-M10.1 asks for "its own meaningful code", and Dispatch has to read the text to tell "posted" from "not posted". See the question in the report block. My recommendation is to keep exit 0 and say so in the contract row ("exit 0 either way; the text says whether it posted").

### Nit

- **Lapses written on every run.** The diff writes lapses and edits lapsed cards on every `jura-growth one-pager`, including `/growth one-pager` (`cli.py:411`). §4.2 names only "the `one-pager` job itself", so this goes beyond it. It is harmless (the writes follow the clock and repeat safely), and the README states it, so accept it on purpose.
- **The Discord guide runs ahead of Dispatch.** `.scratch/mission-control/setup/discord.md:72-73` says to answer a card with `/growth approve A-nnnn` in Discord. That only works once MC-11a and Dispatch D1 to D4 are live (PRD, the 2026-10-26 note before §6). A half-line, "once Dispatch is connected (`remote-control.md`)", would avoid a confused first try.

### Checked and holding

- **AC-M1.1:** one message with the sections in order and the PNG on the last piece. The split case at 2,100+ characters is tested with the PNG on the last piece only.
- **AC-M1.5:** `one-pager` is not in `NEVER`, `may_use("one-pager", "one-pager")` is true, and the job is placed directly after `digest` with agent `digest` at 08:00, as PRD §5.3 says.
- **AC-M1.6:** tested twice through the CLI and twice through `remote`, with exact answers. `-- one-pager --no-post` is refused with exit 2.
- **AC-M14.1:** the guide drafts are in place, and the digest still writes `daily-summary.json`.
- **X12:** `expire_due` runs on the writable connection and commits before `mission.read`. A failing expiry doesn't stop the post. No new card posts at 08:00.
- **X14:** checked on the HTML (tokens only, a word in every cell, unique labels, the legend, scout-send and publish collapsed) and on the real PNG's size.
- **Sweep (AC-M11.1, AC-M12.1):** runs over the real Chrome post, the split pieces and the outbox.
- **AC-M3.7:** no run update for the job.
- **Allowlist:** still sorted, and the contract row is present.

### Dismissed

- **§4.3 "Keychain masking isn't loaded before the build":** not so. `mission.read` calls `privacy.load_for_masking(conn)` unconditionally (`mission.py:155`) before it reads anything, and `post()` builds only from that snapshot.

## Security

There are no blocking findings. I ran this pass inline, following the `security-review` method on this diff.

- **The PNG can't carry a secret or a name.**
  - Every string in `grid_html` is escaped.
  - Job names come from `source.jobs` (`config/settings.yaml`), not from `runs.job` (`mission.py:252`).
  - The cell words, legend and `_unavailable` text are fixed, and the title is a date.
  - No database text, skip reason or summary reaches the pixels.
  - The bytes that leave go through `discord.attachment` → `images.pixels_only`, and only for files under the data or outputs folders. Chrome's own output already has only `IHDR`, `IDAT` and `IEND`.
- **Chrome is never pointed at a remote URL.** `images.run_chrome` takes an argv list (no shell), and both callers pass only the `file://` URI of a page they just wrote to a temp folder (`images.py:128`, `agents/social/render.py:311`). With `OFFLINE` off in production, the page does fetch the design system's Google Fonts (`design-system/tokens/fonts.css:5`). That is the social cards' existing pattern and sends nothing from the engine.
- **`OFFLINE` can't be left on in production.** It is the literal `False` (`one_pager.py:242`), and no environment variable, flag or setting changes it; only test monkeypatches do (`test_one_pager_post.py:51`, `test_remote.py:59`). The opposite risk is a nit: production never checks that the web fonts loaded (social has `fonts_loaded`), so an 08:00 run without network would draw in fallback fonts without saying so.
- **The job runs headless correctly.** It is `kind: command`, so `permissions()` gives it exactly `one-pager`. `NEVER` doesn't block it, and a Claude job can't call it unless its plug-in declares it. `remote` takes nothing after `one-pager` (`remote.py:71-77`).
- **Data exposure:** the text is masked by `discord.post` after `mission.read` has loaded the Keychain values.
- **Nit: the grid-failure note carries raw error text.** The note appends the raw exception text (Chrome's stderr tail, or a `Type: message` that can hold a local path) to the Discord message (`one_pager.py:266`). It is masked, and the channel is Ting Yu's own. A fixed phrase in Discord with the detail kept in the `one_pager.grid_failed` event would be tidier.
- **Company separation:** the only TaskWise or ZenexFlow mention is the morning-brief guide telling Ting Yu to leave those sections alone. No data crosses.

## Retention

### Should fix

- **S-1: the grid PNGs are never pruned.**
  - **Growth:** `data/growth/one-pager/grid-<day>.png` is written once a day and never pruned. That is about 74 KB a day in OneDrive (measured on the 10-Nov fortnight grid), roughly 27 MB a year, and it keeps growing.
  - **The repo's rule:** every growing file kind under `data/growth/` has a limit in the `retention` block of `config/settings.yaml:48-50` (`backups_days: 14`, `transcripts_days: 30`), and the 23:30 backup prunes them (`backup.py:28-50`).
  - **Recommendation:** add `retention.one_pager_days: 14`, matching the grid's own 14-day span and the backups. Prune `one-pager/grid-*.png` older than that in the same backup step, with a test next to the existing pruning tests, and note "(14 days)" on the README layout line (S-4).
  - **Why 14:** each PNG is a picture of data `growth.db` already holds, so keeping a copy past 14 days adds nothing; the backups already keep 14 days of the database.
