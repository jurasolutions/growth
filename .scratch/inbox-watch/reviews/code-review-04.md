# Code review 04: he can see and steer it from Discord

Branch `crew/inbox-watch-04-steer` at 0c647f6, against its merge-base with `crew/inbox-watch`, 7f2a79a (three commits, efcdaa9, 7086690 and 0c647f6, 37 files). Spec: the ticket, then the PRD with its "Amended" sections, then the functional, technical and test-strategy reviews, ADR 0002 and 0004, and `docs/dispatch-contract.md`.

**Verdict: changes-requested.** The verdict rests on the four blocking findings below: P-1, P-2, SEC-1 and SEC-2. The wall around the commands is sound: no run reached a steering command, directly or through `remote`, and a hostile message can't become guidance. The defects are inside the commands. `done` launders an item past the "never sent again" rule, a redraft's ask outlives its card, and `unsuppress` trusts one column and two addresses further than it should.

**How this was checked.** Line numbers are at 0c647f6. "Reproduced" means it ran on the repo's test doubles in a throwaway detached worktree, under the worktree exports, and each finding gives its input. That worktree has been removed. Nothing touched a real mailbox, Discord, Resend or D1. The Standards, Spec and Security reads were done separately from this diff, and each finding kept here was checked again by hand.

| Check | Result |
|---|---|
| `uv run pytest -q -p no:cacheprovider -o addopts=""`, worktree exports, at 0c647f6 | 5597 passed in 408s |
| Build, typecheck, lint | None configured (operating card). `pyright` was not run |
| Blocked paths | None in the diff. No file under `jurasolutions/inputs/` or `design-system/` is newer than this ticket's work |
| UI files | None in the diff, so `crew:web-design-review` doesn't apply |
| The stray empty file in `jurasolutions/` | Gone. The folder's top level holds only `CLAUDE.md`, `.DS_Store` and the usual folders, and its mtime (2026-11-01 00:56) fits a file made and removed. The only empty file outside runtime locks and old scratch is `inputs/do-not-contact.csv`, dated 2026-10-31 02:01, which `agents/scout/dnc.py` reads and which predates this ticket |

## The questions in the brief

| Question | Answer |
|---|---|
| Can a scheduled run reach `redraft`, `reword`, `draft`, `done`, `unsuppress`, directly or through `remote`? | No. Reproduced with `JURA_GROWTH_JOB=inbox-check`: all six commands and `remote … inbox list` exit 2 with "may not use". Enforced on the leaf callback (`headless.py`), and `commands.py:117-121` also needs an `Origin` that only `remote` puts in the click context |
| Can a hostile message's text become guidance or reach a privileged path? | Not as guidance: only `store.ask_for_draft` and `reopen_for_draft` write it, both from `steer.py`. `submit` can't set `asked_at`. But see SEC-2: a hostile `Reply-To` chooses which address `unsuppress` lifts |
| Does `reword` bind the new approval to exactly his words? Can it reword something claimed? | Yes, and no. The draft is written and the request raised in one transaction, so the new hash covers his words (`steer.py:144-150`). Claimed and approved cards refuse (`steer.py:80-83`), rechecked under the lock (`:145`) |
| Does `unsuppress` ever lift a suppression from a link, a bounce or a complaint? | Yes in one case: SEC-1. A row that came from a reply keeps `source = reply` when a stronger event lands on it |
| Is the one-pager's read model read-only, with no `content()`? | Yes. `mission.py:185` opens `mode=ro`, `one_pager.py` only reads, and `test_inbox_replies_waiting.py:258-260` makes `content()` raise |
| Does retention remove the words everywhere? | From `growth.db`, yes. Reproduced: after a reword, a redraft and a skip, then the clock past 90 days, no table held the body, subject, draft, guidance, name or address, and a later `cards.sweep` ran clean. The outbox goes in 14 days and `inbox-check`'s transcripts in 7 (`caps.THIRD_PARTY_TEXT_JOBS`). The copies Discord itself holds stay: P-8. A typed mistake can reach `events`: SEC-5 |
| Can a stale approval go out over a requested redraft? | Not stale bytes. A card approved before the redraft refuses it (`steer.py:82`). A card approved after goes out as exactly what he approved (reproduced), under ADR 0003's hash. Keeping the card open is the better design and functional S1 asks for it ("the old card closes only after the new one exists"). It is safe to keep, once P-2 and P-3 are fixed and P-7 records it |
| Both `//` and `\n\n` as paragraph breaks? | Yes, as whole words. Reproduced: `Thanks for asking. // Levi will write back.` and the same with `\n\n` each make a blank line, and `https://jurasolutions.sg//x` and `--flag` pass through whole. See the nit on a `\n\n` glued to a word |

