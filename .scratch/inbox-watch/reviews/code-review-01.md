# Code review 01: see mail and report it

Branch `crew/inbox-watch-01-see-mail` at d19419c, against the fixed point `crew/inbox-watch` at 478e4d2 (four commits, 30 files). Spec: the ticket, then the PRD with its "Amended" section, then the functional, technical and test-strategy reviews.

**Latest verdict: see Round 2 at the end of this file.**

**Round 1 verdict: changes-requested.** The verdict rests on the seven blocking findings below: P-1 to P-5, S-1 and S-2. The foundations are sound, and the suite is green, so these are gaps the tests don't look at.

**How this was checked.** Line numbers are at the branch tip. Every finding marked "reproduced" ran on test doubles in a throwaway worktree, since removed. Nothing touched a real mailbox or Discord, and how Discord renders text was not tested.

| Check | Result |
|---|---|
| `uv run pytest -q -p no:cacheprovider -o addopts="" -rs`, worktree exports | 4223 passed, no skips, in 325s |
| `tests/test_privacy.py`, `tests/test_outreach_privacy.py` | untouched in the diff, 68 passed |
| `tests/test_publish_audit.py` | untouched |
| Blocked paths (`inputs/`, `design-system/`, `.env`, `data/growth/`) | no change under any of them |
| Build, lint, typecheck | none configured (operating card) |

## The developer's departure on opt-outs

**The departure is justified, but its implementation isn't safe, so it blocks (P-1).** The amended rule read literally suppresses "How do we stop retyping invoices?" (6 words), and the Given/When/Then table, which wins, says it must not. An exception for some questions is therefore right.

The exception as built is too wide and points the wrong way. It tests for a `?` anywhere in the message and then only keeps the suppression if a narrow list of phrasings matches (`replies.py:51-54`, `:254`). So a real opt-out now fails unless it happens to match, and some real customer questions still suppress.

## Spec

### Blocking

**P-1. Real opt-outs are lost, and real questions still suppress.** `outreach/replies.py:51-54`, `:254`, the same function for the subject at `:266`. Breaks E2 ("An opt-out is honoured") and the F1 table ("a real question must not suppress"). Reproduced with `opt_out_reason`.

| Message | Result today | Should |
|---|---|---|
| `Can you stop?` / `Could you please stop?` / `STOP?` | nothing | suppress |
| `Can you stop spamming me?` | nothing | suppress |
| `Stop. Who gave you my address?` | nothing | suppress |
| `Please stop. How did you get my email?` | nothing | suppress |
| `How did you get my email? Stop.` | nothing | suppress |
| `How did you get this address? Remove it please.` | nothing | suppress |
| `Can you remove this address?` | nothing | suppress |
| `Could you remove jane@acme.sg from your list?` | nothing | suppress |
| `Please stop or I will report you. Understood?` | nothing | suppress |
| Subject `Stop?`, subject `Re: Can you stop?` | nothing | suppress |
| `How do we stop this happening?` | suppressed | nothing |
| `Can your tool stop these duplicate invoices?` | suppressed | nothing |
| `Can you remove my old invoices from the system?` | suppressed | nothing |
| `Do you stop sending reminders once an invoice is paid?` | suppressed | nothing |

The most common shape, an angry "stop" next to "how did you get my address?", is lost because the second sentence holds the `?`.

Fix:
1. Judge the sentence holding the word, not the whole message.
2. Exempt a question only when the word's object is plainly something else ("stop retyping invoices", "remove my old invoices"). Tighten `this`, `these`, `your` and `my` to the mail or the person: `my email`, `my address`, `these emails`.
3. When it is ambiguous, suppress. A wrong suppression is visible in R1 and can be undone with ticket 04's `unsuppress`, whereas a lost opt-out shows nowhere and the person may be chased.
4. Add the table above as test cases.

**P-2. Mail from a lead's domain skips the noise rule, so a newsletter can unsubscribe a lead.** `outreach/replies.py:289-291`, `inbox/mail.py:245-247`, and `_batch` at `replies.py:397`. Breaks R2, N4 ("Bounces and `mailer-daemon` count as R2 noise") and F1's "in a person's own words". This is new here: F2's domain match reaches addresses the old exact match never did. Reproduced through `mail.intake`:

