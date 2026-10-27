# Code review 04b: Terminal decisions and approval cards

- **Branch:** `crew/mission-control-04b-terminal-decisions-and-cards` (a58d682 to 29023eb, 11 commits), compared with fixed point 8e3d9b4 (`git diff 8e3d9b4...<branch>`, 23 files)
- **Spec:** `issues/04b-terminal-decisions-and-cards.md` and its comments; PRD MC §4.3, §4.6 A8 to A12, A16, A17, §5.6; MC3 (crew-log G2: "six-character code for Terminal approvals, none from Claude sessions"); ADR 0004; `reviews/technical-v2.md` B2; `reviews/test-strategy-v3.md` (04b rows, §5.3 G13)
- **Reviewer run:** 2026-10-26, from a crew reviewer session that is itself a Claude Code process (`claude` is an ancestor, and `CLAUDECODE=1` is set)

## Verdict: changes-requested

There is one blocking finding, S1. The control that MC3 and A8 promise, "so no agent session can decide", does not hold. From this Claude session I recorded two Terminal decisions using only stock macOS tools. To be fair to the developer: the code does what AC-M7.4 literally asks. The gap is in the claim the spec and the docs make. Fixing it takes one small code change and one decision from Ting Yu: accept the limit in the wording below, or ask for proof of presence. Everything else is *should fix* or smaller.

## Evidence

- `uv run pytest -p no:cacheprovider` in the developer's worktree, with `JURA_ROOT` set and temp data and outputs folders: **1670 passed in 40.28s**.
- Pyright on the touched modules reports 0 errors (from the Standards reviewer).
- The probe for S1 used a temp data folder under the session scratchpad, `JURA_GROWTH_DISCORD=off`, no env file, no Discord webhooks and no Keychain. It never touched the live `growth.db`. The request came from `tests/origin_child.py`'s file kind. Transcript:
  1. `origin_child.py approvals`, run from the Bash tool with no TTY and no `JURA_GROWTH_JOB`, exits 0 and lists `A-0001 · … · code c6c430`.
  2. `sqlite3 -readonly growth.db "select substr(content_hash,1,6) …"` gives the same codes.
  3. `printf 'c6c430\n' | script -q /dev/null … approve A-0001`, still a child of the session, is refused: "a decision can't come from inside a Claude session". The ancestry check works while the tree is intact.
  4. `( /usr/bin/expect -c "spawn … approve A-0001; expect \"code (\"; send \"c6c430\r\"; expect eof" & )` answers **"A-0001 approved."** The record reads `approved | terminal | terminal:tingy`.
  5. `( nohup /usr/bin/expect … skip A-0002 … & )` answers **"A-0002 skipped."** The record reads `skipped | terminal | terminal:tingy`.
  6. The same as 4, with `env -u CLAUDECODE -u CLAUDE_PID`, answers **"A-0004 approved."**
  7. `( sh -c 'echo ppid=$PPID CLAUDECODE=$CLAUDECODE' & )` prints `ppid=1 CLAUDECODE=1`. An orphan is adopted by launchd but keeps Claude Code's environment markers.
- The repo's own suite shows the same thing. `tests/test_origin_processes.py::test_under_a_real_terminal_the_right_code_records_the_terminal_decision` passes inside this Claude session, because `tests/pty_driver.py` double-forks out of the session's process tree (`pty_driver.py:59-63`).

## Security

### Blocking

**S1. A process started by an interactive Claude session can record a Terminal decision.** Where: `jura_growth/origin.py:184-198` (`detect()`), and the claims at `origin.py:10-11`, `approvals_cli.py:3-4`, PRD MC §4.6 A8 ("Claude Code's Bash tool has no TTY, so no agent session can decide") and ADR 0004. The rule it breaks is MC3, "none from Claude sessions", together with the ticket's "and no agent process can".

How each part of the control holds up:

- **The code is not a secret.** It is the first six hex characters of the content hash.
  - The card in `#approvals` shows it (`cards.py:79`).
  - `jura-growth approvals` prints it, and it checks only `JURA_GROWTH_JOB`, not the origin (`approvals_cli.py:113-114`).
  - Anyone can read it from `growth.db` (`approvals.content_hash`).
  - Anyone who can read the item can compute it.
  - It never appears in `approve`'s argv or the process list, because it is typed on stdin. That doesn't matter, since the session already has it. Scrollback doesn't matter for the same reason.

  So the code proves that someone looked, not who typed it.
- **The TTY check** stops the Bash tool itself. It does not stop a pseudo-terminal the session makes: `/usr/bin/expect`, `/usr/bin/script` or Python's `pty`.
- **The ancestry check** is a denylist walked upward. Any route that leaves the tree defeats it:
  - Reproduced: a subshell orphan `( … & )` and `nohup … &`.
  - Read but not run: Python's `os.fork()` plus `setsid()` (the test driver does exactly this); `launchctl submit` (its parent is launchd); `tmux new -d` (the tmux server's parent is launchd); `open -a Terminal x.command` or `osascript … do script` (the chain is login, then Terminal, then launchd, inside a real Terminal TTY). I didn't run the last two because they open a window on Ting Yu's desktop. `osascript` also needs Automation consent the first time; `open` does not.
