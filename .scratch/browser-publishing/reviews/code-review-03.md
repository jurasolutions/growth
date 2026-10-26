# Code review 03: BP-03, the `publish` browser job (Facebook Page first), rounds 1 and 2

- **Branch:** `crew/browser-publishing-03-browser-job` at 2c2bdda (7d98ca9, ec8c68a, 5fe8c6a, 4be4d14, b2a5109, c5a281f, 2c2bdda), compared with its merge-base 284a2c7. `git merge-tree` is clean against both `crew/mission-control` (8c13d28) and `crew/browser-publishing-02b-community-items` (21b8aff).
- **Ticket:** `.scratch/browser-publishing/issues/03-browser-job-facebook-page.md`. **Spec:** `prd/pending/prd-jura-browser-publishing-2026-10-25.md` §2 (SC6 to SC11), §4.6, §4.7, §4.9, §5.8 and §5.9; `spike-headless-chrome.md`; ADR 0005; test strategy v3, the BP-03 rows (§4.2, §4.3, §7).
- **Reviewed:** 2026-10-27. I read every changed file: `config/settings.yaml`, ADR 0005, `docs/dispatch-contract.md` and `docs/social.md`; the publish `__init__`, `audit.py`, `hosts.py`, `job.py` and `scope.py`; `backup.py`, `caps.py`, `headless.py`, `health.py`, `remote.py`, `run_update.py`, `runner.py`, `schedule.py` and `transcripts.py`; `prompts/publish.md`; the fixture site, `publish_fake.py`, `publish_transcripts.py` and the nine new or changed test files. For context I also read `claim.py`, `commands.py` (`next`, `done`, `stopped`), `items.create_social`, `runner._run_claude` and `_judge`, `headless.claude_rules` and the README plug-in table.

## Round 2 verdict: changes-requested

**Reviewed:** 2026-10-27, after fix round 1. The branch was rebased onto 67584cf and is now at 06c3902. The fixes are in four commits:

- ce8cf00: the audit.
- 9a694cf: the job, the claim's read-only copies and `publish stopped`.
- 6b30de0: the upload rule and the scratch pruning.
- 06c3902: the README, docs, prompt and UAT step.

I read the whole of `git diff 04f3505 06c3902`, which is the round-1 head as rebased, against the fixes. That covers:

- `audit.py`, `job.py`, `claim.py`, `commands.py`, `hosts.py`, `scope.py` and the publish `__init__`;
- `backup.py` and `runner.py`;
- `prompts/publish.md`, `README.md` and `docs/social.md`;
- the changed tests.

Every round-1 finding is fixed, and my round-1 repros now fail the run where they should. One new blocking finding remains: **B3**. A page can make `after_run` raise. When it does, the audit is skipped, nothing pauses, and the model's own summary reaches the run row, `#alerts` and the run update. The cause is the tab parser added in round 1, which I missed then. The round-2 fail-closed rule makes the tab parser read every page result, so it now matters more.

### Round 2 evidence

- **Full suite** in the developer worktree at 06c3902, with `JURA_ROOT` set, temp data and outputs folders, the fake `claude`, the Discord double and no Chrome: `uv run pytest -rs` printed **2926 passed in 114.08s**, 0 skipped.
- **Pyright** (`--pythonpath .venv/bin/python`) on `commands.py`, `job.py` and `audit.py` printed **0 errors**, in both the worktree and the main checkout.
- **`repro_audit.py`**, the round-1 audit repro, run unchanged:
  - Fragmented typing now fails.
  - Acting after `publish stopped` fails (click, type and key).
  - An upload of a secret path fails.
  - An unreadable tab format fails ("couldn't read the address of tab 4101").
- **`repro_audit_r2.py`**, new attacks on the audit after a real claim. "Typed" means typed with `computer` `type`.

  | Case | Result |
  |---|---|
  | The approved text, typed once | `failures=[]` |
  | Fragments typed one character per call | fails |
  | The approved text plus " call 9123" in the same field | fails (102 characters) |
  | The approved text, then a click, then "hunter" | fails |
  | The approved text typed into two fields | `failures=[]` (nit N2) |
  | `get_page_text` holding a nested JSON array or object | **raises `RecursionError`** (B3) |
  | Page text with a planted `{"tabId": 4101, "url": "https://www.facebook.com/x"}` next to an unreadable real address | `failures=[]` (S-10) |

