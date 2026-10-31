### C01 normal Name: description

- typed in Discord: `/growth apps idea Site visit report: write up a site visit with photos and a signature, and save it as a PDF`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 313700446586920582:499935 --json -- apps idea Site visit report: write up a site visit with photos and a signature, and save it as a PDF`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Site visit report
  slug    site-visit-report
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
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
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C02 no colon

- typed in Discord: `/growth apps idea a tool that turns supplier price lists into one comparison table`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 164222524137774301:688677 --json -- apps idea a tool that turns supplier price lists into one comparison table`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 1, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    A tool that turns supplier
  slug    a-tool-that-turns-supplier
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    a tool that turns supplier price lists into one comparison table
1 older idea of yours comes first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -183,0 +184,8 @@
+- name: A tool that turns supplier
+  slug: a-tool-that-turns-supplier
+  does: a tool that turns supplier price lists into one comparison table
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C03a URL first

- typed in Discord: `/growth apps idea https://www.iras.gov.sg/taxes/goods-services-tax-(gst) a GST registration checker for small firms`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 939261967932003873:980539 --json -- apps idea 'https://www.iras.gov.sg/taxes/goods-services-tax-(gst)' a GST registration checker for small firms`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Https://www.iras.gov.sg/taxes/goods-services-tax-(gst) a GST
  slug    https-www-iras-gov-sg-taxes-goods-services-tax-gst-a-gst
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    https://www.iras.gov.sg/taxes/goods-services-tax-(gst) a GST registration checker for small firms
2 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -191,0 +192,8 @@
+- name: Https://www.iras.gov.sg/taxes/goods-services-tax-(gst) a GST
+  slug: https-www-iras-gov-sg-taxes-goods-services-tax-gst-a-gst
+  does: https://www.iras.gov.sg/taxes/goods-services-tax-(gst) a GST registration checker for small firms
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C03b time inside

- typed in Discord: `/growth apps idea Remind staff at 9:30 to submit their timesheets every Friday`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 270457209995205716:268413 --json -- apps idea Remind staff at 9:30 to submit their timesheets every Friday`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 3, 424242424242424242, 9-30-, 9:30

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Remind staff at 9:30 to
  slug    remind-staff-at-9-30-to
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Remind staff at 9:30 to submit their timesheets every Friday
3 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -199,0 +200,8 @@
+- name: Remind staff at 9:30 to
+  slug: remind-staff-at-9-30-to
+  does: Remind staff at 9:30 to submit their timesheets every Friday
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C03c second URL-first idea

- typed in Discord: `/growth apps idea https://www.mom.gov.sg/employment-practices/leave a leave entitlement checker`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 583635014077749930:738097 --json -- apps idea https://www.mom.gov.sg/employment-practices/leave a leave entitlement checker`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 4, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Https://www.mom.gov.sg/employment-practices/leave a leave
  slug    https-www-mom-gov-sg-employment-practices-leave-a-leave
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    https://www.mom.gov.sg/employment-practices/leave a leave entitlement checker
4 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -207,0 +208,8 @@
+- name: Https://www.mom.gov.sg/employment-practices/leave a leave
+  slug: https-www-mom-gov-sg-employment-practices-leave-a-leave
+  does: https://www.mom.gov.sg/employment-practices/leave a leave entitlement checker
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C03d URL after the name

- typed in Discord: `/growth apps idea Grant finder: check https://www.enterprisesg.gov.sg for grants that fit at 06:30 each day`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 166171720783156538:891477 --json -- apps idea Grant finder: check https://www.enterprisesg.gov.sg for grants that fit at 06:30 each day`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 424242424242424242, 5

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Grant finder
  slug    grant-finder
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Grant finder: check https://www.enterprisesg.gov.sg for grants that fit at 06:30 each day
5 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -215,0 +216,8 @@
+- name: Grant finder
+  slug: grant-finder
+  does: 'Grant finder: check https://www.enterprisesg.gov.sg for grants that fit at 06:30 each day'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C04 empty

