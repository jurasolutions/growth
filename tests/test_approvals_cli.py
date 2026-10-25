"""`jura-growth approvals`, `approve` and `skip` from Terminal (MC §4.6 A8 to A10; ticket 04b).

AC-M5.4 (the listing), AC-M7.1 (the code-level refusal under `JURA_GROWTH_JOB`), gate cases G30
(only A-ids are typed) and G33 (closed answers, from Terminal), through click's `CliRunner`. The
origin rides in the click context, the in-process seam only `remote` sets for real; the real
detection is in `test_origin.py` and `test_origin_processes.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from click.testing import CliRunner

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, approvals_cli, config, headless, origin
from jura_growth.cli import cli
from jura_growth.origin import Origin

ARGS = ["promo_days=sat,sun", "post_days=any"]


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def invoke(words, *, origin_=None, actor=None):
    obj = None if origin_ is None else {"origin": origin_, **({"actor": actor} if actor else {})}
    return CliRunner().invoke(cli, words, obj=obj)


def raised(conn, world, text="Quotes that write themselves"):
    return aw.request(conn, aw.KIND, world.item(text))


# --- approve and skip ---------------------------------------------------------------------


def test_approve_with_the_right_code_records_the_terminal_decision(conn, world):
    approval = raised(conn, world)
    result = invoke(["approve", approval.id, *ARGS], origin_=aw.terminal(approval))
    assert result.exit_code == 0, result.output
    assert f"{approval.id} approved." in result.output
    record = aw.record(conn, approval.id)
    assert record["status"] == "approved"
    assert record["decided_by"] == f"terminal:{aw.TERMINAL_USER}" and record["decided_origin"] == "terminal"
    assert world.ran("on_approve")[0][2] == {"promo_days": "sat,sun", "post_days": "any"}


def test_words_after_the_arguments_are_a_note_on_the_decision(conn, world):
    approval = raised(conn, world)
    result = invoke(["approve", approval.id, *ARGS, "looks", "good"], origin_=aw.terminal(approval))
    assert result.exit_code == 0, result.output
    (note,) = aw.events(conn, "approval.note")
    assert note == {"approval": approval.id, "decision": "approve", "note": "looks good", "actor": f"terminal:{aw.TERMINAL_USER}"}


def test_skip_records_the_skip_and_its_note(conn, world):
    approval = raised(conn, world)
    result = invoke(["skip", approval.id, "wrong", "one"], origin_=aw.terminal(approval))
    assert result.exit_code == 0, result.output
    assert aw.record(conn, approval.id)["status"] == "skipped"
    assert aw.events(conn, "approval.note")[0]["note"] == "wrong one"


def test_a_wrong_code_is_refused_and_the_request_stays_pending(conn, world):
    approval = raised(conn, world)
    result = invoke(["approve", approval.id, *ARGS], origin_=aw.terminal(approval, "000000"))
    assert result.exit_code == 2
    assert result.output.startswith("refused:")
    assert aw.record(conn, approval.id)["status"] == "pending"


def test_without_an_origin_in_the_context_the_real_check_runs(conn, world, monkeypatch):
    approval = raised(conn, world)
    asked = []

    def detect(prompt):
        asked.append(prompt)
        return Origin.refused(origin.NO_TERMINAL)

    monkeypatch.setattr(origin, "detect", detect)
    result = invoke(["approve", approval.id, *ARGS])
    assert result.exit_code == 2
    assert "decisions need a terminal or the Dispatch link" in result.output
    assert approval.id in asked[0]
    assert aw.record(conn, approval.id)["status"] == "pending"


def test_an_ssh_origin_in_the_context_carries_its_actor(conn, world, monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", "111")
    config.reset_caches()
    approval = raised(conn, world)
    result = invoke(["approve", approval.id, *ARGS, "--ref", "1234567890:dlv-77"], origin_=Origin.ssh(), actor="discord:111")
    assert result.exit_code == 0, result.output
    record = aw.record(conn, approval.id)
    assert record["decided_by"] == "discord:111" and record["decision_ref"] == "1234567890:dlv-77"


def test_the_same_ref_twice_is_recorded_once_and_answers_the_same(conn, world):
    approval = raised(conn, world)
    first = invoke(["approve", approval.id, *ARGS, "--ref", "m1:d1"], origin_=aw.terminal(approval))
    second = invoke(["approve", approval.id, *ARGS, "--ref", "m1:d1"], origin_=aw.terminal(approval))
    assert first.exit_code == second.exit_code == 0
    assert first.output == second.output
    assert len(aw.events(conn, "approval.approved")) == 1


def test_a_decision_edits_the_card_straight_away(conn, world, discord_double):
    approval = raised(conn, world)
    approvals.post_unposted(conn)
    invoke(["approve", approval.id, *ARGS], origin_=aw.terminal(approval))
    (patch,) = [r for r in discord_double.requests if r.method == "PATCH"]
    assert "Approved by Ting Yu" in patch.content


# --- G33: every answer has its exit code ---------------------------------------------------


def _states(conn, world, monkeypatch):
    made = {}
    made["recorded"] = raised(conn, world)
    expired = raised(conn, world, "expires")
    made["expired"] = expired
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
    made = _states(conn, world, monkeypatch)
    if answer == "expired":
        aw.at(monkeypatch, made["expired"].decide_by)
    if answer == "unknown-id":
        result = invoke(["approve", "A-9999", *ARGS], origin_=Origin.terminal(aw.TERMINAL_USER, "abcdef"))
    elif answer == "refused":
        approval = made["recorded"]
        result = invoke(["approve", approval.id, *ARGS], origin_=Origin.refused("not a human origin"))
    else:
        approval = made[answer]
        result = invoke(["approve", approval.id, *ARGS], origin_=aw.terminal(approval))
    assert result.exit_code == approvals_cli.EXIT_CODES[answer], result.output
    assert set(approvals_cli.EXIT_CODES) == set(approvals.ANSWERS)
    assert len(set(approvals_cli.EXIT_CODES.values())) == len(approvals.ANSWERS)


# --- G30: only A-ids are typed ---------------------------------------------------------------


@pytest.mark.parametrize("typed", ["P-0042", "publish_item:42", "42", "fake_item:1"])
def test_only_an_a_id_names_a_request(conn, world, typed):
    approval = raised(conn, world)
    result = invoke(["approve", typed, *ARGS], origin_=aw.terminal(approval))
    assert result.exit_code == approvals_cli.EXIT_CODES["unknown-id"]
    assert aw.record(conn, approval.id)["status"] == "pending"
    assert aw.events(conn, "approval.approved") == []


# --- the listing (AC-M5.4) --------------------------------------------------------------------


def test_thirty_pending_lists_the_fifteen_soonest_to_lapse_then_the_rest_by_kind(conn, world):
    made = []
    for n in range(30):
        world.decide_in = timedelta(hours=60 - n)  # the later raised, the sooner it lapses
        made.append(raised(conn, world, f"item {n}"))
    result = invoke(["approvals"])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    soonest = list(reversed(made))[:15]
    assert [line.split(" · ")[0] for line in lines[:15]] == [a.id for a in soonest]
    first = soonest[0]
    assert lines[0] == f"{first.id} · fake · decide by Wed 11 Nov, 17:02 SGT · code {first.code} · fake item {first.subject}"
    assert lines[15] == "and 15 more: /growth approvals fake"
    assert len(lines) == 16


def test_the_listing_filters_by_kind(conn, world):
    raised(conn, world)
    assert invoke(["approvals", "outreach-email"]).output.strip() == "No outreach email requests are waiting."
    assert invoke(["approvals", aw.KIND]).output.startswith("A-0001 · fake")


def test_an_empty_listing_says_so(conn, world):
    assert invoke(["approvals"]).output.strip() == "No requests are waiting."


def test_a_request_past_its_decide_by_is_not_offered_as_waiting(conn, world, monkeypatch):
    early = raised(conn, world)
    world.decide_in = timedelta(days=5)
    later = raised(conn, world, "later")
    aw.at(monkeypatch, early.decide_by)
    lines = invoke(["approvals"]).output.strip().splitlines()
    assert lines[0].startswith(later.id)
    assert lines[-1] == "1 more passed its decide-by and expires unanswered."


def test_the_listing_writes_nothing(conn, world, monkeypatch):
    early = raised(conn, world)
    aw.at(monkeypatch, early.decide_by)
    invoke(["approvals"])
    assert aw.record(conn, early.id)["status"] == "pending"


# --- AC-M7.1: refused in any scheduled run ----------------------------------------------------


@pytest.mark.parametrize("job", sorted(config.settings()["jobs"]))
@pytest.mark.parametrize("command", ["approve", "skip", "approvals"])
def test_every_configured_job_is_refused(conn, world, monkeypatch, job, command):
    approval = raised(conn, world)
    monkeypatch.setenv("JURA_GROWTH_JOB", job)
    words = {"approve": ["approve", approval.id, *ARGS], "skip": ["skip", approval.id], "approvals": ["approvals"]}[command]
    result = invoke(words, origin_=aw.terminal(approval))
    assert result.exit_code == 2
    assert "refused:" in result.output
    assert aw.record(conn, approval.id)["status"] == "pending"


@pytest.mark.parametrize("command", ["approve", "skip", "approvals"])
def test_the_commands_refuse_a_run_on_their_own_without_never(conn, world, monkeypatch, command):
    """Each layer alone (test strategy v3 §5.3): with `NEVER` emptied, the command still refuses."""
    approval = raised(conn, world)
    monkeypatch.setattr(headless, "NEVER", ())
    monkeypatch.setattr(headless, "may_use", lambda job, name: True)
    monkeypatch.setenv("JURA_GROWTH_JOB", "social")
    words = {"approve": ["approve", approval.id, *ARGS], "skip": ["skip", approval.id], "approvals": ["approvals"]}[command]
    result = invoke(words, origin_=aw.terminal(approval))
    assert result.exit_code == 2 and "refused:" in result.output
    assert aw.record(conn, approval.id)["status"] == "pending"