## Standards

### Should fix

- **S-1. `backup.py:55` lets config raise the outbox limit.** It breaks the operating card's "a config value may lower a limit, never raise it". `outbox_days` is read raw, with no `caps` constant, so `outbox_days: 400` keeps people's words past 90 days. Its own docstring says it "mustn't outlive PRD §4's limit", and `_browser_days()` at `backup.py:103-106` shows the pattern: a constant and `caps.effective`.
- **S-2. Reuse.** New code repeats what exists.
  - `one_pager.py:74` and `report.py:268,284` hand-write the query of `approvals.latest`, which says "Reads only, so it works on the read model's read-only connection". The comment at `one_pager.py:73`, "`approvals` functions may supersede on a read", is wrong for that function.
  - `one_pager.py:139` and `report.py:270` repeat `approvals.format_id`.
  - `one_pager.py:85,87` and `report.py:269,285` use `"pending"` and `"approved"` where `approvals.PENDING` and `approvals.APPROVED` exist.
  - `signals._plural` copies `health._plural` (`health.py:134`), and `one_pager.py:173-177,231` writes it out again.
- **S-3. `README.md:239-263` omits the new `retention` and `one_pager_section` hooks.** `CLAUDE.md` says the README covers the plug-in interface, and that table is it.

### Nit

- **S-4. Test tokens.** The strategy's line 3 says tests cite criteria as `IW-…` so tokens can't collide. `test_inbox_steer.py:70` uses `s1` for functional S1, where the strategy's S1 is untrusted text, and `test_inbox_replies_waiting.py:302` and `test_inbox_signals.py:241` use `s7` for two different things. The file headers say so, which is why this is a nit.
- **S-5. Judgement calls, not rule breaks.**
  - Possible Mysterious Name: `kinds.py:55` `_SUBJECT = store.approval_subject(0).removesuffix("0")`, with `kinds.subject_of` now a pure delegate.
  - Possible Feature Envy: `steer._restore_lead` (`:268-274`) writes outreach's tables, and `steer._also_on_the_website` (`:252-262`) belongs in `suppression.py`.
  - Possible Primitive Obsession: `report.py:167` reads the note's prose (`"unsuppress" not in newest["note"]`), and `steer.py:196` probes with `{**item, "draft": "x"}`.
  - Possible Duplicated Code: `steer._CLEARED_BY_DONE` and `one_pager._LISTED` are the same five states, and `LISTED_DAYS` and `HAND_REPLY_LISTED_DAYS` the same 7.

## Spec

### Blocking

- **P-1. `done` then `draft` sends an `unknown` item again, and undoes the `failed` and `unverified` guards.** PRD: "There is no resolve command: an unknown item is never sent again (N13)". Contract, `dispatch-contract.md:96`: "an `unknown` item is never sent again either way". N3: an unverified item gets "no draft".
  - **Why:** `done` moves `unknown`, `failed` and `unverified` to `done` (`steer.py:37`, `store.py:358`). `_why_no_draft` (`steer.py:175-200`) judges only the current state, and `_mark_unknown` leaves `sent_at` empty (`send.py:216-217`).
  - **Reproduced:** an approved reply gets a Resend 500, then passes the 23-hour line to `unknown`. `inbox draft I-0001` refuses, "A reply already went, or may have". `inbox done I-0001` clears it. `inbox draft I-0001` now answers exit 0. A new card, an approve and `send_due` make a second POST, with a different body, under the same `jura-inbox-reply-1` key. Once that key's 24 hours have gone, nothing stops a second email reaching them. The same two commands reopen a `failed` item past the guard at `steer.py:183` and an `unverified` one past `:179`.
  - **Also:** `done` isn't in `store.NOT_HISTORY` (`store.py:60`), so an unverified message's unproved words join the conversation triage reads and the brand check's `their_words`.
  - `test_iw_n13_done_on_an_unknown_item_never_sends_it` (`test_inbox_steer.py:422`) only runs `send_due` after `done`, so it can't see this.
  - **Fix:** clearing must not erase what the item was. Keep the state and set a cleared stamp, or refuse `draft` on anything with `send_attempts` or a claimed approval, and keep unverified words out of history. Test the three sequences.
