# Code review 18: a local D1 stand-in for UAT (MC-18)

- **Branch:** `crew/mission-control-18-uat-d1-stub` at `a619072` (commits `b3bdbad`, `a619072`). Reviewed against the fixed point `3cf76e8` with `git diff 3cf76e8...crew/mission-control-18-uat-d1-stub`.
- **Changed files (10):** `.scratch/mission-control/uat.md`, `jura_growth/agents/outreach/send.py`, `jura_growth/cloudflare.py`, `jura_growth/paths.py`, `tests/conftest.py`, `tests/d1_stub.py` (new), `tests/resend_stub.py`, `tests/test_d1_stub.py` (new), `tests/test_uat_seed_outreach.py` and `tests/uat/seed.py`. I read every one, along with every D1 caller: `suppression.py`, `agents/outreach/sync.py`, `agents/scout/registry.py`, `agents/apps/inputs.py` and `send.status`.
- **Spec:** `issues/18-uat-d1-stub.md`, plus the conductor's note on it, and `uat.md` (X13).
- **Date:** 2026-10-27

## Verdict: approve

There are no blocking findings.

- **No blocked path is touched.** The diff changes nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- **The full suite passes with 0 skipped.**
- **I couldn't defeat the override.** The probes below never reached a non-loopback host. With the override set, the real Cloudflare token is never read or sent. A refused override never falls back to Cloudflare. A live data folder, a missing one, a symlink into the live folder and a `..` path are all refused.

Five *should fix* items remain. SEC-1 is the one to fix before UAT runs. The rest can be fixed on this branch or in a follow-up:

- a D1 stub can be set without the Resend stub (SEC-1)
- a uat.md conflict with `crew/mission-control` (SP-1)
- new pyright errors (ST-1)
- a dead alias (ST-2)
- a duplicated stub-resolve shape (ST-3)

## Evidence

All commands ran in the developer worktree `.claude/worktrees/agent-adcfb7705018f23c8`, read-only. `JURA_ROOT` was set, and the data and outputs variables pointed at `mktemp -d` folders. Nothing reached Cloudflare or Resend, and the live `growth.db` was never opened.

- `uv run pytest -rs -q -p no:cacheprovider`: exit 0, 2223 tests passed. The log has 2223 `.` and no `s`, `F` or `E`. The doubled `-q` (from `addopts`) hides the summary line.
- `uv run pytest -rs tests/test_d1_stub.py tests/test_uat_seed_outreach.py tests/test_outreach_send.py`: 101 passed in 14.07s.
- `pyright --pythonpath .venv/bin/python` on the touched files: 6 errors, 5 of them new (ST-1).
- `git merge-tree --write-tree`:
  - against `crew/mission-control` (`47c62bd`): CONFLICT in `uat.md` (SP-1).
  - against `crew/mission-control-09-...`: CONFLICT in `uat.md`, the same hunks. `paths.py` auto-merges and parses.
  - against `crew/mission-control-05-...`: CONFLICT in `tests/uat/seed.py`. This conflict is not caused by 18: 05 already conflicts with `3cf76e8` itself, because of ticket 17.
  - against `crew/mission-control-10b-...`: clean.
- The bypass probe calls `cloudflare.query` through an `httpx.MockTransport` and records the host the request would reach.
  - **Accepted, and every one reaches loopback:**
    - `http://evil.com@127.0.0.1:8025` and `http://evil.com\@127.0.0.1:8025` reach host 127.0.0.1. httpx turns the userinfo into Basic auth in place of the Bearer header, so even the placeholder token isn't sent.
    - `http://127.0.0.1:8025#@evil.com` reaches 127.0.0.1.
    - `http://[::1]:8025`, `HTTP://127.0.0.1:8025` and `http://LOCALHOST:8025` are accepted.
    - `http://127.0.0.1:8025/../../evil` reaches the path `/evil/...` on 127.0.0.1.
  - **Refused:**
    - `http://127.0.0.1@evil.com`
    - `http://127.0.0.1:80@evil.com:8025`
    - `[::ffff:127.0.0.1]`
    - `127.1` and `2130706433`
    - `localhost.`
    - tab, newline and space tricks
    - `http:\\evil.com\@127.0.0.1`
    - `https://127.0.0.1`
    - `http://127.0.0.1.example.com`
  - **Data-folder checks**, with a valid stub URL:
    - `JURA_GROWTH_DATA_DIR` = the live `data/growth`: refused.
    - variable unset: refused.
    - a symlink in `/tmp` pointing at the live folder: refused, because the path is resolved first.
    - `/tmp/../Users/.../data/growth`: refused.
