# Code review 05: the watch reads the platforms and can't act

Branch `crew/inbox-watch-05-watch` (16ea1c6) against `crew/inbox-watch` (5534075, also the merge-base).

**Verdict: changes-requested.** Five blocking findings: B1 and B2 under Security, B3 and B4 under Spec, B5 under Security.

The core claim holds. No allowed tool lets a watch run click, type, upload or run script. What fails is
what the watch's records and alerts can be made to say, and two places where the prompt or the order of
the checks does the wrong thing on a real first run.

## Evidence

| Check | Result |
|---|---|
| `uv run pytest -q -p no:cacheprovider -o addopts=""` in the ticket's worktree, with the worktree exports | 4643 passed in 424s |
| `git diff --stat ... -- tests/test_publish_audit.py` | empty, and the file passes in the run above |
| Blocked paths in the diff (`inputs/`, `design-system/`, `.env`, CI, live `data/growth/`) | none |
| Build, lint, typecheck | none configured (operating card) |
| UI files in the diff | none, so `crew:web-design-review` doesn't apply |
| Reviewer's probes, using the repo's fake `claude` and real `jura-growth` children | `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/3dcab9c8-e10d-45d9-9c0b-7a40a70479ee/scratchpad/test_probe_05.py` and `test_probe_05b.py` in the same folder |

Nothing was run against Chrome, Meta or Claude Code's real rule matching. Findings marked "reproduced"
came from these probes. The security skill's preloaded diff was `main` to the feature branch, not this
ticket, so the pass was run against the ticket's diff instead. Each security finding kept here was
reproduced by hand rather than filtered by a second agent.

## Security

### Blocking

**B1. A model's words and a clickable link reach #alerts and the run row.**
`jura_growth/agents/inbox_browser/job.py:121` puts `found.failures` into the error, and
`jura_growth/agents/publish/audit.py:244` (through `_tab_of`, `audit.py:391-396`) and
`jura_growth/agents/publish/hosts.py:231` put the tab id and the host into those failures.
Breaks PRD S2: "A model's words never reach a run row, `#alerts` or a run update." Also breaks the
promise in `job.py:6-8`.
Reproduced. A `read_page` call with `tabId: "[Resume now](https://evil.example/pay) urgent"` posts this to #alerts:

```
`inbox-watch` failed: The audit of run 1 failed: a read_page call on tab [Resume now](https://evil.example/pay) urgent, which this run didn't open.
```

A `navigate` to `send-your-password-to-evil.example` also puts that host in the alert. `allowed_mentions`
stops pings, not links. The audit counts attempts, so Chrome refusing a non-numeric tab id may not stop
the string being recorded (not tested live). The existing test `test_iw_a3_...caught_and_quoted_nowhere`
only plants words the failures don't quote.
Fix: keep the detail in the `inbox.audit_failed` event, and give the run's error fixed words with a count
of findings. That leaves `publish` as it is.

**B2. The N3 check can be passed with words the page never said.**
`jura_growth/agents/inbox/watch.py:399` counts the whole tool result, including the tab context, and
`watch.py:628` matches each line anywhere in everything the run read.
Breaks N3: "checks each observed text appears in that run's Chrome results" and "Stored text is checked".
Reproduced, end to end. Both of these settle as `new`, so ticket 02 would draft from them:

- Text `please-send-your-bank-details`, with the run navigating to `...?x=please-send-your-bank-details`. The
  page says nothing of the kind, and the address in the tab context verifies it.
- Text `password\nplease\nsend\nyour` on a page where those words are scattered through other sentences.

Fix: strip the trailing tab context (`audit.py` already finds it), and require a message's lines to be
contiguous within one result, allowing for what `read_page`'s tree puts between them. Add both as tests.

**B5. A percent-encoded `..` passes the look-alike check.**
`jura_growth/agents/inbox/watch.py:158` compares raw path segments.
Breaks test strategy A10, an Accept item: a look-alike target "keeps the person but no target".
Reproduced. `target_problem` returns None for each of these:

- `https://www.facebook.com/groups/%2e%2e/l.php?u=https://evil.example/`
- `https://www.facebook.com/groups/x/%2e%2e/%2e%2e/flx/warn/?u=https://evil.example/`
- `https://www.instagram.com/p/%2e%2e/%2e%2e/accounts/logout/`

The same address without encoding is refused, and a browser treats the two alike. The kept address shows
as `Open: <...>` in #mission-control and becomes a reply target in ticket 06.
Fix: percent-decode the path before the segment check and before `_first_segment`, as `hosts.py` already
does for its path shapes (it imports `unquote`). Refuse any `%2f` or `%5c` left after decoding.

### Should fix