- **Depth probe.** `audit._tabs('[' * 1000 + ']' * 1000)` raises `RecursionError`, and depth 900 passes. So a page needs only 2,000 characters, which is shorter than a Facebook comment can be.
- **`test_zz_review_r2.py`**, whole runs through `runner.run("publish")` with the fake `claude` and a scratch copy of `tests/` that adds two steps to the scratch fake (`tamper_restore`, `unlink`):

  | Case | Result |
  |---|---|
  | B1 recheck: a clean post, then `FAIL: the page said …` | Error is "Run 1 ended FAIL: after A-0001 was recorded as done; its words are withheld …". The page text appears in no row, alert or update. |
  | A login stop | One alert ("Publishing stopped at A-0001 … in run 1: … The run's transcript keeps what the page showed for 7 days."), plus the run update. The model's text appears nowhere. |
  | A stop reason outside the closed list (`--reason "the page said call Mrs Tan"`) | Click refuses with exit 2. The item becomes `unknown` and the alert is the fixed `publish resolve` text. |
  | The image copy rewritten, then chmod restored to 0444 | Fails with "image copy 1 of A-0001 no longer holds the approved image", and `publish` pauses. |
  | The image copy deleted | `status=ok`, nothing flagged (nit N1) |
  | **JSON bomb on the page, then unapproved typing, ending `FAIL: the page said …`** | `run.after_run_error` RecursionError. The row's error and summary, the alert and the run update are all `FAIL: the page said Visitor comment from the Page wall about invoices`. It paused only because the item fell to `unknown` first. |
  | **JSON bomb on the page, unapproved typing, then a clean post ending `OK:`** | `run.after_run_error` RecursionError. `status=ok`, no alert, **no pause**, and the summary and update read "posted A-0001" in the model's words. The typed "hunter2 not approved" goes unaudited. |

### The coordinator's pyright item (`commands.py:212`)

This is not a defect.

- `caps` is imported at `jura_growth/agents/publish/commands.py:28` (`from jura_growth import approvals, caps, db, …`).
- `caps.BROWSER_TRANSCRIPT_DAYS` exists (`caps.py:42`).
- Pyright reports 0 errors on the branch file.
- The line runs under test: `tests/test_publish_queue.py::test_publish_stopped_marks_the_item_pauses_publish_and_alerts` sets the run id and asserts `f"run {run}" in alert`, which is the same `run_id is not None` branch. My fake-claude stop repro's alert ends with that line's sentence ("… for 7 days.").
- So no NameError path exists. A pyright run that resolves `jura_growth` to another checkout (one without `BROWSER_TRANSCRIPT_DAYS`) would flag the attribute, not the name.

### Round 1 findings, rechecked

| Finding | Status | How it was checked |
|---|---|---|
| B1 model text in row, alerts and update | Fixed | `job.after_run` rewrites the summary and error from the record (`_failure`, `_ending`); B1 recheck above |
| B2 typing in fragments, typing before the claim | Fixed | Typing is judged per field, in order, against whole approved texts, and a claim is needed first; four repros above |
| S-1 README | Fixed | `README.md` covers the browser job, `allowed_tools`, `alerted`, `must_be_unset`, `claimed-only` and the job keys |
| S-2 host-check duplication | Fixed | `hosts.url_problem` is shared, and `transcripts.on_domains` is used for Discord. The port and user name are refused in the audit now |
| S-3 the upload rule's query | Fixed | `claim.approved_ready` and `mission.open_read_only` |
| S-4 two alerts per stop | Fixed | `Outcome.alerted`; one alert in the stop repro |
| S-5 screenshot path | Resolved | PRD AC-P6.1 and §4.6 amended (reason and run id), `--screenshot` removed |
| S-6 sweep coverage | Fixed | `test_publish_run.py` sweeps the unknown, mismatch and no-browser alerts as well |
| S-7 tab address fails open | Fixed, with S-10 below | A page-tool result with no readable tab address fails the run |
| S-8 uploads and rewritable copies | Fixed | Copies are chmod 0444 and re-hashed in `after_run`; caught in the repro |
| S-9 actions after a stop | Fixed | Click, key, type, form input, upload and navigate after `publish stopped` fail the run |
| Round-1 nits | Fixed | Precheck syncs first; `no_browser` reads only the tab tools; live text and copies are pruned after 7 days (`backup.prune_browser_work`) |