- **The decision is attributed to Ting Yu** (`terminal:tingy`, `decided_origin = terminal`), so the audit trail can't tell the two apart afterwards.

**A headless scheduled run can't do any of this.** I read the code but couldn't run a headless job, because the operating card forbids `jura-growth run`.

- `runner.claude_command` (`runner.py:248-286`) runs `claude -p --permission-mode dontAsk`.
- The `--allowedTools` list holds only the job's own `jura-growth …` commands, `Write` and `Edit` in its work folder, and WebSearch and WebFetch. `headless.NEVER` denies `approve`, `skip`, `approvals` and `remote`, bare and with `:*` (`headless.py:45`, `:127-128`).
- No job is allowed `expect`, `script`, `python`, `nohup`, `open`, `osascript`, `launchctl` or `sqlite3`. A headless run has no tool to make a terminal or leave its tree.
- Even past those rules, `refuse_in_a_run()` (`approvals_cli.py:45-50`) refuses while `JURA_GROWTH_JOB` is set.
- What is left is Claude Code's own parsing of compound commands (`;`, `&&`, `$( )`) under `dontAsk`. This repo doesn't test it: AC-M7.7's fake claude proves the code-level refusal, not the rules.

Interactive sessions sit outside these guards the same way they already do for direct writes. ADR 0004 records that raw SQL can approve. I confirmed it again on the temp DB: `UPDATE approvals SET status='approved' …` passes the trigger. The reparenting route therefore adds no new power over the database. What it does is make the Terminal origin claim false, and make a forged decision look like a real Terminal one.

**The narrowest fix (recommended, about 10 lines in `origin.py`, inside this ticket):**

1. `detect()` and `detect_ssh()` also refuse when Claude Code's environment markers are present: `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT` or `CLAUDE_PID`.
   - This only ever refuses, so it fits the module's rule that an origin is never *granted* from an environment variable.
   - It survives every reparenting route above (probe 7), so it catches every accidental or casual route. Only deliberate stripping gets past it (probe 6).
   - `tests/pty_driver.py` must then strip those variables for its positive cases, so the test shows on its face that it is evading. Add one real-process case that keeps the markers and is refused.