| Sender | Headers and body | Result |
|---|---|---|
| `news@<lead domain>` | `List-Id`, `List-Unsubscribe`, footer "Click here to unsubscribe" | sender suppressed, lead `unsubscribed` |
| `noreply@<lead domain>` | "Your invoice is ready." | lead `replied`, follow-ups cancelled |
| `mailer-daemon@<lead domain>` | "Delivery failed." | lead `replied`, follow-ups cancelled |

Fix: when the match is by domain, apply `_noise_evidence` first, in both paths, and share the rule so the 16:45 check can't drift from it. It needs moving somewhere `replies.py` can reach.

**P-3. No production code records an outgoing `Message-ID`.** `inbox/store.py:207` has no caller outside tests, and `resend_payload` (`outreach/send.py:625`) sets no `Message-ID`. Breaks F4 ("Outgoing `Message-ID`s are kept") and F2 ("mail whose `In-Reply-To` or `References` names a message Jura sent"). `test_iw_f2_mail_naming_a_message_jura_sent_is_that_leads_reply` passes only because the test plants the row itself. `_batch` doesn't use the path either, so a paused inbox wouldn't get it once wired. No later ticket picks this up.

Fix: set a `Message-ID` on outreach sends and record it with the lead, or move this half of F2 and F4 into ticket 03's Accept line by name and remove the claim from this ticket.

**P-4. R2's list of noise senders reaches nobody.** `inbox/store.py:158` `noise_since` has no caller, and only the digest counts noise (`inbox/__init__.py:85`). Breaks R2 ("The one-pager shows the count and, for each, the sender's domain, so nothing can be silently swallowed"). `CONTEXT.md`'s Noise entry says the one-pager lists it, which isn't true yet. Ticket 04 owns the section hook, but its Accept line doesn't name R2, so nothing currently makes this happen. This matters more than it sounds, because S16 sends cold replies in Junk to this list and nowhere else.

Fix: name R2 and S16 in ticket 04's Accept line and take R2's list out of this ticket, or build it here. Either way, make the `CONTEXT.md` entry true.

**P-5. A `sqlite3` error in the precheck can auto-pause the mail, even across weeks.** `inbox/mail.py:210` re-raises `sqlite3.Error`, `:130` catches only `RepliesError`, `inbox/job.py:21-22` has no guard. Breaks B5 rule 1 ("three flaps ... pause mail for good") and the amended "so a bad message can't stop the mail". Two things combine:
- A locked database or integrity error leaves the precheck as a failed run. Reproduced: `OperationalError: database is locked` raised out of `job.precheck`. The database has a 30-second busy timeout and sits in OneDrive.
- A good check leaves no run row (`NothingToDo` becomes a `run.quiet` event), and `pause.check_auto_pause` reads only run rows. So failures spread far apart still count as "in a row". Reproduced: one failure, 50 good checks, repeated three times, and `inbox` was paused, with every later run `skipped`.

Network faults are handled properly: `OSError`, `ssl.SSLError`, timeouts, `IMAP4.abort` and `IMAP4.readonly` at login, select, search, fetch and list did not raise. Discord being down is also handled, because `_deliver` turns `httpx` errors into `DiscordError` and `test_inbox_report.py:184` covers it.

Fix: `job.precheck` must not raise for anything in the intake or the report. Catch per message and per check, log it, and alert once a day through the existing `_failed` path, so a real bug is still seen. Add a test that repeats failures with good checks between them. Ticket 02 will have the same exposure once triage exists.

### Should fix

**P-6. The 16:45 check crashes if `inbox-check` counts the same reply first.** `outreach/replies.py:408-413`, `:339`. Both jobs run at 16:45. `_batch` checks `counted`, fetches the body over the network, then runs a plain `INSERT` on a `UNIQUE` key. Reproduced: `IntegrityError: UNIQUE constraint failed: outreach_replies.message_key` out of `replies.check`. `sync.py:296` catches only `RepliesError`, so `scout-sync` fails, and `send.py:421` has the same exposure. Breaks "A 16:45 `scout-sync` counts nothing again" in the concurrent case. Fix: re-check inside `apply_reply`'s atomic step, or use `INSERT OR IGNORE` and act on the row count.

**P-7. A refused header fetch still moves the last-good-check stamp.** `outreach/replies.py:173-174`, `inbox/mail.py:201`, `:135`. Breaks B5 rule 3 ("the last-success stamp moves only when a check finished"). Reproduced: a `NO` on the header `FETCH` gave 0 items and a moved stamp. The one-day look-back recovers most of this. Fix: raise `RepliesError` on a non-OK fetch in the inbox path.

