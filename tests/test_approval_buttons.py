"""Approve and Skip buttons on approval cards (X11; MC §4.8 D5; ticket review T10, technical-v2 N6).

`components` is sent only when `approvals.post_buttons` is true, and never on a card whose
approve needs typed `key=value` arguments: `group-rules` needs its days, so its card has no
button. Each button's `custom_id` is what Dispatch turns into `approve A-nnnn` or
`skip A-nnnn` (`docs/dispatch-contract.md`). A card that is no longer pending loses its buttons
when its first line is edited.
"""

from __future__ import annotations

import types

import pytest

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import agents, cards, config


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def buttons(monkeypatch, on: bool) -> None:
    patched = dict(config.settings())
    patched["approvals"] = {**(patched.get("approvals") or {}), "post_buttons": on}
    monkeypatch.setattr(config, "settings", lambda: patched)


def plain(world) -> None:
    """The fake kind, without typed arguments: an approve needs nothing but the tap."""
    world.kind.decision_args = ()


def raised(conn, world, text="Quotes that write themselves", kind=aw.KIND):
    return aw.request(conn, kind, world.item(text))


def expected(approval_id: str) -> list[dict]:
    return [{"type": 1, "components": [
        {"type": 2, "style": 3, "label": "Approve", "custom_id": f"growth:approve:{approval_id}"},
        {"type": 2, "style": 4, "label": "Skip", "custom_id": f"growth:skip:{approval_id}"},
    ]}]


def test_no_buttons_while_post_buttons_is_off(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, False)
    plain(world)
    raised(conn, world)
    cards.sweep(conn)
    (card,) = discord_double.posts("approvals")
    assert card.components is None and "with_components" not in card.url


def test_with_post_buttons_on_a_card_carries_approve_and_skip(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, True)
    plain(world)
    approval = raised(conn, world)
    cards.sweep(conn)
    (card,) = discord_double.posts("approvals")
    assert card.components == expected(approval.id)
    assert "with_components=true" in card.url and "wait=true" in card.url


def test_a_card_that_needs_typed_arguments_gets_no_buttons(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, True)  # the fake kind keeps decision_args = (promo_days, post_days)
    raised(conn, world)
    cards.sweep(conn)
    (card,) = discord_double.posts("approvals")
    assert card.components is None


def test_a_group_rules_card_never_gets_buttons(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, True)
    kind = aw.FakeKind(world)
    kind.name = "group-rules"
    plugin = types.SimpleNamespace(NAME="community-double", approval_kinds=lambda: {"group-rules": kind}, __name__="group_rules_double")
    real = agents.plugins
    monkeypatch.setattr(agents, "plugins", lambda: (*real(), plugin))
    raised(conn, world, kind="group-rules")
    cards.sweep(conn)
    (card,) = discord_double.posts("approvals")
    assert card.components is None
    assert "/growth approve A-0001 promo_days=… post_days=…" in card.content


def test_a_long_card_carries_its_buttons_on_the_first_piece_the_one_that_is_edited(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, True)
    plain(world)
    approval = raised(conn, world, "\n".join(f"line {n} " + "x" * 90 for n in range(40)))
    cards.sweep(conn)
    first, *rest = discord_double.posts("approvals")
    assert rest and first.components == expected(approval.id)
    assert all(piece.components is None for piece in rest)


def test_a_decided_card_loses_its_buttons_when_it_is_edited(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, True)
    plain(world)
    approval = raised(conn, world)
    cards.sweep(conn)
    aw.approve(conn, approval, args={})
    cards.sweep(conn)
    (edit,) = [r for r in discord_double.requests if r.method == "PATCH"]
    assert edit.components == [] and "Approved by Ting Yu" in edit.content


def test_with_buttons_off_an_edit_leaves_components_alone(conn, world, discord_double, monkeypatch):
    buttons(monkeypatch, False)
    plain(world)
    approval = raised(conn, world)
    cards.sweep(conn)
    aw.approve(conn, approval, args={})
    cards.sweep(conn)
    (edit,) = [r for r in discord_double.requests if r.method == "PATCH"]
    assert edit.components is None
