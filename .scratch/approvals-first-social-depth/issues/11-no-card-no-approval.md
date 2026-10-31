# 11: No card, no approval, and close review 10

Status: done
Blocked by: 10

Work on the same branch, `crew/approvals-first-social-depth-10-final-fixes`, in the same worktree. Read `reviews/code-review-10.md` first; the finding ids below are its own.

**First commit: merge `origin/crew/approvals-first-social-depth` (for this ticket), then `origin/main`, which has moved by PR #20.** No rebase. PR #20 touches `agents/social/__init__.py`, `mission.py`, `remote.py`, `cli.py` and `agents/publish/commands.py`. Its new `pending.py` reads the same requests this feature changed, so check that what it says about a social post still holds in browser mode.

**B1, test-first. A social post with no card can't be approved.** `SocialPost.on_approve` refuses whenever `latest.posted_at is None`. A skip still works. Typed approval is not kept as a route for a Discord outage: the heartbeat re-posts the card and the post can wait for it. The conductor decided this, and the PRD records it.

**The same rule for `outreach-email`, test-first.** An outreach request with `posted_at None` is approved and sent today, and `config/scout.yaml` is `mode: live`. An email to a real prospect is the action least able to be taken back, and Ting Yu named scout drafts in the request that started this feature. If the rule needs more than the shared helpers and fixtures to change, stop at social, keep the failing outreach test in the report, and say so; ticket 12 then takes it.

**The fixtures.** The reviewer measured 186 failures and 47 errors from the social change alone, and read the cause as fixtures deciding without a sweep. Fix them in the shared helpers, by giving the request a card the way production does. No assertion gets weaker, no test is deleted to pass, and `gate_adapter_*` may only gain lines (X6). Any test whose assertion has to change goes in the report with the reason.

**Also close:**
- **St3:** the twin of the learned-name test, with no sweep before the decision, so that removing `privacy.learn` from `card_problem` fails a test. Prove it by mutation. With B1 in, re-check whether `card_problem` in `on_approve` can still be reached. If it can't, remove the dead branch and say so.
- **St1:** delete `test_the_live_engine_writing_its_run_log_does_not_fail_the_refusal_test`, or point it at the watcher.
- **St2:** one function for the request's clock reading (`_place` and `mission._request`), and the `decided` line and `last_run_on` check in `items`. Reuse `picture._sentence` and `discord`'s prefix. Leave the `plan.py` restatement unless it is a one-liner to remove.
- **SEC1:** compare webhooks by parsed id, refuse a `keychain:` value in the UAT env file, and refuse when no live env file can be found to compare against, including with `JURA_ROOT` unset. The value is never printed.
- **The suite must not open the live `.env`.** Tests plant `LIVE_ENV_FILES`. Only a real `seed` run reads the live file, read-only.
- **S1:** the seed's times (`tests/uat/seed.py:40,288,290,365`) and their pins, to main's schedule and the 17:00 decide-by. Correct `reviews/functional.md` only if a line there would mislead the UAT.
- **S2:** add AF5 and A13 to the `test_digest_figures` line in `reviews/qa-final.md`.
- **Nits worth one edit:** the two "so"s at `kinds.py:262`. Set tickets 05 to 11 to `Status: done`.

**Not here:**
- S3 (ST-S2): `CLAUDE.md`'s numbers rule stays Ting Yu's to change.
- SEC2's masked outreach and community cards: ticket 12.

**Acceptance:** the failing tests were red first. The full suite is green, run twice, once with the clock across midnight, with failure names kept. X1 to X8 are rerun on the merged tree and recorded in `reviews/qa-final.md`. X9 is rerun if a card's CSS or HTML changed.

## Comments
