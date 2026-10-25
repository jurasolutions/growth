# Ticket review: mission control and browser publishing (tech lead)

Tech lead, 2026-10-25. This covers the 16 mission-control tickets (`.scratch/mission-control/issues/01` to
`16`) and the 6 browser-publishing tickets (`.scratch/browser-publishing/issues/01` to `06`). I read them
against both signed-off PRDs (MC §4.6, §5.3, §5.12; BP §5.4 to §5.12), my `reviews/technical-v2.md`,
`reviews/test-strategy-v3.md`, and the code on `crew/growth-blocker-fixes` at `0ad538e`.

## Verdict

**Changes needed, then approve.** The breakdown has the right shape: vertical slices, the PRD's edges,
prefactors first, human steps split out. Twelve changes are needed before G3 (T1 to T12). Ten are ticket
edits the project manager can make from this file. One is a step for the conductor before the first
worktree (T11). One is a question for Ting Yu at G3 (the shared integration branch, T11). None changes
scope.

The four main problems:

- Ticket 04 is too big for one context window, and so are 10 and browser-publishing 02 (T1, T8, T9).
- The approval seam has no hook for kinds whose change is applied when the decision is made
  (`group-rules`, `app-build`), so 05 and 10 would each invent one in `approvals.py` (T2).
- The runner hook as written in 01 can't see skips or the lock skip that 03 must report. It also can't
  let the publish audit fail a run, and quiet `claude` jobs run with no run id (T3).
- The four either-order pairs rely on "the second to land". That can't be briefed in advance and is
  easy to drop. All four become ordinary edges, and those edges don't lengthen the critical path (T4).

## Evidence

- `uv run pytest -rs -p no:cacheprovider` on `crew/growth-blocker-fixes` at `0ad538e` printed **987 passed
  in 22.32s**. `git status --short` was the same before and after the run (diffed through the
  scratchpad).
- `runner.py`:
  - `run()` returns on the PAUSE file and on the lock skip before any connection or hook.
  - `_run_locked` returns on every skip before `finish_run`.
  - `run_id = None if quiet else log.start_run(...)` means a quiet `claude` job would get
    `JURA_GROWTH_RUN_ID="None"` and a `None-<job>.jsonl` transcript.
- `headless.may_use` checks `command.split()[0] in NEVER`. A two-word entry such as `publish resolve`
  can never match.
- `jura_growth/*.py` contains no `jura_growth.agents.` import. The one-pager PNG ticket (09) routes
  through `agents/social/render.py`, which would be the first.
- `paths.site_repo()` (`JURA_SITE_REPO`) already exists, and `tests/conftest.py` already points it at
  `tmp_path/site`.
- `CONTEXT.md`, `docs/adr/` and both feature folders are untracked on this branch. Worktrees created from
  a future `crew/mission-control` won't contain them.
- `discord.post()` already takes `suppress_embeds`, so 03 doesn't need to change `discord.py`.

## Blocking changes

### T1. Split 04 into the core and the Terminal decisions

04 holds the migration and trigger, all of `approvals.py`, both halves of `origin.py`, three CLI
commands, card posting and in-place edits, the posting sweep, the heartbeat and backup lapses, the UAT
seed, the gate-matrix harness and 24 criteria. That doesn't fit one context window. The checkpoint the
ticket already names is the natural seam.

- **Keep `issues/04-approvals-core.md` as MC-04a, the core.** Its contents:
  - `0003_approvals.sql` with the trigger and both indexes;
  - `approvals.py`: `request`, `decide` (taking an injected `Origin`), `use`, `expire_due`, `pending`,
    `get` and `raised_by(conn, run_id)`, which 03 needs;
  - the `ApprovalKind` protocol with T2's `on_approve`;
  - the `Origin` value type in `origin.py` (the type only, no detection);
  - the fake kind, the gate-matrix harness (T7) and ADR 0003.

  It traces AC-M4.1 to AC-M4.7, AC-M6.1 (through `decide()`), AC-M6.2, AC-M6.3, AC-M6.4 (the record),
  AC-M7.6 and the core matrix cases. `Blocked by: 01, 02`.
