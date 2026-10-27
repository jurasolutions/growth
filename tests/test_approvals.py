"""The approvals core (seam S6): request, decide, use, expire_due, pending,
get and raised_by against a temp growth.db and the fake kind (MC §4.6 A1 to
A17, ADR 0003). The cases every kind runs are in test_approval_gates.py."""

import hashlib
import time
import types

import pytest

from jura_growth import approvals, db
from jura_growth.origin import Origin

import approval_world as aw


@pytest.fixture
def world(monkeypatch, conn):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def test_request_raises_one_pending_record_over_the_kinds_content(conn, world):
    subject = world.item("Hello")
    run_id = aw.run(conn)
    approval = aw.request(conn, aw.KIND, subject, run_id=run_id)
    expected = hashlib.sha256(world.kind.content(conn, subject)).hexdigest()
    assert approval.id == "A-0001"
    assert approval.status == "pending"
    assert approval.content_hash == expected
    assert approval.requested_at == aw.NOW
    assert approval.decide_by == "2026-11-12T10:02:15+08:00"
    assert approval.raised_by_run == run_id
    assert aw.get(conn, "A-0001") == approval
    [event] = aw.events(conn, "approval.requested")
    assert event["approval"] == "A-0001" and event["hash"] == expected and event["at"] == aw.NOW


def raise_one(conn, world, text="Hello", **kw):
    subject = world.item(text)
    return subject, aw.request(conn, aw.KIND, subject, **kw)


def test_request_twice_over_the_same_content_returns_the_same_record(conn, world):
    """G26: one live request per subject."""
    subject, first = raise_one(conn, world)
    again = aw.request(conn, aw.KIND, subject, reason="asked again")
    assert again == first
    assert len(aw.events(conn, "approval.requested")) == 1


def test_a_second_live_row_for_one_subject_fails_on_the_partial_unique_index(conn, world):
    """G26: the index, not only the code, keeps one live request."""
    subject, first = raise_one(conn, world)
    with pytest.raises(Exception, match="UNIQUE"):
        conn.execute(
            "INSERT INTO approvals (kind, subject, content_hash, reason, requested_at, decide_by) VALUES (?, ?, 'x', 'r', ?, ?)",
            (aw.KIND, subject, aw.NOW, aw.later(aw.NOW, days=1)),
        )


def test_request_over_new_content_supersedes_the_live_record_and_raises_a_new_one(conn, world):
    subject, first = raise_one(conn, world, "Hello")
    world.items[subject] = "Hello again"
    second = aw.request(conn, aw.KIND, subject)
    assert second.id == "A-0002" and second.status == "pending" and second.supersedes == first.number
    old = aw.get(conn, first.id)
    assert old.status == "superseded" and old.close_reason == "the content changed" and old.closed_at == aw.NOW
    assert [e["approval"] for e in aw.events(conn, "approval.superseded")] == ["A-0001"]


def test_request_for_a_gone_item_supersedes_the_live_record_and_raises_nothing(conn, world):
    subject, first = raise_one(conn, world)
    del world.items[subject]
    assert approvals.request(conn, aw.KIND, subject, reason="a test asked", run_id=None) is None
    assert aw.get(conn, first.id).status == "superseded"
    assert approvals.get(conn, "A-0002") is None  # nothing raised


def test_request_for_a_kind_no_plugin_declares_raises_unknown_kind(conn, world):
    with pytest.raises(approvals.UnknownKind):
        approvals.request(conn, "no-such-kind", "x:1", reason="r", run_id=None)


def test_raised_by_lists_the_requests_a_run_raised(conn, world):
    run_id = aw.run(conn)
    a = aw.request(conn, aw.KIND, world.item("one"), run_id=run_id)
    raise_one(conn, world, "not this run")
    b = aw.request(conn, aw.KIND, world.item("two"), run_id=run_id)
    assert [x.id for x in approvals.raised_by(conn, run_id)] == [a.id, b.id]


def test_ids_are_never_reused_after_a_pending_row_is_deleted(conn, world):
    _, first = raise_one(conn, world)
    conn.execute("DELETE FROM approvals WHERE id = ?", (first.number,))
    _, second = raise_one(conn, world)
    assert second.id == "A-0002"


def test_parse_id_accepts_only_a_ids():
    assert approvals.parse_id("A-0412") == 412
    assert approvals.parse_id("a-0412") == 412
    for text in ("P-0042", "publish_item:42", "42", "A-", "A-12x", "", "A-٤١٢"):
        assert approvals.parse_id(text) is None


@pytest.mark.parametrize("build", [
    lambda: Origin("terminal"),  # Terminal decisions are off (ADR 0004)
    lambda: Origin("terminal", reason="typed in Terminal"),
    lambda: Origin("ssh", reason="anything"),
    lambda: Origin("claude"),
    lambda: Origin("refused"),
])
def test_an_origin_is_valid_however_it_is_built(build):
    """N5 (code review 04): a hand-built Origin can't skip the checks."""
    with pytest.raises(ValueError):
        build()


# --- decide ------------------------------------------------------------------

SSH_REF = "1234567890:dlv-77"


