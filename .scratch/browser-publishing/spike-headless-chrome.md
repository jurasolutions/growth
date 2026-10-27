# Spike: can a scheduled `claude -p` run drive Claude in Chrome?

_Infra persona, 2026-10-25. Read-only spike: nothing was installed, enabled or reconfigured, and no repo code changed. Every probe touched example.com only._

## Setup observed on this Mac

| Item | Observed | Evidence |
|---|---|---|
| Claude Code | 2.1.310 at `~/.local/bin/claude` (on the launchd PATH in `jura_growth/schedule.py`) | `claude --version` |
| Auth | claude.ai OAuth (subscription login), first-party | `claude auth status` -> `"authMethod": "claude.ai"` |
| Chrome | Running (`Google Chrome --restart`, started 2026-10-24 22:20) | `ps` |
| Extension | Claude in Chrome 1.0.102, **two** extension instances connected to the account | debug log `extensions_list` (device ids redacted) |
| Native host | `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.anthropic.claude_code_browser_extension.json` present, points at `~/.claude/chrome/chrome-native-host` | `cat` of the manifest |
| User config | `claudeInChromeDefaultEnabled: true`, onboarding complete (in `~/.claude.json`) | `grep` for Chrome keys only |
| Repo | No `.claude/settings.json` in `repos/growth` | `ls .claude/` -> `worktrees` only |

All probes used the runner's own flags from `jura_growth/runner.py` `claude_command`: `-p --output-format stream-json --verbose --permission-mode dontAsk --strict-mcp-config --setting-sources project --no-session-persistence --max-budget-usd <n>`, run from a scratch folder. Total spend across six probes: about US$0.33.

## 1. Which flag makes the Chrome tools available

**`--chrome` on the command line. Nothing else works for `-p`, and it is compatible with `--strict-mcp-config`.**

Same runner flags, with and without `--chrome`, allow rule `mcp__claude-in-chrome__*`:

```
nochrome exit=0   mcp_servers: []   chrome tools: []
chrome   exit=0   mcp_servers: [{'name': 'claude-in-chrome', 'status': 'connected', 'source': 'dynamic'}]
                  chrome tools: [browser_batch, computer, file_upload, find, form_input, get_page_text,
                  gif_creator, javascript_tool, list_connected_browsers, navigate, read_console_messages,
                  read_network_requests, read_page, resize_window, select_browser, shortcuts_execute,
                  shortcuts_list, switch_browser, tabs_close_mcp, tabs_context_mcp, tabs_create_mcp, upload_image]
```

- The server is in-process (`source: dynamic`), so `--strict-mcp-config` does not drop it and no `--mcp-config` file is needed. Debug log: `MCP server "claude-in-chrome": In-process Chrome MCP server started`.
- "Enabled by default" does **not** carry into `-p`. Even without `--strict-mcp-config` and with every MCP source loaded, a plain `claude -p` listed 0 Chrome tools.
- A project can't switch it on. The docs say Claude Code ignores `CLAUDE_CODE_ENABLE_CFC` in project settings ("a repository you check out must not be able to connect Claude to your browser"). With `--setting-sources project`, the runner's argv is the only lever, which is the right place for it.
- **Auth condition.** The docs say Chrome integration needs a `/login` (OAuth) session: "If you authenticate with an API key or a long-lived token from `claude setup-token`, Claude Code keeps Chrome integration off, even when you pass `--chrome`." The runner passes `os.environ` through and launchd sets only `PATH`, so a scheduled run uses the same keychain OAuth login as the probes. Setting `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` for headless runs later would silently remove the browser tools.
- **Code gap.** `claude_command` has no way to add `--chrome` today. A job spec key such as `chrome: true` would need to add the flag, and only for jobs that need it, because the tools add context to every run.

## 2. What it needs at run time, and what happens when Chrome is closed or the Mac is locked

How the connection works (debug log from probe 3, ids redacted):

```
[Claude in Chrome] Connecting to bridge: wss://bridge.claudeusercontent.com/chrome/<user-id>
[Claude in Chrome] Paired with Chrome extension (duration: 353ms)
[Claude in Chrome] Auto-connecting to the last-picked extension: <device-id>
[Claude in Chrome] Sending tool_call: "tabs_context_mcp"
```

The CLI does not talk to Chrome through a local socket. It pairs with the extension through Anthropic's cloud bridge, matched by the claude.ai account. So:

