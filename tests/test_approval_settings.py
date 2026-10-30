"""The `approvals:` settings block (ticket 04b; ticket review T10; X3's settings half).

06, 10 and 11 only read this block. Its three switches start off, and a configured deadline may
shorten one of `caps.py`'s, never lengthen it.
"""

import pytest
import yaml

from jura_growth import approval_settings, caps, config, discord, paths


def test_the_block_sits_directly_after_the_discord_channels_with_only_the_button_switches_on():
    """post_buttons ships on since 2026-10-31, when Dispatch began owning the #approvals webhook,
    and discord_buttons since U17 passed the same day; dispatch_builds stays off until GC-05/06."""
    text = (paths.config_dir() / "settings.yaml").read_text(encoding="utf-8")
    top_level = [line.split(":")[0] for line in text.splitlines() if line and not line[0].isspace() and not line.startswith("#")]
    assert top_level[top_level.index("discord") + 1] == "approvals"
    block = yaml.safe_load(text)["approvals"]
    assert block["discord_buttons"] is True
    assert block["post_buttons"] is True
    assert block["dispatch_builds"] is False


def test_approvals_is_a_discord_channel():
    assert "approvals" in discord.channels()


@pytest.mark.parametrize("name", ["dispatch_builds"])
def test_each_switch_reads_off_from_the_shipped_settings(name):
    assert approval_settings.switch(name) is False


def _with_block(monkeypatch, block):
    patched = dict(config.settings())
    patched["approvals"] = block
    monkeypatch.setattr(config, "settings", lambda: patched)


def test_a_switch_set_true_reads_true(monkeypatch):
    _with_block(monkeypatch, {"post_buttons": True})
    assert approval_settings.switch("post_buttons") is True
    assert approval_settings.switch("discord_buttons") is False


def test_a_misspelt_switch_name_is_a_programming_error():
    with pytest.raises(KeyError):
        approval_settings.switch("discord_button")


def test_a_missing_block_reads_every_switch_off_and_every_deadline_at_its_cap(monkeypatch):
    patched = {k: v for k, v in config.settings().items() if k != "approvals"}
    monkeypatch.setattr(config, "settings", lambda: patched)
    assert approval_settings.switch("dispatch_builds") is False
    assert approval_settings.deadline("app-build", "decide_by_days") == caps.APP_BUILD_DECIDE_BY_DAYS


@pytest.mark.parametrize(
    "kind, key, hard",
    [
        ("outreach-email", "decide_by_business_days", caps.OUTREACH_DECIDE_BY_BUSINESS_DAYS),
        ("outreach-email", "use_by_business_days", caps.OUTREACH_USE_BY_BUSINESS_DAYS),
        ("app-build", "decide_by_days", caps.APP_BUILD_DECIDE_BY_DAYS),
        ("app-release", "decide_by_days", caps.APP_RELEASE_DECIDE_BY_DAYS),
        ("app-release", "use_by_days", caps.APP_RELEASE_USE_BY_DAYS),
        ("group-rules", "decide_by_days", caps.GROUP_RULES_DECIDE_BY_DAYS),
    ],
)
def test_the_shipped_deadlines_are_the_caps_and_may_shorten_but_never_lengthen(monkeypatch, kind, key, hard):
    assert approval_settings.deadline(kind, key) == hard
    _with_block(monkeypatch, {"deadlines": {kind: {key: hard + 5}}})
    assert approval_settings.deadline(kind, key) == hard
    _with_block(monkeypatch, {"deadlines": {kind: {key: 1}}})
    assert approval_settings.deadline(kind, key) == 1


def test_the_shipped_block_names_only_deadlines_that_have_a_cap():
    """A kind applied on decide (app-build, group-rules) claims at the decision, so it has no use-by
    to configure (final code review St5)."""
    text = (paths.config_dir() / "settings.yaml").read_text(encoding="utf-8")
    shipped = yaml.safe_load(text)["approvals"]["deadlines"]
    assert {(kind, key) for kind, keys in shipped.items() for key in keys} == set(approval_settings.DEADLINE_CAPS)
    assert ("app-build", "use_by_days") not in approval_settings.DEADLINE_CAPS
    assert not hasattr(caps, "APP_BUILD_USE_BY_DAYS")


def test_a_deadline_is_never_shortened_below_one(monkeypatch):
    _with_block(monkeypatch, {"deadlines": {"app-build": {"decide_by_days": 0}}})
    assert approval_settings.deadline("app-build", "decide_by_days") == 1


def test_a_deadline_with_no_cap_is_a_programming_error():
    with pytest.raises(KeyError):
        approval_settings.deadline("app-build", "decide_by_weeks")
