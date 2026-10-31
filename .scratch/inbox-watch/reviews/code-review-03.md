# Code review 03: approve an email reply and it goes out threaded

Branch `crew/inbox-watch-03-email-reply` at 8439ddc, against its fork point with `crew/inbox-watch`, bbcfc15 (two commits, 303f865 and 8439ddc, 27 files). Spec: the ticket, then the PRD with its "Amended" section, then the functional, technical and test-strategy reviews, and ADR 0003 and 0004.

**Verdict: changes-requested.** The verdict rests on the five blocking findings below: SEC-1, SEC-2 and P-1 to P-3. The gate itself is sound. What goes out is what was hashed, to the one recipient hashed, claimed before Resend, once, under one key, and nothing I tried broke that. The gaps are around it: what the card shows of the subject, a person writing again under a new subject, and what a D1 outage or a refused Resend key does to approved replies and to outreach.

**How this was checked.** Line numbers are at 8439ddc. "Reproduced" means it ran on the repo's test doubles in a throwaway detached worktree, under the worktree exports. Nothing touched a real mailbox, Discord, Resend or D1. The probes are in `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/3dcab9c8-e10d-45d9-9c0b-7a40a70479ee/scratchpad/probes-03/`, which is temporary, so each finding also gives its input. The Standards, Spec and Security reads were done separately from this diff, and each finding kept here was checked again by hand.

| Check | Result |
|---|---|
| `uv run pytest -q -p no:cacheprovider -o addopts=""`, worktree exports, at 8439ddc | 4966 passed in 388s |
| `pyright` on `agents/inbox/send.py` and `kinds.py` (advisory) | 0 errors |
| Blocked paths (`inputs/`, `design-system/`, `.env`, `data/growth/`) | no change under any of them |
| Build, lint | none configured (operating card) |
| UI diff | none, so `crew:web-design-review` doesn't apply |
| Trial merge into `crew/inbox-watch` (`git merge-tree`) | conflicts in `config/settings.yaml`, `inbox/__init__.py`, `commands.py`, `store.py` and other files both tickets add to. Ordinary for parallel tickets, and not a finding. The merged tree was not tested |

## The questions the brief asked me to judge

**Can anything but the approved bytes go out, to anyone but the approved recipient? No, by the hash. But Ting Yu doesn't see all the bytes he approves (SEC-1).** The subject is in the hash, and only its first 80 characters are on the card.

**Is the claim committed before Resend, once, with a sound key and retry bound? Yes.** The gate matrix's double reads the record on a fresh connection at call time. There is one key per item, the payload is byte-identical on a retry, and the retry stops at 23 hours, inside the 24 hours Resend's documentation gives its keys. Two gaps sit beside this: the bound isn't reached while a read or a sync is failing (P-4), and three tries end a reply long before 23 hours (P-3, P-5).

**The rest of the attack list.**

| Attack | Result | Evidence |
|---|---|---|
| Header injection through the subject, Reply-To or thread ids | held | `store.clean_line`, `_one_address`, `MESSAGE_ID_RE`; tests `IW-A7`, `IW-A8` |
| Reply-To at Jura | held | Probed `LEVI@JURASOLUTIONS.SG`, `levi@jurasolutions.sg.`, the ideographic full stop, `x@sub.hello.jurasolutions.sg`, a quoted local part, `;` and CRLF lists: all `None` from `valid_recipient` |
| Suppressed address | held for the From and the Reply-To, at `content()`, the claim and a retry. Exact address or exact domain only (N-5) | `IW-E2`; `kinds.py:86-92` |
| A newer message at claim time | held in the same conversation. **Fails under a new subject (P-1)** | `IW-F9`; probe |
| BCC exactly one | held | Payload probe: `bcc` is `['levi@jurasolutions.sg']`, `to` is one address, no `cc`. `IW-D3` asserts the whole JSON |
| One Discord message at every length (B8) | held | 65 high-priority cards scanned across draft sizes and recipient lengths: the longest was 1,995 characters and none split. The other 54 became hand replies |