| Condition | Needed? | Basis |
|---|---|---|
| Chrome running, with the extension enabled | **Yes.** With Chrome closed, the docs give "No browsers are connected" ("Chrome isn't open with the extension signed in to the same claude.ai account and organization"). `claude -p` itself still starts ("Claude Code starts normally when Chrome isn't running"), so the run fails at its first browser call, not at launch. | Docs, "Common error messages". Not reproduced: closing Chrome would disrupt your session. |
| Extension signed in to the **same account and organisation** as the CLI | **Yes.** A mismatch gives "Browser extension is not connected". Today they match: pairing succeeded. | Docs; probe 3 log `Paired`. |
| Network access to `bridge.claudeusercontent.com` | **Yes.** | Debug log; docs. |
| Logged-in GUI session | **Yes, indirectly.** The plist installs into `gui/<uid>`, and LaunchAgents only run while you are logged in. Chrome also needs a logged-in user. The OAuth credential is read from the login keychain. | `schedule.py` `_domain()`; macOS behaviour. |
| Screen unlocked | **Not required for the connection.** The bridge is a websocket, so locking the screen does not drop it. **Untested:** whether `computer` screenshots and clicks work on an occluded or locked display. Chrome may throttle a hidden window, and the extension's service worker can go idle ("Receiving end does not exist"). | Inferred from architecture; docs, "Connection drops during long sessions". |
| Mac awake | **Yes.** Asleep, nothing runs. launchd runs a missed `StartCalendarInterval` job once on wake. | macOS behaviour. |
| A browser already chosen | **Yes, when more than one extension instance is connected.** Two are connected now. The CLI auto-picked "the last-picked extension". With no earlier pick, the docs say "Claude prompts you to pick one", and `dontAsk` would deny that prompt. | Probe 3 log; docs, "Get started". |

Tab hygiene: every run's `tabs_context_mcp(createIfEmpty: true)` makes a new tab group holding one empty "New Tab". The probe closed its own tab, but that empty tab stayed in the group while the run lasted. The docs say the group closes when the session exits if it holds only empty new tabs. I did not check this after the runs, because listing your tabs from outside would mean reading your other tabs.

**Setup items for Ting Yu (not done, because each one changes your environment):**

1. Locked-screen test. Lock the Mac (keep it awake, for example with `caffeinate -d -t 600` in a terminal), then from a second machine over SSH, or from a one-off launchd job you install yourself, run the section 3 command with `mcp__claude-in-chrome__computer` added to `--allowedTools` and a screenshot step added to the prompt. Record whether `navigate`, `get_page_text` and the screenshot work.
2. Chrome-closed test. Quit Chrome, run the section 3 command, and confirm the error text and that the run ends with `FAIL:` and does not hang.
3. Decide which Chrome profile the engine drives. Two extension instances are connected. A dedicated profile, signed in only to the accounts the engine may post as, limits what a misbehaving run can reach. Pick it once in `/chrome` -> "Select browser…" so `-p` runs auto-connect to it.
4. Energy settings: keep the Mac from sleeping at the scheduled slots (`pmset` schedule or "Prevent automatic sleeping").

## 3. The harmless probe

