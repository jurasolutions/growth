# Functional review: inbox watch

Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md`, cited as criterion and line (W3 L34). Reviewed 2026-10-31 by reading the PRD and code. Nothing was run.

Verdict: the shape is right, and the approval path is sound. As written, real people would still be missed, and some would get a stale or doubled reply. Every finding carries a decision, because Ting Yu asked not to be asked. PRD §7 records that he has not read the PRD, so the conductor should copy each accepted fix into it.

## Blocking

**F1. A real question can suppress the person for good (W6 L37, E2 L64).** `replies.py:35` matches a bare `remove` or `stop` anywhere in their own words. "How do we stop retyping invoices?" suppresses the address and marks the lead unsubscribed, then the claim refuses the reply. `jura-growth suppression` has only `add` and `check`, so it can't be undone.
*Fix:* suppress when the subject has the word, or their own words have it and run to 12 words or fewer, or triage classes the message `opt-out` (a model can only make this safer). Any other match suppresses nothing: follow-ups are cancelled anyway, and the message gets normal triage. Use one rule in `inbox-check` and at 16:45. Add `/growth suppression lift <A-id or item>`, in the allowlist, for a mistaken suppression.

**F2. A reply from a colleague doesn't count as a reply (W6 L37, R3 L45).** `replies.py:155` matches the exact sender. Outreach to `info@acme.sg` answered by `jane@acme.sg` cancels no follow-up, so Acme gets chased after answering. Jane is also a non-contact, so the model may class her `noise`.
*Fix:* treat a sender as the emailed contact's lead when their domain equals the lead's domain (excluding free-mail domains), or when `In-Reply-To` or `References` names a message Jura sent. W6 and R3 then apply. An opt-out suppresses that sender and cancels the lead's queue.

**F3. The model can hide a first-time enquirer (R2 L44, R3 L45).** A person writing directly from their own address is a non-contact, so `noise` reduces them to `gmail.com` on tomorrow's one-pager. Their text can also ask for that class. R2's "no-reply senders" also catches the enquiry sender of W8 (L39).
*Fix:* `noise` needs evidence in the headers: `List-Id`, `List-Unsubscribe`, `Precedence: bulk`, `Auto-Submitted`, a no-reply sender or a known platform domain. W8 is tested first. Without evidence the mail is reported under R1 whatever the model says.

**F4. Jura's own mail comes back as a reaction (D3 L53).** The BCC lands in Levi's mailbox, in the same thread, so each sent reply reads as a new message and may count as "they wrote again" (D5). His own test mail does the same.
*Fix:* drop mail from any Jura address at intake, except the W8 enquiry: no item, no R1, no noise count. Keep each outgoing `Message-ID` so the copy is recognised even if the header is rewritten.

**F5. Cold people land in folders the spec doesn't name (W2 L33, D4 L54, §3 L87).** A non-follower's Instagram DM goes to Requests, and replying needs an Accept click, which §3 forbids. These are exactly Jura's new prospects. `hosts.py:41` also lacks `messenger.com`, so a run redirected there fails its audit and pauses the agent.
*Fix:* name the surfaces in W2 and the prompt: Instagram Primary, General, Requests and activity; the Page's inbox at `business.facebook.com` including Spam, plus its notifications, mentions and reviews. Approving a reply to a Request also authorises Accept, for that thread only, and the audit allows that one click. Runs stay on the existing hosts.

**F6. The 8-post limit covers about four days, not 14 (W3 L34).** Facebook and Instagram each get a post a day (`CONTEXT.md` L195), plus group posts, so a comment on a six-day-old post is never read.
*Fix:* notifications from F5 catch comments on a post of any age. Then read the 8 least recently read posts from the last 30 days, rather than the 8 newest, so every post is reached over the day.

**F7. A repeated message disappears (W5 L36).** The social key is platform, kind, thread, author and text. "Hello?" sent again on Thursday hashes the same as Monday's, so the chaser is dropped. And a model reads the text, so a "See more" cut or a changed spacing gives a new hash and a duplicate card.
*Fix:* use the comment id in the permalink where there is one. Otherwise hash the first 200 normalised characters plus the occurrence number of that text in the thread as read. For an empty text (sticker, voice note) hash the attachment type and the occurrence number.

**F8. "Thanks" can cancel the answer to a question (D5 L55, E1 L63, R1 L43).** "How much is it?" then "thanks" supersedes the draft, and the new message merits none, so the question goes unanswered. "Hi", "I have a question", "how much?" also raises three reports and three drafts.
*Fix:* triage a conversation, not a message. Draft when any unanswered message in it merits one. A conversation has at most one open card. Each triage posts one R1 per conversation, listing the new messages.

**F9. A reply can go out over a newer message, or on top of a human answer (D3 L53, D4 L54, D5 L55).** The watch reads hourly, so a DM from 10 minutes ago is unknown to `content()` when the 10:30 reply run posts. Likewise the Page answered from his phone at 10:20.
*Fix:* just before the claim, `inbox-reply` opens the target and reports its newest message, and `inbox-send` runs the mail intake. A newer message from them supersedes. An answer from the Page closes the item as `answered by hand`. A target that has gone closes it (S4). Only a clean read is claimed. The audit's rule that no typing happens before the claim still holds.

**F10. Nobody owns a promised reply (D9 L59, E4 L66).** The holding reply and "Levi will come back personally" both end at `sent`, and the item leaves R4. The person is then waiting on a promise the system has closed.
*Fix:* a `promised` flag, set for a `high` draft and any draft with that promise. After sending, the item becomes `needs-you` and stays first in R4, showing its age, until `/growth inbox done`. It doesn't age out of the 7-day list.

**F11. The Discord defaults defeat R1 and D1 (§5 L117, S7 L78, §4 L95).** Each of these needs a named test:
- `own_copy` still masks learned names, so "Hi Jane," and even "Hope this helps" (with `hope.lee@` learned; `privacy.py:315`) would change. L117 then refuses the draft. Two refusals and every greeting becomes `needs-you`. Check a draft for secrets, phones and addresses only, not names.
- `cards.py:190` passes no copy class, and `discord.py:250` masks again on edit, so a card's quoted words can change when he presses Approve.
- `replies.py:169,186` registers the subject and reply lines with `never_show`. In the same process R1 and the card would read `[removed]`.
- `discord.post` dedupes by default (`discord.py:153,198`), so an identical second R1 the same day is dropped silently. R1 uses `dedupe=False`.
- `remote.py` masks answers without the class, and `inbox list` excerpts must use it.

**F12. The first run floods him with stale drafts (W7 L38, W3 L34).** Seven days of mail and every old comment and DM become R1s and cards, including threads he has already answered, because reading Sent is out of scope. On first sight every post also "rose" from nothing. A long absence does the same.
*Fix:* anything older than 48 hours at intake is reported without a draft ("older than 48 hours: answer by hand if it still matters"), and more than 5 of those fold into one message. The first social read is a baseline: it records counts silently, and records comments and DMs as seen unless they're under 48 hours old and unanswered by the Page.

**F13. A blind watch looks like a quiet day (W2 L33, R2 L44).** A run that fails to read Instagram DMs and finds nothing is the same as no new messages. Opening a thread also clears the unread badge, which is his only other signal.
*Fix:* each run records per surface `read ok, N items` with `inbox observe`, and a surface with no such record fails that surface. R4 shows the last good read per surface. Over 3 hours inside the window goes to Needs you. Record each message as it's read, so a crash can't lose an opened thread.

**F14. A person who opted out and writes again goes nowhere (E2 L64, §5 L115, R4 L46).** `content()` returns None, read as `superseded`, which R4 doesn't list. `suppression.py:36` also refuses a colleague when the whole domain is suppressed. A new enquiry from them is lost.
*Fix:* no draft and no card. The item is `needs-you`, and R1 says: "They opted out earlier (reason) and wrote again. The engine won't send. Answer by hand if it's right." Suppression still never lifts itself.

**F15. He is never told whether a reply went out (D3 L53, D4 L54, R1 L43).** The card ends at "claimed" (`cards.py:81`), which is internal and doesn't mean sent. An `unknown` or `failed` result waits for tomorrow's R4, and meanwhile he may answer by hand and double it.
*Fix:* one line in `#mission-control` on `sent` ("A-0412 sent to Priya, 14:22, link"). On `failed` or `unknown`, a line in `#alerts` with the link: "may have posted, check here before answering by hand".

