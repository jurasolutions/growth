"""The publish job's precheck and its setup gap (AC-P8.2, AC-P9.5; seams S9 and S3).

Through `runner.run("publish")` in process, with a fake `claude` binary that must never start
when nothing can be claimed or an auth variable is set.
"""

from __future__ import annotations

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import agents, approvals, db, health, runner
from jura_growth.agents import publish
from runner_support import fake_claude, mirrored, settings_with

AUTH = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


@pytest.fixture
def world(monkeypatch, tmp_path):
    pw.social_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    for name in AUTH:
        monkeypatch.delenv(name, raising=False)
    pw.at(monkeypatch, pw.TEN)
    settings_with(monkeypatch, binary=str(fake_claude(tmp_path, "SKIP: nothing due")))


def started(tmp_path) -> bool:
    return (tmp_path / "stdin.txt").exists()


def runs(conn) -> int:
    return db.scalar(conn, "SELECT count(*) FROM runs WHERE job = 'publish'")


# --- AC-P8.2 nothing claimable: no Claude, a quiet trace ------------------------------------------


@pytest.mark.parametrize("setup", ["nothing", "pending", "skipped"])
def test_nothing_claimable_starts_no_claude_and_leaves_one_quiet_trace(conn, world, monkeypatch, tmp_path, discord_double, setup):
    if setup != "nothing":
        _, request = pw.item(conn)
        if setup == "skipped":
            pw.decide(conn, request, "skip")
    discord_double.requests.clear()

    outcome = runner.run("publish", ignore_schedule=True)

    assert not started(tmp_path), "claude started with nothing to claim"
    assert outcome.status == "ok"
    assert runs(conn) == 0
    quiet = [e for e in mirrored("run.quiet") if e["job"] == "publish"]
    assert len(quiet) == 1 and quiet[0]["reason"] == "nothing due"
    assert [p for p in discord_double.posts() if p.channel != "approvals"] == []


def test_something_claimable_lets_the_run_start(conn, world, monkeypatch, tmp_path):
    pw.at(monkeypatch, pw.MORNING)
    pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    assert publish.precheck("publish", conn) is None
    runner.run("publish", ignore_schedule=True)
    assert started(tmp_path)


def test_the_precheck_syncs_first_so_a_changed_post_gets_its_new_card(conn, world, monkeypatch, discord_double):
    found, request = pw.item(conn)
    conn.execute("UPDATE social_posts SET text = text || ' (changed)' WHERE id = ?", (found.ref_id,))
    discord_double.requests.clear()

    reason = publish.precheck("publish", conn)

    assert isinstance(reason, agents.NothingToDo)
    assert approvals.get(conn, request.id).status == "superseded"
    fresh = [r for r in db.rows(conn, "SELECT * FROM approvals WHERE subject = ? AND status = 'pending'", (found.subject,))]
    assert len(fresh) == 1
    assert fresh[0]["posted_at"], "the fresh card wasn't posted"
    assert discord_double.posts("approvals"), "no card reached #approvals"
    assert not conn.in_transaction  # committed, not left open


# --- AC-P9.5 an auth variable hides the Chrome tools ------------------------------------------------


@pytest.mark.parametrize("name", AUTH)
def test_an_auth_variable_skips_with_its_name_as_a_plain_skip(conn, world, monkeypatch, tmp_path, name):
    pw.at(monkeypatch, pw.MORNING)
    pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    monkeypatch.setenv(name, "sk-ant-secret-value-123")

    outcome = runner.run("publish", ignore_schedule=True)

    assert not started(tmp_path)
    assert outcome.status == "skipped" and not isinstance(outcome.summary, agents.NothingToDo)
    assert name in outcome.summary and "secret-value" not in outcome.summary
    row = db.one(conn, "SELECT status, summary FROM runs WHERE job = 'publish'")
    assert row["status"] == "skipped" and name in row["summary"]
    assert not [e for e in mirrored("run.quiet") if e["job"] == "publish"]


@pytest.mark.parametrize("name", AUTH)
def test_an_auth_variable_is_a_setup_gap_by_name_only(monkeypatch, name):
    for other in AUTH:
        monkeypatch.delenv(other, raising=False)
    assert not [g for g in health.setup_gaps() if g.name in AUTH]
    monkeypatch.setenv(name, "sk-ant-secret-value-123")
    gaps = [g for g in health.setup_gaps() if g.name in AUTH]
    assert [g.name for g in gaps] == [name]
    assert gaps[0].line == f"`{name}`: set, and must not be"
    assert "secret" not in gaps[0].line