Command (prompt file asked for: get a tab group, open a new tab, navigate to https://example.com, read the title, close the tab; no clicks, no typing, no scripts):

```bash
claude -p --output-format stream-json --verbose --permission-mode dontAsk --strict-mcp-config \
  --setting-sources project --no-session-persistence --max-budget-usd 0.40 --model sonnet --chrome \
  --allowedTools mcp__claude-in-chrome__tabs_context_mcp mcp__claude-in-chrome__tabs_create_mcp \
    mcp__claude-in-chrome__navigate mcp__claude-in-chrome__get_page_text mcp__claude-in-chrome__read_page \
    mcp__claude-in-chrome__tabs_close_mcp \
  --disallowedTools mcp__claude-in-chrome__javascript_tool mcp__claude-in-chrome__file_upload \
    mcp__claude-in-chrome__upload_image Bash \
  < prompt.txt > probe.jsonl
```

Output (tool calls and results, trimmed):

```
exit=0
INIT chrome tools 19, javascript_tool present: False, file_upload present: False
CALL mcp__claude-in-chrome__tabs_context_mcp {"createIfEmpty": true}   -> ok, new tab group, 1 empty tab
CALL mcp__claude-in-chrome__tabs_create_mcp {}                          -> ok "Created new tab."
CALL mcp__claude-in-chrome__navigate {"url": "https://example.com"}    -> ok "Navigated to https://example.com/"
CALL mcp__claude-in-chrome__get_page_text {}                            -> ok "Title: Example Domain"
CALL mcp__claude-in-chrome__tabs_close_mcp {}                           -> ok "Closed tab ... 1 tab(s) remain."
FINAL TITLE=Example Domain CLOSED=yes | cost 0.0786 | denials []
```

The extension needed no setup and showed no per-site prompt (see 4). Nothing was missing.

## 4. Can `dontAsk` plus an allowlist scope the Chrome tools?

**Yes, at three levels, and every unapproved call is denied without hanging.**

| Mechanism | Probe | Result |
|---|---|---|
| Bare tool deny removes the tool from the model's context | `--disallowedTools mcp__claude-in-chrome__javascript_tool mcp__claude-in-chrome__file_upload` | Probes 1 and 2: the tool is absent from `init.tools` (19 of 22 left), and a ToolSearch for it returns nothing (`JS=absent`). |
| A tool that is neither allowed nor denied is denied in `dontAsk` | `computer` screenshot on example.com, not in the allowlist (probe 3) | `"Permission to use mcp__claude-in-chrome__computer has been denied because Claude Code is running in don't ask mode."` It shows in the result's `permission_denials`, so the runner's existing denial logging catches it. |
| Parameter deny rule on an MCP tool (CLI only, exact value) | `--disallowedTools "mcp__claude-in-chrome__navigate(url:https://example.com/blocked-by-rule)"` (probe 2) | `"Permission to use mcp__claude-in-chrome__navigate with url:https://example.com/blocked-by-rule has been denied."` It matches the exact value only, so it is no use as a domain blocklist. |
| **Domain allow rule** | `--allowedTools ... "ClaudeInChromeDomain(example.com)"` with **no** allow for `navigate` or `get_page_text` (probe 4) | `NAV=allowed TEXT=allowed TITLE=Example Domain`, denials `[]`. Claude Code's own permission suggestions in the debug log use this rule form: `{"toolName": "ClaudeInChromeDomain", "ruleContent": "example.com"}`. |

So the scope for a publishing job is: allow the tab tools plus `ClaudeInChromeDomain(<the one site>)`, deny by name `javascript_tool`, `file_upload` (unless the post needs an image), `read_network_requests`, `shortcuts_execute`, `gif_creator`, `switch_browser` and `select_browser`, and keep `Bash` limited to the job's `jura-growth` commands as now. What I could not test, because it needs a second domain: whether a site outside the `ClaudeInChromeDomain` rule is denied. The `dontAsk` rule ("anything that would prompt is denied") and the domain-shaped suggestion both point to yes. Ting Yu should confirm this with a second harmless domain before any social site goes in a rule.

**The extension's own per-site prompts.** None appeared in any run. The docs say site permissions "are inherited from the Chrome extension", and Claude Code raises the per-site check itself as a permission prompt ("Claude in Chrome wants to…", with "allow all actions on that site for the session"). In `dontAsk` that prompt never shows: either an allow rule (a tool rule or a `ClaudeInChromeDomain` rule) approves the call, or the call is denied. I can't tell whether example.com was already allowed in the extension's settings, because I did not open them. If the extension itself blocks a site, expect a tool error in the transcript, not a hang. One more limit: in `dontAsk`, MCP tools marked `requiresUserInteraction` are always denied. None of the Chrome tools used here were.

## Touchpoints for a browser-publishing job

| Touchpoint | Change needed | Owner | Status |
|---|---|---|---|
| `jura_growth/runner.py` `claude_command` | Add `--chrome` only for job specs that opt in | developer | not started |
| `config/settings.yaml` job spec | `tools` takes `ClaudeInChromeDomain(<site>)` and tab tools; `disallowed_tools` takes the risky Chrome tools | developer | not started |
| Auth | Must stay claude.ai OAuth in the keychain; no API key or setup-token in the launchd environment | Ting Yu | ok today |
| Chrome plus extension | Running, signed in to the same organisation, one profile chosen | Ting Yu | running; two instances, choice pending |
| Network | Outbound to `bridge.claudeusercontent.com` | Ting Yu | ok |
| launchd and power | Logged in, awake at the slot; locked-screen behaviour unverified | Ting Yu | setup items 1, 2 and 4 |
| Secrets | None new. The probes read no `.env` and no `growth.db`. | - | ok |

Rollback for any later build: drop `--chrome` from the job (or `jura-growth pause <agent>`). The browser tools disappear and nothing else changes.

**Verdict: feasible with conditions.** You need `--chrome` in the runner's argv, an OAuth login (not an API key or setup-token), Chrome running with the extension signed in to the same organisation, one chosen browser profile, the Mac logged in and awake, and scoping through `ClaudeInChromeDomain(...)` plus named-tool denies. Locked-screen behaviour and the deny for an unlisted domain still need Ting Yu's two checks.
