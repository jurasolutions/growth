# Code review 01: the morning picture

- **Branch:** `crew/morning-brief-01-the-picture` at `7ba3e5b`
- **Fixed point:** `bf8c73e` (5 commits, 24 files)
- **Spec:** `issues/01-the-picture.md`, with what it points to in `reviews/functional.md` §1-3, `reviews/technical.md` and `reviews/test-strategy.md`, and the PRD

## Verdict: changes-requested

There are six blocking findings. Two let the verdict say "Nothing needs you right now." when something does. One prints a guessed zero. One cuts Fix instructions. Two let personal data reach the saved page or the picture. Most are small fixes.

The rest of the build holds up. The suite is green, ADR 0002 stands, the page escapes every route, no markup can be injected, and the lock retry stays on the post path. Test strategy criterion 8 counts a false verdict or a failing criterion as major and an unmasked value as critical, which is why these block.

File references are at `7ba3e5b`. "Reproduced" means I ran it on temp data in a throwaway checkout.

## What you asked me to look at

| Question | Answer | Finding |
|---|---|---|
| Can the verdict falsely say "Nothing needs you"? | Yes, by two routes. Three more give an all-clear that is too strong or undercounts | B1, B2; S1, S3 |
| Is any figure not recorded by the engine? | Yes. A 0 in the Decide heading on a bad day, and US$0.00 when a run's cost wasn't recorded | B3; S4 |
| Is every route into the page and the `.html` masked? | No. Text is cut before it is masked on three routes, and a lock during mask learning leaves names unmasked | B5, B6 |
| Does ADR 0002 hold (read-only, no `content()` or `preview()`)? | Yes | Spec, "Checked" |
| Does the lock retry stay on the post path? | Yes, but it misses a lock inside a plug-in hook, and its wait nearly fills Dispatch's 60 seconds | S2, S5 |

## Standards

**Blocking:** none.

**Should fix**

- **S7. New code duplicates existing helpers.**
  - `picture.py:134` `_plural` is the same as `health.py:134`, and `picture` already imports `health`.
  - `picture.py:365` `_unavailable` is the same as `one_pager.py:92`. Move it to `mission`, beside `db_problem`, because `one_pager` imports `picture`.
  - `one_pager.py:68` `_fix_line` has the same shape as `remote.py:224` `_short`.
- **S8. The glossary now contradicts itself.** `CONTEXT.md:34` says `due` "never counts as needing attention", but `picture.py:56,66` puts a passed `due` slot into Fix and the verdict. The diff changed the Health strip entry and not this one. Say that this is the classifier's word and that the picture reads a passed `due` as "Didn't run". Code review 02's S3 clause on "not installed" belongs in the same edit.

**Nit** (judgement calls; none breaks a documented rule unless it says so)

- `health.py:157,186`: `brief` is a name `CONTEXT.md` says to avoid for this. Use `short`. This one is a small breach of a documented rule.
- `health.py:157-196`: possible Repeated Switches. `short` is branched on at seven sites, and `:194` bypasses `worded`.
- `health.py:202,227`: possible Duplicated Code. `_missed` and `_missed_counts` walk the same window. The ticket's conflict rule asks for this split, so leave it until the rebase.
- `picture.py:99,281` repeat the `reply_detection is False` rule. `picture.py:89,209` repeat the `snapshot.morning.figures if snapshot.morning else {}` read. `_counted` (`:138`) and `_tile` (`:269`) repeat the dash check.
- `health.py:254`: possible Primitive Obsession. `problem.strip.partition(". ")` parses a sentence back apart. `DbWording` could carry the action as a field.
- `picture.py:195`: possible Mysterious Name. `UNAVAILABLE` sits beside `NOT_AVAILABLE` (`:43`), and `OUT_OF_DATE` shadows `health.OUT_OF_DATE`, with both used at `:243-244`.
- `images.py`: possible Speculative Generality. The `.page or body` fallback has one production caller, whose page has `.page`.
- `picture.py:177-183,252` hard-code jobs, kinds and figure keys in the core. Technical N7 accepts this, so no change is needed.

**Checked, no finding:** every CSS token exists in the design system (test and my read). The core imports no agent. `MAX_HEIGHT` and `LOCK_PATIENCE` aren't caps, so they don't belong in `caps.py`. Commit style and page voice follow the card and README §3. `pyright` on the eight touched modules reports 0 errors.

## Spec

### Blocking

