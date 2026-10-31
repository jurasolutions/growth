# Approve a social reply and it posts once, in the right place

Status: ready-for-agent
Spec: `jurasolutions/prd/pending/prd-jura-inbox-watch-2026-10-31.md` (read §2 and "Amended 2026-10-31 after the spec reviews", which win over anything earlier)
Reviews: `reviews/technical.md` (seams, B and N numbers), `reviews/functional.md` (F and S numbers, and its Given/When/Then table), `reviews/test-strategy.md` (name tests `IW-<criterion>` and `IW-A<n>`)
Blocked by: 03, 04, 05

The `social-reply` kind (feed attributes as in 03), `inbox reply-due`, `inbox reply-next`, `inbox reply-done`, and the pre-claim outcomes of F9 (a newer message, answered by hand, target gone), the `inbox-reply` job, `prompts/inbox-reply.md`, `hosts` checks for DM targets (N12 as amended), the fixture's inbox pages, the setup guide at `.scratch/inbox-watch/setup/inbox-watch.md` (the release copies it to `outputs/growth/setup/`), and UAT Part B folded into `reviews/uat.md` with the golden set G.

Accept: the gate matrix and Terminal refusal for `social-reply`, including its switch reading the `publish` flag; D4 (comment under the comment, DM in the thread, one per run, read-back); F5's Accept; F9 for social; `inbox-social` refuses every line break; `one_line` end to end (fails the run and pauses `inbox-browser`); N3 of functional; N13; S4 of functional; a watch that finds the Page already answered closes the item and still reports it. `uv run pytest` is green across the suite on the branch. The setup guide says a message moved from Junk to the inbox stays noise, so answer it by hand. UAT Part B reads the id that opens the server's `Authentication-Results` on one raw enquiry and puts it in `auth_servers` in `config/inbox.yaml`. Until then every enquiry reads as unsigned, and a sender's own header counts for nothing (code review 01, N-2, R-5).
