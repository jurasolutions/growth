# 02: defect: a send turns "couldn't be read" into "nothing pending"

Severity: minor. It needs an empty or lost `growth.db`, which is rare. When it happens, the answer is
the false comfort ticket 01 exists to rule out, so it fails AC5 and, for the empty file, AC6.

Found by QA 01 at `d80d73f`. Red tests: `tests/test_pending_qa01.py` on branch
`crew/growth-help-pending-qa01` (commit `14f9fa6`), the four under "defect 02".

## Case A: an empty `growth.db`

`remote._leave_database_alone` leaves the file alone only when it is missing or mid-write. A 0-byte
file opens as a valid, empty database, so `_masked` and `_record` open it with `db.session`, which runs
every migration.

Steps, with the card's temp folders and a copy of the live data:

1. `: > "$JURA_GROWTH_DATA_DIR/growth.db"`
2. `remote --actor discord:<id> --ref a:1 --json -- pending`
3. The same again.

Expected: both answers say what couldn't be read, and the file stays at 0 bytes.

Actual: the first answer lists six "no such table" lines. By the time it returns, the file is 352,256
bytes with every table in it. The second answer, on the live copy:

```
**Waiting for you**
Nothing.

**Growth is on it**
- 1 of your ideas waits in the backlog for the app factory. The next is [name of the idea left out of this public repo].
```

With no open idea, it is `Nothing pending. Nothing is waiting for you, and growth has nothing under way.`

The data folder sits under OneDrive, which makes a truncated or placeholder file more plausible than
on a plain disk.

## Case B: `/growth help` on a missing `growth.db`

`help` is new, and its text comes from `ALLOWLIST`, so it needs no database. It still goes through
`db.session` and creates one.

Steps:

1. `rm "$JURA_GROWTH_DATA_DIR/growth.db"`
2. `remote … -- pending` says `growth.db doesn't exist yet`, twice, and no file appears. This is right.
3. `remote … -- help`. A `growth.db` now exists.
4. `remote … -- pending` answers as in case A.

Expected: step 4 still says the database couldn't be read.

The natural order for someone who sees a strange answer is to ask for help next, so this order is
likely. `status` and any scheduled run create the database too, and
`test_every_other_command_still_opens_the_database` keeps that on purpose. Fixing `help` closes only
the case this ticket added. It doesn't make an empty database after a real loss distinguishable from
a new one.

## Evidence

```
test_pending_on_an_empty_database_file_writes_nothing_to_it: assert 352256 == 0
test_a_second_pending_on_an_empty_database_file_still_says_what_couldnt_be_read: 'nothing pending' in the answer
test_help_on_a_missing_database_leaves_it_missing: growth.db exists
test_pending_after_help_on_a_missing_database_still_says_so: 'nothing pending' in the answer
```
