# Code review 13: refusals say why, and close review 11

Reviewed `crew/approvals-first-social-depth-10-final-fixes` at `bee9118`, the delta from `2e00e94`, against `issues/13-refusals-say-why.md`. `f2ac501` only merges the feature branch's records, and `origin/main` is still `019133d`, which the tip holds. This is a narrow pass: no sub-agents, and the only mutation evidence is the developer's. File references are at `bee9118`. "Walked" means run on temp data in the stand-in root described under Evidence, with throwaway probes in the session scratchpad.

## Verdict: approve

No blocking finding is open. B2 is closed for every kind that refuses with no card, through the real `remote` command in a new process. The suite is green at 5967.

One condition travels with this verdict, and the conductor's plan already covers it. **On a loose `.env`, B2's original symptom comes back** (see F1). It doesn't block, because it fails safe and one `chmod` clears it. The file-mode check in the after-merge steps isn't optional, though, and only Ting Yu can run it, since no agent may look at that file.

## Spec

### Blocking

None.

### Should fix (for ticket 12)

**F1. A loose env file still hides every refusal's reason.** `remote.py:357-358`, `_run` at `remote.py:307-312`, `config.py:90-97`.

- **Cause, from the code:** `_env_file` prints a permissions warning to stderr when the file is readable by group or others. `_run` captures stderr into the same buffer as the answer. `handle` tests only the start of that buffer for `refused:`, so the warning leads and `_usage_refusal` replaces the text.
- **Walked on a temp env file at 0644, through `remote` in a new process:**
  - Control user in the file: `(2, 'refused', 'refused: the command was not understood')`, status `pending`.
  - Control user in the environment: the same.
  - A skip: `recorded`, and the reply's text opens with the warning twice, including the file's path and the `chmod` command. So on a loose file, that path would reach Discord in the reply. It holds no value.
  - At 0600, each answer is whole.
- **Every refusal is affected, not only the no-card ones.** Any exit-2 answer loses its reason while the file is loose, in every SSH call, because each is a new process.
- **Ruling: doesn't block.**
  - It fails safe: nothing is approved, and the status stays `pending`.
  - It predates this feature, and `remote.py` is out of scope for this ticket by its own wording.
  - It depends on a mode the warning itself tells him to fix, and one `chmod 600` clears it.
  - It does bring back review 11's retry hazard while the file is loose, which is why the check has to be real.
- **The plan is right.** Add the file-mode check to the after-merge steps, for Ting Yu to run by hand. I did not check the live file's mode, and nothing in this review looked at it.
- **For ticket 12:** test the first line that isn't a `warning:`, or capture stderr apart for a decision, as `_run(errors=False)` already allows for output read as JSON. Add one test at 0644. Have the warning stay out of the reply.

**F2. The `BadArgs` half of the developer's report: confirmed, and nothing live is affected.** Every `BadArgs` in the code starts `refused:`, by reading: `cards.py:239,241`, `group_rules.py:44` (`DAYS_HELP`, which `:78` and `:112` use), `group_rules.py:118`, `approvals.py:618,620`, and `_refuse`. The README's plug-in table now says it must. A future kind that forgets gets "not understood", and only the table stops it. The fix in F1 can cover this too.

### Nits

- **"Growth is on it" still lists a refused card's `P-nnnn`: acceptable.** Walked: the top of the same answer says "no card: Discord would mask part of the post... Nothing goes out, and it lapses Tue 10 Nov, 17:00 SGT", then `P-0001, facebook, 2026-11-10: ready (request pending)` appears under the second heading. The row is true as a state, the count leaves the post out, and it asks him to do nothing wrong. Only the heading overstates it, and only until the lapse. Tidy it in ticket 12.
- **S4 has no permanent test.** The developer used a throwaway probe, and so did I. A test-helper's behaviour needs little, so this is a nit.
- The `outreach/approval.py` `on_approve` docstring still says "The heartbeat posts the card". That is true and now only part of it.

## Standards

No finding. `cards.refuse_with_no_card` is core code that imports no agent, and both kinds call it. Commit subjects follow the card. README's `on_approve` row states the new rule.

## Security

No finding. `refuse_with_no_card` prints an id, a deadline and the refusal text, and `remote` masks the reply. No new query, send path or file read in product code.

### Blocked paths

None changed. The delta holds nothing under `inputs/`, `design-system/`, `.env`, `.github/`, `launchd/`, `data/` or `config/`. No webhook, key or long id in the added lines.

## UI

No template, CSS or `visuals.py` change, so nothing to review. X9 needn't rerun.

## Answers to the brief

### 1. B2 through the real `remote`, in a new process

`tests/remote_child.py`, `remote --json`, a temp env file at 0600, no webhook in the child, and the Discord double in the parent for the sweep.