2. Correct the over-claims at `origin.py:10-11` and `approvals_cli.py:3-4`. PRD A8's "so no agent session can decide" and ADR 0004 need the known limit below (S1-Q).
3. Optional, and a larger change: refuse a chain that reaches launchd without passing a terminal host (Terminal, iTerm2, VS Code's helper, `login`, `sshd`). That closes the silent routes: orphan, setsid, launchctl, tmux and the detached pty. It leaves only routes that open a visible window. It also stops the positive real-process tests from running inside a Claude session, so those move to canned `ps` tables plus U1. I recommend item 1 alone now.

Nothing that runs as Ting Yu's macOS user can fully close this: whatever `jura-growth` can read, the session can read too. Proof of presence that no process can produce would close it. One example is macOS LocalAuthentication (Touch ID or the login password in a system dialog) inside `detect()`. That needs a new dependency or helper, so it is Ting Yu's call and would be a new ticket.

**S1-Q, the known limit to add to ADR 0004 (and in short to PRD A8), if Ting Yu accepts it.** It answers the developer's question. Yes, list it, but it covers more than reparenting:

> A second known limit: the Terminal origin tells a real terminal from a pipe and refuses a process
> that is visibly part of a Claude session, but it can't tell Ting Yu's keystrokes from another
> process running as his macOS user. A process started from an interactive Claude session can leave
> the session's process tree (a double fork, `nohup … &`, `launchctl submit`, a new Terminal window
> through `open` or `osascript`), give itself a terminal (`expect`, `script`, Python's `pty`) and type
> the code, which is not a secret: the card, `jura-growth approvals` and `growth.db` all show it. The
> code proves someone read the card, not who typed it. `origin.py` also refuses Claude Code's
> environment markers, which survive reparenting, so only a deliberate evasion gets through.
> Headless runs can't do any of this: their rules allow only their own `jura-growth` commands and no
> tool that makes a terminal or starts a process. So an interactive session on the Mac is trusted not
> to decide, as it is trusted not to write `growth.db`: don't let one run shell commands without
> asking (auto mode, `--dangerously-skip-permissions`) while it reads content from outside. Closing
> this needs proof of presence that no process running as Ting Yu can give, such as Touch ID or his
> login password through macOS LocalAuthentication.

### Should fix

None beyond S1.

### Nit

- **S2.** `origin.py:145-151`. `_is_claude` matches the basename of `ps -o comm=`. On macOS that follows argv[0]: `pty_driver.py:67` makes a Python process show as `claude` this way. So a Claude Code started under a different argv[0] would not be seen, for example by its versioned install path rather than the `claude` link. I didn't verify that case. Item 1 of the fix covers it.
- Cards and edits: I found no high-confidence issue.
  - `discord.edit()` masks through `privacy.for_discord`, sends `allowed_mentions: {parse: []}`, and never quotes the URL in an error (`discord.py:222-245`, `:314-321`).
  - The sweep loads the Keychain values first (`cards.py:132`).
  - `message_id` comes from Discord's own response.
  - The seed's refusal resolves the path and requires the temp root and every data variable inside it (`tests/uat/seed.py:52-68`).

## Standards

From the Standards reviewer, with two claims checked by me (marked "checked"). No documented standard is broken, and pyright is clean.

### Should fix

- **St1. Feature envy, against the module ownership in `approvals.py`'s docstring.** `cards.py:140` (checked) selects pending, unposted approvals. `cards.py:168` (checked) writes `UPDATE approvals SET posted_at …`. `cards.py:87` looks up the successor. Meanwhile `cards.py:33` claims the card uses `get()` and `pending()`. Move these into `approvals` (`unposted()`, `mark_posted()`, `successor()`), or correct the docstring.
- **St2. Middle man and an import cycle.** `approvals.post_unposted` (`approvals.py:696-702`) only lazy-imports `cards` and calls `sweep`. The name also hides that it edits cards too.
- **St3. Duplicated code.** The same swallow-and-warn wrapper around the sweep appears three times: `approvals.py:716-722`, `approvals_cli.py:88-91` and `cli.py:196-199`. Extract one helper.
- **St4. Duplicated code.** `discord.edit()` (`discord.py:229-234`) repeats `post()`'s preamble: the channel check, `privacy.learn`, `for_discord`, and the webhook and env-name lookup. Unlike `post()`, it takes no `client=` for injection.
- **St5. Primitive obsession.** `cards.py:78-85` and `:182` use raw status strings, though `approvals.py:30` defines `PENDING` and the rest. `"used"` has no constant.

### Nit

- **St6.** `cards.py:82` says "used at" in text Ting Yu reads. `CONTEXT.md` (Claim) says to avoid "use" in prose; write "claimed at".
- **St7. Speculative generality.** `FINAL` (`cards.py:47`, checked) is never used. `_approval_upkeep(post=…)` (`cli.py:189`) is only ever called with `True`.
- **St8. Reuse.** `approvals_cli.py:117-119` counts by hand, which duplicates `collections.Counter`. `refuse_in_a_run` (`approvals_cli.py:48`) is a third raw read of `JURA_GROWTH_JOB`, after `headless.py:174` and `paths.py:127`. One `current_job()` helper would serve all three.
- **St9.** `approvals.py:711` imports `functools` inside a function. Neighbouring modules import at the top.
- **St10.** `approvals_cli.py:101-102` parses each `decide_by` twice.

## Spec

From the Spec reviewer, with its first two findings checked by me. Every acceptance criterion in the ticket has a test that would fail if the behaviour broke: AC-M5.2 to AC-M5.5, AC-M7.1 to AC-M7.4, AC-M7.7, X12, X13, G33, the card sweep, pending-only posting and the stored message id. Not posting without the approvals webhook fits A12, because the record waits as unposted.

### Should fix

- **Sp1. The supersede text in AC-M5.3 can't be produced.** AC-M5.3 asks for "Superseded: lead unsubscribed". The core writes only "the item is gone" or "the content changed" (`approvals.py:365`, `:371`, `:510`, `:514`, checked), and a kind can't supply its own reason. So `cards.py:88` can never show the AC's text, and no test asserts it. Either add a reason to the kind contract (for example, `content()` returning a gone-reason), or record in the ticket that MC-06 owns this text and how it will supply it.
- **Sp2. "Every raising command" calls `post_unposted()` (A11, A12, X12), but nothing is wired.** `approvals.raises_requests` (`approvals.py:705-724`) decorates nothing. A grep of `issues/` finds no later ticket (05, 06, 10, 10b, BP) that mentions it, so the hand-off would be lost. Comment the decorator onto those tickets, or add a structural test that every A11 command's callback is wrapped once it exists.

### Nit

- **Sp3. Scope.** The 23:30 backup posts new cards as well as editing them (`cli.py:206`). The ticket asks it only to write lapses, and A12 names the heartbeat and the raising commands as the posters. A new card at 23:30 can notify Ting Yu. Use `post=False` for the backup, or edit without posting.
- **Sp4. The listing.** It adds a kind-filtered tail line (`approvals_cli.py:121`) and a "passed its decide-by" line (`:129`). When some requests have lapsed, the listing no longer ends with AC-M5.4's line. `uat.md` A4 expects `approvals` at 16:31 to read "Expired", which the plain read rightly doesn't write (A17), so the UAT text needs updating.
- **Sp5. For MC-08.** A request decided before its card posted never gets a card (`cards.py:21`, as the ticket comment asks). 08's "unposted" line must count pending requests only.
- **Sp6. The seed.** It requires three variables (`tests/uat/seed.py:34`), but not `JURA_GROWTH_CONFIG_DIR` or the env file that `uat.md` sets inside `$UAT`. `uat.md` still names `tests.mission_seed`.

## Blocked paths

None touched. The diff changes `config/settings.yaml`, `jura_growth/` and `tests/` only: no `inputs/`, no `design-system/`, no `.env`, and no live `data/growth/`.

## UI

No UI files changed, so `web-design-review` doesn't apply.
