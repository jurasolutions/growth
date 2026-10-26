"""The UAT seed's outreach scenarios and `--today` (ticket 17; X13; `uat.md` S1, S3, S4, S9, S10).

`uat.md` makes every decision through Dispatch on the real clock, so the seed dates everything from
the day it is run (`--today`), and the outreach steps (A4, B6) get their set-up from the seed:
live mode in the temp config, a hand edit to one queued draft, and a shadow trial to requeue.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

import resend_stub
from discord_double import discord_double  # noqa: F401 - a fixture
from mission_world import stat_snapshot
from jura_growth import brand_check, cloudflare, config, db, paths
from jura_growth.agents.outreach import approval, queue, requeue, send
from test_scout_support import CONTROL_ID, REGISTRY, decide, fake_d1, fake_resend, outreach_requests
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
    file's settings with no Cloudflare credentials, Resend and D1 pointed at the stub, and D1 and
    Resend behind doubles."""
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(uat / "config"))
    monkeypatch.setenv("JURA_INPUTS_DIR", str(uat / "inputs"))
    site = tmp_path / "site" / "src" / "apps"
    site.mkdir(parents=True)
    (site / "registry.json").write_text(json.dumps(REGISTRY))
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "site"))
    monkeypatch.setenv("RESEND_API_KEY_OUTREACH", seed.RESEND_KEY)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "uat-unsubscribe-secret")
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", CONTROL_ID)
    monkeypatch.setenv(send.RESEND_BASE_ENV, STUB)
    monkeypatch.setenv(cloudflare.BASE_ENV, STUB)
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


@pytest.mark.parametrize("variable", ["JURA_GROWTH_CONFIG_DIR", send.RESEND_BASE_ENV, cloudflare.BASE_ENV])
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


@pytest.mark.parametrize("variable, url", [
    (send.RESEND_BASE_ENV, "https://api.resend.com"),
    (cloudflare.BASE_ENV, "https://api.cloudflare.com/client/v4"),
])
def test_outreach_live_refuses_a_stub_that_isnt_on_this_mac(window, monkeypatch, variable, url):
    monkeypatch.setenv(variable, url)
    with pytest.raises(seed.Refused, match=f"{variable} must point at the local UAT stub"):
        seed.seed(window, "outreach-live", today=TUESDAY)


# --- S4: the requests come from the outreach commands (A4) ----------------------------------


def buttons_on(window) -> None:
    """A4: Ting Yu sets `approvals.discord_buttons: true` in `$UAT/config/settings.yaml` only."""
    path = window / "config" / "settings.yaml"
    text = path.read_text()
    assert text.count("discord_buttons: false") == 1
    path.write_text(text.replace("discord_buttons: false", "discord_buttons: true"))
    config.reset_caches()


@pytest.fixture
def cards(live, window, monkeypatch, request):
    """Buttons on, the clock at 10:00, Discord behind its double."""
    buttons_on(window)
    monkeypatch.setenv("JURA_GROWTH_NOW", f"{TUESDAY.isoformat()}T10:00:00+08:00")
    return request.getfixturevalue("discord_double")


def message_of(conn, lead_id: int) -> int:
    return db.scalar(conn, "SELECT id FROM outreach_messages WHERE lead_id = ? AND status = 'queued'", (lead_id,))


def request_for(conn, lead_id: int, status: str = "pending"):
    subject = approval.subject_of(message_of(conn, lead_id))
    (found,) = [r for r in outreach_requests(conn, status) if r.subject == subject]
    return found


def test_the_first_send_due_raises_todays_5_requests_and_posts_5_cards(live, cards):
    assert send.live_problems() == []
    conn = db.connect()
    try:
        result = send.send_due(conn)
        assert len(outreach_requests(conn, "pending")) == 5
        assert request_for(conn, 233)  # due since the previous business day
        assert len(approval.without_request(conn)) == 12  # 17 queued, less the 5 asked about
    finally:
        conn.close()
    assert result.note.startswith("nothing approved to send")
    assert len(cards.posts("approvals")) == 5
    assert live == []  # nothing is approved, so nothing reaches the stub
    conn = db.connect()
    try:
        topped_up = send.send_due(conn)  # the next slot: no room, so no new request
    finally:
        conn.close()
    assert topped_up.note.endswith("5 waiting for a decision, 12 waiting for a request slot")
    assert len(cards.posts("approvals")) == 5


def test_an_approved_email_goes_to_the_stub_once(live, cards):
    conn = db.connect()
    try:
        send.send_due(conn)
        assert decide(conn, request_for(conn, 233)).answer == "recorded"
        result = send.send_due(conn)
        again = send.send_due(conn)
    finally:
        conn.close()
    assert result.summary and result.summary.startswith("sent message"), result.note
    assert "sent message" not in (again.summary or "")
    (sent,) = live
    assert str(sent.url) == f"{STUB}/emails"
    assert json.loads(sent.content)["to"] == ["info@example.com.sg"]


def test_every_s4_draft_passes_the_send_time_brand_gate(live):
    """So whichever card A4 approves, the email reaches the stub."""
    conn = db.connect()
    try:
        failing = []
        for message in db.rows(conn, "SELECT * FROM outreach_messages WHERE status = 'queued'"):
            lead, row = queue.recipient(conn, message["lead_id"])
            email = queue.build(conn, lead, row, subject=message["subject"], body=message["draft_body"])
            args = queue.check_args(lead, email, kind="first", tool=message["tool_slug"])
            if not brand_check.check(email.check_text, **args).passed:
                failing.append(message["lead_id"])
    finally:
        conn.close()
    assert failing == []


