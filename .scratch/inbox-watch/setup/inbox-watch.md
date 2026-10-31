# Inbox watch: setup guide

This is yours to follow after the merge, in order, once. It takes an afternoon, mostly waiting. The tests prove
the rules with doubles. These steps prove the real mailbox, Meta's real pages, Resend, Discord and launchd,
which no build can touch. `reviews/uat.md` Part B is the fuller script that follows, with the test messages.

The order matters. The browser jobs stay paused until each check has passed, because each read is more
automated activity on the real accounts.

## 1. Get the code and fix the clock

1. In the checkout that runs the live jobs:

   ```bash
   git pull
   uv sync
   ```

2. **Restart the Mac, if it hasn't restarted since 1 October.** Launchd calendar jobs fire about 9 hours early
   until it does (approvals-first PRD §1). Every window here is checked in code as well, so an early run only
   skips, but until you restart, the slots on your health strip read as missed.

## 2. Keep the browser jobs off, then install the schedule

3. Do these two in this order. The first line is what stops the second from starting hourly reading:

   ```bash
   uv run jura-growth pause inbox-browser
   uv run jura-growth schedule install
   ```

   `inbox-check` and `inbox-send` start now, and `inbox-watch` and `inbox-reply` skip until you resume them.

## 3. Make Discord tell you

4. Set `#mission-control` to notify on **all messages**: right-click it, Notification settings, All Messages.
   Reactions land there, and neither the card nor the alert channel carries them. Set `#approvals` and `#alerts`
   the same way if they aren't already.
5. Send `/growth status`. No setup gap should name the IMAP settings.

## 4. Check the mail

6. Send yourself a test from a personal address to Levi's mailbox. Within 15 minutes it is reported in
   `#mission-control`, and the message in the mailbox is still unread.
7. **Does `info@` need the second mailbox?** Send a test through the form on jurasolutions.sg. Website enquiries
   go to `info@jurasolutions.sg`. If that enquiry shows up in Levi's mailbox, `info@` forwards there and you
   need nothing more. If it doesn't, add these four to `.env`, and the next check reads that mailbox too:

   ```
   ENQUIRY_IMAP_HOST=
   ENQUIRY_IMAP_PORT=
   ENQUIRY_IMAP_USER=
   ENQUIRY_IMAP_PASSWORD=
   ```

8. **Set `auth_servers`.** Open that enquiry's raw headers ("Show original" in Gmail, "View message source" in
   Zoho) and find the line starting `Authentication-Results:`. The first word after the colon is your mail
   server's id, such as `mx.zoho.com`. Put exactly that in `config/inbox.yaml`:

   ```yaml
   auth_servers: ["mx.zoho.com"]
   ```

   Until you do, every enquiry reads as unsigned: it is reported and can still be answered, with a note, and a
   sender's own header counts for nothing, because anyone can write that header. A wrong guess here would be
   trusted, so read it from the real message.
9. **Junk.** A cold reply can land in Junk, and the watch lists those in the one-pager with the sender's domain
   and subject. A message you move from Junk to the inbox stays noise: the engine has already filed it by its
   id, so answer it by hand.
10. Your own opens count in the first app usage report, the first check after 08:00.

## 5. The watch: first-run checks

A build can't try real Meta pages. Do these once, with `#mission-control` open.

### Before you start

11. Keep Chrome open on the Jura publishing profile, signed in to the Facebook account that runs the Page and
    to Instagram as `@jura_solutions`, with the Claude extension on.
12. Check `pages` in `config/inbox.yaml`. It should say `https://www.facebook.com/jurasolutionssg` and
    `https://www.instagram.com/jura_solutions/`, and the `name`s exactly as the platforms show them, because a
    reply run stops if the session isn't acting under that name. If `page_url` is set in `config/social.yaml`,
    the two must match.

### One watched run

13. Run it once by hand, inside its hours (09:05 to 21:05), then pause again until you've checked it:

    ```bash
    uv run jura-growth resume inbox-browser
    uv run jura-growth run inbox-watch --ignore-schedule
    uv run jura-growth pause inbox-browser
    ```

14. The first read of a surface is a silent baseline, so expect few messages or none: only comments and
    messages under 48 hours old that the Page hasn't answered. Old ones are stored and not told.

### What to check

15. **Every surface was read.** `uv run jura-growth inbox status` lists each surface's last good read. The nine
    are Instagram Primary, General, Requests and activity; the Page's inbox, Spam, notifications and mentions;
    and Jura's recent posts. A surface reading "never" didn't work. Read that run's transcript in
    `data/growth/transcripts/` to see what the page showed.
    - The likeliest to need a change are the start addresses in `SURFACES`, in
      `jura_growth/agents/inbox/watch.py`: `/direct/general/`, `/latest/inbox/spam` and
      `/latest/notifications`. None could be tried in the build.
    - Check which identity `www.facebook.com/notifications` shows. The browser is signed in as Levi's
      profile, and the watch can't click to switch to the Page. If it shows Levi's notifications, that
      surface will read as failed, because it isn't the Page's. Then find an address that shows the Page's
      (Business Suite has one) and change its start in `SURFACES`.
    - Instagram's General tab may have no address of its own. If so, it can't be read without a click.
      Decide then: drop that surface, or allow `computer` (the next step).