- **Add `issues/04b-terminal-decisions-and-cards.md` as MC-04b.** Its contents:
  - `origin.detect()`, the real check (TTYs, the typed code, `SSH_ORIGINAL_COMMAND`, `ps` ancestry);
  - the CLI commands `approvals`, `approve` and `skip`, with `--ref`, the answer enum and the
    `JURA_GROWTH_JOB` refusal;
  - in `discord.py`: `?wait=true`, stored message ids, `edit()`, the one-line follow-up and the
    `approvals` channel;
  - `post_unposted()`, plus the heartbeat and backup lapses;
  - the `approvals:` settings block (T10) and `tests/uat/seed.py`.

  It traces AC-M5.2 to AC-M5.5 (AC-M5.4 from Terminal), AC-M7.1 (the code refusal for three commands),
  AC-M7.2 to AC-M7.4, AC-M7.7, and the sweeps over cards. `Blocked by: 04`. `Status: ready-for-agent`.
- **Origin plumbing for 11.** In 04b, `approve` and `skip` take their `Origin` from `origin.detect()`
  unless the in-process click context carries one (`ctx.obj["origin"]`), which only the `remote`
  dispatcher in 11 sets. There is no flag and no environment variable for it (test strategy §1 and
  E6).
- **Re-point the edges.**
  - 04a only: 03, 07 (already on 01), 08.
  - 04b: 05, 06, 10, 11, 13, browser-publishing#02.
- The `04b` file name bends the numbered-from-01 convention so that every existing `mission-control#04`
  reference stays valid. `04-…` still sorts before `04b-…`.

### T2. Add `on_approve` to the kind protocol (04a)

`group-rules` is "applied on decide" (MC §5.7). The `app-build` handoff "claims the approval and writes
the `handed_off` row in one transaction" on approve (MC §5.9). The test strategy agrees ("the handoff on
approve"; "group-rules … applies the change in the decide transaction"). The protocol in MC §4.6 has
`on_skip`, `on_expire` and `on_lapse`, but nothing that runs on approve. If 05 and 10, which run in
parallel, each add their own, they collide in `approvals.py`.

- In 04a, add `on_approve(self, conn, subject, args: dict[str, str]) -> str | None` as an optional
  member with a no-op default. `decide()` calls it inside the decision's `BEGIN IMMEDIATE` transaction,
  after it writes `approved`. It may raise `approvals.BadArgs(text)`. The answer is then `refused` with
  that text, and nothing is recorded. Any returned string is appended to the answer text (the
  "Build it: …" line).
- `decide()` refuses with `BadArgs` when any of the kind's `decision_args` is missing. 05 supplies the
  text "say the days: promo_days=… post_days=…".
- 04a's fake kind declares `decision_args = ("promo_days", "post_days")` and an `on_approve` that
  records its call, so 11 can test the remote grammar without the real kind.
- The business analyst adds `on_approve` to the MC §4.6 code block as a clarification. Nothing in the
  contract changes.

### T3. Fix the runner hook shape in 01, and answer QA Q1

As written ("called after `finish_run`"), the hook can't deliver 03's AC-M3.2 (a pause-flag skip
returns before `finish_run`) or AC-M3.4 (the lock skip happens in `run()` before any connection). It
also can't let BP-03's audit fail the run (AC-P9.3), because the run row and auto-pause are already
written by then. Replace 01's hook bullet with these:

- **Plug-in `after_run(conn, job, run_id, outcome) -> Outcome | None`.** Called in `_run_locked` after
  the job body and **before** `finish_run`, only for runs that actually started. A returned `Outcome`
  replaces the original, so the run row, `#alerts` and `check_auto_pause` all see the final status. An
  exception is logged as a `run.after_run_error` event and the original outcome stands (the hook half
  of AC-M3.6).
- **Core run-update notification.** 01 adds `jura_growth/run_update.py` holding
  `after_run(conn | None, job, spec, run_id, outcome) -> None`, which does nothing yet. The runner calls
  it once on every path except the PAUSE file:
  - a pause-flag, schedule or precheck skip;
  - a quiet run with nothing to do;
  - a finished run, after `finish_run`, the alert and auto-pause;
  - the lock skip, with `conn=None`, so the database is never opened.

  It is wrapped like the plug-in hook. 03 then fills in `run_update.py` and doesn't touch `runner.py`,
  so the file still changes only in 01 and browser-publishing#03.
