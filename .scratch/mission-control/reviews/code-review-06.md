# Code review 06: the outreach email gate (MC-06)

- **Branch:** `crew/mission-control-06-outreach-gate` at 7e7fe22, compared with its fork point 04a609e (`git diff 04a609e...7e7fe22`, 25 files, +2081 / -91).
- **Spec:** `prd-jura-mission-control-2026-10-25.md` (email gate, MC1, MC2, §4.4, §4.6 A6/A13/A14, §5.7, §5.8, 2026-10-26 amendment). **Ticket:** `issues/06-outreach-gate.md`. **Tests:** `reviews/test-strategy-v3.md` (§11.2 row MC-06, G-cases, E14).
- **Date:** 2026-10-27

## Verdict: changes-requested

There is one blocking finding, B1. A live send does not check, inside the claim transaction, that the email it sends is the content the claimed approval covers. Two repro tests show that an email different from the approved one can go out. Everything else holds or is a should-fix.

## Evidence

| Command | Result |
|---|---|
| `uv run pytest` in the developer worktree (temp `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`, `JURA_ROOT` set) | 1932 passed in 54.73s |
| The MC-06 files: `test_outreach_{gate,claim,decisions,email_kind,cards,greeting,send,approval}.py` | all pass |
| The reviewer repros (scratch copy of `tests/`, not committed): `test_stale_read_sends_unapproved_body`, `test_nfd_body_matches_nfc_approval` | 2 passed. Both assert that the gap exists |
| `git merge-tree` of 06 against `crew/mission-control` (c2b468f), `-10-app-factory-kinds` and `-11-remote-core` | all clean |
| Changed paths under `inputs/`, `design-system/`, `.env`, `data/growth/`, `config/` | none |
| E14: `config/settings.yaml` `approvals.discord_buttons`; `config/scout.yaml` `mode` on the branch head | `false`; `shadow` |

## Standards

- **should fix, S1.** `send.py:518` builds the email before the claim, and `send.py:543-546` sends it after the claim. The module docstring for step 8 and `_claim`'s docstring both say the claim guarantees "what goes out is still what was approved", but the code doesn't do that (see B1). Fix the code, not the docstring.
- **nit, S2.** `approval.py` `_canonical` NFC-normalises every field before hashing. The ticket says the hash covers the recipient, subject and `draft_body`. Normalising widens the match beyond those bytes (see Sec2).
- **nit, S3.** `send.py:557`: `attempts = message["attempts"] + 1` relies on `message` being the pre-claim read while `_claim` already wrote `attempts + 1`. The comment says so, and the value is consistent today. It breaks if B1's fix re-reads the row inside the claim, so derive it from the row the claim returns.

No new dependency, and nothing reimplements an existing helper. `role_addresses.is_shared_inbox`, `paths.is_within`, `db.transaction` and `store.add_business_days` are all reused.

## Spec

All of the ticket's acceptance criteria have a test, and the tests pass. I checked these against the code:

- **AC-M8.1 and send without approval.** With `approved_only`, `due()` lists only messages with an `approved` record. `_claim` → `approvals.use()` refuses pending, expired, superseded and used records (`test_live_send_due_sends_nothing_while_the_request_is_pending`).
- **AC-M8.2, AC-M8.3, AC-M8.13 and requeue-shadow flooding.** `raise_due` raises at most `quota("live") - open_requests` requests, only for messages due by today (`send_after <= today`), inside `BEGIN IMMEDIATE`. `test_requeue_shadow_in_live_mode_raises_requests_only_up_to_todays_quota` and `test_a_follow_up_raises_no_request_until_its_day` cover them.
- **AC-M8.11 and live mode with `discord_buttons: false`.** `approval_gate_problem()` is the first entry in `live_problems()`, so `_send_due` refuses, `raise_due` raises nothing, and `switched_off` makes `use()` refuse without claiming (`test_no_request_is_raised_while_the_buttons_are_off`, parametrised over the commands).
- **AC-M8.12 and the caps after approval.** Every existing check (window, quota, per_run, gap, spacing, registry, D1 sync, blockers, the follow-up checks, the send-time brand gate) runs before `_claim`. The spacing probability uses the approved-only list (`test_the_spacing_probability_counts_approved_emails_only`).
- **Two send-due runs at once.** `SEND_LOCK` is held from `_send_due` through `raise_due`, and the claim runs under `BEGIN IMMEDIATE`. In G8, two connections claim the same record and exactly one wins.
- **An approval for one lead used for another.** The subject is `outreach_message:<id>`, and the content includes the recipient address. Messages are never deleted, so an approval cannot move to another lead.
- **AC-M8.4 to AC-M8.7, AC-M8.10 and follow-ups.** The skip, expire, lapse and shadow-sent lapse transitions match MC §5.7. `declined_by_ty` is in `FINAL_LEAD_STATUSES`. A follow-up needs its own approval, because it is its own subject.

