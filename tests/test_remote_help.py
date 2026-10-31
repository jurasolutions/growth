"""`/growth help`: every control command with a summary (growth-help-pending ticket 01).

Seam S8, as in `test_remote.py`: Dispatch's call through click's `CliRunner`, with the SSH origin
passed in process. The list is built from `remote.ALLOWLIST`, so it can't go stale.
"""

from __future__ import annotations

import json

import pytest

import approval_world as aw
from jura_growth import privacy, remote as remote_mod
from test_remote import answer, events, remote, world  # noqa: F401 - the fixture

INTRO = "Send each as `/growth <command>`, or as a plain message in #control."


def lines(world) -> list[str]:  # noqa: F811 - the fixture
    return answer(remote(["help"], as_json=True))["text"].splitlines()


def test_help_starts_by_saying_how_to_send_a_command(world):  # noqa: F811
    assert lines(world)[0] == INTRO


def test_every_allowlisted_command_has_its_own_line_usage_first_then_its_summary(world):  # noqa: F811
    assert lines(world)[1:] == [f"`{entry.usage}`: {entry.summary}" for entry in remote_mod.ALLOWLIST.values()]


@pytest.mark.parametrize("name", list(remote_mod.ALLOWLIST))
def test_every_entry_has_a_one_line_summary_in_plain_words(name):
    summary = remote_mod.ALLOWLIST[name].summary
    assert summary.strip() and "\n" not in summary
    assert summary[0].isupper() and summary.endswith(".")
    assert "!" not in summary


def test_help_lists_itself_and_pending():
    assert {"help", "pending"} <= set(remote_mod.ALLOWLIST)
    assert remote_mod.ALLOWLIST["help"].summary and remote_mod.ALLOWLIST["pending"].summary


@pytest.mark.parametrize("name", ["apps built", "apps handoffs"])
def test_the_commands_only_dispatch_sends_say_so(name):
    assert "Dispatch" in remote_mod.ALLOWLIST[name].summary


@pytest.mark.parametrize("name", sorted(set(remote_mod.ALLOWLIST) - {"apps built", "apps handoffs"}))
def test_no_other_command_says_only_dispatch_sends_it(name):
    assert "Dispatch" not in remote_mod.ALLOWLIST[name].summary


def test_the_whole_text_fits_with_no_cut_after_masking(world):  # noqa: F811
    built = remote_mod.help_text()
    assert len(built) < remote_mod.TEXT_LIMIT, len(built)
    assert privacy.for_discord(built) == built  # masking changes nothing, so it can't grow or cut
    body = answer(remote(["help"], as_json=True))
    assert body["text"] == built
    assert "(cut" not in body["text"] and len(body["text"]) < remote_mod.TEXT_LIMIT


def test_an_entry_without_a_summary_cant_be_written():
    with pytest.raises(TypeError):
        remote_mod.Entry("status", remote_mod._none("status"))  # type: ignore[call-arg]


def test_the_voice_rules_hold(world):  # noqa: F811
    text = answer(remote(["help"], as_json=True))["text"]
    assert "!" not in text
    assert text.isascii() or set(ch for ch in text if not ch.isascii()) <= {"…"}  # the usages' own ellipsis, no emoji


def test_help_answers_recorded_in_the_contract_shape_and_writes_one_event(conn, world):  # noqa: F811
    result = remote(["help"], ref="m1:d1", as_json=True)
    body = json.loads(result.output)
    assert result.exit_code == 0
    assert set(body) == {"contract", "ok", "answer", "exit_code", "text"}
    assert body["contract"] == 1 and body["ok"] is True and body["answer"] == "recorded" and body["exit_code"] == 0
    (event,) = events(conn)
    assert event["words"] == ["help"] and event["ref"] == "m1:d1" and event["actor"] == aw.CONTROL


def test_words_after_help_are_refused(conn, world):  # noqa: F811
    result = remote(["help", "me"], as_json=True)
    body = json.loads(result.output)
    assert result.exit_code == 2 and body["answer"] == "refused" and body["text"].startswith("refused:")