**The outreach `Message-ID`: an email already approved still sends, and nothing is superseded. Reproduced across the two versions.** I raised and approved an outreach email on bbcfc15 and copied its database. On 8439ddc I applied the one new migration and ran `send_due`. `frame_fingerprint()` is the same, the approval's hash is the same, one email went out, the record is `approved` and used, and there are 0 superseded rows. The only change to the request is one more header. Behaviour does change in two other places: the 16:45 check now counts a stranger who names the id (asked for by F2, but see SEC-4), and an email claimed but unfinished when this merges has a narrow edge (N-1).

**Does Resend take `Message-ID` through `headers`? Unverified, and it probably doesn't keep it (P-6).**

- What I could read: Resend's API reference says `headers` is "Custom headers to add to the email", and its reply guide documents `In-Reply-To` and `References` through `headers`. So threading is on documented ground. I found nothing from Resend on `Message-ID`.
- AWS's SES documentation says "If you provide a Message-ID header, Amazon SES overrides the header with its own value". If Resend sends through SES, the id won't survive. I could not confirm that from Resend's documents; only the repo's own test fixture assumes it.
- What I can't verify, because no live call is allowed: whether Resend accepts the field, rewrites it, or refuses the request.
- If it rewrites it, the fallback is tested and sound: a colleague's domain match still works, copies are dropped by sender domain, and someone elsewhere is reported as a stranger.
- If it refuses it, every live outreach send ends `failed`.

**"D1 sync runs before claims; a failed sync can auto-pause outreach": holding the reply is right, pausing outreach from here is a surprise, and it blocks (P-2).** Failing closed on a stale suppression list is right for E2. But `sync_suppression` was written for outreach's own slots, where a paused agent stops running. `inbox-send` isn't stopped by that flag, so it pauses outreach again at every slot while a reply is waiting.

**What a D1 outage does to replies:** none is claimed, and each approved reply waits up to its 2-day use-by, then lapses to "answer by hand". A reply already claimed stays `sending` until D1 is back, then becomes `unknown` if the 23 hours have passed. Throughout, the only thing he is told is "Paused `outreach`". Nothing says replies are held.

## Standards

### Should fix

- **S-1. `RETRIES` is a limit outside `caps.py`.** `agents/inbox/send.py:45`. Rule: "Hard limits live in `jura_growth/caps.py`" (operating card), with `INBOX_TRIAGE_ATTEMPTS` as the precedent. It also repeats the bare `attempts < 3` at `outreach/send.py:601`.
- **S-2. Reuse: new code that repeats what the repo has.**
  - `send.py:51` `in_window` repeats `inbox/job.py:22`. Pass the window as an argument to one helper.
  - `send.py:247` `_clock` repeats `cards.py:63`.
  - `send.py:135` and `outreach/send.py:548` build the same seed, `{subject}|{content_hash}|{used_at}`. It belongs in `store.outgoing_id` (`store.py:323`).
  - `kinds.py:70` `_thread` repeats `report.py:77` and `triage.py:328`. Make it a `store` helper.
  - `kinds.py:227` `_masked_length` repeats the expression inline in `report.card_quote`.
- **S-3. A setup gap is listed twice.** `inbox/__init__.py:105-110` adds `RESEND_API_KEY_OUTREACH`, which `outreach/__init__.py:20` already declares, and `health.setup_gaps` (`health.py:115-122`) doesn't remove duplicates. Drop `_sending_gaps` or remove duplicates there. `kinds.switched_off` already refuses the card.

### Nit

- `CONTEXT.md`, "Claim", still says the one exception is an outreach retry, while ADR 0003 now gives `email-reply` the same bound. "Needs a hand reply" omits two new routes: a card too long (`kinds.py`, `_TOO_LONG`) and a promised reply (`send.py`, `_mark_sent`).
- `approvals.py:120-141`: the list of optional kind members lacks `conversation_card`. Only the README has it.
- `send.py` reports a crash through `mail.failed`, so the event reads `inbox.mail_failed {"mailbox": "send"}`. The helpers are used as generic health helpers, so give them a neutral name.
- `outreach/send.py:54` adds a module-level import of `inbox.store`, and `replies.py:458` imports inbox inside a function, while `inbox/kinds.py` imports outreach. It works, and plug-ins always load together. Possible Feature Envy: the outgoing table is shared by both, so it could live outside either.
- Names: `d1` (`send.py:107`), `number` holding an id (`kinds.py`, `send.py`), and `Reply.bytes` shadowing the builtin.