- **Pairing probe.** I set only `JURA_GROWTH_D1_BASE_URL`, with a temporary data folder and no Resend override. `cloudflare.stub_problem()` is None, `configured()` is True, and `send.resend_url()` returns `https://api.resend.com/emails` (SEC-1).
- **Proxy probe.** With `HTTP_PROXY` set, httpx routes the loopback stub URL through the proxy. Only the placeholder `uat-stub` token and the stub's SQL would go there, never a real credential. This is noted under SEC-n1 and needs no action.

## Standards

**Should fix**

- **ST-1. New pyright errors in touched files.** `docs/agents/crew.md`, Commands, Typecheck, says: "don't add new errors in files you touch".
  - `tests/d1_stub.py:46` (twice) and `tests/resend_stub.py:43-44`: `suppression: list[dict] = ()`, a tuple default on a parameter typed as a list. Use `Sequence[dict] = ()`.
  - `tests/test_d1_stub.py:127`: `"..." in cloudflare.stub_problem()` applies `in` to `str | None`.
  - The `log_message` error in `resend_stub.py:80` was already there.
- **ST-2. A dead alias.** `jura_growth/agents/outreach/send.py:97` sets `temporary_data_problem = paths.temporary_data_problem`. Nothing in `jura_growth/` or `tests/` calls `send.temporary_data_problem` any more, because `resend_stub.refusal()` now calls `paths` directly. Delete it (smell: Middle Man).
- **ST-3. The stub-resolve shape is duplicated** (reuse rule). `cloudflare._stub()` (`cloudflare.py:40-47`) and `send.resend_url()` (`send.py:103-110`) both do the same steps:
  1. read the variable, and return early if it is unset;
  2. call `paths.stub_url_problem`;
  3. raise a `*StubRefused`;
  4. `rstrip("/")`.

  The guard is the security boundary, so it should exist once. One helper, for example `paths.stub_base(variable) -> str | None` raising a shared refusal, would serve both callers.

**Nit**

- **ST-n1. `paths.py` has taken on URL parsing** (`paths.py:113-149`, `_LOOPBACK`, `urlsplit`). Its docstring says the module is about "where things live". The data-folder check fits that; the loopback URL check doesn't (smell: Divergent Change). Either move both into a small `jura_growth/uat_stub.py`, or name the new section in the module docstring.
- **ST-n2. `query()` doesn't use the new `SECRETS` tuple.** `cloudflare.py:23` adds `SECRETS`, but `query()` (`cloudflare.py:62-64`) still spells out the three names. They also appear in `send.py:164` and `agents/outreach/__init__.py:22`.
- **ST-n3. A check that runs twice.** `tests/uat/seed.py`, in `outreach_live`, does `if problem(): raise Refused(problem())`. Bind the result once.
- **ST-n4. The try/except import.** `tests/resend_stub.py:30-33` imports `d1_stub` inside a try/except, so pytest and `python -m tests.resend_stub` load it under different module names. That is harmless today, and the comment explains it.

**Clean**

- Both commit messages are plain sentence-case imperatives that match the history.
- `conftest.py` clears both base-URL variables in `isolated`, following the existing pattern.
- The stub binds to 127.0.0.1 only.

## Spec

Each criterion against the code:

- **AC1, met.** "With the override set to a loopback stub, sync and the D1 checks in `live_problems` use the stub; no request leaves the machine (network guard test)."
  - `test_sync_reads_suppression_from_the_stub_without_cloudflare_credentials` and `test_toolbox_usage_comes_from_the_stub` make real loopback requests to a stub on a free port.
  - The refusal tests run with real-looking credentials. A fall-back to `api.cloudflare.com` would trip the autouse `NetworkGuard` (`tests/conftest.py:170-178`), which fails any test that reaches past loopback.
  - `test_live_problems_count_the_stub_as_d1` covers the D1 lines in `live_problems`.
- **AC2, met.** "A non-loopback override is refused with a clear error." `D1StubRefused` carries "`JURA_GROWTH_D1_BASE_URL` must point at the local UAT stub (http://127.0.0.1:<port>), not ...". It surfaces in three places:
  - `live_problems`;
  - the sync error, where sync also auto-pauses outreach;
  - `apps.inputs.usage` ("unavailable: ...").
- **AC3, met.** "`uv run pytest -rs` passes with 0 skipped." See Evidence.
- **"Wire it into the UAT seed and uat.md's environment block": met on the branch.** `outreach-live` refuses without a valid D1 stub URL (`tests/uat/seed.py`, `outreach_live`; parametrised tests in `test_uat_seed_outreach.py`).

