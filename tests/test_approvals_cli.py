"""`jura-growth approvals`, `approve` and `skip` (MC §4.6 A8 to A10 as amended 2026-10-26; ADR 0004).

Terminal decisions are off: typed in Terminal, `approve` and `skip` refuse, point to #approvals and
record nothing. They decide only through the in-process seam ticket 11's `remote` sets: an SSH
origin and the Discord actor in the click context. Covers AC-M5.4 (the listing), AC-M7.1 (the
code-level refusal under `JURA_GROWTH_JOB`), G30 (only A-ids) and G33 (closed answers).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from click.testing import CliRunner

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, approvals_cli, cards, config, headless, origin
from jura_growth.cli import cli
from jura_growth.origin import Origin

ARGS = ["promo_days=sat,sun", "post_days=any"]
REFUSAL = f"refused: {origin.TERMINAL_OFF}."


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def terminal(words):
    """Typed in Terminal: no origin in the click context."""
    return CliRunner().invoke(cli, words)


def remote(words, *, origin_=None, actor=aw.CONTROL):
    """As ticket 11's `remote` will call it, after `origin.detect_ssh()`."""
    return CliRunner().invoke(cli, words, obj={"origin": origin_ or aw.dispatch(), "actor": actor})


def raised(conn, world, text="Quotes that write themselves"):
    return aw.request(conn, aw.KIND, world.item(text))


def nothing_recorded(conn, approval) -> None:
    assert aw.record(conn, approval.id)["status"] == "pending"
    for kind in ("approval.approved", "approval.skipped", "approval.refused", "approval.note"):
        assert aw.events(conn, kind) == [], kind


# --- Terminal decisions are off -------------------------------------------------------------


@pytest.mark.parametrize("words", [["approve", "{id}", *ARGS], ["skip", "{id}", "wrong", "one"], ["approve", "{id}", "--ref", "m:d"]])
def test_a_decision_typed_in_terminal_is_refused_and_points_to_approvals(conn, world, words):
    approval = raised(conn, world)
    result = terminal([w.format(id=approval.id) for w in words])
    assert result.exit_code == approvals_cli.EXIT_CODES["refused"]
    assert result.output.strip() == REFUSAL
    assert "#approvals" in result.output
    nothing_recorded(conn, approval)
    assert world.calls == []


def test_a_terminal_refusal_asks_for_nothing_and_opens_no_database(tmp_path):
    result = CliRunner().invoke(cli, ["approve", "A-0001"], input="c6c430\n")
    assert result.output.strip() == REFUSAL
    assert not (tmp_path / "data" / "growth.db").exists()


# --- through remote's seam: the SSH origin ---------------------------------------------------


def test_an_ssh_approval_records_the_dispatch_decision(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *ARGS, "--ref", "1234567890:dlv-77"])
    assert result.exit_code == 0, result.output
    assert f"{approval.id} approved." in result.output
    record = aw.record(conn, approval.id)
    assert record["status"] == "approved" and record["decided_origin"] == "ssh"
    assert record["decided_by"] == aw.CONTROL and record["decision_ref"] == "1234567890:dlv-77"
    assert world.ran("on_approve")[0][2] == {"promo_days": "sat,sun", "post_days": "any"}


def test_words_after_the_arguments_are_a_note_on_the_decision(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *ARGS, "looks", "good"])
    assert result.exit_code == 0, result.output
    (note,) = aw.events(conn, "approval.note")
    assert note == {"approval": approval.id, "decision": "approve", "note": "looks good", "actor": aw.CONTROL}


def test_skip_records_the_skip_and_its_note(conn, world):
    approval = raised(conn, world)
    result = remote(["skip", approval.id, "wrong", "one"])
    assert result.exit_code == 0, result.output
    assert aw.record(conn, approval.id)["status"] == "skipped"
    assert aw.events(conn, "approval.note")[0]["note"] == "wrong one"


def test_a_stranger_through_ssh_is_refused(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *ARGS], actor="discord:999")
    assert result.exit_code == 2 and result.output.startswith("refused:")
    assert aw.record(conn, approval.id)["status"] == "pending"


def test_a_refused_origin_in_the_context_is_refused(conn, world):
    approval = raised(conn, world)
    result = remote(["approve", approval.id, *ARGS], origin_=Origin.refused(origin.IN_CLAUDE))
    assert result.exit_code == 2 and origin.IN_CLAUDE in result.output
    assert aw.record(conn, approval.id)["status"] == "pending"


def test_the_same_ref_twice_is_recorded_once_and_answers_the_same(conn, world):
    approval = raised(conn, world)
    first = remote(["approve", approval.id, *ARGS, "--ref", "m1:d1"])
    second = remote(["approve", approval.id, *ARGS, "--ref", "m1:d1"])
    assert first.exit_code == second.exit_code == 0
    assert first.output == second.output
    assert len(aw.events(conn, "approval.approved")) == 1


def test_a_decision_edits_the_card_straight_away(conn, world, discord_double):
    approval = raised(conn, world)
    cards.sweep(conn)
    remote(["approve", approval.id, *ARGS])
    (patch,) = [r for r in discord_double.requests if r.method == "PATCH"]
    assert "Approved by Ting Yu" in patch.content


# --- G33: every answer has its exit code ---------------------------------------------------


