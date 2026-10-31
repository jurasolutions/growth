# Reading inboxes through the browser, and what may reach Discord

Status: accepted (2026-10-31, ticket 05 of `prd-jura-inbox-watch-2026-10-31.md`). Amends ADR 0005
(browser jobs), Mission control PRD §4.4 (reply bodies in Discord) and Scout PRD §5.5 (no stored bodies).

Ting Yu asked on 2026-10-31 to be told about every reaction to Jura, on email, Instagram and Facebook,
and to approve every reply. A person who writes to Jura is the most valuable thing the engine can
notice. Today most would go unseen, and he can't judge a draft without seeing what it answers.

## Decision 1: read with the browser, in jobs of their own

Facebook and Instagram are read through Claude in Chrome, not the Graph API. The API would be the
compliant and sturdier way to read comments and messages, but it needs a Meta app, and BP §3.3 already
dropped it for posting. Two jobs join `publish` in `caps.BROWSER_JOBS`: `inbox-watch` reads, and
`inbox-reply` types. They share Chrome and the accounts, so all three take one `browser` lock in the
runner, after the job's own. A job that finds it held leaves a `run.quiet` event and starts no Claude.
It is one lock because asking whether another job's lock is held takes that lock for a moment, so a
probe landing as a run starts would make that run skip.

## Decision 2: a watch can't act

A transcript audit reports damage once it's done, and a watch reads hostile text on every page with the
accounts signed in. So `computer`, `form_input`, `file_upload` and `upload_image` are denied by name
for `inbox-watch`, on top of `publish.scope.DENIED_TOOLS`. A deny beats the domain allow. It reads with
`navigate`, `read_page`, `get_page_text` and `find`, and opens a thread by the address it finds. A
`read_only` audit stays as the second layer: any click or key fails the run, even a denied one, and
pauses `inbox-browser`. The audit gains `AuditRules`, keyword-only with the publish job's as defaults,
so `tests/test_publish_audit.py` doesn't change.

`inbox observe --file` takes everything from a scratch file, so a page's words never pass through
Bash quoting. Every field is validated, and a refusal gives a fixed reason. The text a message stores
must appear in what `get_page_text` or `read_page` returned to that run (`find` is a retelling), in one
result with its lines together, and not in the tab's address or title, or the item is `unverified`:
reported as such, with no draft. Messages are held until that check, so nothing unchecked reaches a report
or triage. A surface counts as read only if the run said so, read a page on that platform and passed its
audit. Anything else has failed, which is different from a quiet day. A model's words and links never
reach a run row, #alerts or a run update: `after_run` writes them from a closed list and record fields,
and an audit's findings, which can quote what a model asked for, stay in the event.

`inbox-watch` and `inbox-reply` start in an empty folder of their own, as triage does (`caps.CLEAN_CWD_JOBS`,
code review 02 SEC-1), because Claude Code runs read-only Bash unasked, and `grep -r KEY .` from the repo
would reach `.env`. A session on hostile pages with the accounts signed in needs that more than triage does.
So every path these jobs are handed is absolute: scratch files and image copies alike. `publish` hasn't
moved, because it is a rehearsed live job, and has its own follow-up.

The read-only audit is an allow list, so a tool the extension adds later fails until it is looked at.
What a run may ask to open is held to a surface, a thread, a post of Jura's or a post in a group, so no
page can send it to `l.php` or `/accounts/logout/`. Where the platform then redirects is its own
choice: a login wall is a stop signal, not a finding.

A reply run has to click and type, so it keeps `computer`, for the steps that need it and no others. Before
anything else it reads the one target it was handed and says what it found. A newer message supersedes the
draft, and only a clean read is claimed. Until the claim, and after its done word, the audit holds it to reading,
as it does a watch. In between it may use `left_click`, `type` and `key`, with no more clicks than the steps name
before it types, and `one_line` holds it to the approved text, whole, once, with one send. `form_input` and
uploads are denied by name. The audit holds either kind to the claimed thread or post, by what its tab showed.

What the run says is believed only as far as Chrome bears it out, because it has just read hostile text:

- **`sent` takes proof:** an audit with no failures, the whole text typed and sent, and its words at the target's
  address in a read after the send. On a comment the Page's or account's name must be beside them. A direct
  message shows no name on its own, so who it went as rests on the page having shown that name before the claim.
  Anything less is `unknown`, which pauses `inbox-browser`, alerts and is never sent again, so nothing resolves it.
