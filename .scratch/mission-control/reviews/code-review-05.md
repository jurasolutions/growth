# Code review 05: the `group-rules` kind

## Round 2 (2026-10-27): approve

- **Branch:** `crew/mission-control-05-group-rules-kind`, rebased onto abe16b0. Commits 562ad0b, 82d6ae2, f76101b, bed1c19 and 8d22653.
- **Scope:** I read the fix-round diff in full (`git diff f76101b..8d22653`) and re-read every changed file against `abe16b0...crew/mission-control-05-group-rules-kind`.

The verdict is **approve**. Round 1's blocking finding is closed, and I found no new blocking or should-fix finding. Round 1 is kept below for the record.

### Evidence

- `uv run pytest -p no:cacheprovider` in the ticket worktree printed **2332 passed in 88.63s**. It ran with `JURA_ROOT` set and temp data and outputs folders, against the Discord double only, and the worktree was clean afterwards.
- `git merge-tree --write-tree crew/mission-control crew/mission-control-05-group-rules-kind` merged **clean** (tree 28f92ce, exit 0), and abe16b0 is on `crew/mission-control`.
- I wrote 40 probe tests outside the repo, in the session scratchpad, and ran them against the worktree's conftest. All **40 passed**: 30 for bypass attempts, and 10 for the business analyst's two checks.

### Round 1 findings, rechecked

**B1, the quoted yes: closed.**
- `groups.parse_pairs` is now the single parser. It drops one layer of quotes from the key and from the value.
- `set_parsed` refuses `rules_confirmed=yes` and both day keys unless `by_decision=True`. The only caller that passes it is `on_approve` (`group_rules.py:113`; I grepped `jura_growth/` and `tests/uat/`).
- `set_by_hand` refuses any `rules_confirmed` value that is not a yes or a no, and turns every yes into the request.
- The round 1 repro now raises A-0002, and `rules_confirmed` stays 0.
- The in-repo tests are at `test_group_rules.py:262`, `:277`, `:292`, `:310` and `:321`.

**The ways I tried to open days or confirm rules without a decision, each starting from a group that was unconfirmed but kept its decided days.** None got through.
- **Yes spellings that raise a card and confirm nothing:** `"yes"`, `'y'`, `yes` followed by a non-breaking space, `RULES_CONFIRMED = TRUE`, `"rules_confirmed"=1` and `On`.
- **Spellings refused with "must be yes or no":** curly double and single quotes, nested quotes (`"'yes'"`), fullwidth `ｙｅｓ`, a zero-width space inside `yes`, a literal `\n`, and a Cyrillic `у` in `уes`.
- **A Cyrillic `о` in the key** is refused as not settable.
- **Day keys:** `promo_days`, `"promo_days"`, `PROMO_DAYS = any`, `post_days='any'` and `promo_days` followed by a non-breaking space are all refused with the decision pointer. `promo_days_confirmed` and `post_days_confirmed` are refused as not settable.
- **Calling the module directly:** `set_parsed`, `set_fields` and `set_by_hand` each refuse `rules_confirmed=yes`, `promo_days` and `post_days`.
- **remote:** `remote community set …` is refused with "isn't a control command". The only community command remote takes is `community removed`.
- **Headless:** the community job's `permissions()` still lists only `context`, `add-group`, `summary`, `plan-add`, `publish-plan`, `social render` and `check`. `headless.NEVER` holds `approve`, `skip` and `remote`.
- **Other writers:** `add-group` takes no confirmation or day fields, and nothing else writes those columns. `on_approve` validates the days with `read_days` before it claims.

**S1, the merge conflict: closed.** `tests/uat/seed.py` follows round 1's recipe. It uses ticket 17's `seed()`, `--today` and `option()`, adds `--group`, and posts the cards after the commit. The branch merges into `crew/mission-control` cleanly.

**S2, reuse: closed.** `approvals.pending(conn, kind, subject)` now replaces `_waiting` and the raw SQL in `apps/catalog.py`. Its filter values are bound parameters, and the column names come from a fixed tuple.

**S3, the precheck write: closed.**
- The README hook table now documents the catch-up write.
- `precheck` logs a failed pass as `community.group.rules_pass_error` and lets the run go ahead (`test_group_rules.py:575`).

**S4, the one-off pass: closed.**
- The pass writes a `community.group.rules_confirmed_earlier.done` event when it finishes, and returns at once when that event exists.
- My probe set `rules_confirmed = 1` by raw SQL after the marker existed. It was not written down as history, matching `test_group_rules.py:558`.
- Nothing deletes from `events`, so the marker stays.

**S5, confirming a confirmed group again: closed by the conductor's decision.**
- It raises a card. Approving the card replaces the days, and a skip or expiry keeps the earlier confirmation.
- `docs/community.md` documents this, and `test_group_rules.py:236` and `:243` test it.

