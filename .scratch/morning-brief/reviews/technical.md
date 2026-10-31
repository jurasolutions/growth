# Technical review: morning brief

PRD: `jurasolutions/prd/pending/prd-jura-morning-brief-2026-10-31.md`. Draft: `73c13d5` on `crew/morning-brief`. Every decision below is taken under the standing instruction. Nothing here needs Ting Yu.

The approach is sound: a pure page built from the `mission.Snapshot`, drawn through the core Chrome helper, with `outreach raise-due` as a thin quiet job. Five things must change before it can ship, and one of them is in the schedule move rather than the picture.

Probes ran in temp folders with throwaway scripts: real Chrome on built snapshots, and `slots.classify` on simulated records. Nothing posted, and no launchd job was touched.

## Answers

### (a) Sizing the picture from content

**Decision: measure, then shoot. Add `images.measure_height(page, width, *, chrome, offline) -> int` and leave `images.screenshot` as it is.**

- `measure_height` adds a script to a private copy of the page. On `load` and `document.fonts.ready`, the script writes `.page`'s rounded-up height to an attribute on `<html>`. It runs Chrome with `--dump-dom` through the existing `run_chrome` and parses that attribute.
- `brief.render` measures, refuses if the height is over `MAX_HEIGHT` by raising `RenderError`, then calls `screenshot(page, out, WIDTH, height)`. A refusal falls back to the long text (MB11), so the picture is never clipped.
- The saved `.html` and the shot page never contain the script. This keeps the test strategy's exit criterion 7.
- The page itself becomes auto-height: remove `height: 100%` and `overflow: hidden` from `html`, `body`, `.page`, `.columns` and `.col` (`brief.py:205,207,211,212`). This also fixes MB9's page that can't scroll.

Evidence from the probes:

| Check | Result |
|---|---|
| Measured height at window height 800 and at 2400 | Identical, online and offline (for example 1392 and 1392; 1708 and 1708) |
| Shot at the measured height | Exactly that size, with the whole page and its bottom padding visible |
| Cost per Chrome run | 0.8 to 1.1 s, with the test suite running alongside |

The test strategy's note that a two-pass measure can't trust the viewport is right about the viewport: at window height 800, `innerHeight` is 713. It doesn't apply here, because an auto-height page's content height doesn't depend on the viewport.

I rejected adding up heights from counts, as `grid_size` does. That page has fixed cell heights. This one has wrapping text and two font states, so the constants would drift from the CSS and cut off silently.

