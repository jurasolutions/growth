"""The approval gate matrix (test strategy v3 §5.2), run once per kind.

This file is the harness, owned by ticket MC-04a alone. It collects one
adapter from every `tests/gate_adapter_*.py` module through
`pytest_generate_tests`, so a kind's ticket adds only its own adapter file
and never edits this one (ticket review T7). The core-only cases (G8, G11,
G12, G16, G26, G27, G32, G37) are in `test_approvals.py`.

An adapter module exports `ADAPTER`, a class built per test as
`ADAPTER(conn=, monkeypatch=, tmp_path=)`, which registers its kind, freezes
the clock and prepares its world. It has:

    kind: str                  the approval kind
    agent: str                 the agent whose pause flag stops the action
    applied_on_decide: bool    True for kinds that take effect inside the
                               decision (group-rules, app-build); the cases
                               marked "not applied on decide" (those taking
                               the `claimed` fixture) aren't collected for them
    item() -> subject          a fresh item that would raise a request
    twin(subject) -> subject   another item whose content reads the same
    raise_request(subject) -> Approval   through the kind's raising command
    approve(approval) -> Answer, skip(approval) -> Answer
                               a Terminal decision with the right code and
                               any decision arguments the kind needs
    attempt(subject)           run the gated action once; a refusal is not
                               an exception
    went_out() -> int          outward effects so far (the effect's double)
    seen_at_call() -> [bool]   per effect: the claim was committed when the
                               double was called, read on a fresh connection
    change(subject), remove(subject)   change one field of the content; make
                               the item gone
    switch(on: bool)           the kind's own switch
    fail_in_flight(on: bool)   make the caller's in-flight write fail
    hook_ran(hook, subject) -> int     how often on_skip, on_expire or
                               on_lapse took effect for the item

Expected in every refusal: nothing went out, and no `approval.used` event.
"""

import importlib
from contextlib import suppress
from pathlib import Path

import pytest

from jura_growth import approvals, pause, paths, timeutil

import approval_world as aw

ADAPTER_MODULES = sorted(Path(__file__).parent.glob("gate_adapter_*.py"))


def adapters() -> list[type]:
    return [importlib.import_module(path.stem).ADAPTER for path in ADAPTER_MODULES]


def pytest_generate_tests(metafunc):
    if "adapter_class" in metafunc.fixturenames:
        found = adapters()
        if "claimed" in metafunc.fixturenames:
            # Cases "not applied on decide" (§5.2) are never collected for kinds applied on
            # decide, rather than skipped, so the suite has no skips (E3). Those kinds trace
            # the cases that do apply to them (G9, G19, G21, G22) in their own test files.
            found = [a for a in found if not a.applied_on_decide]
        metafunc.parametrize("adapter_class", found, ids=[a.kind for a in found])


@pytest.fixture
def gate(adapter_class, conn, monkeypatch, tmp_path):
    return adapter_class(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)


@pytest.fixture
def claimed(gate):
    """The gate, for a case collected only for kinds whose action claims later."""
    return gate


def attempt(gate, subject):
    with suppress(Exception):
        gate.attempt(subject)


def claims(conn) -> int:
    return aw.claims(conn)


def requested(gate) -> tuple[str, approvals.Approval]:
    subject = gate.item()
    return subject, gate.raise_request(subject)


def test_g1_no_approval_record_refuses(gate, conn):
    attempt(gate, gate.item())
    assert gate.went_out() == 0 and claims(conn) == 0


def test_g2_a_pending_request_refuses(gate, conn):
    subject, _ = requested(gate)
    attempt(gate, subject)
    assert gate.went_out() == 0 and claims(conn) == 0


def test_g3_a_skipped_request_refuses_and_its_skip_action_ran_once(gate, conn):
    subject, approval = requested(gate)
    assert gate.skip(approval).answer == "recorded"
    attempt(gate, subject)
    assert gate.went_out() == 0 and claims(conn) == 0
    assert gate.hook_ran("on_skip", subject) == 1


def test_g4a_approve_at_the_decide_by_answers_expired_one_second_before_records(gate, conn, monkeypatch):
    subject, approval = requested(gate)
    aw.at(monkeypatch, approval.decide_by)
    assert gate.approve(approval).answer == "expired"
    assert aw.get(conn, approval.id).status == "expired"
    other, second = requested(gate)
    aw.at(monkeypatch, aw.later(second.decide_by, seconds=-1))
    assert gate.approve(second).answer == "recorded"


