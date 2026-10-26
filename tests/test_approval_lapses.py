"""Who writes lapses and posts cards on a schedule (MC §4.6 A12, A17; X12, gate case G36; ticket 04b).

The noon heartbeat and the 23:30 backup each call `expire_due()` and edit the cards that changed;
only the heartbeat posts unposted cards, so nothing new notifies at 23:30. (The 08:00 `one-pager`
job joins them in ticket 09.)
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, runner
from jura_growth.cli import cli


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def due(conn, world, monkeypatch):
    """A pending request whose decide-by has just passed, its card posted."""
    approval = aw.request(conn, aw.KIND, world.item())
    cards.sweep(conn)
    aw.at(monkeypatch, approval.decide_by)
    return approval


@pytest.mark.parametrize("command", ["heartbeat", "backup"])
def test_the_scheduled_writer_expires_a_lapsed_request_once(conn, world, monkeypatch, command):
    approval = due(conn, world, monkeypatch)
    result = CliRunner().invoke(cli, [command])
    assert result.exit_code == 0, result.output
    assert aw.record(conn, approval.id)["status"] == "expired"
    assert len(world.ran("on_expire", approval.subject)) == 1
    CliRunner().invoke(cli, [command])
    assert len(world.ran("on_expire", approval.subject)) == 1


@pytest.mark.parametrize("command", ["heartbeat", "backup"])
def test_the_scheduled_writer_edits_the_lapsed_card(conn, world, monkeypatch, discord_double, command):
    approval = due(conn, world, monkeypatch)
    discord_double.requests.clear()
    CliRunner().invoke(cli, [command])
    (patch,) = [r for r in discord_double.requests if r.method == "PATCH"]
    assert patch.content.splitlines()[0] == f"**{approval.id} · fake** · Expired: not approved in time"


def test_the_heartbeat_posts_a_card_a_crash_left_unposted(conn, world, discord_double):
    approval = aw.request(conn, aw.KIND, world.item())  # committed; the raising command died before posting
    CliRunner().invoke(cli, ["heartbeat"])
    posted = discord_double.posts("approvals")
    assert len(posted) == 1 and posted[0].content.startswith(f"**{approval.id} · fake**")
    assert aw.record(conn, approval.id)["posted_at"] is not None


def test_the_backup_posts_no_new_card_at_23_30(conn, world, discord_double):
    """Code review 04b, Sp3: a new card would notify Ting Yu at night; the heartbeat posts it."""
    approval = aw.request(conn, aw.KIND, world.item())
    CliRunner().invoke(cli, ["backup"])
    assert discord_double.posts("approvals") == []
    assert aw.record(conn, approval.id)["posted_at"] is None


def test_the_scheduled_heartbeat_job_does_the_same(conn, world, monkeypatch, discord_double):
    approval = due(conn, world, monkeypatch)
    outcome = runner.run("heartbeat", ignore_schedule=True)
    assert outcome.status == "ok", outcome
    assert aw.record(conn, approval.id)["status"] == "expired"


def test_a_failing_sweep_never_stops_the_heartbeat(conn, world, monkeypatch, discord_double):
    monkeypatch.setattr(cards, "sweep", lambda conn, post=True: (_ for _ in ()).throw(RuntimeError("sweep broke")))
    result = CliRunner().invoke(cli, ["heartbeat"])
    assert result.exit_code == 0, result.output
    assert any("Heartbeat" in (p.content or "") for p in discord_double.posts("daily-digest"))
    assert "sweep broke" in aw.events(conn, "approval.cards_error")[0]["error"]


def test_a_failing_expiry_never_stops_the_backup(conn, world, monkeypatch, tmp_path):
    monkeypatch.setattr(approvals, "expire_due", lambda conn, now=None: (_ for _ in ()).throw(RuntimeError("expiry broke")))
    result = CliRunner().invoke(cli, ["backup"])
    assert result.exit_code == 0, result.output
    assert list((tmp_path / "data" / "backups").glob("growth-*.db"))
