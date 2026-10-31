"""One line per change for every real kind (FD1, FD3; test strategy R4), through each kind's own
gate adapter: the kind's raising command, its card and a real decision, then `cards.sweep`.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards
from test_feed import FD1_CHANNELS

ADAPTERS = sorted(Path(__file__).parent.glob("gate_adapter_*.py"))
REAL = [module.ADAPTER for module in (importlib.import_module(path.stem) for path in ADAPTERS) if module.ADAPTER.kind in FD1_CHANNELS]
ON_DECIDE = [adapter for adapter in REAL if adapter.applied_on_decide]


def ids(adapter) -> str:
    return adapter.__module__.removeprefix("gate_adapter_")


@pytest.fixture
def carded(request, conn, monkeypatch, tmp_path, discord_double):
    """A real request of this kind, with its card posted. Returns the adapter, the request and the
    card's title line."""
    gate = request.param(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)
    approval = gate.raise_request(gate.item())
    cards.sweep(conn)
    [card] = [c for c in discord_double.contents("approvals") if c.startswith(f"**{approval.id} ")]
    return gate, approval, card.split("\n")[1]


def lines(double, gate, approval) -> list[str]:
    return [m for m in double.contents(FD1_CHANNELS[gate.kind]) if m.startswith(f"**{approval.id} ")]


def test_the_kinds_covered_are_every_kind_the_table_names():
    assert {adapter.kind for adapter in REAL} == set(FD1_CHANNELS)
    assert {adapter.kind for adapter in ON_DECIDE} == {"app-build", "group-rules"}


@pytest.mark.parametrize("carded", REAL, ids=ids, indirect=True)
def test_an_approval_posts_one_line_named_as_its_card_named_it(conn, carded, discord_double):
    gate, approval, title = carded
    assert gate.approve(approval).answer == "recorded"
    cards.sweep(conn)
    cards.sweep(conn)
    [line] = lines(discord_double, gate, approval)
    assert line.startswith(f"**{approval.id} approved** · {title}")


@pytest.mark.parametrize("carded", REAL, ids=ids, indirect=True)
def test_a_skip_posts_one_line(conn, carded, discord_double):
    gate, approval, title = carded
    assert gate.skip(approval).answer == "recorded"
    cards.sweep(conn)
    cards.sweep(conn)
    assert lines(discord_double, gate, approval) == [f"**{approval.id} skipped** · {title}"]


@pytest.mark.parametrize("carded", REAL, ids=ids, indirect=True)
def test_an_expiry_posts_one_line(conn, carded, discord_double, monkeypatch):
    gate, approval, title = carded
    aw.at(monkeypatch, approval.decide_by)
    approvals.expire_due(conn)
    cards.sweep(conn)
    cards.sweep(conn)
    assert lines(discord_double, gate, approval) == [f"**{approval.id} expired** · {title}\nNot approved in time."]


@pytest.mark.parametrize("carded", ON_DECIDE, ids=ids, indirect=True)
def test_a_kind_applied_on_decide_reports_as_approved_and_never_again(conn, carded, discord_double):
    gate, approval, _ = carded
    assert gate.approve(approval).answer == "recorded"
    cards.sweep(conn)
    assert aw.get(conn, approval.id).used_at
    cards.sweep(conn)
    cards.sweep(conn)
    assert [line.split(" · ")[0] for line in lines(discord_double, gate, approval)] == [f"**{approval.id} approved**"]
