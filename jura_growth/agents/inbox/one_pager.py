"""R4: Replies waiting, the section of the one-pager's long text, and what `/growth pending` lists.

Since the morning picture, the 09:00 post is the picture and a short message, which carry only counts:
this section is in the text `--no-post` prints and in the post when the picture can't be drawn, and
`/growth inbox list` prints it on request.

One line per open conversation: who wrote, where, how long ago, a short excerpt and what he must do. A
promised reply is first (F10), then anything `high` (D9), then what only he can move, oldest first.
Above them, what happened since the last one-pager. Below, the noise it filtered (R2, S16) and when the
watch last read each surface (F13). `/growth inbox list` prints the same.

It runs on the read model's read-only connection (ADR 0002): it writes nothing and calls no kind's
`content()`, which could supersede a request. `approvals.latest_for_subject` only reads. A request past its decide-by reads as lapsed
by the clock, and the one-pager job has written that before this runs.

An excerpt and a name are **plain-masked** (technical review B3): only cards and R1 carry the
conversation class, so a learned name reads `[name removed]` here, and the domain beside it still says
who. They are masked before they are cut, so a cut can't leave half a phone number that no longer looks
like one.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from typing import NamedTuple

from jura_growth import approvals, caps, health, privacy, timeutil
from jura_growth.agents import GROWTH, LISTED, NEXT_STEP, YOU, PendingItem
from jura_growth.agents.inbox import report, store, watch

SECTION = "Replies waiting"
LINES_SHOWN = 10  # functional review, Edges: then "and N more"
PENDING_SHOWN = 5  # `/growth pending` has one message for everything growth holds
EXCERPT_CHARS = 70
NAME_CHARS = 40
DOMAIN_CHARS = 40
DOMAINS_SHOWN = 12
JUNK_SHOWN = 5
JUNK_SUBJECT_CHARS = 60
_MAILBOX = "Levi's mailbox"
_OPEN = (store.NEW, store.TRIAGED, store.WAITING, store.SENDING)
_DECIDE, _HAND, _NOTHING_TO_DO = 0, 1, 2  # what a line asks of him, in the order they sort
# What `inbox done` clears and a line doesn't already say so: a hand reply's own line names the command.
_CLEARED_BY_DONE = tuple(state for state in store.LISTED_STATES if state != store.NEEDS_HAND_REPLY)


def _shown(text: str, limit: int) -> str:
    """Masked, then cut: one line, unable to restyle anything or ping anyone."""
    masked = report.neutral(privacy.for_discord(store.clean_line(text)))
    if len(masked) <= limit:
        return masked
    return masked[: limit - 1].rstrip() + "…"


def _age(stamp: str, now: datetime) -> str:
    minutes = max(0, int((now - timeutil.parse(stamp)).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h" if minutes < 24 * 60 else f"{minutes // (24 * 60)}d"


def _who(item: dict) -> str:
    name = _shown(item["sender_name"], NAME_CHARS)
    domain = _shown(item["sender_domain"], DOMAIN_CHARS)
    if item["source"] in store.SOCIAL_SOURCES:
        return name or "Someone"
    return f"{name} ({domain})" if name and domain else name or domain or "Someone"


def _where(item: dict) -> str:
    """Where to answer by hand."""
    if item["source"] in store.MAIL_SOURCES:
        return _MAILBOX
    return f"<{item['target']}>" if item["target"] else "the platform"


def _lapsed(item: dict) -> tuple[int, str]:
    return _HAND, f"Lapsed: answer by hand if it still matters, from {_where(item)}."


def _card_words(item: dict, record: approvals.Approval | None, now: datetime) -> tuple[int, str]:
    if record is None:
        return _NOTHING_TO_DO, "Draft ready: its card follows."
    if record.status == approvals.APPROVED:
        return _NOTHING_TO_DO, "Approved: it goes out on the next send."
    if record.status != approvals.PENDING or now >= timeutil.parse(record.decide_by):
        return _lapsed(item)
    if item["asked_at"]:
        return _DECIDE, "Redraft asked: a new card follows, and this one stays open until it does."
    if record.posted_at is None:
        return _DECIDE, f"Its card hasn't posted yet. Decide by {timeutil.when(record.decide_by)}."
    return _DECIDE, f"Approve or skip in #approvals by {timeutil.when(record.decide_by)}."


def _what_to_do(item: dict, record: approvals.Approval | None, now: datetime) -> tuple[int, str]:
    label = store.label(item["id"])
    state = item["state"]
    if state == store.WAITING:
        return _card_words(item, record, now)
    if state == store.TRIAGED:
        return _NOTHING_TO_DO, "Draft ready: its card follows."
    if state == store.NEW:
        return _NOTHING_TO_DO, "Being read by triage: nothing to do yet."
    if state == store.SENDING:
        return _NOTHING_TO_DO, "On its way: don't answer by hand yet."
    if state == store.NEEDS_HAND_REPLY and item["sent_at"]:
        return _HAND, f"You owe a personal reply, from {_where(item)}. Then `/growth inbox done {label}`."
    if state == store.NEEDS_HAND_REPLY:
        return _HAND, f"Answer by hand from {_where(item)}, then `/growth inbox done {label}`."
    if state == store.LAPSED:
        return _lapsed(item)
    if state == store.FAILED:
        return _HAND, f"It didn't go: answer by hand if it still matters, from {_where(item)}."
    if state == store.UNKNOWN:
        return _HAND, f"It may have gone out: check {_where(item)} before answering by hand."
    return _HAND, f"Unverified: read the thread yourself, at {_where(item)}."


def _is_promised(item: dict) -> bool:
    return item["state"] == store.NEEDS_HAND_REPLY and bool(item["promised"]) and bool(item["sent_at"])


def _excerpt(item: dict) -> str:
    words = _shown(item["text"], EXCERPT_CHARS)
    if words:
        return f'"{words}"'
    if item["text_removed_at"]:
        return "(their words were removed after 90 days)"
    return f"({report.no_text(item)})" if item["source"] in store.SOCIAL_SOURCES else "(no text)"


class _Line(NamedTuple):
    """One conversation: how it sorts, what it reads, what it asks of him, and what to send once he has."""

    key: tuple
    text: str
    tier: int
    then: str


def _line(conn: sqlite3.Connection, items: list[dict], now: datetime) -> _Line:
    newest = items[-1]
    record = approvals.latest_for_subject(conn, store.approval_subject(newest["id"]))
    tier, action = _what_to_do(newest, record, now)
    promised, high = _is_promised(newest), any(item["priority"] == "high" for item in items)
    number = record.id if record and newest["state"] == store.WAITING and tier != _HAND else store.label(newest["id"])
    tag = f"**Promised · {number}**" if promised else f"**High · {number}**" if high else f"**{number}**"
    stamp = newest["received_at"] or newest["recorded_at"]
    count = f", {len(items)} messages" if len(items) > 1 else ""
    text = f"- {tag} · {_who(newest)} · {report.heading(newest)}{count} · {_age(stamp, now)} · {_excerpt(newest)} {action}"
    then = f" Then `/growth inbox done {store.label(newest['id'])}`." if newest["state"] in _CLEARED_BY_DONE else ""
    return _Line((not promised, not high, tier, stamp), text, tier, then)


def _open_conversations(conn: sqlite3.Connection, now: datetime) -> list[list[dict]]:
    """What R4 lists, a conversation at a time. A promised reply stands alone: he owes it whatever the
    person has written since."""
    cutoff = timeutil.stamp(now - timedelta(days=caps.INBOX_LISTED_DAYS))
    people = ", ".join("?" for _ in store.PEOPLE_SOURCES)
    rows = [dict(row) for row in conn.execute(
        f"SELECT * FROM inbox_items WHERE source IN ({people}) AND (state IN ({', '.join('?' for _ in _OPEN)}) "
        f"OR (state IN ({', '.join('?' for _ in store.LISTED_STATES)}) AND updated_at >= ? AND closed_at IS NULL) "
        "OR (state = ? AND promised = 1 AND sent_at IS NOT NULL)) ORDER BY id",
        (*store.PEOPLE_SOURCES, *_OPEN, *store.LISTED_STATES, cutoff, store.NEEDS_HAND_REPLY),
    )]
    promised = [[row] for row in rows if _is_promised(row)]
    return promised + list(store.by_conversation([row for row in rows if not _is_promised(row)]).values())


def _counted(conn: sqlite3.Connection, since: str) -> str | None:
    """Reactions since the last one-pager, and what reached the website rather than the mailbox (S12)."""
    reactions = store.reactions_since(conn, since)
    rows = conn.execute(
        "SELECT json_extract(payload_json, '$.reason') AS reason, count(*) AS n FROM events "
        "WHERE kind = 'outreach.suppressed' AND ts >= ? GROUP BY reason", (since,),
    ).fetchall()
    found = {row["reason"]: row["n"] for row in rows}
    clicks, bounces = found.get("unsubscribe", 0), found.get("bounce", 0)
    if not (reactions or clicks or bounces):
        return None
    parts = [f"{health.plural(reactions, 'reaction')} since the last one-pager"]
    if clicks:
        parts.append(health.plural(clicks, "unsubscribe click"))
    if bounces:
        parts.append(health.plural(bounces, "bounce"))
    return ", ".join(parts)


def _noise_line(conn: sqlite3.Connection, since: str, *, capped: bool = True) -> str | None:
    """R2: the count and each sender's domain. S16: a Junk message's subject as well, because cold
    replies land there and this line is the only sign of them. The one-pager caps them to stay readable,
    and the list shows all of them, so nothing is swallowed (code review 04, P-5)."""
    rows = store.noise_since(conn, since)
    if not rows:
        return None
    domains = Counter(row["sender_domain"] or "an unknown sender" for row in rows if row["note"] != store.JUNK_NOTE)
    shown = [f"{_shown(domain, DOMAIN_CHARS)} ({n})" if n > 1 else _shown(domain, DOMAIN_CHARS)
             for domain, n in domains.most_common(DOMAINS_SHOWN if capped else None)]
    if capped and len(domains) > DOMAINS_SHOWN:
        shown.append(f"and {len(domains) - DOMAINS_SHOWN} more")
    junk = [row for row in rows if row["note"] == store.JUNK_NOTE]
    listed = [f'{_shown(row["sender_domain"] or "an unknown sender", DOMAIN_CHARS)} "{_shown(row["subject"], JUNK_SUBJECT_CHARS)}"'
              for row in (junk[:JUNK_SHOWN] if capped else junk)]
    if capped and len(junk) > JUNK_SHOWN:
        listed.append(f"and {len(junk) - JUNK_SHOWN} more")
    line = f"Noise: {len(rows)} filtered"
    if shown:
        line += f": {', '.join(shown)}"
    if listed:
        line += f". Junk: {', '.join(listed)}"
    return line


def _surface_line(conn: sqlite3.Connection) -> str | None:
    """F13: each surface's last good read. A blind watch must not look like a quiet day."""
    rows = {row["surface"]: row for row in watch.surface_reads(conn)}
    known = {name: rows[name] for name in watch.SURFACES if name in rows}
    if not known:
        return None
    by_time: dict[str, list[str]] = {}
    for name, row in known.items():
        when = timeutil.when(row["last_good_at"]) if row["last_good_at"] else "never"
        by_time.setdefault(when, []).append(watch.SURFACES[name].label)
    if len(by_time) == 1 and len(known) == len(watch.SURFACES):
        return f"Last good read: every surface, {next(iter(by_time))}"
    parts = [f"{', '.join(labels)} {when.removesuffix(' SGT')}" for when, labels in by_time.items()]
    return "Last good read: " + "; ".join(parts)