**B1. An installed job that has never left a trace gives a false all-clear.** `picture.py:66-79`; `slots.py:239`.

- **Rule:** functional B1, "a job that didn't run becomes a Fix line"; MB6; PRD "The verdict can't falsely clear him."
- **Reproduced:** `installs` says `installed`, and the job has no record, so its passed 08:30 slot reads `not installed`. The row says "Not installed / No run on record yet", Fix is empty, and the verdict is "Nothing needs you right now." The full read gave the same slot status and no Fix line for the job.
- **Why it matters:** this is `outreach-requests` on its first mornings, the one job with no history. If launchd never fires it, the picture contradicts itself indefinitely: the job is installed by `health`, "Not installed" by its row, and absent from Fix.
- **Fix:** in `_didnt_run` and `_overdue_row`, treat a passed `not installed` slot as "Didn't run" when `installs[job] == INSTALLED`. Ticket 02's `installed_at` should exclude slots from before the install, so install day stays clean. Functional §4 calls the row correct "until its first trace". That holds for the word before the first slot passes, not after.

**B2. A recorded reply is hidden when reply detection is off.** `picture.py:99`, and `:281` for the tile.

- **Rule:** MB1, "appears only when all four counts are 0".
- **Reproduced:** `replies=2, reply_detection=False` gives "Nothing needs you right now." and a dash on the tile. The flag is today's setting and the count is yesterday's, so turning IMAP off overnight is enough.
- **Fix:** return the count when it is above 0, and treat detection off as 0 only when the count is 0 or missing. Show the recorded count on the tile too. See "For the conductor" on the 0 case.

**B3. The bad-day page prints a guessed zero.** `picture.py:414`.

- **Rule:** MB7, "never a guessed zero".
- **Reproduced:** `database_locked()` and `database_missing()` both draw "Decide in #approvals 0" above "Not available". I viewed the render. No test covers it.
- **Fix:** show a dash when `snapshot.approvals is None`, and assert it in `test_slots_that_cant_be_read_say_not_available_everywhere` and the two bad-day read tests.

**B4. Real plug-in Fix lines lose their instruction.** `picture.py:84`; `agents/apps/builds.py:302`; `agents/apps/releases.py:433,446`.

- **Rule:** MB3, "its instruction is not cut"; S1, "put the action first in the short wording".
- **Reproduced in Chrome, offline, through `oracle.inspect`:**

| Line | Characters | Result |
|---|---|---|
| "App on its preview: …; reporting the build again with `jura-growth apps built` … asks again." | 191 | Cut at 3 lines |
| "App release waiting for main: …; once main holds it, run `jura-growth apps released` …" | 173 | Cut at 3 lines |
| "Build handoff waiting for a builder: … Build it: open Claude Code …" | 204 | Cut at 3 lines |
| "App release approved: …" | 113 | Fits exactly |

- **Why the test missed it:** `test_each_real_fix_wording_fits_its_row_whole` reads `HEALTH_ITEMS`, whose plug-in row is a stand-in, "Build it: APP-014 (approval A-0153)" (`tests/test_one_pager.py:117`). That file must stay as it is, so add the real wordings to `picture_world.health_pages()`.
- **Also in the strip:** the "Not posted to #approvals" and "approved but not used" lines (`health.py:182,185`) weren't reworded. They fit, but check them against the rule when you add the wordings.
- **Fix:** reword these lines with the action first and at most about 114 characters, or give the `health` hook a short form. The message still carries them in full, so a phone is unaffected.

### Should fix

**S1. A broken digest for Scout, Community or App factory still gives the plain all-clear.** `picture.py:102-115`. Reproduced: each digest raising, with nothing else wrong, gives "Nothing needs you right now." above a row showing "–". Outreach and Social get the qualified verdict only because their keys feed the counts. `test_a_plugin_whose_digest_raises_shows_dashes_not_zeros` tests only Social. Give any unread figure the "some figures couldn't be read" verdict. MB1 doesn't name this case, so it doesn't block, but the PRD's "can't falsely clear him" does cover it.

**S2. A lock inside a plug-in hook isn't retried.** `mission.py:233`; `digest.py:57`; `mission.py` `_plugin_lines`. Functional S4 says "on a lock, retry the read". Both hook routes catch the error, so `db_state` stays `ok`.

