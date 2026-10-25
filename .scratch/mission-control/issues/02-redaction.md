# 02 — MC-02 prefactor: redaction before anything reaches Discord

Status: ready-for-agent
Blocked by: - (precondition: the blocker fixes on `main` and the shared-files commit, as in 01)
PRD ticket: MC-02 in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC11, SC12 (the masking function)

## What to build

Every string the later tickets put in a Discord message passes through one masking path: blocker ticket 01's `config.redact()` with Keychain values loaded first, then the personal-data rule in MC §4.4. `discord.post()` redacts again on its own as the last line of defence. The suite gains the Discord double and one reusable sweep that every later message-building ticket calls from its own test file.

## What to change

- `config.load_secrets_for_masking()`, called once per process before building a one-pager, a run update or an approval card, so Keychain values are masked too.
- `privacy.for_discord(text)`: the masking in MC §4.4 on top of `config.redact()`. Role addresses stay; an address that names a person becomes `j***@example.com.sg` with its source page; phone numbers, a prospect's personal name, reply, bounce and complaint bodies, Ting Yu's own contact details and anything from `personal-finance/` never appear.
- `discord.post()` runs `config.redact()` on its content before `content_hash()`, using the values already loaded, and makes no Keychain lookup of its own. Messages keep `allowed_mentions: {"parse": []}`.
- `tests/discord_double.py`: the Discord double on `.invalid` URLs (accept, 500, 429, unreachable), recording every request.
- `tests/sweep.py`: `assert_clean(double, outbox, planted)`, which first asserts the double received the planted marker. Later tickets call it from their own test files and never edit a shared list. Neither file goes in `conftest.py` (01 owns that file in this wave, and the network guard).

## Acceptance criteria

- [ ] **AC-M11.1** Given `RESEND_API_KEY_OUTREACH=re_uat_9Xq7Lm2Pz` and a Keychain stub value
  `kc_uat_44Lw` planted in a summary, an error, a transcript, an email draft and remote output,
  then neither value, raw or URL-encoded, nor any 8-character piece of one, appears in any Discord
  payload, attachment or outbox file. The sweep first asserts the double received the planted
  marker message.
  *Owned here: the sweep, run over `discord.post()`, existing posts, alerts and the outbox. 03, 04b, 06, 08, 10, 11 and browser-publishing#02 call `assert_clean` over the messages they build.*
- [ ] **AC-M11.3** Then `discord.post()` redacts before computing its dedupe hash and makes no Keychain
  lookup of its own.
- [ ] **AC-M12.1** Given `jane.tan@example.com.sg`, `+65 9123 4567`, a prospect's personal name and
  the reply text "Please take us off your list" planted in summaries, errors, transcripts, drafts
  and reply rows, then none appears in Discord, and `j***@example.com.sg` appears with its source
  page.
  *Owned here: `privacy.for_discord()` with one table row per planted item, and existing posts. The same tickets as above plant into their own messages.*
- [ ] AC-M15.1 (owned by 01) still holds; its network-guard clause applies from 01's merge on.

## Done when

Every criterion above passes, the Discord double's "received at least one message" assertion exists and passes, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC §4.3, §4.4, §5.3 (`privacy.py`, `config.py`, `discord.py`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T7, T12
- `.scratch/mission-control/reviews/technical-v2.md`: N12, N13
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §2 (Discord double, Keychain double), §3 (D2 secrets, D3 personal data, H hostile text), §4.1 (AC-M11.1, AC-M11.3, AC-M12.1), §11.2 row MC-02
- Code: `jura_growth/config.py` (`redact`, `secret_values`), `discord.py`
