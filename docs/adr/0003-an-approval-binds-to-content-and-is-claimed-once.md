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
Ting Yu is alerted; it is never sent again under that approval.
*Amended 2026-10-31 (code review S13-4 of the designed outreach email):* for an outreach email the
bytes handed out include what the code adds around the draft: the call button, the signature, the
footer, the HTML template, the sender and Reply-To. The content carries `compose.frame_fingerprint()`,
a hash of that frame rendered for a stand-in recipient, so a template change between approval and
claim supersedes the request instead of sending a frame Ting Yu never saw. The card names the
template version and the frame's first eight hex digits.
*Amended 2026-10-31 (inbox watch ticket 03):* an `email-reply` holds to all of this. Its bytes include its
frame and its BCC, and a retry has the same bound, under its one key. It adds one rule: a retry goes only
while the reply still hashes to what was approved, so if they wrote again after the claim, or were
suppressed, it is marked unknown and never sent again. A pending
request lapses at its decide-by and an approved, unclaimed one at its use-by, two separate clocks, so
a yes is never lost behind the send caps. Approval state lives only in the `approvals` table: plug-in
tables hold their item's lifecycle and never a copy of the decision. Don't loosen this to "approved
for this lead" or "approved today", and don't move the claim after the effect.
