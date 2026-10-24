"""Tests never write into the repo or the live jurasolutions/ folders.

`conftest.py` installs a write guard for the whole session. These tests check
the guard itself. The live-folder probes aim at a folder that doesn't exist, so
even without the guard they can't create anything.
"""

import plistlib
import sqlite3

import pytest

from jura_growth import paths, runner, schedule

MISSING = "no-such-folder-from-a-test"


def test_a_write_into_the_repo_is_refused(write_guard):
    probe = paths.REPO_ROOT / "probe-from-a-test.txt"
    try:
        with pytest.raises(PermissionError):
            probe.write_text("x")
        assert not probe.exists()
    finally:
        if probe.exists():
            probe.unlink()
    assert any("probe-from-a-test.txt" in v for v in write_guard.take())


@pytest.mark.parametrize("folder", ["data", "outputs"])
def test_a_write_into_live_data_or_outputs_is_refused(write_guard, folder):
    target = paths.JURA_ROOT / folder / MISSING / "probe.txt"
    with pytest.raises(PermissionError):
        open(target, "w")
    assert any(MISSING in v for v in write_guard.take())


def test_opening_a_database_in_live_data_is_refused(write_guard):
    target = paths.JURA_ROOT / "data" / MISSING / "growth.db"
    with pytest.raises(PermissionError):
        sqlite3.connect(target)
    assert any(MISSING in v for v in write_guard.take())


def test_writes_into_the_test_folder_are_fine(write_guard, tmp_path):
    (tmp_path / "fine.txt").write_text("x")
    assert write_guard.take() == []


# --- the folders tests point elsewhere --------------------------------------


def test_render_writes_plists_to_the_plist_folder_override(monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_PLIST_DIR", str(tmp_path / "rendered"))
    [written] = schedule.render(["heartbeat"])
    assert written == tmp_path / "rendered" / "sg.jurasolutions.growth.heartbeat.plist"
    assert plistlib.loads(written.read_bytes())["Label"] == "sg.jurasolutions.growth.heartbeat"


def test_claude_jobs_read_prompts_from_the_prompts_folder_override(monkeypatch, tmp_path):
    folder = tmp_path / "my-prompts"
    folder.mkdir()
    (folder / "social.md").write_text("A prompt from the override folder.")
    monkeypatch.setenv("JURA_GROWTH_PROMPTS_DIR", str(folder))
    _, prompt = runner.claude_command("social", runner.job("social"))
    assert prompt == "A prompt from the override folder."


def test_each_test_gets_its_own_copy_of_the_prompts():
    real = paths.REPO_ROOT / "prompts"
    assert paths.prompts_dir() != real
    assert sorted(p.name for p in paths.prompts_dir().iterdir()) == sorted(p.name for p in real.iterdir())
    assert (paths.prompts_dir() / "social.md").read_text() == (real / "social.md").read_text()
