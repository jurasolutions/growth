# Code review 12: the `apps` commands on the remote allowlist (MC-11b)

- Branch: `crew/mission-control-12-remote-apps-commands` at 063c7ec, one commit from ffbf34d
- Compared with: `git diff ffbf34d...crew/mission-control-12-remote-apps-commands` (4 files, +501 / -15)
- Spec: ticket `issues/12-remote-apps-commands.md`; PRD `prd-jura-mission-control-2026-10-25.md` §4.6 A3 (amended 2026-10-27), §4.7, §4.8 D6 to D8, §5.9, §5.10, §5.12; `docs/dispatch-contract.md`; code review 11; test strategy v3 (§4.1, §11.2 row MC-11b); technical review v2 N5
- Reviewed: 2026-10-27

## Verdict: approve

There are no blocking findings. Every new command keeps ticket 11's origin and `CONTROL_DISCORD_USER_ID` checks, and option values can't be turned into arguments the commands didn't ask for. The unmasked `prd_text` reaches only Dispatch's JSON. It never reaches the `text` Dispatch posts, and it never reaches the `remote.command` event. Two *should fix* items are edge cases that the reviewer reproduced: a newer handoff can be stuck behind an oversized one, and a secret-looking value in a PRD breaks the hash promise without any warning. Both can go into a follow-up commit before the merge.

## Evidence

- `uv run pytest -p no:cacheprovider`, run in the developer worktree with `JURA_ROOT` set and temp data and outputs folders: **2448 passed** in 123s.
- `uv run pytest tests/test_remote.py tests/test_remote_apps.py`: 204 passed.
- `pyright` on the branch's `jura_growth/remote.py`: 0 errors, so nothing new.
- `git merge-tree --write-tree crew/mission-control crew/mission-control-12-remote-apps-commands` against 55b2f86: no conflicts.
- **Blocked paths:** none touched. The diff changes `docs/dispatch-contract.md`, `jura_growth/remote.py` and two test files only. It doesn't reach `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **Secrets:** no key, token or ID value is added.
- **Reviewer probes** were run through `remote` with the branch's own fixtures, from a scratch test file that is not committed:
  - p1: an approved PRD holding `sk-ant-…` is handed out with `[redacted]` in `prd_text`, and its SHA-256 no longer matches `prd_sha256` (S2).
  - p2: an approved PRD holding `jane.tan@example.com` is handed out with the address unmasked in `prd_text`, and the address does not appear in `text` (Q1).
  - p3 to p8 (injection):
    - `--branch "a\n--force"` and `--branch "x;rm -rf ~"` exit 1, refused by `check_build`.
    - `--` as a word, `--help`, and `apps handoffs --json` exit 2 at the allowlist.
    - `--task=` exits 1 with "must be a Dispatch task id".
    - `apps release-plan --help` reaches the command as the app id `--help`, because it goes after `--`, and exits 1.
    - No release request is raised by any of them.
  - p9: APP-101 (fits `apps handoffs --json` alone) and APP-102 (small) both handed off. Two polls through remote both return APP-101 with `handoff: null` and `more: 1`. APP-102 is never handed out (S1).

## Standards

| Rank | Where | Finding |
|---|---|---|
| should fix | `jura_growth/remote.py:383` (`_trim_handoffs`) and `jura_growth/agents/apps/builds.py:260` (`handoffs_json`) | **Duplicated policy, measured two ways.** Both files carry the rule "drop into `more`, or null the lone handoff with a problem", the same 64 KB constant (`remote.py:50`, `builds.py:37`), and the same problem sentence, copied word for word. They disagree on the order (see S1 under Spec) and on the measure: `builds._size` uses `indent=2`, while `payload()` uses compact JSON plus remote's envelope. The core can't import the plug-in, so a shared helper is not the fix. Make remote's trim a backstop that matches builds' order: null the oversized entry and keep the newer ones that fit. Pin the problem text in one place, through a test that compares the two. |
| nit | `jura_growth/remote.py:308`, `:316` | `apps handoffs` runs the plug-in twice, first as text and then as `--json`. Each run reads the database separately, so a handoff that lands between them shows up in one and not the other. A plain-text call also exits 1 if the JSON run fails. The docstring says why it works this way. Deriving `text` from the JSON object, or accepting the gap in a comment, would close it. |
| nit | `jura_growth/remote.py:129`, `:151`, `:155`, `:166` | `_with_options` is generic but hardcodes `<APP-NNN>` in its refusals. Its `wanted` string also rebuilds what the `Entry` usage string already holds, so the two have to be kept in step by hand. Pass the usage string in, or name the builder for what it builds. |
| nit | `jura_growth/remote.py:166` | The line is 185 characters long. The file's one-row-per-line allowlist rule allows it, and no linter is configured. |

