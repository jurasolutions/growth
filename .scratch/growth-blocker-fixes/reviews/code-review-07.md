# Code review 07: group rules that forbid days are read as forbidding them

## Round 3 (14614a8)

- **Branch:** `crew/growth-blocker-fixes-07-community-negated-days` at 14614a8 ("Leave day rules for Ting Yu to confirm instead of reading them in code"), on top of fe35657
- **Fixed point:** `crew/growth-blocker-fixes`, now 4a7859e, which includes ticket 01
- **Spec for this round:** the ticket, plus Ting Yu's decision "always confirm day rules" (`crew-log.md`, conductor entries at 16:50 and 17:03 on 2026-10-25)
- **Files read:** the full round-3 diff (`git diff fe35657 14614a8`): `rules.py`, `groups.py`, `plan.py`, `agents/community/__init__.py`, `migrations/0002_confirmed_days.sql`, `docs/community.md` and `tests/test_community.py`. That is every file in it. I also read `db.migrate` and, in the merged tree, ticket 01's `headless.claude_rules`. Line numbers below are from the worktree at 14614a8.

### Verdict: changes-requested

The new design is right, and nearly all of it works.

- **Every day-naming phrasing from both rounds is now closed.** That is 179 inputs: the round-1 and round-2 tables, my probes and the Spec agent's probes. Each one gives `names_days = True` and `parsed = False`. Both value posts and closing lines are refused on all seven days until Ting Yu confirms the days.
- **The migration is safe on a live `growth.db`.**
- **Rules with no day reference still parse as before.**
- **The branch merges cleanly with 4a7859e**, and the merged tree passes its tests.

**One gap is left, and it blocks.** The day detector misses several common ways of writing a day: a day inside a hashtag thread name, "wknd" and "wkend", "weeknights", and "week days" with a space. A rule like that is not treated as naming a day. Because it also carries a permission word, it parses as `promotion allowed` with `parsed = True` and every day open. And when Ting Yu sets `rules_confirmed=yes`, he is never asked for the days. That breaks the decision as recorded ("any rule naming a day"), and it breaks the new docs (`docs/community.md:96-98`). Over-detecting costs only one confirmation, so the fix is to loosen the detector (R3-B1).

### What I checked, and what it showed

| Check | Result |
|---|---|
| No day-naming phrasing opens a day without confirmation | **Holds for the parser's day vocabulary; fails outside it (R3-B1).** 201 distinct inputs went through `groups.rules_for` with no confirmed days. 179 are closed on every day for both kinds of post: all rows of both rounds' tables, `probe*.py`, `inputs4.txt` and the Spec agent's `inputs1-3.txt`. The 22 still open are the true no-day rules below, plus the R3-B1 and R3-S1 rows |
| Migration `community/0002_confirmed_days.sql` on a live-style database | **Safe.** It is two `ALTER TABLE ... ADD COLUMN ... TEXT` statements, nullable, with no default and no rewrite. `db.migrate` runs the file and its `schema_migrations` row in one `BEGIN`/`COMMIT` script. Test: the 4a7859e code built a database, added a joined group with "Promo Saturdays only." and `rules_confirmed=yes`, then the 14614a8 code opened it. The migration was applied once and the row was unchanged, with both new columns NULL. A second `migrate` applied nothing. The group came out closed on all seven days, with the "Ting Yu confirms the days" summary. No other branch adds a community `0002` (checked 4a7859e and the ticket 02 branch). An older checkout ignores the extra columns |
| Confirm path | `promo_days=sat` on its own stays closed, because both fields are required. `promo_days=sat post_days=any` opens promotion on Saturday and value posts on every day. `post_days=funday` is refused. `promo_days=none` gives `no_promo`. New rules text clears both columns. `rules_confirmed=yes` without days is refused while the text names days |
| Rules with no day still parse | "No self-promo." gives `no_promo`. "No links." gives `no_links`. "No promotion. No links." gives both. "Self-promotion is welcome." gives `promotion allowed`. "You cannot share links." gives `no_links`. "Be kind and respectful." gives `parsed = False` (rules_ok). "Promotion is allowed, but no spam." gives `no_promo`, the same as base. The existing parse table passes |
| Headless runs can't confirm days | In the merged tree, `headless.claude_rules("community")` denies `Bash(jura-growth community set)` and `set:*`, and does not allow them. `add-group` can't write the new columns, because `groups.FIELDS` doesn't include them |
| `git merge-tree --write-tree crew/growth-blocker-fixes crew/growth-blocker-fixes-07-community-negated-days` | Clean, exit 0, tree 7a4f327. Its pytest run: 779 passed |

