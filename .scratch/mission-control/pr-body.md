## Summary

This adds mission control and browser publishing to the growth engine, on one branch, against the two signed-off PRDs: `prd/pending/prd-jura-mission-control-2026-10-25.md` and `prd/pending/prd-jura-browser-publishing-2026-10-25.md`, read with their 2026-10-26 and 2026-10-27 amendments. The tickets, reviews and decisions are in `.scratch/mission-control/` and `.scratch/browser-publishing/`. The full release notes, with every after-merge step and the rollback, are in `.scratch/mission-control/release-notes.md`.

**Everything outward waits for your approval in Discord.** That covers social posts, community posts, group joins and their answers, app builds, app releases and outreach emails. Group rules and open days are confirmed the same way. **Decisions come in only through the SSH forced command** that Dispatch calls. Terminal and every headless run are refused.

How an outward action runs now:

```text
a job drafts something outward (email, post, join, app build, release, group rules)
  approvals.raise(kind, subject, exact bytes)      # A-nnnn card in #approvals: what, why, decide-by
  ... you answer in Discord ...
  Dispatch -> ssh -> bin/growth-remote             # forced command; shlex split, execv, no shell
    jura-growth remote approve|skip A-nnnn
      origin.detect_ssh()                          # forced-command variable, root sshd ancestor, no claude ancestor
      approvals.decide()                           # the only writer of 'approved'; actor discord:<your id>
  the gated action, at its next slot
    BEGIN IMMEDIATE
      approvals.use(A-nnnn)                        # recomputes the bytes; changed -> superseded, new card
    the effect                                     # Resend send, Chrome post or join, merge plan
  silence -> the request lapses; never a yes
```

What gets added:

```diff
 jura_growth/
+  approvals.py, approvals_cli.py, cards.py      # the approval contract (ADR 0003), cards in #approvals
+  origin.py, remote.py                          # decisions only from a human origin (ADR 0004)
+  mission.py, one_pager.py, health.py, slots.py # 08:00 one-pager and the 14-day grid (ADR 0001, 0002)
+  run_update.py, privacy.py                     # one run update per run; masking for everything in Discord
   agents/
+    publish/                                    # browser job: claim, audit, fixture platform (ADR 0005)
     outreach/  +approval.py                     # every email needs a claimed approval
     apps/      +builds.py, +releases.py         # app-build and app-release kinds
     community/ +group_rules.py                  # rules and days confirmed in Discord; joins as the Page
+bin/growth-remote                               # the SSH forced command
+config/publish.yaml                             # window 09:00 to 18:00, 20-minute gap, 1 item a run
+prompts/publish.md
+docs/dispatch-contract.md, docs/adr/0001..0005
 config/settings.yaml
+  jobs: one-pager (08:00 daily), publish (09:00 to 17:40 every 20 min, daily)
```

Seven new migrations, all forward-only. Only `app-factory/0003` rewrites a table: it rebuilds `app_prds` so a slug can be reused, keeping every row and id.

```diff
+core/0003_approvals.sql          core/0004_approval_cards.sql
+app-factory/0002_app_builds.sql  app-factory/0003_app_prds_slug_reusable.sql  app-factory/0004_app_builds_release.sql
+community/0003_joined_as_the_page.sql
+publish/0001_publish_items.sql
```

## Evidence

- **Before:** `main` (855e48c) is the blocker-fix release, whose suite recorded 987 passed. Emails in live mode would send with no review, nothing posts on social platforms, and `jura-growth approve` doesn't exist.
  **After:** on this branch (0354503), `uv run pytest -rs -p no:cacheprovider -o addopts=""` gives **3305 passed, 0 skipped, in 146s**, with `JURA_ROOT` set and temp data and outputs folders. The live `growth.db` was untouched (same mtime before and after), and `git status` was clean.

