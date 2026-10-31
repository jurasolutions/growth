# 09: Defect: a typed approval of a refused card goes through

Status: ready-for-agent
Severity: major
Owner: developer
Found by: the final review, as SP-B2 (`reviews/code-review-final.md`). QA reproduced it in separate processes at f0db1e5 (`reviews/qa-final.md`).
Failing test: `.scratch/approvals-first-social-depth/issues/test_qa_final_defects.py`, the test under "09"

## Steps

Each of these is its own process, on a temp folder with a frozen clock.

1. Seed `social-day` while the #approvals webhook answers 500, so both requests stay pending with no card. In the walk this came from the recorder's failure mode.
2. Add a named contact whose address teaches a word in the post, for example `marta.picture@acme.example.sg`. The post says "Picture a small trading firm".
3. `jura-growth heartbeat`. The sweep refuses each card.
4. `python -m tests.uat.seed "$UAT" --scenario decide --approval A-0001 --decision approve --today 2026-11-10`, which decides through `Origin.ssh()`, as Dispatch's call does.
5. `jura-growth publish next --json`.

## Expected

Step 4 answers `refused`, as `docs/social.md:325` says ("a typed approval is refused"), and step 5 hands out nothing. The note from step 3 has told him: "Nothing goes out, and it lapses Tue 10 Nov, 17:00 SGT."

## Actual

- Step 3 posts "**A-0001 has no card** ... Discord would mask part of the post, so its card can't show the exact text. Nothing goes out, and it lapses Tue 10 Nov, 17:00 SGT."
- Step 4 answers "A-0001 approved."
- Step 5 answers `"due": true, "approval": "A-0001"`, and the request's `used_at` is set. A post nobody saw on a card is handed to the browser.

## Why

`SocialPost.card_problem` asks `privacy.own_copy_as_shown`, which masks with what this process has learned, and nothing on the decision path learns first. A sweep's process has learned the name, so it refuses. A new process deciding hasn't, so it allows. The existing test `test_a_typed_approval_of_a_post_with_no_card_is_refused_and_can_be_skipped` plants a phone number, which masks by pattern in any process, so it can't see this.

## Severity

Major rather than critical.

- **Why it isn't critical:** the approval still binds the exact hash, a person has to type it, and getting here takes a failed first post or a name learned between the gate and the sweep.
- **Why it is major:** it breaks AF1's promise that he decides on what the card shows, a documented refusal doesn't hold, and the note's "Nothing goes out" becomes false.

**One limit on this repro:** it uses the seed's `decide` in a fresh process, not a real SSH call, because `Origin.ssh()` needs a real `sshd` parent for `jura-growth remote`. The seed makes the same `approvals.decide` call, and in a real SSH call `remote.py` learns only after the decision (`_masked`), per the final review.

## Fix

The final review's: call `privacy.learn(conn)` at the top of `card_problem`, or have `on_approve` refuse when `cards.refusal(conn, latest.id)` is set.
