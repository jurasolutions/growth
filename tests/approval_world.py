"""Builders for the approvals core: the fake kind, its plug-in, and its gated
action. Kind-specific builders live in each kind's own `gate_adapter_<kind>.py`
(ticket review T7); this file holds only the core and the fake kind.

The fake kind keeps its items in memory: `world.items[subject]` is the text
that would go out, and deleting it makes the item gone. Its hooks record each
call in `world.calls`, so a test can assert a hook ran once, with which
arguments, and that `on_approve` saw `approved` already written.
"""

from __future__ import annotations

import json
import sqlite3
import types
from datetime import datetime, timedelta

from jura_growth import agents, approvals, db, log, paths, timeutil
from jura_growth.origin import Origin

# The real discovery, kept before any test patches `agents.plugins`.
REAL_PLUGINS = agents.plugins

KIND = "fake"
AGENT = "fake-agent"
# A Tuesday that is a business day (test strategy v3 §3, reference dates).
NOW = "2026-11-10T10:02:15+08:00"
TERMINAL_USER = "tingyu"


def at(monkeypatch, moment: str) -> datetime:
    """Freeze growth's clock at `moment` (an ISO timestamp)."""
    monkeypatch.setenv("JURA_GROWTH_NOW", moment)
    return timeutil.parse(moment)


def later(moment: str, **delta) -> str:
    return timeutil.stamp(timeutil.parse(moment) + timedelta(**delta))


class FakeKind:
    """An approval kind with no agent behind it. `decision_args` and the
    recording `on_approve` let ticket 11 test the remote grammar too."""

    name = KIND
    decision_args = ("promo_days", "post_days")

    def __init__(self, world: "World"):
        self.world = world

    def content(self, conn, subject):
        text = self.world.items.get(subject)
        if text is None:
            return None
        return json.dumps({"subject": subject, "text": text}, sort_keys=True).encode("utf-8")

    def preview(self, conn, subject):
        return approvals.Preview(title=f"fake item {subject}", text=self.world.items.get(subject) or "", reason="a test asked")

    def deadlines(self, conn, subject, now):
        return approvals.Deadlines(decide_by=now + self.world.decide_in, use_by=now + self.world.use_in if self.world.use_in else None)

    def switched_off(self, conn, subject):
        return self.world.switch

    def on_approve(self, conn, subject, args):
        status = conn.execute(
            "SELECT status FROM approvals WHERE kind = ? AND subject = ? ORDER BY id DESC LIMIT 1", (KIND, subject)
        ).fetchone()["status"]
        self.world.calls.append(("on_approve", subject, dict(args), status, conn.in_transaction))
        if self.world.approve_raises:
            raise approvals.BadArgs(self.world.approve_raises)
        return self.world.approve_says

    def on_skip(self, conn, subject):
        self.world.calls.append(("on_skip", subject))

    def on_expire(self, conn, subject):
        self.world.calls.append(("on_expire", subject))

    def on_lapse(self, conn, subject):
        self.world.calls.append(("on_lapse", subject))


class World:
    """The fake kind's items, switches and the record of what went out."""

    def __init__(self):
        self.items: dict[str, str] = {}
        self.calls: list[tuple] = []
        self.sent: list[dict] = []
        self.decide_in = timedelta(days=2)
        self.use_in: timedelta | None = timedelta(days=3)
        self.switch: str | None = None
        self.approve_raises: str | None = None
        self.approve_says: str | None = None
        self.fail_in_flight = False
        self.kind = FakeKind(self)
        self.plugin = types.ModuleType("fake_plugin")
        self.plugin.NAME = AGENT
        self.plugin.approval_kinds = lambda: {KIND: self.kind}
        self._next = 0

    def item(self, text: str = "Quotes that write themselves") -> str:
        self._next += 1
        subject = f"fake_item:{self._next}"
        self.items[subject] = text
        return subject

    def ran(self, hook: str, subject: str | None = None) -> list[tuple]:
        return [c for c in self.calls if c[0] == hook and (subject is None or c[1] == subject)]

    def act(self, conn: sqlite3.Connection, subject: str, *, run_id: int | None = None):
        """The fake gated action: claim, write the in-flight marker in the
        same transaction, commit, then the outward effect. Returns the
        refusal, or None when it went out."""
        with db.transaction(conn):
            try:
                approvals.use(conn, KIND, subject, run_id=run_id)
            except approvals.NotApproved as refusal:
                return refusal
            if self.fail_in_flight:
                raise RuntimeError("in-flight marker failed")
            conn.execute("INSERT INTO fake_in_flight (subject) VALUES (?)", (subject,))
        self.effect(subject)
        return None

    def effect(self, subject: str) -> None:
        """The outward call's double. Like the Resend hook (G21), it reads the
        record through a fresh connection at call time."""
        fresh = db.connect(migrate_now=False)
        try:
            row = fresh.execute(
                "SELECT used_at, used_by_run FROM approvals WHERE kind = ? AND subject = ? AND used_at IS NOT NULL",
                (KIND, subject),
            ).fetchone()
        finally:
            fresh.close()
        self.sent.append({"subject": subject, "used_at": row["used_at"] if row else None, "used_by_run": row["used_by_run"] if row else None})


def install(monkeypatch, world: World | None = None) -> World:
    """Register the fake plug-in beside the real ones."""
    world = world or World()
    real = agents.plugins
    monkeypatch.setattr(agents, "plugins", lambda: (*real(), world.plugin))
    return world


def prepare(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS fake_in_flight (subject TEXT NOT NULL)")


def terminal(approval, code: str | None = None) -> Origin:
    return Origin.terminal(TERMINAL_USER, code if code is not None else approval.code)


def approve(conn, approval, *, args=None, origin=None, actor=None, source_ref=None):
    return approvals.decide(
        conn,
        approval.id,
        "approve",
        actor=actor,
        origin=origin or terminal(approval),
        source_ref=source_ref,
        args={"promo_days": "sat,sun", "post_days": "any"} if args is None else args,
    )


def skip(conn, approval, *, origin=None, actor=None, source_ref=None):
    return approvals.decide(conn, approval.id, "skip", actor=actor, origin=origin or terminal(approval), source_ref=source_ref, args={})


def run(conn) -> int:
    return log.start_run(conn, AGENT, "fake-job")


def mirrored(kind: str) -> list[dict]:
    """The payloads of every `kind` line in the JSONL mirror."""
    folder = paths.data_dir() / "runs"
    found = []
    for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry["kind"] == kind:
                found.append(entry["payload"])
    return found


def claims(conn) -> int:
    """`approval.used` events, which the database and the mirror must agree on."""
    in_db = len(events(conn, "approval.used"))
    assert len(mirrored("approval.used")) == in_db, "the mirror and growth.db disagree about claims"
    return in_db


def events(conn, kind: str) -> list[dict]:
    return [json.loads(r["payload_json"]) for r in conn.execute("SELECT payload_json FROM events WHERE kind = ? ORDER BY id", (kind,))]


def record(conn, approval_id: str) -> dict:
    return db.one(conn, "SELECT * FROM approvals WHERE id = ?", (approvals.parse_id(approval_id),))
