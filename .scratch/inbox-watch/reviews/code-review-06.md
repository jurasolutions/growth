# Code review 06: approve a social reply and it posts once, in the right place

Branch `crew/inbox-watch-06-social-reply` at 3ed9542, against `crew/inbox-watch` (ac41456, also the merge-base).
Spec: the ticket, then the PRD with its "Amended" sections, then `reviews/functional.md` and `reviews/technical.md`, then ADR 0003 and 0006.

**Verdict: changes-requested.** Nine blocking findings: SEC-1 to SEC-5 under Security, and P-1 to P-4 under Spec.

The gate itself is sound. The claim is one transaction, the text is handed out only after it commits, one run claims one reply, and a claim with no outcome is `unknown` and never goes again. Typing is well held: a line break, Return mid-text, a second Return, a retype and any other words all fail the run. What fails is what the code believes. The run's own word decides where the reply went, who it went as, whether it went at all, and whether a real person's item closes. The audit has no way to disagree with any of those.

## Evidence

| Check | Result |
|---|---|
| `uv run pytest -q -rs -p no:cacheprovider -o addopts=""`, worktree exports, at 3ed9542 | 5920 passed in 343s, none skipped |
| `pyright` on `reply_run.py`, `social.py`, `inbox_browser/job.py`, `publish/hosts.py` (advisory) | 0 errors |
| Blocked paths in the diff (`inputs/`, `design-system/`, `.env`, live `data/growth/`, CI) | none |
| Build, lint | none configured (operating card) |
| UI files in the diff | only `tests/fixtures/publish-site/*.html`, test pages imitating Meta that never ship, so `crew:web-design-review` doesn't apply |
| Reviewer's probes, with the repo's fake `claude` and real `jura-growth` children | `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/3dcab9c8-e10d-45d9-9c0b-7a40a70479ee/scratchpad/probes-06/test_zz_probe_06.py` and `.../scratchpad/sec06/test_sec06_probe.py`, cited below as P numbers |

"Reproduced" means it ran on those doubles. Nothing touched Chrome, Meta, Discord or launchd, so anything about how a real page or Discord behaves is marked as untested. The security skill's preloaded diff was `main` to the feature branch, so the pass ran against this ticket's diff instead. `T:` below means `tests/test_inbox_social_reply.py`.

## The questions the brief asked

| Attack | Result | Evidence |
|---|---|---|
| Type anything but the approved text, in any tool | Held for `type`, keys, `form_input` and uploads, with one gap: `repeat` on a key can change the bytes | T:618; P9b; should-fix S-1 |
| Send twice | A second Return, a click after Return, and a retype in the same or a new field all fail. `repeat`, `double_click` and a refused `reply-done` slip past | P8c, P8d, P8e, P9a, P9b; S-1, S-2 |
| A fragment through Return or a line break | Fails and pauses. A fragment sent by a click and followed by `inbox stopped` leaves the audit clean, though the item still ends `unknown` and paused | T:618; P10; S-3 |
| Reply in another thread | **Passes on a comment run, and on a DM run that skips `reply-due`** | SEC-1 |
| Reply as the wrong identity | **Passes** | SEC-2 |
| Act before the claim | Typing fails. **Clicks pass** | T:585; SEC-4 |
| Act after a stop | Fails. `reply-next` is refused too, because a stop pauses the agent | T:904 |
| Steer the read into superseding a real item | Recovers. The newer text is held, goes `unverified` if the page didn't show it, and the card is raised again | T:438 |
| Steer the read into closing it as answered, or gone | **Passes, with no page read at all** | SEC-3 |
| Claim for the wrong author | Refused when the name differs, and audited after the fact against the page. Two people with one name can't be told apart | T:543, T:593 |
| A claim left open by a killed run | Settled `unknown` at the next slot, or by the mail check while paused. Never retried, and nothing resolves it | T:700 to T:786; P23 |
| A DM target look-alike | Host look-alikes, `http`, a user name, a backslash, a climbing path, `%2f`, and a repeated, `;`-joined, non-ASCII or non-numeric `selected_item_id` are all refused. **`asset_id` isn't looked at** | P20; SEC-2 |
| What an upload path looks like now | There isn't one. `file_upload` and `upload_image` are denied by name and `images=[]` fails any attempt, even of the run's own scratch file. `reply-due` and `reply-next` hand out only `read_file` and `live_text_file`, both absolute, and `GuardedPath` keeps both flags to the run's folders. `--read-file /etc/hosts` is refused | P21; T:227, T:237 |