def _unread_line(conn: sqlite3.Connection, now: datetime) -> str | None:
    """B2: comments a post counts that the watch couldn't read, as its last read of each post found
    them. A watch message tells this figure when it rises, and a post's silent first read sets it too,
    so it can be more than any message said. It goes once a later read finds them read."""
    cutoff = timeutil.stamp(now - timedelta(days=caps.INBOX_WATCH_POST_DAYS))
    unread = conn.execute(
        "SELECT sum(told_unread) FROM inbox_watch_posts WHERE gone_at IS NULL AND last_read_at >= ?", (cutoff,),
    ).fetchone()[0] or 0
    if not unread:
        return None
    return f"{health.plural(unread, 'comment')} the watch couldn't read: check by hand"


def _conversations(conn: sqlite3.Connection, now: datetime) -> list[_Line]:
    """Every open conversation's line, most pressing first."""
    return sorted((_line(conn, items, now) for items in _open_conversations(conn, now)), key=lambda line: line.key)


def to_answer(conn: sqlite3.Connection) -> int:
    """How many conversations only he can move, for the morning picture. A count, and the same selection
    as the section's lines, so the two can't disagree."""
    return sum(1 for line in _conversations(conn, timeutil.now_sgt()) if line.tier == _HAND)


def _capped(holder: str, found: list[str], order: int) -> list[PendingItem]:
    more = [f"and {len(found) - PENDING_SHOWN} more: send `/growth inbox list`"] if len(found) > PENDING_SHOWN else []
    return [PendingItem(holder, text, order) for text in [*found[:PENDING_SHOWN], *more]]


