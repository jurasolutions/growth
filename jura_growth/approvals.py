"""The approval contract (MC §4.6 A1 to A17, ADR 0003).

Every outward action (an email, a post, a group join, an app build or
release) is a gated action: it names a kind and a subject, and claims a
matching approval before it runs. This module owns everything else: the
content hash, the state machine, both clocks, the claim, the decision and
its hooks, and the `approval.*` audit events. Callers never pass a hash.

The core never imports an agent by name. Plug-ins declare their kinds with
`approval_kinds() -> dict[str, ApprovalKind]`, found with `getattr` like
`digest()`. A record whose kind no loaded plug-in declares fails closed:
`use()` and `decide()` refuse it and `expire_due()` leaves it alone (A15).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from jura_growth import agents, caps, config, db, log, pause, timeutil
from jura_growth.origin import NOT_DISPATCH, Origin

PENDING, APPROVED, SKIPPED, EXPIRED, SUPERSEDED = "pending", "approved", "skipped", "expired", "superseded"

# A10: every decision answers exactly one of these. Exit codes for each are
# set by the commands that print them (tickets 04b and 11).
RECORDED, ALREADY_DECIDED, ALREADY_USED, UNKNOWN_ID, REFUSED = (
    "recorded",
    "already-decided",
    "already-used",
    "unknown-id",
    "refused",
)
ANSWERS = (RECORDED, EXPIRED, SUPERSEDED, ALREADY_DECIDED, ALREADY_USED, UNKNOWN_ID, REFUSED)
DECISIONS = ("approve", "skip")
_DISCORD_ACTOR = re.compile(r"discord:\d+")


class BadArgs(Exception):
    """A kind's `on_approve` refuses the decision's arguments. The decision
    is then answered `refused` with this text and nothing is recorded."""


class UnknownKind(LookupError):
    """No loaded plug-in declares this kind."""


class NotApproved(Exception):
    """A claim was refused, so nothing goes out. `approval` is the record
    judged, if there is one. `reason` is one of `REASONS`:

    From `use()`:
        `missing`       no request exists for the kind and subject
        `pending`       the request is waiting for a decision
        `skipped`       Ting Yu skipped it
        `expired`       past its decide-by, or approved and past its use-by
        `superseded`    the item changed or went away
        `used`          it was already claimed
        `unknown-kind`  no loaded plug-in declares the kind
        `paused`        the PAUSE file or the agent's pause flag is set
        `switched-off`  the kind's own switch is off (shadow mode, a draft platform)

    From a kind's own checks inside the claim's transaction:
        `gone`          outreach: the email is no longer queued
        `changed`       outreach: the email changed during the run
        `mismatch`      outreach: what would go out isn't what was approved
        `unwritten`     app-build: the build handoff couldn't be written
    """

    MISSING, PENDING, SKIPPED, EXPIRED, SUPERSEDED, USED = "missing", "pending", "skipped", "expired", "superseded", "used"
    UNKNOWN_KIND, PAUSED, SWITCHED_OFF = "unknown-kind", "paused", "switched-off"
    GONE, CHANGED, MISMATCH, UNWRITTEN = "gone", "changed", "mismatch", "unwritten"
    REASONS = (MISSING, PENDING, SKIPPED, EXPIRED, SUPERSEDED, USED, UNKNOWN_KIND, PAUSED, SWITCHED_OFF,
               GONE, CHANGED, MISMATCH, UNWRITTEN)

    def __init__(self, reason: str, text: str, approval: "Approval | None" = None):
        if reason not in self.REASONS:
            raise ValueError(f"NotApproved has no reason {reason!r}; expected one of {self.REASONS}")
        super().__init__(text)
        self.reason = reason
        self.text = text
        self.approval = approval


@dataclass(frozen=True)
class Preview:
    """What a card shows: a title, the text as it will go out, why the
    engine is asking, and at most ten files (ticket 04b posts it)."""

    title: str
    text: str
    reason: str
    files: tuple[Path, ...] = ()


@dataclass(frozen=True)
class Deadlines:
    """`decide_by`: a pending request expires then. `use_by`: an approved,
    unclaimed one expires then; None for a kind applied on decide."""

    decide_by: datetime
    use_by: datetime | None


class ApprovalKind(Protocol):
    """What a plug-in implements for each kind it owns.

    `content` returns the exact bytes of what would go out now, with no
    Unicode normalisation (UTF-8, JSON with sorted keys; ADR 0003 as
    amended), or None when the item is gone.
    `deadlines` is asked at request time for the decide-by and at approval
    time for the use-by. The optional members are found with `getattr`:

        decision_args: tuple[str, ...]  the `key=value` arguments an approve
            must carry (group-rules: promo_days, post_days)
        args_help: str  the refusal text when one is missing
        on_approve(conn, subject, args) -> str | None  applies the change
            at decision time, inside the decision's transaction, after
            `approved` is written; may raise BadArgs; a returned string is
            appended to the answer
        switched_off(conn, subject) -> str | None  the kind's own switch
            (outreach in shadow mode, a platform in draft): a reason means
            `use()` refuses without claiming
        on_skip, on_expire (pending past decide-by), on_lapse (approved,
            unclaimed, past use-by): (conn, subject) -> None
        superseded_note(conn, subject) -> str | None  why the item changed
            or went away, in Ting Yu's words ("lead unsubscribed"), for the
            card's edited first line; asked after the record is superseded,
            so it reads the item's own state. None keeps the core's reason
            ("the item is gone", "the content changed"). MC-06 fills it for
            outreach-email.
        used_word: str  how a decision on a used request names the use
            ("A-0412 was already sent at 10:40 SGT"); "used" by default
    """

    name: str

    def content(self, conn: sqlite3.Connection, subject: str) -> bytes | None: ...

    def preview(self, conn: sqlite3.Connection, subject: str) -> Preview: ...

    def deadlines(self, conn: sqlite3.Connection, subject: str, now: datetime) -> Deadlines: ...


@dataclass(frozen=True)
class Approval:
    """One row of `approvals`. `id` is the A-nnnn Ting Yu types."""

    number: int  # the row id; `id` below is A-nnnn, the `approval_id` decide() takes
    kind: str
    subject: str
    content_hash: str
    status: str
    reason: str
    raised_by_run: int | None
    supersedes: int | None
    requested_at: str
    decide_by: str
    use_by: str | None
    decided_at: str | None
    decided_by: str | None
    decided_origin: str | None
    decision_ref: str | None
    used_at: str | None
    used_by_run: int | None
    closed_at: str | None
    close_reason: str | None
    posted_at: str | None
    message_id: str | None

    @property
    def id(self) -> str:
        return format_id(self.number)

    @property
    def live(self) -> bool:
        return self.status == PENDING or (self.status == APPROVED and self.used_at is None)

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict) -> "Approval":
        row = dict(row)
        values = {f.name: row[f.name] for f in fields(cls) if f.name != "number"}
        return cls(number=row["id"], **values)


@dataclass(frozen=True)
class Answer:
    """What a decision answers: one of `ANSWERS`, a line of text for Ting
    Yu, and the record as it now stands (None for `unknown-id`)."""

    answer: str
    text: str
    approval: Approval | None = None


# --- ids and hashes ---------------------------------------------------------

_ID = re.compile(r"[Aa]-([0-9]+)")


def format_id(number: int) -> str:
    return f"A-{number:04d}"


def parse_id(text: str) -> int | None:
    """The row id in `A-0412`, or None for anything else (`P-0042`, `42`)."""
    match = _ID.fullmatch(str(text).strip())
    return int(match.group(1)) if match else None


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --- kinds ------------------------------------------------------------------


@dataclass(frozen=True)
class _Registered:
    kind: ApprovalKind
    agent: str


def kinds() -> dict[str, _Registered]:
    """Every kind a loaded plug-in declares, with the agent that owns it. A
    kind two plug-ins both declare is left out, so it fails closed."""
    found: dict[str, _Registered] = {}
    clashing: set[str] = set()
    for module in agents.plugins():
        declare = getattr(module, "approval_kinds", None)
        if declare is None:
            continue
        try:
            declared = dict(declare())
        except Exception as error:  # noqa: BLE001
            print(f"warning: {getattr(module, 'NAME', module.__name__)}.approval_kinds() failed: {error}", file=sys.stderr)
            continue
        for name, kind in declared.items():
            if name in found or name in clashing:
                clashing.add(name)
                found.pop(name, None)
                continue
            found[name] = _Registered(kind, getattr(module, "NAME", module.__name__))
    return found


def _kind(name: str) -> _Registered | None:
    return kinds().get(name)


def _hook(kind: ApprovalKind, name: str):
    return getattr(kind, name, None)


# --- reading ----------------------------------------------------------------


# A live request: pending, or approved and not yet claimed. The migration's
# partial unique index allows one per (kind, subject).
_LIVE = "status IN ('pending', 'approved') AND used_at IS NULL"


def _one(conn: sqlite3.Connection, sql: str, params: tuple) -> Approval | None:
    row = conn.execute(sql, params).fetchone()
    return Approval.from_row(row) if row else None


def get(conn: sqlite3.Connection, approval_id: str) -> Approval | None:
    number = parse_id(approval_id)
    if number is None:
        return None
    return _one(conn, "SELECT * FROM approvals WHERE id = ?", (number,))


def pending(conn: sqlite3.Connection, kind: str | None = None, subject: str | None = None) -> list[Approval]:
    """Pending requests, soonest to lapse first, optionally of one `kind` and
    one `subject`. A plain read: deadlines and content are judged by
    `decide`, `use` and `expire_due`."""
    where, params = ["status = 'pending'"], []
    for column, value in (("kind", kind), ("subject", subject)):
        if value is not None:
            where.append(f"{column} = ?")
            params.append(value)
    rows = conn.execute(f"SELECT * FROM approvals WHERE {' AND '.join(where)} ORDER BY decide_by, id", params)
    return [Approval.from_row(r) for r in rows]


def raised_by(conn: sqlite3.Connection, run_id: int) -> list[Approval]:
    """The requests a run raised, oldest first (its run update lists them)."""
    rows = conn.execute("SELECT * FROM approvals WHERE raised_by_run = ? ORDER BY id", (run_id,))
    return [Approval.from_row(r) for r in rows]


def _live(conn: sqlite3.Connection, kind: str, subject: str) -> Approval | None:
    return _one(conn, f"SELECT * FROM approvals WHERE kind = ? AND subject = ? AND {_LIVE}", (kind, subject))


def _latest(conn: sqlite3.Connection, kind: str, subject: str) -> Approval | None:
    return _one(conn, "SELECT * FROM approvals WHERE kind = ? AND subject = ? ORDER BY id DESC LIMIT 1", (kind, subject))


def latest(conn: sqlite3.Connection, kind: str, subject: str) -> Approval | None:
    """The newest record for `(kind, subject)`, in whatever state; None if it never had one.
    Reads only, so it works on the read model's read-only connection."""
    return _latest(conn, kind, subject)