**The developer's two reported fixes both hold.**

- **`inbox-send` and live social claims.** `send.py:227` skips anything outside `MAIL_SOURCES`, `send.due` joins only on `email-reply`, and `_settle_held` acts only with the browser lock free. T:777 and T:797 prove it.
- **The email cap.** `store.py:416` counts mail sources only, and its one caller is `send.py:150`. Social replies count from the claim at `reply_run.py:87`. T:284 and T:298 prove it.

## Standards

### Should fix

- **The new Discord lines are never swept.** `tests/test_inbox_social_reply.py` plants nothing and never calls `assert_clean`; it uses `sweep` only for `outbox_dir` at T:123. Rule: README, "A test that builds a Discord message plants the secrets and personal data in `tests/sweep.py` where its builder reads, then calls `assert_clean`". `reply_run.tell` (`reply_run.py:433-459`) and the card (`social.py:177-185`) both build Discord messages.
- **A limit that isn't enforced as one.** `caps.INBOX_SOCIAL_REPLIES_PER_RUN` (`caps.py:108`) is only printed at `reply_run.py:238`, and the real limit is `claimed_by(...) is not None` at `:237`. Rule: "Hard limits live in `jura_growth/caps.py`". `social.py:127,166` also restate `INBOX_REPLY_WINDOW` as words.
- **Reuse: new code that repeats what the repo has.**
  - `watch.py:237` hand-builds a query string, which `urlencode(..., doseq=True)` does (used at `outreach/compose.py:204`). It also drops the re-encoding.
  - `reply_run.tell` (`:433-459`) mirrors `send._tell` (`send.py:309-332`).
  - The "UPDATE ... send_attempts + 1" at `reply_run.py:304` is `send.py:211`.
  - `expire_due` then `sweep_safely` at `reply_run.py:137-138,216-217,281-282` is `job._cards_read_again` (`inbox_browser/job.py:134`).
  - `reply_precheck` (`job.py:153-160`) repeats `precheck` (`:52-60`), and `_reply_audit`'s opening repeats `_audit` (`:67-70`).
  - `watch.py:348,350` inline `social.platform_of` and an `is_dm` test (`social.py:47-52`).
  - `social.py:142-144,187-218,228-253,256-270` mirror `kinds.py:71-73,310-339,362-391,406-419`. Possible Duplicated Code, and a fix to one fail-closed path won't reach the other.

### Nit

- `store.CLOSED` (`store.py:53`) collides with the glossary's **Closed** (`CONTEXT.md:277`). At `reply_run.py:252-255`, the word `gone` maps to `CLOSED` and the word `closed` maps to needs-you. Possible Mysterious Name.
- `Reply.kind` (`social.py:70`, comment or dm) clashes with **Approval kind** (`CONTEXT.md:131`).
- `reply_is_due` (`reply_run.py:154`) exists so that `audit.py:115`'s `"due": true` doesn't match it, and no comment says so.
- `words[0]` to `words[3]` at `reply_run.py:192,201`. `close_and_tell` (`store.py:423`) tells nothing itself.
- `as_json` is unused (`commands.py:123,126`). `tell_now` (`reply_run.py:462-466`) only imports `send` lazily, to get round a cycle (`send.py:49`).
- "an item to answer by hand" (`README.md:214`, `social.py:11-12`) uses "item" alone, against `CONTEXT.md:240`. Older inbox prose does the same.

## Spec

### Blocking

**P-1. `sent` isn't evidenced.** `reply_run.py:369-376` compares only the model's own file, and `inbox_browser/job.py:184-193` checks only the pre-claim read against Chrome.
Spec: D4, "then reads it back"; F15, "One line in `#mission-control` on `sent`".
Reproduced, each ending `status=ok`, `sent` and no pause:

- P7: no page read after the send, and the live file copied from the handed-out text.
- P7b: the page read after the send shows `Couldn't send. Tap to retry` and not the reply.
- The spec reviewer's probe: claim, type nothing, `reply-done`. `#mission-control` says "A-0001 sent to Priya Nair".

The person is never answered, and Ting Yu has been told they were, so he won't look. Code review 05's B2 held the watch's N3 check to the page for the same reason.
**Fix:** in `reply_after_run`, `sent` stands only if the transcript shows the whole text typed, one send, and the draft's words in a read result on the claimed thread after that send. Otherwise the item is `unknown` and the agent pauses, with fixed words.

