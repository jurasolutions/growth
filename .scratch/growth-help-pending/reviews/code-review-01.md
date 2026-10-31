# Code review: ticket 01, `/growth help` and `/growth pending`

Branch `crew/growth-help-pending-01-help-and-pending` at `83b912c`, against the fixed point
`crew/growth-help-pending` (`4bd23fc`, which is also the merge-base). Commits: `2d85425`, `83b912c`.
All 23 changed files were read or covered by an axis.

**Verdict: changes-requested.** Three blocking findings, each reproduced by running the code.

## Evidence

- Full suite on `83b912c`, in a detached worktree with the card's exports: **4672 passed**, 334s. It
  doesn't catch any blocking finding below.
- Pyright on `builds.py`, `publish/commands.py`, `tests/test_remote_help.py`, `pending.py`,
  `releases.py`, `timeutil.py`, `remote.py` and `agents/__init__.py`: **0 errors**. So the IDE's errors
  about `PendingItem`, `GROWTH`, `YOU`, `timeutil.ago` and `Entry.summary` are refuted: stale, as you
  guessed. The whole package reports 70, under the card's advisory 84.
- The reproductions are in
  `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/0d7f42af-63af-4b4e-8fd9-479f3cbb14f0/scratchpad/review01-reproductions.py`.
  To run them, copy the file into `tests/` of a checkout as `test_zz_review01.py`. It isn't committed
  anywhere. The worktree it ran in is removed.

## Standards

**Blocking:** none.

**Should fix**

- `jura_growth/pending.py:52-68`, reuse. `_requests` rewrites `approvals_cli.waiting(conn, kind)`
  (`approvals_cli.py:99`), "the one selection both listings show": pending, still in time, soonest to
  lapse first, with the decide-by. Its docstring's reason, "its own SELECT, as in the read model", is
  mission's concern about `approvals.py` superseding on a read, and `approvals.pending` is documented
  as a plain read. Crew rule: new code duplicating an existing helper. A single selection also means
  `pending` and `approvals` can't disagree on what is waiting.

**Nit**

- `agents/community/__init__.py:98`, `agents/outreach/__init__.py:77`, `agents/social/__init__.py:52`:
  possible Duplicated Code, the same count-and-plural line three times; `health._plural`
  (`health.py:134`) is private.
- `pending.py:87-100` and `mission._plugin_lines` (`mission.py:419`): possible Duplicated Code, the
  same walk over the hooks.
- `agents/__init__.py:123`: possible Primitive Obsession, `order` is 0 to 3 with meanings only in a
  docstring. Name them, as `YOU` and `GROWTH` are named. The README's hook row (`README.md:203`)
  doesn't mention `order`.
- `releases.py:474-479` and `:503-510`: possible Repeated Switches on `app.state`.
- `pending.py` `_why`, `_checked`: possible Mysterious Name.
- `mission.py:262`: `mission.connect` is now a public name beside `db.connect`, the one ADR 0002 says
  not to switch to. `connect_read_only` would say which it is.
- `agents/apps/backlog.py:14`: the module docstring still says "every read, change and save runs under
  `locked()`", which `ideas.pending_items` now deliberately doesn't.

