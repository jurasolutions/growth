"""The UAT harness `tests/uat/seed.py` (X13; ticket 04b; `uat.md` Part A).

It seeds the Part A scenarios into a temporary folder, and refuses unless the data, outputs and
PRD folders are all inside that folder and the folder is a temporary one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jura_growth import config, db, paths
from sweep import KEYCHAIN_VALUE, PHONE, REPLY, RESEND_KEY  # noqa: F401
from uat import seed

SEED = Path(seed.__file__)


@pytest.fixture
def uat(tmp_path, monkeypatch):
    """The Part A window: every folder under one temp folder, the clock at Tue 10 Nov, 08:00."""
    folder = tmp_path / "uat"
    folder.mkdir()
    for variable, name in (("JURA_GROWTH_DATA_DIR", "data"), ("JURA_GROWTH_OUTPUTS_DIR", "outputs"), ("JURA_PRD_DIR", "prd")):
        monkeypatch.setenv(variable, str(folder / name))
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T08:00:00+08:00")
    return folder


# --- the refusal --------------------------------------------------------------------------


def test_a_temp_folder_holding_every_folder_is_accepted(uat):
    assert seed.refusal(uat) is None


@pytest.mark.parametrize("variable", ["JURA_GROWTH_DATA_DIR", "JURA_GROWTH_OUTPUTS_DIR", "JURA_PRD_DIR"])
def test_a_folder_left_unset_is_refused(uat, monkeypatch, variable):
    monkeypatch.delenv(variable)
    assert variable in seed.refusal(uat)


@pytest.mark.parametrize("variable", ["JURA_GROWTH_DATA_DIR", "JURA_GROWTH_OUTPUTS_DIR", "JURA_PRD_DIR"])
def test_a_folder_outside_the_uat_folder_is_refused(uat, monkeypatch, tmp_path, variable):
    monkeypatch.setenv(variable, str(tmp_path / "elsewhere"))
    assert variable in seed.refusal(uat)


# --- SEC-S1: the seed can't reach the live Discord -----------------------------------------------

LIVE_WEBHOOK = "https://discord.com/api/webhooks/1234/live-token-in-a-test"


def test_with_no_env_file_of_its_own_it_is_refused(uat, monkeypatch):
    """Without the export, the repo's .env holds the live webhooks, and every sweep would post."""
    monkeypatch.delenv("JURA_GROWTH_ENV_FILE")
    assert "JURA_GROWTH_ENV_FILE" in seed.refusal(uat)


@pytest.mark.parametrize("inside", [paths.REPO_ROOT, paths.JURA_ROOT / "repos" / "growth"])
def test_an_env_file_in_the_repo_is_refused(uat, monkeypatch, inside):
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(inside / ".env"))
    assert "JURA_GROWTH_ENV_FILE" in seed.refusal(uat)


def test_a_webhook_in_the_shell_is_refused_and_not_printed(uat, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_APPROVALS", LIVE_WEBHOOK)
    why = seed.refusal(uat)
    assert "DISCORD_WEBHOOK_APPROVALS" in why and "live-token" not in why


@pytest.mark.parametrize("url", ["http://127.0.0.1:9000/api/webhooks/1/x", "https://discord.invalid/api/webhooks/1/x"])
def test_a_webhook_that_cannot_leave_this_mac_is_allowed(uat, monkeypatch, url):
    monkeypatch.setenv("DISCORD_WEBHOOK_APPROVALS", url)
    assert seed.refusal(uat) is None


@pytest.mark.parametrize("url", ["https://127.0.0.1.discord.com/api/webhooks/1/x", "https://discord.invalid.discord.com/api/webhooks/1/x",
                                 "https://x.invalid@discord.com/api/webhooks/1/x", "https://discord.com\\@x.invalid/api/webhooks/1/x"])
def test_a_host_that_only_looks_like_a_stand_in_is_refused(uat, monkeypatch, url):
    monkeypatch.setenv("DISCORD_WEBHOOK_APPROVALS", url)
    assert "DISCORD_WEBHOOK_APPROVALS" in seed.refusal(uat)


def uat_env(monkeypatch, tmp_path, line: str):
    """A planted live env file holding LIVE_WEBHOOK, and a UAT env file holding `line`."""
    live_env = tmp_path / "live.env"
    live_env.write_text(f"DISCORD_WEBHOOK_APPROVALS={LIVE_WEBHOOK}\n", encoding="utf-8")
    monkeypatch.setattr(seed, "LIVE_ENV_FILES", (live_env,))
    copy = tmp_path / "uat.env"
    copy.write_text(line + "\n", encoding="utf-8")
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(copy))