### Standards

No findings.

- **Typecheck:** pyright errors per file, base against branch: `rules.py` 8 to 0, `groups.py` 3 to 3, `plan.py` 12 to 12, `__init__.py` 0 to 0. No new errors.
- **Commit message:** a plain sentence-case imperative, with a body that explains the decision.
- **Docs:** `docs/community.md` documents the new `set` keys and the closed-until-confirmed rule.
- **Reuse:** `read_days` builds on `days_in`.
- **Scope:** the migration and the two `set` keys go beyond the ticket, but they follow from Ting Yu's decision. The decision as logged says "parsed=False and needs rules_ok". The build is stricter: the group stays closed until Ting Yu confirms. That is the safe direction, and the 17:03 conductor entry records it.

### Spec

#### Blocking

- **Spec R3-B1. A day the detector doesn't recognise bypasses confirmation (`rules.py:36-38`, `ANY_DAY_RE`/`days_in`, used at `rules.py:204`).** `names_days` is set only when `DAY_RE`, `RANGE_RE` or `GROUPS_RE` matches, and all of them need word boundaries and exact spellings. The phrasings below name a day but are missed. Each parses as `promotion allowed`, with `parsed = True` and all seven days open. `_check_days_confirmed` (`groups.py:219-231`) never asks Ting Yu for the days. The results are the same on base, so the gap is pre-existing, but it breaks this round's own rule:

  | Rules text | 14614a8 |
  |---|---|
  | Self-promo is welcome on #SelfPromoSaturday. | promotion allowed, every day |
  | Promotion allowed in the #FridayPromo thread only. | promotion allowed, every day |
  | Promo allowed on wknds only. | promotion allowed, every day |
  | Self-promotion ok on wkends. | promotion allowed, every day |
  | Promo is fine on weeknights only. | promotion allowed, every day |
  | Ads welcome on week days. | promotion allowed, every day |

  Ting Yu's decision covers "any rule naming a day", and `docs/community.md:96-98` says such text "is never read into days by code ... no open day ... until Ting Yu sets" the days. PRD §5.2 asks for "none on a day its rules forbid".

  Fix: give `names_days` a looser detector of its own, and leave `read_days` strict. For example: full day names with no word boundary on the left (`(?:mon|tues|wednes|thurs|fri|satur|sun)day`), plus `\bwk?e?nds?\b`, `\bwkends?\b`, `\bweeknights?\b` and `\bweek\s+days?\b`. Over-detecting only asks Ting Yu for one confirmation, which is the direction he chose. Add the six rows above as tests.

#### Should fix

- **Spec R3-S1 (pre-existing). A promotion permission limited by something other than a weekday is read as a blanket permission (`rules.py:212-214`).** "Promotion allowed once a week.", "Self-promo allowed on the 1st of every month." and "Promo allowed on public holidays only." each give `promotion allowed`, with `parsed = True` and every day open. Only `#FridayPromo`-style thread rules overlap with R3-B1. Fix: when a promotion permission clause also says "only", "once", "thread", "month" or "holiday", return `parsed = False`, so the plan needs a `rules_ok` statement.

#### Nits