def _reload(conn: sqlite3.Connection, number: int) -> Approval:
    return Approval.from_row(conn.execute("SELECT * FROM approvals WHERE id = ?", (number,)).fetchone())


# --- the audit trail (A16) --------------------------------------------------
#
# Every event here is written inside a db.transaction(), so its row and its
# JSONL mirror line exist only once that transaction commits: a claim or a
# decision that rolls back leaves no trace in either store (code review 04).


def _audit(
    conn: sqlite3.Connection,
    event: str,
    approval: Approval | None,
    agent: str | None,
    *,
    actor: str | None,
    shown: str | None = None,
    origin: str | None = None,
    ref: str | None = None,
    at: str | None = None,
    run_id: int | None = None,
    **extra,
) -> None:
    payload = {
        "approval": approval.id if approval else shown,
        "kind": approval.kind if approval else None,
        "subject": approval.subject if approval else None,
        "hash": approval.content_hash if approval else None,
        "actor": actor,
        "origin": origin,
        "ref": ref,
        "at": at or timeutil.stamp(),
        **extra,
    }
    level = "warning" if event == "approval.refused" else "info"
    log.event(conn, event, payload, level=level, agent=agent, run_id=run_id)


# --- raising ----------------------------------------------------------------


def _clamp(moment: datetime, now: datetime) -> datetime:
    """No deadline runs past the hard ceiling in `caps.py`."""
    return min(moment, now + timedelta(days=caps.APPROVAL_DEADLINE_MAX_DAYS))