**P-8. A refused body fetch loses the message's words and any opt-out, for good.** `outreach/replies.py:188`, `inbox/mail.py:253-256`. Reproduced: `Please remove me` with a `NO` on the body fetch recorded empty text, counted the reply, and did not suppress, including on the next check. The 16:45 code had the same hole, but the inbox now also reports "(no text: see the mailbox)" forever. Fix: leave the message unrecorded, so the next check tries again.

**P-9. A real opt-out with a signature passes 12 words.** `outreach/replies.py:269`, `own_text` at `:239`. Reproduced: `Please stop emailing me.` plus a six-line signature is 15 words and suppresses nothing, and `Please remove me from your list.` with one is 18. This meets the amended rule's letter, which counts on triage for longer messages, but triage won't see all of them: not with `inbox` paused, and not when the mail is stale (state `reported`). It is the usual shape of a business email, not an edge case. See the question in the report: an explicit ask should suppress at any length.

**P-10. A reply's subject is Jura's own words, and it still suppresses.** `outreach/replies.py:266-268`. By reading, the subject path does this for `Re: Stop retyping invoices`. It meets the rule's letter but breaks its reason, "in a person's own words". Outreach subjects are written per lead, so one with `stop` or `remove` would suppress everyone who answers it. Fix: skip the subject when it matches, less `Re:`, one Jura sent that lead.

**P-11. The two checks don't quite share one rule.** `outreach/replies.py:403`, `inbox/mail.py:234`. Breaks F1 ("Both `inbox-check` and the 16:45 check use this one rule"). The 16:45 check tests the raw subject. Reproduced: `=?utf-8?q?please_stop?=` gives `None`, and `please stop` suppresses. Fix: decode the subject before the rule in `_batch`.

**P-12. A Keychain value it can't read reads as a quiet day.** `inbox/mail.py:104`, `outreach/replies.py:102`. Breaks B5 rule 1 ("no successful check for 2 hours, gives one alert a day"). Reproduced with `OUTREACH_IMAP_PASSWORD=keychain:<missing>`: `mailboxes()` returned `[]`, the check reported `failed=0`, and `setup_gaps` sees nothing because `is_set` never asks the Keychain. Fix: settings set but unreadable go through `_failed`.

**P-13. A sequence number can pair one message's headers with another's body.** `outreach/replies.py:183-191`, `inbox/mail.py:253`. By reading, not reproduced. If Ting Yu deletes a mail on his phone during a check, the numbers shift. Then one person's words appear under another's name, and an opt-out could suppress the wrong address. The 16:45 code had the pattern, but nothing showed the body then. Fix: compare the fetched body's `Message-ID` with the header's, and leave a mismatch for the next check.

### Nits

- **W6 test gap.** `tests/test_inbox_mail.py:276` never asserts the post with `inbox` paused, and no W6 test plants a queued follow-up. The code looks right.
- **S9, the reverse order.** A reply under 48 hours that the 16:45 check counted first also gets an R1 (`mail.py:304`, pinned at `test_inbox_mail.py:242`). The R1 adds his only view of the words, so keep it and record the decision.
- **Rescuing from Junk.** A message moved from Junk to the inbox stays `noise`, with no report, because `store.known` skips it. Reproduced. Worth a line in the setup guide.
- **Scope.** `COUNTED_JOBS` (N8, ticket 04) and the caps for later tickets came early. Both are harmless, and the `tests/` edits they need have to be listed in a `qa-*.md` under exit criterion 7.
- **Row-level `Reply-To`.** See N-1 under Security, which is for ticket 03.

### Checked and good

W1, including the strict double; W5; W7; W8; F3 for non-contacts; F12's mail half; S10 (the 16:45 check doesn't depend on the `inbox` pause); S11; the B3 class tests; B5 rule 2 (no transaction across the network; `StrictIMAP.watch` proves it, and `apply_reply` posts after its atomic step); B7; R5 (counts only); N5 apart from S-2 under Security; three tables in the migration; the Language terms in `CONTEXT.md`.

## Security

Threat model: anyone can email the watched mailbox, so its headers and text are hostile. None of these is high severity, since a person still reads everything and nothing is sent in this ticket.

### Blocking

