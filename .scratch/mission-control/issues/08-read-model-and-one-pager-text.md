# 08 — MC-08 the read model and the one-pager text

Status: ready-for-agent
Blocked by: 07, 04
PRD ticket: MC-08 in `prd-jura-mission-control-2026-10-25.md` §5.12
Covers: SC1 (the text), SC11 (AC-M11.2), SC13; the one-pager halves of AC-M2.4, AC-M3.3, AC-M5.2, AC-M6.4 and AC-M8.5; ADR 0002

## What to build

`jura-growth one-pager --no-post` prints the one-pager's text: the header, Needs you (the health strip), Approvals waiting, Today, Yesterday and Ask me, in that order. It reads `growth.db` read-only and never repairs it, so a stale journal or a missing table is a line, not a crash. `jura-growth status` and the health strip list the same setup gaps from one shared function, and plug-ins add their own gaps and "Needs you" lines through two hooks, so the core never imports an agent. Posting, the PNG and the 08:00 job are 09.

## What to change

- `mission.py`: the read model. A `Source` (db path, data, outputs and PRD folders, clock) in; plain dataclasses out. It opens `sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)` with `PRAGMA query_only = ON`, fetches and closes before rendering; never `db.connect()`, `db.session()`, `immutable=1`, a `journal_mode` pragma or a job lock. It reads `approvals` rows with its own `SELECT`s (stored status, deadlines, `posted_at`, `decided_origin`) and treats a request past its decide-by or use-by as lapsed by comparing with `now_sgt()`. It never calls `approvals.py` functions or a kind's `content()`, which may supersede, a write. Every string it returns is redacted.
- **Two optional plug-in hooks**, documented in `agents/__init__.py`: `setup_gaps() -> list[Gap]` (names and booleans only), read by `health.setup_gaps()` and so by `jura-growth status`; and `health(conn) -> list[str]`, extra "Needs you" lines, called with the read-only connection, so a write raises. A `REQUIRED_SETTINGS` attribute beside `NAME` in each plug-in's `__init__.py` is the shorthand the default `setup_gaps()` reads. 10 and browser-publishing#03 implement the hooks.
- `health.py`: `setup_gaps()`, install state through an injected `installed` callable, and the other health-strip items in MC §5.4. `cli.status` calls `setup_gaps()`; its output is otherwise unchanged.
- `one_pager.py`: the text builder, through `privacy.for_discord()` and `discord.split()` past 2,000 characters; `digest.spend(conn, day)` for spend yesterday and so far today. AC-M1.3 and AC-M1.4 seed rows with the kind names `outreach-email` and `social-post`; the read model never imports a kind.
- Call 02's `assert_clean` over the one-pager text.
- ADR 0002 moves to accepted.

## Acceptance criteria

- [ ] **AC-M1.2** Given nothing in the health strip, when the one-pager is built, then "Needs you"
  reads "Nothing needs you".
- [ ] **AC-M1.3** Given 4 pending `outreach-email` requests (the oldest A-0101, decide-by 2026-11-10
  16:30) and 1 pending `social-post` request, when the one-pager is built, then "Approvals
  waiting" shows "outreach-email 4, social-post 1", names A-0101 as the oldest, and lists all five
  as lapsing before the next one-pager.
- [ ] **AC-M1.4** Given a `social-post` request whose 18:00 decide-by passed yesterday and no write
  since, when the read model builds the one-pager, then it is not counted as waiting.
- [ ] **AC-M11.2** Given an unset key, then its setup-gap line reads "`RESEND_API_KEY_OUTREACH`: not
  set"; every gap line matches `NAME: set`, `NAME: not set` or `Discord: n of m webhooks`.
- [ ] **AC-M13.1** Given a stat snapshot of the temp data, outputs and PRD folders, with and without a
  hot journal, when the one-pager's read model runs, then nothing changed, and with the hot journal
  the "unfinished write" line appears.
- [ ] **AC-M13.2** Given `db.connect`, `db.session` and `paths.writable` patched to fail, when the read
  model runs, then none is called, no job lock is taken, and a missing `growth.db` or unmigrated
  table is a line, not a crash.
- [ ] **The text half of AC-M1.1 (owned by 09).** `one-pager --no-post` gives the header "Tue 10 Nov, as of 08:00 SGT", then Needs you, Approvals waiting, Today, Yesterday, Ask me, split only past 2,000 characters.
- [ ] **One-pager halves of earlier criteria.** The read model feeds each record to the classifier once (AC-M2.2); the jobs-not-installed list (AC-M2.4); the PAUSE file under Needs you (AC-M3.3); an unposted request listed as unposted (AC-M5.2); a note that a decision came from Terminal (AC-M6.4); an approved request that lapsed unused, listed (AC-M8.5).
- [ ] **X15.** Spend yesterday and so far today are sums of recorded `cost_usd` either side of SGT midnight, never projected; Yesterday equals `digest.build()` for yesterday.
- [ ] **Shared gaps.** `jura-growth status` and the health strip list the same gaps from one fixture, including a plug-in's `setup_gaps()`, and `status` output is unchanged apart from the gap lines (golden from `main`). A plug-in `health()` line appears under Needs you, and a write inside it raises.
- [ ] The sweep over the one-pager text finds no planted secret or personal data (AC-M11.1 and AC-M12.1, owned by 02).
- [ ] `docs/adr/0002-the-read-model-never-repairs-growth-db.md` says accepted.
- [ ] AC-M15.1 (owned by 01) still holds.

## Done when

Every criterion above passes, the structure greps in test strategy v3 §11.1 return no hits for `mission.py`, D4's hot-journal self-check passes, `uv run pytest` passes, and the report is in. Then wait for go-ahead.

## Pointers

- PRD: MC SC1, SC13, §4.2, §5.4, §5.3 (`mission.py`, `health.py`, `one_pager.py`, `digest.py`)
- `.scratch/mission-control/reviews/tickets-technical.md`: T5, N8
- `.scratch/mission-control/reviews/technical-v2.md`: N1; `technical.md` C1 (carried over)
- `.scratch/mission-control/reviews/test-strategy-v3.md`: §4.1 (AC-M1.1 to AC-M1.4, AC-M11.2, AC-M13.x), §4.3 (X15), §3 (D1, D4, D5, D6), §11.1, §11.2 row MC-08
- `docs/adr/0002-…`; `CONTEXT.md` (One-pager, Health strip, Setup gap, Install state)
- Code: `jura_growth/db.py`, `digest.py`, `cli.py` (`status`), `discord.py` (`split`), `agents/__init__.py`
