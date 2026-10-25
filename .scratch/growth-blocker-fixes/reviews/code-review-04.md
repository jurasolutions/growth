# Code review 04: the numbers rule catches figures written as words

## Round 2 (62c7ae5, 6f348e9)

**Verdict: changes-requested.** There is one blocking finding (R2-B1), and the round-1 fix introduced it.

- **What is fixed:** all of round 1's B1 and S1 to S4, plus the duplicated ceiling.
- **What broke:** the new "of you / of us / of them" exemption lets a spelled-out team size or client count through in a sentence about Jura, while the digit form fails. I recommended that exemption in round 1 (S4). My recommendation was too broad, and the hole is mine as much as the developer's.

- **Head:** `crew/growth-blocker-fixes-04-numbers-rule-words` at 6f348e9
- **Round-2 diff:** `git diff cb87ac6 6f348e9`, which changes `jura_growth/brand_check.py`, `tests/test_brand_check.py` and `prompts/social.md`. I read all three in full.
- **Line numbers** refer to the branch, as checked out in the developer worktree.

### Evidence

All runs used `JURA_ROOT=/Users/tingy/OneDrive/Desktop/projects/jurasolutions`, with fresh scratch folders for `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR`. The worktree stayed clean.

- `uv run pytest` in the worktree printed **557 passed**.
- I ran the branch's `tests/test_brand_check.py` against the fixed-point `brand_check.py`. It printed **24 failed, 105 passed**: the 14 must-fail tests from round 1 plus the 10 new must-fail cases. The new must-pass tests and the crash test pass on the old code too, as expected.
- Pyright on `brand_check.py` and `tests/test_brand_check.py` printed **0 errors**.
- I re-ran the round-1 probe set (92 sentences) and a new set of 28 sentences aimed at the round-2 changes.

### Round-1 findings, checked again

| Finding | Status | Evidence |
|---|---|---|
| B1 "per cent" | fixed | "We cut admin by forty per cent.", "Jura automates ninety per cent of your invoicing.", "Our clients see a hundred per cent accuracy." and "Most SMEs lose thirty per cent of their week to admin." all fail. "We post two per week." fails, the same as its digit form. |
| S1 hedges | fixed | "twelve or more", "twelve or fewer", "forty or so clients", "two or three processes" and "two or more businesses" all fail, in sentences about Jura. |
| S2 vague scales | fixed | "a couple of dozen", "several hundred", "a few dozen", "some thousand", "many hundred" and "a couple of thousand" all fail (`VAGUE_FIGURE_RE`, brand_check.py:402-406). |
| S3 lookalike crash | fixed | "ſixty" and "ſeven" return a result with no exception (`re.A`, :406 and :427). A regression test exists. |
| S4 false positives | fixed | "the two of you", "These two matter most to us." and "…the two fit together for us." all pass. |
| S-std1 ceiling | fixed | `SMALL_COUNT_MAX` (:398) is used by both the word path and `_is_small_count`. |
| N-std2, N-std3 | fixed | Clearer names (`COUNTS_NOTHING_AFTER`, `CARDINAL_WORDS_RE`, `VAGUE_FIGURE_RE`), and the `_Figure` NamedTuple. |
| N-std5 social.md | fixed | The bullet is rewrapped and now says "any sentence with a figure". |
| S5 ordinals, N1 suffix compounds, N2 predicate counts and zero | open, documented | These are now listed as known limits in the comment block (:427-437). Still follow-ups, not defects on this ticket. |
| "one or two <noun>" | passes | This matches the conductor's ruling in `crew-log.md`. "one or two hundred invoices" and "one or two dozen businesses" still fail, which is correct. |

No regressions on the should-pass side. The sentences that still fail are exactly the round-1 "within the G2 boundary" list.

### Standards

No hard violations. Both commit messages are sentence-case imperatives, and pyright shows no new errors.

- **Nit:** "dozen" is still spelled out by hand in `_CARDINAL` (:420), while the large scales are built from `SCALE_WORDS`. This does no harm.

### Spec

#### Blocking