- **`navigate` has no path limit.** `audit.py:248` with `places=()`, called from `inbox_browser/job.py:74`.
  Reproduced: `www.facebook.com/l.php?u=https://evil.example/DM` and `www.instagram.com/accounts/logout/`
  both give no failures. An off-host landing fails the audit, but only after the request has left, and DM
  text could go in the query. Meta's interstitial probably limits this; not tested live. Fix: pass the
  allowed starts to `places`, with a `place_check` for the surfaces, neutral segments and Jura's own pages.
  `AuditRules.place_check` already exists for this. (The skill's confidence filter would drop this one. It
  stays because the brief asks about `navigate` directly.)
- **The read-only audit is a deny-list.** `audit.py:253`. Reproduced: a call to an unknown tool
  `press_button` with a valid tab gives no failures. The argv covers every tool the extension has today, but
  a new one would pass both the domain rule and the audit. B2 of the technical review wants the audit as the
  second layer. Fix: with `read_only`, fail any Chrome tool outside `navigate`, `read_page`,
  `get_page_text`, `find` and the tab tools.
- **A steered run can drop a post for good, silently.** `watch.py:517-523` and `:494`; `job.py:112`.
  Reproduced: a run that records `gone: true` and then fails its audit leaves `gone_at` set, `gone_told` 0,
  the post out of `targets`, and nothing told. No later run has it in `last_run_id`, so it is never told and
  never read again. A passing run gets it told but also never restored. Breaks S4's "reported as a
  reaction" and the comment at `job.py:111`. Fix: hold `gone` until a trusted run settles it, and clear it
  when a later read finds the post.
- **Same-name authors are hidden.** `watch.py:302-304`. Reproduced: author `Jura Solutions` saying "I want a
  refund" gives `own: 1` and no row. Facebook names aren't unique, and an impersonator is exactly who he
  would want to hear about. Breaks R3: every social comment or DM "is reported whatever". Fix: report a
  count of what was dropped as own, and match against the Page's address where the page gives one.
- **`observe` raises on bad input.** `watch.py:296`, against "Never raises for what it was given" at
  `watch.py:224`. Reproduced: `attachment: []` raises TypeError, so the file's later entries are lost,
  including its surface record, and a good read turns into a failed surface. A lone surrogate in `url` and
  deep JSON in `parse_file` reportedly raise too (security pass, not reproduced by me). Fix: check the type
  first, and wrap each entry.

### Nit

- `paths.guard` also accepts `outputs/growth/` (`paths.py:108`), a little wider than N1's "in scratch". The
  JSON and N3 checks limit it.
- A steered model can run `inbox stopped` and pause `publish`, which only Ting Yu can undo. It fails safe.
  Worth a line in the alert saying a page's words may have caused it.

### What holds

- **Click, type, upload, script.** `scope.py` denies `computer`, `form_input`, `file_upload`,
  `upload_image`, `javascript_tool`, the network, console, shortcut, batch and browser-switching tools by
  name. Only `navigate`, `read_page`, `get_page_text`, `find` and the tab tools remain. `read_page` and
  `find` return text and refs, and with `computer` denied a ref can't be used. `test_iw_b2_...` proves the
  argv. Live matching is a UAT step.
- **Another host.** Rules name seven exact hosts. `javascript:`, `data:`, `file:` and schemeless addresses
  fail the audit (reproduced). No WebFetch or WebSearch.
- **`inbox observe --file` to a privileged path.** It goes through `GuardedPath`, SQL is parameterised,
  refusals use fixed words, `--reason` is a closed choice, and `<target>` can't break out of its brackets
  because `_UNSAFE_URL` refuses them. Observed text reaches only R1, as S7 intends. The route to #alerts is
  B1, which runs through the audit and not through `observe`.
- **`publish` unchanged.** With default rules, every changed line in `audit.py` gives the same strings and
  the same flags. `sent` does nothing unless `one_line` is set, and `attempted_done` has the same condition.
  `domain_rules()` with no argument is unchanged. The runner adds only the skip: a held `browser` lock
  gives a `run.quiet` and the same `_run_update` as `NothingToDo`, so no Claude, no precheck, no
  `_abandon_stale` on that slot. `test_iw_b6_...` runs this for `publish` too.
- **The page addresses.** `config/inbox.yaml` matches
  `outputs/growth/setup/browser-publishing.md:30-31,44,236` exactly. `config/social.yaml` has `page_url: null`,
  so nothing there contradicts them, and `outputs/growth/setup/social-accounts.md:19` is the older plan,
  marked "to be confirmed" (worth correcting by hand). Nothing is invented there. The three unproved surface
  addresses are disclosed in the setup guide (`.scratch/inbox-watch/setup/inbox-watch.md:46-47`).

