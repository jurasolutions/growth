"""Reviewer's reproduction harness. Copies the repo's isolation fixture so every
test runs against a temporary data folder, no Discord, no secrets, no network."""

import sys
from pathlib import Path

import pytest

REPO = Path("/Users/tingy/OneDrive/Desktop/projects/jurasolutions/repos/growth")
sys.path.insert(0, str(REPO / "tests"))

from jura_growth import config  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JURA_GROWTH_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JURA_GROWTH_PAUSE_FILE", str(tmp_path / "PAUSE"))
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("JURA_GROWTH_LAUNCH_AGENTS", str(tmp_path / "LaunchAgents"))
    monkeypatch.setenv("JURA_GROWTH_DISCORD", "off")
    monkeypatch.setenv("JURA_INPUTS_DIR", str(tmp_path / "inputs"))
    monkeypatch.setenv("JURA_PRD_DIR", str(tmp_path / "prd"))
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "site"))
    for name in ("JURA_GROWTH_RUN_ID", "JURA_GROWTH_AGENT", "JURA_GROWTH_JOB", "JURA_GROWTH_NOW"):
        monkeypatch.delenv(name, raising=False)
    config.reset_caches()
    yield tmp_path
    config.reset_caches()


@pytest.fixture
def conn():
    from jura_growth import db

    connection = db.connect()
    yield connection
    connection.close()