**P-2. A read of one item closes another approved reply.** `reply_run.py:245-251` takes `waiting[0]` and ignores `handed_to`.
Spec: F9, "Only a clean read is claimed". Reproduced two ways:

- P4: a `high` card approved between `reply-due` and `reply-next` ends `needs-you`. His approval is superseded and the note is false ("couldn't get a clean read of this thread"). Nothing was steered: he only has to press Approve while a run reads, and an older card does the same.
- P5: `reply-next` run three more times in one run closes three more approved replies, with `status=ok` and no pause. A steered model can empty the queue this way.

P30 is the same hole from the other side: a run that skips `reply-due` still claims, and then `handed` is None, so nothing binds it to the thread (SEC-1).
**Fix:** `next_reply` judges only `handed_to(conn, run_id)`. No hand-out means no claim and no closure. An item that isn't the one handed out is left alone. A read for an approval that is no longer first returns `due: false` and changes nothing. `tests/gate_adapter_social_reply.py:85` narrows `due` and claims with no hand-out, so it needs to call `hand_out` first.

**P-3. UAT Part B's first command fails, and pasting the block goes on to read the real accounts.** `reviews/uat.md:39-42` runs `pause inbox-browser` before `git pull`. `main` has no `inbox_browser` plug-in, and `main`'s `pause` in `cli.py` refuses an unknown agent.
Spec: `uat.md:36`, "in this order, so nothing reads Facebook or Instagram until you say", and the test strategy's exit criterion on the pause.
Run as written, the pause errors, `git pull`, `uv sync` and `schedule install` still run, and `inbox-watch` reads at the next `:05`. The setup guide has the right order (`setup/inbox-watch.md:15-29`). `test_uat_part_b_opens_with_the_pause_before_schedule_install` checks only that the pause precedes the install.
**Fix:** match the guide's order, and have the test assert `git pull` comes before the pause.

**P-4. The canary rows can't be followed in the order given.** `uat.md:51` runs H at step 7, and `uat.md:52` resumes `inbox-browser` at step 8. H3 and H4 need that job running.
Ticket: "UAT Part B reads for a canary from that folder ... for both inbox browser jobs, because no double can prove what Claude Code does with those rules."
"Before the first real message" also can't hold: `inbox-check` starts at install, and `uat.md:49` sends a real enquiry before step 7. The setup guide, which is what he follows first, never mentions canaries, and its section 6 approves real replies. So the one proof of the fence on the real Claude Code can come after the replies it was meant to protect. The tests check for the strings only (`test_inbox_setup_guide.py`).
**Fix:** H1 and H2 with `inbox` paused until they pass, H3 inside the guide's watched run in section 5, H4 before section 6's first approval that isn't the canary, and one line in the guide pointing at each.

### Should fix

- **S-4. A login wall on a DM run reads as an audit failure, and alerts twice.** `inbox_browser/job.py:179` with `audit.py:216`. Spec: S4, "stops at once, alerts once". Reproduced (P16): a redirect to `/accounts/login/` then `inbox stopped --reason login` gives "The audit of run 1 failed" and two messages in `#alerts`. The audit's own docstring says a redirect is the platform's choice (`audit.py:63-64`), and setup guide step 21 tells him to expect one message from the usual stop. T:870 misses it, because its stop page keeps the target's address. **Fix:** hold `places` to what the run asked to open, as `asked_check` does, or clear a shown address when a stop follows.
- **S-5. A sticker skips the newest-message check.** `reply_run.py:224-225`. `newest_from_them: ""` with `newest_attachment: sticker` claims on a page showing a newer written message (P31), and naming the old message does the same (P32). F9's "only a clean read" rests on the model's word for what is newest, which no check can fully prove. The harm is bounded, because only the approved text can go, in the right thread. **Fix:** confirm a claimed attachment against the page where it can be, and record the limit in ADR 0006, which now reads as if the code had decided.
- **S-6. The prompt leaves paths with no instruction** (`prompts/inbox-reply.md`). Each fails safe, except the first:
  - The page won't load, or a tool errors, at step 4. Nothing says what to do, and "isn't there" is one word away from `gone`, which closes the item (SEC-3). Say: end with `FAIL:`, and the reply stays approved.
  - The session's identity isn't shown on the page, at step 5 (SEC-2).
  - Typed, sent, and the reply isn't on the page, at step 7. Say what to write: what the page shows, even if empty, which reads as `unknown`.
  - `reply-done --url` refused, at step 8. Nothing says what next, and it settles `unknown`.
  - "Only the target ... Trying one fails the run and pauses it" (`:22-24`) is false on a comment run (SEC-1).