- **Spec R3-N1.** Misspelt or non-English day names ("Satuday", "Sabtu") are missed too. They can't all be listed, so R3-B1's looser detector won't catch every one. Ting Yu still reads the rules reminder in the checklist. No action beyond R3-B1.
- **Spec R3-N2 (pre-existing).** For a `no_promo` group, `context` reports `with_closing_line: true` on its open days (`__init__.py:232`). The reason is that `promo_days=none` maps to `no_promo` with `promo_days = None`. `link_allowed` is false, and `plan.py:366, 376` refuses the link and any mention of Jura, so nothing wrong can be planned. But the context view tells the run something misleading.

#### For the release notes

After this merges, every live group whose rules name a day and that Ting Yu already confirmed stops getting posts until he runs `jura-growth community set <id> promo_days=... post_days=...`. That is intended, but it is a human step after deploy.

### Security

No findings.

- **The UPDATE in `groups.set_fields` (`groups.py:212-214`) is safe.** It builds column names only from keys checked against `SETTABLE` (`groups.py:183-184`) and the fixed `DAY_COLUMNS` map, and binds every value as a parameter.
- **Day input is validated.** `read_days` refuses anything that isn't a day form.
- **The migration is static SQL.**
- **Headless runs can't write the confirmed days.** Ticket 01's `set` deny and `groups.FIELDS` see to that.

### Blocked paths and UI

- **Blocked paths:** none touched. The migration is a repo file. The migration test used scratch databases, never the live `jurasolutions/data/growth/`.
- **UI:** none.

### Evidence

- **Branch suite:** `uv run pytest` in the worktree at 14614a8, with temp data and outputs folders: 601 passed.
- **Community tests:** `tests/test_community.py`: 144 passed.
- **Merged tree:** `git merge-tree --write-tree` against 4a7859e is clean (7a4f327). `pytest` on that tree, using the worktree venv: 779 passed.
- **Invariant probe:** `scratchpad/rev/invariant.py` over `scratchpad/rev/all_uniq.txt` (201 inputs): 179 closed, 22 open. The open rows are listed above, in R3-B1, R3-S1 and the no-day rules. Output is in `scratchpad/rev/invariant_out.txt`.
- **Migration test:** a database built by the 4a7859e tree (`scratchpad/rev/base4a`), then opened by the 14614a8 code. Results as in the table above.
- **Typecheck:** pyright on the four touched modules, base against branch: 8/3/12/0 errors to 0/3/12/0.
- **Scratch folder:** all `scratchpad/` paths here are under `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/`.

---


## Round 2 (fe35657)

- **Branch:** `crew/growth-blocker-fixes-07-community-negated-days` at fe35657 ("Ban a clause's days only when the negation covers them"), on top of e35ddd7
- **Fixed point:** `crew/growth-blocker-fixes` (01ce0e9)
- **Files read:** the full fix-round diff (`git diff e35ddd7 fe35657`) for `jura_growth/agents/community/rules.py`, `tests/test_community.py` and `docs/community.md`. That is every file in it. Line numbers below are from the worktree at fe35657.

### Verdict: changes-requested

Every round-1 finding is fixed, and every row of my round-1 tables now gives `parsed = False`, the right days, or a safe refusal. But a fresh probe found one more wrong permission with the same root cause. When the negation comes *first* and is about something else, followed by a day permission, the clause is still read as a ban on the permitted day. "No links, promo on Fridays." opens every day but Friday, drops the links ban, and returns `parsed = True`. Base read these rules correctly.

**This shape was already in e35ddd7.** I missed it in round 1. My round-1 fix advice ("every day comes after the negation and nothing after the first day brings in another subject") didn't cover it, and the developer followed that advice exactly. The gap is in my advice as much as in the code.

### Round-1 findings, rechecked