def _states(conn, world):
    made = {"recorded": raised(conn, world), "expired": raised(conn, world, "expires")}
    superseded = raised(conn, world, "changes")
    world.items[superseded.subject] += " (changed)"
    made["superseded"] = superseded
    decided = raised(conn, world, "decided")
    aw.skip(conn, decided)
    made["already-decided"] = decided
    used = raised(conn, world, "used")
    aw.approve(conn, used)
    assert world.act(conn, used.subject, run_id=aw.run(conn)) is None
    made["already-used"] = used
    return made


@pytest.mark.parametrize("answer", ["recorded", "expired", "superseded", "already-decided", "already-used", "unknown-id", "refused"])
def test_every_answer_has_one_exit_code(conn, world, monkeypatch, answer):
    made = _states(conn, world)
    if answer == "expired":
        aw.at(monkeypatch, made["expired"].decide_by)
    if answer == "unknown-id":
        result = remote(["approve", "A-9999", *ARGS])
    elif answer == "refused":
        result = remote(["approve", made["recorded"].id, *ARGS], origin_=Origin.refused("not a human origin"))
    else:
        result = remote(["approve", made[answer].id, *ARGS])
    assert result.exit_code == approvals_cli.EXIT_CODES[answer], result.output
    assert set(approvals_cli.EXIT_CODES) == set(approvals.ANSWERS)
    assert len(set(approvals_cli.EXIT_CODES.values())) == len(approvals.ANSWERS)


# --- G30: only A-ids are typed ---------------------------------------------------------------


@pytest.mark.parametrize("typed", ["P-0042", "publish_item:42", "42", "fake_item:1"])
def test_only_an_a_id_names_a_request(conn, world, typed):
    approval = raised(conn, world)
    result = remote(["approve", typed, *ARGS])
    assert result.exit_code == approvals_cli.EXIT_CODES["unknown-id"]
    assert aw.record(conn, approval.id)["status"] == "pending"
    assert aw.events(conn, "approval.approved") == []


# --- the listing (AC-M5.4) --------------------------------------------------------------------


def test_thirty_pending_lists_the_fifteen_soonest_to_lapse_then_the_rest_by_kind(conn, world):
    made = []
    for n in range(30):
        world.decide_in = timedelta(hours=60 - n)  # the later raised, the sooner it lapses
        made.append(raised(conn, world, f"item {n}"))
    result = terminal(["approvals"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    soonest = list(reversed(made))[:15]
    assert [line.split(" · ")[0] for line in lines[:15]] == [a.id for a in soonest]
    first = soonest[0]
    assert lines[0] == f"{first.id} · fake · decide by Wed 11 Nov, 17:02 SGT · fake item {first.subject}"
    assert lines[15] == "and 15 more: /growth approvals fake"
    assert len(lines) == 16


def test_the_listing_shows_no_code(conn, world):
    approval = raised(conn, world)
    assert approval.content_hash[:6] not in terminal(["approvals"]).output


def test_the_listing_filters_by_kind(conn, world):
    raised(conn, world)
    assert terminal(["approvals", "outreach-email"]).output.strip() == "No outreach email requests are waiting."
    assert terminal(["approvals", aw.KIND]).output.startswith("A-0001 · fake")


def test_an_empty_listing_says_so(conn, world):
    assert terminal(["approvals"]).output.strip() == "No requests are waiting."


def test_a_request_past_its_decide_by_is_not_offered_and_the_listing_still_ends_with_the_rest(conn, world, monkeypatch):
    early = raised(conn, world)
    world.decide_in = timedelta(days=5)
    for n in range(16):
        raised(conn, world, f"later {n}")
    aw.at(monkeypatch, early.decide_by)
    lines = terminal(["approvals"]).output.strip().splitlines()
    assert early.id not in " ".join(lines[:15])
    assert lines[15] == "1 more passed its decide-by and expires unanswered."
    assert lines[-1] == "and 1 more: /growth approvals fake"


def test_the_listing_writes_nothing(conn, world, monkeypatch):
    early = raised(conn, world)
    aw.at(monkeypatch, early.decide_by)
    terminal(["approvals"])
    assert aw.record(conn, early.id)["status"] == "pending"


# --- AC-M7.1: refused in any scheduled run ----------------------------------------------------


@pytest.mark.parametrize("job", sorted(config.settings()["jobs"]))
@pytest.mark.parametrize("command", ["approve", "skip", "approvals"])
def test_every_configured_job_is_refused(conn, world, monkeypatch, job, command):
    approval = raised(conn, world)
    monkeypatch.setenv("JURA_GROWTH_JOB", job)
    words = {"approve": ["approve", approval.id, *ARGS], "skip": ["skip", approval.id], "approvals": ["approvals"]}[command]
    result = remote(words)
    assert result.exit_code == 2
    assert "refused:" in result.output
    assert aw.record(conn, approval.id)["status"] == "pending"


@pytest.mark.parametrize("command", ["approve", "skip", "approvals"])
def test_the_commands_refuse_a_run_on_their_own_without_never(conn, world, monkeypatch, command):
    """Each layer alone (test strategy v3 §5.3): with `NEVER` emptied, the command still
    refuses, even carrying the SSH origin `remote` would set."""
    approval = raised(conn, world)
    monkeypatch.setattr(headless, "NEVER", ())
    monkeypatch.setattr(headless, "may_use", lambda job, name: True)
    monkeypatch.setenv("JURA_GROWTH_JOB", "social")
    words = {"approve": ["approve", approval.id, *ARGS], "skip": ["skip", approval.id], "approvals": ["approvals"]}[command]
    result = remote(words)
    assert result.exit_code == 2 and "refused:" in result.output
    assert aw.record(conn, approval.id)["status"] == "pending"
