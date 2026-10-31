# 01: The morning picture

Status: ready-for-agent
Blocked by: none

Turn the first draft (`jura_growth/brief.py`) into the morning picture that #mission-control receives. PRD MB1 to MB13, as worded in `reviews/functional.md` §2, which replaces the PRD where they differ.

**Take from the reviews:**

- `reviews/technical.md`: answer (a), measure then shoot, with `images.measure_height`, an auto-height page and `MAX_HEIGHT = 1600`; the layout with Decide and Fix side by side and This morning below at full width; T-B1, T-B2, T-B3, T-B4; N1 (rename to `picture.py`, `picture_png`, `picture-<day>.png`, `one_pager.picture_failed`); N2, N3, N4, N5. The lock retry on the post path only, with the sleep injected.
- `reviews/functional.md`: B1 (the verdict counts drafts to post by hand and replies to read, and a job that didn't run is a Fix line, skipped when its install state is out of date); B2 (a dash, never a guessed zero, and "Not available" when slots can't be read; reply detection off shows a dash, through a new figure); S1 (Fix clamps at 3 lines, action first in short wording); S4; S5 (language).
- `reviews/test-strategy.md`: seam P with `tests/brief_chrome.py` (name it `tests/picture_chrome.py`), `tests/brief_world.py` (name it `tests/picture_world.py`), fixtures Q, T, B, H and W, the six-part oracle, and risk 1's per-route privacy plants. It says which existing tests change and which must not.

**Conflict rule:** `crew/approvals-first-social-depth` is in flight. Keep `health.py` changes small, as `reviews/technical.md` "To keep it small" item 2 says: `_gap_lines` and `_missed_counts` at the end of the file, and leave `_missed`'s signature alone.

**Also:** `CONTEXT.md`: add "Morning picture", update "One-pager" (no grid in the post, 09:00), and say "Fix" is the picture's name for the health strip.

**Acceptance:** every MB row in `reviews/test-strategy.md` has a passing test. `brief.py` no longer exists, and nothing on the page holds a `<script`. `uv run pytest -rs -p no:cacheprovider -o addopts=""` is green apart from any test ticket 02 owns, which you list.

## Comments