@pytest.fixture
def control_user(monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")


def test_an_ssh_approval_records_actor_origin_growths_time_hash_and_ref(conn, world, control_user):
    """AC-M6.1, through decide() with an injected SSH origin."""
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:111", source_ref=SSH_REF)
    assert answer.answer == "recorded"
    row = aw.record(conn, approval.id)
    assert row["status"] == "approved"
    assert row["decided_by"] == "discord:111"
    assert row["decided_origin"] == "ssh"
    assert row["decided_at"] == "2026-11-10T10:02:15+08:00"
    assert row["decision_ref"] == SSH_REF
    assert row["content_hash"] == approval.content_hash
    [event] = aw.events(conn, "approval.approved")
    assert event["actor"] == "discord:111" and event["origin"] == "ssh" and event["ref"] == SSH_REF
    assert event["at"] == "2026-11-10T10:02:15+08:00" and event["hash"] == approval.content_hash


def test_there_is_no_terminal_origin_and_a_lookalike_decides_nothing(conn, world):
    """MC3 as amended 2026-10-26: Terminal decisions are off (ADR 0004), so
    AC-M6.4's Terminal record can't be made, even by an object that looks
    like the old Terminal origin."""
    assert not hasattr(Origin, "terminal")
    _, approval = raise_one(conn, world)
    lookalike = types.SimpleNamespace(kind="terminal", human=True, user="tingyu", code=approval.content_hash[:6], reason=None)
    for decision in (aw.approve, aw.skip):
        assert decision(conn, approval, origin=lookalike, actor=None).answer == "refused"
    assert aw.get(conn, approval.id).status == "pending"


def test_an_ssh_actor_that_is_not_the_control_user_is_refused_and_logged(conn, world, control_user):
    """AC-M7.6, G12. This is the consistency check behind the origin, which
    is attribution: the SSH key and Dispatch's allowlist are the guard."""
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:999", source_ref=SSH_REF)
    assert answer.answer == "refused"
    assert aw.get(conn, approval.id).status == "pending"
    [event] = aw.events(conn, "approval.refused")
    assert event["actor"] == "discord:999" and event["origin"] == "ssh"
    assert world.ran("on_approve") == []


def test_an_ssh_decision_is_refused_when_no_control_user_is_configured(conn, world, monkeypatch):
    monkeypatch.delenv("CONTROL_DISCORD_USER_ID")
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:111")
    assert answer.answer == "refused" and aw.get(conn, approval.id).status == "pending"


@pytest.mark.parametrize("origin", [Origin.refused("no terminal"), Origin.refused("a claude ancestor")])
def test_a_refused_origin_decides_nothing(conn, world, origin):
    _, approval = raise_one(conn, world)
    for decision in (aw.approve, aw.skip):
        answer = decision(conn, approval, origin=origin)
        assert answer.answer == "refused"
    assert aw.get(conn, approval.id).status == "pending"
    assert world.calls == []
    assert len(aw.events(conn, "approval.refused")) == 2


def test_a_refused_origin_stays_refused_whatever_actor_it_claims(conn, world, control_user):
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, origin=Origin.refused("a claude ancestor"), actor="discord:111")
    assert answer.answer == "refused" and "a claude ancestor" in answer.text
    assert aw.get(conn, approval.id).status == "pending"


def test_an_ssh_decision_without_an_actor_is_refused(conn, world):
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, actor=None)
    assert answer.answer == "refused" and "--actor" in answer.text
    assert aw.get(conn, approval.id).status == "pending"


def test_the_same_ref_twice_records_once_and_returns_the_first_answer(conn, world, control_user):
    """AC-M6.2, G16."""
    _, approval = raise_one(conn, world)
    first = aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:111", source_ref=SSH_REF)
    second = aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:111", source_ref=SSH_REF)
    assert first.answer == second.answer == "recorded" and second.text == first.text
    assert len(aw.events(conn, "approval.approved")) == 1
    assert len(world.ran("on_approve")) == 1
    assert db.scalar(conn, "SELECT COUNT(*) FROM approval_decisions") == 1


def test_the_same_ref_arriving_while_the_first_is_deciding_gets_the_first_answer(conn, world, control_user, monkeypatch):
    """G16 with two connections (code review 04, S1): Dispatch's retry lands
    while the first delivery holds the lock, and must not read as a failure."""
    import threading

    _, approval = raise_one(conn, world)
    inside, release = threading.Event(), threading.Event()
    recorded = world.kind.on_approve

    def slow_on_approve(c, subject, args):
        inside.set()
        release.wait(timeout=30)
        return recorded(c, subject, args)

    monkeypatch.setattr(world.kind, "on_approve", slow_on_approve)
    answers = {}

    def deliver(name):
        own = db.connect(migrate_now=False)
        try:
            answers[name] = aw.approve(own, approval, origin=Origin.ssh(), actor="discord:111", source_ref=SSH_REF)
        finally:
            own.close()

    first = threading.Thread(target=deliver, args=("first",))
    first.start()
    assert inside.wait(timeout=30)
    second = threading.Thread(target=deliver, args=("second",))
    second.start()
    time.sleep(0.5)  # the second has read no ref yet and waits on BEGIN IMMEDIATE
    release.set()
    first.join(timeout=60)
    second.join(timeout=60)
    assert answers["first"].answer == answers["second"].answer == "recorded"
    assert answers["second"].text == answers["first"].text
    assert len(world.ran("on_approve")) == 1


def test_a_claim_refused_inside_on_approve_answers_refused_and_records_nothing(conn, world, monkeypatch):
    """G37 (code review 04, S2): app-build's on_approve claims through use(),
    which refuses while app-factory is paused. decide() still answers."""

    def claiming_on_approve(c, subject, args):
        raise approvals.NotApproved("paused", "fake-agent is paused (by hand)")

    monkeypatch.setattr(world.kind, "on_approve", claiming_on_approve)
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, source_ref="m:d")
    assert answer.answer == "refused" and "fake-agent is paused" in answer.text
    assert aw.get(conn, approval.id).status == "pending"
    assert aw.events(conn, "approval.approved") == [] and aw.mirrored("approval.approved") == []
    assert db.scalar(conn, "SELECT COUNT(*) FROM approval_decisions") == 0
    [refused] = aw.events(conn, "approval.refused")
    assert refused["approval"] == approval.id


def test_another_exception_from_on_approve_is_a_programming_error_and_rolls_back(conn, world, monkeypatch):
    def broken(c, subject, args):
        raise KeyError("bug")

    monkeypatch.setattr(world.kind, "on_approve", broken)
    _, approval = raise_one(conn, world)
    with pytest.raises(KeyError):
        aw.approve(conn, approval)
    assert aw.get(conn, approval.id).status == "pending" and aw.mirrored("approval.approved") == []


