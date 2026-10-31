"""Seam S3: setup gaps, install state and the plug-in health hooks (MC-08).

`health.setup_gaps()` is the one function both `jura-growth status` and the
one-pager's health strip read (round 2 decisions §2). A gap names a setting
and says whether it is set; never a value, prefix, length or Keychain service.
"""

from __future__ import annotations

import re
import types

import pytest

from jura_growth import agents, config, discord, health

GAP_LINE = re.compile(r"^(`[A-Z0-9_]+`: (set|not set)|Discord: \d+ of \d+ webhooks)$")
REAL_PLUGINS = agents.plugins


def env_file(tmp_path, monkeypatch, text: str):
    env = tmp_path / "test.env"
    env.write_text(text)
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    config.reset_caches()


def with_plugins(monkeypatch, *extra):
    real = REAL_PLUGINS()
    monkeypatch.setattr(agents, "plugins", lambda: (*real, *extra))


def test_an_unset_key_reads_not_set_and_every_line_has_a_known_shape(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY_OUTREACH", raising=False)
    lines = [gap.line for gap in health.setup_gaps()]
    assert "`RESEND_API_KEY_OUTREACH`: not set" in lines
    assert lines, "the temp env sets nothing, so there must be gaps"
    for line in lines:
        assert GAP_LINE.match(line), line


def test_a_set_key_is_not_a_gap_and_no_value_or_keychain_service_is_shown(tmp_path, monkeypatch):
    env_file(
        tmp_path,
        monkeypatch,
        "RESEND_API_KEY_OUTREACH=re_uat_9Xq7Lm2Pz\nUNSUBSCRIBE_SECRET=keychain:jura-growth-uat\n",
    )
    asked = []
    monkeypatch.setattr(config, "_keychain", lambda service: asked.append(service) or "kc_uat_44Lw")
    gaps = health.setup_gaps()
    names = {gap.name for gap in gaps}
    assert "RESEND_API_KEY_OUTREACH" not in names
    assert "UNSUBSCRIBE_SECRET" not in names  # a keychain: reference counts as set
    assert asked == [], "checking a gap never asks the Keychain"
    text = "\n".join(gap.line for gap in gaps)
    for leaked in ("re_uat", "kc_uat", "jura-growth-uat", "keychain"):
        assert leaked not in text


def test_discord_counts_the_webhooks_set_out_of_every_channel(tmp_path, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
    channels = discord.channels()
    env_file(tmp_path, monkeypatch, f"{discord.env_name(channels[0])}=https://discord.invalid/api/webhooks/1/x\n")
    lines = [gap.line for gap in health.setup_gaps()]
    assert f"Discord: 1 of {len(channels)} webhooks" in lines


def test_every_webhook_set_means_no_discord_gap(tmp_path, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
    env_file(
        tmp_path,
        monkeypatch,
        "".join(f"{discord.env_name(c)}=https://discord.invalid/api/webhooks/{n}/x\n" for n, c in enumerate(discord.channels())),
    )
    assert not [gap for gap in health.setup_gaps() if gap.name == "Discord"]


def test_a_plugin_adds_gaps_through_required_settings(monkeypatch):
    plugin = types.SimpleNamespace(NAME="extra", REQUIRED_SETTINGS=("EXTRA_TOKEN",))
    with_plugins(monkeypatch, plugin)
    assert "`EXTRA_TOKEN`: not set" in [gap.line for gap in health.setup_gaps()]


def test_a_plugin_setup_gaps_hook_replaces_its_required_settings(monkeypatch):
    plugin = types.SimpleNamespace(
        NAME="extra",
        REQUIRED_SETTINGS=("IGNORED_TOKEN",),
        setup_gaps=lambda: [health.Gap("PUBLISH_AUTH"), health.Gap("PUBLISH_FINE", ok=True)],
    )
    with_plugins(monkeypatch, plugin)
    lines = [gap.line for gap in health.setup_gaps()]
    assert "`PUBLISH_AUTH`: not set" in lines
    assert not any("IGNORED_TOKEN" in line or "PUBLISH_FINE" in line for line in lines)


def test_a_failing_plugin_hook_is_a_gap_line_not_a_crash(monkeypatch):
    def broken():
        raise RuntimeError("secret re_uat_9Xq7Lm2Pz")

    with_plugins(monkeypatch, types.SimpleNamespace(NAME="extra", setup_gaps=broken))
    lines = [gap.line for gap in health.setup_gaps()]
    assert "`EXTRA_SETUP_CHECK`: not set" in lines
    assert not any("re_uat" in line for line in lines)


@pytest.mark.parametrize("bad", ["lower_case", "HAS SPACE", "A=B"])
def test_a_gap_name_must_be_a_setting_name(bad):
    with pytest.raises(ValueError):
        health.Gap(bad)


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "EXTRA_TOKEN", "ok": "re_uat_9Xq7Lm2Pz"},
        {"name": "Discord", "have": "re_uat_9Xq7Lm2Pz", "of": 1},
        {"name": "Discord", "have": 1, "of": "8"},
        {"name": "Discord", "have": True, "of": 8},
    ],
)
def test_a_gap_carries_names_booleans_and_counts_only(fields):
    with pytest.raises(ValueError):
        health.Gap(**fields)