- **A quiet `claude` job still gets its run row before Claude starts.** It spends money, and it needs a
  run id for `used_by_run`, the transcript name and the claim gap in AC-P5.1 line 6. `quiet` keeps its
  meaning only for `command` jobs.
- **Q1, settled: `run.quiet`.** `agents/__init__.py` gains `class NothingToDo(str)`. When a precheck
  returns a `NothingToDo`, the runner writes `run.quiet {"job", "started_at", "reason"}`, never
  `run.skipped`, whatever the job's `quiet` flag. Any other string stays a skip as today. In the
  publish job, "nothing due" returns `NothingToDo`, and the auth-variable skip returns a plain string,
  because that skip is a problem Ting Yu should see. The classifier (07) then needs no special case for
  publish. ADR 0001 gains one sentence about prechecks.
- **01's new criteria.** The notification runs exactly once per path above and never for the PAUSE file.
  A plug-in `after_run` that returns a failed `Outcome` is what the run row, the alert and auto-pause
  record. A quiet `claude` job's transcript and environment carry a real run id. A `NothingToDo`
  precheck writes one `run.quiet` and no run row.

### T4. Turn the four either-order pairs into edges

"The second to land carries the shared test" can't be briefed in advance. Both developers branch
before either lands, and the status file already lists dropping the test as a risk. Each pair becomes
an edge, and none of them lengthens the critical path (see "Build order").

| Pair | Edge to add | Owner of the shared test | Why the edge is free |
|---|---|---|---|
| 03 / 04 | 03 `Blocked by: 01, 02, 04` | 03 owns the "Waiting for you" line, using `approvals.raised_by()` and the fake kind | 03 feeds only 13 and browser-publishing#03, and both wait for later tickets |
| 05 / 11 | 05 `Blocked by: 04b, 11` | 05 owns AC-M10.6 from Terminal and through `jura-growth remote` | 05 feeds only browser-publishing#05 and #06, which wait for #03, which waits for 11 anyway |
| 08 / 10 | 10 `Blocked by: 04b, 08` | 10 owns the one-pager's "build handoffs waiting for a builder" line, through 08's plug-in `health()` hook (T5) | 10 feeds 10b, 12 and 16, and 16 waits for Dispatch D6 |
| 09 / 11 | 09 `Blocked by: 08, 11` | 09 puts `one-pager` on the remote allowlist and owns AC-M1.6 through `remote` | 09 and 11 both sit one step after 04b and 08; 13 waits for 09 either way |

Delete every "Order-independent with …" paragraph from tickets 03, 04, 05, 08, 09, 10 and 11, and add
the owner's line instead. Ticket 11 drops AC-M1.6 and the AC-M10.6 remote half from its notes. It keeps
the remote grammar test for `key=value` decision arguments, using the fake kind from T2.

### T5. Give 08 the plug-in hooks that 10 and browser-publishing#03 need, and add the missing edge

- 08 defines two optional plug-in hooks, documented in `agents/__init__.py`:
  - `setup_gaps() -> list[Gap]`, with names and booleans only, read by `health.setup_gaps()` and
    therefore by `jura-growth status`;
  - `health(conn) -> list[str]`, extra "Needs you" lines, called with the read-only connection, so a
    write raises.

  The ticket's "required settings as a module attribute" becomes a `REQUIRED_SETTINGS` shorthand that
  the default `setup_gaps()` reads.
- 08's read model reads `approvals` rows with its own `SELECT`s (stored status, deadlines, `posted_at`,
  `decided_origin`). It never calls `approvals.py` functions or a kind's `content()`, because they may
  supersede, which is a write. AC-M1.3 and AC-M1.4 seed rows with the kind names `outreach-email` and
  `social-post`; the read model never imports a kind.
- **browser-publishing#03 gains `Blocked by: mission-control#08`.** AC-P9.5 says `jura-growth status`
  lists the auth variable as a setup gap. That needs 08's `setup_gaps()` hook, through
  `setup_gaps()` in the publish plug-in. The edge is free: 08 lands two steps before #03 can start.

### T6. 09 must not import the social agent from the core