- **P-2. A redraft's ask outlives the card, so its guidance and `must_draft` reach his next, unrelated message.** PRD E1: "Don't draft for a bare like, an emoji, 'thanks', 'nice'". `steer.py:11` and the contract say approving "drops the redraft".
  - **Why:** `_settle_redrafts` (`triage.py:134`) reaches only `state = waiting` through `store.asked_redrafts` (`store.py:321`). A skip moves the item at once, and a claim can move it first, so neither clears `asked_at` or `guidance`. `_shown` then reads `asked_at` on every item in the conversation, whatever its state (`triage.py:210`, `:221`).
  - **Reproduced:** `inbox redraft A-0001 offer them a free call`, then skip. `asked_at` and `guidance` stay after `settle`. The person writes "Thanks, that is all I needed." Triage is handed `guidance = "offer them a free call"`, `must_draft = true`. The approve-and-send path does the same: the item reads `state = sent` with `asked_at` set, and the next message arrives with `guidance = "shorter"`.
  - **Effect:** the prompt says "a class with no draft is refused", so a model that believes it drafts a sales offer at someone who said thanks, on guidance he gave for a card he has since closed. It lasts until retention. A card still stands between that and sending, so nothing goes out unseen, but he is asked to approve what he told the engine not to do.
  - **Fix:** clear both whenever the item leaves `waiting` for a closed state, and in `_shown` read the ask only from items still open. The D5 case (they wrote while a redraft waited) must still carry his guidance: `test_iw_d5_they_write_again…` holds that.

### Should fix

- **P-3. A redraft that lands after an approve supersedes the approved card.** `steer.py:11` says approving "sends what it says and drops the redraft". `_redrafted` (`triage.py:396`) doesn't recheck the record, so `approvals.request` supersedes the approved one. Reproduced: redraft, approve, then the handed-out triage submits: "OK: I-0001 redrafted", the old card reads `superseded`, a new one `pending`, nothing sent. Nothing unapproved goes, but his yes is dropped silently. Refuse inside `_redrafted`'s transaction when the latest record isn't `pending`, and clear the ask.
- **P-4. `done` exits 0 with a card waiting.** `dispatch-contract.md:96`: "Exit 1 while it has a card waiting". `steer.py:236-242` only checks for a card when nothing is clearable, so an older lapsed message plus a newer open card clears and answers 0. The ticket asks that "the contract tables match the code": change one of them. Read, not reproduced.
- **P-5. R2 and S16 cap what they promise in full.** R2: "for each, the sender's domain, so nothing can be silently swallowed". `one_pager.py:33-34,190-196` stops at 12 domains and 5 Junk subjects, then "and N more". The caps are right on the one-pager, but `/growth inbox list` reuses the line (`one_pager.py:243`) despite `limit=None`, so the rest show nowhere. Code review 01's P-4 notes Junk is the only sign of cold replies. Honour `limit=None` in `_noise_line`.
- **P-6. The first check reports every complaint in history.** `signals.py:105` starts at event id 0. On the first run each old complaint gets a `high` report and an `#alerts` line saying "outreach is paused" (`:115`), which may no longer be true. Start from the current newest event id when no cursor exists. Read, not reproduced.
- **P-7. The D6 deviation isn't recorded where it counts.** D6: "Each closes the old card and raises a new one". The ticket's Accept line repeats it. The code keeps the card open, as functional S1 asks, and says so in `steer.py`, the contract row and `uat.md` U22, but not in the PRD's amendments or `crew-log.md`. No row covers the side effect that an approve in the wait sends the old text. Add one line to the PRD, which is the conductor's to write.
- **P-8. Retention doesn't say Discord keeps its copies.** PRD §4: "Text is removed 90 days after an item closes." Cards and R1 messages sit in Discord, and nothing deletes them. PRD §4 accepts Discord as a third party, and technical N6 scopes removal to `first_piece` and the outbox, so the code is within its brief. But `README.md:194`, `CONTEXT.md:272` and `text_retention.py`'s "What goes" read as if the words are gone. Say that Discord's own copies stay until he deletes them.

### Nit

- **P-9.** `_unread_line`'s docstring (`one_pager.py:222-224`) says the figure is "what that message said". `told_unread` is also written on a silent first read (`watch.py:647-651`), so R4 can show a figure no message said. The ticket says "from the latest watch message". Showing it seems the safer behaviour, so correct the docstring.
- **P-10.** R4 "counts reactions", and `store.py:239` counts only people's messages, where CONTEXT's Reaction includes a rise in counts and an app opened. Fine for the reader, but say so in the glossary or the line.
- **P-11.** A `\n\n` glued to a word stays literal. Reproduced: `Soon\n\nafter.` goes into the draft with the backslashes. N9 only asks for the word form and the card shows it, but on a phone this is the natural slip. Split on it inside a word too.
- **P-12.** An id too big for SQLite answers "failed: OverflowError: Python int too large…". Reproduced with `inbox done I-99999999999999999999` and `reword A-999…`. No harm, but it should read as "there is no inbox item".

