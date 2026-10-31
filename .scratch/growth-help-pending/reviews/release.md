# Release: `/growth help` and `/growth pending`

```
Recommendation: open the PR, and Ting Yu merges it
Tested commit:  crew/growth-help-pending @ 1095412 (base origin/main @ c11eb61, 0 commits behind)
Suite:          4755 passed, 0 skipped, on Python 3.12.14 and on 3.14.7
```

This file's commit adds only this file and `pr-body.md`, so the run above stands for the branch tip.

**Three things to read before pushing.**

1. **`uv sync` did not give this worktree the project's Python.** The repo has no `.python-version`, and `requires-python` is `>=3.12`, so a fresh `uv sync` picks the newest Python installed: 3.14.7. The main checkout's `.venv`, which the engine and `bin/growth-remote` use, is 3.12.14. I ran the suite on both. The worktree's `.venv` is now 3.12, made with `uv sync --python 3.12 --frozen`. The reviews and QA don't record which Python they ran on.
2. **The repo is public.** QA quoted the live backlog, including the name of Ting Yu's next unbuilt idea. The conductor took that name out of `reviews/qa-01.md` and `issues/02-…md` and rewrote the unpushed commits, so it never reached GitHub. Only `.scratch/` changed, so the suite run above stands for the code. There are no credentials, Discord ids or real addresses here, and `jane.tan@gmail.com` in the tests is a fixture.
3. **This branch tracks `origin/main`.** Push it by name, with `git push -u origin crew/growth-help-pending`. The checkout has no `push.default` set, so a bare `git push` should refuse, but don't rely on that.

## Readiness

| | Item | Note |
|---|---|---|
| n/a | `reviews/quality-gate.md` says GO at the current SHA | Route S has no quality gate. QA and the final re-review are the evidence. See waiver W1 |
| ✅ | Every `code-review-*.md` approves, `final` included | `code-review-01.md` is one file with three verdicts: changes-requested at `83b912c`, then approve at `d80d73f`, then approve at `d7d3211`. Route S has no `final`. `git diff d7d3211 1095412`, outside `.scratch/`, is empty, so the approved code is the code at the tip |
| ✅ | Up to date with its base, suite green after that | `git rev-list --count HEAD..origin/main` gives 0 after a fresh fetch. Suite above |
| ✅ | No commit touches a blocked path | `git diff --name-only c11eb61..HEAD` has nothing under `inputs/`, `design-system/`, `data/growth/` or `.github/`, and no `.env` |
| ✅ | No secrets or credentials in the diff | The checklist's grep finds only setting names, a fixture name and the word "token" in QA's prose. A second search for real key, webhook and private-key shapes finds nothing |

## Package

| | Item | Note |
|---|---|---|
| n/a | Version bumped | `pyproject.toml` has stayed at 0.1.0, there are no tags, and the card sets no per-PR bump |
| n/a | `CHANGELOG.md` entry | The repo has none. The card says release notes go in the PR body |
| ✅ | Release notes | In the PR body |
| ✅ | PR body | `.scratch/growth-help-pending/pr-body.md`, the path the brief gave |

## Runtime

| | Item | Note |
|---|---|---|
| n/a | Migrations | None: 18 `.sql` files at `c11eb61` and at the tip, and none in the diff. Checked both ways on temp databases, on Python 3.12 (below) |
| n/a | New configuration or environment variables | None. Nothing under `config/` changes, `pyproject.toml` and `uv.lock` are unchanged, and the source diff adds no environment variable |
| n/a | Feature flags | None. Both commands do nothing until someone sends them, and no scheduled run can send them. To stop using them, stop sending them |
| ✅ | Schedule | No change. No job, time or setting moved, so `jura-growth schedule install` isn't needed |
| ✅ | Dispatch | No change. The contract says Dispatch runs `jura-growth remote` with Ting Yu's text as sent (`docs/dispatch-contract.md`, Transport and D2), and growth's `ALLOWLIST` is the gate. I read the contract, not Dispatch's code, which isn't in this repo |
| ✅ | What to watch | Below |

**An older checkout still runs.** Using `git archive c11eb61` beside the tip, both on Python 3.12 and on temp data folders:

| Database made by | Then run | Result |
|---|---|---|
| The tip | The older code: `status`, `approvals` | Exit 0 both. Schema hash `9f26393b21d5` before and after, 18 migrations before and after |
| The older code | The tip: `pending`, `status` | Exit 0 both. Same schema hash, 18 migrations, and `pending` answers |

The older code has no `pending` command, and answers `No such command 'pending'`.

### After merge

From `repos/growth`, the main checkout, which is clean and on `main` at `c11eb61`:

```bash
git pull --ff-only
uv sync
.venv/bin/python --version    # should still say 3.12
```

- The install is editable, and `bin/growth-remote` runs `<repo>/.venv/bin/jura-growth`, so the next call uses the new code. Nothing needs restarting.
- `uv.lock` is unchanged, so `uv sync` should install nothing. uv reuses a `.venv` that fits `requires-python`, which is why the version line should hold. I didn't run this in the main checkout, so the check is there to confirm it.
- No PRD moves. Ticket 01 is a dated amendment to `prd-jura-mission-control-2026-10-25.md`, and that PRD's own state doesn't change with this release.