| Finding | Status | Evidence |
|---|---|---|
| Spec B1, a permission followed by a negation | fixed | All 10 rows give `parsed = False`, except row 6, which also keeps `no_links`. Re-run probe |
| Spec B2, n't forms and except words that name no day | fixed for apostrophe forms | "Promotion isn't allowed on weekends." gives promotion Mon–Fri. The `unless`/`only` rows now give `parsed = False` |
| Spec S1, a links ban dropped in a day clause | fixed | "Promotion only on Saturdays, no links." gives Sat plus `no_links` (`_bans_links_on_every_day`, `rules.py:190-200`) |
| Standards S1, `_posts_only_on` duplicating `day_names` | fixed | `rules.py:112-113` now calls `day_names` |
| Standards N1, duplicated branches and data clump | fixed | `_DaySets` at `rules.py:203-220`, `ALL_DAYS` constant |
| Standards N2, docs | fixed | `docs/community.md:92-100` |
| Standards N3, `WEEKDAYS_ONLY` | fixed | Now `MON_TO_FRI` at `tests/test_community.py:17` |
| Standards N4, helper order | fixed | `_day_rule` at `rules.py:144`, above `parse` |
| The three audit sentences and the context/checklist tests | still met | |
| NEG_RE widening | still errs safe | "You cannot share links." gives `no_links`. "Promotion is allowed, but you must not spam." gives `no_promo`, the same as base does for "but no spam" |

### Standards

No new findings.

- **Typecheck:** pyright on `rules.py` reports 4 errors, at `rules.py:100` and `:284`. Both are the old unchanged `", ".join(day_names(...))` lines, so there are no new errors.
- **Commit message:** a plain sentence-case imperative with a body.
- **New helpers:** `_days_all_excepted`, `_bans_links_on_every_day` and `_DaySets` have docstrings and match the module's style.

### Spec

#### Blocking

- **Spec R2-B1 (a regression from this branch, already present in round 1).** When a negation about something else comes *before* a day permission, `_day_rule` reads the clause as a ban on the permitted days (`rules.py:166-175`). The checks at `:169` look only at what follows the first day, and at whether a day comes before the negation. Neither looks at what lies *between* the negation and the first day.
  - In "No links, promo on Fridays" the "no" negates "links", and a comma and a second subject ("promo") follow before the day.
  - `_bans_links_on_every_day` also misses the links ban here, because a day comes after "links".
  - PRD §5.2 asks for "none on a day its rules forbid". The ticket says "Mixed or ambiguous clauses come back `parsed = False`".

  All results below have `parsed = True` on the branch; base got them right.

  | Rules text | Base promo days | fe35657 promo days |
  |---|---|---|
  | No links, promo on Fridays. | fri | **every day but fri**, links ban lost |
  | No DMs, promo on Fridays. | fri | **every day but fri** |
  | No spam, self-promo on Saturdays. | sat | **every day but sat** |
  | No tagging, ads on weekends. | sat, sun | **mon–fri** |
  | Don't spam, promotion on Fridays. | fri | **every day but fri** |
  | Never post links, promo thread on Sundays. | sun | **every day but sun**, links ban lost |
  | No selling, but promo thread every Sunday. | sun | **every day but sun** |

  The last row is the common "No promo. Promo thread on Sundays." rule, written with a comma instead of a full stop.

  **Fix:** return "ban" only when the text between the negation and the first day mention holds the clause's one subject and no clause break: no comma, dash, colon, "but" or "and", and no second subject. Return "unclear" for everything else. "Don't hesitate to share promo on Fridays." would then still read as a ban on Friday. That is a wrong refusal, which is acceptable. Add the seven rows above as regression tests.

#### Should fix

- **Spec R2-S1 (pre-existing). Contractions typed without the apostrophe still invert, with `parsed = True`:**
  - "Promotion isnt allowed on weekends." gives promotion only on sat, sun.
  - "Promos arent permitted on Sundays." gives promotion only on sun.
  - "Promotion wont be tolerated on weekends." gives promotion only on sat, sun.

  The new `\w+n['’]t` at `rules.py:50` needs the apostrophe; "dont" and "cant" are already covered without one. Fix: allow the apostrophe to be missing for `isnt|arent|wasnt|werent|wont|doesnt|didnt`. A bare `\w+nt` would also match words like "want" and "event".