**S-1. The signature check reads text that isn't a verdict, so a forged enquiry passes.** `inbox/mail.py:403`. Breaks the amended F3 ("needs Jura's DKIM pass to be treated as one") and IW-A9. The regex runs over the whole header. Reproduced with `_signed_by_jura`:

| `Authentication-Results` | Returns |
|---|---|
| `mx.zoho.com; dkim=none; spf=pass smtp.mailfrom=dkim=pass.header.d=jurasolutions.sg@evil.test` | True |
| `mx.zoho.com; dkim=fail (dkim=pass header.d=jurasolutions.sg) header.d=jurasolutions.sg; spf=fail` | True |
| `mx.zoho.com; dkim=pass header.d=evil.test; dkim=fail header.d=jurasolutions.sg` | False, correctly |

The first is reachable, because the sender chooses the envelope address and the server echoes it. The Security reviewer printed the effect: a report reading `Website enquiry` from `evil.test` with the "isn't signed" warning gone. The limit is that it must still reach the inbox: the Security reviewer's DNS lookup found the domain's DMARC at `p=quarantine`, and mail landing in Junk only becomes noise.

Fix: strip comments, split on `;`, and require a clause that itself starts `dkim=pass` with `header.d` at or under Jura's domain. Add the rows above to the tests.

**S-2. A nested masked link gets through the quote.** `inbox/report.py:31`, `:41`. Breaks IW-A5, which the ticket's Accept line names, and N5 ("a masked link shows its real address, unclickable"). The test strategy calls a failed adversarial case major. Ticket 03 will put Approve buttons beside this text. Discord's own rendering is untested, but the link syntax plainly survives. Reproduced with `report.quoted`:

`[[x](http://a.test)](http://b.test)` becomes `> [[x] (http[:]//a.test)](http://b.test)`

The Security reviewer also printed `[[Approve I-0007]](https://evil.test/a)` coming through unchanged. `|||hide|||` keeps a spoiler pair too.

Fix: `run_update.py:223` already has the rule, `text.replace("](", "]\\(")`, which holds for every nesting. Use it instead of the regex.

### Should fix

**S-3. Anyone's words can blank the frame around their own report.** `inbox/mail.py:307`, `privacy.py:293-296`. Plain masking blanks every `never_show` value, with no word boundary, and the report's head is plain. Reproduced: a mail from `a@evil.test` with the subject `evil.test` reports `**I-0001 · Email** · [removed], 26 Oct 11:00 SGT`, hiding the sender's domain. The Security reviewer also blanked the unsigned warning, a fold's text and an alert's text with the same trick. Fix: post the fixed frame as its own class, skipping `_never` and learned names. Don't widen what the conversation class covers.

**S-4. Anyone can unsubscribe a lead by forging a colleague.** `outreach/replies.py:291`, `inbox/mail.py:245`. Reproduced: `From: nobody-real@<lead domain>`, `Subject: stop`, `dmarc=fail` left the lead `unsubscribed` and the forged address suppressed. Forging a contact's exact address already worked, but F2 widens it to any local part. The `Authentication-Results` header is already fetched. Fix: let a domain match change state only with an aligned pass, and otherwise report it without acting.

### Nits

**N-1. For ticket 03.** The report's frame names the `From` domain while `thread.reply_to` may be another domain, and A9 says the card must show the real recipient domain. Reproduced by the Security reviewer. Carry it into ticket 03's Accept line.

**N-2. For UAT.** MX is Zoho. Whether a real enquiry carries a plain `Authentication-Results` is unconfirmed, and if it doesn't, the top header could be missing or the sender's own. Today's failure is safe: enquiries read as unsigned. Look at one raw message in UAT Part B.

### Checked and sound