def _insert(
    conn: sqlite3.Connection,
    registered: _Registered,
    kind: str,
    subject: str,
    digest: str,
    *,
    reason: str,
    run_id: int | None,
    supersedes: int | None,
    now: datetime,
) -> Approval:
    decide_by = _clamp(registered.kind.deadlines(conn, subject, now).decide_by, now)
    if decide_by <= now:
        raise ValueError(f"{kind} gave a decide-by that has already passed for {subject}")
    cursor = conn.execute(
        "INSERT INTO approvals (kind, subject, content_hash, reason, raised_by_run, supersedes, requested_at, decide_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, subject, digest, reason, run_id, supersedes, timeutil.stamp(now), timeutil.stamp(decide_by)),
    )
    approval = _reload(conn, int(cursor.lastrowid or 0))
    _audit(conn, "approval.requested", approval, registered.agent, actor="engine", at=approval.requested_at, run_id=run_id, reason=reason)
    return approval


def request(conn: sqlite3.Connection, kind: str, subject: str, *, reason: str, run_id: int | None) -> Approval | None:
    """Raise a request for `subject`, as a side effect of a gated command's
    own checks (A11). A live request over the same content is returned as
    it is; one over different content is superseded and a new one raised.
    Returns None when the item is gone (after superseding any live request),
    and the expired record when the live one had passed its deadline."""
    registered = _kind(kind)
    if registered is None:
        raise UnknownKind(kind)
    now = timeutil.now_sgt()
    content = registered.kind.content(conn, subject)
    live = _live(conn, kind, subject)
    if live is not None:
        lapsed = _lapse_if_due(conn, registered, live, now)
        if lapsed is not None:
            return lapsed
    if content is None:
        if live is not None:
            _supersede(conn, registered, live, "the item is gone", now)
        return None
    digest = content_hash(content)
    if live is not None:
        if live.content_hash == digest:
            return live
        _supersede(conn, registered, live, "the content changed", now)
    return _insert(
        conn, registered, kind, subject, digest, reason=reason, run_id=run_id, supersedes=live.number if live else None, now=now
    )


