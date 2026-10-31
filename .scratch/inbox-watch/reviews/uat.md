# UAT: inbox watch

Run this on the real system after merge, mostly from your phone in Discord. Allow an afternoon, plus a look the next morning. Start before 16:00 on a day the Mac stays on, so the social replies fit before 20:50.

Expected results marked (F1) or (S3) depend on that finding in `reviews/functional.md`. If the conductor ruled a fix out, skip that line.

**This is live.** Replies really go out, so answer only the test person's cards. A real person may appear during the test: treat their card normally.

## What you need

- **Test person:** a friend, or a second Facebook and Instagram account that doesn't follow Jura. Not the Levi Ting profile, because it runs the Page.
- **Test email A:** a personal address that isn't Jura's and has never been emailed by outreach.
- **Test email B:** a throwaway address. It gets suppressed for good, unless the `lift` command from F1 is built.
- Start every test message with `UAT`, so you can find and delete them.

## A. Before you start

1. In the checkout: `git pull`, `uv sync`, `uv run jura-growth schedule install`. Restart the Mac if it hasn't restarted since 1 October.
2. Open Chrome on the Jura publishing profile, signed in to Facebook and Instagram. Leave it open.
3. In Discord, set `#mission-control`, `#approvals` and `#alerts` to notify on all messages.
4. Send `/growth status`. Pass: `inbox-check`, `inbox-send`, `inbox-watch` and `inbox-reply` are installed, and no setup gap names the IMAP settings.
5. Wait for the first `inbox-check` and `inbox-watch`. Pass (F12): anything older than 48 hours is reported without a draft, more than 5 fold into one message, and no post reports its old counts as new.

## What every check looks for

**The report** in `#mission-control`: where, who, their words exactly, any phone or address masked, and what happens next.

**The card** in `#approvals`: one message (S5) with what they said, who and where, the draft, Approve and Skip, and what each answer does (S6).

**After Approve:** a "sent" line in `#mission-control` (F15), and the next watch raises nothing new from Jura's own reply (F4, S8).

**Wait times:** email is seen within 15 minutes. Social is read at the next `:05` from 09:05 to 21:05, and triaged within 15 minutes after that. An approved email goes within 10 minutes, and an approved social reply on the next run, at most 20 minutes later.

## B. First run for each channel

| Row | Channel | Do this as the test person | Pass when |
|---|---|---|---|
| U1 | Email | From email A to Levi's mailbox: `UAT how long does a first automation take? My number is 9123 4567.` | Report and card, with the number masked. Approve. It arrives threaded, `Re:` subject, from Levi. The BCC is in his mailbox and raises no report. The message in his mailbox is still unread |
| U2 | Facebook comment | Comment on the latest Page post: `UAT do you work with clinics?` | Report with their display name and a link, and a card. Approve. A reply sits under that comment, as the Jura Page, word for word |
| U3 | Facebook Messenger | Message the Page: `UAT what does discovery involve?` | Report and card. Approve. The reply is in that thread, as the Page. Expect "Seen" within the hour (N1) |
| U4 | Instagram comment | Comment on the latest post: `UAT is this for small teams?` | Report and card. Draft has no URL (N3). Approve. The reply is under that comment, as @jura_solutions |
| U5 | Instagram DM | From an account that doesn't follow Jura, so it lands in Requests: `UAT do you do invoices?` | Report and card (F5). Approve. The request is accepted, the reply is in that thread, and nothing else was clicked |
| U6 | App usage | Open one toolbox app at jurasolutions.sg/apps and finish it once. Check the next morning | The first check after 08:00 posts one line per app with opens and completions. No names or addresses. Your own opens are included (S14) |

## C. Would a good colleague have done this?

Send these on any channel unless stated, and read the draft as the person getting it. Pass needs a plain, warm reply with the answer first, no invented fact, no price in public and no selling.

