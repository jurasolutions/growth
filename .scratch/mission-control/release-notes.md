# Release notes: mission control and browser publishing

*For Ting Yu. Branch `crew/mission-control` at 0354503, into `main` at 855e48c. Written 2026-10-27
by the crew's release manager against `prd/pending/prd-jura-mission-control-2026-10-25.md` (MC)
and `prd/pending/prd-jura-browser-publishing-2026-10-25.md` (BP), with their dated amendments.*

## What ships

- **Mission control in Discord.** A one-pager in `#mission-control` at 08:00 SGT and on request:
  what needs you, approvals waiting, today, yesterday, and a 14-day grid that tells a missed slot
  from a quiet run. Each scheduled run posts one run update in its own channel.
- **Approvals.** Every outward action now waits for your yes in `#approvals`: outreach emails,
  social posts, community posts, group joins and their answers, app builds and app releases. Group
  rules and their open days are confirmed the same way. Each card shows the exact text that would go
  out, why, and when the request lapses. An approval covers those exact bytes and is used once. If
  the text changes, the old request is superseded and a new card appears. Silence is never a yes.
- **Decisions come only through Dispatch.** The only way a decision reaches the Mac is Dispatch
  calling `bin/growth-remote` over SSH, through the forced command in `authorized_keys`. Terminal
  and every headless run are refused. `jura-growth approve` and `skip` in Terminal answer
  "refused: decisions aren't taken in Terminal: approve or skip it in #approvals."
- **Control from your phone.** `/growth status`, `approvals`, `one-pager`, `pause`, `resume` and the
  other commands on the allowlist in `docs/dispatch-contract.md`.
- **Browser publishing.** A new `publish` job posts one approved item per run through Claude in
  Chrome, as the Jura Facebook Page, Instagram account or LinkedIn company page, inside 09:00 to
  18:00. It also joins groups and posts in them as the Page. Every run is audited against its
  transcript, and any login wall, captcha, checkpoint, rate limit, removal, admin warning or wrong
  identity stops the run and pauses publishing.
- **A fixture platform** for rehearsing the real publish job on local pages (R1 to R6), refused on
  live data or a non-loopback address.

## What stays off after the merge

Nothing outward changes by merging. Each switch below is off in the committed config, and turning
it on is one of your steps:

| Switch | Committed value | Turned on in |
|---|---|---|
| `outreach.mode` (`config/scout.yaml`) | `shadow` | ticket 15, after U17 |
| `approvals.discord_buttons`, `approvals.post_buttons` | `false` | ticket 15 |
| `approvals.dispatch_builds` | `false` | ticket 16 |
| `publish_mode` per platform (`config/social.yaml`) | `draft`, `page_url: null` | after R1 to R6, Facebook first |
| `browser` (`config/community.yaml`) | `false` | after U12, for U14 and U15 |
| `pages_project` (`config/apps.yaml`) | `null`, so `apps built` refuses every preview | ticket 16 |

## What changes the day you merge and reinstall the schedule

1. **Two new launchd jobs.** `one-pager` at 08:00 daily, and `publish` every 20 minutes from 09:00
   to 17:40, every day including weekends. While every platform is in `draft`, the publish
   precheck finds nothing to claim and skips without starting Claude.
2. **Terminal can't decide anything any more**, and neither can a headless run. Until Dispatch is
   live (ticket 14), requests are raised and posted, then lapse unanswered.
3. **App PRDs will lapse until Dispatch is live.** The first factory run or `submit-prd` raises one
   `app-build` request for each PRD already in `prd/pending/apps/` (five today), and one for each
   new PRD. A request unanswered for 7 days moves its PRD to `prd/skipped/apps/` as "Expired
   unanswered", and the idea rests for 30 days. If you'd rather keep them, run
   `jura-growth pause app-factory` until ticket 14 passes, then `resume app-factory`.
4. **Group days are confirmed in Discord only.** `community set` refuses `promo_days=` and
   `post_days=`. `community set <id> rules_confirmed=yes` raises a `group-rules` card, and you type
   the days in its decision: `/growth approve A-nnnn promo_days=… post_days=…`. Groups you
   confirmed earlier keep their confirmation and days. This replaces step 1 of the blocker-fix
   release notes.
5. **Community drafts are written as the Jura Facebook Page** ("we", in the Jura voice), not as you
   personally (`post_as` in `config/community.yaml`, decision TY1).
