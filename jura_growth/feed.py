"""One line in the agent's own feed when Ting Yu's decision lands (Ting Yu, 2026-10-31).

The ask goes to #approvals. What became of it goes to the agent's feed: "the updates and feeds
after they are approved, skipped or sent will go into the agent feeds". `cards.sweep()` sees each
request's change once, when it edits the card, so that is where the line goes out.

    approved, skipped, expired   one line here
    claimed after an approval    nothing: the action reports itself (`#outreach-sent` when an
                                 email goes, the publish run's update with the post's address)
    superseded by a new request  nothing: a new card is already asking

The channel is the kind's `feed_channel`, or the plug-in's `FEED_CHANNEL`, or the channel its run
updates go to. A kind may add `feed_approved`, what happens next, in one short sentence. Words are
the card's own title, so the feed names the item as the card did, masked the same way.
"""

from __future__ import annotations

import sqlite3

from jura_growth import agents, approvals, discord, log

USERNAME = "Jura growth · approvals"
CLAIMED = "used"  # what a card shows once its request is claimed (`cards.CLAIMED`)
_WORDS = {approvals.APPROVED: "approved", approvals.SKIPPED: "skipped", approvals.EXPIRED: "expired"}


def channel_for(registered) -> str | None:
    """Where a request of this kind reports, or None when its plug-in names nowhere."""
    named = getattr(registered.kind, "feed_channel", None)
    if named:
        return named
    module = agents.by_name(registered.agent)
    return getattr(module, "FEED_CHANNEL", None) or getattr(module, "RUN_UPDATE_DISCORD_CHANNEL", None)


def line(approval: approvals.Approval, was: str, now: str, title: str, registered) -> str | None:
    """The feed's line for this change, or None when the feed has nothing to hear."""
    # A kind applied on decide (app-build) goes from waiting straight to claimed: that is its approval.
    shown = approvals.APPROVED if now == CLAIMED and was == approvals.PENDING else now
    word = _WORDS.get(shown)
    if word is None and not (shown == approvals.SUPERSEDED and approval.close_reason):
        return None
    if word is None:
        return f"**{approval.id} withdrawn** · {title}\nThe request closed: {approval.close_reason}."
    text = f"**{approval.id} {word}** · {title}"
    if shown == approvals.APPROVED:
        next_step = getattr(registered.kind, "feed_approved", None)
        return f"{text}\n{next_step}" if next_step else text
    if shown == approvals.EXPIRED and approval.close_reason:
        return f"{text}\n{approval.close_reason.capitalize()}."
    return text


def announce(conn: sqlite3.Connection, approval: approvals.Approval, was: str, now: str, title: str, *,
             has_successor: bool = False) -> None:
    """Post the line for one change. Never raises: a feed line never holds up a card."""
    if now == approvals.SUPERSEDED and has_successor:
        return
    try:
        registered = approvals.kinds().get(approval.kind)
        if registered is None:
            return
        channel = channel_for(registered)
        text = line(approval, was, now, title, registered)
        if channel and text:
            discord.post(conn, channel, text, username=USERNAME, dedupe=False, suppress_embeds=True)
    except Exception as error:  # noqa: BLE001
        log.event(conn, "approval.feed_error", {"approval": approval.id, "error": f"{type(error).__name__}: {error}"},
                  level="warning")