- **R2-B1. The "of you / of us / of them" exemption passes counts about Jura that the digit path fails.**
  - **Where:** `OF_PEOPLE_RE` (:429) and the early return in `_counts_a_noun` (:599-600). These apply to any number word, with or without "the" in front.
  - **Reproduced on 6f348e9:**
    - "There are twelve of us at Jura." passes, but "There are 12 of us at Jura." fails.
    - "We have helped forty of them go live." passes, but "We have helped 40 of them go live." fails.
    - "Forty of you have booked a call with us." passes.
    - "We have helped two or three of them." passes.
  - **Why it blocks:** "forty of them go live" is a client count and a results claim, and "twelve of us" is a team size stated as a figure. Both break the ticket's "a spelled-out figure is treated like a digit figure: it needs a source or an approved claim" and the design-system §3 numbers rule. The round-1 bypass was blocking for the same reason.
  - **Fix:**
    - Exempt "of you/us/them" only when "the" comes straight before the number word ("the two of you", "the three of us"). Count it in every other case.
    - Add the four sentences above as must-fail tests.
    - Keep "We'd like to meet the two of you." as a must-pass test.

#### Should fix

- **R2-S1. Verb-list words that are also nouns let a count through after a possessive.**
  - **Where:** `VERBS_AFTER_A_NUMBER` (:432-435) holds words such as help, work, sync, cost, add, share, run and link. `DETERMINER_BEFORE_RE` (:431) includes our, your, their, its and my.
  - **Reproduced:** each of these passes in a sentence about Jura:
    - "Our two help desks answer within the day."
    - "Our twelve work streams run in parallel."
    - "Our forty sync jobs run each night."
    - "Our twenty cost centres sit in one sheet."
    - "Our forty add-ons run on your tools."
    - "All twelve share one login with us."
  - **Fix:** drop the possessives from `DETERMINER_BEFORE_RE`. The cases R2-S1 set out to rescue ("these two matter", "the two fit") use the, these, those, both or all. "Our twelve …" is the place a Jura figure lives.
  - **Optional:** also drop the noun-ambiguous words (help, work, cost, add, sync, link, show, run) from the verb list.
  - **Tests:** add "Our forty sync jobs run each night." as a must-fail test.

#### Nit

- "We have helped a couple of businesses go live." passes, because "a couple" (2) isn't matched unless a scale follows it. That is outside G2, which flags number words only, so log it with the S5 follow-up.

### Security

The round-2 diff adds only regexes and pure functions over agent-written text. It has no I/O, SQL, subprocess calls, secrets or auth, and no vulnerabilities. Adding `re.A` removes the round-1 crash, so `check()` no longer raises on lookalike letters. R2-B1 is a bypass of a compliance control, and it is ranked under Spec.

### Blocked paths

None touched. The round-2 diff changes only `jura_growth/brand_check.py`, `tests/test_brand_check.py` and `prompts/social.md`.

---

## Round 1 (06d7b12, cb87ac6)

**Verdict: changes-requested.** There is one blocking finding (B1). The branch writes "forty per cent", the way Singapore English spells it, and the result passes even in a claim about Jura, while "40 per cent" fails. Everything else is should fix or nit.

- **Branch:** `crew/growth-blocker-fixes-04-numbers-rule-words` (06d7b12, cb87ac6)
- **Fixed point:** `crew/growth-blocker-fixes` (merge-base 01ce0e9). Diff: `git diff crew/growth-blocker-fixes...crew/growth-blocker-fixes-04-numbers-rule-words`
- **Changed files, all read in full:** `jura_growth/brand_check.py`, `tests/test_brand_check.py`, `prompts/app-factory.md`, `prompts/community.md`, `prompts/scout.md`, `prompts/social.md`
- **Spec:** `issues/04-numbers-rule-spelled-out-figures.md`, the G2 boundary in `crew-log.md` ("flag number words two and above when they count a following noun; 'one' and 'a' on their own pass"), and audit finding B3.
- **Line numbers** in this section refer to the branch at cb87ac6.

### Evidence

All runs used `JURA_ROOT=/Users/tingy/OneDrive/Desktop/projects/jurasolutions`, with `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` set to fresh scratch folders. Nothing touched the live `data/growth/` or `outputs/growth/`, and the worktree stayed clean.

