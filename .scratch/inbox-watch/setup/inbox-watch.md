# Inbox watch: setup guide

This is the draft. The release copies the finished guide to `outputs/growth/setup/inbox-watch.md`. Ticket
06 finishes it, with the mail and reply steps. This section covers the watch run.

## The watch: first-run checks

A build can't try real Meta pages: nothing in a test touches them, and each run adds activity on the
real accounts. So the tests prove the rules, and these checks prove Meta. Do them once, in order, with
`#mission-control` open. Don't run the schedule until the last one passes.

Start with the browser jobs off:

```bash
jura-growth pause inbox-browser
```

### Before you start

1. Keep Chrome open on the Jura publishing profile, signed in to the Facebook account that runs the Page
   and to Instagram as `@jura_solutions`, with the Claude extension on.
2. Check `pages` in `config/inbox.yaml`. It should say `https://www.facebook.com/jurasolutionssg` and
   `https://www.instagram.com/jura_solutions/`. If `page_url` is set in `config/social.yaml`, the two must
   match.
3. Make sure `#mission-control` notifies you on all messages. Reactions land there, not in `#alerts`.

### One watched run

4. Resume it and run it once by hand, inside its hours (09:05 to 21:05):

   ```bash
   jura-growth resume inbox-browser
   jura-growth run inbox-watch --ignore-schedule
   ```

5. The first read of a surface is a silent baseline, so expect few messages or none: only comments and
   messages under 48 hours old that the Page hasn't answered. Old ones are stored and not told.

### What to check

6. **Every surface was read.** `jura-growth inbox status` lists each surface's last good read. The nine are
   Instagram Primary, General, Requests and activity; the Page's inbox, Spam, notifications and mentions;
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
     Decide then: drop that surface, or allow `computer` (the step below).
7. **It can see enough without clicking.** Open two threads and two posts yourself, and compare them with
   what the run recorded. Check that:
   - it found threads from the list with no click, because the page gives them an address;
   - it read a whole message, not only the preview;
   - comments on a post load on first paint, at least the first few.

   The watch reports what it couldn't load as "3 comments the watch couldn't read: check by hand". If that
   line shows on most posts, reading is too thin. The fix is one line: take `computer` out of `WATCH_DENIED`
   in `jura_growth/agents/inbox_browser/scope.py`. The audit still fails everything but looks, so scrolling
   works and a click still fails the run. Record that you did it in ADR 0006.
8. **Permalinks hold.** On a comment the run recorded, check that `Open:` in its report goes to that comment.
   On Facebook it should carry `comment_id`; on Instagram it should look like `/p/<code>/c/<id>/`. Then run
   the watch again an hour later. Nothing should report twice. If a message does, the page gave a different
   address or different words, and it's worth a look before leaving this on.
9. **It said "Unverified" rarely.** A real message marked unverified means the page's text and the model's copy
   differed. A run or two is fine to look at. If most are, the prompt needs another look.
10. **It acted as nobody.** Open the Page's activity log and Instagram's login activity. There should be no
    likes, follows, hidden comments or sent messages from the run. Expect "Seen" on threads it opened, which is
    a cost we accepted: opening an unread thread shows the sender it was read and clears the unread mark.
11. **A stop works.** You don't have to force one. The first time one fires (a login wall is the usual one),
    check that `#alerts` got one message, that `inbox-browser` and `publish` both show as paused, and that
    nothing resumes until you run both resume commands in the alert.

### Then

12. Install the schedule. This is the step that turns on hourly reading:

    ```bash
    jura-growth schedule install
    ```

13. Hourly reading is more automated activity on the same accounts (`prd-jura-inbox-watch` §4), and it doesn't
    make that compliant. If either account gets a warning, run `jura-growth pause inbox-browser` and
    `jura-growth pause publish`, and reopen the Graph API question in ADR 0006.

### If a surface goes blind later

Meta changes its layouts, and that shows up as a failed surface. After 3 of the watch's hours with no good
read, the one-pager's Needs you names it, with its last good read. Until it's fixed, check that surface by
hand, because a person there is going unseen. `jura-growth inbox status` shows the same.