| Row | Do this | Pass when |
|---|---|---|
| U7 | `UAT thanks, that helps` | Report saying no reply is needed. No card |
| U8 | Website form, with a phone number, using email A | Report shows the name and `Came from:` when sent from an app page. Card says a number is in the mailbox. The reply reaches email A with a human subject (S3) |
| U9 | Public comment: `UAT how much would this cost for my clinic?` | Draft answers the general part and invites a DM or email. No figure, and no request for a phone number in public |
| U10 | Comment: `UAT nice post` | Report only. No draft |
| U11 | Email: `UAT this is the third time, I want a refund` | `high`, first in Replies waiting, and in `#alerts` (S7). Draft is a short holding reply. After sending, it stays listed as promised until you send `/growth inbox done` (F10) |
| U12 | Email B: `UAT please remove me` | Report, address suppressed, no card, no reply ever goes out |
| U13 | Email B again: `UAT sorry, one question, what do you charge?` | Report says they opted out earlier and to answer by hand. No card (F14) |
| U14 | Email A: `UAT how do we stop retyping invoices?` | Not suppressed. Normal card (F1) |
| U15 | Watch for this in the first week, on real outreach: a colleague answers from another address at the same company | Follow-ups stop, and the lead shows replied (F2) |

## D. Double and stale replies

| Row | Do this | Pass when |
|---|---|---|
| U16 | Email A asks something. When the card appears, send a second email, then press Approve on the old card | Old card reads "they wrote again". Approve answers `superseded`. The new card's draft covers both |
| U17 | Email: `UAT how much is it?`, then `UAT thanks` once its card is up | The new card still answers the question (F8) |
| U18 | Instagram DM card: Approve just after a `:10`, `:30` or `:50` run, then have the test person send another DM | Next reply run types nothing. Old card is superseded, and a new card appears (F9) |
| U19 | Facebook comment card: answer it yourself as the Page on your phone, then Approve | The run types nothing, and the item closes as answered by hand (F9) |
| U20 | Press Approve twice on any card | Second press answers `already-decided`. One reply goes out |
| U21 | Run a test comment through its reply, then wait for two more watches | No second report, card or reply |

## E. Changing a draft from your phone

| Row | Do this | Pass when |
|---|---|---|
| U22 | `/growth inbox redraft A-nnnn shorter, and ask what they use today` | Within about 15 minutes the old card closes, and a new draft follows the guidance |
| U23 | `/growth inbox reword A-nnnn Thanks for asking. Levi will write back today.` | Old card closes, and the new card shows those exact words |
| U24 | Reword with something that fails the brand check, such as `Thanks!` | The answer gives the reason, and the old card stays open (S1) |
| U25 | Press Skip on a card | Nothing goes out, and the card reads skipped |

## F. Staying in charge

| Row | Do this | Pass when |
|---|---|---|
| U26 | `/growth one-pager` | **Replies waiting** sits between Needs you and Approvals waiting, with A-id, source, sender, wait and excerpt. It shows the last good read per surface (F13) and a reactions count |
| U27 | `/growth inbox list` | Shows the same waiting items, with the words readable, not `[name removed]` (F11) |
| U28 | `/growth pause inbox-browser`, then comment as the test person | No watch or social reply runs. Email still works. `/growth resume inbox-browser`, and the comment is reported |
| U29 | `/growth pause inbox`, then email from email A | No report or send while paused. `/growth resume inbox`, and the email is reported. On real outreach, the 16:45 check still records a contact's reply while paused (S10) |
| U30 | Close Chrome for two watch slots, then reopen it | Failures show on the health strip within the hour. Then `/growth resume inbox-browser` if it auto-paused |
| U31 | Next morning's brief and `daily-summary.json` | Counts only: no names, addresses or text |
| U32 | Leave one test card for 3 days | It lapses, with one line in `#mission-control` (S7), and is listed for 7 days. The person gets nothing |

## If something fails

Stop the part that's wrong: `/growth pause inbox` for mail and email replies, `/growth pause inbox-browser` for Facebook and Instagram. Note the row number and what you saw, and pass it to Claude. Any platform warning, checkpoint or login wall pauses publishing too: read it on the platform before you resume.

## When it passes

Delete the `UAT` comments by hand, since the engine never deletes anything. Then move the PRD to `prd/done/` with the ship date.