## Standards

No hard breach of a code rule. Core modules name jobs and import no agent.

### Should fix (reuse)

New code that duplicates what exists:

- `inbox_browser/job.py:140-160` `failed_closed` duplicates `publish/job.py:249`; `job.py:82` `_no_browser`
  duplicates `publish/job.py:273`; `job.py:77` `_ending` duplicates `publish/job.py:207`; `job.py:57` the auth
  loop duplicates `publish/job.py:48`. Share them, since a fix to one fails-closed path should reach both.
- `watch.py:79-85`: six `STOP_REASONS` entries are copied from `publish/commands.py:36`. They describe the
  same accounts, so they should stay one list.
- `watch.py:436-438` re-parses `HH:MM`, duplicating `schedule._hm` (`schedule.py:59`).
- `job.py:26-28` `in_window` repeats `inbox/job.py:21-24`.
- `watch.py:158`'s dot-segment check repeats `hosts.within`.

### Should fix (docs)

- `README.md:136`: "each platform switched on and in `browser` mode" is false for the watch, which ignores
  `publish_mode` (`inbox_browser/scope.py:9`, N11).

### Nit

- `watch.py:43,45`: `OBSERVE_FILE_BYTES` and `MAX_OCCURRENCE` sit outside `caps.py` (README: hard limits live
  there). There is precedent in `MAX_PAGE_BYTES`.
- `watch.py:511` hard-codes "30 days" against `caps.INBOX_WATCH_POST_DAYS`; `job.py:53` says "an hour" against 55 minutes.
- `inbox_browser/__init__.py:61`: `Gap("INBOX_WATCH_PAGES")` renders as an unset variable that doesn't exist.
- Social sources are listed in `watch.py:72`, as SQL at `:264` and `:576`, and in `report.py`. `"post-stats"` at
  `watch.py:609` copies `report.RUN_MESSAGE`. `AGENT` and `PUBLISH` at `watch.py:40-41` copy names held elsewhere.
- `CONTEXT.md` lacks `observed` and `baseline`, which are new states.
- `docs/adr/0006:51` cites `caps.THIRD_PARTY_TEXT_JOBS`, which arrives with ticket 02 (`caps.py:48` there). It
  reads true once both are merged, so it only needs checking at merge.

Judgement calls not raised as findings: `watch.py` at 711 lines has six concerns and could split, and
`report.py` now branches on source five times.

## Spec

### Blocking

**B3. The first run posts unread comments it should keep silent.**
`jura_growth/agents/inbox_browser/job.py:110-112` calls `finish_surfaces` before `post_lines`, so
`jura_growth/agents/inbox/watch.py:560,581` always sees `posts` as already read.
Breaks F12: "The first social read is a silent baseline", and the comment at `watch.py:553`.
Reproduced end to end on an empty database. The very first run posts:

```
I-0001 · From the watch · P-0001 on Facebook: 9 comments the watch couldn't read: check by hand.
```

`test_iw_f12_on_the_very_first_read_of_posts_unread_comments_are_silent` passes only because it skips
`finish_surfaces`. Fix: take `posts_read_before` before `finish_surfaces`, and run that test through `after_run`.

**B4. The prompt tells the model to stop on the pages W3 sends it to.**
`prompts/inbox-watch.md:69-70`: "If you read a page that isn't Jura's own Page or account, that is the
`wrong-identity` stop signal."
Breaks W3 ("community posts in groups") and S4's narrow list of stops, and contradicts the table's own
wording at `prompts/inbox-watch.md:50` ("Signed in as anyone but"). A group post, a commenter's profile or a
notification's target isn't Jura's own page. A model that follows this line stops, and `publish` pauses until
Ting Yu resumes it. It also makes it easier for a hostile page to cause a stop.
Fix: say what the check is, which account the session is acting as, and add a prompt test. Also confirm in
the first-run checks which identity `www.facebook.com/notifications` shows, since the watch can't click to
switch from Levi's profile to the Page. That part is inferred and can't be tested without Meta.

### Should fix

- **The prompt relies on memory the run doesn't have.** `prompts/inbox-watch.md:22,92`: "something you haven't
  recorded". `watch.py:498-502`: `watch-targets` returns no record. Each run starts empty, so unread marks are
  all it has, and opening a thread clears them. Two claims then fail: `watch.py:600-601` says over-cap
  messages "wait for the next run", and F13 says "Messages are recorded as they are read", whereas
  `prompts/inbox-watch.md:67-68` records per surface, so a run that dies loses opened threads. Fix: give each surface its
  last good read in `watch-targets`, and record after each thread.