def test_a_revoke_keeps_answering_its_own_ref(conn, world, control_user):
    """Approve under one ref, skip under another: a late repeat of the first
    delivery still gets its own first answer, not already-decided."""
    _, approval = raise_one(conn, world)
    aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:111", source_ref="m1:d1")
    assert aw.skip(conn, approval, origin=Origin.ssh(), actor="discord:111", source_ref="m2:d2").answer == "recorded"
    assert aw.approve(conn, approval, origin=Origin.ssh(), actor="discord:111", source_ref="m1:d1").answer == "recorded"
    assert aw.get(conn, approval.id).status == "skipped"


def test_a_second_decision_answers_already_decided_and_changes_nothing(conn, world):
    """G15."""
    _, approval = raise_one(conn, world)
    aw.approve(conn, approval)
    assert aw.approve(conn, approval).answer == "already-decided"
    _, other = raise_one(conn, world, "other")
    aw.skip(conn, other)
    assert aw.approve(conn, other).answer == "already-decided"
    assert aw.skip(conn, other).answer == "already-decided"
    assert len(world.ran("on_approve")) == 1 and len(world.ran("on_skip")) == 1


def test_a_skip_on_a_pending_request_runs_on_skip_once(conn, world):
    subject, approval = raise_one(conn, world)
    answer = aw.skip(conn, approval)
    assert answer.answer == "recorded"
    assert aw.get(conn, approval.id).status == "skipped"
    assert world.ran("on_skip") == [("on_skip", subject)]
    [event] = aw.events(conn, "approval.skipped")
    assert event["actor"] == aw.CONTROL and event["origin"] == "ssh"


@pytest.mark.parametrize("number", ["A-9999", "P-0042", "publish_item:42", "42"])
def test_an_id_that_names_no_request_answers_unknown_id(conn, world, number):
    answer = approvals.decide(conn, number, "approve", actor=aw.CONTROL, origin=aw.dispatch(), source_ref=None, args={})
    assert answer.answer == "unknown-id"


def test_approve_at_the_decide_by_answers_expired_and_writes_the_transition(conn, world, monkeypatch):
    """G4a and G14: growth's clock decides, never Discord's message time."""
    subject, approval = raise_one(conn, world)
    aw.at(monkeypatch, approval.decide_by)
    answer = aw.approve(conn, approval)
    assert answer.answer == "expired"
    row = aw.record(conn, approval.id)
    assert row["status"] == "expired" and row["close_reason"] == "not approved in time" and row["used_at"] is None
    assert world.ran("on_expire") == [("on_expire", subject)] and world.ran("on_approve") == []


def test_approve_one_second_before_the_decide_by_records(conn, world, monkeypatch):
    _, approval = raise_one(conn, world)
    aw.at(monkeypatch, aw.later(approval.decide_by, seconds=-1))
    assert aw.approve(conn, approval).answer == "recorded"


def test_a_decision_on_changed_content_answers_superseded_and_raises_the_new_request(conn, world):
    """G6 and G9 at decision time: the yes never lands on content it didn't see."""
    subject, approval = raise_one(conn, world, "old text")
    world.items[subject] = "new text"
    answer = aw.approve(conn, approval)
    assert answer.answer == "superseded" and "A-0002" in answer.text
    assert aw.get(conn, approval.id).status == "superseded"
    assert aw.get(conn, "A-0002").status == "pending"
    assert world.ran("on_approve") == []
    assert aw.approve(conn, approval).answer == "superseded"


def test_approval_sets_the_use_by_from_the_decision_time(conn, world, monkeypatch):
    _, approval = raise_one(conn, world)
    aw.at(monkeypatch, aw.later(aw.NOW, hours=5))
    aw.approve(conn, approval)
    assert aw.get(conn, approval.id).use_by == aw.later(aw.NOW, hours=5, days=3)


# --- on_approve and decision arguments (G37, ticket review T2) ----------------


def test_on_approve_runs_once_inside_the_decision_after_approved_is_written(conn, world):
    subject, approval = raise_one(conn, world)
    aw.approve(conn, approval, args={"promo_days": "sat,sun", "post_days": "any"})
    assert world.ran("on_approve") == [("on_approve", subject, {"promo_days": "sat,sun", "post_days": "any"}, "approved", True)]


def test_a_string_on_approve_returns_is_appended_to_the_answer(conn, world):
    world.approve_says = "Build it: open Claude Code in jurasolutions/"
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval)
    assert answer.answer == "recorded" and answer.text.endswith("Build it: open Claude Code in jurasolutions/")


def test_bad_args_from_on_approve_refuses_with_its_text_and_records_nothing(conn, world):
    world.approve_raises = "say the days: promo_days=… post_days=…"
    _, approval = raise_one(conn, world)
    before = db.scalar(conn, "SELECT COUNT(*) FROM events")
    answer = aw.approve(conn, approval, source_ref="m:d")
    assert answer.answer == "refused" and answer.text == "say the days: promo_days=… post_days=…"
    assert aw.get(conn, approval.id).status == "pending"
    assert db.scalar(conn, "SELECT COUNT(*) FROM events") == before
    assert db.scalar(conn, "SELECT COUNT(*) FROM approval_decisions") == 0
    world.approve_raises = None
    assert aw.approve(conn, approval, source_ref="m:d").answer == "recorded"


@pytest.mark.parametrize("args", [{}, {"promo_days": "sat"}, {"promo_days": "sat", "post_days": ""}])
def test_a_missing_decision_arg_refuses_before_on_approve(conn, world, args):
    _, approval = raise_one(conn, world)
    before = db.scalar(conn, "SELECT COUNT(*) FROM events")
    answer = aw.approve(conn, approval, args=args)
    assert answer.answer == "refused" and "post_days=" in answer.text
    assert world.ran("on_approve") == [] and aw.get(conn, approval.id).status == "pending"
    assert db.scalar(conn, "SELECT COUNT(*) FROM events") == before