- `uv run pytest` in the worktree printed **541 passed**.
- I ran the branch's `tests/test_brand_check.py` against the fixed-point `brand_check.py`, extracted with `git archive`. It printed **14 failed, 99 passed**, so every new figure-must-fail test is a real regression test.
- I ran 92 probe sentences through the old and the new checker. The results follow below.
- The Spec reviewer ran 29 example strings from the four `prompts/*.md` files, both claim texts and both `match` phrases from `config/approved_claims.yaml`. Old and new results are identical for all of them.
- Pyright reports 0 errors in `brand_check.py` and `tests/test_brand_check.py`, before and after the change.

### Standards

No hard violations. The commit messages are sentence-case imperatives, as `docs/agents/crew.md` asks. The decision order is documented in the existing `# --- 7. numbers` block (brand_check.py:362-366). The tests follow the file's parametrized pass and fail style. The prompt lines meet design-system §3.

#### Should fix

- **S-std1. The `<= 12` small-count ceiling is written twice** (brand_check.py:504 and :569). If someone changes one and not the other, digits and words drift apart, which is exactly the parity this ticket exists to create. Put the ceiling in one constant. (Possible Duplicated Code.)

#### Nit

- **N-std1.** The scale words appear three times: in `SCALE_WORDS` (:410), spelled out by hand in `NUMBER_WORD_RE` (:413-417), and again in `_number_value` (:546). Build the pattern from the dict.
- **N-std2.** `NOT_COUNTED` (:423) doesn't say what it holds: the words after a number word that mean it counts nothing. `NUMBER_WORD_RE` and `WORD_FIGURE_RE` are near-identical names for different rules. (Possible Mysterious Name.)
- **N-std3.** Figures travel as a bare `(match, text, small)` tuple (:498-517). (Possible Data Clump.)
- **N-std4.** `approved_claim_texts()` (tests/test_brand_check.py:218) reloads the YAML that `approved_phrases()` already reads. "Most first automations go live within weeks." appears twice in that parametrize list.
- **N-std5.** In `prompts/social.md:65-69`, the edited bullet is ragged at line 68. It keeps the stale "were/well/wed" sentence, which the conductor has already logged as a follow-up. Its "any sentence with a digit" now leaves out number words.

### Spec

All acceptance criteria are met as written:

- Both B3 sentences now fail with `[numbers] A figure about Jura must be an approved claim`. They passed on the old code.
- "Most first automations go live within weeks.", "Start with one process." and every approved claim still pass.
- No prompt example and no existing test changed result.
- `uv run pytest` passes.
- There is no scope creep. The conductor asked for the cb87ac6 prompt lines.

The findings below come from the ticket's "What to change": "a spelled-out figure is treated like a digit figure: it needs a source or an approved claim".

#### Blocking

- **B1. "Per cent" spelled as two words lets spelled-out percentages through, even about Jura.**
  - **Where:** `per` is in `NOT_COUNTED` (brand_check.py:426). `_counts_a_noun` (:565) therefore treats "forty per cent" as counting nothing.
  - **Reproduced:**
    - "We cut admin by forty per cent." passes, but "We cut admin by 40 per cent." fails.
    - "Jura automates ninety per cent of your invoicing." passes.
    - "Our clients see a hundred per cent accuracy." passes.
    - "Most SMEs lose thirty per cent of their week to admin." passes.
    - "forty percent", as one word, fails, so the branch is inconsistent with itself.
  - **Why it blocks:** percentages are the figure design-system §3 names ("no ROI percentages"). "Per cent" is the standard spelling in Singapore copy, and the digit path already counts it as part of the figure (`FIGURE_RE` :395). This breaks the ticket's "treated like a digit figure" and the non-negotiable numbers rule.
  - **Fix:** when the next word is `per` and the word after it is `cent`, count it. Or drop `per` from `NOT_COUNTED`: "2 per week" already fails in a sentence about Jura, so parity holds either way. Add the four sentences above as failing tests.

#### Should fix

- **S1. Hedged counts pass, while the digit forms fail.**
  - **Where:** `_counts_a_noun` checks only the very next word (:556-565), and `or` is in `NOT_COUNTED`.
  - **Reproduced:** "We have helped twelve or more businesses." passes, but "…12 or more…" fails. "Jura has served forty or so clients." passes.
  - **Fix:** look past `or more`, `or so`, `or fewer` and `or three` to the noun.