## Should fix

- **S1. Reword and redraft failures (D6 L56).** The old card closes only after the new one exists. A brand refusal answers with the reasons in Discord and leaves the card open. D8's two-strikes rule doesn't apply to his words. Both refuse a decided or lapsed card, and say why. Dispatch joins words on whitespace (`dispatch-contract.md` L39), so an email reword loses its paragraphs: `//` marks a paragraph break.
- **S2. No draft means no way back (R1 L43, `CONTEXT.md` L118).** If the model says no reply is needed and he disagrees, he has no id to type. Each R1 gets an item id: `/growth inbox draft I-nnnn [guidance]`, and `/growth inbox done I-nnnn`. Amend the glossary's "only id he ever types".
- **S3. An enquiry reply reads as internal (D3 L53, `submit.js:126`).** "Re: Enquiry from Jane Tan (Acme)" is a subject she never saw. An enquiry reply uses the subject "Your enquiry to Jura Solutions", with no `In-Reply-To`. If the enquiry holds a phone number, its card says "They left a number. It's in the mailbox", because the card masks it.
- **S4. A missing page isn't a stop signal (S4 L75, `CONTEXT.md` L213).** A deleted comment or post reads like a "removal notice" and would pause publishing too. "Content isn't available" and a closed reply box are outcomes: the item closes with a note, or becomes `needs-you`. A group admin removing Jura's post is reported as a reaction. A real platform warning still stops.
- **S5. One card, one message (D1 L51, `discord.py:166,215`).** Buttons sit on the first piece only, so a long email splits the draft below them. Cap their text so the card fits in 2,000 characters, then "full text: mailbox" or the thread link. The draft is never cut.
- **S6. Next-step lines (D1 L51).** Email Approve: "sends as Levi within 10 minutes, or at 08:00 if it's after 22:00". Social: "posts on the next reply run, 09:10 to 20:50". Skip: "nothing goes out. Use this too if you've answered by hand." Change: both typed commands. The card also says when a `high` item must be answered.
- **S7. Lapses and urgent items are silent (D7 L57, D9 L59, `cards.py:17`).** Card edits don't notify, and R4 comes at 08:00. A lapse posts one R1 line. A `high` item posts to `#alerts` at once, and again at 24 hours if undecided. The setup guide sets `#mission-control` to all messages: `#approvals` and `#alerts` are set that way, and R1 lands in neither.
- **S8. Counts (W3 L34).** Report reactions and shares only: comments get their own R1, and Jura's own replies would inflate the count. Exclude the Page as an author everywhere. Use the count as the one check a model can't talk around: if comments rose by more than were recorded, R1 says "2 new comments counted, 1 recorded, check this post" with its link.
- **S9. One message, not two (W6 L37, R1 L43).** `replies.py:214` also posts to `#outreach-replies`. Once `inbox` is on, that becomes the R1 only, and the 16:45 path posts only what `inbox-check` missed.
- **S10. Pausing must not stop follow-up cancelling (S6 L77, W6 L37).** A failing triage auto-pauses `inbox`. The 16:45 `scout-sync` check keeps running whatever `inbox`'s state, so a paused inbox can't chase someone who said stop. Triage failure alone leaves the model-free intake running.
- **S11. Who a reply goes to (D3 L53).** It goes to `Reply-To` if set, otherwise `From`. Copied people aren't included, because each would need its own suppression check: the card says "They copied 2 others: reply by hand if they need it".
- **S12. Other reactions to email (L11 his words, R1 L43, `suppression.py:4`).** An unsubscribe click and a bounce count in R4's reactions. A spam complaint gets a `high` R1, without a draft.
- **S13. Language (E4 L66).** A message not in English gets an English draft, and the card says "They wrote in Chinese. This draft is English", so he can answer by hand.
- **S14. App usage after an absence (W4 L35).** Report each unreported day, at most 7, on one message, not only yesterday. The first report may include his own test opens; the guide says so.
- **S15. Flood guard (R1 L43).** Over 10 R1s in a run: the first 10, then one line with the count and "see `/growth inbox list`". `spam` always folds first.
- **S16. Spam folder (W1 L32, `replies.py:121`).** Cold replies land in Junk. Read Junk read-only as well: it never gets a draft, only a line in R2's list with the sender's domain and subject.

