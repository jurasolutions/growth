# Browser publishing: the Jura Chrome profile, and the checks before anything posts

*Browser publishing, ticket BP-01. About an hour, plus the rehearsal. Drafted for BP-01 step 1; the
release copies it to `outputs/growth/setup/browser-publishing.md`.*

The `publish` job posts approved items through Claude in Chrome: one item per run, only after you
approve its card in `#approvals`, and only between 09:00 and 18:00 SGT. It drives whichever Chrome
profile the extension last connected to, and no code can choose that profile for it. So the profile,
its sign-ins and the checks below are yours. Nothing posts until you switch a platform on in the
last section, and every switch ships off.

Below, `<repo>` means the growth repo's full path on this Mac:
`/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth`. The rules behind this guide are
in BP §4.7 and §4.9 and in ADR 0005 (`docs/adr/0005-browser-automation-runs-only-in-the-publish-job.md`).

**The risk you accepted (BP §4.1).** Meta's and LinkedIn's terms forbid automated posting. Your
approval controls what is said, not whether a platform treats the account as automated. The
platforms can warn, restrict or disable the Page, the company page, or the personal profiles that
administer them. The limits in this build slow the accounts down; they don't make the automation
compliant.

## 1. Make the dedicated Chrome profile (TY4)

1. In Chrome, add a new profile from Chrome's profile menu. Name it so you
   can't mistake it, for example **Jura publishing**. Don't sign it in to a Google account, and
   turn sync off if Chrome offers it: a synced profile pulls in bookmarks, passwords and sign-ins
   from elsewhere.
2. Use this profile for nothing else. No everyday browsing, no other tabs left open in it.
3. In this profile, sign in to these three accounts and nothing else:
   - the Facebook account that administers the **Jura Solutions** Page (`facebook.com/jurasolutionssg`);
   - the Jura Instagram account, `@jura_solutions`;
   - the LinkedIn account that administers the Jura company page.
4. Never sign this profile in to Discord, Gmail, any TaskWise or ZenexFlow account, a bank, or
   anything else. A run that misbehaves can reach only what this profile is signed in to.
5. Let Chrome remember these sign-ins (stay signed in). The run never types a password or a code:
   a login wall stops it ("After a stop alert", at the end).

### Act as the Jura Page on Facebook

The run never switches who it posts as. Its prompt says to stop rather than use any "switch
profile" or "switch to Page" control (`prompts/publish.md`). So leave Facebook, in this profile,
already acting as the Jura Solutions Page, not as your personal profile:

1. Open `https://www.facebook.com/jurasolutionssg` in the profile.
2. Use Facebook's own control to switch to the Page, so the account menu and the composer show the
   Page's name and picture.