**Nits N1 to N6: addressed.** The note-rules docstrings now say "will", `_raise` is renamed `_raise_fresh` with an explanation, the class attribute moved to the top, the docs are re-wrapped, and the preview no longer repeats the typed form.

### The business analyst's two checks

**1. Every outcome leaves the group re-confirmable, with no collision on `approvals_one_live`.**
- The index covers one pending, or approved-and-unused, request per kind and subject. `on_approve` claims through `approvals.use` inside the decision, so an approved `group-rules` request always has `used_at` set (it was `True` in the probe).
- **Approve, re-confirm, approve, re-confirm:** A-0001 approved and used, A-0002 approved and used with the new days, then A-0003 pending.
- **Skip, then re-confirm:** A-0002 skipped, the confirmation and days kept, then A-0003 pending.
- **Expiry found by the raise itself:** A-0001 expired, then A-0002 raised, approved, then A-0003 pending.
- **Expiry through `expire_due`:** A-0002 expired, the confirmation kept, then A-0003 pending.
- Result: **no collision.** In every case the command exits 0 and exactly one live request remains.

**2. The "set the rules first" refusal applies only to an empty field.**
- Researched text such as `not stated in public sources`, `Not stated` or `-` raises a request on `rules_confirmed=yes`.
- `rules=   `, `rules=""` and `rules='  '`, each sent with `rules_confirmed=yes`, are refused with "set the rules first" and raise no request.
- This matches PRD §5.1 as amended 2026-10-27. Round 1's A2 (a quoted empty value getting past the check) is fixed by the shared parser.

### Blocked paths

The diff from abe16b0 touches no `inputs/`, `design-system/`, `.env` or `data/growth/` path. **No finding.**

### Round 2 findings

**Standards**
- *Nit.* `approvals.pending(conn, kind, subject)` has no direct unit test. It is covered indirectly by the app catalog's waiting-pile tests and by the pointer test (`test_group_rules.py:151`). One test of the filter in `tests/test_approvals.py` would pin it.

**Spec**
- *Nit.* No in-repo test runs `rules_confirmed=yes` on its own over researched placeholder text and expects a request. The two existing "not stated" tests (`test_group_rules.py:168` and `:179`) set new rules text in the same command. My probe shows it works, and the business analyst's check 2 makes it a stated requirement, so it deserves a test.
- *Nit, for the record.* `rules_confirmed=no` unconfirms at once and keeps the decided days, so a group with no link can still be posted to on its open days. This was already true before this ticket, and `docs/community.md` describes it ("unconfirms a group at once, with no card"). To close a group's days, approve a re-confirmation card with `promo_days=none post_days=none`.

**Security**
- No finding.
- The new `pending()` binds its values as parameters. `parse_pairs` normalises input without widening what can be set. Card and event payloads are unchanged from round 1, where they were swept clean.

---

## Round 1 (2026-10-27): changes-requested (superseded by round 2)

- **Branch:** `crew/mission-control-05-group-rules-kind` (6bd121f, eaefae4, c6a4e79), compared with its merge-base 4cc477e
- **Ticket:** `.scratch/mission-control/issues/05-group-rules-kind.md`. **Spec:** MC §4.6 A11, §5.1 "Group rules", §5.6, §5.7 `group-rules` row, §5.12 MC-05 (amended 2026-10-26)
- **Reviewed:** 2026-10-27. I read every changed file: `group_rules.py`, the community `__init__.py`, `groups.py`, `rules.py`, `README.md`, `docs/community.md`, `tests/test_group_rules.py`, `tests/gate_adapter_group_rules.py`, `tests/test_community.py`, `tests/test_approval_buttons.py`, `tests/test_uat_seed.py` and `tests/uat/seed.py`.

### Verdict: changes-requested

There is one blocking finding, B1. `community set` can still set `rules_confirmed=1` with no decision, which breaks X9 and ADR 0004. I reproduced it.

Everything else holds:
- AC-M10.6 through `remote`.
- G37, G19 (the PAUSE file and the paused agent), X2 under three time zones, and the sweep.
- The gate adapter, which the matrix picks up.
- "Existing confirmations stand".

### Evidence

- `uv run pytest -p no:cacheprovider` in the ticket worktree printed **2232 passed in 86.68s**. It ran with `JURA_ROOT` set and temp data and outputs folders, against the Discord double only.
- The touched files alone (`test_group_rules`, `test_community`, `test_uat_seed`, `test_approval_buttons`) printed **392 passed**.
- Pyright, from the Standards sub-agent: 15 errors on the branch and 15 at 4cc477e, all in the untouched `plan.py`. The branch adds none.
- `git merge-tree --write-tree crew/mission-control crew/mission-control-05-group-rules-kind` reports **CONFLICT in `tests/uat/seed.py`** (7 hunks). There are no other conflicts. See S1.
- I wrote a repro test outside the repo, in the session scratchpad, and ran it against the worktree's conftest: `rules_confirmed="yes"` → `(1, 'sat,sun', 'any')` with no new request. Test text is under B1.