def test_an_argument_the_kind_does_not_take_is_refused(conn, world):
    _, approval = raise_one(conn, world)
    answer = aw.approve(conn, approval, args={"promo_days": "sat", "post_days": "any", "send_now": "yes"})
    assert answer.answer == "refused" and "send_now" in answer.text
    _, other = raise_one(conn, world, "other")
    assert approvals.decide(conn, other.id, "skip", actor=aw.CONTROL, origin=aw.dispatch(), source_ref=None, args={"x": "1"}).answer == "refused"


# --- use: the claim -----------------------------------------------------------


def approved_one(conn, world, text="Hello"):
    subject, approval = raise_one(conn, world, text)
    aw.approve(conn, approval)
    return subject, aw.get(conn, approval.id)


def test_use_outside_a_transaction_is_a_programming_error(conn, world):
    subject, _ = approved_one(conn, world)
    with pytest.raises(RuntimeError, match="inside"):
        approvals.use(conn, aw.KIND, subject, run_id=None)
    assert aw.events(conn, "approval.used") == []


@pytest.mark.parametrize("state", ["missing", "pending", "skipped", "used"])
def test_use_refuses_with_its_reason_and_claims_nothing(conn, world, state):
    """AC-M4.1: each refusal names its reason; expired and superseded are in
    the gate matrix (G4a, G4b, G5, G6)."""
    subject = world.item()
    if state != "missing":
        approval = aw.request(conn, aw.KIND, subject)
        if state == "skipped":
            aw.skip(conn, approval)
        if state == "used":
            aw.approve(conn, approval)
            world.act(conn, subject)
    with db.transaction(conn):
        with pytest.raises(approvals.NotApproved) as refused:
            approvals.use(conn, aw.KIND, subject, run_id=None)
    assert refused.value.reason == state
    assert len(aw.events(conn, "approval.used")) == (1 if state == "used" else 0)


def test_not_approved_takes_only_the_reasons_its_docstring_lists():
    """Final code review St6: the reasons are constants, and the docstring names each one."""
    N = approvals.NotApproved
    assert N.REASONS == (
        N.MISSING, N.PENDING, N.SKIPPED, N.EXPIRED, N.SUPERSEDED, N.USED, N.UNKNOWN_KIND, N.PAUSED,
        N.SWITCHED_OFF, N.NOT_SSH, N.GONE, N.CHANGED, N.MISMATCH, N.UNWRITTEN,
    )
    assert N.UNKNOWN_KIND == "unknown-kind" and N.SWITCHED_OFF == "switched-off"
    for reason in N.REASONS:
        assert f"`{reason}`" in N.__doc__, reason
    with pytest.raises(ValueError):
        N("not-a-reason", "text")


def test_every_not_approved_in_the_engine_names_its_reason_by_constant():
    import re
    from pathlib import Path

    import jura_growth

    root = Path(jura_growth.__file__).parent
    literal = re.compile(r"NotApproved\(\s*[\"']")
    found = [f"{path.relative_to(root)}" for path in root.rglob("*.py") if literal.search(path.read_text(encoding="utf-8"))]
    assert found == []


def test_a_claim_sets_used_at_and_used_by_run_and_logs_one_used_event(conn, world):
    subject, approval = approved_one(conn, world)
    run_id = aw.run(conn)
    assert world.act(conn, subject, run_id=run_id) is None
    row = aw.record(conn, approval.id)
    assert row["used_at"] == aw.NOW and row["used_by_run"] == run_id and row["status"] == "approved"
    [event] = aw.events(conn, "approval.used")
    assert event["approval"] == approval.id and event["actor"] == f"run:{run_id}" and event["hash"] == approval.content_hash
    assert world.sent == [{"subject": subject, "used_at": aw.NOW, "used_by_run": run_id}]


def test_use_inside_a_raw_begin_is_refused_and_claims_nothing(conn, world):
    """R2-S2 (code review 04): only db.transaction() holds mirror lines
    until the commit, so a raw BEGIN would bring the B1 leak back."""
    subject, approval = approved_one(conn, world)
    conn.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RuntimeError, match="db.transaction"):
            approvals.use(conn, aw.KIND, subject, run_id=None)
    finally:
        conn.execute("ROLLBACK")
    assert aw.get(conn, approval.id).used_at is None and aw.claims(conn) == 0


def test_a_refusal_the_caller_lets_escape_leaves_nothing_in_either_store(conn, world):
    """B1 (code review 04): when the caller's transaction rolls back, the
    supersede and the new request use() wrote go from the mirror too."""
    subject, approval = approved_one(conn, world, "H1")
    world.items[subject] = "H2"
    with pytest.raises(approvals.NotApproved):
        with db.transaction(conn):
            approvals.use(conn, aw.KIND, subject, run_id=None)
    assert aw.get(conn, approval.id).status == "approved"
    assert aw.mirrored("approval.superseded") == [] and len(aw.mirrored("approval.requested")) == 1
    assert aw.events(conn, "approval.superseded") == []


def test_ac_m4_2_a_changed_draft_supersedes_a_0412_and_raises_a_0413(conn, world):
    conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('approvals', 411)")
    subject, approval = approved_one(conn, world, "H1 body")
    assert approval.id == "A-0412"
    world.items[subject] = "H2 body"
    refusal = world.act(conn, subject, run_id=None)
    assert refusal.reason == "superseded" and world.sent == []
    assert aw.get(conn, "A-0412").status == "superseded"
    fresh = aw.get(conn, "A-0413")
    assert fresh.status == "pending" and fresh.content_hash == approvals.content_hash(world.kind.content(conn, subject))


def test_ac_m4_4_two_connections_claiming_at_once_give_exactly_one_claim(conn, world):
    """G8: both wait at a barrier, then claim under BEGIN IMMEDIATE."""
    import threading

    subject, approval = approved_one(conn, world)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def claim():
        own = db.connect(migrate_now=False)
        try:
            barrier.wait()
            with db.transaction(own):
                try:
                    approvals.use(own, aw.KIND, subject, run_id=None)
                    results.append("claimed")
                except approvals.NotApproved as refusal:
                    results.append(refusal.reason)
        finally:
            own.close()

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(results) == ["claimed", "used"]
    assert len(aw.events(conn, "approval.used")) == 1