- typed in Discord: `/growth apps idea`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 2148601193076895:55078 --json -- apps idea`
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

### C05a 500 characters (boundary, accepted)

- typed in Discord: `/growth apps idea Long idea: records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver a`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 676919499535965034:944935 --json -- apps idea Long idea: records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver a`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 424242424242424242, 6

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Long idea
  slug    long-idea
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Long idea: records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver a
6 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -223,0 +224,13 @@
+- name: Long idea
+  slug: long-idea
+  does: 'Long idea: records each delivery with the date the driver and a signature records each delivery
+    with the date the driver and a signature records each delivery with the date the driver and a signature
+    records each delivery with the date the driver and a signature records each delivery with the date
+    the driver and a signature records each delivery with the date the driver and a signature records
+    each delivery with the date the driver and a signature records each delivery with the date the driver
+    a'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C05b 501 characters

- typed in Discord: `/growth apps idea Long idea: records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver ay`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 179633722559193988:21284 --json -- apps idea Long idea: records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver and a signature records each delivery with the date the driver ay`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: 500, 501

Reply as Ting Yu reads it:

```text
refused: the idea is 501 characters; keep it to 500
```

Backlog diff:

```diff
(unchanged)
```

### C06a --force

- typed in Discord: `/growth apps idea Stock tool: count stock --force`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 280739477950924221:314409 --json -- apps idea Stock tool: count stock --force`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps idea` takes no options (found --force); send the idea as plain words.
```

Backlog diff:

```diff
(unchanged)
```

### C06b -h alone

- typed in Discord: `/growth apps idea -h`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 799319739027932560:857462 --json -- apps idea -h`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps idea` takes no options (found -h); send the idea as plain words.
```

Backlog diff:

```diff
(unchanged)
```

### C06c --source=seed

- typed in Discord: `/growth apps idea Evil tool: --source=seed --status=live`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 745656548391630364:9105 --json -- apps idea Evil tool: --source=seed --status=live`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps idea` takes no options (found --source=seed); send the idea as plain words.
```

Backlog diff:

```diff
(unchanged)
```

### C06d --help

- typed in Discord: `/growth apps idea --help`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 247664113442389268:314595 --json -- apps idea --help`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps idea` takes no options (found --help); send the idea as plain words.
```

Backlog diff:

```diff
(unchanged)
```

### C06e dashes inside words

- typed in Discord: `/growth apps idea Range tool: 5-10 items, -5 degrees, a well-known - dash and -- a double one`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 207287187485930211:931548 --json -- apps idea Range tool: 5-10 items, -5 degrees, a well-known - dash and -- a double one`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 424242424242424242, 5, 5-10, 7

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Range tool
  slug    range-tool
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Range tool: 5-10 items, -5 degrees, a well-known - dash and -- a double one
7 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -236,0 +237,8 @@
+- name: Range tool
+  slug: range-tool
+  does: 'Range tool: 5-10 items, -5 degrees, a well-known - dash and -- a double one'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C07a Quote builder (live, pending, backlog)

- typed in Discord: `/growth apps idea Quote builder: quotes for contractors with GST`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 461799499972125235:499651 --json -- apps idea Quote builder: quotes for contractors with GST`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: 001

Reply as Ting Yu reads it:

```text
not added: "Quote builder" (quote-builder) clashes with Quote builder (backlog: prd-pending, APP-001). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07b quote-builder slug, no colon

- typed in Discord: `/growth apps idea quote-builder`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 76062278361551658:449911 --json -- apps idea quote-builder`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: 001

Reply as Ting Yu reads it:

```text
not added: "Quote-builder" (quote-builder) clashes with Quote builder (backlog: prd-pending, APP-001). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07c QUOTE BUILDER caps and punctuation

- typed in Discord: `/growth apps idea QUOTE-BUILDER!: shouting`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 330569424859536234:175013 --json -- apps idea 'QUOTE-BUILDER!:' shouting`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: 001

Reply as Ting Yu reads it:

```text
not added: "QUOTE-BUILDER" (quote-builder) clashes with Quote builder (backlog: prd-pending, APP-001). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07d Product photo studio (live, not in backlog)

- typed in Discord: `/growth apps idea Product photo studio: tidy product photos`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 464948362587250892:205533 --json -- apps idea Product photo studio: tidy product photos`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
not added: "Product photo studio" (product-photo-studio) clashes with the slug product-photo-studio (live in the site registry). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07e Payslip maker (seed idea row)

- typed in Discord: `/growth apps idea Payslip maker: payslips with CPF`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 176041205189203464:686216 --json -- apps idea Payslip maker: payslips with CPF`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
not added: "Payslip maker" (payslip-maker) clashes with Payslip maker (backlog: idea). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07f PDF merge and split (dropped row, live)

