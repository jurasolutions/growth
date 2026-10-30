"""The fixture platform with every browser platform enabled (BP-07 after BP-04; code review 07, M1).

BP-04 drives Facebook, Instagram and LinkedIn, and lets the audit take only the claimed item's own
platform. While the fixture is on, none of that may bring a real platform's host back: the argv's
only domain rule and every host the audit accepts are the fixture's. And `social submit` with a
refused fixture says `refused:`, not a traceback.
"""

from __future__ import annotations

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import config, paths, runner
from jura_growth.agents.publish import hosts, scope
from test_social import TIP, env, write  # noqa: F401 - env is a fixture

FIXTURE = "http://publish-fixture.localhost:8765"
FIXTURE_ENV = "JURA_GROWTH_PUBLISH_FIXTURE_URL"
EVERY = ("facebook", "instagram", "linkedin")
REAL = {host for platform in EVERY for host in hosts.BROWSER_HOSTS[platform]}


@pytest.fixture
def every_platform_on_the_fixture(monkeypatch):
    monkeypatch.setenv(FIXTURE_ENV, FIXTURE)
    pw.social_config(monkeypatch, browser=EVERY, urls={p: f"{FIXTURE}/page.html" for p in EVERY})


def test_every_platform_drives_its_real_hosts_without_the_fixture(monkeypatch):
    pw.social_config(monkeypatch, browser=EVERY)
    assert set(scope.browser_hosts()) == REAL  # the merge's other side, so the next test means something


def test_no_real_platform_domain_rule_while_the_fixture_is_on(every_platform_on_the_fixture):
    built, _ = runner.claude_command("publish", config.settings()["jobs"]["publish"])
    rules = [arg for arg in built if "ClaudeInChromeDomain" in arg]
    assert rules == ["ClaudeInChromeDomain(publish-fixture.localhost:8765)"]
    assert not [arg for arg in built if any(host in arg for host in REAL)]


@pytest.mark.parametrize("platforms", [None, *((p,) for p in EVERY), EVERY])
def test_the_audit_hosts_are_only_the_fixture_whatever_was_claimed(every_platform_on_the_fixture, platforms):
    assert scope.browser_hosts(platforms) == ("publish-fixture.localhost",)


@pytest.mark.parametrize("platform", EVERY)
def test_a_real_post_address_is_refused_for_every_platform(every_platform_on_the_fixture, platform):
    real = {"facebook": "https://www.facebook.com/jura/posts/1", "instagram": "https://www.instagram.com/p/abc/",
            "linkedin": "https://www.linkedin.com/feed/update/urn:li:activity:1/"}[platform]
    assert "fixture" in (hosts.post_problem(platform, real) or "")
    assert hosts.post_problem(platform, f"{FIXTURE}/post.html?id=1") is None


def test_social_submit_says_refused_when_the_fixture_is_refused(env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, urls={"facebook": f"{FIXTURE}/page.html"})
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    monkeypatch.setenv(FIXTURE_ENV, "http://publish-fixture.example:8765")
    folder = write(paths.work_dir("social") / pw.DAY.isoformat(), TIP)

    result = pw.invoke("social", "submit", str(folder), "--offline")

    assert result.exit_code != 0
    assert "refused:" in result.output and FIXTURE_ENV in result.output
