"""The whole publish job on the fixture platform, with the fake `claude` (BP-07; seam S10).

What rehearsal R1 and R3 will show with real Chrome, played here with no browser: a clean post on
the fixture site passes the audit and is recorded with its fixture permalink; a visit to the
platform's real host or to `example.org` fails the run; and a fixture the guard refuses fails the
run before Claude starts.
"""

from __future__ import annotations

import pytest

import publish_fake
import publish_transcripts as t
import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import db, pause, runner

FIXTURE = "http://publish-fixture.localhost:8765"
PAGE = FIXTURE + "/page.html"
POST = FIXTURE + "/post.html?id=1"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    found = publish_fake.install(tmp_path, monkeypatch)

    def on_the_fixture(social):
        social["platforms"]["facebook"]["page_url"] = PAGE

    found.social(on_the_fixture)
    monkeypatch.setenv("JURA_GROWTH_PUBLISH_FIXTURE_URL", FIXTURE)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)
    return found


@pytest.fixture
def approved(conn, fake, monkeypatch):
    pw.at(monkeypatch, pw.MORNING)
    found, approval = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    return found, approval


def chrome(step: dict) -> dict:
    return {"chrome": step["name"].removeprefix(t.CHROME), "input": step["input"], "result": step["result"],
            "error": step["error"], "denied": step["denied"]}


def claim() -> list[dict]:
    return [*(chrome(s) for s in t.browser_check()), {"cli": ["publish", "next", "--json"]}]


def post_steps() -> list[dict]:
    """R1 on the fixture site: open the composer, type, upload, post, read back, record, close."""
    return [
        chrome(t.created()), chrome(t.opened(PAGE)),
        chrome(t.page("get_page_text", {}, "Jura Solutions\nPosting as Jura Solutions", url=PAGE)),
        chrome(t.page("computer", {"action": "left_click", "ref": "ref_12"}, "Clicked.", url=PAGE)),
        chrome(t.page("computer", {"action": "type", "text": "{TEXT}"}, "Typed.", url=PAGE)),
        chrome(t.page("file_upload", {"paths": ["{IMG1}"]}, "Uploaded 1 file.", url=PAGE)),
        chrome(t.page("computer", {"action": "left_click", "ref": "ref_30"}, "Clicked Post.", url=PAGE)),
        chrome(t.opened(POST)),
        chrome(t.page("get_page_text", {}, "{TEXT}", url=POST)),
        {"write": "{A}-live.txt", "text": "{TEXT}"},
        {"cli": ["publish", "done", "{A}", "--url", POST, "--live-text-file", "{WORK}/{A}-live.txt"]},
        chrome(t.closed()),
    ]


def run():
    return runner.run("publish", ignore_schedule=True)


def test_r1_a_clean_fixture_post_passes_the_audit_and_records_its_permalink(conn, fake, approved):
    found, _ = approved
    fake.scenario([*claim(), *post_steps()], "OK: posted {A} " + POST)

    outcome = run()

    assert outcome.status == "ok", outcome
    domain_rules = [rule for rule in fake.argv if rule.startswith("ClaudeInChromeDomain(")]
    assert domain_rules == ["ClaudeInChromeDomain(publish-fixture.localhost:8765)"]
    row = pw.item_row(conn, found.id)
    assert row["state"] == "done" and row["post_url"] == POST
    assert not pause.is_paused(conn, "publish")


@pytest.mark.parametrize("off", ["https://www.facebook.com/jura-test-page", "https://example.org/"])
def test_a_visit_off_the_fixture_fails_the_run_and_pauses_publish(conn, fake, approved, off):
    steps = [*claim(), *post_steps()]
    steps.insert(len(claim()) + 2, chrome(t.opened(off)))
    fake.scenario(steps, "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert off.split("/")[2] in outcome.error
    assert pause.is_paused(conn, "publish")


def test_a_refused_fixture_fails_the_run_before_claude_starts(conn, fake, approved, monkeypatch):
    found, approval = approved
    monkeypatch.setenv("JURA_GROWTH_PUBLISH_FIXTURE_URL", "http://publish-fixture.example:8765")
    fake.scenario([*claim(), *post_steps()])

    outcome = run()

    assert outcome.status == "failed"
    assert "JURA_GROWTH_PUBLISH_FIXTURE_URL" in outcome.error
    assert not fake.started
    assert pw.item_row(conn, found.id)["state"] == "ready"
    assert db.scalar(conn, "SELECT used_at FROM approvals WHERE id = ?", (approval.id,)) is None


def test_a_new_tab_reported_with_an_empty_address_is_not_a_page(conn, fake, approved):
    """Rehearsal R1, 2026-10-30: real Chrome reports a just-created tab as ("") before it navigates.
    That isn't an address outside the fixture, so the audit passes."""
    steps = post_steps()
    steps[0] = chrome(t.created(url=""))
    fake.scenario([*claim(), *steps], "OK: posted {A} " + POST)

    outcome = run()

    assert outcome.status == "ok", outcome