16. **Does the watch see enough without clicking?** Open two threads and two posts yourself, and compare them
    with what the run recorded. Check that:
    - it found threads from the list with no click, because the page gives them an address;
    - it read a whole message, not only the preview;
    - comments on a post load on first paint, at least the first few.

    The watch reports what it couldn't load as "3 comments the watch couldn't read: check by hand". If that
    line shows on most posts, reading is too thin. The fix is one line: take `computer` out of `WATCH_DENIED` in
    `jura_growth/agents/inbox_browser/scope.py`. The audit still fails everything but looks, so scrolling works
    and a click still fails the run. Record that you did it in ADR 0006.
17. **Permalinks hold.** On a comment the run recorded, check that `Open:` in its report goes to that comment.
    On Facebook it should carry `comment_id`; on Instagram it should look like `/p/<code>/c/<id>/`. Then run the
    watch again an hour later. Nothing should report twice. If a message does, the page gave a different address
    or different words, and it's worth a look before leaving this on.
18. **Thread addresses can take a reply.** A DM's target must be `/direct/t/<id>/`, `/messages/t/<id>/`, or
    Business Suite's `/latest/inbox/…` with a numeric `selected_item_id`. A DM the watch kept under any other
    address reads "answer by hand" and gets no card. If most do, the shapes in `hosts.dm_target_problem` need
    another look.
19. **It said "Unverified" rarely.** A real message marked unverified means the page's text and the model's copy
    differed. A run or two is fine to look at. If most are, the prompt needs another look.
20. **It acted as nobody.** Open the Page's activity log and Instagram's login activity. There should be no
    likes, follows, hidden comments or sent messages from the run. Expect "Seen" on threads it opened, which is a
    cost we accepted: opening an unread thread shows the sender it was read and clears the unread mark.
21. **A stop works.** You don't have to force one. The first time one fires (a login wall is the usual one),
    check that `#alerts` got one message, that `inbox-browser` and `publish` both show as paused, and that
    nothing resumes until you run both resume commands in the alert.

## 6. The first replies

Have a friend or a second account that doesn't follow Jura leave a comment and send a DM, starting `UAT`. Not
the Levi Ting profile, because it runs the Page. Resume for this:

```bash
uv run jura-growth resume inbox-browser
```

22. **One comment.** Wait for the report and the card, read it, and press Approve. Within 20 minutes, during
    09:10 to 20:50, a line reads "sent to …" in `#mission-control`, with a link. Open it and check:
    - the reply sits under that comment, not on the post;
    - it is by the Page, word for word. A platform may put `@their-handle` in front: that's allowed;
    - nothing else on the post was liked, hidden or changed, in the Page's activity log.
23. **One DM.** The same. The reply is in that thread, as one message. Two messages or a broken-off sentence
    would be a real fault, and the audit should already have failed the run: tell Claude.
24. **One request.** A DM from someone who doesn't follow Jura lands in Requests, and its card says approving
    also accepts it. Check that only that thread was accepted.
25. **Answer one yourself.** On a comment card, reply by hand as the Page from your phone, then press Approve.
    The run types nothing, and the item closes as answered by hand.
26. Only now is it on. Leave `inbox-browser` resumed.

## 7. Keep in mind

- **A reply can wait.** A DM after about 20:20 can't be answered on social the same evening, and one after 21:05
  isn't seen until 09:05. Email keeps the same-evening promise until 22:00.
- **`unknown` means look.** If `#alerts` says a reply "may have posted, check here before answering by hand",
  open the link. A run left a claim open, so it may or may not have gone. It is never sent again, and there's no
  command to settle it: `inbox-browser` is paused until you resume it, and `/growth inbox done I-nnnn` clears the
  line once you've looked.
- **The audit can't tell what a click did.** A click on Like or Hide would pass it. Skim the Page's activity log
  now and then, more often in the first week.
- **If either account gets a warning,** run `uv run jura-growth pause inbox-browser` and
  `uv run jura-growth pause publish`, and reopen the Graph API question in ADR 0006. Hourly reading is more
  automated activity on the same accounts (`prd-jura-inbox-watch` §4), and nothing here makes that compliant.
- **If a surface goes blind later.** Meta changes its layouts, and that shows up as a failed surface. After 3 of
  the watch's hours with no good read, the one-pager's Needs you names it, with its last good read. Until it's
  fixed, check that surface by hand, because a person there is going unseen. `uv run jura-growth inbox status`
  shows the same.