@pytest.mark.parametrize("spelling", [
    LIVE_WEBHOOK,
    f"'{LIVE_WEBHOOK}'",
    f"{LIVE_WEBHOOK}/",
    f"{LIVE_WEBHOOK}?wait=true",
    "https://discord.com/api/v10/webhooks/1234/live-token-in-a-test",
    "https://ptb.discord.com/api/webhooks/1234/live-token-in-a-test",
    "https://discordapp.com/api/webhooks/1234/live-token-in-a-test",
    "https://discord.com/api/webhooks/%31234/live-token-in-a-test",
])
def test_a_live_webhook_in_any_spelling_in_the_env_file_is_refused_and_not_printed(uat, monkeypatch, tmp_path, spelling):
    uat_env(monkeypatch, tmp_path, f"DISCORD_WEBHOOK_FEED={spelling}")
    why = seed.refusal(uat)
    assert "DISCORD_WEBHOOK_FEED" in why and "live-token" not in why


def test_the_test_servers_webhook_in_the_env_file_is_allowed(uat, monkeypatch, tmp_path):
    uat_env(monkeypatch, tmp_path, "DISCORD_WEBHOOK_FEED=https://discord.com/api/webhooks/9/test-server")
    assert seed.refusal(uat) is None


def test_a_keychain_value_in_the_env_file_is_refused_and_not_printed(uat, monkeypatch, tmp_path):
    """`config.secret` would resolve it after the compare, to whatever the Keychain holds."""
    uat_env(monkeypatch, tmp_path, "DISCORD_WEBHOOK_FEED=keychain:jura-live-feed-name")
    why = seed.refusal(uat)
    assert "DISCORD_WEBHOOK_FEED" in why and "keychain" in why and "jura-live-feed-name" not in why


def test_a_webhook_that_cannot_be_compared_is_refused_and_not_printed(uat, monkeypatch, tmp_path):
    uat_env(monkeypatch, tmp_path, "DISCORD_WEBHOOK_FEED=https://hooks.example.test/no-id-here")
    why = seed.refusal(uat)
    assert "DISCORD_WEBHOOK_FEED" in why and "no-id-here" not in why


def test_with_no_live_env_file_to_compare_against_it_is_refused(uat, monkeypatch, tmp_path):
    """As in a worktree with `JURA_ROOT` unset, where neither place holds the live file."""
    monkeypatch.setattr(seed, "LIVE_ENV_FILES", (tmp_path / "absent" / ".env", tmp_path / "also-absent.env"))
    why = seed.refusal(uat)
    assert "live" in why and "JURA_ROOT" in why


def test_a_live_env_file_with_a_webhook_it_cannot_read_is_refused(uat, monkeypatch, tmp_path):
    live_env = tmp_path / "live.env"
    live_env.write_text("DISCORD_WEBHOOK_APPROVALS=keychain:jura-live-approvals\n", encoding="utf-8")
    monkeypatch.setattr(seed, "LIVE_ENV_FILES", (live_env,))
    monkeypatch.setattr(config, "_keychain", lambda name: None)
    why = seed.refusal(uat)
    assert "DISCORD_WEBHOOK_APPROVALS" in why and "jura-live-approvals" not in why


def test_a_live_webhook_behind_the_keychain_is_still_compared(uat, monkeypatch, tmp_path):
    live_env = tmp_path / "live.env"
    live_env.write_text("DISCORD_WEBHOOK_APPROVALS=keychain:jura-live-approvals\n", encoding="utf-8")
    monkeypatch.setattr(seed, "LIVE_ENV_FILES", (live_env,))
    monkeypatch.setattr(config, "_keychain", lambda name: LIVE_WEBHOOK)
    copy = tmp_path / "uat.env"
    copy.write_text(f"DISCORD_WEBHOOK_FEED={LIVE_WEBHOOK}/\n", encoding="utf-8")
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(copy))
    assert "DISCORD_WEBHOOK_FEED" in seed.refusal(uat)


# --- the suite stays out of the live .env --------------------------------------------------------


def test_the_suite_compares_against_a_planted_file_and_never_the_live_one(tmp_path):
    assert seed.LIVE_ENV_FILES == (tmp_path / "planted-live.env",)


def test_the_seeds_own_default_names_the_live_places_without_opening_them():
    fresh = seed.live_env_places()
    assert paths.REPO_ROOT / ".env" in fresh and paths.JURA_ROOT / "repos" / "growth" / ".env" in fresh