Otherwise the code follows the repo's conventions:

- The core never imports the plug-in: `_handoffs` runs `apps handoffs --json` in process (README plug-in rule).
- Free words still go after `--`, and option values go over as `--option=value`.
- `_record` still writes the words and the answer only, never `handoff` (code review 11).
- The allowlist and the contract rows stay sorted, and a test enforces that.

## Spec

| Rank | Where | Finding |
|---|---|---|
| should fix | `jura_growth/remote.py:383-397`; contract `docs/dispatch-contract.md:144` | **A newer handoff can wait forever (probe p9).** The contract says handoffs that don't fit "come on a later poll, once the earlier ones are reported built". `_trim_handoffs` pops the newer handoffs first, then nulls the last one left. A PRD that fits `apps handoffs --json` on its own but not beside remote's text therefore becomes `handoff: null`. Dispatch is told not to build a null entry, so it is never reported built, and every newer handoff stays in `more` on every poll. Today's app PRDs are 4 to 8 KB and the window starts near 58 KB, which is why this is *should fix*, not blocking. Fix: with more than one entry, null an oversized entry before dropping newer ones (builds' own order), and add p9 as a test. |
| should fix | `jura_growth/remote.py:316` (`_handoffs`) with `jura_growth/cli.py:50` (`_Cli.main` → `config.redacted_output`); contract `:140`; PRD §4.6 A3 as amended 2026-10-27 ("the exact bytes handed out") | **The hash promise breaks silently (probe p1).** Every byte `jura-growth` prints passes through the redacting stream. A PRD holding a configured secret, or a value shaped like a secret (`sk-ant-`, `re_`, `whsec_`, `Bearer`, or any run of 8 or more characters of a configured secret), is handed out with `[redacted]` in it. The `prd_sha256` stays the approved one. The secret does not leak, which is good. But Dispatch gets a brief that is not the approved bytes, with no `problem`, and the contract only says Dispatch "may" check the hash. Fix: in `_handoffs` (or in `builds.handoff`, which ticket 10 owns), refuse an entry whose `config.redact(prd_text) != prd_text`. Set `handoff: null` with a problem such as "the PRD holds a secret-looking value; it isn't handed out", and add p1 as a test. |
| nit | `tests/test_remote_apps.py:313` | AC-M9.9 through remote checks the done PRD for the release approval only. SC9 says it carries "the ship date and a sign-off line naming both approvals". Ticket 10b covers this in process, so one more assertion here is enough. |
| nit | contract `docs/dispatch-contract.md:77`, PRD §4.8 D7 | "(later Dispatch D7)" overstates what is there today. D7 expects the SHA from `apps release-plan --json`, but the remote answer carries the SHA only inside `text`. The claim is also spent once the command runs. If Dispatch loses the answer, a retry gets "already used", because `--ref` makes retries safe only for decisions. That is ticket 10b's design and fine while Ting Yu merges by hand. Word the row as "for Ting Yu to run on the Mac". |
| nit | `jura_growth/remote.py:166`, PRD §5.10 | The PRD writes `--branch <b>`, and the usage string expands it to `<branch>`. This is cosmetic and matches the file's style. |
| note | contract `:127-148`, AC-M9.2 | The top-level `handoff` is the `apps handoffs --json` wrapper (`{contract, more, handoffs: [{…, handoff: {repo, base, prd_text, prd_sha256, approval}}]}`). AC-M9.2 names the inner object. This follows D6 ("for each build handoff") and the contract documents it accurately. It is recorded here so that Dispatch's side is built against the wrapper. |