def test_g11_the_right_subject_under_the_wrong_kind_refuses(conn, monkeypatch, world):
    other = aw.World()
    other.kind.name = "fake-release"
    other.plugin.NAME = "fake-release-agent"
    other.plugin.approval_kinds = lambda: {"fake-release": other.kind}
    aw.install(monkeypatch, other)
    subject, _ = approved_one(conn, world)
    other.items[subject] = world.items[subject]
    with db.transaction(conn):
        with pytest.raises(approvals.NotApproved) as refused:
            approvals.use(conn, "fake-release", subject, run_id=None)
    assert refused.value.reason == "missing"


def test_a_kind_two_plugins_declare_fails_closed(conn, monkeypatch, world):
    subject, _ = approved_one(conn, world)
    twin = aw.World()
    aw.install(monkeypatch, twin)
    assert aw.KIND not in approvals.kinds()
    with db.transaction(conn):
        with pytest.raises(approvals.NotApproved) as refused:
            approvals.use(conn, aw.KIND, subject, run_id=None)
    assert refused.value.reason == "unknown-kind"


def test_ac_m4_7_a_kind_whose_plugin_failed_to_import_is_refused_and_left_alone(conn, monkeypatch, tmp_path, world):
    """G27, A15: use() refuses; expire_due() and decide() leave the record alone."""
    from jura_growth import agents

    pending_subject, waiting = raise_one(conn, world, "waiting")
    subject, approved = approved_one(conn, world)
    package = tmp_path / "plugins" / "zz_broken_fake"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('broken on import')\n", encoding="utf-8")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(agents, "__path__", [*agents.__path__, str(package.parent)])
            patch.setattr(agents, "plugins", aw.REAL_PLUGINS)
            aw.REAL_PLUGINS.cache_clear()
            aw.REAL_PLUGINS()
            assert "zz_broken_fake" in agents.BROKEN
            aw.at(monkeypatch, aw.later(aw.NOW, days=30))
            with db.transaction(conn):
                with pytest.raises(approvals.NotApproved) as refused:
                    approvals.use(conn, aw.KIND, subject, run_id=None)
            assert refused.value.reason == "unknown-kind"
            assert approvals.expire_due(conn, aw.timeutil.now_sgt()) == []
            assert aw.skip(conn, waiting).answer == "refused"
    finally:
        aw.REAL_PLUGINS.cache_clear()
        agents.BROKEN.pop("zz_broken_fake", None)
    assert aw.get(conn, waiting.id).status == "pending"
    assert aw.get(conn, approved.id).status == "approved" and aw.get(conn, approved.id).used_at is None
    assert world.calls == [("on_approve", subject, {"promo_days": "sat,sun", "post_days": "any"}, "approved", True)]


# --- expire_due ---------------------------------------------------------------


def test_expire_due_supersedes_changed_and_gone_items_without_raising_new_requests(conn, world):
    changed, a = raise_one(conn, world, "one")
    gone, b = approved_one(conn, world, "two")
    kept, c = raise_one(conn, world, "three")
    world.items[changed] = "one, changed"
    del world.items[gone]
    result = approvals.expire_due(conn, aw.timeutil.now_sgt())
    assert sorted(x.id for x in result) == [a.id, b.id]
    assert aw.get(conn, a.id).close_reason == "the content changed"
    assert aw.get(conn, b.id).close_reason == "the item is gone"
    assert aw.get(conn, c.id).status == "pending"
    assert [x.id for x in approvals.pending(conn)] == [c.id]


def test_expire_due_logs_a_failing_hook_and_carries_on(conn, world, monkeypatch):
    first, a = raise_one(conn, world, "one")
    second, b = raise_one(conn, world, "two")

    def on_expire(conn, subject):
        if subject == first:
            raise RuntimeError("cancel failed")
        world.calls.append(("on_expire", subject))

    monkeypatch.setattr(world.kind, "on_expire", on_expire)
    result = approvals.expire_due(conn, aw.timeutil.parse(aw.later(aw.NOW, days=5)))
    assert [x.id for x in result] == [b.id]
    assert aw.get(conn, a.id).status == "pending"
    assert aw.events(conn, "approval.hook_error")[0]["approval"] == a.id


def test_expire_due_inside_a_callers_transaction_uses_a_savepoint(conn, world):
    _, a = raise_one(conn, world)
    with db.transaction(conn):
        changed = approvals.expire_due(conn, aw.timeutil.parse(aw.later(aw.NOW, days=5)))
    assert [x.id for x in changed] == [a.id] and aw.get(conn, a.id).status == "expired"


# --- G36: each writer writes a due transition once ---------------------------


def expired_events(conn, approval) -> int:
    in_db = [e for e in aw.events(conn, "approval.expired") if e["approval"] == approval.id]
    assert len([e for e in aw.mirrored("approval.expired") if e["approval"] == approval.id]) == len(in_db)
    return len(in_db)


def refused_reason(conn, subject) -> str:
    with db.transaction(conn):
        try:
            approvals.use(conn, aw.KIND, subject, run_id=None)
        except approvals.NotApproved as refusal:
            return refusal.reason
    return "claimed"


def test_g36_decide_writes_a_due_expiry_once_and_the_others_find_it_written(conn, world, monkeypatch):
    subject, approval = raise_one(conn, world)
    now = aw.at(monkeypatch, approval.decide_by)
    assert aw.approve(conn, approval).answer == "expired"
    assert refused_reason(conn, subject) == "expired"
    assert approvals.expire_due(conn, now) == []
    assert aw.skip(conn, approval).answer == "expired"
    assert expired_events(conn, approval) == 1 and len(world.ran("on_expire", subject)) == 1


