# See mail and report it, with no model

Status: ready-for-agent
Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md` (read §2 and "Amended 2026-10-31 after the spec reviews", which win over anything earlier)
Reviews: `reviews/technical.md` (seams, B and N numbers), `reviews/functional.md` (F and S numbers, and its Given/When/Then table), `reviews/test-strategy.md` (name tests `IW-<criterion>` and `IW-A<n>`)
Blocked by: none

Prefactors first: split `outreach/replies.py` into a mailbox read and `apply_reply` (its tests stay, apart from the F1 rule); add `conversation=` to `privacy.for_discord`, `discord.post` and `discord.edit` (B3).

Then the `inbox` plug-in, its migration (three tables at most, see the PRD's §5 model), `caps.py`, `config/inbox.yaml`, the `inbox-check` job and its precheck with no prompt work yet (the job may stay a precheck-only quiet run in this ticket), `store.record`, the noise filter, `report_due`, R1 (every item reports on record for now), `report.quoted`, and the CONTEXT.md terms in functional.md's Language section.

Accept: W1, W5 (mail), W6 with F1 and F2, W7, W8, R2, R5's counts, F3's evidence rule, F4, F12's mail half, S9, S11's recipient rule, S16, B3's class tests, B5 rules 1 to 3, B7, N5. The strict IMAP double sees `EXAMINE`/readonly and `BODY.PEEK` only. A 16:45 `scout-sync` counts nothing again. `tests/test_privacy.py` and `tests/test_outreach_privacy.py` are untouched and green. IW-A4, A5, A6, A7, A8, A9, A12, A14.

Moved by code review 01, so not tested here: F2's `In-Reply-To` and `References` half and F4's kept `Message-ID`s (ticket 03); R2's list on the one-pager, including S16's Junk lines (ticket 04). Here R2 and S16 mean no message of its own, a count in the digest, and `store.noise_since` holding the domain and subject.
