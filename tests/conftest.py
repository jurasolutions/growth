import pytest

from jura_growth import config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own data, outputs and launchd folders, no Discord
    and no secrets, so nothing touches jurasolutions/data or the live server."""
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JURA_GROWTH_OUTPUTS_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("JURA_GROWTH_PAUSE_FILE", str(tmp_path / "PAUSE"))
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("JURA_GROWTH_LAUNCH_AGENTS", str(tmp_path / "LaunchAgents"))
    monkeypatch.setenv("JURA_GROWTH_DISCORD", "off")
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