### Round 2 findings

#### Blocking

- **B3. A page can crash `after_run`, which turns the audit off and lets model text out.**
  - **Where:** `jura_growth/agents/publish/audit.py` `_json_chunks`/`_walk`. `raw_decode` and `_walk` recurse, and only `ValueError` is caught. `get_page_text` returns page content, and a comment on the Jura Page is page content. Two thousand characters of `[[[…]]]` raise `RecursionError` out of `audit.audit`, and so out of `job.after_run`. The runner then logs `run.after_run_error`, and the model's outcome stands (`README.md`: "An exception is logged as `run.after_run_error` and the outcome stands").
  - **What follows:**
    - No audit and no pause.
    - The copy re-hash never runs.
    - The model's summary and `FAIL:` line reach the run row, `#alerts` and the `#social-drafts` run update.
  - **Rules it breaks:**
    - AC-P9.3: the audit "fails the run and pauses `publish`".
    - PRD §4.7: "run updates never quote page text".
    - The test strategy's AC-P8.1 row: "never page text".
  - **Repro:** the two JSON-bomb rows above.
  - **Fix, all three:**
    1. The audit must never raise on page content. Catch `RecursionError` (or any exception) per result in `_json_chunks` and treat that result as unreadable, which the fail-closed rule then fails. Or scan with a bounded depth.
    2. `job.after_run` must fail closed. Wrap the audit and the copy check, and turn any exception into a failed `Outcome` with a fixed error ("the audit of run N couldn't run"), a pause, and the record-built summary.
    3. Add the bomb transcript to dataset T, both as a pure audit test and as a fake-claude run.

#### Should fix

- **S-10. Planted JSON in page text satisfies the fail-closed tab-address check.**
  - **Where:** `audit.py:186-190`. `_tabs` reads `tabId`/`url` pairs from anywhere in a result, page text included.
  - When the extension's real tab context is in a form the audit can't read, a page that carries `{"tabId": <our tab>, "url": "https://www.facebook.com/…"}` clears the result, so the real off-host address goes unseen. The repro `planted_tab_json` gives `failures=[]`.
  - The run can't know its tab id in advance, but a page can try common ids, or echo what it sees.
  - **Fix:** once R1 records the real format, read the address only from the extension's own block (for example, the trailing tab-context JSON), never from a JSON object found anywhere in page text.

#### Nits

- **N1.** A missing image copy passes the re-hash (`job.py` `_copy_problems` skips `not path.exists()`). The run can't delete with its tools, so this is low risk, but a missing copy after a claim should fail closed like an unreadable one.
- **N2.** The approved text typed whole into two fields passes. It is content-safe; the prompt's one-field rule is the only guard.
- **Blocked paths:** none. `git diff --name-only 04f3505 06c3902` touches only `README.md`, `docs/`, `jura_growth/`, `prompts/`, `tests/` and `.scratch/mission-control/uat.md`. `git merge-tree` with `crew/mission-control` is clean.
- **N3.** Audit findings name hosts, and a host is attacker-chosen text (`call-mrs-tan.evil.test`). Hosts are fine to show, as the PRD's audit wording expects, but consider masking hosts that aren't on a known list to "a host outside the list" in the `#alerts` text.

---

## Round 1 verdict: changes-requested

Two findings block. Both are reproduced below.

1. **B1.** Model text, which can be page text, reaches the run row, `#alerts` and the run update in `#social-drafts`.
2. **B2.** A model that types in fragments gets past the typed-text audit.

The rest of the branch is sound:

- `--chrome` is reachable only through `caps.BROWSER_JOBS`.
- The argv matches AC-P9.2.
- Every page tool is scoped by domain.
- The precheck keeps Claude from starting when nothing is due.
- No blocked path is touched.

## Evidence

- Full suite in the developer worktree (`JURA_ROOT` set, temp data and outputs folders, fake `claude`, Discord double, no Chrome): **2742 passed in 112.06s**. `tests/test_community_fetch_block.py` plus every `tests/test_publish_*.py`: **225 passed**. `test_community_fetch_block.py` is unchanged in the diff.
- `git diff --name-only 284a2c7...` shows nothing under `inputs/`, `design-system/`, `.env` or the live `data/growth/`.
- Reviewer probes, run from a scratch copy of `tests/` with the branch's own fixtures and nothing changed in the worktree:
  - `repro_audit.py` calls `audit.audit` over dataset-T transcripts.
  - `test_zz_review_repro.py` and `test_zz_review_repro2.py` run the whole job through `runner.run("publish")` with the fake `claude` binary.
  - Their results are quoted under each finding.