- **A page can't close an item.** `gone` and `answered` count only with evidence at the target's address: a page
  without their words, or their words with the Page's name after them. Otherwise the item needs a hand reply, and
  the line says why. A session the page doesn't name gets a hand reply too, with no stop.

What this can't prove, and accepts: which control a click between the claim and the send hit, so the prompt
names them and Part B reads the Page's activity log. That a page showing the Page's name is acting as it, since a
page can show both. That the message reported as newest really is, since a run can name an old one or claim a
sticker: the sticker's word is looked for on the page, and the harm is bounded because only the approved text can
go, in the right thread. Two people with one name can't be told apart.

## Decision 3: the conversation class

Text a person wrote and their display name may appear on a card and on an R1 message, on Ting Yu's own
private server, with phone numbers, email addresses and secrets still masked. `privacy.for_discord(...,
conversation=…)` carries exactly those strings and nothing else. Only cards and R1 use it: the one-pager's
excerpts and `/growth inbox list` stay plain-masked. Discord is still a third party outside Singapore,
which he accepted by asking. To make a draft possible, `inbox_items` stores a person's text, capped at
4,000 characters and removed 90 days after an item closes. It also lands in triage and browser
transcripts (7 days), in `approval_cards.first_piece`, in the Discord outbox and in `growth.db`'s 14-day
backups, all of which live in OneDrive.

## Decision 4: triage is scratch-only

`inbox-check` reads the same hostile text, so `caps.THIRD_PARTY_TEXT_JOBS` gives it only its scratch
folder, as ADR 0005 established for browser jobs. The text is input, and a class and a draft are the only
output. The draft goes to Ting Yu.

## Decision 5: two plug-ins, and one registers the commands

A pause flag, a run set, auto-pause and a kind's `agent` all key on a plug-in's `NAME`, so two flags need
two plug-ins: `pause inbox` stops the mail and `pause inbox-browser` stops the browser. `inbox_browser` is
thin. It has no `register`, because a second `inbox` click group would silently replace the first, and
no `MIGRATIONS`. It imports `inbox` at the top, so if `inbox` is broken both are, and closed. A stop signal
in a browser run writes both the `inbox-browser` and `publish` flags, because they share the accounts, and
`inbox_browser.precheck` reads the `publish` flag, so `publish` needs no edit. Only Ting Yu resumes.

## Consequences and limits

- **It isn't compliant.** BP §4.1 applies and grows: hourly reading is more automated activity on the
  same accounts. The hourly limit, one reply per run and the stop signals slow it, and don't make it
  compliant. Reopen the Graph API if an account gets a warning.
- **"Seen".** Opening an unread thread shows the sender "Seen" and clears its unread mark. The prompt reads
  the list first and opens only threads with something new.
- **Unread comments are counted, not lost.** With no clicks, comments not loaded on first paint go unread.
  The page's own count, less what was recorded, reports as "3 comments the watch couldn't read: check by
  hand".
- **A key's limit.** A message is keyed on its first 120 alphanumerics. A cut shorter than that, such as a
  list preview, reads as a different message, so the prompt copies from the thread and not from a preview.
- **A steered stop.** A page can talk a model into `inbox stopped`, which pauses browser work until he
  resumes it. That fails safe and costs an hour's reading, so it stays, and the alert says so.
- **Counts include the Page's own.** A post's page shows one total of reactions and shares, with no split,
  so S8's "excluding the Page's own activity" holds only for comments, through `page_comments`.
- **The Page's name.** Facebook names aren't unique. What the page links to the Page's address is the
  Page's. What only has its name is set aside, and counted once in #mission-control.
- **Layouts change.** Meta's pages can't be tried in a build. The fixture proves the code, and the setup
  guide's first-run checks prove Meta. A failed surface is how a layout change shows up.
- **Business Suite threads** carry their thread in the query, not the path. The reply job binds to them
  with `selected_item_id`, and anything else is reported as "answer by hand".

## Reversal

Remove the jobs from `caps.BROWSER_JOBS` and run `jura-growth schedule uninstall inbox-watch`. If the first-run
check shows reads are too thin, allow `computer` in `inbox_browser/scope.py` by taking it out of
`WATCH_DENIED`: one line, and the `read_only` audit still fails everything but looks.