def test_g4b_an_approval_past_its_use_by_refuses_with_no_lapse_written_first(claimed, conn, monkeypatch):
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    use_by = aw.get(conn, approval.id).use_by
    aw.at(monkeypatch, use_by)
    attempt(gate, subject)
    assert gate.went_out() == 0 and claims(conn) == 0
    other, second = requested(gate)
    gate.approve(second)
    aw.at(monkeypatch, aw.later(aw.get(conn, second.id).use_by, seconds=-1))
    attempt(gate, other)
    assert gate.went_out() == 1


def test_g5_expire_due_writes_each_lapse_once_and_both_refuse(gate, conn, monkeypatch):
    waiting, unanswered = requested(gate)
    approved_subject, approved = requested(gate)
    gate.approve(approved)
    use_by = aw.get(conn, approved.id).use_by
    latest = max(unanswered.decide_by, use_by or unanswered.decide_by)
    now = aw.at(monkeypatch, latest)
    approvals.expire_due(conn, now)
    assert aw.get(conn, unanswered.id).status == "expired"
    assert gate.hook_ran("on_expire", waiting) == 1
    if not gate.applied_on_decide:
        lapsed = aw.get(conn, approved.id)
        assert lapsed.status == "expired" and lapsed.used_at is None
        assert gate.hook_ran("on_lapse", approved_subject) == 1
    attempt(gate, waiting)
    if not gate.applied_on_decide:
        attempt(gate, approved_subject)
        assert claims(conn) == 0
    assert gate.went_out() == 0
    before = [aw.get(conn, a.id) for a in (unanswered, approved)]
    assert approvals.expire_due(conn, now) == []
    assert [aw.get(conn, a.id) for a in (unanswered, approved)] == before
    assert gate.hook_ran("on_expire", waiting) == 1
    if not gate.applied_on_decide:
        assert gate.hook_ran("on_lapse", approved_subject) == 1


def test_g6_a_request_superseded_before_its_decision_refuses(gate, conn):
    subject, approval = requested(gate)
    gate.change(subject)
    approvals.expire_due(conn, timeutil.now_sgt())
    assert aw.get(conn, approval.id).status == "superseded"
    attempt(gate, subject)
    assert gate.approve(approval).answer == "superseded"
    assert gate.went_out() == 0 and claims(conn) == 0


def test_g7_an_approval_is_used_once(claimed, conn):
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    attempt(gate, subject)
    used = aw.get(conn, approval.id)
    assert gate.went_out() == 1 and used.used_at and used.used_by_run
    attempt(gate, subject)
    assert gate.went_out() == 1 and claims(conn) == 1


def test_g9_content_changed_after_approval_refuses_supersedes_and_raises_the_new_request(claimed, conn):
    """AC-M4.2. A kind applied on decide traces it in its own tests."""
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    gate.change(subject)
    attempt(gate, subject)
    assert aw.get(conn, approval.id).status == "superseded"
    [fresh] = [a for a in approvals.pending(conn) if a.subject == subject]
    assert fresh.supersedes == approval.number and fresh.content_hash != approval.content_hash
    assert gate.went_out() == 0 and claims(conn) == 0


def test_g10_the_right_content_for_the_wrong_subject_refuses(gate, conn):
    subject, approval = requested(gate)
    twin = gate.twin(subject)
    gate.approve(approval)
    before = gate.went_out()
    attempt(gate, twin)
    assert gate.went_out() == before


def test_g15_a_second_decision_answers_already_decided_and_changes_nothing(gate, conn):
    _, approval = requested(gate)
    gate.approve(approval)
    first = aw.get(conn, approval.id)
    # A kind applied on decide may already have claimed it (app-build).
    assert gate.approve(first).answer == ("already-used" if first.used_at else "already-decided")
    assert aw.get(conn, approval.id) == first
    _, other = requested(gate)
    gate.skip(other)
    skipped = aw.get(conn, other.id)
    assert gate.approve(skipped).answer == "already-decided"
    assert gate.skip(skipped).answer == "already-decided"
    assert aw.get(conn, other.id) == skipped


def test_g17_a_skip_after_approval_wins_until_the_claim(claimed, conn):
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    assert gate.skip(approval).answer == "recorded"
    attempt(gate, subject)
    assert gate.went_out() == 0 and claims(conn) == 0
    assert gate.hook_ran("on_skip", subject) == 1


