# Jura growth engine

The scheduled agents that find leads, send outreach, draft social and community posts, publish
approved posts, and write app PRDs for Jura Solutions, and the shared plumbing they run on.

## Scheduling

**Agent**:
A named worker with its own pause flag and digest section (scout, outreach, social, community,
app-factory, publish, inbox, inbox-browser), plus the system agents heartbeat, digest and backup.
_Avoid_: bot, worker

**Job**:
One entry in the schedule: what runs, for which agent, and when. One agent may own several jobs
(outreach owns scout-send and scout-sync).
_Avoid_: task, cron

**Slot**:
One scheduled time at which a job is due to run, in SGT. A business-days job has no slots on
weekends or public holidays.
_Avoid_: tick, occurrence

**Run**:
One actual execution of a job, with a start, a finish, a status and a summary.
_Avoid_: execution, invocation

**Quiet run**:
A run of a job marked quiet (scout-send, publish) that found nothing to do. It leaves a trace that
it ran, but no Discord post.

**Slot status**:
What happened at a slot: **ok**, **failed**, **skipped** (with its reason: paused, not a business
day, precheck, previous run still going), **running**, **due** (the slot's time has passed but its
window is still open and nothing is recorded yet; never counts as needing attention), **missed**
(the next slot came with no run or skip recorded), **upcoming**, or **not installed** (the job isn't
loaded in launchd, or the slot is earlier than the job's first run, skip or quiet-run trace).
_Avoid_: result, state

**Install state**:
Whether a job is loaded in launchd: **installed**, **installed but out of date** (the plist in
`~/Library/LaunchAgents` differs from what the schedule would generate now), or **not
installed**.
_Avoid_: deployed, enabled

## Outputs

**Artifact**:
Anything a run produced that a person may want to read: an outreach email, a lead, a social
draft, a community post or reply idea, an app PRD, a digest, a Discord post, a transcript.
_Avoid_: output, deliverable

**Transcript**:
The full record of a headless Claude run, kept for 30 days (7 days for browser and triage runs,
which hold third-party text).
_Avoid_: log

## Scout research

**Candidate**:
A company the research run looked at today and scored, whether or not it is kept. A run
compares about 20 of them and submits them as one ranked batch.
_Avoid_: prospect

**Shortlist**:
The day's kept leads: every candidate at or above the score threshold, best first, up to
`research.shortlist`. The code ranks the day once. Candidates not kept are remembered as
researched for 12 months.
_Avoid_: daily target

**Hiring evidence**:
A job posting that shows a candidate hiring for manual work: its URL, title, date seen and the
duties it names. Evidence only, never a contact source.
_Avoid_: job lead

## Mission control

**Mission control**:
How the engine and Ting Yu talk, entirely in Discord: the one-pager and run updates going out,
approval requests and control commands coming back through Discord Dispatch. There is no local
page.
_Avoid_: dashboard, admin

**One-pager**:
The single Discord message in `#mission-control`, daily at 08:00 SGT and on request, that says
whether everything ran and what needs Ting Yu: the health strip, approvals waiting, today's slots,
yesterday's figures, and a 14-day grid as an image.
_Avoid_: report, summary, dashboard (the 17:30 digest is a separate message)

**Health strip**:
The "Needs you" section at the top of the one-pager: the PAUSE file, paused agents, recent
failures, missed slots, undelivered Discord posts, unposted approval requests, approved emails that
lapsed unsent, jobs not installed or out of date, setup gaps, build handoffs waiting for a builder,
built apps not yet released (left on their preview, approved and waiting for `release-plan`, or
claimed and waiting for `main`), and a growth.db with an unfinished write.
_Avoid_: status bar, alerts panel

**Run update**:
The one Discord message an agent's run posts to its own Discord channel when it finishes, skips or
fails: status, timing, cost, its summary as a short quote (at most 300 characters), a failed run's
error in one line, what it produced and the approval requests it raised. A PAUSE-file skip posts none; publish posts one only when it claimed a publish item.
_Avoid_: notification, log line

**Setup gap**:
A setting or secret the engine needs that isn't configured yet, named but never shown: for
example "`RESEND_API_KEY_OUTREACH`: not set" or "Discord: 3 of 10 webhooks". `jura-growth status`
and the health strip report the same gaps.
_Avoid_: missing config, error

**Channel**:
Always qualified. A **Discord channel** is where a message posts (`#approvals`, `#alerts`). A
**brand channel** is the `gate.py` rule set a piece of text is checked against (`email`, `social-facebook`).
_Avoid_: bare "channel"

## Approvals and control

**Approval request**:
A record in the `approvals` table, and its card in `#approvals`, asking Ting Yu to approve or skip
one outward-facing action. Its id (`A-nnnn`) is the id he types to decide; an inbox item's `I-nnnn`
is the only other id he types. It carries what and why, a preview, a decide-by, a use-by and the
content the kind computed. Its status is pending, approved, skipped, expired or superseded; an
approved one is claimed at most once.
_Avoid_: ticket, confirmation, sign-off (a PRD sign-off is a different thing), `P-nnnn` in commands

**Request reading**:
What an approval request means now, judged by growth's clock for the one-pager and the health strip,
before anything writes the change: **waiting**, **lapsed** (unanswered past its decide-by),
**approved**, **lapsed unused** (approved, never claimed, past its use-by), **used**, **skipped** or
**superseded**. Kept apart from the stored status, which changes only when something writes it.
_Avoid_: state, status (that is the stored one)

**Approval kind**:
The type of action an approval request covers, declared by the plug-in that owns it, with its own
content, preview, deadlines and skip, expiry and lapse actions: `outreach-email`, `app-build`,
`app-release`, `group-rules`, browser publishing's `social-post`, `community-post`, `group-join`,
and the inbox's `email-reply` and `social-reply`.

**Decision**:
Ting Yu's approve or skip on one approval request, recorded with the actor, the human origin it came
through, growth's own time, the content hash and the Dispatch delivery reference. A skip is allowed
until the request is claimed.
_Avoid_: "approval" for the act

**Decide-by**:
When a pending approval request lapses unanswered. It then expires and its kind's expiry action runs
(an email is cancelled). Judged by growth's clock, not Discord's message time.
_Avoid_: "expiry" alone

**Use-by**:
When an approved but unclaimed approval request lapses. It then expires with nothing claimed and its
kind's lapse action runs. For an email it is separate from the decide-by, so a yes isn't lost behind
the send caps.
_Avoid_: "expiry" alone

**Claim**:
Using an approval at the point of no return: inside a `BEGIN IMMEDIATE` transaction, before the
outward effect (a Resend call, a click in Chrome, a build handoff), re-checking that the record is
approved, before its use-by, unused and matching, and marking it used. After a claim, a skip is too
late and no deadline is checked again, with one exception (amended 2026-10-27): a retry of an outreach
email or an email reply under the same claim is also bounded by the approval's use-by and by 23 hours from
the claim. Past either, it is marked uncertain or unknown and Ting Yu is alerted; it is never resent.
_Avoid_: use (in prose), consume

**Human origin**:
Where a decision or control command may come from: `jura-growth remote`, reached through the SSH
forced command from Dispatch, carrying Ting Yu's Discord decision from `#approvals`. Never Terminal
(off since 2026-10-26, until a Touch ID ticket; ADR 0004), never a process with a `claude` ancestor
or Claude Code's environment markers, and never a headless run. Redrafting or rewording an inbox
reply comes through the same origin.
_Avoid_: authenticated user (the Discord user id is attribution, not authentication)

**Gated action**:
An action that claims a matching approval before it runs and refuses without one: sending an
outreach email, writing a build handoff, handing out a release merge, confirming a group's rules,
publishing a post, joining a group, sending an inbox reply.
_Avoid_: protected action

**Build handoff**:
The `app_builds` record written when an `app-build` approval is claimed: the app, the PRD text and
its hash, and the approval. Dispatch, or Ting Yu by hand until Dispatch can, builds from it on the
app's own task branch. The same record then follows the build: `built` once `apps built` reports
its task, branch, head commit and preview, and `released` once `apps released` finds that commit on
`main` after a second, `app-release` approval.
_Avoid_: build request, ticket

**Control command**:
A `jura-growth` command Ting Yu sends from Discord through Dispatch, run by `jura-growth remote`
against its own allowlist, with his Discord user id recorded as the actor.
_Avoid_: remote command, bot command

**Skip**:
Only the decision. Use **skipped run** for the slot status, **dropped** for text the brand gate
refused, and **fit: skip** for a community group judged not worth posting in.
_Avoid_: bare "skip" in mixed contexts

## Publishing

**Publish item**:
One action the browser may take, with frozen content: a social post for one platform and day, a
community post for one group and day, a group join, or the membership answers for one join. It is
the subject of exactly one approval request. Its lifecycle is ready, claimed, done, stopped, unknown
or withdrawn; its approval state lives only in the approval request.
_Avoid_: "item" alone (community plan items and checklist items are different things)

**Posting identity**:
The account a publish item acts as: the Jura Facebook Page or the Jura Instagram account (the Jura
LinkedIn company page too while LinkedIn was on; it was switched off on 2026-10-29). In groups it is always the Jura Page; a group that only lets personal profiles
join or post is skipped.
_Avoid_: account, login

**Posting window**:
09:00 to 18:00 SGT, when the publish job may act (`caps.PUBLISH_WINDOW`). A post's decide-by and
use-by are the end of the posting window on its day.
_Avoid_: "publish window", alongside the outreach "send window"

**Stop signal**:
Anything on a page that makes a browser run stop at once without clicking further: a login wall, a
CAPTCHA, a checkpoint, a warning, a restriction, the wrong posting identity, or anything it can't
identify on a step that would post. It pauses publishing and the inbox's browser jobs until Ting Yu
resumes them. Membership questions, a group that doesn't allow Pages, a deleted post or comment and
a closed reply box are outcomes, not stop signals.
_Avoid_: error

## Inbox watch

**Reaction**:
Anything a person or a platform did in response to Jura: a message, a comment, a rise in a post's
counts, an app opened.
_Avoid_: "reply" for anything inbound. A reply already means an inbound answer in outreach and an
outbound one here, so say **inbound message** and **inbox reply**.

**Inbound message**:
What a person wrote to Jura: an email, a website enquiry, a comment or a direct message.

**Inbox reply**:
What Jura sends back to an inbound message, only ever after Ting Yu approves it. It goes out as
**Levi**, the sender name on Ting Yu's email.

**Inbox item**:
One recorded reaction, with its id `I-nnnn`.
_Avoid_: "item" alone

**Conversation**:
Every message from one person in one thread. It is the unit of triage, and it has at most one open
card.
_Avoid_: thread, when it means the person's messages rather than the place

**Triage**:
The step that classes each new conversation and drafts an inbox reply where one is merited. The
model only proposes: it can hide nobody and send nothing.

**Watch run**:
One read of the social platforms in the browser. It can read and record, and it can't act.

**Reply run**:
One `inbox-reply` run, which posts at most one approved social reply. It reads the target before its
claim and the code decides from what it reports. It types only the approved text, whole, once, and reads
it back. A claim it leaves open is `unknown` and is never sent again.

**Surface**:
One place a watch run reads, such as Instagram Requests or a Page's notifications. A surface with
no record of a good read has failed, which is different from a quiet day.

**Unverified**:
A message a watch run recorded whose words weren't in what a page returned to that run, or that a run
with a failed audit recorded. It is reported as such and gets no draft. Until that check a message is
**held** (state `observed`), and goes to neither a report nor triage.

**Baseline**:
What a surface's first good read found, except a message known to be under 48 hours old that the Page
hasn't answered. It is stored and never told.

**Replies waiting**:
The one-pager's section for open inbox items, between Needs you and Approvals waiting. `/growth inbox
list` shows the same on request.

**Closed**:
An inbox item Ting Yu is asked nothing more about. A person's words are removed 90 days after it closes.
A reported message closes when its report went, noise when it was recorded, and a hand reply when he
clears it or a week on, when the list stops showing it. A promised reply stays listed until he clears it,
and its words still go 90 days after it was sent.

**Promised**:
An inbox reply that says Levi will come back personally. The item stays open after it goes, until
Ting Yu clears it.

**Needs a hand reply**:
An inbox item the engine won't answer: no single address or thread to reply to, a draft that failed the
brand gate twice, a draft whose card won't fit one message, a person who opted out and wrote again, or a
reply run that couldn't get a clean read of the thread. Also a sent
reply that promised a personal one from Levi, which he owes until he clears it. Its state in the code is
`needs-you`.
_Avoid_: "needs you", which is the health strip

**Noise**:
Mail with evidence in its headers that no person wrote it: a mailing list, a no-reply sender, a
platform's notice, and anything in the Junk folder. It gets no message of its own. The digest counts
it, and the one-pager lists it under Replies waiting with each sender's domain, and a Junk message's
subject.
_Avoid_: spam, which is a class a model gives a person's comment
