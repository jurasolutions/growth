"""Terminal decisions are off, for every kind and every record state (test strategy v3 G38;
MC §4.6 A8 as amended 2026-10-26; ADR 0004).

Run over the gate-matrix adapters (`tests/gate_adapter_*.py`, collected as `test_approval_gates.py`
collects them), each with one record in every D7 state:

- `approve` and `skip` typed in Terminal exit 2 with the pointer to #approvals, and change nothing:
  the record, its events, its decisions, the card double, and what went out;
- `approvals.decide()` answers `refused` for every origin but `Origin.ssh()`, and records no
  decision; the same record then still decides through the SSH origin when it is pending.

A kind applied on decide (`group-rules`, `app-build`) has no "approved and unused" record and no
lapse from approved, so those two states are not collected for it.
"""

from __future__ import annotations

import types
from contextlib import suppress

import pytest
from click.testing import CliRunner

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, approvals_cli, cards, db, origin, timeutil
from jura_growth.cli import cli
from jura_growth.origin import Origin
from test_approval_gates import adapters

REFUSAL = f"refused: {origin.TERMINAL_OFF}."

STATES = (
    "pending",
    "approved and unused",
    "approved and used",
    "skipped",
    "expired from pending",
    "expired from approved, unused",
    "superseded",
)
NOT_APPLIED_ON_DECIDE = {"approved and unused", "expired from approved, unused"}

TYPED = {
    "approve": (["approve", "{id}"], ["approve", "{id}", "promo_days=any", "post_days=any", "--ref", "m:d"]),
    "skip": (["skip", "{id}"], ["skip", "{id}", "wrong", "one", "--ref", "m:d"]),
}

# Every origin but Origin.ssh(): each refused reason `origin.py` gives, and objects that only
# look like an origin (the old Terminal one, an SSH one built outside `Origin`, and none at all).
NOT_SSH = {
    "refused: Terminal": Origin.refused(origin.TERMINAL_OFF),
    "refused: not Dispatch": Origin.refused(origin.NOT_DISPATCH),
    "refused: in Claude": Origin.refused(origin.IN_CLAUDE),
    "refused: unchecked": Origin.refused(origin.UNCHECKED),
    "a Terminal lookalike": types.SimpleNamespace(kind="terminal", human=True, user="tingyu", code="c6c430", reason=None),
    "an SSH lookalike": types.SimpleNamespace(kind="ssh", human=True, reason=None),
    "none": None,
}


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames:
        cases = [(a, s) for a in adapters() for s in STATES if not (a.applied_on_decide and s in NOT_APPLIED_ON_DECIDE)]
        metafunc.parametrize("case", cases, ids=[f"{a.kind}-{s.replace(' ', '-').replace(',', '')}" for a, s in cases])


@pytest.fixture
def made(case, conn, monkeypatch, tmp_path, discord_double):  # noqa: F811 - the fixture
    """(gate, record): one record of the case's kind in the case's state, its card posted."""
    adapter_class, state = case
    gate = adapter_class(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)
    return gate, in_state(gate, conn, monkeypatch, state)


def in_state(gate, conn, monkeypatch, state: str) -> approvals.Approval:
    subject = gate.item()
    approval = gate.raise_request(subject)
    cards.sweep(conn)  # the card goes out while the request is pending
    if state in ("approved and unused", "approved and used", "expired from approved, unused"):
        assert gate.approve(approval).answer == "recorded"
    if state == "approved and used" and not gate.applied_on_decide:
        with suppress(Exception):
            gate.attempt(subject)
    elif state == "skipped":
        assert gate.skip(approval).answer == "recorded"
    elif state == "expired from pending":
        approvals.expire_due(conn, aw.at(monkeypatch, approval.decide_by))
    elif state == "expired from approved, unused":
        lapse = aw.get(conn, approval.id).use_by or approval.decide_by
        approvals.expire_due(conn, aw.at(monkeypatch, lapse))
    elif state == "superseded":
        gate.change(subject)
        approvals.expire_due(conn, timeutil.now_sgt())
    cards.sweep(conn)  # and is edited for the record's new state
    record = aw.get(conn, approval.id)
    assert describe(record) == state, record
    assert record.message_id, "the card was posted, so its message id is stored"
    return record


def describe(record: approvals.Approval) -> str:
    """The D7 state a record is in."""
    if record.status == "approved":
        return "approved and used" if record.used_at else "approved and unused"
    if record.status == "expired":
        return "expired from approved, unused" if record.decided_at else "expired from pending"
    return record.status


def snapshot(conn, record, gate, discord_double) -> dict:  # noqa: F811 - the fixture
    number = record.number
    return {
        "record": db.one(conn, "SELECT * FROM approvals WHERE id = ?", (number,)),
        "events": [dict(r) for r in conn.execute("SELECT * FROM events ORDER BY id")],
        "decisions": [dict(r) for r in conn.execute("SELECT * FROM approval_decisions WHERE approval_id = ?", (number,))],
        "discord": len(discord_double.requests),
        "went out": gate.went_out(),
    }


@pytest.mark.parametrize("decision", ["approve", "skip"])
def test_a_decision_typed_in_terminal_is_refused_for_every_kind_and_state(made, decision, conn, discord_double):  # noqa: F811
    gate, record = made
    before = snapshot(conn, record, gate, discord_double)
    for words in TYPED[decision]:
        result = CliRunner().invoke(cli, [w.format(id=record.id) for w in words], input="c6c430\n")
        assert result.exit_code == 2 == approvals_cli.EXIT_CODES["refused"], result.output
        assert result.output.strip() == REFUSAL and "#approvals" in result.output
        assert "code" not in result.output.lower()  # no code asked for
    assert snapshot(conn, record, gate, discord_double) == before
    cards.sweep(conn)
    assert len(discord_double.requests) == before["discord"], "the card has nothing to change"


@pytest.mark.parametrize("decision", ["approve", "skip"])
def test_decide_refuses_every_origin_but_ssh_for_every_kind_and_state(made, decision, conn, discord_double):  # noqa: F811
    gate, record = made
    before = snapshot(conn, record, gate, discord_double)
    wanted = getattr(approvals.kinds()[record.kind].kind, "decision_args", ()) or ()
    args = {name: "any" for name in wanted} if decision == "approve" else {}
    for name, given in NOT_SSH.items():
        answer = approvals.decide(conn, record.id, decision, actor=aw.CONTROL, origin=given, source_ref=f"m:{name}", args=args)
        assert answer.answer == "refused", name
    after = snapshot(conn, record, gate, discord_double)
    assert after["record"] == before["record"]
    assert after["decisions"] == before["decisions"]
    assert after["went out"] == before["went out"]
    added = after["events"][len(before["events"]):]
    assert {e["kind"] for e in added} == {"approval.refused"} and len(added) == len(NOT_SSH)
    if record.status == "pending":  # the refusals were the origin's: the SSH origin still decides
        decided = gate.approve(record) if decision == "approve" else gate.skip(record)
        assert decided.answer == "recorded"