## Standards

### Should fix

- **S-1. README.md drifted from the plug-in interface it documents** (CLAUDE.md: "`README.md` covers layout, commands, tests and the plug-in interface"). These parts are stale:
  - `README.md:112-125`, "What a headless run can do", still says every claude job reads under `jurasolutions/` and gets web search and fetch. The publish job has no `--add-dir`, gets `--chrome` and is denied both.
  - The `permissions(job)` row (`:178`) leaves out `Permissions.allowed_tools`.
  - The `setup_gaps()` row (`:185`) leaves out `Gap(must_be_unset=True)`.
  - The run-update paragraph (`:194`) leaves out `run_update: claimed-only` and the `browser: true` job key.
- **S-2. Reuse: the audit's host check duplicates two helpers and differs from both.**
  - `audit.py:138` is `transcripts.on_domains(text, DISCORD)` written out by hand.
  - `audit._url_problem` (`audit.py:131-144`) re-implements `hosts.problem` but without the port and user-info refusals. So `https://www.facebook.com:8443/` passes the audit, which `publish done` would refuse (`transcripts.host_of` drops the port).
  - Fix: one shared check that takes a hosts tuple.
- **S-3. Reuse: `scope.next_has_image` (`scope.py:65-88`) duplicates two existing pieces.**
  - It opens growth.db read-only by hand, which duplicates `mission.open_read_only` (`mission.py:137`) without `PRAGMA query_only`.
  - It copies `claim._ready`'s selection but with `day = ?` where `_ready` has `day <= ?`, and it parses `content_json` raw instead of using `items.Item.content`.
  - Fix: move the query beside `_ready` in `claim`/`items` and reuse the helper.

### Nits

- `job._no_browser` (`job.py:149-153`) adds a second once-a-day mechanism, next to `discord.post(..., dedupe=True)`. It is defensible, because `alert` doesn't dedupe, but it should say why.
- The content keys `"text"`, `"images"` and `"copies"` are bare strings across `claim.py:226/239`, `scope.py:88` and `job.py:144-145`. Small accessors on `Item` would gather them (possible Primitive Obsession).
- `__init__.permissions` checks `job != "publish"` itself, while `precheck` checks inside `job.py`. Pick one place.
- In `job.run_update` (`job.py:101-108`), `produced = [...]; return produced` is a redundant temporary.
- Pyright on the 12 touched files reports 2 errors at both base and head, both pre-existing in `runner.py`. `audit.py` and `scope.py` have none.

## Spec

### Blocking

- **B1. Model text (page text) reaches the run row, `#alerts` and the `#social-drafts` run update.**
  - **Where:** `jura_growth/agents/publish/job.py:84-88`. When an item was claimed and the outcome failed with no stop or audit error, `errors = [...] or [outcome.error]` keeps the model's own `FAIL:` line. That line becomes the run's `error`. The runner posts it to `#alerts` (`runner.py:158`), and the run update prints it as `Error:`.
  - **Rules it breaks:**
    - PRD §4.7: "run updates never quote page text".
    - Test strategy v3, AC-P8.1 row: "… outcome and URL or stop reason, never page text".
    - Ticket: "Publish transcripts kept 7 days, not 30, and run updates never quote page text".
    - The `after_run` docstring's own promise: "never the model's text, so neither the run row nor the run update can quote page text".
  - **Repro:** a clean post through the fake `claude`, ending `FAIL: the page said Visitor comment from the Page wall about invoices`. Results:
    - Run row `error`: `FAIL: the page said Visitor comment from the Page wall about invoices`
    - `#alerts`: `` `publish` failed: FAIL: the page said Visitor comment from the Page wall about invoices ``
    - `#social-drafts`: `**publish** · failed · … Error: FAIL: the page said Visitor comment from the Page wall about invoices\n> A-0001 · Facebook Page · posted · https://…/posts/123456789`
  - The phone redaction caught a planted phone number in an earlier variant, but names and free page text pass.
  - **Fix:**
    - For every publish run, build the error from the record, never from `outcome.error`. For example: "the run ended FAIL: after A-0001 was posted; its words are withheld, see transcript `<run id>`".
    - Do the same for the summary when nothing was claimed (`job.py:89` falls back to `outcome.summary`).
    - Add the case to the run test and the sweep.