- **Spec R2-S2 (pre-existing). Negative words outside the negation list still invert, with `parsed = True`:**
  - "Avoid promo on weekends." gives promotion only on sat, sun.
  - "Weekends are promo-free." gives promotion only on sat, sun.
  - "Refrain from promotion on Sundays." gives promotion only on sun.

  These are negative clauses in plain English, but they use words rather than grammatical negation. That is why they rank below round 1's B2. Fix: add `avoid|refrain|off[- ]limits|\w+-free` to NEG_RE, with tests.

#### Nits

- **Spec R2-N1 (pre-existing, rare phrasing).** "No promotion on weekdays only." gives promotion Mon–Fri, and "No promotion only on weekends." gives promotion Sat–Sun. `ONLY_DAYS_RE` treats "only" next to the days as an exception even when it limits the ban. Both phrasings are ambiguous. "Unclear" would be safer whenever "only" follows a negation with no comma between them.

#### Accepted

- **Day permissions that come after the subject now go to `rules_ok`.** "Promotion on Sundays is not allowed." and "Promotion is only for Fridays, not weekends." now give `parsed = False`. That is the "ask" direction and costs one `rules_ok` sentence. Base read the first one as a permission.

### Security

No findings. The fix round adds only regex constants built from the module's own static patterns, a dataclass and pure helpers. There are no new sinks.

### Blocked paths and UI

- **Blocked paths:** none touched. The round-2 diff changes `rules.py`, `tests/test_community.py` and `docs/community.md` only.
- **UI:** none.

### Evidence

- **Full suite:** `uv run pytest` in the worktree at fe35657, with `JURA_ROOT` set and temp data and outputs folders: 565 passed in 19.9s.
- **Community tests:** `uv run pytest tests/test_community.py`: 108 passed.
- **Typecheck:** `pyright --pythonpath .venv/bin/python jura_growth/agents/community/rules.py`: 4 errors, at lines 100 and 284 (pre-existing).
- **Probes:** every round-1 probe was re-run against fe35657 (`probe.py`, `probe2.py`, `probe3.py`), plus 30 new inputs (`probe4.py` with `inputs4.txt`), all in `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/rev/`.
- **Root cause in round 1:** the R2-B1 rows give the same wrong days on e35ddd7 (`scratchpad/rev/r1/`).

---

## Round 1 (e35ddd7)


- **Branch:** `crew/growth-blocker-fixes-07-community-negated-days` (e35ddd7)
- **Fixed point:** `crew/growth-blocker-fixes` (01ce0e9), which is also the merge-base
- **Spec:** `issues/07-community-negated-day-rules.md`, audit C-B1 in `audit/code-review-03-social-community.md`, repro `audit/repro/test_verify_social_community.py::test_negated_day_rules_are_inverted`, community scout PRD §1 and §5.2
- **Files read:** `jura_growth/agents/community/rules.py` and `tests/test_community.py`, which are every file in the diff. I also read the consumers, `agents/community/__init__.py:205-245` and `plan.py:350-392, 600-620`, and the docs in `docs/community.md:86-105`. Line numbers below are from the worktree.
- **Weighting:** as the brief asks, a wrong permission (a forbidden day offered with `parsed = True`) counts far worse than a wrong refusal or a `parsed = False` that sends the plan to `rules_ok`.

## Verdict: changes-requested

The branch fixes the three sentences the audit named, and it meets every acceptance criterion that names a test. But the new `_day_rule` creates a fresh wrong permission, Spec B1. Base read these rules correctly. When a day permission is followed by any unrelated negation, the branch reads the permitted day as the one banned day and opens the other six, with `parsed = True`. One example is "Promo on Saturdays, no links." Two pre-existing forms of the same C-B1 inversion also survive, Spec B2. The ticket's own "What to change" text covers both. Either finding blocks on its own.

