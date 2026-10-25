"""The community job can't fetch any Facebook host (community scout PRD §3, §4).

The blocked domains have one source, the community plug-in's list
(`groups.blocked_domains()`), and the job's argv denies each apex and every
subdomain of it (see `groups.fetch_denials()` for why that takes two rules).
"""

import shutil

import pytest

from jura_growth import config, paths, runner
from jura_growth.agents.community import groups as groups_mod
from test_headless import rules


def webfetch_denials(job: str) -> set[str]:
    _, denied = rules(job)
    return {rule for rule in denied if rule.startswith("WebFetch(")}


@pytest.fixture
def blocked_config(tmp_path, monkeypatch):
    """A copy of config/ whose blocked_fetch_domains starts with the given
    entries (each written as YAML), used for the rest of the test."""
    configs = tmp_path / "config"
    shutil.copytree(paths.config_dir(), configs)
    community = configs / "community.yaml"
    text = community.read_text(encoding="utf-8")
    assert "blocked_fetch_domains: [facebook.com," in text

    def use(*entries: str):
        added = "".join(f"{entry}, " for entry in entries)
        community.write_text(text.replace("blocked_fetch_domains: [", f"blocked_fetch_domains: [{added}"), encoding="utf-8")
        monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(configs))
        config.reset_caches()
        return configs

    return use


# Pinned on purpose, not read from groups.BLOCKED_DEFAULT: the test fails if
# the default list ever shrinks.
FACEBOOK_DOMAINS = ("facebook.com", "fb.com", "fb.me", "fb.watch", "fbcdn.net", "facebook.net", "messenger.com")


@pytest.mark.parametrize("domain", FACEBOOK_DOMAINS)
def test_the_community_job_denies_each_facebook_apex_and_its_subdomains(domain):
    denied = webfetch_denials("community")
    assert f"WebFetch(domain:{domain})" in denied
    assert f"WebFetch(domain:*.{domain})" in denied


def test_every_domain_in_the_plugins_list_is_denied():
    """Regression for the audit repro test_facebook_deny_list_misses_listed_and_sub_domains:
    fb.watch, fbcdn.net, facebook.net and messenger.com were listed but fetchable,
    and no subdomain rule existed."""
    denied = webfetch_denials("community")
    domains = groups_mod.blocked_domains()
    assert set(FACEBOOK_DOMAINS) <= set(domains)
    missing = [d for d in domains if not {f"WebFetch(domain:{d})", f"WebFetch(domain:*.{d})"} <= denied]
    assert missing == []


def test_adding_a_domain_to_the_plugins_list_blocks_it_without_editing_settings(blocked_config):
    configs = blocked_config()
    settings_before = (configs / "settings.yaml").read_bytes()
    blocked_config("instagram.com")

    assert {"WebFetch(domain:instagram.com)", "WebFetch(domain:*.instagram.com)"} <= webfetch_denials("community")
    assert groups_mod.is_blocked("https://www.instagram.com/x")
    assert (configs / "settings.yaml").read_bytes() == settings_before


OTHER_CLAUDE_JOBS = sorted(
    name for name, spec in config.settings()["jobs"].items() if spec["kind"] == "claude" and name != "community"
)


@pytest.mark.parametrize("job", OTHER_CLAUDE_JOBS)
def test_other_jobs_webfetch_access_is_unchanged(job):
    allowed, _ = rules(job)
    assert webfetch_denials(job) == set()
    assert ("WebFetch" in allowed) == ("WebFetch" in runner.job(job).get("tools", []))


def test_a_domain_written_loosely_in_config_is_still_blocked(blocked_config):
    blocked_config("' *.Instagram.COM. '")

    assert "instagram.com" in groups_mod.blocked_domains()
    assert {"WebFetch(domain:instagram.com)", "WebFetch(domain:*.instagram.com)"} <= webfetch_denials("community")
    assert groups_mod.is_blocked("https://WWW.instagram.com/x")


@pytest.mark.parametrize("entry", [
    "https://instagram.com", "'tiktok.com/'", "'threads.net:443'", "instagram", "'insta gram.com'",
    "'user@instagram.com'", "'*.*.instagram.com'",
])
def test_an_entry_that_is_not_a_bare_domain_refuses_to_build_the_job(blocked_config, entry):
    """A URL, path or port would make deny rules that match no host and an
    is_blocked that misses, so the job refuses to start rather than fail open."""
    blocked_config(entry)

    with pytest.raises(groups_mod.BlockedDomainError, match=r"blocked_fetch_domains.*not a bare domain"):
        runner.claude_command("community", runner.job("community"))
    with pytest.raises(groups_mod.BlockedDomainError):
        groups_mod.is_blocked("https://www.instagram.com/x")


def test_settings_yaml_carries_no_hand_written_facebook_rules():
    """The plug-in's list is the one source; a second list in settings.yaml drifts."""
    assert not [rule for rule in runner.job("community").get("disallowed_tools", []) if rule.startswith("WebFetch(")]