## Spec

### Blocking

- **P-1. A person's newer message under a new subject doesn't stop the reply.** `kinds.py:95-99` (`wrote_again`), with the conversation key at `mail.py:324`, which is the person plus the bare subject.
  - Spec: F9, "A newer message from them supersedes"; D5, "If the person writes again before the reply goes out"; E2, "An opt-out is honoured and never answered".
  - Reproduced, with a reply approved under "Pricing" and then read by the send's own intake:
    - `Subject: Please ignore my last email`, body "We have gone with another vendor. Please ignore my question.": `1 sent`, and the new message sits at `new`.
    - `Subject: Stop`, body "Please stop emailing me.": `1 sent`, with the address not yet suppressed, because for a non-contact that decision waits for triage.
  - F8's thread-based conversation is right for what triage hands out, but the guard has to be wider than the thread. People don't keep to a thread, and the reply goes within minutes of the fresh read that saw their message.
  - **Fix:** hold, don't supersede. Refuse the claim while any newer message from the same sender or reply address, in any conversation, is still untriaged. Once triage settles it, an opt-out suppresses and supersedes through the existing path, and a different topic lets the reply go on the next slot. Add `IW-F9` tests for both inputs above.

- **P-2. A failed D1 sync in `inbox-send` pauses outreach again at every slot, and says nothing about the replies.** `send.py:107-109`, through `outreach/sync.py:62`.
  - Rule: this is a concrete failure, and it goes against B5's reasoning that the job's failures mustn't stop another part of the engine. S6 gives each agent its own pause.
  - Reproduced with D1 answering 500 and one approved reply, through `runner.run("inbox-send")`:
    - three slots gave three identical alerts, "Paused `outreach`: suppression sync from D1 failed", and three run rows;
    - `jura-growth resume outreach`, then the next slot, and outreach is paused again;
    - no line in any channel says a reply is held. Two days later the reply lapses.
  - With a reply waiting, that is an alert every 10 minutes for the length of the outage, up to 85 a day. A one-slot blip on a Saturday evening, when outreach has no slot of its own, stops outreach until he notices.
  - **Fix:** give `sync_suppression` a mode that doesn't pause on a failed read, for this caller. Keep the hold on replies. Tell him once a day through `mail.problem`, naming how many approved replies are held. Facts that arrive through a good sync (a complaint, the bounce rate) should still pause outreach, because those are outreach's own rules and don't depend on who read them. `IW-E2`'s failed-sync test should also assert that outreach isn't paused.

- **P-3. A refused Resend account uses up every approved reply in 30 minutes.** `send.py:225-227`.
  - Spec: technical B5, "Follow `send.classify` for `pause`, `retry` and `fail`". Outreach's `pause` branch (`outreach/send.py:596-599`) leaves the message able to go again and stops further sends.
  - Reproduced with three approved replies and Resend answering 401:
    - three slots made nine calls, and all three replies ended `failed`;
    - after the key was fixed the next slot sent nothing, and they stay `failed` for good;
    - each alert reads "It may have gone out", after a definite refusal.
  - The same happens at `429 quota`, on a key shared with outreach. `IW-B5`'s refused-account test stops after two runs, so it asserts `sending` and never sees this.
  - **Fix:** a `pause` outcome spends no attempt, stops the run so no further reply is claimed, and leaves the claim to retry inside the 23-hour bound. Don't pause the `inbox` flag (B5). After a definite refusal, the words should say it didn't go.

### Should fix