**The NEG_RE widening stays within the ticket and errs safe.** See "Accepted scope" under Spec. Keep it.

## Standards

### Blocking

None. Two rules from the operating card pass:

- **Typecheck.** `docs/agents/crew.md` says "don't add new errors in files you touch". Pyright on `rules.py` reports 8 errors on base and 4 on the branch. The 4 left are at `rules.py:93` and `:245`, on unchanged lines. Routing the post-days text through `_posts_only_on` removed two of the old errors.
- **Commit voice.** "Read group rules that forbid days as bans, not permissions" is a plain sentence-case imperative.

### Should fix

- **Standards S1 (reuse). `rules.py:105-106`: `_posts_only_on` re-implements `day_names` (`rules.py:101-102`) inline as `WEEKDAYS[d] for d in sorted(days)`.** The reuse rule makes a second copy of an existing helper a should-fix. The likely reason for the copy is that `day_names` returns `list[str] | None`. Fix: call `", ".join(day_names(days) or [])`, or give both functions one helper that never returns None.

### Nits

- **Standards N1. Possible Duplicated Code and Data Clumps (a judgement call).** The same "banned, else permitted" branch appears three times, at `rules.py:161-167`, `176-179` and `187-190`. Then `194-205` merges promotion and posts with the same "permitted days, or all seven, minus the banned ones" pattern. `promo_days`/`promo_banned` and `post_days`/`post_banned` always travel together (`rules.py:142-145`). A small accumulator with `add(days, banned)` and `resolve()` would collapse all of these. `set(range(7))` is written out at `:198`, `:205` and `:133`.
- **Standards N2. `docs/community.md:92-96` is now incomplete.** It still lists only the old parses. The module docstring (`rules.py:3-9`) now says that "no promotion on weekends" means Monday to Friday, and that a clause which both permits and bans days needs `rules_ok`. Ting Yu reads the doc, so add one sentence to it.
- **Standards N3. `tests/test_community.py:166`: `WEEKDAYS_ONLY` means Monday to Friday, but `rules_mod.WEEKDAYS` holds all seven days.** A name like `MON_TO_FRI` reads more clearly. It is also defined mid-file, while the other test constants sit near the top.
- **Standards N4. `rules.py:211`: `_day_rule` is defined after its caller `parse`.** The module's other helpers (`_day`, `days_in`, `_posts_only_on`) sit above theirs.

## Spec

### Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| "No promotion on weekends." gives promotion Mon–Fri; "No posts on Sundays." gives posts Mon–Sat; "Promotion allowed Monday to Friday. No links on weekends." gives promotion Mon–Fri | met | `tests/test_community.py:172-175`; my probe agrees |
| The repro becomes a passing regression test | met in substance | The repro asserts the old behaviour. Run against the branch, it now fails at line 30 (`promo_days == {0..4}`), so the bug is gone. The inverse is kept at `tests/test_community.py:172-175`. 22 of the new cases fail on base `rules.py`, so the tests do catch the bug |
| The existing table still passes | met | `tests/test_community.py:135-154` passes (80 passed in the file) |
| "Planned as" and `days_open` follow the corrected result | met | `tests/test_community.py:508` (context) and `:527` (checklist) |
| `uv run pytest` passes | met | 537 passed |
| "A negative clause without an 'except' form makes its days forbidden" | **partial** | Spec B2 |
| "Mixed or ambiguous clauses come back `parsed = False`" | **partial** | Spec B1 and Spec S1 |

### Blocking