## Security

### Blocking

- **SEC-1. `unsuppress` lifts a manual block, or a website click, that landed on a row a reply started.** PRD: "lifts a suppression that came from a reply, and only that". Contract: "Exit 1, with nothing lifted, for an unsubscribe click, a bounce, a complaint, a manual entry".
  - **Why:** `suppression.add` is `INSERT OR IGNORE` (`suppression.py:73`), and `steer.py:290` and `lift_reply` trust the row's `source`. A later event never changes it.
  - **Reproduced:** a reply suppresses `priya@clinic.example`. `jura-growth suppression add priya@clinic.example --reason manual` prints "already suppressed". `inbox unsuppress I-0001` answers exit 0 and the address is free.
  - **Website events:** the same row hides a click, a bounce or a complaint synced from D1, and `_also_on_the_website` is then the only evidence. It says "It fails closed", but `steer.py:255-256` returns None when `cloudflare.configured()` is false, and `configured()` is false whenever a `keychain:` secret can't be read (`config.py`, `security` failing or timing out). A locked Keychain under an SSH session, which is how Dispatch arrives, is a plausible way there. That path is read, not reproduced.
  - **Fix:** when a non-reply event meets an existing row, record it: overwrite `source` and `reason`, or keep a row per source. Then make `_also_on_the_website` refuse unless D1 answered, treating secrets that can't be read as no answer. Add the stacked case to `test_iw_e2_unsuppress_lifts_only_a_suppression_that_came_from_a_reply`.
- **SEC-2. A stranger's `Reply-To` chooses whose opt-out is lifted.** PRD E2: "An opt-out is honoured". Code review 02's SEC-2 drew this same line with `own_sender`.
  - **Why:** `unsuppress` acts on `kinds.addresses_of(item)`, which includes `Reply-To` (`kinds.py:90`), and checks only the row's source, not that this item caused it (`steer.py:283,290`). `_why_no_draft` then advertises the command (`steer.py:195`), and the answer names no address.
  - **Reproduced:** `victim@other.example` opted out by reply. A mail arrives `From: evil@bad.example`, `Reply-To: victim@other.example`. `inbox draft I-0001` answers "The address is suppressed (unsubscribe)… `/growth inbox unsuppress I-0001` lifts one that came from a reply". `inbox unsuppress I-0001` answers "I-0001's suppression is lifted", and the victim is free. From there `draft` and an approve would mail them, which I didn't run.
  - Ting Yu has to type the command, but the prompt is the engine's and nothing shows him it concerns someone else.
  - **Fix:** lift only what this item's own message caused. Record the causing item on the suppression, or at least limit the lift to the item's own unforged sender, and name the domain in the answer.

### Should fix

- **SEC-3. An address row and a domain row: it says lifted and isn't.** Contract: "Exit 1, with nothing lifted, for … a whole domain". Reproduced: a reply row plus a manual `clinic.example` row answers exit 0, "suppression is lifted", while `is_suppressed` still reads `manual (domain)`, and the lead has been restored. `suppression.source_of` looks only at the address row. Check the domain before lifting. It fails safe, since no mail goes.
- **SEC-4. Restoring a lead undoes someone else's unsubscribe record.** `steer.py:268-274`: on a lead with two contacts, the boss clicked unsubscribe and Priya said stop by reply. Reproduced: lifting Priya flips the lead from `unsubscribed` to `replied`, and `outreach_replies.unsubscribe` is cleared for the whole lead. The boss's own row stays and `replied` mails nothing further, so only the record is lost. Restore only when no other contact on the lead is suppressed.
- **SEC-5. A typo keeps his words in `events`, which are never pruned.** The contract says the event "keeps only the name and the id", and N6 is why. `remote._logged` (`remote.py:452-458`) keeps every word when `match` refuses. Reproduced: `inbox rewrd A-0001 Dear PRIVATETYPO` stores all five words. A mistyped reword is exactly a draft naming a person. Keep only the first two words of anything refused.

No SQL, shell or path injection was found. New queries use placeholders, `store.mark_alerted`'s column is a constant, the remote id is checked with `fullmatch` and words follow `--`, and `neutral` and the masking run before anything reaches R4.

## Summary

Standards: 3 should fix, 2 nits. Worst: S-1, config can keep words past their limit. Spec: 2 blocking, 6 should fix, 4 nits. Worst: P-1, an `unknown` reply can be sent again. Security: 2 blocking, 3 should fix. Worst: SEC-1, a manual block or a website event can be lifted.

**Verdict: changes-requested.**