- With a real `BEGIN EXCLUSIVE` held during the social digest: no sleep, a dash on the row, and the by-hand count silently gone from the verdict.
- With `OperationalError("database is locked")` raised from the apps `health` hook: no sleep, and a false Fix line, "its health check failed".
- The lock has to arrive after the first query and last past the 2-second timeout, so this is less common than the case the retry handles. Re-raise a lock error from both catches on the read path, as `_yesterday` already does.

**S3. "To post by hand" counts only today's drafts and subtracts every day's requests.** `picture.py:87-92`; `agents/social/__init__.py:50`.

- Reproduced on a real read: a `draft` row dated yesterday gives a count of 0. With nothing else open, the verdict is "Nothing needs you right now."
- Reproduced on a built snapshot: 1 draft today and 1 `social-post` request from yesterday give "1 to decide." and no by-hand count.
- Functional B1 says "drafts waiting". If a stale draft really shouldn't be posted, record that decision and say so in the docstring. If it should, count open drafts across recent days. Match requests to drafts by date either way.

**S4. Claude spend shows US$0.00 when no cost was recorded.** `picture.py:282`; `digest.py:24`; `mission.py:372`. Reproduced: a `social` run yesterday with `cost_usd` NULL shows US$0.00. `log.finish_run` leaves it NULL on abandoned runs (`runner.py:220`). MB7 wants a dash for a figure that can't be read. This needs `digest.spend` to tell "no Claude runs" from "runs with no cost", and command jobs also leave NULL, so filter by job kind. A partly recorded day undercounts for the same reason.

**S5. The lock wait nearly fills Dispatch's window.** `mission.py:66`; `docs/dispatch-contract.md:45`. Read, not run. Worst case, `read_patiently` takes about 58 seconds (8 sleeps of 5 seconds, 9 reads of 2 seconds), then two Chrome runs at about a second each. Dispatch runs `/growth one-pager` with a 60-second timeout, so it could report a failure for a post that still goes out, and one-pagers aren't deduplicated (`one_pager.py:304`), so asking again posts twice. Functional S4 says "up to 60 seconds", so 45 meets it. `LOCK_PATIENCE = 45` is the small fix.

**S9. The privacy plants don't cover two of the nine routes.** `tests/test_picture_privacy.py:79`. The test strategy's risk 1 says to plant each value alone, per route.

- A nested digest figure is tested at the read seam with one address (`tests/test_picture_read.py:69`), not with every value through the page. Add it to `ROUTES`, which means drawing the figure through a route that reaches the page.
- The ICP line's `health()` is ticket 02's. Its plant belongs at the merge, so the conductor should carry it.

### Nit

- `one_pager.py:34,68`: MB10 says "in full", and a Fix line over 360 characters is cut. It protects the 2,000-character limit, and no real wording reaches it. See "For the conductor".
- `picture.py:252`: "Emails send 09:30" and "Posts go out" come from the schedule alone, so they read the same while paused or in shadow mode.
- `config/settings.yaml:53` and `.scratch/mission-control/setup/discord.md:46,114` still describe the grid. The conductor has these down for this ticket's merge. Nothing on the branch does them yet.

### Not asked for

All minor and defensible: the qualified verdict "Nothing to decide or fix, but some figures couldn't be read." (`picture.py:113`, logged by the developer), the row words "Out of date" and "Not installed", and skipping `NOT_INSTALLED` as well as `OUT_OF_DATE` (`picture.py:63`).

### Checked, no finding

| Item | Evidence |
|---|---|
| MB1 to MB13 each have tests | `test_picture.py`, `test_picture_chrome.py`, `test_one_pager_post.py`, `test_picture_read.py`. MB1, MB3 and MB7 have gaps, as above |
| T-B1 to T-B4, N1 to N5 | Met, apart from the wording gap in B4. `brief.py` is gone and no page holds `<script` |
| ADR 0002, MB13 | Read `mission.py`, `outreach.health`, `send.live_problems` and the digest hook. All read only. Spies on `content()` and `preview()` record no call. `cards.label` only replaces hyphens |
| Lock retry placement | `read_patiently` has one caller, `cli.py:418`, after `--grid` and `--no-post` return. `test_an_ordinary_read_never_waits` holds it. The sleep is injected |
| MB6 boundaries | 5 and 6 minutes, and the Monday community slot through Wednesday |
| A dead run reading "Still running" | `_abandon_stale` (`runner.py:127,205`) marks it failed after the timeout plus 15 minutes, before the one-pager reads. No finding |
| Conflict rule | `_missed`'s signature matches `main`. `_gap_lines` and `_missed_counts` are at the end of `health.py`. A trial merge with `crew/approvals-first-social-depth` conflicts in one hunk each in `health.py` and `mission.py` |
| Frozen tests | `test_mission_read.py` and `test_one_pager.py` change only time values and clock arguments. `sweep.py`, `fortnight.py`, `mission_world.py`, `test_mission_slots.py`, `pyproject.toml` and `uv.lock` have an empty diff against `main` |