- **P-4. The 23-hour bound sits behind the read and the sync.** `send.py:108` and `:115` both come before `_retry` (`:175-191`).
  - Ticket: "stops at 23 hours, past which it is marked unknown".
  - Reproduced: a claim with one failed attempt, D1 down, checked 24 hours later: still `sending`, no alert, and no further call to Resend. It became `unknown` only on the first slot after D1 came back. Nothing extra goes out, so this isn't blocking, but he isn't told what F15 promises.
  - **Fix:** close expired claims before the sync and the read.
- **P-5. Three tries end a reply at about 20 minutes, not 23 hours.** `send.py:45`, `:225`, pinned by `IW-F15` (`test_inbox_email_reply.py:809`). The ticket states only the 23-hour limit. It matches outreach's rule, but the key makes more tries safe, and a Resend outage of half an hour leaves approved replies `failed` for good. Retry to the bound, or log the decision that three is meant.
- **P-6. The first live use of the `Message-ID` header could be an outreach send.** `outreach/send.py:640`; `uat.md` U1. UAT U1 is the only check, and merging is what lets live jobs use the header. If Resend refuses the field, `classify` reads that as `fail` and each outreach email ends `failed`. Make U1's single test send a step before the first outreach slot after merge, and say so in the release notes for G4.

### Nit, or a decision to log

- **N-2.** A crash in a send run doesn't count toward auto-pause (`IW-B5`, line 847), though B5 says "only a crash counts". The code cites P-5 of review 01, which was about the precheck. I think the code is right, because a good slot leaves no run row, but log the decision.
- **N-3.** `raise_due` also runs from `inbox send-due`, where N10 says "Raise only in `inbox submit` and `reword`". It is needed when the switch was off at submit. In that path `raised_by_run` is empty, which is what N10 was avoiding. Log it.
- **N-4.** In production `used_by_run` is empty, because the job is quiet and has no run id at the claim (probed: `None`). Outreach's `scout-send` is the same. The matrix adapter starts a run row by hand, so its "used by a run" check proves something the live job doesn't do.
- **F15, "with the link".** An email has no permalink, so the `sent` and alert lines carry none. Defensible; log it.
- **`_TOO_LONG`.** D1 promises a card, and a draft that can't fit gets a hand reply instead. Defensible under B8; log it.
- **D1 not configured.** `inbox-send` proceeds on the local list, while outreach's live mode refuses in that state. With no D1, no click can be read. Log it, since a lost `CLOUDFLARE_*` setting would stop unsubscribes reaching replies without anyone hearing.
- **Dependency, not a defect.** The card and the promised line name `/growth inbox redraft`, `reword` and `done`, which have no handler at this commit. Ticket 04 mentions redraft and reword, but no ticket names `inbox done` verbatim. Check that ticket 04 carries it, and don't enable this before ticket 04 lands.

## Security

### Blocking

- **SEC-1. Ting Yu approves subject text he can't see, and it goes out signed by Levi.** `kinds.py:141` and `:212`, `SUBJECT_SHOWN = 80` at `:45`, `SUBJECT_CHARS = 300` at `store.py:45`.
  - Rule: D1, "the draft exactly as it will go out"; ADR 0003's content is what the card must show; S1, "Links in a draft may only be Jura's".
  - Reproduced: `Subject: Quick question ` + 170 × `x` + ` buy now https://evil.test/phish`. The card's own line stops at 80 characters and the quote at 160, so `evil.test` appears nowhere on the card. The request to Resend carries all 221 characters, link included.
  - The stranger chooses both the text and, with a `Reply-To`, who receives it. So one approval can send their words to a third party from Jura's domain, past the link rule that binds the draft.
  - **Fix:** the subject that goes out is the subject on the card. Cap what is sent to what is shown, or show it whole. Apply the draft's link rule to it, and fall back to `NO_SUBJECT` when it holds a link that isn't Jura's. Add both to `IW-A7`.

