"""One line in the agent's own feed when Ting Yu's decision lands (Ting Yu, 2026-10-31).

The ask goes to #approvals. What became of it goes to the agent's feed: "the updates and feeds
after they are approved, skipped or sent will go into the agent feeds". `cards.sweep()` sees each
request's change once, when it edits the card, so that is where the line goes out. A request that
never had a card gets no line: the one-pager lists the unposted.

    approved, skipped, expired    one line here
    item gone, nothing replacing  one "withdrawn" line, in the card's own words
    claimed after an approval     nothing: the action reports itself (`#outreach-sent` when an
                                  email goes, the publish run's update with the post's address)
    content changed               nothing, with or without a new request yet: a new card asks

The channel is the kind's `feed_channel`, or the plug-in's `FEED_CHANNEL`, or the channel its run
updates go to. A kind may add `feed_approved`: what happens next, in one short sentence, or a
`(conn, subject)` function returning it. Words are the card's own title, so the feed names the
item as the card did, masked the same way.

Feed lines are at most once, by design. They are a courtesy report, and `approvals` and the run
updates stay the record. A crash between the card's update and the post loses the line, and a
line Discord doesn't take goes to the outbox, where the one-pager counts it. Each is sent silently
(an expiry can land at 23:30), and waits at most `PATIENCE` seconds, because a decision's own
sweep runs inside Dispatch's call.
"""

from __future__ import annotations

import sqlite3

from jura_growth import agents, approvals, discord, log

USERNAME = "Jura growth · approvals"
PATIENCE = 5.0  # seconds
_WORDS = {approvals.APPROVED: "approved", approvals.SKIPPED: "skipped", approvals.EXPIRED: "expired"}


def channel_for(registered) -> str | None:
    """Where a request of this kind reports, or None when its plug-in names nowhere."""
    named = getattr(registered.kind, "feed_channel", None)
    if named:
        return named
    module = agents.by_name(registered.agent)
    return getattr(module, "FEED_CHANNEL", None) or getattr(module, "RUN_UPDATE_DISCORD_CHANNEL", None)


def _next_step(conn: sqlite3.Connection, approval: approvals.Approval, registered) -> str | None:
    """What the kind says happens next. A kind that can't say still gets its line."""
    step = getattr(registered.kind, "feed_approved", None)
    try:
        said = step(conn, approval.subject) if callable(step) else step
        return str(said) if said else None
    except Exception as error:  # noqa: BLE001 - a feed line never fails on a kind's wording
        log.event(conn, "approval.feed_error", {"approval": approval.id, "error": f"{type(error).__name__}: {error}"},
                  level="warning", agent=registered.agent)
        return None


def _line(conn: sqlite3.Connection, approval: approvals.Approval, was: str, now: str, title: str, registered,
          note: str | None) -> str | None:
    """The feed's line for this change, or None when the feed has nothing to hear."""
    if now == approvals.SUPERSEDED:
        return f"**{approval.id} withdrawn** · {title}\nThe request closed: {note or approval.close_reason}."
    # A kind applied on decide (app-build) goes from waiting straight to claimed: that is its approval.
    shown = approvals.APPROVED if now == approvals.CLAIMED and was == approvals.PENDING else now
    word = _WORDS.get(shown)
    if word is None:
        return None
    text = f"**{approval.id} {word}** · {title}"
    if shown == approvals.APPROVED:
        step = _next_step(conn, approval, registered)
        return f"{text}\n{step}" if step else text
    if shown == approvals.EXPIRED and approval.close_reason:
        return f"{text}\n{approval.close_reason.capitalize()}."
    return text


def _replaced(conn: sqlite3.Connection, approval: approvals.Approval) -> bool:
    """Whether a new card asks, or will: `expire_due()` supersedes a changed request without
    raising the new one, so the link to a successor may not exist yet (technical review B1)."""
    return approval.close_reason == approvals.CONTENT_CHANGED or approvals.successor(conn, approval) is not None


def announce(conn: sqlite3.Connection, approval: approvals.Approval, was: str, now: str, title: str, *,
             note: str | None = None) -> None:
    """Post the line for one change. Never raises: a feed line never holds up a card. `note` is
    the card's own reason for a request that closed with nothing replacing it."""
    try:
        registered = approvals.kinds().get(approval.kind)
        if registered is None or (now == approvals.SUPERSEDED and _replaced(conn, approval)):
            return
        channel = channel_for(registered)
        text = _line(conn, approval, was, now, title, registered, note)
        if channel and text:
            discord.post(conn, channel, text, username=USERNAME, dedupe=False, suppress_embeds=True, silent=True,
                         patience=PATIENCE)
    except Exception as error:  # noqa: BLE001
        log.event(conn, "approval.feed_error", {"approval": approval.id, "error": f"{type(error).__name__}: {error}"},
                  level="warning")