- **S-7. `reply-done --not-sent` tells him a typed reply didn't post.** See S-2 under Security for the code, and `reply_run.py:454-455` for the words. F15 asks for "may have posted" on `failed` too. T:822 pins "didn't post". That is better wording when it's true, so keep it and log the departure, once `--not-sent` can be trusted.

### Nit

- `setup/inbox-watch.md:67` says "the watch" lists Junk. The mail check does (`mail.py:10`).
- Step 10 of the prompt says `OK: replied` on the `--not-sent` path too. The summary is rewritten, so nothing reads it, but the DM section's not-sent path gives no ending at all.
- A claim stays `sending`, with no alert, while `inbox` and `inbox-browser` are both paused, since neither precheck runs. Both are his own pauses, and the one-pager shows it (`one_pager.py:97`).
- The guide has him edit `config/inbox.yaml`, a tracked file, in the live checkout, which can block a later `git pull`. It doesn't say where an IMAP password comes from, or that `/growth status` may also name `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.
- `reword` refused while the browser is paused (`steer.py:61`) and the `fixture-reply` seed weren't asked for. Both are harmless and useful.

### Reading the setup guide as Ting Yu

He can follow it alone. It pauses `inbox-browser` first and only then installs the schedule, restarts launchd, sets `#mission-control` and the other two channels to all messages, tells him how to decide on the second mailbox (a blank `ENQUIRY_IMAP_PORT` reads as 993), and reads `auth_servers` from a real enquiry's raw headers. It also names the Chrome profile, checks `pages`, runs one watched run before any reply, and says what `unknown` means and that the Junk rule is by design. The faults are P-4's missing canaries, S-4's second alert at step 21, and the nits above.

### Accept table

| Clause | Met | Proof, or the finding against it |
|---|---|---|
| Gate matrix, Terminal refusal, switch reading `publish` | yes | `gate_adapter_social_reply.py`, 49 cases; T:910 |
| D4 DM in the thread | partly | T:197, T:636; SEC-1 when `reply-due` is skipped |
| D4 comment under the comment | no | T:314 asserts only `kind` and target; SEC-1 |
| D4 one per run | yes | T:247, T:258; but P-2 |
| D4 read-back | no | P-1 |
| F5 Accept | yes | T:363, T:373, T:381. What the click did is UAT U5a's |
| F9 for social | partly | T:395, T:473, T:487; SEC-3, P-2, S-5 |
| `inbox-social` refuses every line break | yes | T:1047, T:1053, including U+2028, U+2029 and U+0085 |
| `one_line` end to end | yes | T:618, ten cases; S-1 to S-3 at its edges |
| N3 of functional | yes | T:325, T:333, T:341 |
| N13 | yes | T:700 to T:786; P23 |
| S4 of functional | yes | T:487, T:499, T:881, T:1296; S-4 is the PRD's S4 |
| A watch that finds it answered closes and reports it | yes | T:1246, T:1263. This path is held to the page, which is what SEC-3 asks of the other |
| `uv run pytest` green | yes | 5920 passed |
| Guide: Junk stays noise | yes | `setup/inbox-watch.md:67-69` |
| UAT `auth_servers` | yes | `uat.md:49` |
| `CLEAN_CWD_JOBS`, absolute paths | yes | `caps.py:53`, T:147, T:227, T:237 |
| UAT canary for both browser jobs | partly | Rows exist at `uat.md:125-128`; P-4 |

## Security

### Blocking

**SEC-1. Approved text can go to a thread nobody approved, and the run ends clean and `sent`.** `inbox_browser/job.py:177-179` passes `places` only for a DM, and only from `handed`. `reply_run.py:367` then takes the read-back's address from the model.
Spec: D4, "A comment replies under that comment; a DM goes in that thread". `social.py:12` says "the read-back holds it to its post". It can't, because the address is the model's word and is never compared with where the tab went.
Reproduced, each `status=ok`, `sent`, no audit failure:

- P6: a comment run navigates to `https://business.facebook.com/latest/inbox/all?selected_item_id=777`, types, presses Return, then calls `reply-done --url <the comment>`.
- P6b: the same onto `https://www.facebook.com/jurasolutionssg/posts/555`.
- P30: a DM run skips `reply-due`, puts the A-id in the read file, and types in `/direct/t/999/`.

