"""Shortlist research with job boards (scout PRD §5.2a, amended 2026-10-31).

About 20 candidates a day, scored with the §5.2a weights, ranked in code; every
one at or above the threshold is kept, best first, up to `research.shortlist`
(default 10). The rest are remembered in `scout_rejections` with their score.
"""

import json

from click.testing import CliRunner

from jura_growth import caps
from jura_growth.agents import scout
from jura_growth.agents.scout import settings
from jura_growth.cli import cli

from test_scout_support import at, configure, scout_env, seed  # noqa: F401


# --- §5.2a points 1 and 4: the two settings ---------------------------------


def test_candidates_and_shortlist_default_to_twenty_and_ten():
    assert settings.candidates() == 20
    assert settings.shortlist() == 10


def test_config_may_lower_the_shortlist_and_candidates_but_never_raise_them(monkeypatch):
    configure(monkeypatch, research={"candidates": 12, "shortlist": 3})
    assert settings.candidates() == 12 and settings.shortlist() == 3
    configure(monkeypatch, research={"candidates": 500, "shortlist": 500})
    assert settings.candidates() == caps.SCOUT_CANDIDATES_PER_RUN == 40
    assert settings.shortlist() == caps.SCOUT_SHORTLIST_PER_DAY == 10
    configure(monkeypatch, research={"candidates": -1, "shortlist": -1})
    assert settings.candidates() == 1 and settings.shortlist() == 0


def test_daily_target_is_retired():
    assert "daily_target" not in settings.DEFAULTS["research"]
    assert not hasattr(settings, "daily_target")


def test_today_reports_candidates_shortlist_and_room(isolated, monkeypatch, conn):
    at(monkeypatch, "2026-10-26T09:00:00+08:00")
    seed(conn, 1, queue=False)
    conn.commit()
    info = json.loads(CliRunner().invoke(cli, ["scout", "today", "--json"]).output)
    assert info["candidates"] == 20 and info["shortlist"] == 10
    assert info["kept_today"] == 1 and info["remaining"] == 9
    assert "daily_target" not in info and "added_today" not in info


def test_precheck_skips_once_the_shortlist_is_kept(conn, monkeypatch):
    configure(monkeypatch, research={"shortlist": 1})
    assert scout.precheck("scout-research", conn) is None
    seed(conn, 1, queue=False)
    assert "shortlist of 1" in scout.precheck("scout-research", conn)