- **B2. The typed-text audit passes any text typed in fragments.**
  - **Where:** `audit.py:104-107`. Each `type` or `form_input` call is checked on its own with `_normal(typed) in text`, a substring test. Any sequence of characters, or single words, that appear somewhere in the approved post passes. The calls are also never ordered against the claim, so typing before `publish next` passes when the run later claims an item.
  - **Rules it breaks:**
    - AC-P9.3: "typed text that isn't part of the approved content … fails the run".
    - PRD §4.7: "Never type a password, a one-time code, a phone number or any personal detail that isn't in the approved content".
    - The audit's own docstring: "Nothing may be typed before an item is claimed".
  - **Repro (`repro_audit.py`):** the approved text is the Facebook fixture post.
    - "hunter secret" typed in one call: `failures=["computer typed 13 characters that aren't in the approved content"]`.
    - The same string typed one character per call: `failures=[]`.
  - **Fix:**
    - Join every typed string in transcript order, normalise it, and require the result to be one approved text, or a substring of it, with the parts contiguous.
    - Fail any typing that comes before the `publish next` Bash call in the transcript.
    - The prompt already says "in one go", so a legitimate run is unaffected.

### Should fix

- **S-4. A stop posts two `#alerts` messages.**
  - **Where:** `publish stopped` alerts once. Then `after_run` turns the stop line into the run's error (`job.py:85`), and the runner alerts again (`runner.py:158`).
  - **Rule it breaks:** test strategy AC-P6.1: "one `#alerts` message with the reason and screenshot path".
  - **Repro (`test_zz_review_repro2.py`):** a login wall gives `ALERTS 2`:
    - "`publish` failed: A-0001 · Facebook Page · stopped · login: …"
    - "Publishing stopped at A-0001 …"
  - The existing test filters on "Publishing stopped", so it misses the duplicate.
- **S-5. The AC-P6.1 screenshot path cannot happen.**
  - PRD §4.6 says the run "reports `publish stopped` with the reason and a screenshot path".
  - The prompt (`prompts/publish.md:27`) never passes `--screenshot`, and no allowed tool can write a screenshot to the scratch folder.
  - `test_a_login_wall_…_with_the_screenshot` passes only because the fake writes `{A}-stop.png` itself.
  - This is a spec question: see Questions.
- **S-6. The sweep misses three of the ticket's message kinds.** The ticket wants the sweep over "the `#alerts` posts for stops, mismatches and `unknown` items". `test_publish_run.py:331` sweeps a posted update, a stop and an unclaimed failure. It sweeps no unknown alert, no mismatch alert and no no-browser alert.

### Nits

- **Conductor comment, 2026-10-27T03:40.** The precheck returns on an auth variable before `items.sync()` (`job.py:30` vs `:35`). Nothing is claimed either way, so it is harmless, but the comment asked for sync first.
- **No-browser detection.** It matches "No browsers are connected" in any Chrome result, including page text (`audit.py:90`), not only the first browser call. It matters only for a run that claimed nothing.
- **Scope creep, both tightening.** `upload_image` was added to the denies, and `retention.browser_transcripts_days` is a new setting. Both narrow; keep them.
- **The host list is defensible.** It leaves out the image CDN hosts from §4.7's "for example" list, which narrows scope, as the developer flagged.
- **Rehearsal.** R1 to R6 can't run until ticket 07 (fixture platform) lands, because hosts are hard-coded and https-only. Ticket 07 already owns this, blocked by 03. BP-03 closes only after 07 and the rehearsal.

## Security

I worked through the security-review method inline on this diff. The attack list from the brief comes first.