# --- transitions ------------------------------------------------------------


def _supersede(conn, registered: _Registered, approval: Approval, why: str, now: datetime) -> Approval:
    at = timeutil.stamp(now)
    conn.execute(
        "UPDATE approvals SET status = 'superseded', closed_at = ?, close_reason = ? WHERE id = ?", (at, why, approval.number)
    )
    closed = _reload(conn, approval.number)
    _audit(conn, "approval.superseded", closed, registered.agent, actor="engine", at=at, why=why)
    return closed


def _lapse_if_due(conn, registered: _Registered, approval: Approval, now: datetime) -> Approval | None:
    """Expire a live record past its deadline, running the kind's hook.
    Returns the expired record, or None when it is still in time."""
    at = timeutil.stamp(now)
    if approval.status == PENDING and now >= timeutil.parse(approval.decide_by):
        why, hook = "not approved in time", "on_expire"
    elif approval.status == APPROVED and approval.use_by and now >= timeutil.parse(approval.use_by):
        why, hook = "approved but not used in time", "on_lapse"
    else:
        return None
    conn.execute(
        "UPDATE approvals SET status = 'expired', closed_at = ?, close_reason = ? WHERE id = ?", (at, why, approval.number)
    )
    run = _hook(registered.kind, hook)
    if run is not None:
        run(conn, approval.subject)
    closed = _reload(conn, approval.number)
    _audit(conn, "approval.expired", closed, registered.agent, actor="engine", at=at, why=why)
    return closed


