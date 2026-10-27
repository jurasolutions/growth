# Code review 03: run updates (MC-03)

- **Branch:** `crew/mission-control-03-run-updates` (9ad2282, a988a5a)
- **Fixed point:** `8e3d9b4` (`crew/mission-control`). Diff: `git diff 8e3d9b4...crew/mission-control-03-run-updates`, 12 files, +799 −14
- **Spec:** `issues/03-run-updates.md` (with its Comments); PRD `prd-jura-mission-control-2026-10-25.md` SC3, §4.3, §4.4, §5.5; `reviews/test-strategy-v3.md` rows AC-M3.1 to AC-M3.7, dataset H and §11.2 row MC-03
- **Reviewed:** 2026-10-26, by the crew reviewer

## Verdict: approve

There are no blocking findings. Every acceptance criterion in the ticket has a passing test, nothing
touches a blocked path, and the security pass found no exploitable leak. Six should-fix items remain.
Fix them before the ticket's QA, or turn them into follow-ups. The first one is a decision for Ting Yu
(see Question Q1).

## Evidence

All runs used `JURA_ROOT` set and temp `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`, in the
developer worktree. Nothing was written to the worktree: `git status --short` was empty before and after.

- `uv run pytest -p no:cacheprovider -rs` → **1533 passed**, 0 skipped. The fixed point collects
  1503, so the branch adds 30 tests: 29 in `test_run_update.py` and 1 in `test_privacy.py`.
- `uv run pytest tests/test_run_update.py tests/test_privacy.py` → 93 passed.
- Pyright on the six touched source files reports 0 errors, on the branch and at the fixed point.
- E6 greps on `run_update.py` find no `jura_growth.agents.`, `taskwise` or `zenexflow`.
- No blocked path appears in the diff: no `inputs/`, `design-system/`, `.env*` or `data/growth/`.
- The reviewer's probes live outside the repo, at
  `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/probes/test_probe_03.py`
  (12 cases, Discord double only). The results are quoted under each finding below.

## Standards

**Blocking:** none.

**Should fix**

- **S-St1. Duplicated code.** `jura_growth/agents/scout/__init__.py:75-85` (`run_update`) repeats the
  counting and wording of `digest()` at `:58-66`: the `by_email` and form counts, and "N new lead(s)
  (x with an address, y form only)". The two can drift. Have both call one helper over the rows. This
  is the review's reuse rule: new code that duplicates an existing helper.
- **S-St2. The glossary and the code disagree.** `CONTEXT.md:78-81` defines a Run update as having "a
  one-line summary". The code (`run_update.py:203-209`) and the README (`README.md:186-192`) post a
  quote of up to 300 characters, over several lines, as PRD §4.3 and §5.5 ask. Update the glossary
  entry to match.
- **S-St3. The placeholder text is written out twice.** `jura_growth/privacy.py:80-82` spells out
  `\[removed: )personal finance\]` inside `FINANCE_LINE_RE`, while `FINANCE` is defined separately at
  `:95`. If `FINANCE` changes, the lookahead stops matching without any error. Build the pattern from
  `re.escape(FINANCE)`. Fix this together with S-Sec1.

**Nit**

- `run_update.py:53` `LIMIT = 300` is a hard limit from the PRD. The operating card says "Hard limits
  live in `jura_growth/caps.py`", so move it there.