def test_g18_a_skip_after_use_answers_already_used_and_changes_nothing(gate, conn):
    subject, approval = requested(gate)
    gate.approve(approval)
    if not gate.applied_on_decide:
        attempt(gate, subject)
    used = aw.get(conn, approval.id)
    answer = gate.skip(used)
    assert answer.answer == ("already-used" if used.used_at else "already-decided")
    assert aw.get(conn, approval.id) == used


@pytest.mark.parametrize("brake", ["PAUSE file", "paused agent", "the kind's switch"])
def test_g19_a_kill_switch_refuses_without_claiming_until_it_clears(claimed, conn, brake):
    """AC-M4.6."""
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    if brake == "PAUSE file":
        paths.pause_file().write_text("stop\n", encoding="utf-8")
    elif brake == "paused agent":
        pause.pause(conn, gate.agent, "by hand", notify=False)
    else:
        gate.switch(True)
    attempt(gate, subject)
    assert gate.went_out() == 0 and claims(conn) == 0
    assert aw.get(conn, approval.id).used_at is None
    if brake == "PAUSE file":
        paths.pause_file().unlink()
    elif brake == "paused agent":
        pause.resume(conn, gate.agent)
    else:
        gate.switch(False)
    attempt(gate, subject)
    assert gate.went_out() == 1 and claims(conn) == 1


def test_g21_the_claim_is_committed_before_the_outward_call(claimed, conn):
    """AC-M4.3: the effect's double sees the record used, on a fresh connection."""
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    attempt(gate, subject)
    assert gate.seen_at_call() == [True]


def test_g22_a_failed_in_flight_write_rolls_the_claim_back(claimed, conn):
    gate = claimed
    subject, approval = requested(gate)
    gate.approve(approval)
    gate.fail_in_flight(True)
    attempt(gate, subject)
    record = aw.get(conn, approval.id)
    assert record.status == "approved" and record.used_at is None
    assert gate.went_out() == 0 and claims(conn) == 0
    gate.fail_in_flight(False)
    attempt(gate, subject)
    assert gate.went_out() == 1 and claims(conn) == 1


def test_g25_a_gone_item_supersedes_at_the_next_claim_and_raises_nothing(gate, conn):
    gone_item_case(gate, conn, approved=False)


def test_g25_a_gone_item_approved_but_unclaimed_supersedes_too(claimed, conn):
    gone_item_case(claimed, conn, approved=True)


def gone_item_case(gate, conn, *, approved: bool) -> None:
    subject, approval = requested(gate)
    if approved:
        gate.approve(approval)
    gate.remove(subject)
    attempt(gate, subject)
    approvals.expire_due(conn, timeutil.now_sgt())
    record = aw.get(conn, approval.id)
    assert record.status == "superseded"
    assert [a for a in approvals.pending(conn) if a.subject == subject] == []
    assert gate.went_out() == 0 and claims(conn) == 0


def test_g29_every_transition_leaves_one_event_with_actor_origin_ref_hash_and_time(gate, conn, monkeypatch):
    now = timeutil.stamp(timeutil.now_sgt())
    subject, approval = requested(gate)
    gate.approve(approval)
    if not gate.applied_on_decide:
        attempt(gate, subject)
    _, skipped = requested(gate)
    gate.skip(skipped)
    changed, superseded = requested(gate)
    gate.change(changed)
    approvals.expire_due(conn, timeutil.now_sgt())
    _, unanswered = requested(gate)
    later = aw.at(monkeypatch, unanswered.decide_by)
    approvals.expire_due(conn, later)
    counts = {
        "approval.requested": 4, "approval.approved": 1, "approval.used": 1,
        "approval.skipped": 1, "approval.superseded": 1, "approval.expired": 1,
    }
    if gate.applied_on_decide:
        counts.pop("approval.used")  # app-build's claim is in its own tests
    for kind, count in counts.items():
        found = [e for e in aw.events(conn, kind) if e["kind"] == gate.kind]
        assert len(found) == count, kind
        assert len([e for e in aw.mirrored(kind) if e["kind"] == gate.kind]) == count, kind
        for event in found:
            record = aw.get(conn, event["approval"])
            assert event["hash"] == record.content_hash
            assert event["at"] == (timeutil.stamp(later) if kind == "approval.expired" else now)
            if kind in ("approval.approved", "approval.skipped"):
                assert event["actor"] == record.decided_by and event["actor"].startswith("discord:")
                assert event["origin"] == "ssh" and event["ref"] == record.decision_ref
            else:
                assert event["actor"] and event["origin"] is None and event["ref"] is None
