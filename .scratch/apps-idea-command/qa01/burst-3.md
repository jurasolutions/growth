### burst 3

- typed in Discord: `/growth apps idea Burst tool 3: idea number 3 in a burst`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 634947715026687887:284496 --json -- apps idea Burst tool 3: idea number 3 in a burst`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 19, 2026-10-31, 3, 3:, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Burst tool 3
  slug    burst-tool-3
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Burst tool 3: idea number 3 in a burst
19 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -333,0 +334,8 @@
+- name: Burst tool 3
+  slug: burst-tool-3
+  does: 'Burst tool 3: idea number 3 in a burst'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