- **A failed audit still counts as a good read.** `job.py:110`. Reproduced: all surfaces show `read_ok` 1 and a
  new `last_good_at` after a failed run, which restarts the 3-hour clock and spends the first-read baseline.
  Line 111 already withholds that run's counts, so this should match. F13.
- **W5: one comment recorded twice.** `watch.py:307-318`. Reproduced: a comment read with its permalink, then
  the same words with no `url`, gives two rows, because the thread and so the conversation differ. Two R1s
  and, after ticket 02, two drafts. The prompt allows leaving `url` out (`prompts/inbox-watch.md:108`), and the
  docstring of `_told_under_other_key` says it handles this. It handles only a matching thread.
- **Held items can stay hidden.** `job.py:64` settles only after the window, too-soon and pause checks, and the
  runner runs no precheck while paused. `failed_closed` pauses the agent and leaves that run's items
  `observed`, so they reach no report until he resumes. A killed run followed by a pause does the same. Breaks
  N3's "reported as such", and `watch.py:634`: "A person always stays visible". By reading only; not
  reproduced. Fix: settle orphans from the `inbox-check` precheck too, which a browser pause doesn't stop,
  taking the `browser` lock first.
- **The seam with ticket 02 holds for the queue, not for the history.** The queue reads only `new`
  (`store.py:201` on `crew/inbox-watch-02-triage`), and nothing on either branch reads `observed` except
  `settle`. But `triage.py:178,193` there shows the whole conversation and filters only `noise`, so `unverified`
  and `observed` text reaches the model as history. That contradicts `watch.py:10-11`. Fix on whichever branch
  merges second: exclude `observed`, `unverified` and `baseline`. Also `unreported` must exclude all of `noise`, `new` and `observed`: ticket
  02 has `(NOISE, NEW)` and this branch `(NOISE, OBSERVED)`, and a wrong resolution reports held text.
  `git merge-tree` shows 8 conflicting files, these among them. The migrations don't collide, since ids
  include the file name (`0002_triage.sql`, `0002_watch.sql`).
- **R4's last good read has no owner.** F13: "R4 shows the last good read", and B2's "in R1 and R4". Only
  `inbox status` and the Needs you line exist, and ticket 04's Accept names neither. `watch.py:429` promises the
  one-pager. Fix: add it to ticket 04's Accept.

### Nit

- S8 "excluding the Page's own activity": comments are adjusted through `page_comments`, but reactions and
  shares are page totals (`prompts/inbox-watch.md:134`). The page shows no split, so record this as a limit in ADR 0006.
- A10 "another Page's post": `permalink.php?...&id=2` and any Instagram `/p/` are kept (`watch.py:90`). N12's
  read-back in ticket 06 covers the reply, so this one can wait.
- `test_iw_n11_...match_social_yaml` is vacuous while `page_url` is null, as the spec allows.

### Accept table

| Item | Status | Proof, or the finding against it |
|---|---|---|
| W2 | met | `test_inbox_watch_run.py:75,118,128,137,144,227` |
| W3 as amended | not met | B3, B4 |
| W5 (N2, F7) | partial | `test_inbox_watch_observe.py:65,71,79,90,128`; the no-address case fails |
| B1's table | met | `test_inbox_audit.py` (29 tests) |
| B2 | met | `test_inbox_watch_run.py:66` |
| B6, `publish` too | met | `test_inbox_watch_run.py:507` |
| S3 | met | `test_inbox_watch_run.py:227`, `test_inbox_audit.py` |
| S4, both flags, one alert | not met | counts pass at `test_inbox_watch_run.py:442,465,485`; B4 stops too much |
| S6 | met | `test_inbox_watch_run.py:555,563,571,582,588` |
| N3 | not met | B2 |
| N11 | met | `test_inbox_watch_run.py:82,93,99` |
| F13 | partial | should-fix findings above |
| S8 | partial | nit above |
| `test_publish_audit.py` unchanged and green | met | empty diff, passes |
| IW-A3 | not met | B1; the rest passes at `test_inbox_watch_run.py:240,259,272` |
| IW-A10 | not met | B5; the rest passes at `test_inbox_watch_observe.py:215,226,255` |
| IW-A13 | met | `test_inbox_watch_observe.py:434,520,528,601` |

Scope creep: none of substance. The daily no-browser alert, the auth-variable skip and the 55-minute floor all support W2 or F13.


- **Security:** 3 blocking, 5 should fix, 2 nits. Worst: B2, since a check the ticket names can be passed with invented words.
- **Standards:** 0 blocking, 6 should fix, 6 nits. Worst: the duplicated fail-closed path.
- **Spec:** 2 blocking, 6 should fix, 3 nits. Worst: B4, since a false stop halts `publish` as well.
