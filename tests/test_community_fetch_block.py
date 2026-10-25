"""The community job can't fetch any Facebook host (community scout PRD §3, §4).

The blocked domains have one source, the community plug-in's list
(`groups.blocked_domains()`), and the job's argv denies each apex and every
subdomain of it. Claude Code matches `WebFetch(domain:x)` by exact host and
`WebFetch(domain:*.x)` by subdomain only, so each domain needs both rules.
"""

import shutil

import pytest

from jura_growth import config, paths, runner
from jura_growth.agents.community import groups as groups_mod


def webfetch_denials(job: str) -> set[str]:
    argv, _ = runner.claude_command(job, config.settings()["jobs"][job])
    start = argv.index("--disallowedTools")
    end = next((i for i in range(start + 1, len(argv)) if argv[i].startswith("--")), len(argv))
    return {rule for rule in argv[start + 1:end] if rule.startswith("WebFetch(")}


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


def test_adding_a_domain_to_the_plugins_list_blocks_it_without_editing_settings(tmp_path, monkeypatch):
    configs = tmp_path / "config"
    shutil.copytree(paths.config_dir(), configs)
    settings_before = (configs / "settings.yaml").read_bytes()
    community = configs / "community.yaml"
    text = community.read_text(encoding="utf-8")
    assert "blocked_fetch_domains: [facebook.com," in text
    community.write_text(text.replace("blocked_fetch_domains: [", "blocked_fetch_domains: [instagram.com, "), encoding="utf-8")
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(configs))
    config.reset_caches()

    denied = webfetch_denials("community")
    assert {"WebFetch(domain:instagram.com)", "WebFetch(domain:*.instagram.com)"} <= denied
    assert groups_mod.is_blocked("https://www.instagram.com/x")
    assert (configs / "settings.yaml").read_bytes() == settings_before


OTHER_CLAUDE_JOBS = sorted(
    name for name, spec in config.settings()["jobs"].items() if spec["kind"] == "claude" and name != "community"
)


@pytest.mark.parametrize("job", OTHER_CLAUDE_JOBS)
def test_other_jobs_webfetch_access_is_unchanged(job):
    argv, _ = runner.claude_command(job, config.settings()["jobs"][job])
    assert webfetch_denials(job) == set()
    allowed = argv[argv.index("--allowedTools") + 1:argv.index("--disallowedTools")]
    assert ("WebFetch" in allowed) == ("WebFetch" in config.settings()["jobs"][job].get("tools", []))


def test_a_domain_written_loosely_in_config_is_still_blocked(tmp_path, monkeypatch):
    configs = tmp_path / "config"
    shutil.copytree(paths.config_dir(), configs)
    community = configs / "community.yaml"
    text = community.read_text(encoding="utf-8")
    community.write_text(text.replace("blocked_fetch_domains: [", "blocked_fetch_domains: [' *.Instagram.COM. ', "), encoding="utf-8")
    monkeypatch.setenv("JURA_GROWTH_CONFIG_DIR", str(configs))
    config.reset_caches()

    assert "instagram.com" in groups_mod.blocked_domains()
    assert {"WebFetch(domain:instagram.com)", "WebFetch(domain:*.instagram.com)"} <= webfetch_denials("community")
    assert groups_mod.is_blocked("https://WWW.instagram.com/x")


def test_settings_yaml_carries_no_hand_written_facebook_rules():
    """The plug-in's list is the one source; a second list in settings.yaml drifts."""
    spec = config.settings()["jobs"]["community"]
    assert not [rule for rule in spec.get("disallowed_tools", []) if rule.startswith("WebFetch(")]