6. **`.env` gains three entries:** `DISCORD_WEBHOOK_APPROVALS`, `DISCORD_WEBHOOK_MISSION_CONTROL`
   and `CONTROL_DISCORD_USER_ID`. Without the approvals webhook no card is posted, so every request
   lapses. Without `CONTROL_DISCORD_USER_ID`, `status` shows a setup gap.

## After merging: your steps, in order

Each step is yours because it touches your accounts, your Mac's security settings or a live
platform. Record checks in the ticket's QA file (`reviews/qa-NN.md`).

### 1. The Mac

1. `uv sync` in `repos/growth`.
2. Keep the Mac awake and logged in for the schedule (the publish window runs 09:00 to 18:00 and
   needs a logged-in session): `sudo pmset -c sleep 0`, `sudo pmset repeat wakeorpoweron MTWRFSU
   06:15:00`, `sudo pmset -c autorestart 1`, and log in after any restart (FileVault is on). See
   the blocker-fix infra audit, A4.
3. **Before you reinstall the social job, delete the frozen-clock test rows**: the three
   2026-10-26 `draft` rows in `social_posts`, `runs` row 5, the 2026-10-24 test drafts, and
   `outputs/growth/social/2026-10-26/`. Otherwise the next 07:00 run skips with "today's drafts
   are already in #social-drafts", and the test drafts count toward the 14-day no-repeat history.
   There is no command for this; it is a `sqlite3` delete on the Mac.
4. Don't put an Anthropic API key or a setup token in the launchd environment. It silently drops
   the Chrome tools; the publish precheck then skips with the reason, and `status` lists it.

### 2. Discord channels and Terminal checks (ticket mc 13)

1. Follow `.scratch/mission-control/setup/discord.md`: add `#mission-control` and `#approvals` to
   Jura HQ, and set `#approvals` to notify on all messages.
2. Put the two new webhook URLs in `.env` as `DISCORD_WEBHOOK_APPROVALS` and
   `DISCORD_WEBHOOK_MISSION_CONTROL`, and your Discord user id as `CONTROL_DISCORD_USER_ID`. The
   `wizard` can walk you through it without the values entering a file, log or chat.
3. `jura-growth schedule install` (the job list gains `one-pager` and `publish`).
4. Remove the Jura growth line from the Cowork morning brief
   (`.scratch/mission-control/setup/morning-brief.md`).
5. Run U1 to U5.

### 3. Open the Mac to Dispatch (ticket mc 14)

1. Deploy Discord Dispatch on its always-on machine with D1 to D4, D8 and D9
   (`~/projects/discord-automation/`).
2. Follow `.scratch/mission-control/setup/remote-control.md`: turn on Remote Login for your user
   only, keys only; join both machines to Tailscale; make Dispatch's key on its machine; add the one
   `restrict,command=…,from=…` entry to `~/.ssh/authorized_keys`, and make it the only entry.
3. Bind `#approvals` and `#control` in Jura HQ to company `jura` only, accepting your user only.
4. Run U16 and U7, and the asleep-Mac check.

### 4. UAT Parts A to C

Run `.scratch/mission-control/uat.md` "Before you start", then Parts A, B and C on a test Discord
server and a UAT-only SSH key. Remove that key and binding when you finish.

### 5. Chrome profile, accounts and the rehearsal (tickets bp 01, then bp 07)

1. **Create the Jura Facebook Page** if it doesn't exist yet, and make sure the Facebook account in
   the Chrome profile administers it. Do the same for the Jura Instagram account and the LinkedIn
   company page.
2. **Create a dedicated Jura Chrome profile**, signed in only to those three accounts: not Discord,
   Gmail, or any TaskWise or ZenexFlow account. Enable the Claude in Chrome extension only in this
   profile, on the same claude.ai account and organisation as Claude Code, and pick it once in
   `/chrome` → "Select browser…".
3. Run U9, U10, U11 and U18 (bp 01). U18 records how `ClaudeInChromeDomain` treats subdomains.
4. Run the rehearsal R1 to R6 in `uat.md` Part R, including R1b. Record R1b's two probe results,
   with their `permission_denials` lines, in the Comments of
   `.scratch/browser-publishing/issues/07-fixture-platform.md`. bp 07 closes only then.
5. Record the Facebook permalink shape you saw at R1 on bp 01. The crew then adds it to
   `hosts.post_problem`, so Facebook done-URLs are checked by path shape too.