- **Spec B1 (a regression from this branch). `_day_rule` reads any clause that names days and contains a negation as a ban on all of those days. It never checks that the days fall under the negation (`rules.py:230-237`).** Its "unclear" test only catches days on both sides of a negation. So:
  - A permission followed by a negation about something else (DMs, spam, tagging, links, other days) flips the permitted day into the one forbidden day.
  - A permission that follows a ban is swallowed into the ban.

  The module's own docstring promises that a clause which "both permits and bans days" comes back unparsed. The ticket says "Mixed or ambiguous clauses come back `parsed = False`". The PRD (§5.2) asks for "none on a day its rules forbid", and §1 says groups "remove or ban members". All results below have `parsed = True` on the branch. "Promo days" means the days on which `day_problem(promotional=True)` allows a post.

  | # | Rules text | Base promo days | Branch promo days |
  |---|---|---|---|
  | 1 | Promo on Fridays, no DMs. | fri | **mon, tue, wed, thu, sat, sun** |
  | 2 | Promo on Fridays but don't spam. | fri | **mon, tue, wed, thu, sat, sun** |
  | 3 | Promo Fridays - please do not tag members. | fri | **mon, tue, wed, thu, sat, sun** |
  | 4 | Self-promo on Fridays, never on other days. | fri | **mon, tue, wed, thu, sat, sun** |
  | 5 | Promo on Fridays, you cannot promote on other days. | fri | **mon, tue, wed, thu, sat, sun** |
  | 6 | Promo on Saturdays, no links. | sat (link ban lost) | **every day but sat** (link ban lost) |
  | 7 | Sales posts on weekends, never during the week. | sat, sun | **mon–fri** |
  | 8 | No promo on weekends, promo Fridays. | fri, sat, sun | **mon–thu** (Friday refused, Mon–Thu opened) |
  | 9 | No promotion on weekends, Fridays are for promo. | fri, sat, sun | **mon–thu** |
  | 10 | 1) No promo on weekends 2) Promo on Fridays | fri, sat, sun | **mon–thu** |

  - **Rows 1–7 are regressions:** base got them right. Row 6 is ordinary group-rules phrasing.
  - **Rows 8–10 were already wrong on base**, which offered the forbidden weekends. The branch now offers Monday to Thursday, which the rules never permit, and it doesn't ask.
  - **The widened NEG_RE is not the root cause.** It is involved only in row 5. Rows 1–4 and 6–10 use words that base already treated as negations.

  Fix: return "ban" only when every day mention comes after the negation, and nothing after the first day brings in a second promotion, post or link subject or a permission. Return "unclear" for everything else. "Weekends: no promo." then becomes `parsed = False`, which is the safe direction. Add rows 1, 6, 7 and 8 to `test_a_clause_that_both_permits_and_bans_days_needs_a_person`.

