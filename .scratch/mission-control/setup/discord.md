# Discord setup: "Jura HQ"

*Growth foundation, block 0, updated for mission control (ticket 09). About 15 minutes the first
time, 5 if the server is already set up. You do the clicking; the code takes it from there. Drafted
in ticket 09; the release copies it to `outputs/growth/setup/discord.md`.*

Discord is the readable feed for the growth agents. The log of record is the SQLite database in
`data/growth/growth.db`, so nothing is lost if a channel is muted or a message is deleted.
Posting is one-way: the agents post through webhooks and never read Discord. Decisions and control
commands come back only through Dispatch (`remote-control.md`).

## Already set up? Add the two mission control channels

If Jura HQ already has the eight channels from the first setup, you only need these two:

1. Create `#mission-control` and `#approvals` (step 2).
2. Give each one a webhook and put it in `.env` (steps 3 and 4).
3. Right-click `#approvals` → Notification settings → **All messages**, so each approval request
   reaches your phone.
4. Run the test (step 5).

From then on the one-pager arrives in `#mission-control` at 08:00 SGT every day, and approval
requests arrive in `#approvals`.

## 1. Create the server

1. In the Discord app, click **+** (Add a server) at the bottom of the server list.
2. **Create my own** → **For me and my friends**.
3. Name it **Jura HQ**. Skip the icon for now.

## 2. Create the channels

Create these ten text channels with exactly these names (Discord lower-cases them for you):

| Channel | What lands there |
|---|---|
| `daily-digest` | One summary per day at 17:30 SGT, plus the noon heartbeat |
| `scout-leads` | New qualified leads with score and reasons |
| `outreach-sent` | Each email sent (recipient domain, subject, first line) |
| `outreach-replies` | Replies and unsubscribes detected |
| `app-factory` | Each new app PRD with its pitch and the build command |
| `social-drafts` | Daily posts per platform, images attached |
| `community` | Weekly group posting plan and drafts |
| `alerts` | Failures, auto-pauses, brand-check rejections, cap hits |
| `approvals` | One card per approval request: what would go out, why, and when it lapses. Answer it in Discord |
| `mission-control` | The one-pager at 08:00 SGT and whenever you send `/growth one-pager`: what needs you, approvals waiting, today, yesterday, and the 14-day grid as an image |

You can delete the default `#general`.

**Notifications:**

- Right-click `#approvals` → Notification settings → **All messages**. An approval request lapses
  if nobody answers it, so this is the one channel you need to hear about straight away.
- Right-click `#alerts` → Notification settings → **All messages**.
- For the rest, choose whatever suits you. `#mission-control` posts once a morning, so
  mentions-only or muted is fine; `#outreach-replies` is the other one worth hearing about.

## 3. One webhook per channel

For each of the ten channels:

1. Hover the channel → click the gear (**Edit channel**) → **Integrations** → **Webhooks** →
   **New Webhook**.
2. Name it **Jura growth** (the agents set their own display name per post).
3. Click **Copy Webhook URL**.
4. Paste it into `repos/growth/.env` on the matching line (step 4).

A webhook URL is a password for posting into that channel. Don't paste it anywhere else. If one
leaks, delete that webhook in the same Integrations screen and make a new one.

The Approve and Skip buttons on `#approvals` cards come later, through a webhook Dispatch's own
application owns (`approvals.post_buttons`). Until then, answer a card by typing
`/growth approve A-nnnn` or `/growth skip A-nnnn` in Discord.

## 4. Put the URLs in `.env`

```bash
cd ~/OneDrive/Desktop/projects/jurasolutions/repos/growth
cp .env.example .env   # first time only
chmod 600 .env
open -e .env          # paste each URL after its = sign, save
```

| Channel | Line in `.env` |
|---|---|
| `#daily-digest` | `DISCORD_WEBHOOK_DAILY_DIGEST=` |
| `#scout-leads` | `DISCORD_WEBHOOK_SCOUT_LEADS=` |
| `#outreach-sent` | `DISCORD_WEBHOOK_OUTREACH_SENT=` |
| `#outreach-replies` | `DISCORD_WEBHOOK_OUTREACH_REPLIES=` |
| `#app-factory` | `DISCORD_WEBHOOK_APP_FACTORY=` |
| `#social-drafts` | `DISCORD_WEBHOOK_SOCIAL_DRAFTS=` |
| `#community` | `DISCORD_WEBHOOK_COMMUNITY=` |
| `#alerts` | `DISCORD_WEBHOOK_ALERTS=` |
| `#approvals` | `DISCORD_WEBHOOK_APPROVALS=` |
| `#mission-control` | `DISCORD_WEBHOOK_MISSION_CONTROL=` |

Prefer the macOS Keychain? Store each URL with
`security add-generic-password -a "$USER" -s jura-discord-alerts -w '<url>'` and write
`DISCORD_WEBHOOK_ALERTS=keychain:jura-discord-alerts` in `.env` instead. Both work.

## 5. Test

```bash
uv sync                       # first time only
.venv/bin/jura-growth discord test
.venv/bin/jura-growth one-pager
```

`discord test` should say `posted` for every channel, and a test message should appear in each
one. A channel that says `NOT POSTED (… not set; saved to outbox)` is missing its line in `.env`.

`one-pager` should answer `posted to #mission-control`, and the one-pager should appear there with
the 14-day grid attached. Then reinstall the schedule so the 08:00 job is loaded:
`.venv/bin/jura-growth schedule install`.

Until the webhooks exist, every agent message is kept in `data/growth/discord-outbox/` instead,
so nothing is lost while you set this up.

**Done when:** `jura-growth discord test` posts to every channel, `jura-growth one-pager` answers
`posted to #mission-control`, and `#approvals` is set to all messages.