| Case | Reply | Status | After |
|---|---|---|---|
| `social-post`, no card | `refused: A-0001's card hasn't gone out yet, so it can't be approved. It may be posting now: read it in #approvals and decide there.` | `pending` | A sweep posts the card, then `recorded, A-0001 approved.`, status `approved`, `next_item` gives `P-0001` |
| `social-post`, refused card | `refused: Discord would mask part of the post, so its card can't show the exact text. A-0001 can't be approved. Nothing goes out, and it lapses Tue 10 Nov, 17:00 SGT. You can still skip it.` | `pending` | Skip: `recorded`, status `skipped` |
| `outreach-email`, no card | The same no-card sentence | `pending`, `used_at` None | `send_due` says "nothing approved to send", 0 sent. A sweep posts the card, then `recorded`, then **1 sent**, message `sent` |

The refused card's answer doesn't claim it may be posting, which is right, and the test pins it. A retry still approves a card that went out moments before, as the rule allows. The answer now sends him to read it first, and that is what could fairly be asked of it.

### 2. The remaining report on `remote`

F1 and F2 above. The second half is confirmed on a temp file, and it doesn't block.

### 3. S3

**Closed.** Walked with a real learned name and a real refusal: the line above, with no "no card yet", and it keeps its lapse time. `test_pending_tells_approved_claimed_and_refused_apart_in_browser_mode` pins the refused line, the approved row and the claimed row, each with its count (1, 1, none). It uses `refuse_facebook`, a stubbed refusal, and that is fine for what it pins. The `P-nnnn` row is the nit above.

### 4. S4

**Closed.** `aw.card_goes_out` now calls `cards.build` and stamps only if that succeeds. With `preview` raising, `pw.decide` answers `refused` with `posted_at None`, where review 11 walked `recorded`. The docstring now says what it does. Results are unchanged: the suite has no failure. It still writes no `approval_cards` row and calls no Discord, and the docstring says so by pointing at `cards.sweep` for that.

### 5. SEC3, St4, St5, St6, the two "so"s

| Item | Status | Evidence |
|---|---|---|
| SEC3 | **Closed** | Walked on planted files. All of these are refused, and no id or token is printed: review 10's seven, `1/../<id>`, `1/%2e%2e/<id>`, double-encoded `%252e`, `./<id>`, `0<id>`, `000<id>`, `<id>/../<id>`, `x/../api/webhooks/<id>`, `api%2Fwebhooks%2F<id>`, backslashes, fullwidth digits, `<id>%20`, `+<id>`, and the live id in the second place (`9/<id>`). Allowed, correctly: a test server's id, loopback, `.invalid`, and `9/t?x=/webhooks/<id>` and `9/t#/../../<id>/t`, where the id is in the query or fragment, so the request goes to 9 |
| St4 | **Closed** | One helper, `cards.refuse_with_no_card`, called by `kinds.py:263` and `outreach/approval.py:148` |
| St5 | **Closed** | `conftest.py` uses `seed.live_env_places()`, and the guard now uses `abspath`, so it makes no lookup on the live file when it starts |
| St6 | **Closed** | The comment is back above `switched_off` |
| The two "so"s | **Gone** | See the refused-card reply above, which has one |
| Heartbeat test's name | **Closed** | `test_once_a_sweep_posts_the_card_the_same_post_can_be_approved` |

### 6. One full suite run at the tip

**5967 passed, 0 failed, 0 errors, no `SKIPPED` line**, in 364 s, the developer's figure. See Evidence.

## Evidence

- **Stand-in root:** a throwaway `jurasolutions/` under the scratchpad, from `git archive bee9118`, with copies of `design-system/` and `prd/`, and a canary at `repos/growth/.env`. `JURA_ROOT` was unset, so `paths` resolved inside it and the live path wasn't reachable. Stand-in `claude` first on `PATH`, temp data and outputs.
- **Suite, Python 3.14:** `pytest -rs -rfE -p no:cacheprovider -o addopts="" --tb=short` -> 5967 passed.
- **The live `.env`:** nothing I ran read, grepped, counted, stat-ed or aimed anything at it. Each Python process in these runs had an audit hook logging opens of files named `.env`, comparing path strings only: **0 opens of the canary**, and 22 opens across the suite, all in tests that plant their own under `pytest-of-tingy/`. A stat isn't an audit event, so this can't prove the suite makes no stat when it runs from the real tree. By reading, the two lookups the developer named are gone. The other paths that name the file are `paths.env_file`'s default, which the suite overrides, and `seed.live_env_places`, which is planted.
- **Stand-in `claude`:** its call log was never created. The worktree's `git status` is clean, and its tip is still `bee9118`.
- **Not checked:** a real SSH call (`remote_child.py` supplies the origin), how Discord renders any of this, whether Discord accepts SEC3's other spellings, the live file's mode, and the clock-across-midnight run, which is the developer's record.
- **Nothing was posted or sent,** no `jura-growth run` or `schedule` command was used, and the main checkout wasn't touched.