### 6. The first live posts (U12, U13, U14, U15)

1. Set Facebook's `publish_mode: browser` and its `page_url`, then run U12 (`uat.md` D1 to D3).
2. Instagram, then LinkedIn, each after R1, R2 and R6 for that platform, then U13 (D4). Weekends
   stay on with three platforms; set `weekends: false` if three weekend cards are too many.
3. Set `browser: true` in `config/community.yaml`, then U14 and U15 (D5) in a private test group
   and a second group that allows Pages and asks membership questions. In U14, record the group
   page's address form and a post's timestamp link (code review 05, S2).

### 7. Buttons, then live outreach (ticket mc 15)

1. Dispatch D5: Approve and Skip buttons, through an `#approvals` webhook Dispatch owns. Store it
   as `DISCORD_WEBHOOK_APPROVALS`, replacing the one from step 2.
2. `approvals.post_buttons: true`, then U17.
3. Only when U17 passes: `approvals.discord_buttons: true`.
4. Before `outreach.mode: live`, clear every live pre-condition `jura-growth outreach status` lists:
   - **A legal view on the Spam Control Act**'s address-harvesting provision, then
     `legal_review_done: true`.
   - **Resend and DNS:** choose and verify the sending domain in Resend (the DKIM, MX, TXT and
     DMARC records in Cloudflare DNS), make a sending-only `RESEND_API_KEY_OUTREACH`, set
     `UNSUBSCRIBE_SECRET` identically in growth and in Pages (production and preview), and make
     the From mailbox or alias.
   - **Make the landing page's D1 `suppression` table append-only first** (an
     `id INTEGER PRIMARY KEY AUTOINCREMENT` column, plain inserts, never updated or deleted, as
     `docs/scout.md` says), and start it empty. **Only then** set `CLOUDFLARE_API_TOKEN`,
     `CLOUDFLARE_ACCOUNT_ID` and `D1_DATABASE_ID`. In the other order the sync query fails and
     outreach pauses itself.
   - `inputs/do-not-contact.csv` (a header row is enough).
5. `outreach.mode: live`, then U6, then the first live week (`uat.md` Part E).

### 8. The first app build through Dispatch (ticket mc 16)

1. Merge the `toolbox` branch of `repos/landing-page` into its `main`.
2. Give `repos/landing-page` a `dev` branch (Dispatch ships to each repo's `dev` branch), and put
   Cloudflare Access with your login in front of it and of every `*.pages.dev` branch preview.
3. Set `pages_project` in `config/apps.yaml` to the landing page's Cloudflare Pages project.
4. Dispatch D6 polls `apps handoffs --json`. Once it does, `approvals.dispatch_builds: true`.
5. Check a preview asks for your Cloudflare login in a private window, then U8.

### 9. After acceptance

- Copy the three guides in `.scratch/mission-control/setup/` to `outputs/growth/setup/`. The
  `discord.md` and `morning-brief.md` there today are the older versions (the morning-brief one
  still adds the line this release removes).
- Move both PRDs to `prd/done/` with the ship date, and bring AC-P1.3's wording in line with the
  amended A11 (final review Sp5).

## Gaps found during release prep

- **The browser-publishing setup guide was never drafted.** bp 01 step 1 names
  `.scratch/browser-publishing/setup/browser-publishing.md`, which doesn't exist. Step 5 above and
  bp 01 itself carry what it would say. The crew can draft it on request.
- **The UAT SSH entry's exact form isn't written down.** `uat.md` "Before you start" step 4 still
  says it waits on the tech lead. The approach was decided (crew-log 2026-10-27T02:22: a UAT-only
  key whose forced command fixes the UAT folder variables), but not the `authorized_keys` line
  itself. Parts A to C need it.

## Known limits

- **Facebook profile identity is prompt-only.** The Chrome profile is your own Facebook account,
  which administers the Page, so code can't make a post or join as your personal profile
  impossible. The guards are the prompt's identity check and never-switch rule, the wrong-identity
  stop, rehearsals R5 and R6, and live step U15.
- **Posts held for admin approval stop as unidentified** and pause publishing, until U14 shows how
  often that happens. A pending outcome can be added then.
- **The permalink group segment form is unproven.** If Facebook's post links use a different group
  segment (name or number) from the register's URL, `publish done` is refused and the item goes
  `unknown`. U14 checks it, and `uat.md` D5 says how to settle such an item.
- **Raw SQL on `growth.db` can still forge a decision** (ADR 0004). Nothing scheduled can run it.
- A `file_upload` parameter rule may not narrow uploads (R1b). Until it's known, the audit checks
  every upload against the claimed item's own copies.

## Follow-ups (nits from the final review)

- **St4.** Publish item kinds are switched on in several places; one per-kind table in `items.py`
  if a fifth kind comes.
- **St5.** The `app-build` use-by is never reached, because approval claims at decision time. Drop
  the cap and the config key, or say why they stay.
- **St6.** `NotApproved` reasons (`gone`, `changed`, `mismatch`, `unwritten`) aren't in its
  docstring.
- **St7.** `caps.py` says "publish window" (CONTEXT.md says "posting window"), and times reach
  Discord in three formats.
- **Sp4.** The schema still accepts a `terminal` origin and `use()` doesn't check the origin.
  Defence in depth: a refusal in `use()` and a trigger, in a new migration.

## What to watch, and for how long

- **First week:** the 08:00 one-pager every day (it is also the sign the Mac was up), `#alerts`
  for auto-pauses and setup gaps, and `jura-growth status`.
- **Each first live platform day (U12, U13, U14):** the run update in `#social-drafts` or
  `#community` with the live URL, and the post on the platform itself. Any stop pauses publishing
  and posts in `#alerts` with the run id.
- **First two live outreach weeks:** `#outreach-sent` never shows more than the day's quota, and
  your approval load (the E2 table). Revisit batch approval after two weeks.
- `jura-growth log events --kind approval` and `--kind remote.command` show every decision and
  every Dispatch call.

## Rollback

### Switch everything off first (no revert needed)

1. `touch /Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth/PAUSE` stops every job
   at its next start. `/growth pause <agent>` or `jura-growth pause <agent>` stops one.
2. Set `outreach.mode: shadow`, each platform's `publish_mode: draft`, and community `browser:
   false`. Do this **before** any revert: reverting restores a `send.py` with no approval gate
   (MC §5.8).
3. `jura-growth publish queue`: settle any `claimed` or `unknown` item with
   `jura-growth publish resolve A-nnnn not-posted` (or `posted --url <the post's address>` for a
   post) after checking the account.
