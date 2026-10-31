# Approve an email reply and it goes out threaded

Status: ready-for-agent
Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md` (read §2 and "Amended 2026-10-31 after the spec reviews", which win over anything earlier)
Reviews: `reviews/technical.md` (seams, B and N numbers), `reviews/functional.md` (F and S numbers, and its Given/When/Then table), `reviews/test-strategy.md` (name tests `IW-<criterion>` and `IW-A<n>`)
Blocked by: 02

The `email-reply` kind (declare `feed_channel = "mission-control"` and `feed_approved`, inert until approvals-first lands; see technical.md "Merging"), the card (`conversation_card`, `card_quote`), `inbox send-due`, the `inbox-send` job running the mail intake before each claim (F9).

Accept: the gate matrix and Terminal refusal pass for `email-reply`; D1, D2, D3 (`In-Reply-To`, `References`, `Re:`, one BCC, 08:00 to 22:00), D5, D7, E2, F9 for email, F10, F15, S3, S5, S6, S7's lapse line. Content covers the frame and the BCC (ADR 0003). "Hi Jane," reaches the card unchanged (B3). One Discord piece at every length (B8). A retry under the same claim uses one idempotency key and stops at 23 hours, past which it is marked unknown. A failed send doesn't count toward auto-pause. IW-A7, A8, A9 end to end. F2 and F4's outgoing half, moved here from ticket 01 (code review 01, P-3): `inbox-send` sets a `Message-ID` on each inbox reply and calls `store.remember_outgoing`, the table's first writer, and the 16:45 check's `_batch` uses that lookup too. Outreach sends stay as they are, so F2's domain match keeps covering outreach mail. The card names the real recipient's domain, where it differs from the `From` domain (A9; code review 01, N-1).
