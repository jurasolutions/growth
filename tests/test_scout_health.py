"""A missing ICP is on Fix on any day, through scout's `health()` hook (morning brief SC6, N6)."""

from __future__ import annotations

import re

import pytest

import mission_world as world
from jura_growth import agents, health, mission, paths

ACTION = "inputs/icp.md"
SATURDAY, BUSINESS_DAY = "2026-11-07T09:00:00+08:00", "2026-11-10T09:00:00+08:00"
EITHER_DAY = pytest.mark.parametrize("moment", [SATURDAY, BUSINESS_DAY], ids=["Saturday", "business day"])


@pytest.fixture
def snapshot_at(conn, monkeypatch):
    """The read model at a moment, with growth.db in place and the inputs folder as the test left it."""

    def read(moment: str) -> mission.Snapshot:
        monkeypatch.setenv("JURA_GROWTH_NOW", moment)
        return mission.read(world.source(moment))

    return read


def icp_lines(snapshot: mission.Snapshot) -> list[str]:
    return [line for line in health.strip(snapshot) if "icp" in line.lower()]


@EITHER_DAY
def test_a_missing_icp_says_what_to_do_with_the_action_first(snapshot_at, moment):
    [line] = icp_lines(snapshot_at(moment))
    assert line.startswith(f"Put the ICP in {ACTION}")


def test_the_line_holds_no_absolute_path(snapshot_at):
    [line] = icp_lines(snapshot_at(BUSINESS_DAY))
    assert str(paths.inputs_dir()) not in line and str(paths.outputs_dir()) not in line
    assert not re.search(r"(^|\s)/", line)


def test_the_line_fits_the_pictures_clamp_and_its_first_sentence_stands_alone(snapshot_at):
    """Fix holds about 114 characters in three rows, and the picture keeps an item's first sentence."""
    [line] = icp_lines(snapshot_at(BUSINESS_DAY))
    assert len(line) <= 114, len(line)
    assert ACTION in line.split(". ")[0]


@EITHER_DAY
def test_with_the_icp_in_place_the_line_is_gone(snapshot_at, moment):
    paths.inputs_dir().mkdir(parents=True, exist_ok=True)
    (paths.inputs_dir() / "icp.md").write_text("# ICP\n")
    assert icp_lines(snapshot_at(moment)) == []


def test_the_line_comes_from_scouts_own_hook(conn):
    [line] = agents.by_name("scout").health(conn)
    assert ACTION in line