### Blocked paths

No change touches `inputs/`, `design-system/`, `.env` or the live `data/growth/`. The tests use temp folders, and the seed refuses any folder that isn't temporary (tested). **No finding.**

### Standards

#### Blocking

**B1. Terminal can set `rules_confirmed` without a decision.**
- *Where:* the two key=value parsers disagree on quotes, `jura_growth/agents/community/group_rules.py:186-193, 209-210` against `groups.py:213-214`.
- *Rule broken:*
  - ADR 0004 (decisions come only from a human origin).
  - Ticket 05 X9: "leaves `rules_confirmed` and the days unchanged until that decision is recorded through `remote`".
  - The module's own contract (`group_rules.py:16`): "`community set` never sets `rules_confirmed=yes` … itself".
- *How it breaks:*
  - `_keys` does not strip surrounding quotes, so `rules_confirmed="yes"` (or `'y'`) fails `value.lower() in YES`.
  - The pair is not treated as a confirmation. It goes into `rest` instead.
  - `set_fields` then strips the quotes and writes `rules_confirmed = 1`.
  - `_check_days_confirmed` stops this only when the days are empty. `rules_confirmed=no` (`test_group_rules.py:223`) leaves the decided days in place, so after an unconfirm a quoted yes re-confirms with no request, no `approval.*` row and no earlier-confirmation event. The group already has a used approval, so the one-off pass skips it.
  - Shell quoting normally removes the quotes. They arrive when typed as `'rules_confirmed="yes"'`, from any caller that passes argv without a shell, or from a pasted command.
- *Same root cause:* `rules='""' rules_confirmed=yes` passes the "set the rules first" check, because `group_rules.py:211` sees `'""'` as text. `set_fields` then empties the rules, and the command exits 0 with no message (found by the Spec sub-agent).
- *Fix:*
  - Parse the pairs once, with one parser that `set_fields` and `set_by_hand` share (this is also the Duplicated Code smell).
  - `set_by_hand` should refuse any `rules_confirmed` value other than a plain no, after the shared normalisation.
  - Defence in depth: `set_fields` refuses `rules_confirmed=1` and the day keys unless the caller is `on_approve`. For example, `set_by_hand` passes only non-gated keys to a `set_fields(..., gated=False)`.
- *Failing test to add (it fails on c6a4e79):*

```python
def test_a_quoted_yes_never_confirms_from_terminal(conn):
    request = raised(conn)
    gid = group_rules.group_id_of(request.subject)
    aw.approve(conn, request, args=DAYS)
    assert invoke("community", "set", str(gid), "rules_confirmed=no").exit_code == 0
    invoke("community", "set", str(gid), 'rules_confirmed="yes"')
    assert confirmation(conn, gid)[0] == 0   # today: 1, with no new request
```

#### Should fix

**S2. Reuse: `_waiting` reimplements the approvals read helpers.**
- *Where:* `group_rules.py:226-231`.
- *What:* it runs raw SQL on `approvals` (`status = 'pending'`), then re-reads the row through `approvals.get(format_id(...))`. That duplicates `approvals._live` and `_one`, and `apps/catalog.py:113` has the same shape.
- *Fix:* add a public `approvals.waiting(conn, kind, subject)` and call it from both places.
- *Rule broken:* the reuse rule, which says don't duplicate an existing helper.

**S3. `precheck` now writes.**
- *Where:* `jura_growth/agents/community/__init__.py:76-82`.
- *What:* the plug-in interface in `README.md` defines `precheck` as returning a reason to skip, and `runner.py:106-110` treats it that way. This one writes events inside a transaction. That is undocumented, and a write that fails turns into "precheck failed" for the Monday run.
- *Fix:* document the side effect in the README hook table, or move the write into the run itself.

#### Nits

- **N1.** `group_rules.py:9` and `:135` say `publish note-rules` raises a request and calls `request()`. That command doesn't exist yet (browser-publishing#06). Say "will".
- **N2.** `_raise` (`group_rules.py:140-145`) calls `request` twice. The second call works only because the first wrote the expiry. A name that says so, such as `_raise_fresh`, or a comment, would help.
- **N3.** The same predicate is written twice at `group_rules.py:209-210`. This goes away with B1's shared parser.
- **N4.** `used_word = "applied"` (`group_rules.py:92`) sits between two methods. The other kinds keep class attributes at the top.
- **N5.** `docs/community.md:88` runs past the file's roughly 100-character wrap, and lines 3-5 of the `rules.py` docstring are uneven.