```text
                                                main                       this branch
outreach email in live mode                     sends at its slot          sends only after an approval of its exact text is claimed
email text edited after you approved it         n/a                        old card superseded, new card, nothing sends
request left unanswered                         n/a                        lapses at its decide-by; never counts as yes
jura-growth approve A-0001 in Terminal          no such command            refused: decisions aren't taken in Terminal (exit 2, run today)
JURA_GROWTH_JOB=social jura-growth approve      no such command            refused: a `social` run may not use it (exit 2, run today)
ssh key, command '-- status; touch /tmp/x'      n/a                        refused; /tmp/x not created
publish run sees a login wall or other identity n/a                        stops before typing, pauses publish, one #alerts post
publish run killed mid-claim (final Sp1)        n/a                        next run settles it unknown, pauses, claims nothing
FAIL: [approve here](https://evil.test) ```     n/a                        escaped in run updates and the one-pager (final Sp2)
```

- **Upgrade and rollback path.** A database built with `main`'s code, migrated by this branch, then opened by `main`'s code again runs `status`, `community groups` and `outreach status` without error. All 16 migration ids are recorded once.
- **Reviews.** Every ticket was reviewed. The final review of the merged branch (`.scratch/mission-control/reviews/code-review-final.md`) approves with follow-ups and found no blocker on standards, spec or security. Its should-fix findings (Sp1, Sp2, Sp3, St1, St2, St3, St8) are fixed in 8d6640e. Nine ticket reviews end on changes-requested, and their fix rounds were verified by the conductor with the reviewers' repros, as recorded in the crew-log. `.scratch/mission-control/reviews/release.md` lists them.
- **Quality gate:** _QA lead's verdict to be added here (`.scratch/mission-control/reviews/quality-gate.md`)._
- No blocked path changed (`inputs/`, `design-system/`, `.env`, `data/growth`, `.github`). The secrets scan of the added lines found only test fixtures and the planted UAT value.

## Release notes

**Nothing outward changes by merging.** Outreach stays in `shadow`, every platform stays in `draft`, community `browser` is false, and the three `approvals` switches are false.

What changes as soon as you reinstall the schedule:

1. Two new jobs: `one-pager` at 08:00, and `publish` every 20 minutes from 09:00 to 17:40, every day. While every platform is in `draft`, `publish` skips without starting Claude.
2. Terminal can't decide anything. Until Dispatch is live, requests post and then lapse unanswered.
3. The five app PRDs in `prd/pending/apps/` each get an `app-build` request at the next factory run. Unanswered for 7 days, a PRD moves to `prd/skipped/apps/` and its idea rests for 30 days. To keep them, run `jura-growth pause app-factory` until Dispatch works.
4. Group open days are typed only in a `group-rules` decision in Discord. `community set` no longer takes `promo_days=` or `post_days=`. Groups you already confirmed keep their days.
5. Community drafts are written as the Jura Facebook Page.

What you do after merging, in this order. `release-notes.md` has the detail and each check:

1. **The Mac.** `uv sync`. Keep the Mac awake and logged in (`sudo pmset -c sleep 0`, a 06:15 `pmset repeat wakeorpoweron`, `autorestart 1`). **Delete the frozen-clock social rows** (the 2026-10-26 and 2026-10-24 test drafts, `runs` row 5, `outputs/growth/social/2026-10-26/`) **before you install the social job.** Keep any Anthropic API key or setup token out of the launchd environment.
2. **Ticket mc 13.** Add `#mission-control` and `#approvals`. Set the two new values, **`DISCORD_WEBHOOK_APPROVALS` and `DISCORD_WEBHOOK_MISSION_CONTROL`**, plus `CONTROL_DISCORD_USER_ID`, in `.env`. Run `jura-growth schedule install`, remove the morning-brief line, and run U1 to U5.
3. **Ticket mc 14.** Deploy Dispatch (D1 to D4, D8, D9). **Turn on Remote Login** (your user, keys only) and **Tailscale** on both machines, add the single `authorized_keys` entry, bind `#approvals` and `#control`, then run U16, U7 and the asleep-Mac check.
4. **UAT Parts A to C** in `.scratch/mission-control/uat.md`, on a test server with a UAT-only key.
5. **Ticket bp 01.** **Create the Jura Facebook Page** (and check the Instagram account and LinkedIn company page). **Create the dedicated Jura Chrome profile**, signed in only to those three, and pick it in `/chrome`. Run U9, U10, U11 and U18.
6. **R1 to R6**, then **ticket bp 07** after your R1b: record both probe results in its Comments. Record the Facebook permalink shape on bp 01.
7. **Live posts.** Set Facebook to `browser` with its `page_url`, then **U12**. Instagram and LinkedIn follow, then community `browser: true` and **U14** and **U15**. U14 also records the permalink segment form.
8. **Ticket mc 15.** **Deploy Dispatch with buttons** (D5), store its own `#approvals` webhook, set `post_buttons`, then run U17, then `discord_buttons`. Before live outreach: **a legal view on the Spam Control Act**, then `legal_review_done: true`. **Resend and DNS**: verify the sending domain, create the sending-only key, set `UNSUBSCRIBE_SECRET` in growth and Pages, and create the From mailbox. **Make the landing-page D1 `suppression` table append-only, and start it empty, before you set the D1 secrets.** Add `inputs/do-not-contact.csv`. Then `outreach.mode: live` and U6.
9. **Ticket mc 16.** Merge the landing page's `toolbox` branch. **Give `landing-page` a `dev` branch behind Cloudflare Access**, together with every `*.pages.dev` preview. **Set `pages_project` in `config/apps.yaml`**, check Dispatch D6, set `dispatch_builds`, then run U8.
10. **After acceptance.** Copy `.scratch/mission-control/setup/*.md` to `outputs/growth/setup/`, because the copies there are older. Move both PRDs to `prd/done/`.

