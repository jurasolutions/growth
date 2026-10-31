# 01: Depth and pictures

Status: done
Blocked by: none

Make social posts carry more to read and a picture. PRD DP1 to DP5, PC1 to PC3, as worded in `reviews/functional.md` §3.

**First commit (prefactor):** restore `publish_mode: draft` and `page_url: null` in `config/social.yaml` (ticket 02 flips them last), and make the `TIP` and `NEWS` fixtures in `tests/test_social.py` meet the depth rules in one place. Don't edit each test. See `reviews/technical.md` "Sequencing".

**Take from the reviews:** technical B4 and functional B4 (rewrite `prompts/social.md` and the `docs/social.md` parts for depth, with no word range in the prompt, and a test), technical B5 and functional S1 (tie a figure to the post), functional S12 (two hosts), technical N8, N9 (`chars_max: 2200`, `hashtags_max: 5` for Instagram), N13, N14. Functional S14 wording.

**Prompt (DP4):** insight, not a summary: what happened in specifics, why now, what changes for a small business with a concrete example, and one thing to do this week. Which kind of `visual` suits which theme, and how to write one from the post's own facts. Figures only from a source the post links, never illustrative. Keep every existing brand rule.

**Acceptance:** the criteria above pass with tests at the seams in `reviews/technical.md` "Ticket 01". Real Chrome renders each visual kind at both sizes at maximum field length with nothing overflowing. Attach no illustrative figure to any shipped fixture that could reach a live card. `uv run pytest tests/test_social.py tests/test_social_render.py tests/test_social_linkedin_off.py` is green.

## Comments