- **SEC-2. The subject line on the card isn't neutralised.** `kinds.py:212`.
  - Rule: IW-A5, "Text can't close the quote or restyle the draft ... a masked link shows its real address, unclickable"; technical N5.
  - Reproduced: `Subject: [Confirm at jurasolutions.sg](https://evil.test) ...` reaches the card as `Subject: Re: [Confirm at jurasolutions.sg](https://evil.test)`, outside the quote and directly above the draft, next to Approve. Mentions are safe: `allowed_mentions` is `parse: []`. I checked the text posted, not how Discord draws it; a Discord webhook message normally renders a masked link.
  - `IW-A5` (`test_inbox_email_reply.py:212`) plants hostile text only in the body. `report.shown_name` shows the pattern to follow.
  - **Fix:** pass the subject through `report._neutral`, and plant the same text in the subject in `IW-A5`.

### Should fix

- **SEC-3. A verdict of forged doesn't reach the card, and an odd `From` silences the recipient warning.** `kinds.py:183-190`, `mail.py:308-309`.
  - Rule: D1, "who and where"; code review 02, SEC-6, "approving must show who really gets it".
  - Reproduced with `trust_servers` on: `From: Victim <victim@bank.example>` with a failed DKIM verdict and no `Reply-To`. The intake notes "may not be from this address", but that note reaches only `#mission-control`. The card reads `Goes to v***@bank.example.` with no warning, so approving sends a reply to the person whose address was forged.
  - Reproduced: `From: Priya <priya@clinic.example>, x@y.test` with `Reply-To: m@evil.test`. `from_domain` is empty, `claimed` falls back to `evil.test`, and there is no warning. The card still names the real recipient.
  - The domain-only comparison is what A9 asks for, and the same-domain case (two Gmail addresses) is covered only by the masked address.
  - **Fix:** carry the forged note on the card, and warn when the `From` couldn't be read as one address.

- **SEC-4. Anyone holding a `Message-ID` can suppress a third party and unsubscribe a lead.** `replies.py:458` (`naming_our_mail`) leads to `replies.py:543` (`honour_opt_out(conn, sender, lead_id)`).
  - Reproduced at 16:45: `From: Victim <victim@third.example>`, `In-Reply-To: <the id>`, body `unsubscribe`, on a mailbox with no trusted servers configured. Result: `victim@third.example` is suppressed, and the lead is `unsubscribed`.
  - The id isn't guessable, so this needs a recipient or someone they forwarded to, and a forged `From` that passes `failed_verdict`. It is new in this diff, on the live outreach path, where a suppression is permanent.
  - **Fix:** a match by id alone counts as the lead's reply (F2) but never suppresses or unsubscribes. Report it so Ting Yu can act by hand.

### Nit

- **N-1.** An outreach email claimed and unfinished when this merges retries with one more header under the same key. Resend documents `409 invalid_idempotent_request` for a different payload under one key. `classify` reads that as `fail`, so the email ends `failed` with an alert. There is no duplicate, and at most one message is affected in that window.
- **N-5.** Suppression matches the exact address or exact domain (`suppression.py:28-38`). `victim+x@gmail.com` isn't `victim@gmail.com`, and `a@mail.x.com` isn't covered by a suppression of `x.com`. This predates the diff, but this is the first path where a stranger chooses the address. Worth a line in the follow-ups.
- **N-6.** `References` can reach about 5 KB (20 ids of up to 252 characters) with no byte cap, and no folding is visible on Jura's side. Resend's handling is unverified. The most I can trace is that the sender's own reply fails.

## What holds

- The gate matrix and Terminal refusal pass for `email-reply`, and the adapter is collected by glob.
- Content covers the recipient, subject, draft, thread headers, BCC and frame, each with a test that a change supersedes.
- `Hi Jane,` reaches the card, and stays through the edit (`IW-B3`).
- The newest message in a conversation supersedes, a sticker doesn't, and a stale message still closes the draft.
- A failed read claims nothing, and no network call happens inside the claim's transaction (`IW-F9`).
- Nothing about a person reaches a run row, an event or an alert, and only Resend's status code is kept (`IW-F15`).
- Lapse, use-by, daily cap, F10, S3, S11 and S6 all pass their tests, which I read and which test what their names say.
