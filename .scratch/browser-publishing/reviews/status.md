Feature: browser-publishing   Route: L   Phase: build (mission control's wave 1 running; nothing here started)   As of: 2026-10-25 19:35 SGT
Next decision for the user: start 01 (your Chrome profile and checks) now? Recommended: yes; it touches no code and gates 03.

Precondition: met. PR #1 (with blocker tickets 02 and 07) merged into `main` (855e48c); the tickets are on `crew/mission-control` (1acc1eb). G3 approved the breakdown at 19:22, and these tickets build on `crew/mission-control` as `crew/mission-control-bpNN`.

Ticket edits since G3: 02, 02b and 03 gained the sweep criterion; 03 now lists R2 and R3 before U12; 06 gained AC-P11.1's join identity (test strategy v3 Q9, Q10). None started; no edge moved.

Frontier (ready to start): 01 BP-01 Chrome profile setup and checks (ready-for-human, Ting Yu).

In flight: none.

Blocked (mission-control wave — blocked by — what would clear it):
  - 02 BP-02a publish queue for social posts — w4 — mission-control#01, mission-control#04b — both merged
  - 02b BP-02b community items — w5 — 02 — 02 merged
  - 03 BP-03 browser job, Facebook Page — w5 — 01, 02, mission-control#03, #08, #11 — 01's checks passed and the four merged; closes after R1, R2, R3, R4 and R6, then U12
  - 04 BP-04 Instagram and LinkedIn — w6 — 03 — 03 closed; and your weekend-posts answer (in the ticket)
  - 06 BP-06 joins as the Page — w6 — 03, 02b, mission-control#05 — all done; closes after R5 and U15
  - 05 BP-05 community posts as the Page — w7 — 03, 06, mission-control#05 — all done (06 first: a group must be joined as the Page before a post can go in as the Page); closes after U14

Done: none.

Critical path to the first real post: mission-control 01 and 02, 04, 04b, 11, then 03 here (w5), with 01 passed, then Ting Yu's R1 to R4, R6 and U12 on the Jura Facebook Page. The longest chain ends at 05 in w7.
Parallel lanes: 02 runs beside mission-control#06, #10 and #11; 02b beside 03; 04 and 06 together after 03. `runner.py` changes only in mission-control#01 and then 03. Numbering note: 05 now follows 06; the numbers are kept so the BP-05 and BP-06 ids in the PRD and test strategy stay stable.

Risks:
  - Meta or LinkedIn restrict or disable the accounts for automation — possible / high — Ting Yu (accepted, BP §4.1) — caps and gaps in `caps.py`; any stop signal pauses publishing
  - `--chrome` connects to the last-picked extension, which your own use can change — possible / high — Ting Yu — the dedicated profile (01) and the run's identity check (03)
  - The subdomain behaviour of `ClaudeInChromeDomain` is unknown, so 03's host list can't be final — certain until 01 — Ting Yu — 01's U18
  - An API key or setup-token in the launchd environment silently drops the Chrome tools — possible / medium — QA lead — 03's precheck skips with the reason and `status` lists it as a setup gap

Open questions:
  - Start 01 now? Recommended: yes.
  - Weekend posts, asked in 04 before Instagram and LinkedIn move to `browser`. Recommended: keep weekends on; turn `weekends: false` for all platforms if three weekend cards prove too many.