### Spec

#### Blocking

- B1 above also breaks X9.

#### Should fix

**S1. The merge conflict with `crew/mission-control` in `tests/uat/seed.py`, and the missing `--today`.**
- *What:* ticket 17 changed how the seed passes options. Its scenarios take only `conn` and read `option()` from the module globals `_day`, `_folder` and `_options`; `seed()` takes `today=` and returns notes; `main` has `--today` and `--lead`. Ticket 05 passes `**options` to each scenario instead.
- *Spec line:* uat.md C3 (line 343) runs `--scenario note-rules --group 4 --today "$TODAY"`. On this branch argparse rejects `--today` with exit 2.
- *How to resolve:*
  - Keep ticket 17's `seed()` and `main`, and add `--group`.
  - Rewrite `note_rules(conn)` to read `option("group")`.
  - Keep ticket 17's `today()`-based `_group` date with ticket 05's explicit ids 4 and 7.
  - Put `cards.sweep_safely(conn)` inside ticket 17's `with db.session()` block, after the transaction.
  - Merge the two module docstrings, and drop ticket 17's sentence "The seed never raises an approval request", which `note-rules` makes false.
  - Then rerun `tests/test_uat_seed.py` and `tests/test_uat_seed_outreach.py`.

**S4. The "one-off" pass never stops, so it would log a future bypass as history.**
- *Where:* `group_rules.py:151-170`, called from `__init__.py:81` and `:241`.
- *Spec line:* X9, "recorded once as an event by a one-off, idempotent pass".
- *What:* it runs before every `community set` and every community run. Any later `rules_confirmed = 1` without a used approval would be written down as "confirmed from Terminal before group-rules approvals", which hides a bypass instead of showing it. That includes a raw edit, a future code path, or a group whose earlier approval rows are gone.
- *Fix:* make the pass truly one-off. Record a done marker (a state row or an event) after the first pass, and skip once it exists.

**S5. `rules_confirmed=yes` on a group that is already confirmed raises a fresh request.**
- *Where:* `group_rules.py:219-220`. I reproduced it: A-0001 approved, then A-0002 pending.
- *Spec line:* "raising nothing new if one is already live".
- *What:* this is not asked for, not documented and not tested. Skipping that fresh request leaves the group confirmed with its old days. §5.7 says "skip leaves the rules unconfirmed".
- *Fix:* either refuse, with "group N's rules are already confirmed", or keep it as the one way to change a group's days. If it stays, document it in `docs/community.md` and test both the approve and the skip. The user decides which; see the question below.

#### Nits

- **N6.** The card's preview text (`group_rules.py:84-85`) repeats the typed form that the card's answer line already shows. §5.6 asks for "the rules text only and the typed form". No parsed days leak, and the test at `test_group_rules.py:231` guards that.
- **N7.** PRD §5.1 says "never for researched rules", but `rules_confirmed=yes` over web-researched text raises a request. The 2026-10-26 amendment, "over the rules text now recorded", allows this when Ting Yu asks, and the developer's note says so. Not a defect, but PRD §5.1 should get a matching amendment line (test strategy Q11).

### Security

I scoped this pass to the ticket 05 diff. The `security-review` skill's built-in diff targeted the whole feature branch against `main`, which is the wrong range.

- **Authorization:** B1 is the only finding, a local bypass of the approval gate (medium; it needs Terminal access and an earlier decision's days). The other paths I checked hold:
  - Headless runs can't reach `community set` or `remote`: `community.permissions()` lists neither, and `headless.NEVER` holds `approve`, `skip` and `remote`.
  - `remote` decides only with an SSH origin and the control actor.
  - Terminal `approve` refuses (tested).
  - There is no raw-SQL command; `db` has only `migrate` and `path`.
  - The only writers of `community_groups` are `groups.add`, `set_fields`, `remove` and `plan`'s `last_posted_at`.
- **Injection:** the earlier-confirmation query is parameterised. `set_fields` builds its `UPDATE` only from whitelisted column names.
- **Data exposure:** rules text from the web reaches `#approvals` through `config.redact` with `allowed_mentions: {"parse": []}`. The `assert_clean` sweep over the card and its edit passes (`test_group_rules.py:403`). The event payloads hold group ids, rules text and days, with no personal data.
- **Seed:** `note-rules` refuses folders that aren't temporary (tested).

### Release note check

The note in `docs/community.md` says that groups confirmed before this ticket keep their confirmation and days and are written down once, and that groups confirmed before ticket 07 have no days and stay closed until a card is confirmed.

That matches the code and `test_group_rules.py:432`: the confirmation and days are unchanged, there is one event per group, a group confirmed through a decision is not logged, and no request is raised for these groups. S4 is about the pass staying on after that first run, not about the note.
