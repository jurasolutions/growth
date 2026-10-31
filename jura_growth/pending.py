"""`jura-growth pending`: growth's unfinished work, by who holds the next step (`/growth pending`).

The approvals section is the core's own. Everything else comes from each plug-in's optional
`pending(conn)` hook (`agents/__init__.py`), so the core imports no agent by name.

It only reads, like the one-pager's read model (ADR 0002): growth.db is opened read-only through
`mission.connect`, a request past its decide-by reads as lapsed by the clock with nothing written,
and no kind's `content()` runs, since a read of that may supersede. `remote` masks the answer and
cuts it, so the text starts with what is most urgent. When growth.db is missing, empty or mid-write,
`remote` leaves it alone too (`remote._leave_database_alone`). A 0-byte file is one line: SQLite opens it
as a valid database with no tables, and a send that migrated it would then read as nothing to do.

It says "nothing pending" only when every source was read. A source that couldn't be read gets its
own line, never a silent gap or a guessed zero (the rule in `picture.py`).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from jura_growth import agents, approvals, approvals_cli, cards, db, discord, mission, paths, privacy, timeutil
from jura_growth.agents import GROWTH, UNREAD, YOU, PendingItem

REQUESTS_SHOWN = 5
TITLE_MAX = 100  # a title's own length can't push the urgent lines out of the answer
DECIDE = "Decide in #approvals, or send `/growth approve A-nnnn` or `/growth skip A-nnnn`."
EMPTY_DATABASE = "Pending work couldn't be read: growth.db is an empty file, with no approvals or anything else in it."


def read() -> list[PendingItem]:
    """Everything open, or what couldn't be read. Never raises for the database's state."""
    now = timeutil.now_sgt()
    if mission.is_empty(paths.db_path()):
        return [PendingItem(UNREAD, EMPTY_DATABASE)]
    conn, state, error = mission.connect(paths.db_path())
    if conn is None:
        return [_database(now, state, error)]
    try:
        privacy.load_for_masking(conn, reraise=db.is_lock)  # here too, as `remote`'s own load may meet a lock
        return [*_requests(conn), *_plugins(conn), *_broken()]
    except sqlite3.Error as failure:  # only a lock or a hot journal gets out: a passing state of the whole file
        return [_database(now, mission.state_of(failure), mission.error_name(failure))]
    finally:
        conn.close()


def _database(now: datetime, state: str, error: str | None) -> PendingItem:
    problem = mission.db_problem(mission.Snapshot(now, state, error))
    assert problem is not None
    return PendingItem(UNREAD, f"Pending work couldn't be read: {problem.strip}")


# --- approval requests ------------------------------------------------------------------------


def _requests(conn: sqlite3.Connection) -> list[PendingItem]:
    """Requests still waiting for a decision, soonest to lapse first: the one selection `approvals`
    shows, so the two can't disagree. One past its decide-by has lapsed by the clock, so it isn't
    waiting."""
    try:
        waiting = approvals_cli.waiting(conn, None)[0]
        registry = approvals.kinds()
        items = [PendingItem(YOU, f"{request.id} · {_title(conn, request, registry)} · decide by {timeutil.when(due)}{_no_card(request, registry)}")
                 for request, due in waiting[:REQUESTS_SHOWN]]
    except Exception as error:  # noqa: BLE001 - the plug-ins' lines still go out
        if db.is_lock(error):
            raise
        return [PendingItem(UNREAD, f"Approval requests couldn't be read ({_why(error)}).")]
    if len(waiting) > REQUESTS_SHOWN:
        items.append(PendingItem(YOU, f"and {len(waiting) - REQUESTS_SHOWN} more: send `/growth approvals`"))
    return [*items, PendingItem(YOU, DECIDE)] if items else []


def _no_card(request: approvals.Approval, registry: dict) -> str:
    """A kind that needs its card out before a yes (`needs_card`) can't take the typed approval the
    line below offers until then."""
    registered = registry.get(request.kind)
    needs = registered is not None and getattr(registered.kind, "needs_card", False)
    return " · no card yet, so it can't be approved" if needs and request.posted_at is None else ""


def _title(conn: sqlite3.Connection, request: approvals.Approval, registry: dict) -> str:
    """The card's title; without one, the request's own words. Masked before it is shortened: an
    address or a number across the cut would no longer match a mask."""
    registered = registry.get(request.kind)
    title = ""
    if registered is not None:
        try:
            title = registered.kind.preview(conn, request.subject).title
        except Exception as error:  # noqa: BLE001 - a request with no preview is still waiting
            if db.is_lock(error):
                raise
    return discord.shortened(privacy.for_discord(title or request.reason or cards.label(request.kind)), TITLE_MAX)


# --- the plug-ins ---------------------------------------------------------------------------------


def _plugins(conn: sqlite3.Connection) -> list[PendingItem]:
    items: list[PendingItem] = []
    for module in agents.plugins():
        hook = getattr(module, "pending", None)
        if not callable(hook):
            continue
        try:
            found: Any = hook(conn)
            items += [_checked(item) for item in found or ()]
        except Exception as error:  # noqa: BLE001 - one plug-in never breaks the answer
            if db.is_lock(error):
                raise
            items.append(PendingItem(UNREAD, f"{getattr(module, 'NAME', 'a plug-in')}: its pending work couldn't be read ({_why(error)})."))
    return items


def _why(error: Exception) -> str:
    """SQLite's own words name what is missing; anything else is only named, as in the read model."""
    return str(error) if isinstance(error, sqlite3.Error) else type(error).__name__


def _checked(item: PendingItem) -> PendingItem:
    if not isinstance(item, PendingItem) or item.holder not in (YOU, GROWTH, UNREAD):
        raise TypeError("a pending hook returns PendingItems")
    return item


def _broken() -> list[PendingItem]:
    return [PendingItem(UNREAD, f"{name}: its plug-in didn't load, so its pending work couldn't be read.")
            for name in agents.BROKEN]


# --- the answer -----------------------------------------------------------------------------------


def render(items: list[PendingItem]) -> str:
    """What couldn't be read comes first, since it changes how the rest reads, then what waits for
    Ting Yu, then what growth holds: a cut only ever takes the end. A heading with nothing under it
    says so only when every source was read."""
    held = {holder: _lines(items, holder) for holder in (UNREAD, YOU, GROWTH)}
    if not any(held.values()):
        return "Nothing pending. Nothing is waiting for you, and growth has nothing under way."
    parts = ["**Couldn't be read**\n" + "\n".join(held[UNREAD])] if held[UNREAD] else []
    for heading, holder in (("Waiting for you", YOU), ("Growth is on it", GROWTH)):
        if held[holder]:
            parts.append(f"**{heading}**\n" + "\n".join(held[holder]))
        elif not held[UNREAD]:
            parts.append(f"**{heading}**\nNothing.")
    return "\n\n".join(parts)


def _lines(items: list[PendingItem], holder: str) -> list[str]:
    mine = sorted((item for item in items if item.holder == holder), key=lambda item: item.order)
    return ["- " + " ".join(item.text.split("\n")) for item in mine]
