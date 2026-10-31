# 03: The schedule drift check

Status: done
Blocked by: none

The one-pager says when scheduled jobs fire at the wrong SGT time by a steady amount. PRD SC1, as worded in `reviews/functional.md` §3.

**Take from the reviews:** technical B7 (largest agreeing group, slots more than the tolerance apart, an on-time newer run clears it, ignore runs older than three days, pass `now`), N12, functional S13 (say "most likely", never state the cause as fact; if it is still off the next day, `jura-growth schedule install`).

**Acceptance:** at the seams in `reviews/technical.md` "Ticket 03": steady drift, a routine wake, one late job, the morning after a restart, one outlier, stale runs. The read model stays read-only. `uv run pytest tests/test_mission_health.py tests/test_mission_read.py tests/test_one_pager.py` is green.

## Comments
