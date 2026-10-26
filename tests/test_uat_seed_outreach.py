"""The UAT seed's outreach scenarios and `--today` (ticket 17; X13; `uat.md` S1, S3, S4, S9, S10).

`uat.md` makes every decision through Dispatch on the real clock, so the seed dates everything from
the day it is run (`--today`), and the outreach steps (A4, B6) get their set-up from the seed:
live mode in the temp config, a hand edit to one queued draft, and a shadow trial to requeue.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
import yaml

from jura_growth import db, paths
from jura_growth.agents.outreach import send
from test_scout_support import CONTROL_ID, REGISTRY, d1_env, fake_d1, fake_resend, outreach_requests
from uat import seed

TUESDAY = date(2026, 11, 17)  # a business day; the business day before it is Mon 16 Nov


@pytest.fixture
def uat(tmp_path, monkeypatch):
    """The `uat.md` window: every folder under one temp folder, the clock at 08:00 on TUESDAY."""
    folder = tmp_path / "uat"
    folder.mkdir()
    for variable, name in (("JURA_GROWTH_DATA_DIR", "data"), ("JURA_GROWTH_OUTPUTS_DIR", "outputs"), ("JURA_PRD_DIR", "prd")):
        monkeypatch.setenv(variable, str(folder / name))
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TUESDAY.isoformat()}T08:00:00+08:00")
    return folder


def rows(sql: str, params=()) -> list[dict]:
    conn = db.connect()
    try:
        return db.rows(conn, sql, params)
    finally:
        conn.close()


# --- --today --------------------------------------------------------------------------------


def test_today_dates_every_base_row_from_that_day(uat):
    seed.seed(uat, today=TUESDAY)
    first = rows("SELECT min(started_at) AS first FROM runs")[0]["first"]
    assert first.startswith("2026-11-09")  # eight days back
    factory = rows("SELECT started_at FROM runs WHERE job = 'app-factory' AND started_at LIKE '2026-11-17%'")
    assert [r["started_at"] for r in factory] == ["2026-11-17T06:31:00+08:00"]
    lead_233 = rows("SELECT queued_at, send_after FROM outreach_messages WHERE lead_id = 233")[0]
    assert lead_233 == {"queued_at": "2026-11-16T09:12:00+08:00", "send_after": "2026-11-16"}
    batch = rows("SELECT DISTINCT send_after FROM outreach_messages WHERE lead_id BETWEEN 240 AND 260")
    assert batch == [{"send_after": "2026-11-17"}]
    quiet = rows("SELECT ts FROM events WHERE kind = 'run.quiet'")
    assert {r["ts"][:10] for r in quiet} == {"2026-11-16"}
    assert any(r["ts"].startswith("2026-11-16T10:26") for r in quiet)
    assert list((uat / "prd" / "pending" / "apps").glob("prd-app-014-*-2026-11-17.md"))
    assert (uat / "data" / "transcripts" / "2026-11-17").is_dir()
    assert rows("SELECT max(started_at) AS last FROM runs")[0]["last"].startswith("2026-11-17")


def test_the_previous_business_day_skips_a_public_holiday(uat):
    seed.seed(uat, today=date(2026, 11, 10))  # Mon 9 Nov is Deepavali (observed)
    lead_233 = rows("SELECT send_after FROM outreach_messages WHERE lead_id = 233")[0]
    assert lead_233["send_after"] == "2026-11-06"


@pytest.mark.parametrize("day, why", [(date(2026, 11, 14), "weekend"), (date(2026, 11, 9), "Deepavali")])
def test_a_day_that_isnt_a_business_day_is_refused_and_seeds_nothing(uat, day, why):
    with pytest.raises(seed.Refused, match=why):
        seed.seed(uat, today=day)
    assert not (uat / "data" / "growth.db").exists()


def test_the_default_day_is_today_in_sgt(uat):
    seed.seed(uat)
    assert rows("SELECT 1 FROM runs WHERE job = 'app-factory' AND started_at = '2026-11-17T06:31:00+08:00'")


def test_the_command_line_takes_today(uat):
    assert seed.main([str(uat), "--today", "2026-11-17"]) == 0
    assert rows("SELECT 1 FROM runs WHERE started_at = '2026-11-17T07:00:00+08:00'")
    assert seed.main([str(uat), "--scenario", "base", "--today", "2026-11-14"]) == 2


# --- outreach-live (S3) ------------------------------------------------------------------------

STUB = "http://127.0.0.1:8025"
BUTTONS = "approval buttons not set up"


@pytest.fixture
def window(uat, tmp_path, monkeypatch):
    """`uat.md`'s window for A4: the config and inputs folders in the UAT folder too, the UAT env
    file's settings, Resend pointed at the stub, and D1 and Resend behind doubles."""
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(uat / "config"))
    monkeypatch.setenv("JURA_INPUTS_DIR", str(uat / "inputs"))
    site = tmp_path / "site" / "src" / "apps"
    site.mkdir(parents=True)
    (site / "registry.json").write_text(json.dumps(REGISTRY))
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "site"))
    monkeypatch.setenv("RESEND_API_KEY_OUTREACH", seed.RESEND_KEY)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "uat-unsubscribe-secret")
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", CONTROL_ID)
    d1_env(monkeypatch)
    monkeypatch.setenv(send.RESEND_BASE_ENV, STUB)
    monkeypatch.setattr(send, "chance", lambda: 0.0)
    return uat