_REFUSALS = {
    PENDING: (NotApproved.PENDING, "{id} is waiting for a decision"),
    SKIPPED: (NotApproved.SKIPPED, "{id} was skipped"),
    EXPIRED: (NotApproved.EXPIRED, "{id} expired: {why}"),
    SUPERSEDED: (NotApproved.SUPERSEDED, "{id} was superseded: {why}"),
}


def _not_approved(approval: Approval) -> NotApproved:
    if approval.status == APPROVED:
        return NotApproved(NotApproved.USED, f"{approval.id} was already used at {approval.used_at}", approval)
    reason, text = _REFUSALS[approval.status]
    return NotApproved(reason, text.format(id=approval.id, why=approval.close_reason), approval)


def use(conn: sqlite3.Connection, kind: str, subject: str, *, run_id: int | None) -> Approval:
    """The claim (A6): call it inside the caller's `db.transaction(conn)`,
    before the outward call, and write the in-flight marker in the same
    transaction. The outward call comes after the commit.

    It refuses with `NotApproved` unless the record is approved, before its
    use-by, unused and matching the content the kind computes now, and
    while neither the PAUSE file, the agent's pause flag nor the kind's own
    switch stops it. A lapse or supersede it finds is written in the same
    transaction: catch `NotApproved` inside the `with` block to keep it.
    """
    if not db.in_transaction(conn):
        # Not a raw BEGIN either: only db.transaction() keeps a rolled-back
        # claim out of the JSONL mirror (code review 04, R2-S2).
        raise RuntimeError("approvals.use() runs inside the caller's db.transaction(conn)")
    registered = _kind(kind)
    if registered is None:
        raise NotApproved(NotApproved.UNKNOWN_KIND, f"no loaded plug-in declares {kind}, so nothing is claimed")
    paused = pause.is_paused(conn, registered.agent)
    if paused:
        raise NotApproved(NotApproved.PAUSED, f"{registered.agent} is paused ({paused})")
    switched_off = _hook(registered.kind, "switched_off")
    switch = switched_off(conn, subject) if switched_off is not None else None
    if switch:
        raise NotApproved(NotApproved.SWITCHED_OFF, switch)
    live = _live(conn, kind, subject)
    if live is None:
        latest = _latest(conn, kind, subject)
        if latest is None:
            raise NotApproved(NotApproved.MISSING, f"there is no approval request for {kind} {subject}")
        raise _not_approved(latest)
    now = timeutil.now_sgt()
    current = _refresh(conn, registered, live, now, raise_new=True)
    if current.status != APPROVED:
        raise _not_approved(current)
    at = timeutil.stamp(now)
    conn.execute("UPDATE approvals SET used_at = ?, used_by_run = ? WHERE id = ?", (at, run_id, current.number))
    used = _reload(conn, current.number)
    _audit(conn, "approval.used", used, registered.agent, actor=f"run:{run_id}" if run_id else "engine", at=at, run_id=run_id)
    return used


