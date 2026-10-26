# Code review 07: a fixture platform for the browser rehearsal (BP-07)

- **Branch:** `crew/browser-publishing-07-fixture-platform` at `ef6eb24` (commits `ff55fa4`, `ef6eb24`). Reviewed against the fixed point `b4f0895` with `git diff b4f0895...crew/browser-publishing-07-fixture-platform`.
- **Changed files (14):** `.scratch/browser-publishing/issues/07-fixture-platform.md`, `.scratch/mission-control/uat.md`, `jura_growth/agents/publish/{audit,claim,fixture,hosts,job,scope}.py`, `tests/conftest.py`, `tests/fixtures/publish-site/README.md`, `tests/test_publish_fixture_platform.py`, `tests/test_publish_fixture_run.py`, `tests/test_uat_seed_fixture.py` and `tests/uat/seed.py`. I read every one. I also read every caller of `hosts.problem`, `scope.browser_hosts` and `items.create_social`, plus `uat_stub.py` and `prompts/publish.md`.
- **Spec:** `issues/07-fixture-platform.md`, `uat.md` Part R and `uat_stub.py` (the ticket 18 guard style). I also read code review 18 for its lesson about stub pairs.
- **Date:** 2026-10-27

## Verdict: changes-requested

There is one blocking finding, B1. The fixture guard accepts a URL that Chrome reads as a non-loopback host, so acceptance criterion 2 is not met.

Everything else holds up:

- With the live data folder, the guard always refuses.
- A refused fixture never falls back to the real hosts.
- Mixing the fixture with real-host items is refused at every point: item creation, claim, `publish done`, `publish resolve` and the audit.
- No blocked path is touched.
- The full suite passes with 0 skipped.

## Evidence

All commands ran in the developer worktree `.claude/worktrees/agent-aa7f90ae34da0cc2f`, read-only. `JURA_ROOT` was set, and the data and outputs variables pointed at `mktemp -d` folders. No real Chrome or `claude` was started. The live `growth.db` was never opened. `git status` stayed clean.

- `uv run pytest -rs -p no:cacheprovider`: 2989 passed in 120s, exit 0, with no skipped section.
- `uv run pytest -rs -o addopts="" tests/test_publish_fixture_platform.py tests/test_publish_fixture_run.py tests/test_uat_seed_fixture.py`: 46 passed.
- `pyright --pythonpath .venv/bin/python` on the touched files reports 8 errors on the branch, against 4 on `b4f0895` (all 4 in `tests/uat/seed.py`, already there). The 4 new errors are in `tests/test_publish_fixture_platform.py` (ST-3).
- `git merge-tree --write-tree` came out clean against both `crew/mission-control` (`b4f0895`) and `crew/browser-publishing-04-instagram-linkedin` (`f18ceca`). In the merged tree, 04's new hosts all pass through `scope.browser_hosts()` and `hosts.problem()`, which are both fixture-aware, so 04 adds no host check that skips the fixture.

### Guard probe

`fixture.active()` was run on each URL with a temp data folder. Each derived page URL was then parsed with Node's WHATWG `URL`, the parser Chrome uses.