Findings:

- **should fix, Sp1 (MC §5.8 / PRD line 559, "a retry of that same instance under its own idempotency key").** A claimed email whose send didn't complete is retried with no time bound. This covers a Resend `pause` (401/403 or quota), a `retry`, and a crash before the mark. `approval.claimed()` and `due(approved_only=True)` keep it eligible until it is sent or fails. Resend keeps an idempotency key for 24 hours. If an accepted send crashed before the mark, and outreach is then paused for more than a day, the retry after the unpause is a new email under an expired key: a second email to the prospect on one approval. The retry also goes out days past the approval's use-by. Fix: allow a retry only within the idempotency window (or until the use-by, whichever is sooner). After that, mark the message `failed` with a reason and alert. Add a test that steps the clock past 24 hours.
- **nit, Sp2.** `_nothing_waiting` calls `without_request()`, which counts messages due today with no request. When the reason is the quota rather than a missing request, "waiting for a request slot" is right. When outreach is paused, the earlier return in `_send_due` handles it. Fine as it is, noted only for the one-pager wording in 08.

## Security

- **blocking, B1 (the developer's hardening item; brief: "byte-for-byte what the claimed approval covers, checked inside the claim transaction").** `send.py:518` builds `email` from `message` (read by `due()` before the loop) and from `row` (read by `queue.recipient()` before the claim). `_claim` (`send.py:485-512`) then hashes a fresh read of the database through `content()` / `still_matches()`, and `send.py:546` sends the old `email`. Nothing in the transaction compares the bytes about to be sent with `record.content_hash`. I reproduced this with `test_stale_read_sends_unapproved_body`. In that test, `draft_body` differs when the run reads it and is restored before the claim. The claim succeeds and the Resend double receives the unapproved line. Today no code path rewrites `subject` or `draft_body`. `recipient()` takes the lowest contact id, and contacts are only ever inserted. So the gap needs an out-of-band write: a direct database edit, a future command, or a migration. The guarantee rests on convention, not on the claim, and so the hardening item stays must-fix. Fix: inside the `db.transaction` in `_claim`, re-read the message and the recipient row and build the email from those rows. Hash `(row.email, email.subject, email.draft)` with the same canonical form, and refuse unless it equals the claimed (or just-used) record's `content_hash`. Return that email to `_send_one` and send exactly that. Add the repro above as a regression test, for both the first claim and the retry.
- **should fix, Sec2.** `_canonical` NFC-normalises the values before hashing (`approval.py:52-54`). Two drafts with different bytes but the same NFC form hash the same: `test_nfd_body_matches_nfc_approval` passes. The visible text is the same, but it is not byte-for-byte. Hash the raw UTF-8, or normalise `draft_body` once when queueing and hash the stored bytes.
- **Checked, no finding.**
  - The `JURA_GROWTH_RESEND_BASE_URL` override is refused unless the URL is loopback `http` and the data folder is a temporary one outside `jurasolutions/`, and `live_problems()` lists it. The stub binds 127.0.0.1, refuses a non-temp data folder, and doesn't log the `Authorization` header (X13 tests).
  - The cards mask a named-person address, while the hash covers the full address. Drafts that greet a person or name the person behind the address are dropped by the `email` channel (AC-M12.2 tests). The privacy sweep runs over the cards.
  - SQL uses parameters everywhere. The f-strings interpolate only module constants.
  - No secrets in the diff, logs or events. Refusal texts pass through `store.mask`.

## Blocked paths

None touched. `config/` is unchanged, and both live switches remain off on the branch head (E14).

## Process note

This review covered both axes and the security pass by reading the code directly and running the reproductions. It did not use separate sub-agent runs, because the brief limited fan-out and the coordinator asked for the review to finish from where it had stopped. All 11 production and doc files were read in full. Of the 14 test files, `test_outreach_claim.py` was read in part and the rest were checked by test name and by running them.

## Release note (carried from the ticket)

Before rolling back past this merge, set `mode: shadow` in `config/scout.yaml`. An older `send.py` has no gate.