@pytest.fixture
def live(window, monkeypatch):
    """`base` and `outreach-live` seeded; the doubles for D1, Resend and Discord in place."""
    seed.seed(window, today=TUESDAY)
    seed.seed(window, "outreach-live", today=TUESDAY)
    fake_d1(monkeypatch, ())
    return fake_resend(monkeypatch)


def test_outreach_live_writes_live_mode_into_the_uat_config_only(live, window):
    scout = yaml.safe_load((window / "config" / "scout.yaml").read_text())
    assert scout["mode"] == "live" and scout["legal_review_done"] is True and scout["sending_domain"]
    settings = yaml.safe_load((window / "config" / "settings.yaml").read_text())
    assert settings["approvals"]["discord_buttons"] is False
    assert (window / "inputs" / "do-not-contact.csv").exists()
    real = yaml.safe_load((paths.REPO_ROOT / "config" / "scout.yaml").read_text())
    assert real["mode"] == "shadow"


def test_every_live_pre_condition_holds_but_the_buttons(live):
    problems = send.live_problems()
    assert len(problems) == 1 and problems[0].startswith(BUTTONS)


def test_warm_up_day_3_caps_today_at_5(live):
    conn = db.connect()
    try:
        cap, note = send.daily_cap(conn, "live")
    finally:
        conn.close()
    assert cap == 5 and note.startswith("warm-up day 3")


def test_send_due_refuses_until_the_buttons_are_set_up(live, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TUESDAY.isoformat()}T10:00:00+08:00")
    conn = db.connect()
    try:
        result = send.send_due(conn)
        assert result.note.startswith("live sending refused") and BUTTONS in result.note
        assert outreach_requests(conn) == []
    finally:
        conn.close()
    assert live == []


@pytest.mark.parametrize("variable", ["JURA_GROWTH_CONFIG_DIR", send.RESEND_BASE_ENV])
def test_outreach_live_refuses_without_its_folder_or_the_stub(window, monkeypatch, variable):
    monkeypatch.delenv(variable)
    with pytest.raises(seed.Refused, match=variable):
        seed.seed(window, "outreach-live", today=TUESDAY)
    assert not (window / "config" / "scout.yaml").exists() or yaml.safe_load((window / "config" / "scout.yaml").read_text())["mode"] != "live"


def test_outreach_live_refuses_a_config_folder_outside_the_uat_folder(window, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(tmp_path / "elsewhere"))
    with pytest.raises(seed.Refused, match="JURA_GROWTH_CONFIG_DIR"):
        seed.seed(window, "outreach-live", today=TUESDAY)
    assert not (tmp_path / "elsewhere").exists()


def test_outreach_live_refuses_a_stub_that_isnt_on_this_mac(window, monkeypatch):
    monkeypatch.setenv(send.RESEND_BASE_ENV, "https://api.resend.com")
    with pytest.raises(seed.Refused, match="stub"):
        seed.seed(window, "outreach-live", today=TUESDAY)