def test_g36_use_writes_a_due_lapse_once_in_the_callers_transaction(conn, world, monkeypatch):
    subject, approval = approved_one(conn, world)
    now = aw.at(monkeypatch, approval.use_by)
    refusal = world.act(conn, subject)
    assert refusal.reason == "expired" and world.sent == []
    lapsed = aw.get(conn, approval.id)
    assert lapsed.status == "expired" and lapsed.close_reason == "approved but not used in time" and lapsed.used_at is None
    assert refused_reason(conn, subject) == "expired"
    assert approvals.expire_due(conn, now) == []
    assert aw.skip(conn, approval).answer == "expired"
    assert expired_events(conn, approval) == 1 and len(world.ran("on_lapse", subject)) == 1


def test_g36_expire_due_writes_a_due_expiry_once_and_the_others_find_it_written(conn, world, monkeypatch):
    subject, approval = raise_one(conn, world)
    now = aw.at(monkeypatch, approval.decide_by)
    assert [a.id for a in approvals.expire_due(conn, now)] == [approval.id]
    assert approvals.expire_due(conn, now) == []
    assert aw.approve(conn, approval).answer == "expired"
    assert refused_reason(conn, subject) == "expired"
    assert expired_events(conn, approval) == 1 and len(world.ran("on_expire", subject)) == 1


def test_no_deadline_runs_past_the_hard_ceiling(conn, world, monkeypatch):
    """X3, the core half: whatever a kind asks for, caps.py has the last word."""
    from jura_growth import caps

    world.decide_in = world.use_in = __import__("datetime").timedelta(days=90)
    _, approval = approved_one(conn, world)
    ceiling = aw.later(aw.NOW, days=caps.APPROVAL_DEADLINE_MAX_DAYS)
    assert approval.decide_by == ceiling and approval.use_by == ceiling


def test_a_configured_deadline_can_shorten_but_never_lengthen():
    """X3: the §5.7 maxima go through caps.effective like every other limit."""
    from jura_growth import caps

    assert caps.effective(caps.APP_BUILD_DECIDE_BY_DAYS, 3) == 3
    assert caps.effective(caps.APP_BUILD_DECIDE_BY_DAYS, 30) == caps.APP_BUILD_DECIDE_BY_DAYS
    assert caps.effective(caps.GROUP_RULES_DECIDE_BY_DAYS, None) == 14
    assert max(caps.APP_BUILD_DECIDE_BY_DAYS, caps.APP_RELEASE_USE_BY_DAYS, caps.GROUP_RULES_DECIDE_BY_DAYS) <= caps.APPROVAL_DEADLINE_MAX_DAYS


# --- the trigger (A7, AC-M6.3, G32) ---------------------------------------------


def states(conn, world) -> dict[str, approvals.Approval]:
    """One record in each state, through the interface."""
    _, pending = raise_one(conn, world, "pending")
    _, approved = approved_one(conn, world, "approved")
    used_subject, used = approved_one(conn, world, "used")
    world.act(conn, used_subject)
    _, skipped = raise_one(conn, world, "skipped")
    aw.skip(conn, skipped)
    gone, superseded = raise_one(conn, world, "superseded")
    del world.items[gone]
    approvals.expire_due(conn, aw.timeutil.now_sgt())
    _, expired = raise_one(conn, world, "expired")
    conn.execute("UPDATE approvals SET status = 'expired', closed_at = ?, close_reason = 'test' WHERE id = ?", (aw.NOW, expired.number))
    return {name: aw.get(conn, a.id) for name, a in {
        "pending": pending, "approved": approved, "used": used, "skipped": skipped, "superseded": superseded, "expired": expired,
    }.items()}


DECIDED = "decided_at = '2026-11-10T10:02:15+08:00', decided_by = 'discord:111', decided_origin = 'ssh'"
CLOSED = "closed_at = '2026-11-10T10:02:15+08:00', close_reason = 'test'"

ALLOWED = [
    ("pending", f"status = 'approved', {DECIDED}"),
    ("pending", f"status = 'skipped', {DECIDED}"),
    ("pending", f"status = 'expired', {CLOSED}"),
    ("pending", f"status = 'superseded', {CLOSED}"),
    ("pending", "posted_at = '2026-11-10T10:03:00+08:00', message_id = '991'"),
    ("approved", f"status = 'skipped', {DECIDED}"),
    ("approved", f"status = 'expired', {CLOSED}"),
    ("approved", f"status = 'superseded', {CLOSED}"),
    ("approved", "used_at = '2026-11-10T10:05:00+08:00'"),
    ("approved", "used_at = '2026-11-10T10:05:00+08:00', used_by_run = NULL"),
    # S3 (code review 04): a card can be marked posted once on any record
    # that isn't used, so 04b's sweep can post a card decided before it ran.
    ("approved", "posted_at = '2026-11-10T10:03:00+08:00', message_id = '991'"),
    ("skipped", "posted_at = '2026-11-10T10:03:00+08:00', message_id = '991'"),
    ("expired", "posted_at = '2026-11-10T10:03:00+08:00', message_id = '991'"),
    ("superseded", "posted_at = '2026-11-10T10:03:00+08:00'"),
]