## Notes

- **N1. "Seen" starts a clock (§4 L97).** Every new DM shows "Seen" within the hour, then waits on him. That is accepted risk. Put it in the guide, and have R1 say "they can see it was read".
- **N2. The evening promise is narrower than it reads (§6 L131).** A DM after about 20:20 can't be answered on social the same evening, and one after 21:05 isn't seen until 09:05. Email keeps the claim. The guide should say so.
- **N3. Instagram links aren't clickable (`config/social.yaml:136`).** `inbox-social` on Instagram comments should invite a DM rather than include a URL. Read-back must allow the `@handle` prefill.
- **N4. Reading Sent stays out (§3 L86).** A header-only check of Sent for `In-Reply-To` before claiming would close the last double-reply gap, read-only. Reopen it if a hand reply and an approved one ever collide.
- **N5. Explicitly out:** Carousell (profile only, no listings), Page reviews beyond reading them, and acting on PDPA requests (a `high` holding reply, then by hand; he clears the row with `inbox done`).
- **N6. Acceptance order (L4, L137).** Merging is called acceptance, yet the UAT can only run after merge. Treat merge as "may run", and move the PRD to `prd/done/` only after `reviews/uat.md` passes.
- **N7. Retention (§4 L96).** Define "closes" for `reported`, `noise` and `needs-you`, or their text stays forever.

