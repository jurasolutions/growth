# Code review 11: the remote core (MC-11a)

- Branch: `crew/mission-control-11-remote-core` at 89e6fac, six commits from 04a609e
- Compared with: `git diff 04a609e...crew/mission-control-11-remote-core` (17 files, +1748 / -27)
- Spec: ticket `issues/11-remote-core.md`; PRD `prd-jura-mission-control-2026-10-25.md` §4.6 A8, §4.7, §4.8 D1 to D9, §5.10, and the 2026-10-26 Discord-only amendment; ADR 0004; test strategy v3 (MC-11a rows)
- Reviewed: 2026-10-26

## Verdict: approve

There are no blocking findings. The branch adds two *should fix* items and two nits. Any of them can go into a follow-up commit before the merge, and none of them is a security gap.

## Evidence

- `uv run --no-sync pytest tests/test_remote.py tests/test_origin.py tests/test_origin_processes.py tests/test_growth_remote.py tests/test_approval_buttons.py -q`, run in the developer worktree with `JURA_ROOT` set and temp data and outputs folders: 221 passed.
- `uv run --no-sync pytest`, run the same way: **1992 passed**, with 1 warning (pytest can't write its cache into the repo, which is expected).
- `git merge-tree --write-tree crew/mission-control crew/mission-control-11-remote-core`: no conflicts with c2b468f.
- **Blocked paths:** none touched. The diff doesn't reach `inputs/`, `design-system/`, `.env` or the live `data/growth/`. The setup guide is drafted in `.scratch/mission-control/setup/`, and the release persona copies it to `outputs/` later.
- **Secrets:** no key, token or ID value is added anywhere. `.env.example` gets an empty `CONTROL_DISCORD_USER_ID=` (it reached this branch through 04b).

## Standards

| Rank | Where | Finding |
|---|---|---|
| should fix | `jura_growth/approvals_cli.py:98` (`listed`) | **Reuse.** `listed()` rebuilds the selection that `_listing()` (`:119`) already makes: pending requests, the kind filter, dropping lapsed ones, and the `LIST_LIMIT` cut. Only the title helper was pulled out into `_title`. The remote JSON list and the text list now have two separate ideas of "the 15 soonest". `listed` depends on the order `approvals.pending()` returns, while `_listing` sorts by its parsed `due`. The test `test_thirty_pending_through_remote_lists_the_fifteen_soonest_then_the_rest` passes today, but the two can drift apart. Have both use one selection function that returns `(approval, due)`, and let each one format its own output. |
| nit | `bin/growth-remote:41` | `os.execv` isn't guarded. If `.venv/bin/jura-growth` is missing (before `uv sync`, or after the venv is rebuilt), Dispatch gets a Python traceback with exit 1, not a `refused:` line. That is outside the contract's answer enum. Catch `OSError` around the exec and call `refuse(...)`. Setup step 1 already covers the cause, so this is about robustness only. |
| nit | `jura_growth/remote.py:278` (`_masked`) | Masking carries on silently when `privacy.load_for_masking` raises. The comment explains why, but nothing records it, so a broken contacts load would hide unnoticed. A `log.event(..., level="warning")` from the fallback would make it visible. |

The code otherwise follows the repo's conventions: a `register(cli)` hook like `approvals_cli`, docstrings that explain why, `# noqa: BLE001` with a reason on each broad except, the allowlist sorted one entry per line (N8, enforced by a test), and plain-sentence commit messages.

## Spec

There are no findings. Each criterion was checked against the code and a passing test:

- **The allowlist matches §5.10's core set exactly** (`remote.py:129`). The nine rows are approvals, approve, community removed, outreach requeue-shadow, pause, resume, skip, social skip and status. `one-pager`, `apps` and `publish` are left out as the ticket says. The contract's rows follow the same order, and a test checks this.
- **AC-M10.1 to 10.5, AC-M10.7, AC-M7.5, AC-M7.1, AC-M6.1, AC-M6.2, AC-M5.4, X11 and the real-subprocess exit classes 0, 1 and 2 are covered.** AC-M10.2 is generated over every CLI leaf and every `click.Path` command.
- **The `--json` shape is `{contract, ok, answer, exit_code, text, approvals?}`.** `handoff` is reserved for ticket 12, and the contract says so.
- **The enum and its exit codes match the code.** `EXIT_CODES` in `approvals_cli.py:33` maps recorded 0, refused 2, expired 3, superseded 4, already-decided 5, already-used 6 and unknown-id 7. `docs/dispatch-contract.md` has the same table, and a test checks it.
- **ADR 0004 says accepted**, and records why the root check was added and the limit that remains.

## Security

There are no blocking or should-fix findings. Each attack in the brief was traced to the line that stops it:

| Attack | Result |
|---|---|
| A symlink or user-owned binary named `sshd` | **Blocked.** `origin.py:174` needs `uid == 0` on the `sshd`-named ancestor, and `ps` is called by full path (`origin.py:89`). A real orphaned-symlink run is a regression test (`test_a_symlink_named_sshd_is_not_the_dispatch_origin`). |
| A root process the user can reach | **Blocked.** A process running as Ting Yu's user can't start a root one. Terminal's root `login` isn't named `sshd`, and a test checks that case. |
| Setting `SSH_ORIGINAL_COMMAND`, `SSH_CONNECTION` or the PATH | **Blocked.** The variables can only refuse an origin, never grant one. `detect_ssh` grants only from the `ps` ancestry, and that `ps` is `/bin/ps`. |
| Setting `ctx.obj["origin"]` | **Not reachable from outside.** It is set only by an in-process Python caller (the tests and `remote_child.py`). The CLI has no flag or variable that sets it. |
| Stripped Claude markers | **Still blocked.** The `sshd` and root check doesn't depend on the markers (tested with the markers set and with them stripped). |
| Injection through the forced command | **Blocked.** The wrapper calls `shlex.split` and then `os.execv`, so no shell runs. `remote` takes the words unprocessed with interspersed options off. The builders put any free text after `--`. `--ref` is passed as a single `--ref=value` word. Tests pass `;`, `&&`, `$()`, backticks, newlines and `--ref` inside a note through literally, and a sentinel file stays absent. |
| Another Discord user id | **Refused.** `remote.py:225` matches `discord:\d+` in full against `CONTROL_DISCORD_USER_ID`, and refuses when that isn't set. `discord:999`, a trailing space, `terminal:` and no actor are all tested. |
| Replaying a decision | **Answered once.** `approvals.decide()` looks up the `(approval_id, source_ref)` pair before taking the lock and again inside it (`approvals.py:604`, `:621-634`), and refuses any non-human origin (`:541`, `:601`). Sending the same ref twice gives the same answer and records one event. |
| A command outside the allowlist | **Refused.** `match()` checks two-word names first and then one-word names, and accepts only exact keys. The generated test covers every leaf that isn't on the allowlist, including `run`, `schedule`, `db` and every path-taking command. |
| A scheduled or headless run | **Refused** by `log.current_job()` before the origin is checked. This holds on its own with `headless.NEVER` emptied, and a test checks it. |

**What remains is the documented limit, not a code finding.** Any real SSH login to the Mac counts as a real `sshd` origin. The real guard is therefore the single `restrict,command=,from=` entry in `authorized_keys` with key-only login, and setting that up is Ting Yu's ticket 14. ADR 0004 and the setup guide say this.

**Coverage note.** I ran `security-review`, but it scanned this checkout's whole-feature diff rather than ticket 11's. An independent adversarial subagent scoped to ticket 11 stopped before reaching any conclusion. So the security table above is my own pass alone. It is backed by reading the code and by the passing tests named in it, without a second reviewer.
