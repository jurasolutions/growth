# Code review 01: apps idea command

- **Branch:** `crew/apps-idea-command` at 8b34f3c, compared with `main` at its merge-base 1206360 (PR #17).
- **Spec:** ticket `issues/01-apps-idea-command.md` and `prd/pending/prd-jura-app-factory-2026-10-24.md` §5.6, as amended on 2026-10-31.
- **Reviewer:** crew reviewer, round 1, 2026-10-31.

## Verdict: changes-requested

One finding blocks: `submit-prd --idea` isn't limited to Ting Yu's ideas, so a scheduled factory run can rename any open backlog row. The fix is small. Four are *should fix*: unlocked backlog writes, the missing tests for YAML and mentions, `clash` copying `backlog.find`, and a prompt gap that leaves an idea that can't be filed unheld. The rest are nits.

## Evidence

- Full suite in the worktree (worktree exports, temp data and outputs): `uv run pytest -q -p no:cacheprovider -o addopts=""` gave **4023 passed** in 259s.
- `uv run pytest tests/test_apps_idea.py tests/test_remote.py` gave **221 passed**.
- `uvx pyflakes jura_growth/agents/apps/ideas.py` reported `15:1: 're' imported but unused`.
- Reviewer probes, run on a copy of `tests/` in the scratchpad (`review01/tests_copy/test_review_probe.py`, 6 passed). The branch itself is untouched.
  - `submit-prd --idea invoice-builder` with the Delivery order maker PRD exits 0, and the `invoice-builder` seed row disappears from the backlog (see B1).
  - The reply to `Ping tool: @everyone and <@123> and <@&456> @here` comes back with every mention defused.
  - Two ideas that start with a URL are both named "Https", so the second is refused as a duplicate (N4).
  - `hold-idea --reason` accepts a 5,000-character reason (N3).
- YAML probe (`review01/yaml_probe.py`): text with anchors, `!!python` tags, `---` documents, `key: value`, `#` and U+2028 round-trips through `backlog.save`/`load`, and each row's status and source are unchanged.
- Race probe (`review01/race_probe.sh`): 12 to 20 parallel `jura-growth apps idea` calls, each of which replied "Added", left only 6 to 8 rows in the backlog (S1).
- Blocked paths: the diff touches none of `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- UI files: none, so no web design review.
- `code-review` pass (forked) returned 9 findings. All are folded in below: B1 and its two related gaps, S1, S3, S4, N7, N8 and N9. It couldn't run the tests from its own worktree, so it read the code only.
- `security-review` pass, with a sub-agent scan: no finding reached confidence 8 or more (see Security).

## Standards

### Blocking

- **B1. `--idea` can rename any open backlog row, not only Ting Yu's.**
  - **Where:** `jura_growth/agents/apps/ideas.py:386-391` (`link_problem`) and `jura_growth/agents/apps/backlog.py:83-84` (`mark_written`).
  - **The problem:** `link_problem` checks only that the row is an open idea. `mark_written` then takes that row and overwrites its name, slug, tier, category and status with the PRD's.
  - **Reproduced:** `apps submit-prd --idea invoice-builder <Delivery order maker PRD>` files APP-003 and turns the seed row "Invoice builder" into "Delivery order maker". The Invoice builder idea is gone from the backlog, and its `does` text now sits under the wrong name. The backlog lives in `data/growth/`, outside git, so nothing restores it.
  - **Why it blocks:** this is a new write that the scheduled factory run gets through its existing `apps submit-prd` permission, and the factory's context includes scout content taken from the web.
  - **What it breaks:**
    - PRD §5.6, "Renaming… It files the PRD with `--idea <slug>`, so Ting Yu's row is the one marked".
    - The branch's own docs: `docs/app-factory.md` says "for one of Ting Yu's ideas", and `backlog.py` says "an idea of Ting Yu's, renamed".
  - **The gap in the tests:** `test_submit_prd_refuses_an_idea_slug_that_isnt_an_open_backlog_idea` uses `quote-builder`, which is already prd-pending, so it never tests an open seed idea.
  - **Fix:**
    - Refuse unless `row.get("source") == SOURCE` and `is_open(row)`. Ideally also require that the row is the head of `queue()`, which the prompt already says.
    - Add a test with `--idea invoice-builder`.
  - **Two related gaps the same fix should close** (both found by the `code-review` pass):
    - **The link depends on the model.** Marking Ting Yu's row depends on the model remembering `--idea`. If the factory renames his idea and leaves out the flag, `mark_written` adds a new row (`backlog.py:198-203`). His row stays open and comes first again the next day.
    - **Two rows can share one slug.** When `--idea` picks his row, another row whose slug equals the PRD's new slug is left as an `idea` with that same slug. `effective()` then shows both as prd-pending, and `drop`/`rest`, which look rows up by `app_id`, reach only one of them.
  - **Sturdier fix:** have `factory.submit` bind the PRD to the head of `ideas.queue()` itself whenever the queue is non-empty, or record which idea `apps context` offered. Then the link doesn't rest on a prompt flag.

### Should fix

- **S1. Backlog writes can be lost or torn, now that a second writer can run at any time.**
  - **Where:** `jura_growth/agents/apps/backlog.py:58-62` (`save` uses `write_text` straight onto the file), `ideas.py:341-347` (`add`) and `ideas.py:367-379` (`hold`). Each one loads the file, changes it and saves it, with no lock.
  - **Why it matters now:** `apps idea` arrives from Discord whenever Ting Yu sends it. It can overlap the 06:30 factory (`mark_written`, `hold-idea`) and approval decisions (`drop`, `rest`, `release`).
  - **What happens:**
    - The last writer wins, and the other call has already replied "Added".
    - A read during a write sees a truncated file. Either the next load fails, or the next save writes a short list over the backlog.
  - **Reproduced:** 12 parallel calls kept 6 rows, and 20 parallel calls kept 6 to 8.
  - **Origin:** the unlocked `save` was already on `main`. This branch adds the writer that can actually trigger it.
  - **Fix:**
    - Write to a temp file in the same folder, then `os.replace`.
    - Wrap each load, change and save in the existing `jura_growth/locks.py`. That needs a waiting variant, since `held` doesn't wait.
  - **Not fixable here:** comments that Ting Yu adds by hand are still lost on every save, because only `HEADER` is written back. That was already true on `main`; it is worth a line in the header.
- **S2. Acceptance criterion 3 has no test for YAML or mentions.**
  - **Where:** `tests/test_apps_idea.py`. The ticket's criterion reads "The text can't inject YAML, Discord mentions or extra arguments".
  - **What exists:** tests cover only option-like words (`test_options_are_refused_and_nothing_is_written`).
  - **What is missing:** no test sends anchors, tags or `---`, and none sends `@everyone` or `<@…>` through `apps idea`.
  - **Effect:** the behaviour is safe (see the probes above), but nothing pins it down.
  - **Fix:** add two cases that assert the row round-trips with `source: ting-yu` and `status: idea`, and that the reply has no live mention.
- **S3. `ideas.clash` re-implements `backlog.find`.**
  - **Where:** `ideas.py:315-318` repeats `backlog.find` (`backlog.py:68-75`) line for line: the same slug-or-`slugify(name)` test and the same `normalise_name` test.
  - **Fix:** call `backlog.find(backlog.load(), slug=slug, name=name)`. The rest of `clash` already reuses `catalog.taken`, which is right, and it is no weaker than the checks `validate_factory` runs.

- **S4. An idea that passes the content checks but can't be filed is never held.**
  - **Where:** `prompts/app-factory.md:57-62`.
  - **The problem:** the prompt holds an idea only when it "fails a check" from the content list. Suppose the PRD then fails at `submit-prd`: the brand check fails twice (`app-factory.md:173-174`), or the gate finds a duplicate. The idea is then not held, and it stays first in `ting_yu_ideas`.
  - **Effect:** an idea that keeps failing the brand check is picked first every day and uses up the day's attempt. The rest of the backlog waits, and the reason never reaches the row's notes or the digest.
  - **What it breaks:** the ticket says "When one fails, the factory records why in the row's notes", and PRD §5.6 says "When one of these ideas fails a check… records the reason in the row's notes (`apps hold-idea`)".
  - **Fix:** tell the factory to hold the idea after a final `submit-prd` refusal too, with the gate's reason. Add a prompt-contract test for it.

### Nit

- **N1.** `ideas.py:15`: `import re` is unused (pyflakes).
- **N2.** `ideas.py:366`: an empty `--reason` exits 1. The `Refused` docstring (`ideas.py:280`) says 2 is "for the text itself", so it should be 2.
- **N3.** `ideas.py:364`: `held_reason` has no length cap. A run's reason goes word for word into the backlog notes and the digest line (`apps/__init__.py:100`). A 5,000-character reason is accepted. Cap it at about 200 characters, as other one-line reasons in the repo are.
- **N4.** `ideas.py:296`: the name is taken from the text before the first `:` anywhere in the text.
  - "https://www.iras.gov.sg/... a GST checker" is named "Https".
  - "Remind staff at 9:30 to submit timesheets" is named "Remind staff at 9".
  - A second idea that starts with a URL is then refused as a clash with "Https".
  - Fix: split only on `": "` (colon then space), or only when the colon comes in the first few words.
- **N7.** `ideas.py:298-301`: `NAME_MAX` caps only the name taken from before a colon. The first-five-words fallback has no cap, so one 300-character word gives a 300-character name with a 60-character slug (checked by hand). Cap the name after the fallback as well.
- **N8.** `ideas.py:333-336`: an idea written only in Chinese or another script without Latin letters slugifies to an empty string. It is refused with "the idea needs some words to name it". Say instead that it needs a name in English letters before a colon.
- **N9.** `ideas.py:337-346`: `add` reads the backlog three times: in `clash`, inside `catalog.taken`, and again before it appends. Load the rows once and pass them to `clash`, which also narrows the window in S1.
- **N5.** `ideas.py:361-379`: a hold can't be undone. Once held, the idea never comes first again, and sending it again is refused as a duplicate of its own row. The only way back is to edit the YAML by hand. Ting Yu might want `apps idea` to refresh a held row of his, or a remote `apps unhold`. That is a question for later, not for this ticket.
- **N6.** `ideas.py:361`: `hold` accepts any open idea of Ting Yu's, while the prompt says to hold only the first. Checking `queue()[0]` would enforce it in code. The impact is low: a hold only demotes the idea.

## Spec

The ticket's acceptance criteria, against the branch:

| Criterion | Result |
|---|---|
| Writes one `idea` row with `source: ting-yu` and replies with the next-run line | Met when calls don't overlap; see S1 for overlapping calls |
| Empty, over-500 and near-duplicate text refused, backlog unchanged | Met: exits 2, 2 and 1, each with a plain reason. Tested |
| Can't inject YAML, mentions or extra arguments | Behaviour met (probed). Tests cover only arguments (S2) |
| Allowlist and contract agree; parity test passes | Met. `ALLOWLIST` order matches the contract table, and the parity test in `tests/test_remote.py` passes |
| Prompt states the priority, the unchanged checks and the failure reporting | Met. `prompts/app-factory.md` §1 keeps the checks for an official source, near-duplicates and excluded kinds, and the `prds_per_day` limit. A failing idea is held with its reason, and the OK or SKIP line names it. No existing check was removed or loosened |
| Full suite passes | Met: 4023 passed |
| Dispatch passes the free text through | Met. `docs/dispatch-contract.md:31-44` shows Dispatch quoting each word with `shlex.join` and `bin/growth-remote` splitting with `shlex.split`, so apostrophes survive. Newlines and repeated spaces collapse to single spaces, so "verbatim" means word for word |

The three additions beyond the ticket:

- **`apps hold-idea`: needed.** The factory may cause side effects only through `jura-growth` (repo `CLAUDE.md`), so it can't write the reason into the row's notes any other way. It is safe in what it can do: it only demotes an idea and never deletes one. N3 and N6 apply.
- **`submit-prd --idea`: needed.** Without it, a renamed PRD adds a new row and leaves Ting Yu's row open and first in line every day. It is **not safe as built** (B1).
- **`"apps idea"` in `headless.NEVER`: needed and correct.** It is defence in depth on top of `permissions()` and the job check in `remote`. `never()` matches word by word, so `apps hold-idea` stays allowed, and that is tested.

All three are written into the PRD §5.6 amendment of 2026-10-31.

Reply wording (`ideas.py:394-409`) follows the voice for internal text and states no figures.

- **Nit:** "the app factory writes one PRD a day" and "picks it at its next run" read as promises. On a given day the factory may write nothing: the waiting pile can be at its limit, the job can be paused, the brand gate can drop the PRD, or the idea can be held. "At most one PRD a day" and "picks it first at its next run" would be exact. The ticket asks for the next-run line, so this stays a nit.

## Security

Against the change's threat model, no finding from the security pass reaches high confidence (the full pass is in the reviewer's run).

What was checked, and why each holds:

- **Options and argument splitting:** `remote._idea` (`remote.py:440-449`) passes the text as one value after `--`, with option-like words refused as well, and no shell sees the words.
- **Fields the sender controls:** `source` and `status` are hard-coded in `ideas.add`. The actor comes from the attributed `--actor`, not from the text.
- **YAML:** written with `safe_dump` and read with `safe_load`, and the probe round-trips.
- **Mentions:** defused in the reply by `remote._defuse`. The digest posts with `allowed_mentions: {"parse": []}`.
- **Slug:** limited to `[a-z0-9-]`, used only to look rows up, and never part of a path.
- **`apps idea` from a scheduled run:** unreachable. It isn't in `permissions()`, it is in `NEVER`, Claude Code deny rules cover it, and `remote` refuses whenever `JURA_GROWTH_JOB` is set.
- **Forged rows:** the factory can't write `app-backlog.yaml` directly (Write is limited to its work folder), so it can't forge a `source: ting-yu` row.
- **Personal data:** a PRD built from his text still goes through `private_problems` before it reaches #approvals.

Two items are integrity problems rather than exploits, and both are listed above:

- B1, the unscoped `--idea`.
- S1, the unlocked backlog writes.

---

## Re-review 6b69230

- **Compared:** the round-2 commit 6b69230 against 8b34f3c, and the whole branch against its merge-base 1206360.
- **Checked against:** PRD §5.6, the "Amended 2026-10-31" bullet under step 1, as it is now written.
- **Reviewer:** crew reviewer, round 2, 2026-10-31.

### Verdict: approve

B1 is fixed and S1 to S4 are fixed. The nits are fixed, apart from N5, which was deferred by decision. The new rules hold, and nothing permanently stops the factory from filing.

Two new *should fix* findings remain, R1 and R2, and neither blocks. They share a root cause: a PRD is filed but the backlog row isn't marked, and the next day the factory is refused because of an idea it can't see. The way out is a hold that the refusal names, and I checked that this hold works. No data is lost.

### Evidence

- **Full suite** (worktree exports, temp data and outputs): `uv run pytest -q -p no:cacheprovider -o addopts=""` gave **4056 passed** in 367s. `git status` was clean afterwards, and the temp data folder was empty.
- **`tests/test_apps_idea.py`, `tests/test_remote.py` and `tests/test_uat_seed_outreach.py`:** 304 passed.
- **pyflakes** on `ideas.py`, `backlog.py`, `locks.py` and `factory.py`: clean.
- **Race probe** (`review01/race_probe.sh`), rerun:
  - 12 parallel calls kept 12 of 12 rows.
  - 20 parallel calls kept 20 of 20.
  - 30 parallel calls kept 30 of 30.
  - Round 1 kept 6 to 8.
- **Mixed race** (`review01r2/mixed_race.sh`): 12 `apps idea` calls ran in parallel with 6 `backlog.drop` calls. All 12 rows were kept and all 6 drops landed.
- **Probes** (`review01r2/tests_copy/test_review_probe_r2.py`), 8 passed:
  - **B1:** `submit-prd --idea invoice-builder`, with and without `--dry-run`, exits 1 with "isn't an open idea of Ting Yu's", and the backlog is unchanged. With no idea of Ting Yu's waiting, a normal PRD still files.
  - **Limit refusal:** once today's PRD is filed, a second `submit-prd --idea petty-cash-log` gets "refused: app PRD already written today" before `binding` runs. It has no `idea:` line, the backlog is unchanged and nothing is held.
  - **An idea held yesterday:** it doesn't block today. The next idea of Ting Yu's is bound and marked.
  - **Empty `--reason`:** `--reason ""` exits 2, and leaving `--reason` out also exits 2 (click).
  - **R1, reproduced:** see below.
  - **Lock timeout through `remote`:** it answers in the contract shape, `{"ok": false, "answer": "refused", "exit_code": 1, "text": "failed: TimeoutError: the app-backlog lock is still held after 30 seconds"}`.
  - **Comments:** a hand-added comment is gone after the next `apps idea`. `main` also wrote `HEADER + body` (`git show 1206360:jura_growth/agents/apps/backlog.py:55`), so comments were lost before this change as well. The new header line is accurate.
- **Lock timeout, with real processes** (`review01r2/lock_timeout.sh`):
  - One process held `locks/app-backlog.lock`, and `jura-growth apps idea` exited 1 after 30s with a `TimeoutError` traceback. No row was written.
  - The lock file is `$JURA_GROWTH_DATA_DIR/locks/app-backlog.lock`.
- **`code-review` pass** (forked, read only) returned 10 findings, folded in below. One was not confirmed: an implicit binding giving two rows one slug. `validate_factory` requires the slug to be `slugify(name)` (`prd.py:340`), and `apps idea` refuses any clash when it adds the row, so a PRD that matches the head by name or slug can't take another row's slug.
- **`security-review` pass** (sub-agent scan): nothing at confidence 8 or above.
- **Blocked paths:** none touched. **UI files:** none.

### Round-1 findings, rechecked

| Finding | Status | Where |
|---|---|---|
| B1 | Fixed. `--idea` works only for Ting Yu's oldest open row, and is refused when the renamed row would share a name or slug with another row. Without `--idea`, while that idea waits unheld, any other PRD is refused. A PRD with the idea's own name is bound to it. The link no longer depends on the flag | `ideas.py:156-188`, `factory.py:117-119` |
| S1 | Fixed. Every writer goes through `backlog.locked()`, and `save` uses `mkstemp`, `fsync` and `os.replace` | `backlog.py:67-89` |
| S2 | Fixed. `HOSTILE` YAML cases, newlines and the mention reply are tested | `tests/test_apps_idea.py:219-262` |
| S3 | Fixed. `clash` calls `backlog.find` on rows read once under the lock | `ideas.py:77-90` |
| S4 | Fixed. Prompt §4 step 5 holds an idea whose PRD still can't be filed, and not for a limit refusal. Tested | `prompts/app-factory.md:176-182` |
| N1, N2, N3, N4, N6, N7, N8, N9, and the reply nit | Fixed | |
| N5 (no undo for a hold) | Deferred by the conductor's decision. Now documented in `docs/app-factory.md` | |

### Every backlog writer goes through the lock

- **In `backlog.py`:** `mark_written`, `drop`, `rest`, `release` and `seed_if_missing`. `seed_if_missing` has no caller in the codebase.
- **In `ideas.py`:** `add` and `hold`.
- **Their callers:**
  - `factory.submit`
  - `builds.py:334-337` (skip and expiry)
  - `releases.py:379`
  - the `apps idea` and `hold-idea` commands
- **Nothing writes the file another way:** no other code writes `app-backlog.yaml` (searched `jura_growth/`, `bin/` and the landing-page repo).
- **No job or UAT seed reaches it directly:** the UAT seed writes only inside its temp folder.

### Lock and temp files stay out of the repo

- The lock file is under `paths.data_dir()/locks/`: the live `jurasolutions/data/growth/locks/`, a temp folder in tests. Neither is in a git checkout.
- The temp file sits beside the backlog in the data folder and is removed on any exception.
- `git status` was clean after the full suite.

### Standards

#### Blocking

None.

#### Should fix

- **R1. `binding` and `hold` judge "oldest open idea" from the raw file, while the factory's list comes from the effective status.**
  - **Where:** `ideas.py:163` (`binding`) and `ideas.py:205-213` (`hold`) run `queue()` on `backlog.load()`. `apps context` builds `ting_yu_ideas` from `backlog.effective(...)` (`apps/__init__.py:157,170`), where a PRD file or a live registry entry with the row's slug wins.
  - **When the two disagree:** a row of Ting Yu's still says `idea` in the file, but its PRD is already filed or the tool is live. That happens when `mark_written` fails after the file is written (R2), or when he lists the tool in the registry by hand.
  - **Reproduced:**
    - After a filed PRD whose `mark_written` raised, context lists `ting_yu_ideas: []`, but `binding`'s head is `delivery-order-maker`.
    - The next day, every other PRD is rejected with "Ting Yu's idea delivery-order-maker comes first…".
    - Filing with `--idea` would fail as a duplicate of the pending PRD.
    - The only way out is `hold-idea delivery-order-maker`, which works (exit 0) and clears the block for good.
  - **Why the factory may not find that way out:** the prompt says "Hold only the first idea in the list", and this idea isn't in the list. So the factory may finish `FAIL` instead, and do the same again the next day.
  - **What it breaks:** PRD §5.6, "picks Ting Yu's open ideas … oldest first". Code and prompt disagree on which idea is first.
  - **Fix:**
    - Have `binding` and `hold` use the same view as context: `ideas.queue(backlog.effective(rows, prd_files=catalog.prd_files(), live=...))`, then match the raw row by slug for the write.
    - Add a test with a pending PRD file whose slug matches the row.
- **R2. A lock timeout in `mark_written` crashes `submit-prd` after the PRD is filed.**
  - **Where:** `factory.py:162`.
  - **The problem:**
    - `mark_written` can now raise `TimeoutError` (`locks.py:59`).
    - It runs after the PRD file is written and the `app_prds` row and approval request are committed.
    - Nothing catches it. `builds.py:331-341` and `releases.py:378-384` wrap the same kind of call with "say what is left to do".
  - **What the factory sees:** a traceback instead of "filed". A retry is refused as "already exists". The backlog is left unmarked, which leads to R1.
  - **Fix:**
    - Catch the exception, as `releases.py` does: log `apps.backlog.mark_failed` and add a line telling Ting Yu to mark the row by hand.
    - Fixing R1 makes the next day's run correct either way.

#### Nit

- **R3.** `apps/__init__.py:258,274`: from the terminal, `apps idea` and `hold-idea` show a Python traceback after the 30-second wait. Through `remote` the answer is already clean ("failed: TimeoutError: …", inside Dispatch's 60-second limit), so this affects only local use. Catching `TimeoutError` with a plain "the backlog is busy; try again" would match `Refused`.
- **R4.** `prompts/app-factory.md:173-174`: step 3 says to finish with `FAIL` after a second brand failure, and only step 5 then says to hold the idea first. Put "hold it (step 5), then" into step 3, so an agent that stops at step 3 still holds.
- **R5.** `ideas.py:177`: on the day an idea is held, `binding` lets any PRD through, even while his next idea now waits unheld. This matches the prompt ("the next one waits for tomorrow's run"). It doesn't match the PRD's literal "While that idea waits unheld, no other PRD is filed".
  - Either reword the PRD to "one of his ideas per day", or keep binding a PRD that matches the new head's name on that day.
  - As it stands, a renamed PRD for the next idea filed without `--idea` adds a new row and leaves his row open.
- **R6.** `backlog.py:72`: `mkstemp` makes the file 0600, so after the first save the backlog is 0600 instead of 0644. Every reader runs as `tingy` (`docs/dispatch-contract.md:19`), so nothing breaks. It is a silent mode change worth either a comment or an `os.chmod` to the old mode.
- **R7.** `ideas.py:218` builds the notes line by hand. It copies `backlog._note(row, note)`.
- **R8.** `ideas.py:163,177`: `binding` reads the backlog twice, once in its own load and again in `held_on`. And `head is not None` at line 170 is always true there, since an open row is always in the queue. Pass `rows` to `held_on`.
- **R9.** A `SIGKILL` between `mkstemp` and `os.replace` leaves a `.app-backlog.*.tmp` file in the data folder. It is harmless and untracked.

### Spec

How the code matches the PRD §5.6 amendment:

| Amendment line | Code |
|---|---|
| Name before a first ": ", at most 60 characters, Latin letters | Matches: `NAME_MARK`, `NAME_MAX`, and the refusal for no Latin letters |
| Refusals: empty, over 500, options, a clash that the reply names | Matches |
| Hold when the PRD still can't be filed, but not on a limit refusal | Matches. The limit is checked before `binding` (`factory.py:107-112`), so a limit refusal can't lead to a hold. The prompt says the same |
| Hold reason at most 300 characters; only the oldest can be held | Matches (`REASON_MAX`, `ideas.py:213-215`) |
| `--idea` accepted only for his oldest open idea | Matches, with R1 for which idea counts as oldest |
| "While that idea waits unheld, no other PRD is filed" | Matches for the oldest idea. R5 covers the day of a hold |

Looking for a deadlock in the factory's own flow:

- A head that fails a content check is held in §1.
- A head whose PRD can't be filed is held in §4 step 5. That covers the brand check failing twice, a duplicate, a source it won't accept, and `max_rejections_per_day`.
- A limit refusal stops the day before `binding` runs.
- A head held yesterday is no longer open.
- A resting row isn't open.
- So every path either files the head or holds it. The one exception is R1, where the head the code means isn't the one the prompt shows.

### Security

No finding reaches confidence 8 or above.

What was checked, and why each holds:

- **Arguments:** text after `--` is one argument, and no shell sees it.
- **`apps idea` from a scheduled run:** unreachable (`NEVER`, deny rules, and the `remote` job check).
- **What `--idea` and `hold-idea` can reach:** only his oldest open row, and they can't forge `source`.
- **Paths:** slugs are never part of a path, the lock name is a constant, and `mkstemp` uses `O_EXCL`.
- **YAML:** only `safe_dump` and `safe_load`.
- **`held_reason` in the digest:** it goes through `for_discord` with `allowed_mentions: {"parse": []}`, and it is capped and has its newlines collapsed.

### `test_uat_seed_outreach` and the live data folder

- **It reads the live folder and doesn't write to it.**
  - `test_every_scenario_refuses_the_live_folders_and_changes_nothing` (`tests/test_uat_seed_outreach.py:366-382`) walks and `lstat`s the live `jurasolutions/data/growth/` and the real `config/`.
  - It then runs `tests/uat/seed.py` with `JURA_GROWTH_DATA_DIR` set to the live folder, expecting a refusal.
  - `seed.refusal` (`tests/uat/seed.py:140-155`) refuses a folder inside `jurasolutions/` before it opens a database or writes a file. The test asserts exit 2, "refused:", and an unchanged snapshot.
  - So it never writes to the live folder unless that refusal regresses, and the test would catch such a regression.
- **The likely cause of the flake:** the snapshot leaves out only `growth.db*` and `locks/`.
  - The live engine on `main` keeps writing elsewhere in that folder. `runs/2026-10-31.jsonl` changed at 21:42 tonight, and so can `transcripts/`, `discord-outbox/` and `app-backlog.yaml`.
  - A live write during the few seconds the test runs fails it.
  - This was already true on `main` and isn't caused by this branch.
  - Once this branch is live, a backlog save also briefly creates `.app-backlog.*.tmp` there, which is one more short-lived entry that can trip it.
  - Worth a follow-up: exclude `runs/`, `transcripts/` and `discord-outbox/`, or snapshot only the files the seed could write.

## Re-review d4748a7

- **Compared:** d4748a7 against 6b69230 (the commit approved in round 2). Every changed file was read: `docs/app-factory.md`, `docs/dispatch-contract.md`, `jura_growth/agents/apps/__init__.py`, `backlog.py`, `factory.py`, `ideas.py`, `prompts/app-factory.md`, `tests/test_apps_idea.py`.
- **Checked against:** PRD §5.6, the "Amended 2026-10-31" bullet, including the new hold-day sentence; QA defects 02 and 03; round-2 findings R1 to R8.
- **Reviewer:** crew reviewer, round 3, 2026-10-31.

### Verdict: changes-requested

Every round-2 finding and both QA defects are fixed, and the R1 stuck-day repro now passes. One blocking finding remains, B1, in the new R2 recovery path. `mark_missed` decides that a `mark_failed` event is still unhandled only because no backlog row carries its `app_id`. `backlog.rest` removes that `app_id` when a PRD expires, so the next precheck replays the old event. The rested idea goes back to `prd-pending` for good, and it does the same after every expiry or hand fix. The fix is small: treat an event as handled once it has an `apps.backlog.marked` event, or once its PRD has left `prd/pending/apps/`.

### Evidence

- **Full suite** (worktree exports, temp data and outputs): `uv run pytest -q -p no:cacheprovider -o addopts=""` gave **4070 passed** in 369s. Afterwards the temp data folder was empty and `git status` was clean.
- **pyflakes** (`uvx --offline pyflakes`) on `ideas.py`, `backlog.py`, `factory.py` and `apps/__init__.py`: clean.
- **Round-2 probes** (`review01r2/tests_copy/test_review_probe_r2.py`, rerun from a fresh copy of the branch's tests in `review01r3/tests_copy/`): 7 passed, 1 failed as expected. The one that fails is the round-2 R2 repro, which expected `submit-prd` to raise `TimeoutError`. It now answers `filed`, which is the fix. The remote lock-timeout probe now answers `{"ok": false, "answer": "refused", "exit_code": 1, "text": "refused: the backlog is busy (another command is writing it); try again in a minute"}`.
- **`review01r2/mixed_race.sh`:** 12 of 12 rows kept and 6 of 6 drops landed.
- **`review01r2/lock_timeout.sh`** (real processes): `apps idea` exited 1 after 31s with "refused: the backlog is busy …". It printed no traceback and wrote no row.
- **Round-3 probes** (`review01r3/tests_copy/test_review_probe_r3.py`):
  - **R1 stuck day, passes.** The mark times out, and `submit-prd` exits 0 with "filed: APP-003" and "PRD filed; the backlog row will be marked on the next run (TimeoutError)". `apps context` lists `ting_yu_ideas: []`. The next day, a dry run of another PRD (APP-004 Petty cash log) "passes every check".
  - **Double pass, passes.** The first `mark_missed` returns `["APP-003"]`. The second returns `[]` and leaves the backlog unchanged.
  - **Rest after the catch-up, fails (B1).**
    - After the expiry (`builds._set_aside(..., skipped=False)`) the row reads `{'status': 'idea', 'app_id': None, 'reopens': '2026-12-02', 'prd': None}`.
    - After the next precheck it reads `{'status': 'prd-pending', 'app_id': 'APP-003', 'reopens': '2026-12-02', 'prd': 'prd/pending/apps/prd-app-003-…'}`, and its effective status is `prd-pending`.
  - **Skip before the catch-up, fails (S1).** After the skip the row reads `dropped`, and after the next precheck it reads `prd-pending`. The renamed case (`--idea do-maker`) ends the same way: `prd-pending` for a skipped PRD.
  - **Renamed idea, mark still pending, and a dry run (S2):**
    - A dry run of another PRD is refused with "idea: Ting Yu's idea do-maker comes first …".
    - The real `submit-prd` runs `mark_missed` first, so it files (exit 0) and the renamed row is marked. Under a real `submit-prd`, no PRD is refused while a mark is pending.
  - **Held while its mark was pending:** the row ends `prd-pending` with `held` set. That is harmless, and it is covered by S2.
  - **Slug-less hand row (S3):** `submit-prd --idea do-maker` exits 0 and "backlog updated". The output lists `('DO maker', 'idea', 'ting-yu')` and a new `('Delivery order maker', 'prd-pending', None)` row: his row stays open and a second row is added.
- **`code-review` pass** (forked, read only) returned 7 findings. Findings 1 and 2 are B1 and S1. Finding 3 is S2. Finding 7 is S3, which I reproduced. Findings 4 and 5 are N1 and N2. Finding 6 (altitude: reconcile from `app_prds`) is folded into the B1 fix as an option.
- **`security-review` pass** (sub-agent, read only): nothing at confidence 8 or above.
- **Blocked paths:** none touched (`git diff 1206360 d4748a7 --name-only` has nothing under `inputs/`, `design-system/`, `.env` or CI). **UI files:** none.

### Round-2 findings and QA defects, rechecked

| Finding | Status | Where |
|---|---|---|
| R1 | Fixed. `binding` and `hold` judge the head on `ideas.view` (`backlog.effective` with the same PRD folders and registry as `_overview`), and write the raw row by slug. Tested, and my stuck-day repro passes | `ideas.py:165-202,215-239` |
| R2 | Fixed as asked: "filed", an `apps.backlog.mark_failed` event, and a catch-up in the precheck and `submit-prd`. The catch-up has B1, S1 and S2 | `factory.py:163-200`, `__init__.py:72,301` |
| R3 | Fixed: "refused: the backlog is busy …", exit 1, locally and through `remote` | `__init__.py:263-265,282-284`, `ideas.py:34` |
| R4 | Fixed: step 3 holds (step 5) before `FAIL` | `prompts/app-factory.md:173-175` |
| R5 | Fixed. On a hold day, `--idea` for the new head is accepted, a PRD with its name binds to it, and other PRDs pass. This matches the PRD sentence "may file the next of Ting Yu's ideas (bound with `--idea`, or by its name) or fall back to the normal pick". The prompt's "the next one waits for tomorrow's run" (`prompts/app-factory.md:60-61`) is one of the choices the PRD allows | `ideas.py:194-201` |
| R6 | Fixed: the old mode is kept, and a new file is 0644 | `backlog.py:73-76` |
| R7 | Fixed: `backlog._note` | `ideas.py:238` |
| R8 | Fixed: `held_on(rows, day)`, one load | `ideas.py:155-156` |
| R9 | Left by the conductor's decision | |
| D02 | Fixed: `ideas.sentence` adds a full stop only when the reason doesn't end in `.`, `!`, `?` or `…` | `ideas.py:159-162`, `__init__.py:90` |
| D03 | Fixed: a name with no `[A-Za-z]` is refused with exit 2, for "2026", "<@123>" and "123 456" | `ideas.py:106-107` |

### The R2 recovery path

- **Under the lock?**
  - The precheck runs inside the runner's job lock (`runner.py:111-113`, called from `_run_locked`).
  - The connection is autocommit (`db.py:23`, `isolation_level=None`), so no SQLite write lock is held while `mark_written` waits up to 30 seconds for the backlog lock.
  - Each mark takes the backlog lock inside `mark_written`. The "already marked" check reads the backlog outside that lock (N2).
  - Every exception is swallowed, so a busy backlog never fails the run.
- **Ordering with the queue head:**
  - `submit-prd` runs `mark_missed` before `factory.submit`, so `binding` sees the marked row. My probe filed APP-004 while a renamed mark was pending.
  - A dry run, and `apps context`, don't run it (S2).
- **Idempotency:** a second pass is a no-op, and an `app_id` already on a row is skipped. But "on a row" is the wrong test for "handled" (B1).
- **Events table conventions:**
  - The kind and level follow `apps.backlog.release_failed` and `apps.prd.set_aside_failed`.
  - The payload goes through `config.redact` and the constant SQL is parameterised.
  - `core/0005`'s triggers cover only `approvals` and `approval_decisions`, so they don't touch this event. No migration is added, so an older checkout runs unchanged.
  - Events are append-only (`0001_core.sql:29-32`), and `mark_missed` is the first code that drives state from them. A handled event can't be updated or deleted, so it has to be closed by a second event. `apps.backlog.marked` is already written, but nothing reads it. That is the root of B1.

### Standards

**Blocking**

- **B1. `factory.py:193`: a `mark_failed` event is replayed after `rest` and undoes it.**
  - **The rule it breaks:** `backlog.rest`'s contract (`backlog.py:168`, "the idea is an idea again, offered from `reopens`") and the expiry flow in `builds._set_aside` (`builds.py:337`).
  - **Why it happens:** `mark_missed` treats "no row carries this `app_id`" as "not yet marked", and `rest` pops `app_id`, `prd` and `prd_date`.
  - **Reproduced:**
    1. The mark fails, and the next precheck marks the row.
    2. The PRD expires, and the row is `idea` with `reopens: 2026-12-02`.
    3. The next precheck sets it back to `prd-pending APP-003`, with the path of a PRD that is now in `prd/skipped/apps/`.
  - **The effect:** the idea is never offered again. Because events are append-only, a hand fix that removes `app_id` is reverted at the next 06:30 precheck.
  - **Fix:** skip an event that already has an `apps.backlog.marked` event for its `app_id`. Also skip one whose PRD has left `prd/pending/apps/` (`builds.pending_file(app_id) is None`). Add a test for expiry and one for skip.
  - **Alternative fix:** reconcile from `app_prds`, which already holds the filing, and record the renamed idea's slug there.

**Should fix**

- **S1. `factory.py:193`: a skip before the catch-up is overwritten.**
  - **What happens:** Ting Yu skips the PRD on the day it was filed. `drop` finds the unmarked row by slug and sets it `dropped`, or for a renamed idea finds nothing. The next precheck then marks the row `prd-pending`.
  - **Reproduced** for both cases.
  - **The effect:** the factory's behaviour doesn't change (neither status is a candidate). But `apps backlog` shows a skipped PRD as pending, against his decision ("the idea closes for good", `backlog.py:156`).
  - **Fix:** the same as B1's (`pending_file`).
- **S2. `ideas.py:165-170`, `__init__.py:298-301`: a pending mark for a renamed idea is invisible to the dry run and to `apps context`.**
  - **Why:** `view` matches a PRD to a row by slug only, and the renamed PRD's slug differs.
  - **When it bites:** only after the precheck's own pass was also busy. Then the context lists the idea first, and the factory's mandatory dry run of any other PRD is refused with "do-maker comes first". The factory may then hold an idea whose PRD is filed, or write a second PRD for it on another day.
  - **Fix:** run `mark_missed` on dry runs too, and in `apps context`. It only writes the backlog for an already filed PRD. Or have `view` treat an unresolved event's `idea` as `prd-pending`.
- **S3. `backlog.py:119` against `ideas.py:184`: a hand-added idea row with no `slug` is accepted by `binding` but missed by `mark_written`.**
  - **Why:** `binding` now matches the effective slug, `slugify(name)`. `mark_written` still matches the raw `r.get("slug") == idea`.
  - **Reproduced:** `submit-prd --idea do-maker` exits 0 and "backlog updated". His row stays `idea`, and a new factory row is added.
  - **A regression from 6b69230,** which looked up the raw row and refused.
  - **Fix:** match `(r.get("slug") or prd_mod.slugify(r["name"])) == idea` in `mark_written`.

**Nit**

- **N1. `factory.py:169`:** `except Exception` turns any `mark_written` failure into "filed … will be marked on the next run", including a hand-broken YAML. `mark_missed` then swallows the same error at every pass. Narrow it to `TimeoutError` and `OSError`, or name the error in the digest so a permanent failure is seen.
- **N2. `factory.py:193-195`:** the "already marked" check reads the backlog outside the lock, so a precheck and a `submit-prd` at the same moment can both mark. The second rewrite only moves `prd_date`. Each unresolved event can also wait 30 seconds, so N events can hold up the precheck for N times 30 seconds. B1's "handled" check removes most of both.
- **N3. Reuse.** `ideas.view` (`ideas.py:165-170`) repeats `_overview`'s `backlog.effective(...)` call (`__init__.py:155-158`). Have `_overview` call `ideas.view`, so the two can't drift apart. Drift between them is exactly what R1 was.

### Spec

| Amendment line | Code |
|---|---|
| Name at most 60 characters, in Latin letters | Matches (D03 fixed) |
| Hold reason at most 300 characters, digest carries it | Matches (D02 fixed) |
| "Only the oldest open idea can be held" | Matches, judged on the context's view (R1) |
| `--idea` only for his oldest open idea; "While that idea waits unheld, no other PRD is filed" | Matches, apart from S3 (a slug-less hand row) |
| "On the day an idea is held, the factory may file the next of Ting Yu's ideas (bound with `--idea`, or by its name) or fall back to the normal pick" | Matches (`ideas.py:194-201`, tested by `test_on_the_day_one_is_held_the_new_head_still_binds_r5`) |
| "picks Ting Yu's open ideas … oldest first" | Matches. S2 is the one window where the context and the code see a filed renamed idea as still open |

### Security

No finding reaches confidence 8 or above.

- **Can a forged `mark_failed` payload be written?** Only `factory.submit` writes one, through the parameterised `log.event`. `remote` can't write an event.
- **`prd_path`:** it is stored, never opened.
- **YAML:** still `safe_dump` and `safe_load`.
- **The new error text:** it is an exception name and message with no credentials, and it is redacted.
- **The new chmod:** it copies the existing mode, so an existing file can't become more permissive. A first file is now 0644, as on `main`, and holds no secrets.

## Re-review 725f272

- **Compared:** 725f272 against d4748a7, which was reviewed in round 3. I read every changed file: `docs/app-factory.md`, `jura_growth/agents/apps/__init__.py`, `backlog.py`, `factory.py`, `prompts/app-factory.md` and `tests/test_apps_idea.py`. I also read the code the filing path reaches: `builds.request`, `approvals.request` with `_lapse_if_due`, `builds._set_aside`, `db.transaction` with `after_commit`, `gate.gate`, `discord.alert` and `locks.waiting`.
- **Checked against:** the conductor's round-4 decision (crew-log, 2026-11-01T01:05), PRD §5.6 with the "Amended 2026-10-31" bullet, and round-3 findings B1, S1, S2, S3 and N1 to N3.
- **Reviewer:** crew reviewer, round 4, 2026-10-31.

### Verdict: approve

No finding blocks. The recovery path is gone, and nothing of it is left behind. Filing now takes the backlog lock first. A busy backlog refuses with nothing filed and no attempt used. The lock is released on every exit I could drive. S3 and N3 are fixed, and B1, S1 and S2 can no longer happen. One finding is *should fix*: a mark that fails after filing for a reason other than the lock now has no recovery (R4-S1). There are four nits. None of them changes the verdict.

### Evidence

- **Full suite** (worktree `.venv`, `JURA_ROOT` set to the real tree, temporary `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`): `uv run pytest -q -p no:cacheprovider -o addopts=""` gave **4075 passed** in 314s. HEAD was 725f272 and `git status` was clean afterwards.
- **pyflakes** (`uvx --offline pyflakes`) on `ideas.py`, `backlog.py`, `factory.py` and `apps/__init__.py`: clean. In `tests/test_apps_idea.py` it reports only the `prd_tree` fixture import, which is the suite's usual pattern. **pyright** (`--pythonpath .venv/bin/python`) on `factory.py`, `backlog.py` and `apps/__init__.py`: 0 errors.
- **Round-4 probes** (`review01r4/tests_copy/test_review_probe_r4.py`, on a fresh copy of the branch's tests): **14 passed.**
  - **Busy:** with the lock held and `LOCK_TIMEOUT` at 0.2s, `submit-prd --idea do-maker` exits 1 with exactly `refused: the backlog is busy, try submit-prd again`. The counts of `app_prds`, `approvals`, `qa_attempts` and `events` are unchanged. `rejections_today` stays 0, no `prd-app-003-*` file is written, the backlog is unchanged, and the lock is free afterwards.
  - **Lock released on every exit:** I drove six exits, and the lock was free (`locks.held` got it) after each one:
    - `gate.gate` raising `RuntimeError`
    - a first brand failure (`retry`)
    - a second brand failure (`dropped`)
    - a limit refusal
    - a structural rejection
    - "already exists"
  - **Hold time** of a real filing, timed inside `locks.waiting`: 0.03s.
  - **Moot B1:** file the PRD, let it expire, run the next precheck. The row stays `{'status': 'idea', 'app_id': None, 'reopens': '2026-12-02'}`.
  - **Moot S1:** a renamed idea, filed and then skipped, followed by the next precheck, stays `[('delivery-order-maker', 'dropped')]`.
  - **Moot S2:** after a renamed filing, `apps context` lists `ting_yu_ideas: []`. The next day, a dry run of APP-004 "passes every check".
  - **R4-S1 repro:** see below.
  - **R4-N1 repro:** see below.
- **Real processes** (`review01r4`, worktree `.venv`, temporary data and a copy of the QA PRD tree): a second process held `app-backlog.lock` for 40s. `jura-growth apps submit-prd` printed `refused: the backlog is busy, try submit-prd again` and exited 1 after 30s, with no traceback. The PRD tree was unchanged, and the database showed `app_prds 0, qa_attempts 0`. The one approval present is the `raise_waiting` catch-up for the QA tree's APP-005, which runs before the lock, as on `main`.
- **Earlier probes rerun:**
  - **Round 2** (`test_review_probe_r2.py`): 7 passed. The remote lock-timeout probe still answers `{"ok": false, "answer": "refused", "exit_code": 1, "text": "refused: the backlog is busy (another command is writing it); try again in a minute"}`. The one that fails, `test_mismatch_backlog_unmarked_after_a_failed_mark_written`, now fails by design: it monkeypatches `backlog.mark_written`, which filing no longer calls.
  - **Round 3:** the S3 probe now shows one row, `('Delivery order maker', 'prd-pending', 'ting-yu')`. The other round-3 probes call `mark_missed` or patch the mark, so they are moot.
- **`code-review` pass** (forked, read only): 8 findings.
  - Finding 1 is R4-S1, which I reproduced.
  - Finding 2, the hold time, is folded into the lock-hold assessment below and into R4-N2.
  - Findings 5, 6 and 8 are R4-N3 and R4-N4.
  - I dismissed three:
    - **Finding 3, dry run against real run:** the queue head can change between the two only through `hold-idea` (the factory's own step) or a hand edit. `apps idea` adds the newest row, never the head.
    - **Finding 4, `--idea` re-entry untested:** `test_a_busy_backlog_refuses_submit_prd_before_anything_is_filed` files with `--idea` after the retry. With the default 30s timeout, a re-entry there would hang for 30s and then answer BUSY, so that test would fail.
    - **Finding 7, `ExitStack`:** a style preference. `ExitStack` is the usual way to take a context manager only on some calls.
- **`security-review` pass** (sub-agent, read only): nothing at confidence 8 or above. It raised the Discord alert under the lock, which is R4-N2.
- **Blocked paths:** none. `git diff 1206360 725f272 --name-only` has nothing under `inputs/`, `design-system/`, `.github/` or `.env`. **UI files:** none.

### Check 1: the recovery path is gone

- `git grep -e mark_failed -e mark_missed -e apps.backlog.marked -e _MARK_KEYS -e _mark_written 725f272` (excluding `.scratch/`) finds only the guard test at `tests/test_apps_idea.py:690-695`. Nothing is left in code or docs, and `factory.py` no longer imports `json`.
- **No events written:** the busy path writes no event (the events count is unchanged in the probe). The successful path writes `apps.prd.written`, as on `main`. The branch was never merged, so no live database holds `mark_failed` rows that need cleaning.
- **Docs:** `docs/app-factory.md:42` now describes lock-first filing and the busy answer. The PRD (`prd-jura-app-factory-2026-10-24.md`) never described the recovery path. `docs/dispatch-contract.md` still describes `apps idea`'s busy answer correctly.
- **Helpers:** `_mark_written` is gone. `backlog.mark_written`, the wrapper that takes the lock, no longer has a production caller (R4-N3).

### Check 2: lock-first filing

- **No self-deadlock on the normal paths.** Inside `_submit`, every backlog read goes through `backlog.load()` with no lock. That covers `catalog.taken`, `catalog.next_number`, `ideas.binding` → `ideas.view`, and `mark_written_held`. `gate.gate`, `log.event` and `builds.request` take no backlog lock. `builds.raise_waiting` and `cards.sweep_safely` run outside `factory.submit` (`__init__.py:298-302`). The suite's re-entry test covers the plain path, and the `--idea` retry test covers the renamed path.
- **One hook path reaches `rest` under the lock (R4-N1).** It goes `builds.request` → `approvals.request` → `_lapse_if_due` → `on_expire` → `_set_aside`, then `db.after_commit` → `backlog.rest`. The after-commit step runs when `with db.transaction(conn)` ends at `factory.py:172-179`, and that is still inside `submit`'s lock. `flock` on a second file descriptor blocks inside the same process, so `rest` waits on its own process and times out. It times out rather than hangs.
  - **When it can happen:** only if a live, overdue `app-build` request exists for an app number that no file, `app_prds` row, backlog row or registry entry still uses. That needs a factory-authored PRD placed by hand, raised by the catch-up, then deleted by hand, with no heartbeat in between. The hourly `expire_due` would otherwise supersede the request as "the item is gone".
- **Busy: nothing filed, no attempt used.** The lock is taken at `factory.py:114-118`, before the limit check, the rejection count, the brand gate (`qa_attempts`), the file, `app_prds` and the request. This is confirmed in-process and with real processes.
- **Released on every exit.** `ExitStack` leaves `locks.waiting`, whose `finally` blocks run `LOCK_UN` and `close()`. The six probes above (an exception, both brand outcomes, a limit, a rejection, "exists") and the save-failure probe all leave the lock free.
- **How long the lock is held.** The brand checker is local regex (`brand_check.py`, no I/O), and a passing filing holds the lock for about 0.03s. Two things under the lock can wait longer:
  - **A brand failure** posts to #alerts (`gate.py:76-79` → `discord.alert`, `httpx.Client(timeout=30)`, up to three tries on 429 or 5xx, with sleeps of up to 10s). Normally that is under a second.
  - **The filing transaction and the gate's writes** can wait on SQLite's `busy_timeout` of 30000ms if another process holds a write transaction. The repo's writers keep those short.
  - **So, in practice,** the 30s `apps idea` timeout is exceeded only if Discord hangs for more than 30s, or a SQLite writer stalls, during a factory brand failure around 06:30 SGT.
  - **What Ting Yu sees if it happens:** exit 1 with `refused: the backlog is busy (another command is writing it); try again in a minute`. Nothing is written, so resending is safe. That answer arrives at about 30s plus start-up, inside Dispatch's 60-second SSH `subprocess.run` timeout (`docs/dispatch-contract.md:45`), so he sees the refusal rather than a Dispatch timeout.
  - **The same window** can also make a skip or expiry's `backlog.drop`/`rest` time out, which logs `apps.prd.set_aside_failed` (R4-N2).

### Check 3: round-3 findings

| Finding | Status | Where |
|---|---|---|
| B1 | Moot: there are no `mark_failed` events to replay. My probe shows a rested row stays rested | `factory.py` (removed) |
| S1 | Moot: a skipped filing stays `dropped` after the next precheck | the same |
| S2 | Moot: a renamed idea is marked under the same lock as its filing, so the context and the dry run never see it open | `factory.py:180-189` |
| S3 | Fixed: `mark_written_held` matches `(r.get("slug") or slugify(name)) == idea`. Tested, and my probe shows one `ting-yu` row, `prd-pending` | `backlog.py:127` |
| N1 | Moot: the broad `except` is gone. A failure now raises (see R4-S1) | |
| N2 | Moot: the mark runs under the lock that filing took, and there's no catch-up loop | |
| N3 | Fixed: `_overview` uses `ideas.view` | `__init__.py:157` |

### Check 4: the prompt

`prompts/app-factory.md:177-179` and `:184-186` say that a busy refusal filed nothing and used no attempt, to retry `submit-prd` once in the same run, then to finish `SKIP: backlog busy`, and never to hold the idea for it. Step 5 lists "busy" beside "limit" as not the idea's fault. Dry runs take no lock, so the two dry runs in step 1 can't be refused as busy. This is right: a busy retry spends no brand attempt, and `SKIP` matches how a limit refusal is already handled. `test_the_prompt_retries_a_busy_refusal_once_then_skips_and_never_holds` pins it.

### Standards

**Blocking**

None.

**Should fix**

- **R4-S1. `factory.py:180`: a mark that fails after filing has no recovery, and for a renamed idea his row stays first.**
  - **Why:** `mark_written_held` runs after the file is written and after `app_prds` and the request are committed. Removing `mark_missed` also removed the only catch-up. The lock-timeout cause is now ruled out by design. What is left is I/O: disk full, a `paths.writable` refusal, or a kill in the millisecond between commit and save.
  - **Reproduced** (`test_save_fails_after_filing`, with `backlog.save` raising `OSError(28)`):
    - The command raises a traceback, and the lock is freed.
    - `prd-app-003-delivery-order-maker-…` is filed, with `app_prds 1, approvals 1`.
    - His row reads `{'status': 'idea', 'app_id': None}`, and `ideas.queue(ideas.view(...))` puts `do-maker` at the head.
  - **The effect:** the next day the factory picks `do-maker` again. Its PRD is rejected as a duplicate of APP-003, and under step 5 it is held with a misleading reason. The queue unblocks itself after one wasted day.
  - **Why it isn't blocking:** this failure class (an I/O error after commit) is the same as `main`'s. The only new part is the renamed-idea consequence, and the cause is now rare.
  - **Cheapest fix:** catch `OSError` around the mark and answer `filed: …` plus `backlog not updated (<error>); mark <idea> prd-pending <APP-NNN> in app-backlog.yaml by hand`, the way `releases.py:378-384` already handles `backlog.release`. Alternatively, have `ideas.view` treat a row as filed when `app_prds` holds a filing bound to its slug.

**Nit**

- **R4-N1. `factory.py:172-179` with `builds.py:327-339`: the lapse hook's after-commit `backlog.rest` runs under `submit`'s lock and waits on its own process for 30s.**
  - **Reproduced:** `test_lapse_hook_inside_the_filing_transaction`. An overdue live request for APP-003 was planted, with `LOCK_TIMEOUT` at 1s.
    - The run took 1.25s and logged `apps.prd.set_aside_failed` with "TimeoutError: the app-backlog lock is still held after 1 seconds".
    - The brand-new PRD was moved to `prd/skipped/apps/`.
    - The output still said "filed … approval request A-0001 raised".
  - **What is new:** moving the new file to `prd/skipped/apps/` is existing behaviour from `main`. Only the 30-second self-wait is new.
  - **Why it's a nit:** the precondition needs hand edits and a missed heartbeat (see Check 2).
  - **Fix, if wanted:** refuse to file when `approvals` already holds any record for `app:<app_id>`. That also fixes the file move.
- **R4-N2. `gate.py:76-79`: the brand-failure alert posts to Discord while the backlog lock is held.**
  - **The effect:** a hung Discord call (30s timeout, up to three tries) can make `apps idea` answer busy. It can also make a skip or expiry's `drop`/`rest` time out, which logs `set_aside_failed`. The raw row then stays `prd-pending`, because `backlog.effective` doesn't map `prd/skipped/apps/` to a status.
  - **Fix:** call `gate.gate(..., alert=False)` under the lock, and send the alert after `submit` releases it.
- **R4-N3. `backlog.py:113-119`:** `mark_written`, the wrapper that takes the lock, is used only by `tests/gate_adapter_app_build.py`. `_overview` (`__init__.py:154-157`) now reads `prd_files()` and `registry()` twice, once directly and once inside `ideas.view`. Both are harmless. Passing `files` and `live` into the view would save the second read.
- **R4-N4. `tests/test_apps_idea.py:690-695`:** `test_no_mark_failed_recovery_remains` greps source text, so a later legitimate mention of "mark_failed" would fail it. `hasattr(factory, "mark_missed")` together with the busy behaviour tests is enough.

### Spec

| Amendment line or decision | Code |
|---|---|
| Round-4 decision: "submit-prd takes the backlog lock before it files anything and holds it through mark_written" | Matches (`factory.py:110-120`, `:180`) |
| "a busy backlog refuses the submit with nothing filed (exit 1)" | Matches, in-process and with real processes |
| "the factory retries once in-run" | Matches (`prompts/app-factory.md:177-179`) |
| `--idea` only for his oldest open idea; "While that idea waits unheld, no other PRD is filed" | Matches. The S3 slug-less hand row is now marked |
| "picks Ting Yu's open ideas … oldest first", judged on the context's view | Matches. `_overview` and `binding` share `ideas.view`. The one exception is R4-S1's I/O-failure window |

### Security

No finding reaches confidence 8 or above.

- **Lock exposure:** `submit-prd` isn't on the remote allowlist (`remote.py:207-214`), so nobody in Discord can hold or starve the lock through it.
- **Lock path:** the lock name is a fixed string, and the path goes through `paths.writable`.
- **Slug fallback:** a plain equality check.
- **YAML:** still `safe_load` and `safe_dump`, with an atomic replace.
- **Logging:** no new logging. The removed event, which carried error text, is gone.
- **Prompt:** fixed text, with no untrusted content interpolated.