def test_opening_the_live_env_in_a_test_is_refused_by_the_guard(live_env_guard, tmp_path, monkeypatch):
    """On a planted path: this test must not open the real one to prove it can't."""
    planted = tmp_path / "pretend-live.env"
    planted.write_text("x=y\n", encoding="utf-8")
    monkeypatch.setattr(live_env_guard, "files", {os.path.realpath(planted)})
    with pytest.raises(PermissionError, match="live .env"):
        planted.read_text(encoding="utf-8")
    assert live_env_guard.take() == [os.path.realpath(planted)]


@pytest.mark.parametrize("scenario", ["social-day", "app-prd", "decide"])
def test_a_scenario_that_posts_is_refused_with_no_env_file_and_seeds_nothing(uat, monkeypatch, scenario):
    monkeypatch.delenv("JURA_GROWTH_ENV_FILE")
    with pytest.raises(seed.Refused, match="JURA_GROWTH_ENV_FILE"):
        seed.seed(uat, scenario)
    assert not (uat / "data").exists()


def test_the_live_data_folder_is_refused():
    live = paths.JURA_ROOT / "data" / "growth"
    assert "temporary" in seed.refusal(live)


def test_a_folder_that_isnt_temporary_is_refused(monkeypatch):
    home = Path.home() / "jura-uat"
    for variable, name in (("JURA_GROWTH_DATA_DIR", "data"), ("JURA_GROWTH_OUTPUTS_DIR", "outputs"), ("JURA_PRD_DIR", "prd")):
        monkeypatch.setenv(variable, str(home / name))
    assert "temporary" in seed.refusal(home)


def test_run_as_a_script_it_refuses_a_non_temp_data_folder_and_writes_nothing(tmp_path):
    live = paths.JURA_ROOT / "data" / "growth"
    env = {
        "PATH": "/usr/bin:/bin",
        "JURA_ROOT": str(paths.JURA_ROOT),
        "JURA_GROWTH_DATA_DIR": str(live),
        "JURA_GROWTH_OUTPUTS_DIR": str(tmp_path / "outputs"),
        "JURA_PRD_DIR": str(tmp_path / "prd"),
    }
    ran = subprocess.run([sys.executable, str(SEED), str(live)], env=env, capture_output=True, text=True, timeout=60)
    assert ran.returncode == 2
    assert ran.stdout.startswith("refused:")
    assert not (tmp_path / "outputs").exists() and not (tmp_path / "prd").exists()


# --- the base scenario --------------------------------------------------------------------


@pytest.fixture
def seeded(uat):
    seed.seed(uat)
    conn = db.connect()
    yield conn
    conn.close()


def test_s1_every_scheduled_job_has_history_from_2_november(seeded):
    jobs = {r["job"] for r in seeded.execute("SELECT job FROM runs WHERE started_at < '2026-11-03'")}
    assert {"heartbeat", "app-factory", "social", "scout-research", "digest", "backup"} <= jobs
    holiday = seeded.execute("SELECT count(*) FROM runs WHERE job = 'scout-research' AND started_at LIKE '2026-11-09%'").fetchone()[0]
    assert holiday == 0, "no business-day job runs on the Deepavali holiday"


def test_s1_scout_send_on_6_november_misses_two_slots_then_runs_quietly_at_10_26(seeded):
    rows = seeded.execute("SELECT payload_json FROM events WHERE kind = 'run.quiet' AND ts LIKE '2026-11-06%'").fetchall()
    starts = sorted(json.loads(r["payload_json"])["started_at"][11:16] for r in rows)
    assert "09:50" in starts and "10:00" not in starts and "10:10" not in starts and "10:26" in starts


def test_s2_today_app_factory_and_social_ran(seeded):
    factory = db.one(seeded, "SELECT * FROM runs WHERE job = 'app-factory' AND started_at LIKE '2026-11-10%'")
    assert factory["started_at"] == "2026-11-10T07:01:00+08:00" and factory["cost_usd"] == 1.20 and "APP-014" in factory["summary"]
    social = db.one(seeded, "SELECT * FROM runs WHERE job = 'social' AND started_at LIKE '2026-11-10%'")
    assert social["started_at"] == "2026-11-10T07:30:00+08:00" and social["finished_at"] == "2026-11-10T07:34:12+08:00"
    assert social["cost_usd"] == 0.41