### What to watch

**Not verified by anyone yet: the real SSH hop, and how Discord renders the answers.** The origin check rightly refuses a Claude session, so QA drove `remote` in process with an SSH origin, and read the exact text against Discord's Markdown rules. Nothing was rendered in Discord. Ting Yu's first send is the check.

**Right after the pull:**

1. Send `/growth help`. Expect 20 lines with no "(cut" at the end: the intro and 19 commands, about 1,444 characters.
2. Send `/growth pending`. On today's state, expect APP-005 under "Waiting for you", with A-0004, its date of Sat 14 Nov, 23:04 SGT, and `/growth apps release-plan APP-005`. That approval runs out on that date. After it, the line reads "stays on its preview", and the same answer gives the command to ask again.
3. Paste `/growth pending` as a plain message in `#control`. This checks waiver W3. If it is refused, reopen defect 03.
4. Check how the bare preview link shows, the next time a preview line appears. QA couldn't tell whether it unfurls as an embed.

**Within five minutes of the pull:** Dispatch polls `apps handoffs` about every five minutes, so its next poll runs the changed `remote.py` over the real hop with no one sending anything. Read-only check, from `repos/growth`:

```bash
sqlite3 "file:../../data/growth/growth.db?mode=ro" \
  "select ts, json_extract(payload_json,'$.ref'), json_extract(payload_json,'$.exit_code') from events where kind='remote.command' order by id desc limit 3"
```

Expect `poll:` refs with exit code 0.

**For the first day:**

- The next morning's one-pager should read as it did. `releases.health_lines` now shares its classification with `pending`. The reviewer compared the old and new function byte for byte on eleven states, and they matched.
- `remote.masking_degraded` in the event log, and any `refused:` on a command that used to work.
- If `pending` says `growth.db has an unfinished write` while a job is simply running, that is the known wording in the follow-ups. It clears by itself.

## Rollback

**To revert:** the merge commit of the PR, with GitHub's Revert button or `git revert -m 1 <merge commit>`, through a PR. The branch's own range is `c11eb61..crew/growth-help-pending`, from `4bd23fc` to this file's commit.

**On the Mac afterwards, from `repos/growth`:**

```bash
git pull --ff-only
uv sync
```

No schedule change and no database step. `/growth help` and `/growth pending` then answer `refused: … isn't a control command`, with exit 2, and every other command behaves as it did at `c11eb61`. The older code ran against a tip-made database above.

**What a revert doesn't undo:**

| Left behind | What to do |
|---|---|
| `remote.command` events for `help` and `pending`, in `growth.db` and the JSONL mirror | Nothing. The review found nothing in `jura_growth/` that reads them, apart from the code that writes them |
| Answers already posted in Discord | Nothing. Delete them by hand if wanted |
| What Ting Yu did on `pending`'s advice, such as a claim from `apps release-plan` | Nothing. Those commands exist on `main` already and stand on their own |
| The dated amendment in `prd-jura-mission-control-2026-10-25.md`, which is outside this repo | Add a dated line saying it was reverted |

Neither command writes anything else: no table, column, file or backlog row. There is no data that can't be un-written, beyond the events above.

## Waivers for Ting Yu

Merging accepts these.

- **W1. QA ran at `d80d73f`, not at `d7d3211`.** The last commit fixes QA's defect 02 and adds the decide line, and the re-review at `d7d3211` covered that diff with its own runs. As a check of my own, I ran QA's seven red tests from `14f9fa6` on a copy of the tip: all four for defect 02 now pass. No QA pass was repeated by hand on `d7d3211`.
- **W2. The real SSH hop and Discord's rendering are unverified,** as above. Ting Yu's first `/growth help` after the merge checks them.
- **W3. Defect 03 was closed on a document, not a test.** The conductor closed it because Dispatch PRD AC-D2.2 says a first word of `/growth` is dropped from a plain message. QA's three defect 03 tests still fail on the tip, as expected: they ask growth to accept the prefix, and it doesn't. The contract's Transport section says "verbatim", and I read neither Dispatch's PRD nor its code. Step 3 of "What to watch" settles it. The cost if it is wrong is one refused message, and the refusal lists the right words.

## Follow-ups, not in this release

**Named by the reviews and QA, and left as they are:**

- The approve reply still gives no next step. Approving a release records the decision and says nothing about `apps release-plan`, which is how this ticket began. `pending` now answers it when asked. The ticket keeps the reply, and the card's wording, out of scope.
- Capitalised commands are refused. `Pending` and `PENDING` exit 2, and a phone keyboard capitalises the first word of a plain message, so this is likely in `#control`. Every command has always behaved this way.
- The held-lock wording. While a writer is simply running, the answer says `growth.db has an unfinished write. Send /growth status to clear it.` There is nothing to clear. The wording is shared with the read model, and a test asserts it.
- Markdown in names. A scraped group name or a hand-edited idea can render bold or as a masked link. Mentions, addresses and numbers are defused or masked. `/growth approvals` already does the same.
- A non-empty database file with no tables still migrates. `is_empty` catches only a 0-byte file, so the first `pending` lists each missing table, `remote` migrates the file, and the second says "Nothing pending". It takes dropped tables to get there.
- D7, Dispatch's promotion of the exact SHA `apps release-plan --json` hands out, stays later, and needs a Dispatch PRD amendment. Until then the merge is by hand.