**Should fix**

- **SP-1. uat.md is edited from the old base and conflicts with `crew/mission-control`.** The conductor's note asks to "uncomment it in uat.md's environment block". The branch was cut at `3cf76e8`, before `e91738a` and `fec69b8`. Those commits added three things:
  - `export JURA_INPUTS_DIR="$UAT/inputs"`;
  - the Resend export;
  - a commented `# export JURA_GROWTH_D1_BASE_URL=...`, plus "until ticket 18" text.

  Both `crew/mission-control` and the 09 branch conflict on three hunks. The resolution must:
  - (a) keep `JURA_INPUTS_DIR`, which the branch doesn't have. Losing it would point UAT at the real `inputs/`.
  - (b) keep one Resend export.
  - (c) replace the commented D1 line with the live export.
  - (d) drop step 6 ("Until ticket 18's loopback D1 stub exists...") and A4's "Needs ticket 18's D1 stub" sentence, in favour of the branch's text.

  Either the developer rebases onto `crew/mission-control`, or the conductor resolves it at merge with this list.

**Nit**

- **SP-n1. A refused override is silent in the scout registry.** `registry.usage()` (`agents/scout/registry.py:72`) swallows the `D1Error` and returns `{}`, and `test_d1_stub.py:115` asserts exactly that. Apps and sync show the refusal; the scout registry doesn't. This is acceptable, because `live_problems` and `status` both show it.
- **SP-n2. `status` can contradict itself.** `cloudflare.configured()` (`cloudflare.py:52-57`) is True for a refused override too. So `status` shows `"d1_configured": true` next to the refusal in `live_problems`. This is deliberate (fail loud, not "not configured") and fails safe, but it reads oddly. Consider `d1_configured: "stub (refused)"`.
- **SP-n3. Setup gaps still list the Cloudflare secrets under the stub.** `health.setup_gaps` lists the three Cloudflare secrets as missing while the stub is set (`agents/outreach/__init__.py:19-25`). The uat.md A6 step expects setup gaps by name, so nothing breaks.

## Security

`security-review` was applied inline to this diff. Under its criteria, there are no HIGH or MEDIUM findings. The attack checks the brief asked for all came back negative (see Evidence):

- a real run on the live data folder can't use the override;
- the real token never reaches the override host;
- IPv6, other 127.x forms, `localhost.`, userinfo, fragment and whitespace tricks don't reach a non-loopback host;
- redirects aren't followed, because httpx's default is `follow_redirects=False` and `query()` doesn't change it.

The stub itself is test-only. It binds to 127.0.0.1, answers SELECT only, runs one statement per call, sets `PRAGMA query_only`, and prints only SQL and parameters (email hashes), not row contents.

**Should fix**

- **SEC-1. A D1 stub can be set without the Resend stub, so a run could send real email against an empty suppression list.** Reproduced by the pairing probe, and by the branch's own `test_live_problems_count_the_stub_as_d1`, which asserts `live_problems() == []` with only the D1 stub set.
  - `paths.py:116-119` says the guard exists so "a real run can never ... read its empty suppression list". But with a temporary data folder, a D1 stub and the Resend variable unset, `live_problems()` is empty and `resend_url()` returns the real Resend.
  - Before this ticket, that window had no working D1, so `live_problems` blocked live sending. Now the stub clears that block on its own.
  - In UAT, `uat.env`'s fake Resend key stops actual delivery today. That is the last guard, though, not the guard of record. A UAT window that forgot one `export`, or someone debugging against a copy of `growth.db` in `/tmp`, would be one key away from real mail with no suppression.
  - **Fix:** in `send.live_problems()` (and so `send-due`), refuse when `JURA_GROWTH_D1_BASE_URL` is set and `JURA_GROWTH_RESEND_BASE_URL` is not. The stubs are a pair. Add a test for it.

**Nit**

- **SEC-n1. `localhost` and proxies.** `localhost` is accepted (`paths.py:120`), so it depends on `/etc/hosts`, and httpx sends loopback stub traffic through `HTTP_PROXY` when one is set (`trust_env`). Neither can carry a real credential, because stub mode uses only the placeholder ids. Dropping `localhost` from `_LOOPBACK`, or passing `trust_env=False` for stub requests, would close both.

## Blocked paths

None are touched.

## UI

There are no UI files in the diff, so `crew:web-design-review` didn't apply.