def test_s4_the_queued_emails_are_there(seeded):
    lead = db.one(seeded, "SELECT company, industry, score FROM leads WHERE id = 233")
    assert lead == {"company": "Example Pte Ltd", "industry": "logistics", "score": 78}
    first = db.one(seeded, "SELECT m.status, m.queued_at, m.send_after, c.email FROM outreach_messages m JOIN contacts c ON c.id = m.contact_id WHERE m.lead_id = 233")
    assert first == {"status": "queued", "queued_at": "2026-11-06T09:12:00+08:00", "send_after": "2026-11-06", "email": "info@example.com.sg"}
    batch = seeded.execute("SELECT count(*) FROM outreach_messages WHERE lead_id BETWEEN 240 AND 254 AND status = 'queued'").fetchone()[0]
    assert batch == 15
    named = db.one(seeded, "SELECT c.email, c.kind FROM contacts c WHERE c.lead_id = 260")
    assert named == {"email": "jane.tan@example.com.sg", "kind": "named"}


def test_s5_and_s6_the_planted_values_are_where_the_masking_must_find_them(seeded, uat):
    summaries = " ".join(r["summary"] or "" for r in seeded.execute("SELECT summary FROM runs"))
    errors = " ".join(r["error"] or "" for r in seeded.execute("SELECT error FROM runs"))
    drafts = " ".join(r["draft_body"] for r in seeded.execute("SELECT draft_body FROM outreach_messages"))
    transcripts = " ".join(p.read_text() for p in (uat / "data" / "transcripts").rglob("*.jsonl"))
    for place in (summaries, errors, drafts, transcripts):
        assert RESEND_KEY in place
    assert REPLY in transcripts and PHONE in transcripts


def test_s7_the_factory_prd_is_in_the_pending_apps_folder(seeded, uat):
    (prd,) = (uat / "prd" / "pending" / "apps").glob("prd-app-014-*-2026-11-10.md")
    assert prd.read_text().startswith("# ")


def test_s8_the_two_community_groups(seeded):
    groups = {r["name"]: dict(r) for r in seeded.execute("SELECT * FROM community_groups")}
    g4, g7 = groups["G4 Singapore SME owners"], groups["G7 Logistics operators SG"]
    assert g4["joined"] == 1 and g4["rules_confirmed"] == 0 and g4["promo_rules"] == "promo Saturdays only"
    assert g7["joined"] == 0 and g7["fit"] == "good fit"


def test_seeding_twice_is_refused(seeded, uat):
    with pytest.raises(seed.Refused, match="already seeded"):
        seed.seed(uat)


def test_an_unknown_scenario_is_refused(uat):
    with pytest.raises(seed.Refused, match="no scenario"):
        seed.seed(uat, scenario="nope")


# --- note-rules (S13, ticket 05; uat.md C3) ---------------------------------------------------------


def test_g4_and_g7_keep_the_ids_uat_md_types(seeded):
    names = {r["id"]: r["name"] for r in seeded.execute("SELECT id, name FROM community_groups")}
    assert names == {4: "G4 Singapore SME owners", 7: "G7 Logistics operators SG"}


def test_note_rules_raises_g4s_group_rules_request_and_posts_its_card(seeded, uat, monkeypatch):
    from discord_double import DiscordDouble

    double = DiscordDouble(monkeypatch)
    seed.seed(uat, scenario="note-rules", group=4)
    [request] = seeded.execute("SELECT * FROM approvals").fetchall()
    assert request["kind"] == "group-rules" and request["subject"] == "group:4" and request["status"] == "pending"
    g4 = db.one(seeded, "SELECT * FROM community_groups WHERE id = 4")
    assert g4["rules_confirmed"] == 0 and g4["promo_days_confirmed"] is None
    (card,) = double.posts("approvals")
    assert "promo Saturdays only" in card.content and card.components is None
    assert "promo_days=… post_days=…" in card.content
    seed.seed(uat, scenario="note-rules", group=4)  # again: the same request, no second card
    assert seeded.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1 and len(double.posts("approvals")) == 1


@pytest.mark.parametrize("group, why", [(9, "no group 9"), (7, "no rules"), (None, "--group")])
def test_note_rules_refuses_a_group_it_cant_raise_for(seeded, uat, group, why):
    with pytest.raises(seed.Refused, match=why):
        seed.seed(uat, scenario="note-rules", group=group)
    assert seeded.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0


def test_note_rules_refuses_a_non_temp_folder_too(monkeypatch):
    live = paths.JURA_ROOT / "data" / "growth"
    with pytest.raises(seed.Refused, match="temporary"):
        seed.seed(live, scenario="note-rules", group=4)


def test_note_rules_runs_as_a_script_with_its_group(seeded, uat):
    assert seed.main([str(uat), "--scenario", "note-rules", "--group", "4"]) == 0
    assert seeded.execute("SELECT subject FROM approvals").fetchone()[0] == "group:4"