4. To cut Dispatch off, remove the line from `~/.ssh/authorized_keys` or turn Remote Login off.
   Requests stay pending and lapse.

### Revert the merge

1. With this release still checked out: `jura-growth schedule uninstall publish one-pager`. After a
   revert, `main` has no such jobs, and their plists would fail at every slot.
2. On a branch from `main`: `git revert -m 1 <merge commit>` (the PR's merge commit; the branch
   range is `855e48c..0354503`, first commit `1acc1eb`). `main` is protected, so it goes in as a PR.
3. After it merges: `uv sync`, then `jura-growth schedule install` so the plists match `main`.
4. Remove the PAUSE file.

### What a revert leaves behind

- **Database.** Seven migrations stay applied: `core/0003_approvals`, `core/0004_approval_cards`,
  `app-factory/0002` to `0004`, `community/0003_joined_as_the_page` and
  `publish/0001_publish_items`. None drops data except `app-factory/0003`, which rebuilds
  `app_prds` with every row and id kept. `main`'s code ignores the new tables and columns. Checked
  today: a database built at `main`, migrated by this branch, then opened by `main` again runs
  `status`, `community groups` and `outreach status` without error. Re-merging later applies
  nothing twice.
- **Things already done can't be undone:** posts published, groups joined and answers submitted,
  emails sent, app releases merged into `landing-page` `main`. Delete posts or leave groups by hand
  on the platform.
- **Files moved by decisions stay moved:** PRDs in `prd/skipped/apps/` and `prd/done/apps/`.
- **Discord cards keep their last state.** Pending cards in `#approvals` never update again; delete
  them or ignore them.
- **Publish transcripts hold page text** and fall back under the 30-day rule instead of 7 days.
  Delete the `*-publish.jsonl` files under `data/growth/transcripts/` by hand.
- **Community drafts go back to your personal voice** (`post_as`), and Terminal decisions and
  `community set promo_days=…` come back.
- **Outside the repo, nothing reverts:** the Chrome profile and its sign-ins, Tailscale, Remote
  Login, Dispatch's bindings, the Cowork morning-brief line (its old block is in the guide's
  history), and the landing page's D1 table, `dev` branch and Cloudflare Access.
