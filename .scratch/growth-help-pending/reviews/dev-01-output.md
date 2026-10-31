# Ticket 01: real output

Every answer below is what the code printed. None of it touched the live `data/growth/`.

## `jura-growth help`

Run with `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` on temp folders. Exit 0. The tests hold
the same text through `remote --json`, under 1,900 characters, with no cut.

```
Send each as `/growth <command>`, or as a plain message in #control.
`approvals [kind]`: List the requests waiting for you, soonest to lapse first.
`approve <A-nnnn> [key=value …] [note]`: Approve a request.
`apps built <APP-NNN> --task <T-nnnn> --branch <b> --sha <sha> --preview <url>`: Dispatch sends this when a build ships. Send it yourself to ask again.
`apps handoffs`: Dispatch sends this, to list the builds waiting for a builder.
`apps idea <text>`: Add your own idea to the app backlog.
`apps release-plan <APP-NNN>`: Claim an approved release and get its merge.
`apps released <APP-NNN> --task <T-nnnn>`: Record a release once main holds it.
`community removed <group-id>`: Mark a group as removed, for good.
`help`: List these commands.
`one-pager`: Post the morning picture to #mission-control.
`outreach requeue-shadow [--since YYYY-MM-DD] [--dry-run]`: Queue shadow emails again, each with a request.
`pause <agent|all> [reason]`: Stop an agent, or all of them.
`pending`: List what is unfinished, and what to send next.
`publish queue`: List every publish item and its state.
`publish resolve <A-nnnn> posted --url <url> | not-posted`: Settle a publish item whose outcome is unknown.
`resume <agent|all>`: Start an agent again, or all of them.
`skip <A-nnnn> [note]`: Skip a request.
`social skip <date> <platform>`: Leave out a platform's post, today or tomorrow.
`status`: Show pauses, last runs, the schedule and setup gaps.
```

## `/growth pending` on the APP-005 world

Through `remote --json`, in the test world `tests/test_pending.py::tonight`: APP-005 `built`, A-0004
approved and unclaimed, the clock at Tue 10 Nov 2026 10:02 SGT. Exit 0, `recorded`, 189 characters.

```
**Waiting for you**
- APP-005 Delivery order maker 5 is approved (A-0004), until Tue 24 Nov, 10:02 SGT. Send `/growth apps release-plan APP-005` for the merge.

**Growth is on it**
Nothing.
```

## `/growth pending` on a busy world

`tests/test_pending.py::busy_world`, through `remote --json`. Exit 0, `recorded`, 800 characters.

```
**Waiting for you**
- A-0021 · a test asked · decide by Tue 10 Nov, 12:02 SGT
- APP-005 Delivery order maker 5 is approved (A-0004), until Tue 24 Nov, 10:02 SGT. Send `/growth apps release-plan APP-005` for the merge.
- P-0001, facebook, 2026-11-10: the outcome is unknown. Check the page, then send `/growth publish resolve A-0501 posted --url <url>` or `/growth publish resolve A-0501 not-posted`.

**Growth is on it**
- APP-006 Delivery order maker 6 (approval A-0005) was handed to Dispatch less than a minute ago, and isn't reported built yet.
- P-0002, facebook, 2026-11-10: ready (request approved)
- 1 community post planned for today onward.
- 1 outreach email queued.
- 1 social draft for today onward.
- 1 of your ideas waits in the backlog for the app factory. The next is Petty cash log.
```

## Nothing open, and nothing readable

Nothing open, through `remote --json`:

```
Nothing pending. Nothing is waiting for you, and growth has nothing under way.
```

`jura-growth pending` with no `growth.db`, exit 0:

```
**Couldn't be read**
- Pending work couldn't be read: growth.db doesn't exist yet, so nothing has been recorded.
```