def test_a_plugin_cannot_report_the_discord_count(monkeypatch):
    plugin = types.SimpleNamespace(NAME="extra", setup_gaps=lambda: [health.Gap("Discord", have=7, of=7), health.Gap("EXTRA_TOKEN")])
    with_plugins(monkeypatch, plugin)
    lines = [gap.line for gap in health.setup_gaps()]
    assert "Discord: 7 of 7 webhooks" not in lines
    assert "`EXTRA_TOKEN`: not set" in lines


def test_a_plugin_value_never_reaches_a_gap_line(monkeypatch):
    plugin = types.SimpleNamespace(NAME="extra", setup_gaps=lambda: [health.Gap("Discord", have="re_uat_9Xq7Lm2Pz", of=1)])
    with_plugins(monkeypatch, plugin)
    lines = [gap.line for gap in health.setup_gaps()]
    assert not any("re_uat" in line for line in lines)
    assert "`EXTRA_SETUP_CHECK`: not set" in lines


def test_a_malformed_required_setting_is_a_gap_not_a_crash(monkeypatch, tmp_path):
    from jura_growth import mission

    import mission_world as world

    with_plugins(monkeypatch, types.SimpleNamespace(NAME="extra", REQUIRED_SETTINGS=("lower_case",)))
    assert "`EXTRA_SETUP_CHECK`: not set" in [gap.line for gap in health.setup_gaps()]
    snapshot = mission.read(world.source())
    assert health.Gap("EXTRA_SETUP_CHECK") in snapshot.gaps
    assert any(line.startswith(GAP_PREFIX + "`EXTRA_SETUP_CHECK`") for line in status_output(monkeypatch, tmp_path).splitlines())


def test_control_discord_user_id_is_a_core_gap(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTROL_DISCORD_USER_ID", raising=False)
    assert "`CONTROL_DISCORD_USER_ID`: not set" in [gap.line for gap in health.setup_gaps()]
    env_file(tmp_path, monkeypatch, "CONTROL_DISCORD_USER_ID=111\n")
    assert "CONTROL_DISCORD_USER_ID" not in {gap.name for gap in health.setup_gaps()}


# --- jura-growth status ------------------------------------------------------

# `jura-growth status` on crew/mission-control at 8e3d9b4, before the gap lines, with its
# times following the morning brief PRD.
# TMP is the test's temp folder; {channels} is however many Discord channels
# settings.yaml lists, which parallel tickets add to.
STATUS_GOLDEN = """\
database   TMP/data/growth.db
paused     nothing

job              schedule                                 installed  last run
heartbeat        daily 12:00                              no         never
app-factory      daily 07:00                              no         never
social           daily 07:30                              no         never
scout-research   business days 06:30                      no         never
scout-send       business days 09:30–16:30, every 10 min  no         never
scout-sync       business days 16:45                      no         never
digest           daily 17:30                              no         never
community        Mon 08:00                                no         never
backup           daily 23:30                              yes        never

discord    0 of {channels} channel webhooks set
agents     app-factory, community, inbox, inbox-browser, outreach, publish, scout, social
"""
GOLDEN_JOBS = {line.split()[0] for line in STATUS_GOLDEN.splitlines()[4:13]}
GAP_PREFIX = "setup gap  "


def status_output(monkeypatch, tmp_path) -> str:
    from datetime import timedelta

    from click.testing import CliRunner

    from jura_growth import cli, schedule

    monkeypatch.setattr(schedule, "installed", lambda job: job == "backup")
    monkeypatch.setattr(schedule, "local_offset", lambda: timedelta(hours=8))
    result = CliRunner().invoke(cli.cli, ["status"])
    assert result.exit_code == 0, result.output
    return result.output.replace(str(tmp_path), "TMP")


def test_status_lists_the_same_gaps_as_the_health_strip(monkeypatch, tmp_path):
    with_plugins(monkeypatch, types.SimpleNamespace(NAME="extra", REQUIRED_SETTINGS=("EXTRA_TOKEN",)))
    output = status_output(monkeypatch, tmp_path)
    shown = [line.removeprefix(GAP_PREFIX) for line in output.splitlines() if line.startswith(GAP_PREFIX)]
    assert shown == [gap.line for gap in health.setup_gaps()]
    assert "`EXTRA_TOKEN`: not set" in shown


def test_status_and_the_health_strip_list_the_same_gaps_from_one_fixture(monkeypatch, tmp_path):
    from jura_growth import mission

    import mission_world as world

    with_plugins(monkeypatch, types.SimpleNamespace(NAME="extra", REQUIRED_SETTINGS=("EXTRA_TOKEN",)))
    shown = [line.removeprefix(GAP_PREFIX) for line in status_output(monkeypatch, tmp_path).splitlines() if line.startswith(GAP_PREFIX)]
    strip = health.strip(mission.read(world.source()))
    assert [item for item in strip if GAP_LINE.match(item)] == shown
    assert "`EXTRA_TOKEN`: not set" in shown


def test_status_is_unchanged_apart_from_the_gap_lines(monkeypatch, tmp_path):
    from jura_growth import runner

    later_jobs = set(runner.jobs()) - GOLDEN_JOBS  # jobs other tickets add since the golden
    kept = [
        line
        for line in status_output(monkeypatch, tmp_path).splitlines()
        if not line.startswith(GAP_PREFIX) and not (line.split() and line.split()[0] in later_jobs)
    ]
    assert kept == STATUS_GOLDEN.format(channels=len(discord.channels())).splitlines()