- **S2. Approximate scales pass.** A bare `dozen` or `hundred` after a vague quantifier isn't matched.
  - **Reproduced:** each of these passes about Jura: "We have helped a couple of dozen businesses.", "…several hundred businesses.", "…a few dozen businesses." Meanwhile "dozens of businesses" fails through `WORD_FIGURE_RE`.
  - **Fix:** add bare `dozen`, `hundred` and `thousand` to `WORD_FIGURE_RE`, or match them after `several`, `a few`, `a couple of` and `many`.
- **S3. Unicode case-fold lookalikes crash the checker.**
  - **Where:** `NUMBER_WORD_RE` uses `re.I` without `re.A` (:417). It matches "ſixty" (long s) and "ı" (dotless i). `_number_value` then splits on `[a-z]+` and indexes `NUMBER_WORDS["ixty"]` (:552).
  - **Reproduced:** "We have helped ſixty businesses." raises `KeyError: 'ixty'`. "Jura has ſeven clients." raises `KeyError: 'even'`. The old code returned a result for both.
  - **Impact:** this fails closed. `gate()` calls `check` before any queueing or sending, and `runner.py:124` records the exception. But one character aborts the whole call, for example every item in a `community/plan.py:483` batch.
  - **Fix:** compile with `re.I | re.A`, and add a regression test.
- **S4. "The two of you" and a number word followed by a verb fail in ordinary Jura copy.** These are outside G2, because the number counts no noun.
  - **Where:** `of` counts by design (:426, `test_number_word_counting_through_of_fails`), and any word missing from the deny-list counts as a noun.
  - **Reproduced:** each of these fails as a figure about Jura and passed before: "We'd like to meet the two of you.", "These two matter most to us.", "Both of these work, and the two fit together for us."
  - **Why it matters:** "the two of you" is a natural line in an outreach email to co-founders, and every false positive costs a regeneration.
  - **Fix:** treat `of` followed by a pronoun (`you`, `us`, `them`) as counting nothing. The verb case can stay as a known cost, documented in the comment block. (Round 2: this recommendation was too broad; see R2-B1.)
- **S5. Ordinals used as counts pass.**
  - **Reproduced:** "We just signed our fortieth client." passes, but "…our 40th client." fails.
  - The ticket asks only for cardinal number words, so this is a follow-up rather than a defect on this branch. Log it with S2.

#### Nit

- **N1.** "forty-odd businesses", "twenty-plus clients" and "a twelve-strong team" pass through the hyphen exemption (:559). "40-odd" also passes on the digit path through `EXEMPT_PATTERNS`, so the hole is shared. Fix both together in a follow-up.
- **N2.** Some inputs fall outside the G2 wording. "We are a team of five." passes, with no noun after the number, while "…of 5." fails. "We promise zero errors." passes, while "0 errors" fails. Note them as known limits in the comment block.

#### Within the G2 boundary (for the PR body, not findings)

These now fail, as their digit forms already did. They are the cost of the G2 rule:

- "We'll send you two options." (the conductor accepted this one)
- "We'll give you two ways to switch it off."
- "We pick the two or three steps that take longest."
- "We reply within two business days."
- "We need about thirty minutes of your time."
- "Here are three ways to cut admin time." (a results verb)
- "Most owners make two mistakes when they price a job."
- "Two businesses I spoke to last week had the same problem."
- "Fifty years ago, invoices were paper."

### Security

- **Correct diff:** the `security-review` skill's built-in diff compared `crew/growth-blocker-fixes` with `main`, which is not this ticket. I ran the pass by hand on the ticket 04 diff instead.
- **No vulnerabilities.** The change adds regexes and pure functions over agent-written text. It has no I/O, SQL, subprocess calls, secrets, auth or personal data, and no new attack surface.
- **The crash:** the S3 crash fails closed, so it is a robustness finding, not a bypass.
- **Compliance, not security:** B1 is a bypass of a compliance control and is ranked under Spec.

### Blocked paths

None touched. The diff changes only `jura_growth/`, `tests/` and `prompts/`. `jurasolutions/inputs/`, `design-system/`, `.env` and the live `data/growth/` are untouched.

### Question for Ting Yu (answered)

Should "one or two <noun>" pass? The conductor answered yes, as within G2, and round 2 implements that.
