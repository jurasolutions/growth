# 02: Approvals first, feeds after

Status: ready-for-agent
Blocked by: 01

Asks go to #approvals, an approval triggers the action, and outcomes go to the agent's feed. PRD AF1 to AF5, FD1 to FD4, as worded in `reviews/functional.md` §3.

**First commit (prefactor):** fence-aware `discord.split` with first-piece headroom, and a card's images on its first piece (technical B2, functional B1; refuse a bare ``` line in a post).

**Take from the reviews:** technical B1, B3, B6 (for both platforms: functional B5), N1 to N7, N10 (superseded by the 17:00 decide-by below), N11. Functional B2 (decide-by 17:00, use-by 18:00, tested by `create_social` and the precheck), B3 (digest at 18:05, approval upkeep first), S2 to S9, S11. Add `feed_channel` coverage with a table test over the real kinds, and the required privacy sweep on feed lines.

**Docs:** `docs/social.md`, `docs/app-factory.md`, `README.md` schedule table, `CONTEXT.md` (Agent feed, Feed line, Approval card, Image card, Visual; Posting window; One-pager), `outputs/growth/setup` is not edited here. `publish/__init__.py` docstring.

**Last commit, on its own:** set `publish_mode: browser` and each `page_url` in `config/social.yaml`, and update the shipped-config test. It rewrites `test_every_platform_ships_in_draft_mode`; do not loosen any test that guards an approval rule (see `reviews/test-strategy.md`).

**Acceptance:** the criteria above pass at the seams in `reviews/technical.md` "Ticket 02". `uv run pytest` is green across the suite. Nothing in `browser` mode asks Ting Yu to post by hand: a test greps every message of a submit for it.

## Comments