09 says the PNG goes "through the existing `agents/social/render.py` headless Chrome helper". The core
never imports an agent by name (`agents/__init__.py`), and test strategy E6 greps `one_pager.py` for
`jura_growth.agents.`. Add this to 09's "What to change": move `design_system()`, `chrome_path()`,
`_chrome()`, `screenshot()` and `png_size()` into core `jura_growth/images.py`, with the Chrome path
passed in explicitly. `agents/social/render.py` then calls the core helper, as an expand and contract
inside 09. `tests/test_social_render.py` must pass unchanged.

### T7. One owner per shared test file

05, 06, 10 and browser-publishing#02 run in parallel, and each "adds its adapter" to
`tests/test_approval_gates.py`. Several tickets also "extend 02's sweep". Edits to one parametrize list
from parallel branches will conflict, and nobody owns the merged result. Make these edits:

- **04a:** `tests/test_approval_gates.py` is the harness, owned by 04a alone. It collects adapters from
  every `tests/gate_adapter_*.py` module through `pytest_generate_tests`. 04a ships
  `gate_adapter_fake.py`.
- **05, 06, 10, 10b, browser-publishing#02 and #02b:** each adds only its own
  `tests/gate_adapter_<kind>.py`, with kind-specific builders in that file. `tests/approval_world.py`
  holds only the core and fake-kind builders.
- **02:** the sweep is a function in `tests/sweep.py` (`assert_clean(double, outbox, planted)`). The
  Discord double lives in `tests/discord_double.py`. Neither goes in `conftest.py` (see T12). Each
  later ticket calls the sweep from its own test file and never edits a shared list.

### T8. Split browser-publishing#02, and give `pages-not-allowed` one owner

**The split.** #02 holds a new plug-in, two migrations, three kinds, item creation from three commands,
five commands, six caps, a config expand and contract, `after_run`, digest counts and about 25
criteria. That is more than one context window. Its own checkpoint, "social path first", is the seam.

- **Keep `02-publish-queue-no-browser.md` as BP-02a, social posts.** Its contents:
  - the `publish` plug-in and the `publish_items` migration;
  - the `social-post` kind and item creation from `social submit`;
  - `publish next`, `done --url`, `stopped`, `queue` and `resolve`;
  - all six caps constants, `publish_mode` `draft` or `browser`, and `config/publish.yaml`;
  - `after_run` settling an `unknown` claim, and the digest counts (QA Q5);
  - `publish resolve` in `NEVER`, as N7 below describes;
  - `docs/social.md` and `tests/gate_adapter_social_post.py`.

  It traces AC-P1.1 to AC-P1.4, AC-P2.1 to AC-P2.3, AC-P3.1 to AC-P3.3, AC-P5.1 lines 1, 6, 7 and 11,
  AC-P5.2 to AC-P5.4 (the social switches), AC-P6.1, AC-P6.3, AC-P7.1 to AC-P7.3, AC-P8.3, AC-P10.1,
  AC-P10.2 and the race test. `Blocked by: mission-control#01, mission-control#04b`.
- **Lay out the plug-in by module.** The claim checks go in `agents/publish/claim.py` and expose
  `claimable(conn, now)`, which #03's read-only precheck reuses. The job hooks go in
  `agents/publish/job.py`, which #03 fills in. The browser-publishing kinds are declared by the publish
  plug-in; the community plug-in declares only `group-rules`.
- **Add `02b-community-items.md` as BP-02b.** Its contents:
  - the `community_groups` migration (`joined_as`, `pages_allowed`, `join_status`), as the community
    plug-in's next migration number;
  - the `community-post` and `group-join` kinds, including the answers step;
  - item creation from `community publish-plan` and `community propose-join`;
  - the community checks in `claim.py` and `community.browser: false`;
  - two gate adapters.

  It traces AC-P3.4, AC-P5.1 lines 2 to 5 and 8 to 10, and the community switch in AC-P5.3.
  `Blocked by: 02`. It runs in parallel with #03, which needs only #02a.

**One owner for `pages-not-allowed`.** #05 (composer) and #06 (join screen) both implement
`publish done --outcome pages-not-allowed` and its group effects: `pages_allowed = no`, `fit = skip`,
every pending item superseded. They would build the same handler twice in parallel.