Raised by the Standards reader and dropped after checking: "state" in `Unreleased` (the ticket itself
says "app release states"; it isn't a request's reading), "item" alone (the module already does this
and the context is plain), and lower-case "and N more" (the ticket's own words).

## Spec

**Blocking**

1. `jura_growth/agents/apps/releases.py:443` with `:497`. Breaks "most urgent first" and "Order the text
   so the urgent part survives a cut". Apps are listed by build id, whatever their state, and a skipped
   build stays `built` for good, so old skips sit above a newer approved release. Each preview line runs
   to about 330 characters (`:488`), so five fill the answer. Reproduced: six skipped builds, then
   APP-020 approved and unclaimed. The answer is five "stays on its preview" lines and
   `(cut: 5 more lines)`. APP-020 and its `release-plan` line are gone, along with anything in publish.
   This is the exact case the ticket exists for, and it gets worse with every skip. The suite's long-list
   test (`tests/test_pending.py:715`) has one app and so can't see it.
   **Fix:** pass `order=1` (or lower urgency) on the preview lines so approved and claimed come first,
   and consider a cap with "and N more", or a shorter line. Add the test above.

2. `jura_growth/agents/apps/ideas.py:176`, through `backlog.load` (`backlog.py:63-65`). Breaks "Say
   'nothing pending' only when every source was read" and "never a silent gap or a guessed zero". `load`
   is lenient: wrong shapes become no rows, and no exception reaches the `except`. Reproduced, each
   answering `Nothing pending. Nothing is waiting for you, and growth has nothing under way.`:
   - an empty file;
   - `apps: oops`;
   - `app:` (a typo'd key) with a real open idea of Ting Yu's under it;
   - a top-level list of strings.

   Parser errors, `apps: null` and binary content do say "couldn't be read", so only these shapes
   slip through. The file is documented as hand-editable, so this is a live path. A missing file falls
   back to the seed, which is right.
   **Fix:** in the read `pending` uses, treat a file that exists but isn't a mapping with an `apps` list
   as unreadable, and rows dropped for shape too. Leave the writers' `load` alone unless you mean to
   change them. Parametrise a test over the four shapes.

**Should fix**

- `jura_growth/remote.py:422` and `:464`, on the `remote` path. Breaks the spirit of ADR 0002 ("A
  reporting path must never be the process that decides what happens to an unfinished write") and sits
  badly with AC5. `pending.read` is properly read-only, but `_masked` and `_record` open `db.session`,
  which recovers and migrates. Reproduced through `remote --json`:
  - Hot journal (dataset D4): the answer says "growth.db has an unfinished write. Send `/growth status`
    to clear it", and by the time that answer is returned the journal is gone and the database file has
    changed. The advice is already out of date.
  - Missing database: the first send says it doesn't exist, and creates it. The second says "Nothing
    pending". If the database was lost or moved rather than never made, that second answer is false
    comfort.

  This wrapper predates the ticket and serves every command (by reading, `one-pager` too), and the ticket
  allows the `remote.command` event, so I don't block on it. `tests/test_pending.py:560` covers only the
  bare CLI and `:461` only the first send, so neither shows it. **Recommendation:** for `pending`, don't
  open the database read-write when `mission.connect` reported it missing or mid-write: put the event in
  the JSONL mirror, as `_record` already does on failure. If that is too large, record the behaviour in
  the contract and in ADR 0002 as a known exception.

- `docs/dispatch-contract.md:101`. Two statements don't match the code: "takes no lock" (remote's event
  write takes growth.db's write lock; the ticket means the backlog lock), and "the text then starts with
  'Couldn't be read'" (it starts `**Couldn't be read**`). Dispatch's authors read this file literally.

**Nit**

- `releases.py:446`, a state it omits. A `built` row whose latest request is superseded, or that has none,
  is skipped, and `pending` then says "Nothing pending" (reproduced by forcing the row). I found no code
  path that reaches it: `report_built` always raises a new request in the same transaction, and a
  supersede with no successor needs the row to have left `built`. The one-pager skips it too, so its text
  stays as it was. A line saying "has no release request on record" would close the gap for `pending`.
- `releases.py:488` tells him to send `/growth apps built …`, while `help` says "Dispatch sends this".
  It works (reproduced: exit 0, a new request raised), and the one-pager gives the same advice. The two
  summaries could agree, for example "Dispatch sends this; send it yourself to ask again".
- `publish/commands.py:339`: a stale claim goes to Waiting for you, uncapped, where the ticket lists
  `claimed` under Growth. It is the better reading, and `publish resolve` accepts it. Record it in the
  ticket.
- `releases.py:508`: `on_main` can take `GIT_TIMEOUT` (30s) per claimed app, inside Dispatch's 60-second
  window, if git hangs. Rare with one claimed app at a time.
- `tests/test_pending.py:585,613`: AC6 through `remote` compares row counts, so an UPDATE would pass. The
  bare CLI test has the stronger stat snapshot.
- `ideas.py` idea line: `apps idea` caps a name at 60, but a hand-edited name isn't capped. With a
  2,500-character name the line is cut and the urgent part survives, since it comes last.

## Security

**Blocking**

3. `jura_growth/pending.py:81`, personal data reaching Discord. `_title` cuts to `TITLE_MAX` before
   `remote._masked` runs `privacy.for_discord`, so an address or number across the cut no longer matches
   the masks. Reproduced with the real `group-rules` kind and a group name holding an address, as a
   scraped name can, through `remote --json`:

   ```
   - A-0008 · Group 1 GGG…GGG email jane.tan@gma… · decide by Tue 10 Nov, 16:30 SGT
   ```

   `/growth approvals` on the same record shows `j***@gmail.com or [phone removed]`, so `pending` is weaker
   than its sibling. Group names, and `company` and `industry` in outreach titles, come from scraping
   (the `reason` fallback goes the same way). **Fix:** `discord.shortened(privacy.for_discord(...), TITLE_MAX)`;
   `read()` has already loaded the masks. Add a test with the address across the cut.

**Should fix:** none.

**Nit**

- Titles keep their Markdown, so a scraped name could render as a masked link under Waiting for you.
  `_defuse` stops only mentions, and `/growth approvals` already emits these titles raw, so this is a new
  place for an existing weakness. I couldn't confirm how Dispatch renders it. Not reported as a
  vulnerability.

**Checked, no finding:** `help` and `pending` use `_none`, so any extra word is refused with exit 2. All
new SQL is static or parameterised. `backlog.load` uses `safe_load`. `on_main` uses list-form `subprocess`
with a checked SHA. Branch, SHA, task and preview are checked when stored, so they can't break out of the
backticks. The outreach, social and community lines are counts only.

## Blocked paths

None touched: `git diff --name-only` shows nothing under `inputs/`, `design-system/`, `.env`,
`data/growth/` or CI.

## What you asked

- **Does `pending` tell the truth?** On every reachable state, yes, except findings 2 and the buried line
  in 1. Compared against every `app_builds` status (`handed_off`, `built`, `released`) and every request
  status:
  - An approved request past its `use_by` shows as "stays on its preview: approved, but its merge was never
    printed", by the clock and when written.
  - A claimed release whose build moved on isn't a stale claim: `report_built` raises a new request, which
    becomes the latest, so `pending` lists it once under the requests. Reproduced, and `release-plan` then
    refuses, as the line implies.
  - Claimed lines stay true, since a claimed latest always hashes to the row.
- **`health_lines` byte for byte?** Yes. I ran the old function from `4bd23fc` beside the new one on
  waiting, expired (clock and written), approved, lapsed (clock and written), claimed, skipped, released and
  superseded. The output was equal in all ten. No one-pager test changed.
- **Masking and cuts:** the answer is masked before it is cut (`remote.py:_masked`), except titles (finding
  3). The urgent section can be lost (finding 1). Publish lines carry only `P-nnnn`, platform and day. Idea
  names are masked and sit last.
- **Backlog read:** no lock and no write, by reading and by the suite's tests. Malformed YAML is reported,
  but wrong shapes aren't (finding 2).
- **Renames in `mission.py`:** clean. No `_connect`, `_state_of` or `_error_name` remains in `jura_growth/`
  or `tests/`, and the in-flight branches I checked don't use them. The naming nit is under Standards.
- **`help`'s place:** sorted correctly in `ALLOWLIST`, row present in contract order, and
  `tests/test_remote.py` passes. 1,437 characters against 1,900, with room to spare.
- **Scheduled runs:** they can't send either. No plug-in declares them, `headless` denies by default, and
  `remote` refuses under `JURA_GROWTH_JOB`. `tests/test_pending.py:690-706` pass, so `NEVER` needs no change.
- **Pyright:** the errors are refuted, as above.

## Re-review d80d73f

Branch head `d80d73f`, one commit on top of `83b912c`. Every changed file in that commit was read.

**Verdict: approve.** All three blocking findings are fixed and stay fixed under the original
reproductions. No new blocking finding. One should-fix remains, a test gap, and it doesn't block.

### Evidence

- Full suite on `d80d73f`, in a detached worktree with the card's exports: **4705 passed**, 502s.
- Pyright on the ten changed source files and `tests/test_remote_help.py`: **0 errors**. Whole package: 70,
  the same as at `83b912c`.
- The original reproductions and the new cases below, run against this commit:
  `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/0d7f42af-63af-4b4e-8fd9-479f3cbb14f0/scratchpad/review01-reproductions.py`.
- Blocked paths: none touched. All review worktrees are removed.

### The earlier findings

| Finding | Reproduction at `d80d73f` | State |
|---|---|---|
| B1, skips bury an approved release | Six skips, then APP-020 approved: APP-020 is the first line, then the newest three previews and "and 3 more stay on their previews". 1,220 characters, no cut | Fixed |
| B2, wrong-shape backlog | Empty file, `apps: oops`, `app:` typo and a list of strings each answer "The app backlog couldn't be read (ValueError)". "Nothing pending" no longer appears | Fixed |
| B3, title cut before masking | Real `group-rules` title and the `reason` fallback, every padding from 40 to 99: no part of the address or phone number survives. The address reads `j***@gm…` at worst | Fixed |
| Should-fix, hot journal through `remote` | Journal still there, same size, database bytes unchanged. The second send gives the same answer, so "Send `/growth status` to clear it" is now true | Fixed |
| Should-fix, missing database through `remote` | No database after two sends, and both say it doesn't exist | Fixed for `pending` (see the second nit below) |
| Should-fix, reuse of `approvals_cli.waiting` | `_requests` now calls it, and a test holds `pending` and `approvals` in agreement | Fixed |
| Should-fix, contract wording | Row now says "no backlog lock" and gives the `**Couldn't be read**` heading exactly | Fixed |

Reverting each fix in a throwaway worktree, `tests/test_pending.py` went red every time: B1 4 failures, B2
6, B3 5, the database branch 4. So the new tests do hold these. Six earlier nits are also done: named `order`
values, the README hook row, the backlog docstring, the stale-claim decision in the ticket, the `apps built`
summary, and a remote AC6 test that now compares row contents.

Stress case for anything B1 broke: seven requests, two approved, one claimed, five skipped and six publish
items of unknown outcome. Approved and claimed all survive, previews give way first, and the answer shows
`(cut: 8 more lines)`. That order is what the ticket asks for.

### What you asked

- **Is `_leave_database_alone` limited to `pending`?** Yes (`remote.py:415-424`). It compares the first word
  exactly, and `match` is exact too, so `PENDING`, `Pending` and `pending ` are refused and follow the ordinary
  path. They can't get a real `pending` answer that way. `pending x` takes the branch, which is right and has a
  test. With `database=True` the `_masked` and `_record` paths behave as they did before, by reading.
- **Can a healthy database take the branch and lose the event?** It can take the branch, and it doesn't lose the
  event:
  - With no lock it can't: `mission.connect` reports OK. A held `RESERVED` lock doesn't take it either (run).
  - An `EXCLUSIVE` lock held past the two-second `BUSY_TIMEOUT` does, because `state_of` files every lock under
    `UNFINISHED_WRITE` (run: the database gained no event row).
  - The event goes to the JSONL mirror (run: the line is there), and the next send after the lock clears writes
    its row as usual.
  - At `83b912c` the same lock gave nearly the same result, by reading: `db.session(wait=SHORT_WAIT)` also waits
    two seconds, then falls back to the mirror. The only change is a lock that clears inside that extra wait.
  - Nothing in `jura_growth/` names `remote.command` except the code that writes it, so no reader depends on the row.
  - The whole answer under that lock took 5.4s, well inside Dispatch's 60.
- **Is `backlog.load_checked` only on the read path?** Yes. The one caller is `ideas.pending_items`
  (`ideas.py:176`). The writers still use `load`, and a test holds `load` as lenient as it was.
- **`health_lines`, old against new:** equal on all eleven cases, using the function from `4bd23fc`: waiting,
  expired (clock and written), approved, lapsed (clock and written), claimed, skipped, released, superseded, and
  no request at all. Both `NO_REQUEST` cases give no one-pager line, as before, and `pending` gives each its own
  line under Waiting for you.

### Findings

**Blocking:** none, on Standards, Spec or Security.

**Should fix**

- `tests/test_pending.py:786`, Spec. `test_every_other_command_still_opens_the_database` can't fail on what it
  names. `status` opens the database inside its own command, so the assertion holds with or without the guard.
  Reproduced: with the `words[:1] != ["pending"]` guard removed, `test_pending.py` passes all 164, and
  `test_remote.py`, `test_remote_help.py`, `test_remote_apps.py` and `test_one_pager.py` pass all 313. The code is
  right today, but the limit you asked about has no test. **Fix:** assert `_leave_database_alone` is False for
  every other allowlisted command on a missing database, or send `help`, which doesn't open the database itself,
  and check that it gets created.

**Nit**

- `releases.py` `pending_items`: "and 3 more stay on their previews." has no pointer, unlike the other cap lines
  (`/growth approvals`, `/growth publish queue`). Their preview links can't be reached from this answer.
  `/growth one-pager` lists them, so it could say so.
- `remote.py:415-424`: any other remote command still creates a missing database, `/growth help` included, though
  `help` doesn't need one. Reproduced: `pending` says it doesn't exist, `help` runs, then `pending` says "Nothing
  pending". This is the ordinary route back from a missing database, and the ticket scoped the fix to `pending`.
  Adding `help` to the guard would be one word.
- `remote.py:415` and `docs/dispatch-contract.md:101` say "mid-write" and "unfinished write", which also covers a
  plain lock held by a healthy database. The answer's own wording (`DB_WORDING`) predates this ticket.
- `backlog.load_checked`: a top-level list of rows, which `load` accepts, reads as unreadable. `save` and the seed
  both write the mapping, so only a hand edit gets here, and it errs in the safe direction.
- `releases.py` `pending_items`: approved releases are in build order, not soonest to run out first. It matters
  only with several at once.
- Standing from the first review, unchanged: the three count lines, the walk over the hooks, the `app.state`
  switches, `_why` and `_checked`, the `mission.connect` name, `on_main`'s 30 seconds per claimed app, and the
  uncapped hand-edited idea name.

## Re-review d7d3211

The diff against `d80d73f` only: one commit, for QA defect 02, the should-fix above, and the decide line.

**Verdict: approve.** No blocking finding and no should-fix. Two nits.

**Evidence:** full suite **4755 passed**. Pyright: 0 errors on `pending.py`, `remote.py` and `mission.py`, and 70
across the package, unchanged. No blocked path touched. My checks, run against this commit:
`/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/0d7f42af-63af-4b4e-8fd9-479f3cbb14f0/scratchpad/review03-checks.py`.
The earlier reproductions still pass.

- **`mission.is_empty`:** the only callers are `pending.py:35` and `remote.py:425`. `mission.py` gains that function
  and nothing else, and `releases.py` isn't in this diff, so the one-pager's text is unchanged. The old-against-new
  `health_lines` result from the last re-review still holds.
- **`help` on a healthy database:** writes its event row (run: one more row). So does `pending`.
- **Missing, empty or mid-write:** the file is left alone for `help` and `pending`, including the refused `help x`
  and `pending x`. Run: a missing file stays missing, a 0-byte file stays 0 bytes, and a hot journal and its database
  keep the same bytes. Under a held `EXCLUSIVE` lock there is no new row, and the next send writes one. The event is
  in the JSONL mirror each time. Missing or empty, then `help`, then `pending` still says what couldn't be read.
- **Other commands:** unchanged. The branch tests `words[:1]` against `_READ_ONLY`, and the wait tuple has the same
  three commands as before. `_masked` and `_record` aren't touched here.
- **The decide line:** it can't appear with no request shown. `_requests` adds it only when `items` is non-empty, and
  `items` is non-empty only with a request line. Run: 0, 1, 5, 6 and 7 requests give it exactly when a request line
  shows, and once. It is absent with a request past its decide-by, with only an approved release, with the table gone
  and with a `decide_by` that doesn't parse. Since a cut takes the end, it can't outlive the lines it follows.
- **Your should-fix on the test that couldn't fail:** closed. With the guard removed, `test_pending.py` now fails 35
  tests. Taking `help` out of the guard fails 6, the empty check in the guard 4, the empty check in `read` 1, and an
  unconditional decide line 11.

**Nit**

- `remote.py:425`, `pending.py:35`: `is_empty` catches only a 0-byte file. A file with a header and no tables (8,192
  bytes in my test) reads as OK. The first `pending` lists each missing table, `remote` migrates it, and the second
  says "Nothing pending". It takes dropped tables to get there, so it is rare.
- `pending.py` `DECIDE`: `/growth approve A-nnnn` is right for most kinds, but `group-rules` also takes `key=value`
  arguments. Its card carries the typed form (contract, buttons section).

Any other command on an empty file still migrates it, so `/growth status` then `pending` says "Nothing pending" (run).
That is the limit the ticket and the commit set, not a new finding.