- **Conversation class (the brief's main question).** It widens nothing beyond the quote block. A block holding the frame's text still matches only the block. If `redact` changes the block, the match fails to plain masking. Secrets, phones and named addresses mask inside it. Role addresses show, as they do in plain text. The fold and every other post stay plain.
- **Headers and CRLF.** `"levi@..." <x@evil.test>` gives `x@evil.test`; several addresses and RFC 2047 addresses give None; look-alike Jura domains aren't Jura. `_ids` keeps clean ids only, and `clean_line` strips subject and name.
- **IMAP state.** `select(readonly=True)` and `BODY.PEEK` only, on all paths, including Junk and the partial fetch. Folder names come from the server, not from mail.
- **Hostile text in R1.** All line-break characters get `> `, backticks are replaced, mentions are defanged, and `allowed_mentions.parse` is `[]` with embeds suppressed. `sender_domain` is limited to `ADDRESS_RE` characters, and `note` is fixed text.
- **Secrets in events.** Payloads hold counts, type names, domains and ids. `Account` keeps its password out of `repr`, and `problem` is fixed text. Attachments are names only.

## Standards

There is no `CODING_STANDARDS.md` or `CONTRIBUTING.md`, so the sources are `CLAUDE.md`, the operating card, `README.md`, `CONTEXT.md` and the ADRs. `caps.py`, the plug-in interface, ADR 0001 and ADR 0002 hold, and the core imports no agent by name.

### Should fix

**T-1. New code repeats helpers that exist (reuse).**
- `inbox/report.py:43` is a third copy of `remote.py:252-253` and `run_update.py:224-225`. Extract it to `discord.py`, and S-2's fix comes with it.
- `inbox/report.py:30` `_LINES` is a near copy of `inbox/store.py:36` `_LINE_BREAKS`.
- `inbox/settings.py:47` repeats the floor in `publish/limits.py:75`. Worth sharing as `caps.at_least`, which pairs with `caps.effective`.
- `inbox/mail.py:92-101` has the shape of `replies.py:106`, and `mail.py:307` repeats the `never_show` rule at `replies.py:417`.
- `inbox/mail.py:376` and `:435` repeat the same domain test, and `mail.py:428` repeats `replies.py:320`.

**T-2. Glossary "avoid" words (`CONTEXT.md`).**
- `:228` avoid "reply" for anything inbound: the report's heading `Reply to our email` at `report.py:55`, which Ting Yu reads.
- `:268` avoid "needs you": `open_counts["needs_you"]` at `store.py:181`, which becomes the digest figure `inbox_needs_you` at `__init__.py:95`.
- `:240` avoid "item" alone: `store.py:128`, `:137`, `report.py:3`.

### Nits (judgement calls)

- Possible Shotgun Surgery: the literal "48 hours" at `mail.py:277` and `report.py:111`, while `old_after_hours` can be lowered, so the text would then misstate it.
- Possible Mysterious Name: bare `40` at `report.py:109-110`; `_take` at `mail.py:224`; `mail._decoded` beside `replies._decoded`.
- Possible Feature Envy: `inbox_state` keys and raw SQL outside `store`, at `mail.py:143`, `:462`, `:489`, `commands.py:27-29`.
- Possible Divergent Change: `store.py:5` says "It knows nothing about mail", yet holds mail-check state and outgoing mail at `:185-226`.
- Possible Data Clumps: `conn, imap, known, budget, result, junk` at `mail.py:156`, `:192`, `:204`, `:224`.
- Possible Speculative Generality: `settings.py:10-16`, `:43` and `discord.edit(conversation=)` have no production caller yet, and later tickets need them.

---

## Round 2

Re-review of 92c6157 (new commits 5eb15b7, 6176f96, 92c6157), covering only what changed. Line numbers are at that commit. As in Round 1, probes ran on test doubles in a throwaway worktree, since removed, and Discord's rendering was not tested.

| Check | Result |
|---|---|
| `uv run pytest -q -p no:cacheprovider -o addopts="" -rs`, worktree exports | 4330 passed, no skips, in 328s |
| `tests/test_privacy.py`, `tests/test_outreach_privacy.py` | untouched in the diff, 68 passed |
| Blocked paths | no change under any of them |

**Round 1 findings.** Every Round 1 finding not named below is fixed. I checked P-2, P-6, P-7, P-10 to P-13, T-1 and T-2 by reading the change and running its new tests in `tests/test_inbox_review_01.py`, and re-ran these myself:
- P-1: every row of the table now comes out right.
- P-5: repeated failures left no run row and no pause, and a bug in `report_due` didn't raise.
- P-8: a refused body fetch recorded nothing, and the next check suppressed.
- S-1: both forged headers now return False, along with a quoted-string form and a look-alike domain.
- S-2: every nested link form printed `]\(`, with the address unclickable.

### The conductor's P-9 decision: it holds for the common phrasings, but not yet safely

An explicit ask with a signature now suppresses at any length, through both checks. The two messages from Round 1 (15 and 18 words) do. Giving the rule unlimited reach raises what a false match costs, though, and it has both kinds of error. See R-1 and R-2.

### The two pushbacks

**S-4 (only a stated failure blocks a colleague match): accepted, with one should-fix (R-4).** My Round 1 fix, requiring an aligned pass, was too strict. Plenty of small companies sign nothing, so it would chase a colleague who has already answered, which is the failure F2 exists to prevent. A forgery only ever reduces outreach, and R1 reports it either way, so a missing verdict acting is the right trade. Reproduced: `dmarc=fail`, `spf=softfail`, and `spf=fail` with `dkim=fail` change nothing and are still reported. No header, `none` throughout and an aligned `spf=pass` all still act.

**S-3 (no `never_show` from intake, no names taught, instead of a new frame class): accepted.** It removes the cause, and B3 only said intake "may" call `never_show`. Reproduced: subjects reading `evil.test`, `Website enquiry` and the unsigned warning itself, and `From: reply.email.next@evil.test`, all left the frame intact, with `_never` and the learned names empty after the check. A person's words have no other route to a plain post in this process: the run's summary is counts, and alerts are fixed text with a type name. One thing to carry: the same process in ticket 02 can post `outcome.error` to `#alerts` (`runner.py`), and `never_show` is no longer a net there, so ticket 02's S2 must cover that string as well as the summary.

### Are P-3 and P-4 really carried?

**P-4: yes, accepted.** Ticket 04's Accept line names R2 and S16, the sender's domain, the Junk subject, `store.noise_since` and the `CONTEXT.md` change, and ticket 04 owns the section hook that makes it possible. `CONTEXT.md` is true today.

**P-3: only in part (R-3).** F4 and the inbox-reply half of F2 are properly carried by ticket 03. The outreach half isn't carried at all: see R-3.

### Blocking

**R-1. The any-length rule suppresses customers describing what they want automated.** `outreach/replies.py:61`, `:63`, `:66`, `:68`, `:69`, `:70`. Breaks F1 ("Anything else suppresses nothing") and goes beyond the decision, which covers "an explicit ask to stop being contacted". Each of these suppresses the sender for good and marks the lead `unsubscribed`, at any length, and undoing it needs ticket 04. Reproduced with `opt_out_reason`, each followed by a long neutral sentence so that only the explicit rule can fire:

| Message | Matched on |
|---|---|
| `We would love to stop sending reminder emails by hand.` | stop |
| `We want to stop sending manual emails to our suppliers.` | stop |
| `How do I stop emails going to spam?` | stop |
| `Can you help us stop invoice emails bouncing?` | stop |
| `We need to stop the marketing emails going out twice.` | stop |
| `Can our clients opt out of the reminders?` | opt out |
| `Customers should be able to opt out of your automated follow-ups.` | opt out |
| `With your tool we would have no more emails back and forth with suppliers.` | no more |
| `Can we remove our address from the quotation header?` | remove |
| `Could you remove my name from the invoice template?` | remove |
| `Please do not email me the PDF, send it on WhatsApp instead.` | do not contact |

These are Jura's own customers' words, which is what makes it serious. "In doubt it suppresses" was decided for a short message, where the doubt is real. Across a long message it needs the ask itself to be plain.

Fix: make each pattern name the person or Jura's own mail.
- Line 61: drop the bare form, `the` and the free `\w+` adjective, keeping `your`, `these`, `those`, `this`, `all`, `any` directly before the mail word (`your` may keep an adjective: `your marketing emails`).
- Line 63: `name`, `address` and `details` count only with `from your` or a list, database or records.
- Line 66: `from the` counts only before a mailing, email or contact list.
- Line 68: only `opt me out`, `opt us out`, or a first-person subject (`I`, `we`, `please`).
- Line 69: `me` or `us` must end the clause or be followed by `again` or `anymore`.
- Line 70: only as a short sentence of its own.
- Add the table above as test cases.

**R-2. Explicit asks are still lost.** `outreach/replies.py:322`, `:59`, `:60`, `:69`. Breaks the conductor's P-9 decision and E2. Reproduced with `opt_out_reason`.

| Message | Result | Why |
|---|---|---|
| `Hi Levi,\nThank you.\nPlease remove me from your list.` | nothing | cut at the sign-off |
| `Hi Levi,\nThanks,\nbut please stop emailing me.` | nothing | cut at the sign-off |
| `Hi,\n\nThanks!\n\nStop.` | nothing | cut at the sign-off |
| `Please don’t email me again.` (long) | nothing | typographic apostrophe, the default on a phone |
| `Don’t contact us.` (long) | nothing | typographic apostrophe |
| `Please stop emailing this address.` (long) | nothing | pattern too narrow |
| `Stop contacting my team.` (long) | nothing | pattern too narrow |
| `Please stop emailing our office.` (long) | nothing | pattern too narrow |
| `Stop sending these.` (long) | nothing | pattern too narrow |
| `Do not email again.` (long) | nothing | pattern too narrow |
| `Please do not contact this address again.` (long) | nothing | pattern too narrow |
| `Please remove from mailing list.` (long) | nothing | pattern too narrow |

The first three are the worst, because they are short and passed before this round's change: `_without_signature` stops at the *first* line that looks like a sign-off, and "Thank you." opens as many messages as it closes. Footers must still not count: `Sure, tell me more.\n\nRegards\nJohn\nTo unsubscribe from our newsletter click here` correctly suppresses nothing today.

Fix:
- Cut at the last sign-off line, not the first.
- Normalise `’` to `'` before matching.
- Let `stop` plus a contact verb take `this`, `that`, `my` or `our` plus address, email, inbox, team, staff, office, company or people.
- Let `stop sending` take `these`, `those` or `this` at a clause's end.
- Let `do not` plus a contact verb take `again` or `this address`.
- Let `remove from` take a list with no `your` or `the`.
- Add the table above as test cases.

Not required here: `Please cease contact`, `We do not wish to receive further emails`, `I don't want any more emails from you`, `Please delete my email address`. No list holds every phrasing, and the amended rule gives longer messages to triage (ticket 02's "the opt-out class of F1"). They stay a known gap for stale mail and a paused inbox.

**R-3. The outreach half of F2 is dropped, not moved.** `.scratch/inbox-watch/issues/03-approve-an-email-reply.md:10` says "Outreach sends stay as they are", and `inbox/store.py:222-230` records why. The PRD line still reads "mail whose `In-Reply-To` or `References` names a message Jura sent, is that lead's reply" (PRD line 87), and functional F2 wants the same. A ticket can't narrow an amendment on its own. The cost is real: someone off the lead's domain, say a personal Gmail or an agency, who answers outreach mail is reported as a stranger, so follow-ups aren't cancelled. They are then chased after answering, and any opt-out in their words does nothing. R1 does show Ting Yu the message, but stopping the follow-up is then a manual step he has to know to take. See the question in the report: this clears with a line in the PRD or a line in ticket 03, and no code here.

### Should fix

**R-4. A stated pass for someone else's domain reads as no verdict.** `outreach/replies.py:436-445`. Reproduced: `From: nobody-real@<lead domain>`, `Subject: stop`, `spf=pass smtp.mailfrom=evil.test; dkim=pass header.d=evil.test; dmarc=none` left the lead `unsubscribed`. That isn't a missing verdict: the server said who signed it and it isn't them, and this is the shape of a forgery from the forger's own server when the lead publishes no DMARC. Fix: count as failed when every pass is for an unaligned domain and no aligned pass exists. A real colleague behind an unaligned third-party sender is only reported, not lost.

**R-5. With no server header, the sender's own counts as the server's.** `outreach/replies.py:409-416`. `verdicts`' docstring says a sender "can add one of their own, but only below it", which is only true if the server writes one. Reproduced: a forged `From: no_reply@jurasolutions.sg` with its own `Authentication-Results`, and only an `ARC-Authentication-Results` from the server, returns True. The effect is limited, a "Website enquiry" frame with no warning, and he still approves any send. But ticket 06's UAT line says an enquiry "reads as unsigned without one", which describes only the honest case. Fix: pin the expected authserv-id in `config/inbox.yaml` once UAT shows it, and treat any other as no verdict. Change ticket 06's line to say so.

### Nits

- Ticket 01's own Accept line still lists F2, F4, R2 and S16 whole. Mark what moved, so QA doesn't test for it here.
- A message whose body is refused every time is held silently for 48 hours (`inbox/mail.py:284`), with no count and no report. It is rare, and it ends in a report.

### Round 2 verdict: changes-requested

The verdict rests on R-1, R-2 and R-3. The first two are confined to the opt-out patterns and `_without_signature`, and R-3 needs a decision and one line of text.