## Criteria rewritten so a tester can fail them

Criteria not listed are testable as written, with the findings above applied.

| Id | Given / when / then |
|---|---|
| W3 | Given 20 posts in 30 days, when three watch runs complete, then the 24 reads cover the 20 posts at least once, and no run opens more than 8. Given a post at 2 reactions, read at 5: "3 new reactions, now 5". Read at 5 again: nothing. |
| W5 | Given one comment read twice with different "See more" cuts: one item. Given "Hello?" from Priya in one thread on Monday and Thursday: two items. |
| W6 | Given `info@acme.sg` was emailed and `jane@acme.sg` writes at 10:02: by 10:15 follow-ups are cancelled and the lead is `replied`, and at 16:45 no second record or post appears. With `inbox` paused: the 16:45 check does all of it. |
| Opt-out | "Please remove me": suppressed, R1, no card. "How do we stop retyping invoices?": not suppressed, card raised. A 40-word opt-out the model classes `opt-out`: suppressed, no card. |
| R1 | Given 3 DMs from one person in a run: one R1 quoting all three, the same text byte for byte as stored, with phones and addresses masked. Given two identical messages the same day: two R1s. |
| R2, R3 | A `gmail.com` sender with no bulk headers, classed `noise`: an R1 still posts. A `List-Id` newsletter: no R1, and one line under the count. A social comment classed `noise`: an R1 still posts. |
| D1 | A 4,000-character email with a 180-word draft: one Discord message, with the full draft, the buttons, the four next-step lines and a pointer to the full text. |
| D3 | Approved 14:00: sent by 14:10, with `In-Reply-To`, `References`, `Re:` and the BCC. Approved 22:30: sent 08:00 to 08:10. Approved with a newer message in the mailbox: not sent, superseded. |
| D4, F9 | Approved at 10:25; a newer DM appears before the 10:30 run: nothing typed, superseded, new card. Page already answered: nothing typed, closed `answered by hand`. Target gone: nothing typed, closed with a note, and no pause. |
| D5, F8 | "How much?" with a waiting card, then "thanks": old card superseded, and a new card answers the price. |
| D7 | Waiting past 3 days: card reads lapsed, one R1 line, in R4 for 7 days. Approved and unclaimed past 2 days: lapsed and never sent. |
| E1 | Classes `like`, `emoji`, `thanks`, `out-of-office`, `not-interested` and `opt-out` can't carry a draft: `inbox` refuses one. Fixed cases that must draft: "Do you work with clinics?", "Your figure looks wrong". "A comment with something real in it" means: it asks, states a need, disagrees or shares their situation. |
| E2 | A message from a suppressed address: no draft, no card, `needs-you`, R1 names the reason. |
| E3 | In a public `inbox-social` draft, the gate refuses a price figure and any request to post a phone number or address. |
| E4, E5 | The gate refuses a non-Jura link, a figure not in `approved_claims.yaml`, and a first name absent from the sender's name or text. A fixed "nice post" case: no draft and no selling. |