def pending_items(conn: sqlite3.Connection) -> list[PendingItem]:
    """`/growth pending`'s lines, on the read model's read-only connection. The section's own lines, so
    they are plain-masked and only ever read (technical review B3, ADR 0002). A promised reply or anything
    needing his hand waits for him, with what to send. A card still to decide is listed by the core with
    its A-id and the commands, so it isn't listed twice. What is being read or sent is growth's."""
    found = _conversations(conn, timeutil.now_sgt())
    yours = [line.text.removeprefix("- ") + line.then for line in found if line.tier == _HAND]
    growths = [line.text.removeprefix("- ") for line in found if line.tier == _NOTHING_TO_DO]
    return [*_capped(YOU, yours, NEXT_STEP), *_capped(GROWTH, growths, LISTED)]


def lines(conn: sqlite3.Connection, since: str, *, limit: int | None = LINES_SHOWN) -> list[str]:
    """Every line of the section, most pressing first. It raises if the database does."""
    now = timeutil.now_sgt()
    found = _conversations(conn, now)
    shown = [line.text for line in (found if limit is None else found[:limit])]
    if limit is not None and len(found) > limit:
        shown.append(f"and {len(found) - limit} more: `/growth inbox list`")
    counted = _counted(conn, since)
    head = [counted] if counted else [] if shown else ["Nothing waiting"]
    extras = (_noise_line(conn, since, capped=limit is not None), _unread_line(conn, now), _surface_line(conn))
    return [*head, *shown, *[line for line in extras if line]]


def section(conn: sqlite3.Connection, since: str) -> tuple[str, list[str]] | None:
    """The one-pager's section, or None when the tables aren't there yet: `missing_migrations` says so."""
    try:
        return SECTION, lines(conn, since)
    except sqlite3.OperationalError as error:
        if "no such" in str(error):
            return None
        raise