def expire_due(conn: sqlite3.Connection, now: datetime | None = None) -> list[Approval]:
    """Write every lapse that is due (A17) and supersede live records whose
    content changed or is gone, without raising new ones (ticket review N6).
    Records of a kind no loaded plug-in declares are left alone (A15). Each
    record is its own transaction, so one kind's failing hook is logged and
    retried next time without holding up the rest. Returns what changed."""
    now = now or timeutil.now_sgt()
    registry = kinds()
    changed: list[Approval] = []
    rows = conn.execute(
        f"SELECT * FROM approvals WHERE {_LIVE} ORDER BY id"
    ).fetchall()
    for approval in (Approval.from_row(r) for r in rows):
        registered = registry.get(approval.kind)
        if registered is None:
            continue
        try:
            with db.atomic(conn):
                current = _reload(conn, approval.number)
                after = _refresh(conn, registered, current, now, raise_new=False) if current.live else current
        except Exception as error:  # noqa: BLE001
            log.event(conn, "approval.hook_error", {"approval": approval.id, "kind": approval.kind, "error": f"{type(error).__name__}: {error}"},
                      level="error", agent=registered.agent)
            continue
        if after.status != current.status:
            changed.append(after)
    return changed


def _successor(conn, approval: Approval) -> Approval | None:
    return _one(conn, "SELECT * FROM approvals WHERE supersedes = ? ORDER BY id DESC LIMIT 1", (approval.number,))


def _refresh(conn, registered: _Registered, approval: Approval, now: datetime, *, raise_new: bool) -> Approval:
    """Judge a live record by the clock and by the content the kind computes
    now (A3, A5): it comes back expired, superseded, or as it was. With
    `raise_new`, a content change raises the request for the new content."""
    lapsed = _lapse_if_due(conn, registered, approval, now)
    if lapsed is not None:
        return lapsed
    content = registered.kind.content(conn, approval.subject)
    if content is None:
        return _supersede(conn, registered, approval, "the item is gone", now)
    digest = content_hash(content)
    if digest == approval.content_hash:
        return approval
    closed = _supersede(conn, registered, approval, "the content changed", now)
    if raise_new:
        _insert(
            conn, registered, approval.kind, approval.subject, digest,
            reason=approval.reason, run_id=None, supersedes=approval.number, now=now,
        )
    return closed


def _closed_answer(conn, approval: Approval) -> Answer:
    """The answer for a record that can no longer be decided."""
    if approval.status == APPROVED and approval.used_at:
        used = timeutil.parse(approval.used_at).astimezone(timeutil.SGT).strftime("%H:%M")
        registered = _kind(approval.kind)
        word = getattr(registered.kind, "used_word", None) if registered else None
        return Answer(ALREADY_USED, f"{approval.id} was already {word or 'used'} at {used} SGT; it can't be undone.", approval)
    if approval.status == EXPIRED:
        return Answer(EXPIRED, f"{approval.id} expired: {approval.close_reason}.", approval)
    if approval.status == SUPERSEDED:
        successor = _successor(conn, approval)
        by = f" by {successor.id}" if successor else ""
        return Answer(SUPERSEDED, f"{approval.id} was superseded{by}: {approval.close_reason}.", approval)
    return Answer(ALREADY_DECIDED, f"{approval.id} was already {approval.status}.", approval)


def _attribution(origin: Origin, actor: str | None) -> tuple[str | None, str | None]:
    """(decided_by, None) for the SSH origin whose attribution holds, or
    (None, why it is refused). Terminal decisions are off (ADR 0004)."""
    if not isinstance(origin, Origin) or not origin.human:
        return None, getattr(origin, "reason", None) or NOT_DISPATCH
    # SSH: the Discord user id is attribution, checked for consistency with
    # .env. The guard is the SSH key and Dispatch's own allowlist (A8).
    if not actor or not _DISCORD_ACTOR.fullmatch(actor):
        return None, "a Dispatch decision needs --actor discord:<id>"
    control = config.secret("CONTROL_DISCORD_USER_ID")
    if not control:
        return None, "CONTROL_DISCORD_USER_ID isn't set, so a Dispatch decision can't be checked"
    if actor != f"discord:{control}":
        return None, f"{actor} isn't the control user"
    return actor, None