**Judgement can't fail on a double.** PRD L28 tests everything with doubles, so E1, E3, E4 and E5 prove only that a rule exists. Enforce in code what the table shows. Keep the fixed cases in the prompt's test file as checks on the wording, and test the judgement for real in `uat.md` section C.

## Edges

| Edge | Status |
|---|---|
| Empty: sticker, photo or voice note, an image-only email | Not covered. R1 "sent a voice note, see thread", link, `needs-you`, no model guess. Key per F7 |
| Maximum: 4,000-character cut; a pile of cards | The card says "cut". S5, S15, and R4 shows 10 lines (`high` first) then "and N more" |
| Concurrent: Approve and new mail at the claim; two jobs in Chrome; double click | Covered: ADR 0003, S5, `already-decided` |
| Out of order: new message after approval | F9. Two mailboxes delivering one enquiry: covered by `Message-ID` (W5) |
| Permission: another Discord user, a headless run | Covered: D2, D6 |
| Permission: group bars Pages from commenting; reply box closed | S4 |
| Before the change: `outreach_replies` rows; old threads | F12. Rows already counted aren't reposted (W6) |
| Mac off or Chrome closed for days | F12, F13. Three failures auto-pause, shown on the health strip |
| Spoofed `no_reply@` with an attacker's `Reply-To` | Require Jura's DKIM pass, otherwise an ordinary non-contact. He still approves any send |
| Person deletes a comment while waiting | S4 |

## Language

`CONTEXT.md` needs these entries before tickets are cut, and none of them should reach it with implementation detail:

- **Reaction**: anything a person or platform did in response to Jura. _Avoid_ "reply" for inbound: **reply** already means an inbound answer in outreach and an outbound one here. Use **inbound message** and **inbox reply**.
- **Inbox item**: one recorded reaction. The glossary bars "item" alone (L199), and the PRD uses it throughout.
- **Conversation**: every message from one person in one thread, the unit of triage and of the one open card (F8).
- **Triage**, **Watch run**, **Replies waiting**, **Promised** (F10) and **Surface** (F13). "Needs you" stays the health strip; the state `needs-you` is separate and should be named **needs a hand reply**.
- Update **Agent**, **Approval kind**, **Gated action**, **Transcript** (L53), **Stop signal** (now any browser run, with S4's outcomes) and **Human origin** (nothing changes, but D6's commands join the allowlist). "Levi" is Ting Yu's sender name on email: add it, as the PRD uses both.