REFUSED = [
    ("approved", "status = 'pending', decided_at = NULL, decided_by = NULL, decided_origin = NULL"),
    ("skipped", "status = 'pending', decided_at = NULL, decided_by = NULL, decided_origin = NULL"),
    ("expired", "status = 'pending', closed_at = NULL, close_reason = NULL"),
    ("skipped", f"status = 'approved', {DECIDED}"),
    ("expired", f"status = 'approved', {DECIDED}"),
    ("superseded", f"status = 'approved', {DECIDED}"),
    ("pending", "kind = 'other-kind'"),
    ("pending", "subject = 'fake_item:999'"),
    ("pending", "content_hash = 'abc'"),
    ("approved", "content_hash = 'abc'"),
    ("approved", "decided_by = 'discord:999'"),
    ("approved", "use_by = '2027-01-01T00:00:00+08:00'"),
    ("pending", "used_at = '2026-11-10T10:05:00+08:00'"),
    ("used", "used_at = NULL"),
    ("used", "used_by_run = NULL"),
    ("used", "posted_at = '2026-11-10T10:03:00+08:00'"),
    ("used", f"status = 'skipped', {DECIDED}"),
    ("used", f"status = 'expired', {CLOSED}"),
    ("used", f"status = 'superseded', {CLOSED}"),
    ("used", "message_id = '991'"),
    # closed to closed
    ("skipped", f"status = 'expired', {CLOSED}"),
    ("skipped", f"status = 'superseded', {CLOSED}"),
    ("expired", f"status = 'superseded', close_reason = 'other'"),
    ("expired", f"status = 'skipped', {DECIDED}"),
    ("superseded", f"status = 'skipped', {DECIDED}"),
    ("superseded", "status = 'expired'"),
    ("skipped", "decided_by = 'discord:999'"),
    ("expired", "close_reason = 'rewritten'"),
    # N1 (code review 04): fields a transition doesn't own
    ("approved", "used_by_run = 1"),
    ("approved", f"{CLOSED}"),
    ("pending", "use_by = '2026-11-11T10:00:00+08:00'"),
    ("pending", "decided_by = 'discord:111'"),
    ("pending", f"status = 'expired', {CLOSED}, decided_by = 'discord:111'"),
    ("pending", f"status = 'superseded', {CLOSED}, use_by = '2026-11-11T10:00:00+08:00'"),
    ("pending", "closed_at = '2026-11-10T10:03:00+08:00'"),
    ("approved", f"status = 'expired', {CLOSED}, decided_by = 'discord:999'"),
    ("approved", f"status = 'superseded', {CLOSED}, use_by = NULL"),
    ("approved", f"status = 'skipped', {DECIDED}, {CLOSED}"),
]


@pytest.mark.parametrize("state, change", ALLOWED)
def test_the_trigger_allows_each_a7_transition(conn, world, state, change):
    record = states(conn, world)[state]
    conn.execute(f"UPDATE approvals SET {change} WHERE id = ?", (record.number,))


@pytest.mark.parametrize("state, change", REFUSED)
def test_the_trigger_aborts_every_other_change(conn, world, state, change):
    record = states(conn, world)[state]
    with pytest.raises(Exception, match="approv"):
        conn.execute(f"UPDATE approvals SET {change} WHERE id = ?", (record.number,))
    assert aw.get(conn, record.id) == record


@pytest.mark.parametrize("state", ["pending", "approved", "skipped", "expired", "superseded"])
def test_a_card_is_marked_posted_once(conn, world, state):
    record = states(conn, world)[state]
    conn.execute("UPDATE approvals SET posted_at = ?, message_id = '991' WHERE id = ?", (aw.NOW, record.number))
    for change in ("posted_at = '2026-11-10T11:00:00+08:00'", "message_id = '992'", "posted_at = NULL"):
        with pytest.raises(Exception, match="posted"):
            conn.execute(f"UPDATE approvals SET {change} WHERE id = ?", (record.number,))


@pytest.mark.parametrize("state", ["approved", "used", "skipped", "expired", "superseded"])
def test_a_decided_or_closed_record_is_never_deleted(conn, world, state):
    record = states(conn, world)[state]
    with pytest.raises(Exception, match="never deleted"):
        conn.execute("DELETE FROM approvals WHERE id = ?", (record.number,))


def test_recorded_decisions_are_append_only(conn, world):
    approved_one(conn, world)
    with pytest.raises(Exception, match="append-only"):
        conn.execute("UPDATE approval_decisions SET answer = 'refused'")
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM approval_decisions")


# --- the migration (X7) -----------------------------------------------------------


def test_a_database_at_mains_schema_migrates_through_0003_with_no_row_changed(tmp_path, monkeypatch):
    import shutil

    from jura_growth import log

    old = tmp_path / "core-at-main"
    old.mkdir()
    for name in ("0001_core.sql", "0002_sync_cursors.sql"):
        shutil.copy(db.CORE_MIGRATIONS / name, old / name)
    with monkeypatch.context() as patch:
        patch.setattr(db, "CORE_MIGRATIONS", old)
        conn = db.connect(tmp_path / "old.db")
    run_id = log.start_run(conn, "outreach", "scout-send")
    log.finish_run(conn, run_id, "ok", summary="sent 1")
    conn.execute("INSERT INTO pause_flags (agent, paused, reason, set_at) VALUES ('social', 1, 'by hand', ?)", (aw.NOW,))
    tables = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    before = {t: db.rows(conn, f"SELECT * FROM {t}") for t in tables}
    # 0004 (ticket 04b) adds the approval_cards table and changes no row either, nor 0005's triggers.
    assert db.migrate(conn) == ["core/0003_approvals.sql", "core/0004_approval_cards.sql", "core/0005_ssh_decisions_only.sql"]
    assert {t: db.rows(conn, f"SELECT * FROM {t} WHERE rowid IN (SELECT rowid FROM {t})") for t in tables if t != "schema_migrations"} == {
        t: rows for t, rows in before.items() if t != "schema_migrations"
    }
    assert db.scalar(conn, "SELECT COUNT(*) FROM approvals") == 0
    conn.close()



# --- Sp4: only an SSH decision counts, in use() and in the schema ---------------------

SSH_ONLY = "only an SSH decision"


def at_0004(tmp_path, monkeypatch):
    return aw.connect_before_0005(tmp_path / "old.db", monkeypatch)


