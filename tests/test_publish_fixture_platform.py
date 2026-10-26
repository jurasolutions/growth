"""The fixture platform for the publish rehearsal (BP-07; uat.md R1 to R6).

`JURA_GROWTH_PUBLISH_FIXTURE_URL` points the publish job at the local fixture site in place of
every platform's own hosts, and only on a loopback host with a temporary data folder (the guard
style of `uat_stub`, ticket 18). Seams: the publish argv (S9), the publish commands, the audit
(S11) and the whole job with the fake `claude` (S10).
"""

from __future__ import annotations

import pytest

import publish_world as pw
from jura_growth import approvals, config, paths, runner
from jura_growth.agents.publish import fixture, items, scope

FIXTURE = "http://publish-fixture.localhost:8765"
FIXTURE_ENV = "JURA_GROWTH_PUBLISH_FIXTURE_URL"


def publish_argv() -> list[str]:
    built, _ = runner.claude_command("publish", config.settings()["jobs"]["publish"])
    return built


def domain_rules(built: list[str]) -> list[str]:
    return [rule for rule in built if rule.startswith("ClaudeInChromeDomain(")]


@pytest.fixture
def fixture_on(monkeypatch):
    monkeypatch.setenv(FIXTURE_ENV, FIXTURE)
    pw.social_config(monkeypatch, urls={"facebook": FIXTURE + "/page.html"})
    return FIXTURE


# --- the argv: the fixture host is the only domain rule ------------------------------------------


def test_without_the_fixture_the_publish_argv_keeps_the_platform_hosts(monkeypatch):
    pw.social_config(monkeypatch)
    rules = domain_rules(publish_argv())
    assert "ClaudeInChromeDomain(www.facebook.com)" in rules
    assert "ClaudeInChromeDomain(publish-fixture.localhost)" not in rules


def test_with_the_fixture_the_only_domain_rule_is_the_fixture_host(fixture_on):
    assert domain_rules(publish_argv()) == ["ClaudeInChromeDomain(publish-fixture.localhost)"]


# --- the guard: never the live data folder, never a non-loopback host ----------------------------


@pytest.mark.parametrize("url", [
    "http://publish-fixture.example:8765",  # not loopback
    "http://example.com:8765",
    "http://10.0.0.5:8765",
    "https://publish-fixture.localhost:8765",  # the fixture site is served over http
    "http://someone@publish-fixture.localhost:8765",  # a user name
    "http://publish-fixture.localhost:8765/page.html",  # a base, not a page
    "http://publish-fixture.localhost.evil.test:8765",
    "publish-fixture.localhost:8765",
])
def test_a_non_loopback_or_malformed_fixture_url_is_refused_and_never_falls_back(fixture_on, monkeypatch, url):
    monkeypatch.setenv(FIXTURE_ENV, url)
    with pytest.raises(fixture.FixtureRefused, match=FIXTURE_ENV) as refused:
        publish_argv()
    assert "facebook" not in str(refused.value)


# These two never build the argv or open growth.db: with the live folder, either would touch it.
# `scope.permissions()` refuses before it reads anything.


def test_the_live_data_folder_refuses_the_fixture(fixture_on, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_DATA_DIR", str(paths.JURA_ROOT / "data" / "growth"))
    with pytest.raises(fixture.FixtureRefused, match="temporary"):
        scope.permissions()


def test_an_unset_data_folder_refuses_the_fixture(fixture_on, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_DATA_DIR")
    with pytest.raises(fixture.FixtureRefused, match="JURA_GROWTH_DATA_DIR"):
        scope.permissions()


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765", "http://localhost:8765", "http://publish-fixture.localhost"])
def test_other_loopback_hosts_are_accepted(fixture_on, monkeypatch, url):
    monkeypatch.setenv(FIXTURE_ENV, url)
    from urllib.parse import urlsplit

    assert domain_rules(publish_argv()) == [f"ClaudeInChromeDomain({urlsplit(url).hostname})"]


# --- the publish commands: only fixture addresses ------------------------------------------------


@pytest.fixture
def world(fixture_on, monkeypatch):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


def live_file(text: str) -> str:
    path = paths.work_dir("publish") / "live.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def claimed(conn, monkeypatch):
    pw.at(monkeypatch, pw.MORNING)
    found, request = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    pw.run(conn, monkeypatch=monkeypatch)
    result = pw.invoke("publish", "next", "--json")
    assert result.exit_code == 0 and '"due": true' in result.output, result.output
    return found, request


def test_an_item_targets_the_fixture_page(conn, world, monkeypatch):
    found, _ = claimed(conn, monkeypatch)
    assert found.target_url == FIXTURE + "/page.html"


def test_a_page_url_on_the_platforms_own_host_makes_no_item(conn, world, monkeypatch):
    pw.social_config(monkeypatch, urls={"facebook": pw.PAGE_URL})
    made = items.create_social(conn, pw.draft(conn), run_id=None)
    assert made.item is None
    assert "www.facebook.com" in made.why and "fixture" in made.why


def test_publish_next_hands_out_no_item_whose_target_is_off_the_fixture(conn, world, monkeypatch):
    # Made and approved before the fixture was switched on, so it targets the real Page.
    monkeypatch.delenv(FIXTURE_ENV)
    pw.social_config(monkeypatch)
    pw.at(monkeypatch, pw.MORNING)
    found, _ = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    monkeypatch.setenv(FIXTURE_ENV, FIXTURE)

    result = pw.invoke("publish", "next", "--json")

    assert result.exit_code == 0 and '"due": false' in result.output
    assert "www.facebook.com" in result.output and "fixture" in result.output
    assert pw.item_row(conn, found.id)["state"] == "ready"


def test_a_refused_fixture_claims_nothing(conn, world, monkeypatch):
    pw.at(monkeypatch, pw.MORNING)
    found, request = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    monkeypatch.setenv(FIXTURE_ENV, "http://publish-fixture.example:8765")

    result = pw.invoke("publish", "next", "--json")

    assert '"due": false' in result.output and FIXTURE_ENV in result.output
    assert pw.item_row(conn, found.id)["state"] == "ready"
    assert approvals.get(conn, request.id).used_at is None


def test_publish_done_takes_the_fixture_permalink(conn, world, monkeypatch):
    found, request = claimed(conn, monkeypatch)
    url = FIXTURE + "/post.html?id=1"
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 0, result.output
    assert pw.item_row(conn, found.id)["post_url"] == url


@pytest.mark.parametrize("url", [
    "https://www.facebook.com/jura-test-page/posts/1",  # the platform's own host
    "http://publish-fixture.localhost:9999/post.html?id=1",  # another port
    "https://publish-fixture.localhost:8765/post.html?id=1",  # another scheme
    "http://127.0.0.1:8765/post.html?id=1",  # another loopback name
    "http://x@publish-fixture.localhost:8765/post.html?id=1",
    "http://example.org/",
])
def test_publish_done_refuses_any_other_address(conn, world, monkeypatch, url):
    found, request = claimed(conn, monkeypatch)
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 1 and "refused" in result.output
    assert pw.item_row(conn, found.id)["state"] == "claimed"
