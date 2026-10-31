### F0a idea on 30 Oct

- typed in Discord: `/growth apps idea Site visit report: write up a site visit with photos and a signature, and save it as a PDF`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 933630541663737208:692878 --json -- apps idea Site visit report: write up a site visit with photos and a signature, and save it as a PDF`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-30, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Site visit report
  slug    site-visit-report
  status  idea (source: ting-yu, added 2026-10-30 by discord:424242424242424242)
  does    Site visit report: write up a site visit with photos and a signature, and save it as a PDF
The app factory picks it at its next run (06:30 SGT).
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -11,0 +12,6 @@
+# source: ting-yu marks an idea Ting Yu sent with `apps idea`; the factory picks
+#   those first, oldest first (`added`). One it couldn't take has `held` and
+#   `held_reason`, and is an ordinary candidate from then on.
+#
+# Only this header is written back: comments you add lower down are lost the
+# next time the file is saved.
@@ -169,0 +176,8 @@
+- name: Site visit report
+  slug: site-visit-report
+  does: 'Site visit report: write up a site visit with photos and a signature, and save it as a PDF'
+  status: idea
+  source: ting-yu
+  added: '2026-10-30'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-30.
```