Two gaps found while preparing the release: the browser-publishing setup guide that bp 01 names was never drafted, and the exact UAT `authorized_keys` line (`uat.md` step 4) isn't written down yet.

## Known limits

- **Facebook profile identity is prompt-only.** The Chrome profile is your own account, which administers the Page, so code can't rule out a post or join as your personal profile. The guards are the identity check in the prompt, the wrong-identity stop, R5, R6 and U15.
- **Posts held for admin approval stop as unidentified** and pause publishing until U14 shows how often that happens.
- **The permalink group segment form is checked in U14.** If Facebook links a post through a different group segment from the register's URL, the item goes `unknown`. `uat.md` D5 says how to settle it.

## Follow-ups outside this change

- **St4.** Publish item kinds are switched on in several places. Add one per-kind table if a fifth kind comes.
- **St5.** The `app-build` use-by can never be reached. Drop the cap and its config key, or say why they stay.
- **St6.** The `NotApproved` docstring doesn't list every reason it is raised with.
- **St7.** `caps.py` says "publish window" where CONTEXT.md says "posting window", and times reach Discord in three formats.
- **Sp4.** The schema still accepts a `terminal` origin, and `use()` doesn't check the origin. Add a refusal and a trigger in a later migration.

## Merge danger

**Door:** two-way, as long as you switch outward actions off first

Reverting the merge restores the old engine. Before you revert, set `outreach.mode: shadow`, because the revert brings back a `send.py` with no gate. Set every platform back to `draft` and community `browser: false`, and settle any claimed or unknown publish item. Then run `jura-growth schedule uninstall publish one-pager`, and `git revert -m 1 <merge commit>` as a PR (the range is `855e48c..0354503`). After that, `uv sync` and `schedule install`. To stop everything in the meantime, `touch repos/growth/PAUSE`.

The seven migrations stay in `growth.db`, and `main`'s code ignores them (checked above). The new launchd jobs have to be uninstalled by hand, as above. What a revert can't undo: posts already published, groups joined, answers submitted, emails sent, app releases merged into `landing-page`, PRDs moved by decisions, and the setup outside the repo (Chrome profile, Remote Login, Tailscale, Dispatch).

**Blast radius:** public, once you switch it on

On merge, the change reaches only your Mac and Discord: new channels, two new jobs, and requests that lapse until Dispatch is live. After your steps, it posts on Jura's real Facebook, Instagram and LinkedIn accounts and in Facebook groups, and it sends real email. Each of those happens only after you approve that exact item, within the caps in `caps.py`. The accounts themselves carry the risk the PRD accepts (BP §4.1): Meta or LinkedIn may restrict an account that's driven through a browser.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