Covered as asked:

- AC-M10.1: all four commands, through the table rows in `tests/test_remote.py:184-190` and through `tests/test_remote_apps.py`. One of them runs in a real process.
- AC-M10.2: the generated leaf test still refuses `apps context`, `apps submit-prd` (a `click.Path`) and every other leaf not on the allowlist.
- AC-M9.2, AC-M9.7, AC-M9.8 and AC-M9.9 through remote.
- AC-M15.1: the full suite passes.

## Security

The `security-review` method was applied to this diff, and probes p1 to p9 were run. No high-confidence vulnerability was found.

- **Origin and control-user checks (ticket 11).** `handle()` checks the job, the origin and `_attribution` before `match()`. A new command can't skip those checks. `test_no_apps_command_runs_for_anyone_but_the_control_user_through_dispatch` covers four cases for all four commands: a refused origin, a stranger (`discord:999`), no actor, and a scheduled run. Each one exits 2, claims no approval, raises no release request and returns no `handoff`.
- **A stranger's approve can't drive a build.** A handoff exists only after an `app-build` approval (`builds.on_approve`). `approve` through remote has the same origin and control-user checks (ticket 11; ADR 0004). `apps built` from a stranger is refused before it runs (as above).
- **Argument injection through `built` and `released`.** Each option is accepted once, in either spelling. Any other word starting with `-`, including `--` and `--help`, is refused. Values go over as `--option=value`, and the id goes after `--`. `releases.check_build` then pins the formats with `fullmatch`:
  - task: `T-\d{4,}`
  - branch: a plain name, with no `..`, no `.lock`, no leading `-` and no shell characters
  - SHA: a full 40- or 64-character hex SHA
  - preview: a URL on the landing page's own Pages project

  The only place the branch is printed into a shell line is the hand-run merge plan. This was checked with probes p3 to p8.
- **Where `prd_text` can go.**
  - It is only in the `--json` answer's `handoff`. `_masked` masks `text` and `approvals` and leaves `handoff` alone, as the contract (`:140-141`) says.
  - `_record` writes no output, and a test checks that `prd_text` is not in the event.
  - The plain-text answer never carries it (`test_handoffs_in_plain_text_is_the_listing_alone`).
  - Secrets can't leave through it, because the redacting stream masks them. That is what breaks the hash (S2 above).
  - What Dispatch does with the brief after that is on Dispatch's side of the contract, outside this repo. For example, it may echo the brief into the task's Discord thread or its transcript.

### Can a secret or a person's name get into a PRD at all?

**A secret:** no gate checks for one. `factory.submit` runs `validate_factory` and the brand check on the PRD's copy, not on the whole file. A secret would still be masked on the way out (S2).

**A person's name or address:** nothing stops one either. The factory's context includes scout lead observations as free text (`agents/apps/inputs.py:66`), and no privacy check runs on submitted PRDs. Probe p2 shows an address passing through `prd_text` unmasked. The PRD is also attached to the `app-build` approval card, and Ting Yu reads it before approving, so a human sees it first. This was already true before ticket 12, which only carries the PRD further. See question Q1.

## Questions for Ting Yu

- **Q1.** Should an app PRD that names a person, or holds an address or a secret-looking value, be refused before it is filed? That would add a privacy check to `factory.submit`, in a follow-up to ticket 10. An alternative is to refuse it at handoff with a `problem`. **Recommended:** yes, refuse it at submit, using `privacy.for_discord(text) != text` (after `load_for_masking`) as the test, so the factory regenerates it. Keep S2's check at handoff as the backstop. Then add a line to D6 that `prd_text` is for the task's brief only and is never posted to Discord.
