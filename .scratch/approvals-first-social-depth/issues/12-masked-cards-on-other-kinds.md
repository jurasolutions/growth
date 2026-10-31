# 12: Follow-up: outreach and community cards that hide words

Status: ready-for-human
Blocked by: 11

Not part of this feature's release. It predates this branch, and it needs to be done before `config/community.yaml` turns `browser` on.

**What happens.** From `reviews/code-review-10.md`, SEC2, reproduced on the Discord double. A contact `marta.most@other.example.sg` teaches "Most" as a name. An outreach card then shows "> [name removed] delivery firms sign on paper.", the approval is recorded, and the send double takes one email. A community-post card behaves the same way. Neither kind has `card_problem` or `own_copy`.

**Why it matters less than B1, and still matters.** Ting Yu sees the marker, so he isn't misled silently, but he approves words he couldn't read. The reviewer did not read the sent email's body, so whether the prospect receives the real word is unconfirmed. Check that first.

**Fix.** Give those kinds the rule `social-post` has: a card that can't show the exact text isn't posted and can't be approved, with a note saying why. For `community-post`, also apply ticket 11's no-card rule. Add `outreach-email`'s no-card rule here too if ticket 11 had to stop at social.

## Comments
