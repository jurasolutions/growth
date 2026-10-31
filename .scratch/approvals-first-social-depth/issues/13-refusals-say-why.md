# 13: A refusal over remote says why, and close review 11

Status: done
Blocked by: 11

Work on the same branch and worktree. First merge `origin/crew/approvals-first-social-depth` for this ticket, then `origin/main` if it has moved. Read `reviews/code-review-11.md`; the finding ids below are its own.

**B2, test-first, through `remote`.** A no-card or refused-card answer reaches Ting Yu as "refused: the command was not understood", and an identical retry can then approve a card which went out moments earlier and which nobody has read.

- All three strings start with `refused: `, from one shared helper for the two kinds (St4).
- The answer says what to do: the card may be posting now, so read it in #approvals and decide there.
- Add one `remote`-level test per kind, in a new process, asserting that the reason reaches the reply and the status stays `pending`. Add one for a refused card.
- Check with the double whether any other `BadArgs` from these kinds' hooks loses its text the same way. If `_usage_refusal` can hide a kind's reason in general, say so in the report. Don't change `remote.py`'s allowlist behaviour to fix it.

**Also close:**
- **S3:** `pending` doesn't say "no card yet" for a card that will never come. When `cards.refusal` is set, it says why there's no card and that it lapses at its deadline, as the health strip's refused line does. Pin approved, claimed and refused in browser mode with one test.
- **S4:** `aw.card_goes_out` calls `cards.build` before stamping, or its docstring stops claiming what it doesn't check. Prefer the first. If that changes results, report which tests and why.
- **SEC3:** refuse a `.` or `..` segment in a webhook path, and compare `int()` of ASCII digits, so `1/../<live id>` and `0<live id>` are both caught. Tests plant their own ids.
- **St5:** `conftest.py:166` reuses `seed.live_env_places()`.
- **St6:** restore the comment above `switched_off` at `outreach/approval.py:140`.
- **The nit:** `test_once_the_heartbeat_posts_the_card...` is named for what it calls.

**For the release notes, no code here (S2):** a request approved with no card before this merges can still go out, and the release notes will carry a read-only check for it.

**Not here:** review 11's S1. Ticket 12 now holds it.

**Acceptance:** the failing tests were red first. The full suite is green, run twice, once across midnight, with failure names kept. X1 to X8 are recorded in `reviews/qa-final.md`. X9 is rerun only if a card's CSS or HTML changed.

## Comments