3. Facebook's menus change often, so this guide doesn't name them. When you do this, note what you
   saw: where the switch is, what the composer shows when it is acting as the Page ("Create post"
   with the Page's name and picture, or something else), and what it shows on a group's composer.
   Write it down with your R1 results. The run checks for exactly this before it types anything
   (R6 rehearses the mismatch), so a note now saves a confusing first stop.

Groups work the same way (TY1): joins and posts go out as the Page, only in groups that allow
Pages. A group that only allows personal profiles is skipped for good.

### Instagram and LinkedIn

- **Instagram:** the profile must be signed in as `@jura_solutions` only. If Instagram offers to add
  or switch to another account, decline. The run stops on a "Switch accounts" prompt rather than use
  it.
- **LinkedIn:** the run posts from the company page's admin view, never from your personal feed.
  Open the company page's admin view once in this profile and check that you can start a post as the
  company there. Note what the composer shows (the company's name and logo), with your R1 results.

Instagram and LinkedIn come after Facebook (BP §5.1): set them up now, but switch them on later, one
at a time (section 7).

## 2. The Claude in Chrome extension, in this profile only

1. In the dedicated profile, install the Claude in Chrome extension and sign it in to the **same
   claude.ai account and organisation** as Claude Code on this Mac. A different account or
   organisation gives "Browser extension is not connected" and nothing runs.
2. In every other Chrome profile, disable or remove the extension (`chrome://extensions` in that
   profile). The spike found two extension instances connected to your account; after this step
   there should be one.
3. Leave the extension's own site settings at their defaults. The job's permissions come from
   Claude Code's rules (section 3), and the job never gives the extension a per-site prompt to
   answer. If a rehearsal run shows a tool error that comes from the extension rather than from
   Claude Code's rules, note it with your R1 results.
4. Check how Claude Code is signed in: `claude auth status` should show `"authMethod": "claude.ai"`.
   Never give the scheduled runs an API key or a `setup-token`. With `ANTHROPIC_API_KEY` or
   `CLAUDE_CODE_OAUTH_TOKEN` set, the Chrome tools vanish silently, so the job's precheck skips and
   `jura-growth status` lists it as a setup gap.

### Pick the profile once in `/chrome` (U9)

In an interactive Claude Code session, type `/chrome`, choose **Select browser…**, and pick the
extension in the dedicated profile. Scheduled runs connect to the last browser picked, so you do
this once, and again only if you pick another browser later. Record U9 as passed when the dedicated
profile is the one picked.

## 3. The domain rules: what the job may open

You don't write these rules. The publish plug-in builds them for each run
(`jura_growth/agents/publish/scope.py`), and nothing in config can add a host or a tool.

- **Tab tools by name:** `tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp` and
  `list_connected_browsers`. They open and list tabs, never read a page.
- **Page tools only through `ClaudeInChromeDomain(<host>)` allow rules**, one per host of each
  platform in `browser` mode (`hosts.BROWSER_HOSTS`):

  | Platform | Hosts |
  | --- | --- |
  | Facebook (the Page, and groups while `community.browser` is on) | `www.facebook.com`, `facebook.com`, `m.facebook.com`, `web.facebook.com`, `business.facebook.com` |
  | Instagram | `www.instagram.com`, `instagram.com` |
  | LinkedIn | `www.linkedin.com`, `linkedin.com` |

  No page tool is allowed by name, because a tool-name allow covers every site. No Discord host is
  ever on the list. The list stays explicit until U18 (section 4) shows how the rule treats
  subdomains.
- **Denied by name:** the scripting, network, console, shortcut, recording, browser-switching,
  batch and resize tools, `upload_image`, web search and web fetch.
- **`file_upload`:** denied unless the item the run would claim has an image. When it has one, the
  domain rule allows `file_upload` on that platform's hosts, and the audit checks that every upload
  is one of the claimed item's own image copies. **Still to be recorded:** R1b asks whether Claude
  Code honours a parameter allow rule that limits `file_upload` to files in `work/publish/`. Its
  result goes in the Comments of `.scratch/browser-publishing/issues/07-fixture-platform.md`, and
  BP-07 can't close until it is there.

To see the rules a run would get, without running it: `uv run jura-growth run publish --dry-run`
in `<repo>` prints the argv. After every run the audit reads the transcript and fails the run, and
pauses `publish`, on any host outside the list, any Discord host, a tab the run didn't create, or
typed text that isn't in the approved content.

## 4. The spike's open checks (U10, U11, U18)

These run real Claude and cost a little each (about US$0.10 to US$0.40). Record each as pass or
fail, with a note, in BP §5.1 under "The spike's answer", and in
`.scratch/browser-publishing/reviews/qa-01.md`.

The probes run in a scratch folder with the runner's own flags. Set up a small helper once, in a
Terminal window:

```bash
PROBE="$(mktemp -d)"
probe() {  # probe <name> <domain rule> <prompt>
  printf '%s\n' "$3" > "$PROBE/$1.txt"
  (cd "$PROBE" && claude -p --output-format stream-json --verbose --permission-mode dontAsk \
    --strict-mcp-config --setting-sources project --no-session-persistence --max-budget-usd 0.40 \
    --model sonnet --chrome \
    --allowedTools mcp__claude-in-chrome__tabs_context_mcp mcp__claude-in-chrome__tabs_create_mcp \
      mcp__claude-in-chrome__tabs_close_mcp "ClaudeInChromeDomain($2)" \
    --disallowedTools mcp__claude-in-chrome__javascript_tool mcp__claude-in-chrome__computer \
      mcp__claude-in-chrome__form_input mcp__claude-in-chrome__file_upload Bash \
    < "$PROBE/$1.txt" > "$PROBE/$1.jsonl")
  tail -1 "$PROBE/$1.jsonl"
}
```

The last line it prints is the run's result; its `permission_denials` lists every call that was
denied.

- **U10. Signed in to nothing else, and an unlisted domain is denied.**
  1. In the dedicated profile, check you are signed in to the three Jura accounts only: not
     Discord, Gmail, TaskWise or ZenexFlow.
  2. Run:

     ```bash
     probe u10 example.com "Use only the Chrome tools. Call tabs_context_mcp with createIfEmpty true, open a new tab with tabs_create_mcp, and navigate it to https://example.com. Then navigate the same tab to https://example.org. Close the tab. Report, for each navigation, whether it was allowed or denied. Read nothing from the pages, and click and type nothing."
     ```

  3. Pass when the `example.com` navigation was allowed and the `example.org` one is in
     `permission_denials`.
- **U18. How the domain rule treats subdomains.** Two probes, each opening one Facebook address and
  reading nothing from it, so no page text lands in the transcript:

  ```bash
  probe u18a www.facebook.com "Use only the Chrome tools. Call tabs_context_mcp with createIfEmpty true, open a new tab with tabs_create_mcp, and navigate it to https://m.facebook.com/. Close the tab. Report whether the navigation was allowed or denied. Read nothing from the page, and click and type nothing."
  probe u18b facebook.com "Use only the Chrome tools. Call tabs_context_mcp with createIfEmpty true, open a new tab with tabs_create_mcp, and navigate it to https://www.facebook.com/. Close the tab. Report whether the navigation was allowed or denied. Read nothing from the page, and click and type nothing."
  ```

  Record for each whether the navigation was allowed or denied. The first says whether a rule for
  one subdomain covers a sibling, the second whether a rule for the bare domain covers its
  subdomains. That fixes the host lists in section 3 (BP-03, BP-04, BP-05).
- **U11. The locked screen, and Chrome closed.** Both use the rehearsal's fixture site and UAT
  folder (`uat.md` Part R, "The window"), so nothing real is touched. Run them between 09:00 and
  18:00, the posting window.
  1. *Chrome closed.* `rehearse fixture-post page.html`, quit Chrome, then
     `uv run jura-growth run publish --ignore-schedule`. Pass when the run ends `SKIP:` within a few
     minutes, without hanging, and `uv run jura-growth publish queue` still shows the item approved
     and unclaimed. Open Chrome again.
  2. *Locked screen.* `rehearse fixture-post page.html`, then
     `caffeinate -i sh -c 'sleep 60 && uv run jura-growth run publish --ignore-schedule'` (this keeps
     the Mac awake while it waits and runs, but lets the display sleep). Lock the screen at once
     (Control-Command-Q) and leave it locked for ten minutes. Pass when `publish queue` shows the
     item done with the fixture URL. If it isn't, note what the transcript shows.

## 5. Keep the Mac logged in and awake, 09:00 to 18:00

The job is scheduled every 20 minutes from 09:00 to 17:40. Asleep, nothing runs, and launchd runs a
missed slot once on wake. Logged out, nothing runs at all: the job is a LaunchAgent and needs your
session, and Chrome needs it too.

1. Stay logged in. Locking the screen is fine once U11 passes; logging out is not.
2. In System Settings, set the Mac not to sleep on its own while it is on power. The setting's name
   and place differ between macOS versions and between laptops and desktops, so look for the one
   that prevents automatic sleeping when the display is off.
3. Keep Chrome open, with the dedicated profile's window open. If Chrome is closed or the extension
   isn't connected, a run ends `SKIP:` without claiming anything, the item stays approved until its
   deadline, and one alert a day says so.

## 6. The rehearsal on the fixture site (R1 to R6)

The rehearsal runs the real publish job, with its real prompt, `--chrome` and audit, in the
dedicated profile, against local fixture pages. The fixture platform makes
`ClaudeInChromeDomain(publish-fixture.localhost)` the run's only domain rule, so even though the
profile is signed in to Facebook, the run can't reach it. The exact commands are in
`.scratch/mission-control/uat.md` Part R. What each step proves:

| Step | What it checks | Before |
| --- | --- | --- |
| R1 | An approved post end to end: one new tab, the composer showing the Page, the approved text typed once and whole, the image attached, Post clicked once, the permalink read back, `publish done`, the tab closed | U12, and again per new platform |
| R1b | Record only: whether a parameter allow rule can limit `file_upload` to `work/publish/` (section 3) | BP-07 closing |
| R2 | Each stop page (login, CAPTCHA, checkpoint, rate limit, removal, admin warning): `publish stopped` with the right reason, nothing clicked after it | U12, and again per new platform |
| R3 | A link to another site: no navigation there, or the call denied and the audit failing the run | U12 |
| R4 | The injection page: no Discord visit and no decision recorded | U12 |
| R5 | Membership questions: answers drafted, the form closed unsubmitted, a second card; after you approve it, exactly those answers submitted. A profile-only group is skipped | U15 (joins) |
| R6 | A different identity on the page: `publish stopped --reason wrong-identity` before anything is typed | U12, and again per new platform |

Run R1 to R4 and R6 (with R1b) before the first live Facebook post, R1, R2 and R6 again for each new
platform, and R5 before the first join. Record each in `uat.md` and keep the transcripts as the
script says.

## 7. Switching a platform on

Turn on one platform at a time, Facebook first, and only when its checks are recorded as passed
(the go-live gates in `.scratch/mission-control/reviews/quality-gate.md`):

| Before turning on | These must be recorded as passed |
| --- | --- |
| Facebook's `publish_mode: browser` | U9, U10, U11, U18, then R1 to R4 and R6 (with R1b), then U12 |
| Instagram's or LinkedIn's `publish_mode: browser` | R1, R2 and R6 for that platform, BP §6 answered again, then U13 |
| `community.browser: true` | R5, then U14 and U15 |

1. In `<repo>/config/social.yaml`, under the platform, set `page_url` to the page the run posts to
   (`https://www.facebook.com/jurasolutionssg` for Facebook, `https://www.instagram.com/jura_solutions/`
   for Instagram, the company page's `https://www.linkedin.com/company/<page>/` for LinkedIn), then
   change `publish_mode: draft` to `publish_mode: browser`. Without `page_url`, drafts keep going
   to `#social-drafts` for you to post by hand.
2. For groups, set `browser: true` in `<repo>/config/community.yaml`.
3. If the `publish` job isn't installed yet: `uv run jura-growth schedule install publish`.
4. From then on, each draft that passes the brand gate gets its own card in `#approvals`. Nothing
   posts until you approve it, and an unanswered card expires at 18:00 on its day.

## Pausing and switching off

| To | Do |
| --- | --- |
| Stop every growth job at once | `touch <repo>/PAUSE`. Remove the file to let them run again |
| Stop publishing only | `/growth pause publish <reason>` in `#control`, or `uv run jura-growth pause publish` on the Mac |
| Start it again | `/growth resume publish`, or `uv run jura-growth resume publish`. Only you can: a headless run is refused |
| Go back to posting one platform by hand | `publish_mode: draft` for it in `config/social.yaml` |
| Stop group joins and posts | `browser: false` in `config/community.yaml` |
| Remove the job from the schedule | `uv run jura-growth schedule uninstall publish` |
| Cut the browser off entirely | Disable the extension in the dedicated profile, or quit Chrome |

While any of these is on, approved items aren't claimed. They stay approved until their deadline,
and post if you lift the switch in time. Nothing else in the engine depends on the job.

**After a stop alert.** A login wall, CAPTCHA, checkpoint, warning, removal notice, wrong identity,
or anything the run can't identify stops it at once, marks the item `stopped`, pauses `publish` and
posts the reason and the run id to `#alerts`. Look at the page yourself in the dedicated profile,
fix what it shows by hand (sign in again, clear the check, or leave the group alone), then
`/growth resume publish`. A removal or an admin warning in a group also sets that group to skip for
good.

**An item left `unknown`.** If a run ends with a claimed item neither done nor stopped, the item
becomes `unknown`, `publish` pauses, and `#alerts` asks you to settle it. Check the page, then send
`/growth publish resolve A-nnnn posted --url <the post's address>` or
`/growth publish resolve A-nnnn not-posted`. An `unknown` item is never claimed again.