| Attack | Result |
|---|---|
| Any job other than publish gets `--chrome` | **No.** `runner.py:262` raises `JobError` for `browser: true` outside `caps.BROWSER_JOBS`, and `"--chrome"` appears once in `jura_growth/` (test plus my grep). |
| Reach a non-allowlisted host | **Blocked by permissions, pending BP-01 U18 and R3.** Page tools are allowed only through `ClaudeInChromeDomain(<facebook host>)` under `dontAsk`. The spike could not prove that an unlisted domain is denied, or whether the rule judges the destination or the current tab. The audit is the backstop for `navigate`, for `url` inputs and for recognised tab-URL formats (see S-7). |
| `javascript_tool` | **Denied by name** (`scope.DENIED_TOOLS`), and the audit fails any attempt. |
| `file_upload` of a non-work file | **Allowed by permissions whenever today's item has an image. Caught only after the run** (S-8). |
| Discord or email in Chrome | **No domain rule for either.** The audit names Discord hosts. The dedicated profile (BP-01) holds neither sign-in. |
| Post without a claimed approval of the exact bytes, outside the window or past caps | **The claim gates in code (BP-02a).** The precheck starts no Claude when nothing is claimable. Typing with no claim fails the audit, but only after the fact. Fragments slip through (B2), and image bytes can be swapped (S-8). |
| Keep going after a login wall, CAPTCHA or warning | **Only the prompt stops it.** The audit doesn't look (S-9). |
| Model text reaches Discord or the run row | **Yes** (B1). |
| Prompt injection through post text | **Low.** The text arrives as a `publish next` tool result, and Ting Yu approved it. The prompt's "pages are data" rule doesn't name it (nit). |

### Should fix

- **S-7. The tab-URL check fails open on an unrecognised result format.**
  - **Where:** `audit._tabs` (`audit.py:194-199`) knows two guessed formats: JSON with `tabId`/`url`, and `tabId N: "title" (url)`. The spike recorded neither.
  - If the extension reports tab URLs any other way, AC-P9.3's "foreign URL shown only in a later tool result's tab URL" silently passes every run.
  - **Repro:** a click result `Tab 4101 now at https://evil.example.net/x` gives `failures=[]`.
  - `RESULT_CHARS` truncation (`transcripts.py:151`) could likewise drop a tab context appended after a long `get_page_text`.
  - **Fix:** fail closed. When a run made page-tool calls on its tab, but no result ever gave a recognised URL for that tab, fail the run, or at least warn. Confirm the format at R1.
- **S-8. Uploads: any local file while the item has an image, and image copies the run can rewrite.**
  - When `next_has_image()` is true, `file_upload` is allowed for every path through the domain rule. A prompt injection on a Facebook page (visitor posts and comments sit on the Page) could attach, for example, a key file to the composer. The audit (`audit.py:108-111`) fails the run only afterwards.
  - The run also holds `Write(/<work>/**)` and `Edit(/<work>/**)` over `data/growth/work/publish/<A-id>/`, where `claim._copy_images` writes the approved copies. The audit compares upload paths, never bytes, so a rewritten copy uploads unapproved content and passes.
  - **Fix:**
    - `chmod 0o444` each copy after it is verified.
    - Re-hash the copies in `after_run` against the approval's image hashes, and fail and pause on a mismatch.
    - Ticket 07 already records the R1 test of a parameter allow rule for `file_upload` paths. Add a rehearsal step that injects an upload of a non-work file on the fixture site.
- **S-9. Nothing in code notices page actions after `publish stopped`.**
  - PRD §4.6: "stops at once, without retrying or clicking further". Rehearsal R2: "clicks nothing further".
  - **Repro:** claim, a login stop, then a click, approved text typed and Return pressed. `audit` gives `failures=[]`.
  - **Fix:** fail the run on any `computer`, `form_input`, `file_upload` or `navigate` call after a `publish stopped` Bash call. `tabs_close_mcp` stays allowed.

### Nits

- `<A-id>-live.txt`, which is page text, stays in `data/growth/work/publish/` with no pruning, while transcripts go after 7 days (the intent of §4.7). Prune it with the browser transcripts.
- The ADR and the docs already say the domain rule's subdomain behaviour waits on U18. Keep the host list explicit until then, as built.

## Blocked paths

None. The diff touches only `config/`, `docs/`, `jura_growth/`, `prompts/` and `tests/`.

## Questions for Ting Yu

1. **The AC-P6.1 screenshot path (S-5).** Claude in Chrome's screenshot returns an image to the model, not a file. Either amend AC-P6.1 and §4.6 so the alert carries the stop reason and the run id (whose transcript holds the screenshot for 7 days), or find a tool that writes a file. Recommended: amend.
