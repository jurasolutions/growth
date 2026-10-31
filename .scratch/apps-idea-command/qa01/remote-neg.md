### R1 apps hold-idea through remote

- typed in Discord: `/growth apps hold-idea site-visit-report --reason x`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 916482285209195150:143904 --json -- apps hold-idea site-visit-report --reason x`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps hold-idea` isn't a control command. Send one of: approvals, approve, apps built, apps handoffs, apps idea, apps release-plan, apps released, community removed, one-pager, outreach requeue-shadow, pause, publish queue, publish resolve, resume, skip, social skip, status.
```

Backlog diff:

```diff
(unchanged)
```

Error: refused: a `app-factory` run may not use `jura-growth remote`
### R2 apps idea from inside a scheduled app-factory run

- typed in Discord: `/growth apps idea Sneaky tool: added by the factory itself`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 238663052311792037:519374 --json -- apps idea Sneaky tool: added by the factory itself`
- process exit code: 2; JSON exit_code: None; answer: None; ok: None
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text

```

Backlog diff:

```diff
(unchanged)
```

### R4 a sender who isn't the control user

- typed in Discord: `/growth apps idea Stranger tool: from someone else`
- ssh command (shlex.join): `--actor discord:999 --ref 124036715664663645:797547 --json -- apps idea Stranger tool: from someone else`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 32, 999

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Stranger tool
  slug    stranger-tool
  status  idea (source: ting-yu, added 2026-10-31 by discord:999)
  does    Stranger tool: from someone else
32 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -437,0 +438,8 @@
+- name: Stranger tool
+  slug: stranger-tool
+  does: 'Stranger tool: from someone else'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:999
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### R7 a mention as the name

- typed in Discord: `/growth apps idea <@123>: ping the owner`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 500642148590863792:447181 --json -- apps idea '<@123>:' ping the owner`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 123, 2026-10-31, 33, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    <@​123>
  slug    123
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    <@​123>: ping the owner
33 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -445,0 +446,8 @@
+- name: <@123>
+  slug: '123'
+  does: '<@123>: ping the owner'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### R8 @everyone as the name

- typed in Discord: `/growth apps idea @everyone: tell the team`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 684028534318636991:535433 --json -- apps idea @everyone: tell the team`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 34, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    @​everyone
  slug    everyone
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    @​everyone: tell the team
34 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -453,0 +454,8 @@
+- name: '@everyone'
+  slug: everyone
+  does: '@everyone: tell the team'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### R9 apps idea with nothing but spaces after it (Discord trims)

- typed in Discord: `/growth apps idea      `
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 996838446614933292:476342 --json -- apps idea`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: say the idea: `apps idea <text>`.
```

Backlog diff:

```diff
(unchanged)
```

### R10 typo: apps ideas

- typed in Discord: `/growth apps ideas Something: else`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 531976473017667217:761147 --json -- apps ideas Something: else`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps ideas` isn't a control command. Send one of: approvals, approve, apps built, apps handoffs, apps idea, apps release-plan, apps released, community removed, one-pager, outreach requeue-shadow, pause, publish queue, publish resolve, resume, skip, social skip, status.
```

Backlog diff:

```diff
(unchanged)
```