## Security

Nothing here allows code execution or markup injection. The pass found no secret leak. It was run against the correct diff (`bf8c73e...7ba3e5b`), because the skill's own header showed a different branch. I reproduced B5, B6 and S6 by hand instead of running separate filter tasks.

### Blocking

**B5. Text is cut before it is masked, so part of an address reaches the saved page and the message.** `mission.py:340`, and the same order at `:278` and `:224`.

- **Rule:** MB8, "comes from the masked snapshot"; test strategy criterion 8, "Critical: an unmasked value in any output".
- **Reproduced through the post path:** a `runs.error` with an address straddling character 300 is cut to `jane.tan@exam`, which no longer matches `EMAIL_RE`. That fragment was found in `picture-<day>.html` and in the message. Masking again at `discord.post` can't help.
- **New in this diff:** the short wording now carries the error onto the picture and into the message (`health.py:171`). Before, `fixes()` kept only the first line, so the error stayed out. The PAUSE file's cut at `:278` reached the page already.
- **Pixels:** the three-line clamp hides character 300 in the PNG, so this route reaches the `.html`, kept for 14 days, and the message. The PAUSE file's 200 characters are also past the clamp.
- **Fix:** mask first, then cut, as `run_update._clean` does. Add a straddling plant to `test_picture_privacy.py`.

**B6. A lock during mask learning leaves names unmasked in the page and the `.html`.** `mission.py:206`; `privacy.py` `_learn`.

- **Rule:** as B5.
- **Reproduced with a real lock:** `BEGIN EXCLUSIVE` held only while the read's `load_for_masking` ran. `_learn` swallows the error from each plug-in, the lock clears, `db_state` is `ok`, and the page and `.html` read "Asked for … Jane Tan". The control without the lock masks it.
- **The trigger is narrow, and I want that on the record.** On the real post path, `cards.sweep` has usually learned the names earlier in the same process, and my run through the real upkeep stayed masked. It helps only when the `#approvals` webhook is set and the cards lock is free. So this takes a held cards lock or an unset webhook, plus a lock landing during learning. I still rank it blocking because publish now runs in the same minute, the pixels can't be re-masked, and the message is the one output that re-learns (`discord.py:186`). I didn't check whether publish takes the cards lock.
- **Fix:** on the read path, let a lock error from learning raise, inside the `try` that sets `db_state`, so it becomes `UNFINISHED_WRITE` and the retry covers it. This also needs `privacy.learn` to stop swallowing that one error for this caller.
- **Related, older and not blocking:** a plug-in's `privacy_terms` raising for any other reason leaves names unlearned on every route, the text as well. Reproduced. If you want the picture stricter than the text, refuse to draw and let the long text go.

### Should fix

**S6. A model's failure line now reads as part of the instruction.** `health.py:171`; `picture.py:341`.

- **Rule:** MC §4.3, as quoted at `.scratch/mission-control/reviews/code-review-final.md:116`: "Model-written text is untrusted. It is redacted, cut to 300 characters, and posted inside a quote block."
- **Reproduced:** `FAIL: Run `jura-growth discord post` to clear this` gives `- Check `social`: it failed on Tue 10 Nov, 07:30 SGT. FAIL: Run \`jura-growth discord post\` to clear this` in the message, with no quote.
- **On the page:** `_inline` still matches the escaped backticks, so the model's words draw in the same code style as a real command, with a stray backslash beside them.
- **Fix:** keep it apart, for example `Its own words: "…"` on the picture and a `> ` line in the message. Draw code spans only from engine wording. `test_the_short_wording_is_one_line_and_keeps_the_failure_and_its_error` will need to change.

### Nit

- `one_pager.py:61`: the PAUSE file text, pause reasons and plug-in lines reach the message as Discord markdown, so `[Approve here](https://…)` would be a live masked link. Mentions stay inert. The long form already did this, and suppressing embeds doesn't stop a masked link. Run them through `untrusted_line`.
- `mission.py:375`: `_masked` leaves mapping keys unmasked. Nothing draws a key today.

