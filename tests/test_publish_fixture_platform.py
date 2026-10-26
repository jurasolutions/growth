"""The fixture platform for the publish rehearsal (BP-07; uat.md R1 to R6).

`JURA_GROWTH_PUBLISH_FIXTURE_URL` points the publish job at the local fixture site in place of
every platform's own hosts, and only on a loopback host with a temporary data folder (the guard
style of `uat_stub`, ticket 18). Seams: the publish argv (S9), the publish commands, the audit
(S11) and the whole job with the fake `claude` (S10).
"""

from __future__ import annotations

import pytest

import publish_world as pw
from jura_growth import approvals, config, paths, runner, uat_stub
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
    # Code review 07, B1: what a browser's WHATWG parser reads as another host than Python does.
    "http://evil.com\\.localhost:8765",  # a browser reads `\` as `/`: the host is evil.com
    "http://publish-fixture.localhost\\@evil.com:8765",
    "http://evil.com%2F.localhost:8765",  # percent-encoding in the host
    "http://evil.com%5C.localhost:8765",
    "http://evil.com%00.localhost:8765",
    "http://publish-fixture.localhost%2Eevil.com:8765",
    "http://pub lish-fixture.localhost:8765",  # whitespace a browser strips
    "http://publish-fixture.local\thost:8765",
    " http://evil.com:8765",
    "http://publish-fixtüre.localhost:8765",  # non-ASCII, which a browser folds
    "http://evil.com。localhost:8765",
    "http://publish-fixture.localhost:8765#.localhost",
    "http://publish-fixture.localhost:8765?x",
    "http://publish-fixture.localhost.:8765",
    "http://[::ffff:127.0.0.1]:8765",  # loopback spelled another way
    "http://127.1:8765",
    "http://0.0.0.0:8765",
    "http://publish-fixture.localhost:99999",
    # Code review 07, SEC-n1: a domain rule names a host, not a port, so only the dedicated name
    # or a loopback address literal; never `localhost` or another `*.localhost` name.
    "http://localhost:8765",
    "http://evil.com.localhost:8765",
    "http://HTTP-fixture.localhost:8765",
])
def test_a_non_loopback_or_malformed_fixture_url_is_refused_and_never_falls_back(fixture_on, monkeypatch, url):
    monkeypatch.setenv(FIXTURE_ENV, url)
    with pytest.raises(fixture.FixtureRefused, match=FIXTURE_ENV) as refused:
        publish_argv()
    assert "facebook" not in str(refused.value)


def test_the_uat_stubs_share_the_browser_safe_loopback_check(monkeypatch):
    """One loopback guard for the stubs and the fixture (code review 07, ST-1)."""
    monkeypatch.setenv("JURA_GROWTH_D1_BASE_URL", "http://127.0.0.1:8025\\evil.com")
    assert "must point at the local UAT stub" in (uat_stub.url_problem("JURA_GROWTH_D1_BASE_URL") or "")
    monkeypatch.setenv("JURA_GROWTH_D1_BASE_URL", "http://127.0.0.1:8025")
    assert uat_stub.url_problem("JURA_GROWTH_D1_BASE_URL") is None


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


@pytest.mark.parametrize("url, host", [
    ("http://publish-fixture.localhost", "publish-fixture.localhost"),
    ("http://publish-fixture.localhost:8765/", "publish-fixture.localhost"),
    ("HTTP://PUBLISH-FIXTURE.LOCALHOST:8765", "publish-fixture.localhost"),
    ("http://127.0.0.1:8765", "127.0.0.1"),
    ("http://[::1]:8765", "::1"),
])
def test_the_fixture_name_and_loopback_literals_are_accepted(fixture_on, monkeypatch, url, host):
    monkeypatch.setenv(FIXTURE_ENV, url)
    assert domain_rules(publish_argv()) == [f"ClaudeInChromeDomain({host})"]


def test_the_prompt_takes_the_permalink_on_the_target_urls_host():
    """On the fixture, the permalink is `post.html?id=<n>`, on the fixture host: the prompt must
    not tie it to the platform's real host, or R1 fails for a reason it isn't testing (code
    review 07, SP-1)."""
    prompt = (paths.REPO_ROOT / "prompts" / "publish.md").read_text(encoding="utf-8")
    step = prompt[prompt.index("8. Read it back."):prompt.index("9. Record it")]
    assert "same host as the target URL" in " ".join(step.split())
    assert "the platform's own host" not in " ".join(prompt.split())
    facebook = prompt[prompt.index("### Social post: Facebook Page"):]
    facebook = facebook[:facebook.index("\n### ", 1)]
    assert "same host as the target URL" in " ".join(facebook.split())


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
    assert request is not None
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
    assert request is not None
    pw.at(monkeypatch, pw.TEN)
    monkeypatch.setenv(FIXTURE_ENV, "http://publish-fixture.example:8765")

    result = pw.invoke("publish", "next", "--json")

    assert '"due": false' in result.output and FIXTURE_ENV in result.output
    assert pw.item_row(conn, found.id)["state"] == "ready"
    record = approvals.get(conn, request.id)
    assert record is not None and record.used_at is None


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
    "http://publish-fixture.localhost:8765/post.html\\x",  # a browser reads `\` as `/`
])
def test_publish_done_refuses_any_other_address(conn, world, monkeypatch, url):
    found, request = claimed(conn, monkeypatch)
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 1 and "refused" in result.output
    assert pw.item_row(conn, found.id)["state"] == "claimed"


def test_publish_done_says_refused_when_the_fixture_is_refused(conn, world, monkeypatch):
    """A refused fixture reads as a refusal, not a traceback (code review 07, ST-n4)."""
    found, request = claimed(conn, monkeypatch)
    monkeypatch.setenv(FIXTURE_ENV, "http://publish-fixture.example:8765")
    url = FIXTURE + "/post.html?id=1"
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 1 and "refused:" in result.output and FIXTURE_ENV in result.output
    assert pw.item_row(conn, found.id)["state"] == "claimed"