- **Spec B2 (pre-existing, but inside the ticket's own "What to change" text). Two forms of the C-B1 inversion survive with `parsed = True`.** The output is the same on base and on the branch:
  - **Negations the regex doesn't know.** "Promotion isn't allowed on weekends." gives promotion only on sat, sun. "Promos aren't permitted on Sundays." gives promotion only on sun. `NEG_RE` and `DAY_NEG_RE` (`rules.py:47-54`) list only don't, can't, mustn't and shouldn't, plus a bare "not". So isn't, aren't, won't and any other n't form fall through to "allow". This is a negative clause without an except form, the exact case the ticket's first "What to change" sentence covers. The developer already widened this regex, so adding a general `\w+n['’]t` costs nothing.
  - **An except word that excepts no day.** At `rules.py:233-234`, `_day_rule` returns "allow" whenever any `EXCEPT_RE` word appears in the clause, including "only" anywhere in it, even when no day follows that word:
    - "No links on weekends unless approved by admin." gives promotion only on sat, sun.
    - "Promotion is not allowed on weekends unless it is in the weekly thread." gives promotion only on sat, sun.
    - "Only admins can approve posts, no promo on weekends." gives promotion only on sat, sun.

    These clauses are at best ambiguous, and the ticket sends ambiguous clauses to `parsed = False`. Fix: return "allow" only when a day follows the except word (for "only", when it sits next to the days). Return "unclear" otherwise. Add these inputs as tests.

### Should fix

- **Spec S1 (pre-existing). A links ban in a clause that names promotion days is dropped (`rules.py:174-185`, `elif negative and not days`).** "Promotion only on Saturdays, no links." parses as promotion on Saturday, with `no_links = False` and `parsed = True`. So `community context` reports `link_allowed: true` (`__init__.py:238`), and `plan.py:360-370` lets a link through. The B1 fix would turn the "Promo on Saturdays, no links." form into `parsed = False`, but the "only" form survives because of B2's second point. Fix: when a negation sits in front of the link word, set `no_links` even when the clause names days, or mark the clause unclear. This clause mixes a permission with a ban, so the ticket's "mixed or ambiguous" line covers it, but it is a link rule, not a day inversion. That is why I rank it below blocking.

### Accepted scope

- **The NEG_RE widening (`rules.py:47-51`) stays within the ticket and errs safe.** The ticket's fix depends on recognising negative clauses, so widening the list is in scope. In clauses that name no day, a negation can only ever produce a ban (`rules.py:168-170, 181-183`):
  - "You cannot share links." was `parsed = False` on base. It now reads as `no_links`, which is correct.
  - "Promotion is allowed, but you must not spam." now reads as `no_promo`. That is a wrong refusal, but base already did the same for "but no spam" and "but do not spam" (reproduced). The widening only extends an existing safe-side behaviour.
  - In clauses that name days, the widening matters only through the B1 scoping bug (row 5). It is not a cause of its own.
- **Other changes that are fine:**
  - an empty `post_days` frozenset with the text "no posts on any day";
  - the rule that a day ban never lifts a blanket ban;
  - the rule that a ban covering every permitted day becomes `no_promo`.

## Security

No findings.

- **The diff has no injection, file, process or secret sinks.** It touches only `rules.py`, a pure regex parser over the stored `promo_rules` text, plus tests.
  - `rules.py` imports only `re` and `dataclasses`.
  - Nothing reaches SQL, a subprocess, the filesystem, the network, `eval` or a secret.
  - `DAY_NEG_RE` is built from the static `NEG_RE.pattern`, not from any input.
- **The safety question here belongs to the domain.** A misread rule can get Ting Yu removed from a group. That is covered under Spec B1 and B2, not here.
- **The `security-review` skill collected the wrong diff.** It gathered the base branch against `main` (the audit and setup docs), not this ticket. I ran the pass by hand on the correct two-file diff. The brief's two-sub-agent cap was already used by the two-axis review.

## Blocked paths

None touched. The diff changes `jura_growth/agents/community/rules.py` and `tests/test_community.py` only. All test runs used temp data and outputs folders, and nothing was posted to Discord.

## UI

No UI files changed, so `crew:web-design-review` did not apply.

## Evidence

- **Full suite:** `uv run pytest` in the worktree, with `JURA_ROOT` set and temp `JURA_GROWTH_DATA_DIR`/`JURA_GROWTH_OUTPUTS_DIR`: 537 passed in 21.7s.
- **Community tests:** `uv run pytest tests/test_community.py`: 80 passed.
- **Branch tests against base `rules.py`:** the branch's `tests/test_community.py` run against base `rules.py` in a scratch copy: 22 failed. That confirms the new tests catch C-B1.
- **Audit repro against the branch:** fails at line 30 with `frozenset({0, 1, 2, 3, 4}) == frozenset({5, 6})`. The inverted behaviour is gone.
- **Typecheck:** `pyright --pythonpath .venv/bin/python jura_growth/agents/community/rules.py`: 4 errors on the branch (lines 93 and 245, unchanged), 8 on base.
- **Probe scripts:** the B1, B2, S1 and widening rows were reproduced on both base and branch with `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/rev/probe.py`, `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/rev/probe2.py` and `/private/tmp/claude-501/-Users-tingy-OneDrive-Desktop-projects-jurasolutions-repos-growth/d6daf64b-57e5-467e-9f34-aee2699f7f0f/scratchpad/rev/probe3.py`.