**Smaller nits from the same reports:**

- `/growth approve A-nnnn` in the decide line doesn't mention the `key=value` arguments `group-rules` also takes.
- "and 3 more stay on their previews" has no pointer to `/growth one-pager`.
- Approved releases list in build order, not soonest to run out.
- Any command other than `help` and `pending` still creates or migrates a missing or empty database. That is the ordinary route back, and it is by design.
- `on_main` can take 30 seconds per claimed app if git hangs. QA didn't retest this.
- Reasons name internals, such as `(ValueError)`.
- After `pause all`, `pending` still heads its list "Growth is on it".
- The merge reply ends in `jura-growth apps released`, while `pending` says `/growth apps released`.

**Found during this release:**

- Pin the Python, with a `.python-version` of 3.12, or say so on the card. Until then every fresh worktree tests on a version the jobs don't use. The card's "Python 3.12 venv" holds only for the main checkout.

## Options for G4

The ship path on the card is a GitHub PR from `crew/growth-help-pending` into `main`. The crew doesn't merge into `main`.

| Option | What happens next | View |
|---|---|---|
| **Open a PR** | The conductor settles Q1, then runs `git push -u origin crew/growth-help-pending` and `gh pr create --base main --head crew/growth-help-pending --body-file .scratch/growth-help-pending/pr-body.md`. Ting Yu merges, does "After merge", and sends the three checks. The worktree stays for any feedback | **Recommended.** It is the card's path, nothing live changes until the merge and the pull, and the waivers sit in front of him |
| **Merge locally** | Merge into local `main` in the main checkout, rerun the suite there, and push `main`. The commands go live at once, since that checkout is what the engine runs | Not recommended. It skips the PR body, and the crew may not do it |
| **Keep the branch** | Nothing changes. The worktree and branch stay, nothing is pushed, and `/growth pending` stays refused | Reasonable only if he wants a follow-up in first. A-0004 still runs out on 14 Nov either way |
| **Discard** | After he types `discard`: the branch, its seven commits plus this one, and the worktree are deleted | Not recommended. Offered because the checklist asks for all four |

**Q1, before the push: does the idea's name go public?** Recommended: replace the name with "his next idea" in `reviews/qa-01.md` and `issues/02-…md`, as one commit before the push. It costs one line each and changes no finding. The other answer is to accept it, since earlier QA folders on `origin/main` already hold backlog snapshots, though not this name. The name isn't a secret, but a public push can't be taken back, so it isn't mine to decide.

The card opens the PR "only after the user's G4 answer", while Ting Yu's standing instruction has the conductor deciding and pushing, and opening the PR at the end. That one is for the conductor, as in earlier releases. Opening the PR changes nothing live, and the merge stays his.

## Evidence

Every command ran with the card's exports, on temp data and outputs folders.

| Command | Result |
|---|---|
| `git rev-parse HEAD`, in both suite logs | `1095412` |
| `unset VIRTUAL_ENV; uv sync` then `uv run pytest -rs -p no:cacheprovider -o addopts=""` | 4755 passed, 0 skipped, in 441.01 s, on Python 3.14.7. Exit 0, and `git status --porcelain` empty afterwards |
| `uv sync --python 3.12 --frozen` in a temp venv, then `python -m pytest` with the same flags | 4755 passed, 0 skipped, in 433.06 s, on Python 3.12.14. Exit 0, and `git status --porcelain` empty afterwards |
| `tests/test_pending_qa01.py` from `14f9fa6`, on a copy of the tip, on 3.12 | 4 passed (defect 02), 3 failed (defect 03, closed, expected) |
| `git fetch origin`, then `git rev-list --count HEAD..origin/main` | 0 |
| `git diff --stat d7d3211 1095412 -- . ':(exclude).scratch'` | Empty |
| `git ls-tree -r <sha> --name-only`, counting migration `.sql` files | 18 at `c11eb61`, 18 at `1095412` |
| `jura-growth pending` on the tip, with no `growth.db` | `**Couldn't be read**`, then "growth.db doesn't exist yet", exit 0 |

**Boundaries, as they went.** Nothing was pushed, posted or merged. `jura-growth run`, `schedule install` and `schedule render` were never typed. I read the live `growth.db` once, in `mode=ro`, to explain a recent write: the newest events are Dispatch's own `apps handoffs` polls (`poll:92` to `poll:97`) and `run.quiet`, none from these runs. `app-backlog.yaml` was last changed at 23:36 on 31 Oct, and the newest plist in `~/Library/LaunchAgents` at 23:32 on 31 Oct, both before these runs started.