- **#06 owns the handler for every item kind**, plus its AC-P4.3 join-screen half.
- **#05 adds only the composer branch** of the prompt and its test, and gains
  `Blocked by: 03, 06, mission-control#05`.

This also matches the live order: a group has to be joined as the Page (#06) before a post can go in as
the Page (#05, AC-P5.1 line 10). #06 gains `Blocked by: 03, 02b, mission-control#05`. Update the
browser-publishing status file's "05 and 06 run in parallel" line.

### T9. Split 10 into the build and the release

10 is two tracer bullets: idea to handoff, then preview to release. It has two kinds, a migration, four
commands, file moves, a one-off pass, a prompt change and 11 criteria, against `apps/prd.py` (803
lines).

- **Keep `10-app-factory-kinds.md` as MC-10, idea to handoff.** Its contents:
  - the `app-build` kind with its `on_approve` handoff (T2), and the `app_builds` migration;
  - `submit-prd` raising the request, and `apps handoffs [--json]`;
  - skip and expire moving the PRD to `prd/skipped/apps/`, and the waiting pile;
  - the one-off pass, the prompt and docs change, and the plug-in `health()` line (T4, T5);
  - the `approvals.dispatch_builds` behaviour (Q6) and `gate_adapter_app_build.py`.

  It traces AC-M9.1 to AC-M9.6, AC-M9.10 and AC-M9.11.
- **Add `10b-app-release.md` as MC-10b.** Its contents:
  - `apps built`, the `app-release` kind, `apps release-plan` and `apps released`, with the SHA check
    against `paths.site_repo()` (Q7);
  - `prd/done/apps/` with the sign-off line;
  - `gate_adapter_app_release.py`.

  It traces AC-M9.7 to AC-M9.9. `Blocked by: 10`.
- 12 becomes `Blocked by: 11, 10b`.

### T10. One owner for the `approvals:` settings, and a separate switch for buttons

06 reads `approvals.discord_buttons`, 10 needs `approvals.dispatch_builds` (Q6), and 11 adds a
`components` payload that is "off until D5". No ticket creates the block, and 06, 10 and 11 run in
parallel. There is also a circular dependency:

- ticket 15 checks the buttons (U17) before Ting Yu sets `discord_buttons: true`;
- but buttons can appear only if growth sends `components`;
- and a webhook that Dispatch doesn't own rejects `components` (technical-v2 N6).

The fix:

- **04b** adds this block to `config/settings.yaml`. 06, 10 and 11 only read it.

  ```yaml
  approvals:
    discord_buttons: false   # buttons checked by Ting Yu (U17); unlocks live outreach (06)
    post_buttons: false      # send Approve/Skip components on cards (11); needs Dispatch's own webhook
    dispatch_builds: false   # Dispatch D6 polls handoffs (10)
  ```

  The deadline settings go in the same block; each may only shorten a deadline.
- **11** sends `components` only when `post_buttons: true`. Cards for `group-rules` never get them.
- **Ticket 15**, steps:
  1. Store Dispatch's own webhook as `DISCORD_WEBHOOK_APPROVALS`.
  2. Set `approvals.post_buttons: true`.
  3. Run U17.
  4. Only then set `discord_buttons: true`, then `outreach.mode: live`.
- The QA lead's E14 stays as written.

### T11. Before the first worktree: commit the shared files, and one integration branch

**Commit the shared files first.** `CONTEXT.md`, `docs/adr/0001` to `0005`,
`.scratch/mission-control/` and `.scratch/browser-publishing/` are untracked. A worktree made from
`crew/mission-control` won't have them, so 01 can't "move ADR 0001 to accepted", and no developer can
read their ticket. After the blocker-fix PR merges, the conductor's first commit on
`crew/mission-control` adds all four paths. That commit comes before any worktree. Add this as the
first line of "Precondition" in both status files.

**One integration branch (question for Ting Yu at G3).** Five of the six browser-publishing tickets need
mission-control code (#02a needs MC-01 and 04b; #03 needs 03, 08 and 11; #05 and #06 need 05). A
separate `crew/browser-publishing` from `main` would have to wait for mission control's whole G4, and
a branch stacked on `crew/mission-control` would have to be rebased forward at every merge.

*Recommended:* build both features on `crew/mission-control`, with ticket branches
`crew/mission-control-NN` and `crew/mission-control-bpNN`. At G4 you still choose what ships: one PR, or
two PRs cut at a merge point. Nothing in browser publishing posts anything until you set a platform to
`browser` and reinstall the schedule.

### T12. The network guard belongs in 01 (QA Q2, settled)

01 and 02 run in parallel. 02 lists the network guard in its contents, while 01's AC-M15.1 already
relies on it. Move the network guard and its self-test into 01's "What to change", as a second session
audit hook in `tests/conftest.py`. Delete it from 02. 01 is then the only ticket in the first wave
that touches `conftest.py`. 02's AC-M15.1 note becomes: "the network-guard clause applies from 01's
merge on."

## Non-blocking edits

- **N1. Pointers and baseline.**
  - Every ticket: replace `reviews/test-strategy-v2.md` and its retired row ids (MC3a, BP7d and so on)
    with `reviews/test-strategy-v3.md`: its §4 rows by AC id, its §5 cases by G number, and the
    ticket's row in §11.2.
  - 01: "above the 975 baseline" becomes "above the 987 baseline".
  - Tickets 13 to 16: U-step pointers become v3 §7.
- **N2. Ticket 01.**
  - `outreach.live_problems()` is `send.live_problems()` in `agents/outreach/send.py`.
  - The generated `may_use` test also asserts that each command job's command resolves to a real CLI
    leaf (`headless.command_name` is not empty).
- **N3. Manual step ids.**
  - 14 gains U16 (the real SSH forced command, v3 §7).
  - 15 labels its button check U17.
  - Browser-publishing#01 labels its subdomain check U18, which E1 and E13 grep for.
- **N4. Setup guides outside the repo.**
  - Tickets 09 and 11 and browser-publishing#01 write to the live `jurasolutions/outputs/growth/setup/`
    from a worktree. That bypasses review and rollback.
  - *Recommended:* draft each guide as `.scratch/<feature>/setup/<name>.md` in the ticket. The release
    persona copies it to `outputs/growth/setup/` after the merge. The QA lead points E6's "returns a
    hit" checks at the draft until release.
- **N5. Ticket 06.** Drop "(subject to §6 Q2)" from AC-M12.2's line. Ting Yu accepted Q2 at G2.
- **N6. Ticket 04a.** *Recommended:* `expire_due()` also recomputes content for live records of loaded
  kinds and supersedes the ones that changed or are gone (no re-raise; A15 still leaves unknown kinds
  alone). That way the one-pager job's pre-build step catches stale requests, which the read model
  can't.
- **N7. Browser-publishing#02a.** `publish resolve` in `NEVER` needs `may_use` and `claude_rules` to match
  `NEVER` entries as a leading run of command words, not only `split()[0]`. #02a owns that change in
  `headless.py` and its test. 01's generated test keeps passing.
- **N8. Anchors for parallel edits.** These avoid same-hunk conflicts; each behaviour keeps its own test:
  - **`config/settings.yaml`:** the `one-pager` job goes directly after `digest` (09), the `publish` job
    directly after `community` (browser-publishing#03), and the `approvals:` block after `channels:`
    (04b).
  - **Plug-in `__init__.py` files:** `REQUIRED_SETTINGS` sits beside `NAME` (08), and `run_update()`
    goes after `digest()` (03).
  - **The allowlist in `remote.py`:** sorted by command, one entry per line (11). The tickets that add
    entries later are 09, 12 and browser-publishing#03. Rows in `docs/dispatch-contract.md` are kept
    in the same order.
  - **`prompts/publish.md`:** browser-publishing#03 writes one heading per item kind and platform, with
    the ones not yet enabled marked as such. #04, #05 and #06 each fill only their own section.
- **N9. Ticket 05** adds no community migration; it records existing confirmations with a one-off,
  idempotent pass in code. Browser-publishing#02b takes the next community migration number.
- **N10. Ticket 16** gains a step: once Dispatch polls `apps handoffs --json`, set
  `approvals.dispatch_builds: true`. 13 becomes `Blocked by: 03, 04b, 09`.

## Seams, checked against technical-v2

The breakdown keeps **one new seam**, the `approvals` interface. Every other change extends the
existing plug-in protocol or adds an adapter that technical-v2 already named.

| Seam or adapter | technical-v2 | Owning ticket | Change from this review |
|---|---|---|---|
| `approvals` interface (request, decide, use, expire_due, post_unposted, pending, get) | new seam | 04a (core), 04b (`post_unposted` and cards) | `on_approve` and `BadArgs` (T2); `raised_by()` for 03 |
| Plug-in protocol: `approval_kinds()`, `run_update()`, `after_run()` | extended | 01 (docstring and call sites), 03, 04a, browser-publishing#02a and #03 | `after_run` runs before `finish_run` and may return an `Outcome`; `NothingToDo` (T3) |
| Plug-in protocol: `setup_gaps()`, `health()` | implied by "plug-ins declare settings" | 08 | Named as hooks (T5) |
| Read model `mission.py` | carried | 08 | Reads rows only, never a kind (T5) |
| `origin.py` adapter | adapter | 04a (type), 04b (detection) | The click-context origin for `remote` (T1) |
| `jura-growth remote` adapter | adapter | 11, then 05, 09, 12 and browser-publishing#03 for rows | Sorted allowlist (N8) |
| Fake `claude` binary | adapter | 04b (AC-M7.7), browser-publishing#03 | none |
| Core Chrome render helper | not named | 09 | Moved out of the social agent (T6) |

## Answers to test strategy v3 §12

Questions addressed to me:

- **Q1** (what `publish`'s precheck "nothing due" writes): `run.quiet` with `started_at` and `reason`.
  The precheck returns `agents.NothingToDo`, and the runner change lands in 01 (T3). AC-M2.1's publish
  row seeds `run.quiet` events, and AC-P8.2's "quiet skip" means that event. The auth-variable precheck
  stays a `run.skipped`.
- **Q6** (`approvals.dispatch_builds`): yes, default `false`, created by 04b (T10) and read by 10.
  - With `false`, the decision answer and the one-pager carry the "Build it: …" line.
  - With `true`, the answer says the build was handed to Dispatch. The one-pager still lists open
    handoffs, without the "Build it" text.
  - Tests run both values. Ting Yu flips it in 16 (N10).
- **Q7** (the landing-page path in tests): no new override is needed.
  - `paths.site_repo()` already reads `JURA_SITE_REPO`, and the autouse fixture in `tests/conftest.py`
    points it at `tmp_path/site`.
  - `apps released` checks with `git -C <site_repo> merge-base --is-ancestor <sha> main`. It never
    fetches, pulls or writes.
  - The D13 test asserts that the path the code checked is under `tmp_path`, because the write guard
    doesn't cover subprocesses.

The project manager's questions, settled:

- **Q2:** the network guard goes in 01 (T12).
- **Q3:** no row is traced at "whichever lands second". The four pairs become edges, each with one
  owner (T4). AC-M1.6 is 09's, AC-M3.1's ids are 03's, and the one-pager line for AC-M9.3 is 10's.
  The QA lead updates the Ticket column of those rows and §11.2.
- **Q4:** AC-M12.2 stays in 06, where the ticket already has it.
- **Q5:** the digest counts go in browser-publishing#02a. #02b creates join items through `community
  propose-join` and owns the `group-join` kind with its answers step. #06 owns adding `propose-join` to
  the Monday run, the `--outcome questions` flow, the join outcomes and `pages-not-allowed` (T8).

Q8 belongs to the functional lead and is not answered here.

## Files shared by parallel tickets

Each wave below is a set of tickets that can run at once. Every file two of them touch has one owner per
behaviour, and the anchors in N8 keep the edits in separate hunks.

| Wave | Tickets | Shared files and how they're kept apart |
|---|---|---|
| 1 | 01, 02 | None. Only 01 touches `conftest.py`; 02's helpers are new modules (T7, T12) |
| 2 | 04a, 07 | None |
| 3 | 04b, 08, 03 | `cli.py` (04b's decision commands; 08's `one-pager --no-post` and `status`); `settings.yaml` (04b's block; 03's job flags); plug-in `__init__.py` files (08's `REQUIRED_SETTINGS`; 03's `run_update()`). Only 04b touches `approvals.py` and `discord.py` |
| 4 | 06, 11, 10, bp#02a | None. Only 11 touches `cli.py` and `discord.py`; only #02a touches `headless.py` |
| 5 | 05, 09, 10b, bp#02b, bp#03 | `community/__init__.py` (05's kind and `set`; #02b's `publish-plan` and `propose-join`); `remote.py` and `dispatch-contract.md` (09's and #03's rows); `settings.yaml` (09's and #03's jobs); `agents/publish/` (#02b in `claim.py` and the kinds; #03 in `job.py`) |
| 6 | 12, bp#04, bp#06 | `prompts/publish.md` (#04's and #06's own sections); `agents/publish/` (#04's host list; #06's commands) |
| 7 | bp#05 | - |

## Build order and frontier

**Frontier today.**

- For agents: nothing. `main` doesn't have the blocker fixes yet, because PR #1 is waiting for its G4.
- For Ting Yu: browser-publishing#01, his Chrome profile and checks. It touches no code. I agree with
  the project manager that it should start now.

**Order once PR #1 merges:**

1. The conductor creates `crew/mission-control` from `main` and commits the four untracked paths (T11).
2. The waves below run in order.

| Wave | Agent tickets (blocked by) | Human tickets that open |
|---|---|---|
| 1 | 01 (`main`), 02 (`main`) | - |
| 2 | 04a (01, 02), 07 (01) | - |
| 3 | 04b (04a), 08 (07, 04a), 03 (01, 02, 04a) | - |
| 4 | 06 (04b), 11 (04b), 10 (04b, 08), bp#02a (mc#01, mc#04b) | - |
| 5 | 05 (04b, 11), 09 (08, 11), 10b (10), bp#02b (bp#02a), bp#03 (bp#01, bp#02a, mc#03, mc#08, mc#11) | 14 once Dispatch D1 to D4, D8 and D9 exist |
| 6 | 12 (11, 10b), bp#04 (bp#03), bp#06 (bp#03, bp#02b, mc#05) | 13 (03, 04b, 09); 15 (06, 14, D5) |
| 7 | bp#05 (bp#03, bp#06, mc#05) | 16 (12, 14, D6, D8, the toolbox on `landing-page` `main`) |

**What the changes cost.**

- **The pair edges (T4) don't lengthen the critical path.** On the original breakdown they would start
  03, 05, 10 and 12 one wave later. No ticket that leads to one of Ting Yu's steps moves: 09, 13 and
  browser-publishing#03, #05 and #06 keep their waves, and 16 waits for Dispatch D6 anyway.
- **Splitting 04 (T1) adds one wave** to everything after it. That is the price of fitting one context
  window.
- **Making #05 follow #06 (T8) adds one wave** at the very end. It also matches the live order.
- **Splitting #02 (T8) recovers time.** #03 needs only #02a, so the browser job starts in wave 5, with
  community items alongside it.

**Critical path to the first real use.** 01 and 02, then 04a, 04b, 11, 09, then 13 (Terminal
decisions, run updates and the one-pager). The first Facebook Page post comes after
browser-publishing#03 in wave 5, then Ting Yu's R1 to R4 and U12.

## Follow-ups for other personas

- **Project manager:**
  - apply T1, T4, T5, T7 to T12 and N1 to N10 to the tickets;
  - create `04b`, `10b` and `browser-publishing/02b`;
  - update both status files: edges, frontier, lanes, and the removal of the "order-independent pairs"
    and "04 near one context window" risks.
- **QA lead:**
  - in v3, add the ticket ids MC-04a, MC-04b, MC-10b and BP-02a, BP-02b to §4's Ticket column and to
    §11.2;
  - retire Q3's "lands second" note (§4 preamble, AC-M1.6, AC-M3.1, AC-M9.3);
  - D1 seeds `run.quiet` for publish's "nothing due";
  - E6's setup-guide checks follow N4 if it is accepted.
- **Business analyst:** add `on_approve` (T2) and `NothingToDo` (T3) to MC §4.6 and §5.3 as
  clarifications.
- **Conductor:** do T11's first commit before any worktree. Ask Ting Yu T11's branch question at G3.
