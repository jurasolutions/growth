# An approval binds to content and is claimed once, before the effect

Status: accepted (2026-10-25, ticket MC-04a of `prd-jura-mission-control-2026-10-25.md`).

Every outward action (an email, a post, a group join, an app build or release) needs an approval
record whose content hash matches what will go out now, as computed by the kind's own `content()`.
The gated action claims the approval with `approvals.use()` inside a `BEGIN IMMEDIATE` transaction
**before** the effect, because Resend, Chrome and Dispatch sit outside SQLite and no transaction can
contain them. The claim is the point of no return: a skip is allowed until then, and no deadline is
re-checked after it. One approval covers one action instance; its own retries (the same outreach
message under the same idempotency key) aren't a second use, and publishing never retries. A pending
request lapses at its decide-by and an approved, unclaimed one at its use-by, two separate clocks, so
a yes is never lost behind the send caps. Approval state lives only in the `approvals` table: plug-in
tables hold their item's lifecycle and never a copy of the decision. Don't loosen this to "approved
for this lead" or "approved today", and don't move the claim after the effect.