def _refuse(conn, shown: str, approval: Approval | None, agent: str | None, *, actor, origin, ref, why) -> Answer:
    """A refused decision is logged (G12), though nothing about the record changes."""
    _audit(conn, "approval.refused", approval, agent, actor=actor, shown=shown,
           origin=getattr(origin, "kind", None), ref=ref, why=why)
    return Answer(REFUSED, f"refused: {why}.", approval)


def _args_problem(approval: Approval, kind: ApprovalKind, decision: str, args: dict[str, str]) -> str | None:
    wanted = tuple(getattr(kind, "decision_args", ()) or ()) if decision == "approve" else ()
    extra = sorted(set(args) - set(wanted))
    if extra:
        return f"refused: {approval.id} doesn't take {', '.join(extra)}."
    if any(not str(args.get(name) or "").strip() for name in wanted):
        return getattr(kind, "args_help", None) or f"refused: say {' '.join(f'{name}=…' for name in wanted)}."
    return None


def decide(
    conn: sqlite3.Connection,
    approval_id: str,
    decision: str,
    *,
    actor: str | None,
    origin: Origin,
    source_ref: str | None,
    args: dict[str, str] | None,
) -> Answer:
    """Record Ting Yu's approve or skip on one request (A7 to A10).

    `origin` comes from `origin.py`, through ticket 11's `remote`: only an
    SSH origin decides, and its `actor` must be the control user. Terminal
    decisions are off (ADR 0004). `source_ref` is Dispatch's
    delivery reference: the same one twice returns the first answer.
    Deadlines are judged by growth's clock. A skip is allowed until the
    request is claimed. On approve, the kind's `on_approve` runs inside the
    decision's transaction after `approved` is written; a `BadArgs` from it,
    or a missing decision argument, answers `refused` and records nothing.
    """
    if decision not in DECISIONS:
        raise ValueError(f"a decision is approve or skip, not {decision!r}")
    args = {str(k): str(v) for k, v in (args or {}).items()}
    number = parse_id(approval_id)
    shown = format_id(number) if number is not None else str(approval_id)
    decided_by, why = _attribution(origin, actor)
    if decided_by is None:
        found = get(conn, shown) if number is not None else None
        return _refuse(conn, shown, found, None, actor=actor, origin=origin, ref=source_ref, why=why or "not a human origin")
    if number is None or get(conn, shown) is None:
        return Answer(UNKNOWN_ID, f"There is no approval request {shown}.")
    first = _first_answer(conn, number, source_ref)
    if first is not None:
        return first
    try:
        with db.transaction(conn):
            return _decide_locked(conn, number, decision, decided_by, origin, source_ref, args)
    except BadArgs as refusal:
        return Answer(REFUSED, str(refusal), get(conn, shown))
    except NotApproved as refusal:
        # A kind applied on decide claims inside on_approve (app-build), and
        # the claim refused: the decision rolled back, and it answers.
        found = get(conn, shown)
        registered = _kind(found.kind) if found else None
        return _refuse(conn, shown, found, registered.agent if registered else None,
                       actor=decided_by, origin=origin, ref=source_ref, why=refusal.text)


def _first_answer(conn, number: int, source_ref: str | None) -> Answer | None:
    """The answer already recorded for this delivery, if it came before (A9)."""
    if not source_ref:
        return None
    first = db.one(
        conn, "SELECT answer, text FROM approval_decisions WHERE approval_id = ? AND source_ref = ?", (number, source_ref)
    )
    return Answer(first["answer"], first["text"], _reload(conn, number)) if first else None


