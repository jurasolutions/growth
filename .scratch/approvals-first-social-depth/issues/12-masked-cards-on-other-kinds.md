# 12: Follow-up: outreach and community cards that hide words

Status: ready-for-human
Blocked by: 11

Not part of this feature's release. It predates this branch, and it needs to be done before `config/community.yaml` turns `browser` on.

**What happens.** From `reviews/code-review-10.md`, SEC2, reproduced on the Discord double. A contact `marta.most@other.example.sg` teaches "Most" as a name. An outreach card then shows "> [name removed] delivery firms sign on paper.", the approval is recorded, and the send double takes one email. A community-post card behaves the same way. Neither kind has `card_problem` or `own_copy`.

**Why it matters less than B1, and still matters.** Ting Yu sees the marker, so he isn't misled silently, but he approves words he couldn't read. The reviewer did not read the sent email's body, so whether the prospect receives the real word is unconfirmed. Check that first.

**Fix.** Give those kinds the rule `social-post` has: a card that can't show the exact text isn't posted and can't be approved, with a note saying why. For `community-post`, also apply ticket 11's no-card rule. Add `outreach-email`'s no-card rule here too if ticket 11 had to stop at social.

**Widened after review 11 (its S1).** These kinds also accept a typed approval with no card, reproduced with `approvals.decide` and no sweep. Apply the rule to each of them, and decide whether it should move to the core and be driven by `needs_card`, which today only describes `on_approve`.

| Kind | What follows the approval | Reachable on the shipped config? |
|---|---|---|
| `app-release` | The claim goes through, and `release-plan` prints the merge | Yes. Ting Yu still runs the merge by hand |
| `app-build` | A handoff to Dispatch, on its own branch | Yes, with `dispatch_builds` on |
| `group-rules` | Sets the rules, which unlock community posts | Yes, with no public action of its own |
| `community-post` | Claimed by a run | No: `config/community.yaml` is `browser: false` |
| `group-join`, answers | Claimed by a run | No, as above |

## Comments

**Added after review 13 (F1, F2).** `remote` hides a refusal's reason in two ways, and neither changes what is refused.

- An env file at mode 0644 prints a permissions warning first, so every refusal reads "the command was not understood", and the retry hazard from ticket 13 returns while the file stays loose. After-merge steps tell Ting Yu to check the mode. `remote` should find the `refused:` line whatever comes before it.
- A `BadArgs` without the `refused:` prefix is hidden the same way. Every one has the prefix today, and only the README enforces it. Add a test that walks every kind's hooks, or add the prefix in one place.