A DM run that does call `reply-due` is caught (T:636), so the check exists and is only missing here.
**Fix:** bind both kinds to the claimed item, with a `place_check` built on `watch.thread_of`, which already knows a comment's post. Require the read-back's address to be one the run's tab showed. P-2's fix closes the third case.

**SEC-2. A reply can go out as the wrong identity.** `reply_run.py:256-259` compares `acting_as` with the configured name, and `reply_run.py:160` hands the model that name first. `_read_shown` (`job.py:184-193`) checks the author and the newest message against the page and never the identity.
Spec: D4, "The run acts only as the Jura Page or the Jura Instagram account".
Reproduced (P12): every page shows `Levi Ting`, the read says `jura_solutions`, and the run ends `ok`, `sent`, unpaused. The browser is signed in as Levi's profile, so this is a real route on `/messages/t/<id>`.
`asset_id` makes it worse. `hosts.dm_target_problem` admits `https://business.facebook.com/latest/inbox/all?selected_item_id=123&asset_id=999`, and neither `hosts.same_thread` nor `watch.thread_of` tells it from `asset_id=1` (P20). In Business Suite that value is likely what picks the Page (untested live), and a second Page under one login would reply as the wrong company, which the root `CLAUDE.md` forbids outright.
**Fix:** stop handing out `posting_identity` before the read. Check `acting_as` against the page in `_read_shown`, failing the run. A session whose identity the page doesn't show reports nothing, and the item becomes a hand reply with no stop. Refuse an `asset_id` other than Jura's Page, once the first-run check has recorded it, and make `same_thread` compare it. Also narrow `_SUITE_INBOX` (`hosts.py:170`), which binds `/latest/inbox/settings?selected_item_id=123`.

**SEC-3. A steered or careless read closes a real item, unchecked, and tells him something false.** `reply_run.py:252-255` and `:262-263` act at once on `target` and `page_answered`.
Spec: R3, "The triage model cannot hide a person"; F9. `watch._hold_answered` says why this can't be allowed: "Held until its checks ... so a steered run can't close a card". The reply path skips that.
Reproduced (P2): with no page read at all, `page_answered: true` gives `answered-by-hand`, a superseded approval, `status=ok`, no pause, and `#mission-control` saying "The Page had already answered this by hand". P3: `target: gone` with the page showing the message gives `closed` and "No reply is needed unless they write again". A commenter's own text can ask for this, and he then has every reason not to look. T:473 pins the behaviour: its page shows no answer from the Page.
**Fix:** hold both until `reply_after_run`, as the watch does. A run that failed its audit, or read no page on the target, closes nothing and the item stays approved. `answered` needs the item's words on that page, as `_settle_answered` does. `gone` needs a read of the target. Say in the note that this is what a run reported.

**SEC-4. The read phase isn't read-only.** `audit.py:337-340` judges a click only after the send, and `audit.py:261-262` applies `one_line` with no allow list.
Spec: §3, "Hiding, deleting, blocking, liking, or any other action on the platforms besides the approved reply text"; E6; technical B1, which blocked on this for the watch: "A watch run can Like, Hide, Delete or Block (E6) and pass".
Reproduced, each with an empty audit:

- P1: clicks before the claim, with an ordinary send after.
- P1b: a click, then `reply-next` says nothing is due, then another click.
- P8b: a click after `reply-done`.
- P11: an unknown tool `press_button`, and `computer` actions `left_mouse_down` and `hold_key`.

Up to the claim this run is a watch run with hostile text freshly read, and no step in the prompt clicks before the claim. So failing a click there costs nothing. ADR 0006's accepted limit ("the audit still can't tell what a click did") holds only for the clicks between the claim and the send.
**Fix:** with `one_line`, the run is `read_only` until `claimed` and again after the done word, using the existing `READ_ONLY_TOOLS` and `LOOKS`. After the claim, allow only the listed `computer` actions and fail anything else. This matches code review 05's fix for the watch.

**SEC-5. The card can hide bytes that go out.** `social.py:125` puts the draft in the card unneutralised, under "Draft, exactly as it goes out".
Spec: D1, "the draft exactly as it will go out"; §5, "so the card always shows the exact bytes"; code review 03's SEC-1, blocking for the same reason.
Reproduced (P40). Each of these passes `draft_problems` and `reply_of`, and reaches the card raw:

