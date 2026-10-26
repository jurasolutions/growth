"""`publish queue` and `publish resolve` from Discord, and `resume publish` (BP-03; AC-P6.3,
AC-P10.2 and AC-M10.1 through `jura-growth remote`; seam S8).

Tests play Dispatch's side with the SSH origin passed in process, as `tests/test_remote.py` does.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import publish_world as pw
from jura_growth import pause, remote as remote_mod, runner
from jura_growth.agents import publish
from jura_growth.cli import cli
from jura_growth.origin import Origin

ACTOR = f"discord:{pw.CONTROL_ID}"
URL = "https://www.facebook.com/jura-test-page/posts/42"


def remote(*words, as_json=False):
    argv = ["remote", "--actor", ACTOR, *(["--json"] if as_json else []), "--", *words]
    return CliRunner().invoke(cli, argv, obj={"origin": Origin.ssh()})


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


@pytest.fixture
def unknown(conn, world, monkeypatch):
    """An item claimed by a run that recorded neither done nor stopped (AC-P10.1)."""
    found, request = pw.approved(conn, monkeypatch)
    run = pw.run(conn, monkeypatch=monkeypatch)
    assert pw.invoke("publish", "next").exit_code == 0
    publish.after_run(conn, "publish", run, runner.Outcome("ok"))
    monkeypatch.delenv("JURA_GROWTH_RUN_ID")
    assert pw.item_row(conn, found.id)["state"] == "unknown"
    return found, request


def test_resolve_posted_from_discord_settles_the_item(conn, unknown):
    found, request = unknown
    result = remote("publish", "resolve", request.id, "posted", "--url", URL, as_json=True)
    body = json.loads(result.output)
    assert result.exit_code == 0 and body["answer"] == "recorded", body
    assert f"{request.id}: settled as posted" in body["text"]
    row = pw.item_row(conn, found.id)
    assert row["state"] == "done" and row["post_url"] == URL


def test_resolve_not_posted_from_discord_withdraws_the_item(conn, unknown):
    found, request = unknown
    result = remote("publish", "resolve", request.id, "not-posted")
    assert result.exit_code == 0, result.output
    assert pw.item_row(conn, found.id)["state"] == "withdrawn"


def test_resolve_accepts_the_url_as_one_word_too(conn, unknown):
    found, request = unknown
    assert remote("publish", "resolve", request.id, "posted", f"--url={URL}").exit_code == 0
    assert pw.item_row(conn, found.id)["post_url"] == URL


@pytest.mark.parametrize("words", [
    ["publish", "resolve"],
    ["publish", "resolve", "A-0001"],
    ["publish", "resolve", "A-0001", "posted"],
    ["publish", "resolve", "A-0001", "maybe"],
    ["publish", "resolve", "A-0001", "not-posted", "--url", URL],
    ["publish", "resolve", "P-0001", "not-posted"],
    ["publish", "resolve", "A-0001", "posted", "--url", URL, "extra"],
])
def test_a_malformed_resolve_is_refused_and_settles_nothing(conn, unknown, words):
    found, _ = unknown
    result = remote(*words, as_json=True)
    body = json.loads(result.output)
    assert result.exit_code == 2 and body["answer"] == "refused", body
    assert pw.item_row(conn, found.id)["state"] == "unknown"


def test_resolve_off_the_platforms_hosts_settles_nothing(conn, unknown):
    found, request = unknown
    result = remote("publish", "resolve", request.id, "posted", "--url", "https://www.facebook.com.evil.test/x")
    assert result.exit_code == 1
    assert pw.item_row(conn, found.id)["state"] == "unknown"


def test_a_headless_run_cant_resolve_through_remote_either(conn, unknown, monkeypatch):
    found, request = unknown
    monkeypatch.setenv("JURA_GROWTH_JOB", "publish")
    result = remote("publish", "resolve", request.id, "not-posted")
    assert result.exit_code == 2 and "refused" in result.output
    assert pw.item_row(conn, found.id)["state"] == "unknown"


def test_resume_publish_from_discord_works_after_a_stop(conn, unknown):
    assert pause.is_paused(conn, "publish")
    result = remote("resume", "publish")
    assert result.exit_code == 0, result.output
    assert not pause.is_paused(conn, "publish")


def test_publish_queue_from_discord_lists_items_and_their_a_ids(conn, unknown):
    found, request = unknown
    result = remote("publish", "queue", as_json=True)
    body = json.loads(result.output)
    assert result.exit_code == 0 and body["answer"] == "recorded"
    assert found.label in body["text"] and request.id in body["text"] and "unknown" in body["text"]


def test_publish_queue_takes_nothing_after_it(world):
    result = remote("publish", "queue", "--json")
    assert result.exit_code == 2


def test_both_publish_commands_are_on_the_allowlist_and_in_the_contract():
    assert remote_mod.ALLOWLIST["publish queue"].usage == "publish queue"
    assert remote_mod.ALLOWLIST["publish resolve"].usage == "publish resolve <A-nnnn> posted --url <url> | not-posted"