# --- edit-draft (S9) ------------------------------------------------------------------------


def test_edit_draft_after_approval_supersedes_the_request_and_sends_nothing(live, cards, window):
    conn = db.connect()
    try:
        send.send_due(conn)
        approved = request_for(conn, 240)
        assert decide(conn, approved).answer == "recorded"
        before = db.scalar(conn, "SELECT draft_body FROM outreach_messages WHERE lead_id = 240")
    finally:
        conn.close()

    assert seed.main([str(window), "--scenario", "edit-draft", "--lead", "240", "--today", TUESDAY.isoformat()]) == 0

    conn = db.connect()
    try:
        after = db.scalar(conn, "SELECT draft_body FROM outreach_messages WHERE lead_id = 240")
        assert after != before
        send.send_due(conn)
        assert [r.id for r in outreach_requests(conn, "superseded")] == [approved.id]
        fresh = request_for(conn, 240)
        assert fresh.id != approved.id
    finally:
        conn.close()
    assert live == []  # lead 240 doesn't send, and nothing else was approved


def test_shadow_trial_then_requeue_shadow_asks_only_up_to_todays_quota(live, cards, window):
    """AC-M8.13 at the harness's data (B6)."""
    assert seed.main([str(window), "--scenario", "shadow-trial", "--today", TUESDAY.isoformat()]) == 0
    conn = db.connect()
    try:
        assert len(requeue.candidates(conn)) == 40
        plan = requeue.requeue_shadow(conn)
        assert len(plan.requeued) == 40 and plan.skipped == []
        assert len(plan.requests) == 5  # warm-up day 3, nothing sent or asked about yet today
        assert len(outreach_requests(conn, "pending")) == 5
    finally:
        conn.close()
    assert live == []


def test_requeue_shadow_raises_nothing_once_todays_quota_is_asked_about(live, cards, window):
    conn = db.connect()
    try:
        send.send_due(conn)  # the five base emails due today take the quota
        seed.seed(window, "shadow-trial", today=TUESDAY)
        plan = requeue.requeue_shadow(conn)
        assert len(plan.requeued) == 40 and plan.requests == []
        assert len(outreach_requests(conn, "pending")) == 5
    finally:
        conn.close()


def test_shadow_trial_twice_is_refused(live, window):
    seed.seed(window, "shadow-trial", today=TUESDAY)
    with pytest.raises(seed.Refused, match="already"):
        seed.seed(window, "shadow-trial", today=TUESDAY)


# --- every scenario refuses a non-temp folder ------------------------------------------------

LIVE_DATA = paths.JURA_ROOT / "data" / "growth"
REAL_CONFIG = paths.REPO_ROOT / "config"
# What the live engine itself may change meanwhile: its database and run locks. The seed's
# refusals come before it opens anything, and the script's exit status shows they did.
ENGINE_CHURN = ("growth.db", "locks")


def untouched_snapshot() -> dict:
    found = stat_snapshot(REAL_CONFIG, LIVE_DATA)
    churn = [str(LIVE_DATA / name) for name in ENGINE_CHURN]
    return {path: info for path, info in found.items() if not any(path.startswith(c) for c in churn)}


@pytest.mark.parametrize("scenario", list(seed.SCENARIOS))
def test_every_scenario_refuses_the_live_folders_and_changes_nothing(scenario, tmp_path):
    before = untouched_snapshot()
    env = {
        "PATH": "/usr/bin:/bin",
        "JURA_ROOT": str(paths.JURA_ROOT),
        "JURA_GROWTH_DATA_DIR": str(LIVE_DATA),
        "JURA_GROWTH_OUTPUTS_DIR": str(tmp_path / "outputs"),
        "JURA_PRD_DIR": str(tmp_path / "prd"),
        "JURA_GROWTH_CONFIG_DIR": str(REAL_CONFIG),
        send.RESEND_BASE_ENV: STUB,
    }
    args = [sys.executable, str(Path(seed.__file__)), str(LIVE_DATA), "--scenario", scenario, "--lead", "240"]
    ran = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
    assert ran.returncode == 2 and ran.stdout.startswith("refused:"), ran.stdout + ran.stderr
    assert untouched_snapshot() == before
    assert not (tmp_path / "outputs").exists() and not (tmp_path / "prd").exists()


@pytest.mark.parametrize("scenario", list(seed.SCENARIOS))
def test_every_scenario_refuses_the_real_config_folder(window, monkeypatch, scenario):
    before = untouched_snapshot()
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(REAL_CONFIG))
    with pytest.raises(seed.Refused, match="JURA_GROWTH_CONFIG_DIR"):
        seed.seed(window, scenario, today=TUESDAY, lead=240)
    assert untouched_snapshot() == before
    assert not (window / "data").exists()


def test_the_resend_stub_still_refuses_the_live_data_folder(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(LIVE_DATA))
    assert "not a temporary folder" in resend_stub.refusal()


def test_edit_draft_refuses_a_lead_with_no_queued_email(live, window):
    with pytest.raises(seed.Refused, match="lead 999"):
        seed.seed(window, "edit-draft", today=TUESDAY, lead=999)
    with pytest.raises(seed.Refused, match="--lead"):
        seed.seed(window, "edit-draft", today=TUESDAY)