def _decide_locked(conn, number: int, decision: str, decided_by: str, origin: Origin, source_ref, args) -> Answer:
    # Again under the lock: a retry of the same delivery may have waited
    # here while the first copy was being decided.
    first = _first_answer(conn, number, source_ref)
    if first is not None:
        return first
    approval = _reload(conn, number)
    registered = _kind(approval.kind)
    if registered is None:
        why = f"the plug-in for {approval.kind} isn't loaded, so {approval.id} can't be decided"
        return _refuse(conn, approval.id, approval, None, actor=decided_by, origin=origin, ref=source_ref, why=why)
    if not approval.live:
        return _closed_answer(conn, approval)
    now = timeutil.now_sgt()
    current = _refresh(conn, registered, approval, now, raise_new=True)
    if not current.live or (decision == "approve" and current.status == APPROVED):
        return _closed_answer(conn, current)
    problem = _args_problem(current, registered.kind, decision, args)
    if problem:
        raise BadArgs(problem)
    at = timeutil.stamp(now)
    if decision == "approve":
        asked = registered.kind.deadlines(conn, current.subject, now).use_by
        use_by = _clamp(asked, now) if asked is not None else None
        conn.execute(
            "UPDATE approvals SET status = 'approved', decided_at = ?, decided_by = ?, decided_origin = ?, "
            "decision_ref = ?, use_by = ? WHERE id = ?",
            (at, decided_by, origin.kind, source_ref, timeutil.stamp(use_by) if use_by else None, number),
        )
        _audit(conn, "approval.approved", _reload(conn, number), registered.agent,
               actor=decided_by, origin=origin.kind, ref=source_ref, at=at, args=args or None)
        on_approve = _hook(registered.kind, "on_approve")
        extra = on_approve(conn, current.subject, dict(args)) if on_approve is not None else None
        text = f"{current.id} approved." + (f" {extra}" if extra else "")
    else:
        conn.execute(
            "UPDATE approvals SET status = 'skipped', decided_at = ?, decided_by = ?, decided_origin = ?, decision_ref = ? "
            "WHERE id = ?",
            (at, decided_by, origin.kind, source_ref, number),
        )
        _audit(conn, "approval.skipped", _reload(conn, number), registered.agent,
               actor=decided_by, origin=origin.kind, ref=source_ref, at=at)
        on_skip = _hook(registered.kind, "on_skip")
        if on_skip is not None:
            on_skip(conn, current.subject)
        text = f"{current.id} skipped."
    conn.execute(
        "INSERT INTO approval_decisions (approval_id, source_ref, decision, actor, origin, decided_at, content_hash, "
        "args_json, answer, text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (number, source_ref, decision, decided_by, origin.kind, at, current.content_hash,
         json.dumps(args, sort_keys=True), RECORDED, text),
    )
    return Answer(RECORDED, text, _reload(conn, number))


# --- cards in #approvals (A12) ------------------------------------------------
#
# `cards.sweep()` posts and edits the cards (A12's `post_unposted`); these are
# the reads and the one write it needs, kept here with the rest of the state.


def unposted(conn: sqlite3.Connection) -> list[Approval]:
    """Pending requests whose card hasn't gone out, oldest first. Only a
    pending request gets a card: one decided first never posts."""
    rows = conn.execute("SELECT * FROM approvals WHERE status = 'pending' AND posted_at IS NULL ORDER BY id")
    return [Approval.from_row(r) for r in rows]


def successor(conn: sqlite3.Connection, approval: Approval) -> Approval | None:
    """The request raised over new content in place of `approval`, if any."""
    return _successor(conn, approval)


def mark_posted(conn: sqlite3.Connection, approval: Approval, message_id: str | None) -> None:
    """Record that `approval`'s card went out, once (the trigger allows
    `posted_at` and `message_id` to be set once, on an unused record). Call
    it inside the caller's `db.transaction(conn)`; it writes
    `approval.posted` (A16)."""
    at = timeutil.stamp()
    conn.execute(
        "UPDATE approvals SET posted_at = ?, message_id = ? WHERE id = ? AND posted_at IS NULL AND used_at IS NULL",
        (at, message_id, approval.number),
    )
    registered = _kind(approval.kind)
    _audit(conn, "approval.posted", approval, registered.agent if registered else None, actor="engine", at=at,
           message_id=message_id)