def plant_terminal_approval(conn, world, text="Hello") -> tuple[str, int]:
    """An approved, unclaimed record decided in Terminal, written before 0005 (the database is
    still at 0004), with its decision row. Its content still matches."""
    assert db.scalar(conn, "SELECT count(*) FROM schema_migrations WHERE id = 'core/0005_ssh_decisions_only.sql'") == 0
    subject = world.item(text)
    digest = approvals.content_hash(world.kind.content(conn, subject))
    cursor = conn.execute(
        "INSERT INTO approvals (kind, subject, content_hash, status, reason, requested_at, decide_by, use_by, decided_at,"
        " decided_by, decided_origin) VALUES (?, ?, ?, 'approved', 'a test asked', ?, ?, ?, ?, 'terminal:tingyu', 'terminal')",
        (aw.KIND, subject, digest, aw.NOW, aw.later(aw.NOW, days=1), aw.later(aw.NOW, days=2), aw.NOW),
    )
    number = int(cursor.lastrowid or 0)
    conn.execute(
        "INSERT INTO approval_decisions (approval_id, decision, actor, origin, decided_at, content_hash, answer, text)"
        " VALUES (?, 'approve', 'terminal:tingyu', 'terminal', ?, ?, 'recorded', 'kept')",
        (number, aw.NOW, digest),
    )
    conn.commit()
    return subject, number


def test_use_refuses_a_record_decided_with_any_origin_but_ssh(tmp_path, monkeypatch, world):
    conn = at_0004(tmp_path, monkeypatch)
    subject, number = plant_terminal_approval(conn, world)
    assert db.migrate(conn) == ["core/0005_ssh_decisions_only.sql"]
    refusal = world.act(conn, subject)
    assert refusal is not None and refusal.reason == approvals.NotApproved.NOT_SSH
    assert "SSH" in refusal.text and approvals.format_id(number) in refusal.text
    assert aw.record(conn, approvals.format_id(number))["used_at"] is None
    assert world.sent == [] and aw.events(conn, "approval.used") == []
    conn.close()


REFUSED_WRITES = {
    "a decision moving to approved with a terminal origin": (
        "UPDATE approvals SET status = 'approved', decided_at = :now, decided_by = 'discord:111', "
        "decided_origin = 'terminal' WHERE id = :id"),
    "a decision moving to approved with a terminal: actor": (
        "UPDATE approvals SET status = 'approved', decided_at = :now, decided_by = 'terminal:tingyu', "
        "decided_origin = 'ssh' WHERE id = :id"),
    "a skip with a terminal: actor": (
        "UPDATE approvals SET status = 'skipped', decided_at = :now, decided_by = 'terminal:tingyu', "
        "decided_origin = 'ssh' WHERE id = :id"),
    "a record inserted already approved with a terminal origin": (
        "INSERT INTO approvals (kind, subject, content_hash, status, reason, requested_at, decide_by, decided_at, "
        "decided_by, decided_origin) VALUES ('fake', 'fake_item:forged', :hash, 'approved', 'forged', :now, :now, :now, "
        "'discord:111', 'terminal')"),
    "a record inserted already approved with a terminal: actor": (
        "INSERT INTO approvals (kind, subject, content_hash, status, reason, requested_at, decide_by, decided_at, "
        "decided_by, decided_origin) VALUES ('fake', 'fake_item:forged', :hash, 'approved', 'forged', :now, :now, :now, "
        "'terminal:tingyu', 'ssh')"),
    "a decision row with a terminal origin": (
        "INSERT INTO approval_decisions (approval_id, decision, actor, origin, decided_at, content_hash, answer, text)"
        " VALUES (:id, 'approve', 'discord:111', 'terminal', :now, :hash, 'recorded', 'x')"),
    "a decision row with a terminal: actor": (
        "INSERT INTO approval_decisions (approval_id, decision, actor, origin, decided_at, content_hash, answer, text)"
        " VALUES (:id, 'approve', 'terminal:tingyu', 'ssh', :now, :hash, 'recorded', 'x')"),
}


@pytest.mark.parametrize("write", REFUSED_WRITES, ids=list(REFUSED_WRITES))
def test_the_schema_refuses_every_new_terminal_decision(conn, world, write):
    """Sp-S1 (follow-ups review): AC-M6.4, a terminal origin or a terminal: actor in no new row."""
    _, pending = raise_one(conn, world)
    with pytest.raises(Exception, match=SSH_ONLY):
        conn.execute(REFUSED_WRITES[write], {"now": aw.NOW, "id": pending.number, "hash": pending.content_hash})
    conn.rollback()
    assert aw.record(conn, pending.id)["status"] == "pending"


def test_an_ssh_decision_is_still_recorded_past_the_triggers(conn, world):
    _, pending = raise_one(conn, world)
    assert aw.approve(conn, pending).answer == "recorded"
    record = aw.record(conn, pending.id)
    assert record["decided_origin"] == "ssh" and record["decided_by"] == aw.CONTROL
    _, other = raise_one(conn, world, "other")
    assert aw.skip(conn, other).answer == "recorded"


def test_terminal_decisions_already_on_record_survive_the_migration_and_can_still_lapse_or_be_superseded(
        tmp_path, monkeypatch, world):
    """0005 is forward-only: a database at 0004 keeps its Terminal decisions as they were. An
    approved one never claimed still lapses at its use-by, and one whose item changed is superseded."""
    conn = at_0004(tmp_path, monkeypatch)
    _, lapsing = plant_terminal_approval(conn, world)
    changing, superseded = plant_terminal_approval(conn, world, "Changes later")
    before = (db.rows(conn, "SELECT * FROM approvals"), db.rows(conn, "SELECT * FROM approval_decisions"))
    assert db.migrate(conn) == ["core/0005_ssh_decisions_only.sql"]
    assert (db.rows(conn, "SELECT * FROM approvals"), db.rows(conn, "SELECT * FROM approval_decisions")) == before

    world.items[changing] = "Changed after the decision"
    refusal = world.act(conn, changing)
    assert refusal is not None and refusal.reason == approvals.NotApproved.SUPERSEDED
    gone = aw.record(conn, approvals.format_id(superseded))
    assert gone["status"] == "superseded" and gone["decided_by"] == "terminal:tingyu"

    aw.at(monkeypatch, aw.later(aw.NOW, days=3))
    lapsed = [a for a in approvals.expire_due(conn) if a.number == lapsing]
    assert [(a.status, a.decided_origin) for a in lapsed] == [("expired", "terminal")]
    conn.close()