**The layout must change to meet functional MB5's 1,600 px.** With functional S1's three-line Fix clamp, the worst case in the draft's layout is 1,706 px, because Decide and Fix stack in one column. Decision: put Decide and Fix side by side, with This morning below them at full width and one line per row. That measured 1,471 px online and 1,477 offline. It also matches MB3's reading order better. A verdict that wraps to two lines (functional MB1's four counts) adds 72 px, which gives about 1,550. Set `MAX_HEIGHT = 1600`.

### (b) `digest.build` for today on the read-only connection, and masking

**Safe. The masking guarantee holds today, but one route is shallow and should be tightened.**

- I read every statement in `digest.build` and all six plug-in `digest` hooks. Each is a plain `SELECT`, a config or file read, or a transcript read (`community.audit`). None calls a kind's `content()` or `preview()`. `approvals.pending` and `publish.items.latest_request` are plain reads. `audit_run_cmd` logs an event, but the hook calls `audit()`, which doesn't.
- ADR 0002 stands. A write would raise on the `mode=ro` connection. `digest.build` would catch that as "figures unavailable" (`digest.py:57`), which is why T-B2 matters.
- The cost is a second run of every hook per snapshot. That is acceptable: the reads are small, and the transcript read only happens on a Monday run day and the day after.
- `Request.reason` goes through `_clean` (`mission.py:445`). Every figure value today is an int, a bool, `None` or a top-level string, and `_digest_day` masks top-level strings (`mission.py:354`). So the new fields are masked today.
- A nested value would pass unmasked. Decision: make `_digest_day` mask recursively (N3). The test strategy already plants this case.
- Every string in `brief.html` comes from the snapshot or is static, and the page is escaped on every route (`_inline`, `escape`). The pixels can't be re-masked by `discord.post`, so the snapshot is the only gate. The test strategy's privacy sweep is the right proof.

### (c) `outreach raise-due` as a quiet command job

**It fits without any change to `runner.py` or `headless.py`.**

```python
@outreach_group.command("raise-due")
def raise_due_cmd() -> str | None:
    with db.session() as conn:
        raised = approval.raise_due(conn)
        approval.post_cards(conn)
    return f"raised {len(raised)} ..." if raised else None
```

- **Runner.** `None` leaves one `run.quiet` event and the slot reads as run (`runner.py:152-157`). A summary starts a run row with the right `started_at`. Pause and business days are checked before the command runs, and a pause leaves a `run.skipped` event, which the slot shows as skipped.
- **Quiet is right, though ADR 0001's volume argument doesn't apply to a daily job.** A daily "ok, nothing" row would reset the failure streak `check_auto_pause` reads.
- **Headless.** `permissions()` gives the job exactly `outreach raise-due`, and every claude job's rules refuse it automatically through `leaves(cli)`.
- **Raising.** `raising_problem` already covers shadow mode, pause and live problems. `raise_due` runs in `BEGIN IMMEDIATE`, and `outreach queue` already calls it without `SEND_LOCK`, so the job doesn't need that lock. Sends are still bounded at the claim.
- **SC3 needs no code.** `queue.py:197,216-218` already sets `send_after` to today and raises and posts the card. It needs only a test.
- **It will fail one guard, by design.** `tests/test_no_generic_request_command.py:31-46` lists exactly which commands may raise. Add `outreach raise-due` there, and add a line to the PRD's "Amends" saying it amends mission control A11.
- **One gap.** In live mode with a live problem, the job is silently quiet and the row reads "Ran", with no Fix line until the 09:30 `_refuse` alert. See N5.

### (d) What breaks when the jobs move

| What | Verdict |
|---|---|
| `slots.py` judging past days by today's schedule | **Breaks.** See (e) and T-B5 |
| `mission.one_pager_times`, `_last_one_pager` | Safe. They read the schedule from `Source.jobs` and the real last run. The one-hour grace still works at 09:00 |
| `ONE_PAGER_DEFAULT` (`mission.py:180`) | Used only when a job table has no `one-pager`, which means the test worlds. It causes 8 of the draft's 13 failures. The test strategy's plan to update those time values stands |
| Time-of-day logic in agents | Nothing depends on a moved job's time. A search for `.hour` in the package finds only `send.py`'s window and `schedule.py`, and the send and publish windows don't move. Social's order after app factory is kept |
| 09:00 with publish | New overlap. Functional S4's retry stands. Put it in a wrapper used only by the post path, with the sleep injected, because `/growth status` and `--no-post` should stay fast. By then `_approval_upkeep` has made an ordinary open, so a hot journal is cleared and what's left is a live lock that a retry can outlast |
| Between `git pull` and `schedule install` | Fix correctly says "out of date" and "not installed". Old-time runs land in the previous day's slot, so today's slot has no trace at 09:00. The new "Didn't run" line must not fire then: skip it when `installs[job]` is `OUT_OF_DATE` |
| Drift check on the other branch | See the conflicts section |
| Moved-time comments (SC7) | `README.md:44,87-95`, `CONTEXT.md:84`, `prompts/scout.md:1`, `config/scout.yaml:3`, `config/social.yaml:8,43`, `config/settings.yaml:53`, `run_update.py:17`, and the docstrings in `scout/cli.py:1`, `social/plan.py:1`, `social/__init__.py:3`, `community/__init__.py:3`, `apps/__init__.py:4,60`. Leave `digest.py:6` and `README.md:106`: those mean the AI OS brief. Leave publish's 09:00 |

### (e) False "missed" in the history

**Yes. Every job moved later gets one, and functional §4's "no false misses" holds only for jobs moved earlier.**

A slot owns the window from its time to the next slot. An old 08:00 run falls before the new 09:00 slot, so it counts for the previous day's slot, and the change day's slot has no trace.

The probe simulated installing on Saturday 31 October, after the old times had run that morning:

| As of | Result |
|---|---|
| Sun 1 Nov 09:01 | `one-pager`, `app-factory` and `social` each missed Sat 31 Oct. `community` Mon 26 Oct reads "due" |
| Mon 2 Nov 09:01 | The same three, and `community` Mon 26 Oct is now missed |
| Tue 3 Nov 09:01 | All four still in the 14 days |

`_missed` looks back to the previous business day. So Fix carries three false lines on Sunday and Monday, and the first pictures after the change say "3 to fix". The grid keeps all four for 14 days. `scout-research` moved earlier and is clean. The other branch's digest move to 18:05 will produce the same false line.

**Decision: don't judge a slot from before the job's plist was last installed.** The fix is T-B5. The other past days stay correct but shifted: for a job moved later, each old run shows on the day before it ran. That only shows in `--grid`, and it ages out within 14 days, so leave it.

## Blocking

**T-B1. The page cuts off Fix (MB5).** `brief.py:35,205,207,212,331`. On a day with 4 requests shown and 5 fixes, the probe's picture shows the "Fix 5" heading and none of its rows. Also, `--window-size=1200,1120` lays out at a shorter viewport in the measure pass, so `height: 100%` can't be relied on. Fix: (a) above.

**T-B2. Guessed zeros and false "Not today" (MB7).** Same finding as functional B2, confirmed.

- `brief.py:84,89,93,97,189-191` use `figures.get(key, 0)`. A hook that raised, or a `morning` of `None`, prints 0.
- `brief.py:143,148-149` read empty `snapshot.slots` as "Not today".
- `brief.py:302` says "Nothing else scheduled" in the same state.

Fix: one helper returns a dash for a missing key. `agent_rows` and `later_today` check `snapshot.slots` first and say "Not available".

**T-B3. A passed slot reads "Due" all day (MB6).** `brief.py:156-157`. `slots.py:243` keeps `due` until the next slot, which is right for the classifier, so keep that. `brief._row` takes `now` and reads a `due` slot more than 5 minutes old as "Didn't run", as functional MB6 words it. `brief.py:149` also says it twice; drop the second line.

**T-B4. Pictures are never pruned (MB9).** `backup.py:39` matches only `grid-*.png`, so `brief-*.png` and `brief-*.html`, which hold approval reasons, stay forever. Fix: prune every dated picture file by name and date. Keep the event's `grids_pruned` key so `tests/test_one_pager_post.py:223` still reads it, or add a sibling key. Update the comment at `config/settings.yaml:53`.

**T-B5. False "missed" after the move (ticket 02).** `slots.py:239-247`.

- Add `schedule.installed_at(job) -> datetime | None`: the plist's modified time in `launch_agents_dir()`, the file `install` writes (`schedule.py:162`).
- Add `Source.installed_at`, defaulting to `lambda job: None`. Only `Source.here()` passes the real one, so existing worlds don't change.
- Add `slots.classify(..., installed_at=...)`. In `_Job._status`, after the `self.first` check, a slot with no trace before that moment is `"not installed"`.

It adds no new status, about 15 lines, and no database read. Because the status isn't `due`, the "Didn't run" line is covered too. Running `schedule install` for any reason also clears true misses from before it; I accept that because installs are rare and deliberate.

I rejected a dated schedule history in config, because the install date isn't known at merge, and a release note saying the lines are false, because the first picture would be wrong.

## Non-blocking

- **N1. Rename now.** `brief.py`, `brief_png` and `brief-<day>.png` collide with the AI OS Morning Brief and with `digest.py`'s `brief` and `brief_line`. Crew's log and functional S5 already chose "morning picture". Rename to `picture.py`, `picture_png`, `picture-<day>.png` and `one_pager.picture_failed`, while nothing depends on them. The functional and test-strategy reviews would then read with the new names.
- **N2. `one_pager.py:51` reaches through `brief.cards.label`.** Import `cards` directly.
- **N3. Mask figures recursively** at `mission.py:354`.
- **N4. Tile captions run together** at `brief.py:234`: "emails sent replies posts published". Add a gap. The "posts published" tile reads `social_published`, which excludes community posts, so caption it "social posts".
- **N5. Say when live raising is blocked.** Add an `outreach.health(conn)` hook that returns one Fix line when mode is live and `send.live_problems()` isn't empty, so the 09:00 picture says what the 09:30 alert would.
- **N6. Say the ICP in plain words (SC6).** `icp.missing_reason()` holds absolute paths, so don't reuse it for the Fix line. Word it with the action first and name `inputs/icp.md`. Scout's precheck can keep its own wording. `health()` will add a line to every `mission.read` world without the file, because `JURA_INPUTS_DIR` is a temp folder. Tests that assert exact `plugin_lines` should filter by content, as the current ones do.
- **N7. Keep `brief.AGENTS` in the core.** It names jobs and figure keys but imports no agent, like `one_pager.COUNTED_JOBS`. A plug-in hook with one caller would be speculative. All 7 registered kinds map to a row today. The test strategy's risk 5 keeps that true.
- **N8. Sibling reviews.** Functional §4's "Data from before the change" line is replaced by (e). New tests for T-B5 go in a new file, so the test strategy's exit criterion 6 (`test_mission_slots.py` unchanged) still holds. Its fixture list gains the three-line Fix and the layout above.

## Seams

"Seam" here means where a test holds the code still, named at the highest level available. Ticket 01 adds one new seam. Ticket 02 adds none: it extends one parameter on an existing seam.

**Ticket 01, the picture**

| Seam | Status | Covers |
|---|---|---|
| `brief.*` and `one_pager.summary()` on a built `Snapshot` | New module, same shape as `one_pager.text` | Verdict, order, dashes, MB6 table, wording |
| `mission.read(source)` | Existing | `morning`, `reason`, masking, read-only (spies on `content`, `preview`) |
| `one_pager.post(conn, snapshot)` through the Discord double | Existing | One PNG, fallback, `--grid`, `--no-post`, pruning through `backup` |
| `images.measure_height` and `brief.render` in real Chrome | **New, the one seam** | Height follows content, never over the maximum, PNG equals measure |

`tests/brief_chrome.py` can use `measure_height` for its oracle. Real Chrome is already in the suite (`needs_chrome`).

**Ticket 02, the morning order**

| Seam | Status | Covers |
|---|---|---|
| `runner.run("outreach-requests", ignore_schedule=True)` | Existing | SC2: quiet trace, summary, shadow, pause, no Resend call |
| `config.settings()["jobs"]` | Existing | SC1, SC4, SC5 |
| `slots.classify(..., installed_at=...)` on pure records | Existing, one new parameter | T-B5: the probe's table becomes the test |
| `mission.read` with a fake `installed_at` | Existing | The rule reaches Fix |
| `queue` through `test_outreach_cards.py` | Existing | SC3 |
| `mission.read` with a temp inputs folder | Existing | SC6, through scout's `health()` |
| `test_no_generic_request_command.py` | Existing guard | The new raiser is declared |

## Blast radius

- **Ticket 01:** `brief.py` (new), `one_pager.py`, `mission.py` (`Snapshot.morning`, `Yesterday.figures`, `Request.reason`, the lock retry wrapper), `health.py` (short wording), `images.py` (`measure_height`), `backup.py`, `cli.py`, `outreach/__init__.py` (reply detection figure, functional B2; N5), `social/__init__.py` only if a new figure is needed for the "to post by hand" count, `CONTEXT.md`.
- **Ticket 02:** `config/settings.yaml`, `outreach/cli.py`, `scout/__init__.py` (`health`), `schedule.py`, `slots.py`, `mission.py` (`Source.installed_at`), the doc lines in (d), `tests/test_no_generic_request_command.py`.
- **Schema and data:** no migration. New `run.quiet` events have ADR 0001's existing shape. New files in `data/growth/one-pager/`.
- **APIs:** no external change. `--grid` is new. The post carries a different PNG.
- **Wide refactor:** none, so no expand and contract is needed.

## ADRs

**None needed.** ADR 0002 holds. The `installed_at` rule is surprising and is a real trade-off, but it is easy to reverse, so it fails the three-part test. Write it in `slots.py`'s module docstring, in "The rules" list, where a reader will look.

`CONTEXT.md`: add "Morning picture", update "One-pager" (no grid, 09:00), and note that "Fix" is the picture's name for the health strip. Mission control A11 is amended in the PRD, not in an ADR.

## Prefactoring and order

No prefactor ticket is needed; each change is small enough to sit inside its ticket.

- **Ticket 01:** `measure_height` and the auto-height page first, because every overflow test needs them. Then T-B2, T-B3, T-B4.
- **Ticket 02:** T-B5 before the settings change, so the suite never holds a schedule that produces false misses. Then the command, the job, SC6, and the doc lines last.
- `brief.py:114` already names `outreach-requests`. Until ticket 02 lands, the Outreach row reads "Not today" on live data. Both tickets ship in one PR, so that never reaches production.

## Conflicts with `crew/approvals-first-social-depth`

An in-memory trial merge of the two branches (`git merge-tree --write-tree`) conflicts in two files only.

| File | Hunks | Resolve by |
|---|---|---|
| `mission.py` | 1: both add a `Snapshot` field after `spend_today` | Keep both |
| `health.py` | 2: `items += _missed(...)` next to their drift line; `_gap_lines` and `def _missed` next to their `Drift` block | Keep both |

`settings.yaml` doesn't conflict yet, because that branch hasn't changed it. Its ticket 02 will change only the `digest` schedule line. `config/social.yaml` has heavy edits there, but the two comment lines in SC7 sit outside its hunks.

**To keep it small:**

1. **Merge the other branch first,** as functional S2 decided, and rebase this one once it lands. It carries the drift line this PRD relies on.
2. **Move `_gap_lines` to the end of `health.py`,** and add a `_missed_counts(snapshot)` there instead of changing `_missed`'s signature. Only the one `items +=` line then conflicts, which removes the second hunk.
3. **Add `outreach-requests` after `scout-sync` in `settings.yaml`.** Keep `one-pager` straight after `digest`, because `tests/test_one_pager_post.py:83-85` asserts that order. Change only the schedule value on the moved jobs.

**Behaviour to fix when both are in, not caught by git:**

- **`Drift.line` will lose its instruction on the picture.** It is about 240 characters with "restart the Mac once" at the end, and the three-line clamp holds about 114. Add a short wording with the action first for `strip(short)`.
- **The drift check can give a false alarm after the move.** `app-factory` and `social` both moved by 30 minutes, which meets `DRIFT_MINIMUM`, and that branch's B7 uses the largest agreeing group. Between the pull and their next on-time run, it can say "0.5 hours off". Fix: `schedule_drift` ignores runs from before `installed_at`. Whichever branch lands second makes this change.
- **The digest's move to 18:05 needs T-B5** for the same reason as (e). It works unchanged once T-B5 is in.

## Risks

| Risk | Mitigation |
|---|---|
| **Discord may also limit inline height.** From memory, not verified: desktop may cap inline height, around 350 px. A 1200×1000 picture would then show well under 550 px wide, and MB2's arithmetic fails. No test can reach Discord | Keep typical days compact; the layout above helps. MB10's message stands alone on a phone. UAT U1 checks it on the first post. If it shrinks, the follow-up is to lower `MAX_HEIGHT` and the caps |
| **Fonts differ between the two passes.** A Google Fonts fetch could fail in one Chrome run only. Heights differ by about 6 px between font states, more if a Fix item wraps differently | Low likelihood. The bottom padding of 44 px absorbs the small case. The fallback font still reads |
| **Lock at 09:00 with publish** | The retry in (d) |
| **Clock drift until the Mac restarts.** 09:00 posts at midnight, and this morning's rows read as due | Already Ting Yu's step in the PRD. The other branch's check reports it |
| **Chrome at 09:00 beside publish** | `run_chrome` uses a throwaway profile, so it doesn't touch the publishing profile |
| **Personal data in the `.html`** | Masked snapshot, pruned after 14 days (T-B4), kept in `data/` |
| **Performance** | About 2 s of Chrome per post, a second digest build. No concern |

## Evidence

- `uv run pytest -q -p no:cacheprovider -o addopts=""` on the draft: 13 failed, 3969 passed. The failures match the test strategy's list.
- `digest.build` for today on `mission.open_read_only`, on a temp migrated database holding a community run: no "unavailable" line, and figure values of `int`, `str` and `None` only. That database had no plug-in rows beyond that run, so the hook bodies were also read by hand.
- Probe scripts, not part of the repo: `probe_size.py`, `probe_worst.py`, `probe_slots.py` in `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/2e83ea48-1f12-40ea-9c1c-3041ffd846ed/scratchpad/`.
- No source file changed in this review.