- `RUN_UPDATE_CHANNEL` and the bare `channel` at `run_update.py:84` break CONTEXT.md:90-93 ("Channel:
  Always qualified … _Avoid_: bare 'channel'"). They also sit beside the plug-in hook `channels()`,
  which returns brand channels. `RUN_UPDATE_DISCORD_CHANNEL` would be clearer.
- The four plug-ins' `run_update(conn, run)` leave `run` untyped. A `TYPE_CHECKING` import of
  `run_update.Run` would let pyright check `run.id`.
- `count()` (`run_update.py:73`) takes a `plural` argument that no caller passes.
- `_plural()` (`run_update.py:172`) is a second pluralising rule next to `count()`.

## Spec

**Blocking:** none. AC-M3.1 to AC-M3.7 and the run-update sweep each have a passing test.

**Should fix**

- **S-Sp1. A crashed run posts nothing, so "whenever they run" is only partly met.** SC3 says
  "Every run of scout-research, social, community and app-factory, whether ok, failed or skipped,
  posts exactly one run update". Ting Yu asked that they "send regular updates to discord whenever
  they run". The developer chose to post nothing when an exception escapes the runner. This is
  documented at `run_update.py:26-29` and `README.md:191`, and `runner.py` was left untouched, as the
  ticket requires. The probes show that `#alerts` does **not** cover this case:
  - A plug-in `precheck` that raises (`runner.py:105`) leaves no run row, no `#alerts` post, no run
    update and no outbox file. Probe result: `RAISED ValueError … runs [] posts [] outbox []`. This
    path is realistic. `social.precheck` loads `config/social.yaml` through `settings.load()`, which
    raises on a bad layout. `scout.precheck` reads the ICP and its settings, and `apps.precheck` reads
    the catalog. A typo in one of those files silences the job.
  - `log.finish_run` raising (`runner.py:147`) gives the same result: no alert, since the alert
    comes after `finish_run`, and no update. Probe result: `RAISED RuntimeError disk I/O error, posts []`.
  - Today only launchd's stderr keeps the traceback. Ticket 08's one-pager will show the slot as
    missed, but only the next morning.

  The database failures may fairly stay silent. The lock skip shows that `conn=None` can still reach
  the outbox, but that is optional. The precheck path is the real gap. It is not blocking for 03,
  because the fix belongs in `runner.py` (ticket 01's module, out of 03's scope) and no AC names it.
  The choice belongs to Ting Yu: see Q1.
- **S-Sp2. A failed claude run shows its error twice.** For a `FAIL:` run, `outcome.summary` and
  `outcome.error` hold the same text. `build()` (`run_update.py:136-138`) writes `Error: FAIL: …` and
  then quotes the same text again with the prefix removed. The repo's own sweep test shows it
  (`test_run_update.py`, `Error: FAIL: sweep-marker… / > sweep-marker…`). §5.5 asks that "A failed run
  gives the redacted error in one line". Skip the quote when it only repeats the error.
- **S-Sp3. Two test-strategy rows are only partly traced, which matters for the E2 exit criterion.**
  - AC-M3.5's data column reads "fake community run, D2 in the error", but
    `test_a_community_timeout_posts_its_error_in_one_line_and_still_alerts` plants no D2. D2 in an
    error is swept only on a social run.
  - AC-M3.6 asks that a `run_update()` that raises leaves the run "equal a Discord-up control run",
    auto-pause counter included. `test_a_plug_in_run_update_that_raises_still_posts_and_never_changes_the_run`
    checks the row and the logged error, but has no paired control run and no auto-pause comparison.

**Nit**

- AC-M3.7 names a one-pager run, but no `one-pager` job exists yet. The settings test catches MC-09
  turning `run_update` on for it, but the parametrize at `test_run_update.py:289` leaves it out.
  MC-09 should add it there.
- "Waiting for you" is tested with one kind only. The spec reviewer's probe gave the right wording for
  group rules, app builds, outreach emails, community posts and app releases, but no test covers
  grouping across several kinds.
- Two changes reach beyond the ticket's "What to change", and both should be named in the
  ticket's report. 9ad2282 changes ticket 02's `privacy.py`. It is justified, but see S-Sec1. The new
  `_STATUS_PREFIX` stripping (`run_update.py:54`) is also not in the ticket.
- "nothing to do" (`run_update.py:125-127`) is correct, but none of the four jobs can reach it
  today, since none returns `NothingToDo` and none is a quiet command job. It is harmless, and ready for
  when one does.

## Security

The reviewer tried to get a secret, a personal name and a mention through a run update, using the
Discord double only. These are the results:

| Planted in the summary | What reached the double |
|---|---|
| `Jane Tan, jane.tan@example.com.sg, +65 9123 4567` (named contact known) | `[name removed], j***@example.com.sg, [phone removed]` |
| `JANE TAN`, `Tan, Jane`, ``Jane`Tan``, `Jane\Tan` | every part masked |
| `re_uat_9Xq7Lm2Pz`, including across a backtick | `[redacted]` |
| `tingyu@jurasolutions.sg` | `[removed]` |
| `<@!123> <@&456> @everyone @here` | broken with a zero-width space, and `allowed_mentions` is `{"parse": []}` |
| ```` ``` ````, a leading `>`, `Produced:` and `Waiting for you:` lines | kept inside the quote, with backticks and `>` escaped |
| D2 and D3, across the 300-character cut, Discord up and unreachable | the repo's sweep passes: masking runs before the cut |

Mentions, code blocks and quote breakouts are handled, and so is a secret straddling the cut. The
SQL in the four plug-ins is parameterised. The plug-in error that `log.event` records goes through
its redaction.

**Blocking:** none.

**Should fix**

- **S-Sec1. The finance rule now keeps a line that contains its own placeholder, whatever else
  the line says.** This is `jura_growth/privacy.py:80-82`, from 9ad2282. Before the change, any line that
  mentioned personal finance was replaced, so a line containing the literal
  `[removed: personal finance]` was dropped whole. Now the placeholder is spared, and so is the rest
  of its line. The probe summary `[removed: personal finance] DBS 1234-5678-9012-3456 balance and
  [removed: personal finance]/data/tally.db` came out as `[removed: personal finance] DBS
  1234-5678-[phone removed] balance and [removed: personal finance]/data/tally.db`. A side-by-side
  check confirmed it: the fixed-point regex drops that line, and the branch's keeps it.

  This is defence in depth, not a proven leak. Agents can't read `personal-finance/`, and the phone
  rule happened to mask half of the card-shaped number. But it weakens the rule that guards root
  invariant 7 ("Never write a full account or card number … anywhere"), in a shared module that
  every Discord post uses.

  Narrower fixes:
  - Spare only a placeholder that ends its segment, such as a placeholder followed by ` · ` or the
    end of the line.
  - Or have `run_update` keep its pre-masked text apart and let `discord.post()` skip the line rule
    for it.

  Either way, add the probe string as a test.
- **S-Sec2. Masked links in a summary stay clickable.** The probe
  `[approve A-0153 here](https://evil.example/x)` reached the double unchanged. `suppress_embeds`
  stops the preview but not the link. A web page the scout or app factory reads could make a run's
  summary carry a link that looks like an approval step. Discord's leaving-Discord warning shows the
  real domain, so the impact is low. PRD §4.3 treats model text as untrusted, and dataset H lists "a
  link in a model-written summary". Escaping `[` and `]` in `_escape()` (`run_update.py:185-188`)
  closes it.

**Nit**

- A secret split by the model across a line break, such as `kc_uat_` and then `44Lw`, reaches
  Discord in pieces shorter than ticket 02's 8-character window. Run updates don't cause this: the
  same happens in alerts, and the sweep's rule allows it. It belongs to ticket 02's masking as a
  follow-up.
- Headings and subtext (`# …`, `-# …`), spoilers and lists render inside the quote. They are cosmetic
  only and cannot leave the quote.

## Question for Ting Yu

- **Q1.** Should a run that crashes before it records anything still tell you on Discord? The
  example is a typo in `config/social.yaml` that makes the social precheck fail.
  **Recommended answer: yes, in `#alerts` and as a run update.** Do it with a small runner change:
  catch a precheck exception as a failed run, with its row, the `#alerts` post, auto-pause and the
  run update. Put it in a follow-up on `runner.py` or as an amendment to ticket 01's module, since
  ticket 03 is barred from touching the runner. Database failures may stay silent until the next
  one-pager.