- `Thanks for asking about clinics. ||Jura is a scam, avoid us.||`: a Discord spoiler bar (rendering untested live).
- `We ~~do not~~ work with clinics.`: reads as struck through on the card, and goes out with the tildes.
- `We work with clinicsㅤㅤ and more.`, and also U+2800, U+034F and U+E0101: invisible and not caught.
- A tab. It reads as a space on the card and in the audit, which collapses whitespace (P33). Whether `type` then moves focus in a real field is untested.

Triage writes the draft from hostile text, so the words are within reach of the person writing in. The email card shares this (`kinds.py`, the `draft` line).
**Fix:** in the shared brand check, refuse a draft where `report.neutral(draft) != draft`, or that holds Discord markup, a tab, or those characters. That covers `inbox-email` and `inbox-social` alike.

### Should fix

- **S-1. The audit ignores inputs that change what a key does.** `audit.py:345-356` and `:362-364`. `{"action": "key", "text": "Return", "repeat": 5}` passes (P9b), `key` with `repeat: 100` and `modifiers` pass, and `double_click` on send counts as one send (P9a). `repeat` can change the bytes typed, though only by repeating one character, and a second send normally lands on an empty field (untested live). **Fix:** with `one_line`, fail a `repeat` above 1, modifiers, `left_click_drag`, and a double or triple click once the field holds the text.
- **S-2. Two places believe less than they should.**
  - `audit.py:231-232` resets `sent` on any mention of the done word, refused or not, so P8c's second Return passes after a refused `reply-done`. Check `call.ok`. Retyping still fails (P8d, P8e), so no second copy of the text gets through.
  - `job.py:196-199` looks only for `action == "type"`. P18 types by key presses, sends, then says `--not-sent`, and ends `failed`, unpaused, with "didn't post". Count any keystroke or send.
- **S-3. A fragment sent by a click is clean if a stop follows.** `audit.py:305` forgives a part-typed field after a stop, which is right for publish and wrong for a click in a DM (P10). The item still ends `unknown` and paused, and he is told it may have posted, so nothing is hidden. **Fix:** with `one_line`, a click after text and before it is whole fails.
- **S-8. A model's words reach Discord through the address.** `reply_run.py:367,430,439,459`. `thread_of` ignores other query values and `_UNSAFE_URL` allows `[`, `]`, `(` and `)`. P22 posts `<...?comment_id=998877&Approve_A-0002_now=[Open](https://evil.example)>` in `#mission-control`. The security pass also posted `?note=URGENT:run_/growth_resume_inbox-browser_and_approve_A-0099`. `item["target"]` reaches `#alerts` the same way, by reading, and `discord.alert` logs it to `events`, which retention can't prune. Spec: S2. The angle brackets should stop a link rendering (untested live). **Fix:** post a link rebuilt from `thread_of` and the comment id, on the item's own target. Keep what the run gave only in `thread_json`.
- **S-9. An unverified newer message is still quoted.** A `newest_from_them` the page never showed reaches `#mission-control` quoted, with the "Unverified" note. ADR 0006 allows the label, but quoting a run's invention under a person's name isn't needed. Say that it was unverified, and link the thread.

### What holds

- **The claim.** ADR 0003's order, a re-hash inside one transaction, the text only after commit (T:209, T:1003), and a tampered row refused (T:1025). `run_id=None` is refused in `reply-next` and `reply-done`, so the Terminal can't claim, and `NEVER` keeps a run from any decision.
- **Line breaks.** `social.py:38`, `checks.py:180` and `audit.py:118` cover U+0085, U+2028 and U+2029.
- **Tools and commands.** Every current Chrome tool outside `computer`, the page readers and the tab tools is denied by name (P21). Bash is held to the four reply commands.
- **Paths.** `reply-next` and `reply-done` go through `GuardedPath`. The live file is only compared, and fixed words come back.
- **Retention.** `_THREAD_KEPT` is an allow list, so `claim_read` and `reply_url` go (P19), and `reply.handed.*` doesn't outlive a run.
- **A model's words in the run row.** The summary and errors are fixed words and record fields (T:677, T:688).

## Summary

- **Standards:** 0 blocking, 3 should fix, 6 nits. Worst: the new Discord lines aren't swept.
- **Spec:** 4 blocking, 4 should fix, 5 nits. Worst: P-1, since he is told a reply went when nothing proves it.
- **Security:** 5 blocking, 5 should fix. Worst: SEC-1, since an approved reply can land in another person's thread with a clean audit.