- typed in Discord: `/growth apps idea PDF merge and split: merge PDFs`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 539549421599819470:441454 --json -- apps idea PDF merge and split: merge PDFs`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: 003

Reply as Ting Yu reads it:

```text
not added: "PDF merge and split" (pdf-merge-and-split) clashes with PDF merge and split (backlog: dropped, APP-003). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07g his own earlier idea again

- typed in Discord: `/growth apps idea Site visit report: again, with a map`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 80867973610386330:357599 --json -- apps idea Site visit report: again, with a map`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
not added: "Site visit report" (site-visit-report) clashes with Site visit report (backlog: idea). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C07h Quote builders (plural)

- typed in Discord: `/growth apps idea Quote builders: one per trade`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 955163540777143682:669922 --json -- apps idea Quote builders: one per trade`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 2026-10-31, 424242424242424242, 8

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Quote builders
  slug    quote-builders
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Quote builders: one per trade
8 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -244,0 +245,8 @@
+- name: Quote builders
+  slug: quote-builders
+  does: 'Quote builders: one per trade'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C08a YAML tags, anchors, documents

- typed in Discord: `/growth apps idea Anchor tool: &a !!python/object/apply:os.system ["ls"] *a --- status: live source: seed # comment`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 623561460974714401:759903 --json -- apps idea Anchor tool: '&a' '!!python/object/apply:os.system' '["ls"]' '*a' --- status: live source: seed '#' comment`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: exclamation mark; figures in reply: 06:30, 2026-10-31, 424242424242424242, 9

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Anchor tool
  slug    anchor-tool
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Anchor tool: &a !!python/object/apply:os.system ["ls"] *a --- status: live source: seed # comment
9 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -252,0 +253,8 @@
+- name: Anchor tool
+  slug: anchor-tool
+  does: 'Anchor tool: &a !!python/object/apply:os.system ["ls"] *a --- status: live source: seed # comment'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C08b flow mapping

- typed in Discord: `/growth apps idea { name: x, source: seed, status: live }`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 17489898746737867:516096 --json -- apps idea '{' name: x, source: seed, status: live '}'`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 10, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    { name
  slug    name
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    { name: x, source: seed, status: live }
10 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -260,0 +261,8 @@
+- name: '{ name'
+  slug: name
+  does: '{ name: x, source: seed, status: live }'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C08c list item and key

- typed in Discord: `/growth apps idea - name: Evil row`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 421463643272687014:812689 --json -- apps idea - name: Evil row`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
not added: "- name" (name) clashes with { name (backlog: idea). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C08d status: live as the whole text

- typed in Discord: `/growth apps idea status: live`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 123513947062483045:890528 --json -- apps idea status: live`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 11, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Status
  slug    status
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    status: live
11 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -268,0 +269,8 @@
+- name: Status
+  slug: status
+  does: 'status: live'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C09 mentions

- typed in Discord: `/growth apps idea Ping tool: tell @everyone and <@123> and <@&456> and @here when stock is low`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 826297165213957297:683828 --json -- apps idea Ping tool: tell @everyone and '<@123>' and '<@&456>' and @here when stock is low`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 12, 123, 2026-10-31, 424242424242424242, 456

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Ping tool
  slug    ping-tool
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Ping tool: tell @​everyone and <@​123> and <@​&456> and @​here when stock is low
12 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -276,0 +277,8 @@
+- name: Ping tool
+  slug: ping-tool
+  does: 'Ping tool: tell @everyone and <@123> and <@&456> and @here when stock is low'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C10a Chinese only

- typed in Discord: `/growth apps idea 报价单生成器：为承包商制作报价单`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 325561528881267603:105457 --json -- apps idea '报价单生成器：为承包商制作报价单'`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: the name needs Latin letters (A to Z), because it becomes the tool's web address. Put one before a colon, like `Leave form maker: …`
```

Backlog diff:

```diff
(unchanged)
```

### C10b Chinese name, ASCII colon

- typed in Discord: `/growth apps idea 报价单: 制作报价单`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 608902277539435180:859832 --json -- apps idea '报价单:' '制作报价单'`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: the name needs Latin letters (A to Z), because it becomes the tool's web address. Put one before a colon, like `Leave form maker: …`
```

Backlog diff:

```diff
(unchanged)
```

### C10c accented Latin

- typed in Discord: `/growth apps idea Café menu maker: crème brûlée prices in one menu`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 416215122368645780:727403 --json -- apps idea 'Café' menu maker: 'crème' 'brûlée' prices in one menu`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 13, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Café menu maker
  slug    caf-menu-maker
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Café menu maker: crème brûlée prices in one menu
13 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -284,0 +285,8 @@
+- name: Café menu maker
+  slug: caf-menu-maker
+  does: 'Café menu maker: crème brûlée prices in one menu'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C10d Latin name, Tamil body

- typed in Discord: `/growth apps idea Tamil price list: தமிழ் விலைப்பட்டியல் மாதிரி`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 782652222406534192:223780 --json -- apps idea Tamil price list: 'தமிழ்' 'விலைப்பட்டியல்' 'மாதிரி'`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 14, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Tamil price list
  slug    tamil-price-list
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Tamil price list: தமிழ் விலைப்பட்டியல் மாதிரி
14 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -292,0 +293,8 @@
+- name: Tamil price list
+  slug: tamil-price-list
+  does: 'Tamil price list: தமிழ் விலைப்பட்டியல் மாதிரி'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C10e emoji in text

- typed in Discord: `/growth apps idea Rocket tool: 🚀 a launch checklist`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 736533285819724045:947734 --json -- apps idea Rocket tool: '🚀' a launch checklist`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: emoji; figures in reply: 06:30, 15, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    Rocket tool
  slug    rocket-tool
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    Rocket tool: 🚀 a launch checklist
15 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -300,0 +301,8 @@
+- name: Rocket tool
+  slug: rocket-tool
+  does: 'Rocket tool: 🚀 a launch checklist'
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

### C10f mixed Chinese and Quote builder

- typed in Discord: `/growth apps idea 报价单 Quote builder: 中文`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 872604652965819911:484038 --json -- apps idea '报价单' Quote builder: '中文'`
- process exit code: 1; JSON exit_code: 1; answer: refused; ok: False
- voice lint: clean; figures in reply: 001

Reply as Ting Yu reads it:

```text
not added: "报价单 Quote builder" (quote-builder) clashes with Quote builder (backlog: prd-pending, APP-001). Send it with a different name before a colon.
```

Backlog diff:

```diff
(unchanged)
```

### C13a shell characters and apostrophe

- typed in Discord: `/growth apps idea Tom's tool: run $(rm -rf ~); echo `id` && say "hi" | cat`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 421521682593580393:200173 --json -- apps idea 'Tom'"'"'s' tool: run '$(rm' -rf '~);' echo '`id`' '&&' say '"hi"' '|' cat`
- process exit code: 2; JSON exit_code: 2; answer: refused; ok: False
- voice lint: clean; figures in reply: none

Reply as Ting Yu reads it:

```text
refused: `apps idea` takes no options (found -rf); send the idea as plain words.
```

Backlog diff:

```diff
(unchanged)
```

### C13b one very long word

- typed in Discord: `/growth apps idea SupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilistic and more`
- ssh command (shlex.join): `--actor discord:424242424242424242 --ref 582343524454414070:311119 --json -- apps idea SupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilistic and more`
- process exit code: 0; JSON exit_code: 0; answer: recorded; ok: True
- voice lint: clean; figures in reply: 06:30, 16, 2026-10-31, 424242424242424242

Reply as Ting Yu reads it:

```text
Added to the app backlog:
  name    SupercalifragilisticSupercalifragilisticSupercalifragilistic
  slug    supercalifragilisticsupercalifragilisticsupercalifragilistic
  status  idea (source: ting-yu, added 2026-10-31 by discord:424242424242424242)
  does    SupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilistic and more
16 older ideas of yours come first; the app factory writes at most one PRD a day at 06:30 SGT, oldest first.
Its PRD comes to #approvals as an app-build request; nothing is built before you approve it.
```

Backlog diff:

```diff
--- backlog before
+++ backlog after
@@ -308,0 +309,9 @@
+- name: SupercalifragilisticSupercalifragilisticSupercalifragilistic
+  slug: supercalifragilisticsupercalifragilisticsupercalifragilistic
+  does: SupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilisticSupercalifragilistic
+    and more
+  status: idea
+  source: ting-yu
+  added: '2026-10-31'
+  actor: discord:424242424242424242
+  notes: Sent by Ting Yu with `apps idea` on 2026-10-31.
```