- **Refused:**
  - `http://publish-fixture.example`, `example.com` and `10.0.0.5` (from the branch's tests)
  - `localhost.`
  - `evil.com:8765#.localhost` and `evil.com/.localhost`
  - `[::ffff:127.0.0.1]`, `127.1` and `0.0.0.0`
  - `localhost:99999`
  - `evil.com。localhost`, `xn--localhost-xxx.com`
  - `https://`, a user name, a path
- **Accepted, and loopback in Chrome:**
  - `publish-fixture.localhost`
  - `HTTP://LOCALHOST`
  - surrounding whitespace, and tab tricks (Python and Chrome both strip them)
  - `[::1]`
  - `evil.com.localhost` (`*.localhost` is loopback in Chrome)
- **Accepted, but invalid in Chrome:** `evil.com%2F.localhost`, `%5C` and `%00`. Chrome can't open them, so they are harmless.
- **Accepted, but non-loopback in Chrome:** `http://evil.com\.localhost:8765` (B1).

### Data-folder probe

With a valid fixture URL, `fixture.problem()` gave these results:

- **Refused:**
  - the live `data/growth`
  - an unset `JURA_GROWTH_DATA_DIR`
  - a symlink in `/tmp` pointing at the live folder
  - `/tmp/../Users/.../data/growth`
  - a folder inside `JURA_ROOT`
  - `~/jura-uat`
- **Accepted:** a fresh `mktemp -d`, and `/tmp/jura-uat/data`.

`scope.permissions()` on the live folder raises `FixtureRefused` before it reads `growth.db`.

## Standards

**Should fix**

- **ST-1. The loopback guard is duplicated** (reuse rule; code review 18 ST-3: "The guard is the security boundary, so it should exist once"). The duplication is in `jura_growth/agents/publish/fixture.py:36` and `fixture.py:75-92`:
  - `_LOOPBACK` copies `uat_stub._LOOPBACK`;
  - `problem()` repeats `uat_stub.url_problem`'s shape: read the variable, check scheme and loopback, call `temporary_data_problem()`, and wrap the message "is for ... only, and ...".

  The two guards have already drifted. The fixture accepts `*.localhost` and rejects a path; `uat_stub` does neither. B1's fix belongs in one shared loopback-URL check in `uat_stub`, which both callers use.
- **ST-2. `Fixture.url_problem` repeats `hosts.url_problem`'s parsing step for step** (reuse rule). Compare `fixture.py:56-72` with `hosts.py:49-72`:
  - strip;
  - "no URL given";
  - `urlsplit` plus `.port` under `ValueError`;
  - the `hostname or "an empty host"` fallback;
  - the user-name check, word for word.

  Only the final scheme, host and port comparison differs. Extract the common parse into `hosts` and pass the rule in.
- **ST-3. New pyright errors in a touched file.** `docs/agents/crew.md`, Commands, Typecheck, says: "don't add new errors in files you touch". `tests/test_publish_fixture_platform.py:159` (twice), `:165` and `:180` each access `request.id` or `request.used_at` on an `Approval | None`. Add an `assert request is not None` in `claimed()` or the test.

**Nit**

- **ST-n1. A function-level import with no reason given.** `hosts.py:38` imports `fixture` inside `problem()`, but `fixture` imports only `uat_stub`, so there is no cycle. Move the import to module level, as `scope.py` and `claim.py` do.
- **ST-n2. The same fixture check repeats in seven places** (possible Repeated Switches / Shotgun Surgery). `site = fixture.active(); if site is not None: ...` appears at:
  - `hosts.py:40`
  - `scope.py:47`
  - `audit.py:260`
  - `job.py:40` and `job.py:180`
  - `claim.py:137` and `claim.py:234`

  `audit()` also takes both `hosts` and `site`, but with the fixture on, `hosts` is already `(site.host,)` and is then ignored. A single "address rule for this run" from `hosts`, used by the audit, would remove the second parameter.
- **ST-n3. Test helpers are copied.** `approved` and `chrome()` in `tests/test_publish_fixture_run.py:37-49` are copies of `tests/test_publish_run.py:37-49`; move them into `publish_world` or `publish_transcripts`. The fixture URL literal is repeated across both new test files and `seed.py`.
- **ST-n4. A refusal surfaces as a traceback.** In `publish done`, `publish resolve` and `social submit`, a refused fixture comes out of `hosts.problem()` as a masked traceback, not a `refused: ...` line. It still fails closed with a non-zero exit, so this only affects how the error reads.

**Clean**

- Both commit messages are plain sentence-case imperatives that match the history.
- `conftest.py` clears the new variable in `isolated`.

## Spec

The acceptance criteria against the code:

- **AC1, met.** "With the fixture platform configured on a temp data folder, the publish job targets only the fixture host; any other host is refused."
  - The argv has one rule, `ClaudeInChromeDomain(<fixture host>)`.
  - `publish next` won't hand out an item off the fixture (`claim.py:137`).
  - `page_url`, `publish done --url` and `publish resolve --url` go through `hosts.problem` (`items.py:158`, `commands.py:164`, `commands.py:272`).
  - The audit checks every address against the fixture (`audit.py:260`).
  - Tests: `test_publish_fixture_platform.py` and `test_publish_fixture_run.py`.
- **AC2, not met for one input (B1).** "With the live data folder, or a non-loopback host, the fixture platform is refused." The live folder is refused, and so are ordinary non-loopback hosts. A backslash host is accepted.
- **AC3, open (Ting Yu's step).** "At R1, try a parameter allow rule for file_upload paths ... record whether Claude Code honours it in the ticket's Comments." It needs real Chrome and a real `claude -p`. `uat.md` R1b gives the two probes, and the Comments hold a placeholder. The ticket can't close until the result is recorded.
- **AC4, met.** "`uv run pytest -rs` passes with 0 skipped." See Evidence.
- **"Wire it into `uat.md` R1-R6 and the UAT seed": met.** This covers Part R, `fixture-post` and `fixture-join`, and the seed's refusals (`tests/test_uat_seed_fixture.py`).
- **Design choice, accepted.** The fixture is a switch that replaces every platform's hosts, not a new platform name. It still gives "its own ClaudeInChromeDomain rule" and lets the rehearsal drive each platform's own prompt section. The developer explains the choice in the ticket's Comments.

**Should fix**

- **SP-1. The real prompt contradicts the fixture permalink, so R1 can fail for a reason the rehearsal isn't testing.**
  - `prompts/publish.md:70` says "its permalink, on the platform's own host".
  - `prompts/publish.md:88` says the permalink is "an address on `www.facebook.com` with `/posts/` or `story_fbid` in it. Use that address".
  - The fixture redirects to `post.html?id=<n>` (`tests/fixtures/publish-site/page.html:46`), and `uat.md` R1 expects `publish done` with that address.

  A model that follows the prompt may stop as `unidentified`, or try a `facebook.com` address. The domain rule denies that address and the audit fails the run. Either way R1 would show a false failure. Make the two agree before R1 runs: either word the prompt as "the address the post's timestamp links to", or make the fixture's composer section say it stands in for the platform. Note that editing the prompt changes the production prompt.

**Nit**

- **SP-n1. The guard checks only the data folder.** The spec says "impossible to enable in production data". The config, outputs and PRD folders may still be live. The ticket 18 stubs work the same way, and with a live `config/social.yaml` the real `page_url` is refused, so no item is made. This is consistent and safe; it's noted for the record.
- **SP-n2. R5 can't pass until BP-06.** `fixture-join` seeds R5, but `prompts/publish.md` still lists group joins as not yet enabled. `uat.md` already says "R5 after BP-06".

## Security

`security-review` was applied inline to this diff, because its default target is the current checkout's branch, not this one. I focused on the new production override for where Chrome may go.

**Blocking**

- **B1. The fixture guard accepts a host that Chrome reads as non-loopback.** The problem is at `jura_growth/agents/publish/fixture.py:86`. Python's `urlsplit` keeps a backslash in the netloc, so with `http://evil.com\.localhost:8765`:
  - `parts.hostname` is `evil.com\.localhost`;
  - `host.endswith(".localhost")` is true, and the fixture is accepted.

  Chrome's WHATWG parser treats `\` as `/` for http, so the seeded target `http://evil.com\.localhost:8765/page.html` is `http://evil.com/.localhost:8765/page.html` in the browser. I reproduced this end to end on a temp folder:
  - `seed --scenario fixture-post` makes the item;
  - `claim.claimable()` returns it with that target;
  - the argv's only rule is `ClaudeInChromeDomain(evil.com\.localhost)`.

  Two later layers probably stop the post:
  - Claude Code's matching of that odd domain rule, which is unverified;
  - the audit, which reads the tab as `evil.com` and fails the run, but only after the run has acted.

  Neither is the guard of record. The module docstring says `fixture.py` "is the one place that decides whether the fixture may be used", and AC2 asks for refusal. The same parser differential is in `Fixture.url_problem` (`fixture.py:56-72`) for page addresses. There, exact host equality keeps it out, as long as the env value is clean.

  **Fix:**
  - in `problem()`, refuse any value containing `\`;
  - require the host to match `localhost`, `127.0.0.1`, `::1` or `[a-z0-9-]+(\.[a-z0-9-]+)*\.localhost`, so `%`, `;` and other characters are refused;
  - reject `\` in `Fixture.url_problem` too;
  - add the backslash and percent cases to the parametrised refusal test.

**Nit**

- **SEC-n1. The domain rule names a host, not a port** (`scope.py:54`). `ClaudeInChromeDomain(localhost)` or `(127.0.0.1)`, both of which the guard accepts, would give the page tools every local service on any port. Only the audit enforces the port, and only after the run. `uat.md` uses the dedicated `publish-fixture.localhost`, which limits this in practice. Accepting only a `*.localhost` name (not bare `localhost` or `127.0.0.1`) would close it. `localhost:0` is accepted too, which is harmless.

**Checked and clean**

- **The live data folder can't enable it.** Every probe was refused (see Evidence).
- **A refused fixture never falls back to the real hosts.**
  - `precheck` raises first (`job.py:40`), so the run fails before Claude starts and before anything is claimed.
  - `scope.permissions()` raises before it reads the db.
  - `publish next` returns the refusal and claims nothing (`claim.py:234`).
- **A half-set fixture can't mix real hosts with the fixture.** I checked each combination:
  - a fixture on with a real `page_url`: no item is made;
  - an item approved before the fixture was switched on: not handed out (`test_publish_next_hands_out_no_item_whose_target_is_off_the_fixture`);
  - a claimed real item while the fixture is on: `publish done` refuses its facebook permalink, and the run's only domain rule is the fixture's;
  - the reverse, a fixture item with the fixture off: Chrome has no rule for its host, and `hosts.problem` refuses the fixture permalink.
- **A model in a live run can't switch the fixture on.** Setting the variable in its own command would still fail on the live data folder.

## Blocked paths

None are touched. The diff has nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.

## UI

The fixture HTML is unchanged; only its README changed. There are no UI files in the diff, so `crew:web-design-review` didn't apply.

## Summary

- **Standards:** 3 should fix and 4 nits. The worst is ST-1, a second copy of the loopback guard.
- **Spec:** AC2 is unmet (B1), AC3 is open for Ting Yu, 1 should fix and 2 nits. The worst is SP-1, the prompt's permalink rule against the fixture.
- **Security:** 1 blocking (B1) and 1 nit.
