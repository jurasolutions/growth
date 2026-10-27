# An approval binds to content and is claimed once, before the effect

Status: accepted (2026-10-25, ticket MC-04a of `prd-jura-mission-control-2026-10-25.md`).

Every outward action (an email, a post, a group join, an app build or release) needs an approval
record whose content hash matches what will go out now, as computed by the kind's own `content()`.
*Amended 2026-10-27 (code reviews 06 and BP-02):* the hash covers the exact bytes handed out, the
text and every attachment, with no Unicode normalisation. Two drafts that differ in any byte, even an
NFC and an NFD form of the same text, need separate approvals, because normalising would let a yes
cover bytes Ting Yu never saw.
The gated action claims the approval with `approvals.use()` inside a `BEGIN IMMEDIATE` transaction
**before** the effect, because Resend, Chrome and Dispatch sit outside SQLite and no transaction can
contain them. The claim is the point of no return: a skip is allowed until then, and no deadline is
re-checked after it. One approval covers one action instance; its own retries (the same outreach
message under the same idempotency key) aren't a second use, and publishing never retries.
*Amended 2026-10-27 (code review 06 Sp1):* an outreach retry under the same claim is bounded by
whichever comes first, the approval's use-by or 23 hours from the claim (inside Resend's 24-hour
idempotency key). Past either, the email may already have gone out, so it is marked uncertain and
Ting Yu is alerted; it is never sent again under that approval. A pending
request lapses at its decide-by and an approved, unclaimed one at its use-by, two separate clocks, so
a yes is never lost behind the send caps. Approval state lives only in the `approvals` table: plug-in
tables hold their item's lifecycle and never a copy of the decision. Don't loosen this to "approved
for this lead" or "approved today", and don't move the claim after the effect.
