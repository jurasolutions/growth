# 02: The morning order

Status: done
Blocked by: none

Move the drafting jobs to before 09:00 and the one-pager to 09:00, and add the job that raises outreach requests before the picture. PRD SC1 to SC7, as worded in `reviews/functional.md` §2.

**Take from the reviews:**

- `reviews/technical.md`: answer (c), the `outreach raise-due` command with a quiet `outreach-requests` job; T-B5 first, so the suite never holds a schedule that produces false misses (`schedule.installed_at`, `Source.installed_at`, `slots.classify(..., installed_at=...)`, the rule in `slots.py`'s docstring, new tests in a new file); N6 (the ICP line in plain words, action first, through scout's `health()`); "To keep it small" item 3 (add `outreach-requests` after `scout-sync`, keep `one-pager` straight after `digest`, change only schedule values); the list of moved-time comments in answer (d), including what to leave alone.
- `tests/test_no_generic_request_command.py`: declare the new raiser. It amends mission control A11.
- `reviews/test-strategy.md`: SC rows, and the end-to-end `tests/test_morning_order.py` if ticket 01 has merged by then; otherwise leave that one test to the conductor and say so.

**Times, SGT:** `scout-research` 06:30 business days; `app-factory` 07:00 daily; `social` 07:30 daily; `community` Mondays 08:00; `outreach-requests` 08:30 business days; `one-pager` 09:00 daily. Nothing else moves. The digest belongs to the other branch.

**Not in this ticket:** `CONTEXT.md` (ticket 01). `jura_growth/brief.py` or `picture.py` (ticket 01).

**Acceptance:** every SC row has a passing test, including SC3 with no code change and T-B5's probe table as a test. A search for each moved job's old time finds no stale reference. `uv run pytest -rs -p no:cacheprovider -o addopts=""` is green apart from any test ticket 01 owns, which you list.

## Comments