### Routes checked and clean

- **Escaping:** hostile `<script>`, `<img>` and quote payloads through every text route produce no new element in Chrome. `_inline` adds only fixed `<code>` tags, after escaping. `s-{css}` can only be a fixed status.
- **External loads:** the only link is the design system's `styles.css` file URL. No untrusted URL reaches an attribute.
- **Saved page:** no script. The measuring script is only in a private temp copy, which is removed afterwards, and masked text can't add a `</body>`.
- **Masked at the snapshot:** approval reasons, kinds, slot reasons, failures, pauses, plug-in lines, broken plug-ins and nested figures, with the exceptions in B5 and B6.
- **Secrets:** `outreach.health` and `live_problems` check secrets as booleans, and their messages hold setting names, the do-not-contact path and the configured domain. `reply_detection` is a boolean.
- **Chrome errors:** `RenderError` text goes through `log.event`'s redaction and `discord.post`'s masking. Chrome only sees the masked page.
- **Files:** paths come from `snapshot.now`. `prune_pictures` deletes only names that fully match its pattern. `pixels_only` strips PNG metadata before upload.

## Blocked paths

None. Nothing under `inputs/`, `design-system/`, `.env` or live `data/growth/` changed, and no CI workflow changed.

## UI

`crew:web-design-review` on `jura_growth/picture.py`. It is a fixed image, so the rules on focus, forms, animation, touch, hover, hydration and navigation don't apply: the page has no control or script. I viewed the typical and bad-day renders.

```text
## jura_growth/picture.py

jura_growth/picture.py:277 - "1 replies" when a tile is 1: caption doesn't follow the figure (nit)
jura_growth/picture.py:414 - "Decide in #approvals 0" on a bad day (B3)
jura_growth/picture.py:341 - code style on untrusted text (S6)
```

**Passes:** the heading order is h1, h2, h3; flex children have `min-width: 0`; long text clamps; empty states are handled; the viewport doesn't block zoom; the h1 uses `text-wrap: balance`.

**Notes, not findings:** the guidelines' Title Case gives way to the design system's sentence case. Straight apostrophes match the rest of the engine's text. `%H:%M` is fine for a single-reader SGT image, though the guidelines prefer `Intl`.

## For the conductor

- **Reply detection off with a count of 0.** The developer logged an all-clear here, and `test_picture.py:86` pins it. The tile shows a dash. I agree: otherwise there is no all-clear, ever. But it contradicts MB1's "all four counts are 0", so reword MB1 or record the decision. B2 is separate: it hides a recorded count.
- **MB10's "in full".** Waive it, or reword it to allow the 360-character cut.
- **B1 crosses both tickets.** The picture-side fix is here, and clean install-day behaviour needs ticket 02's `installed_at`.
- **Ticket 02 carries:** the ICP plant in `ROUTES`. A trial merge with ticket 02 conflicts in `README.md` and `.scratch/mission-control/setup/morning-brief.md`, as code review 02 said.
- **Sign-off:** the PRD records "not signed", proceeding under the standing instruction, with merge as his acceptance. I treated this as recorded and not as a finding.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest -rs -q -p no:cacheprovider -o addopts=""` at `7ba3e5b`, worktree exports set | 4181 passed, none skipped, in 414 s |
| `uv run pyright --pythonpath .venv/bin/python` on the eight touched modules | 0 errors, 0 warnings |
| `git merge-tree --write-tree` with `crew/approvals-first-social-depth` | Conflicts in `health.py` and `mission.py`, one hunk each |
| `git merge-tree --write-tree` with `crew/morning-brief-02-the-morning-order` | Conflicts in `README.md` and `morning-brief.md` |
| `git diff --name-only main crew/morning-brief-01-the-picture`, filtered to blocked paths | Empty |
| Throwaway probe tests on temp data | Results as quoted in B1 to B6, S1 to S4, S6. The probes ran in a throwaway checkout and aren't on the branch |
| `picture.render` offline on synthetic fixtures | Typical 1114 px, locked 949 px, worst 1554 px |

Everything ran in temp folders or a throwaway checkout. Nothing posted, `jura-growth run`, `schedule install` and `schedule render` were never run, and live data wasn't touched by these runs. Afterwards, the newest plist in `~/Library/LaunchAgents` was dated 29 October, and the newest file in the live `one-pager` folder was dated 30 October.

Not verified: real fonts (QA's record), Discord's display, and S5's timing, which I worked out by reading the code.
