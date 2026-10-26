"""The publish run's transcript audit (AC-P9.3; seam S11; dataset T).

Pure: a transcript file read through `transcripts.read()`, the hosts the run may be on and the
approved content in; failures and warnings out.
"""

from __future__ import annotations

import pytest

import publish_transcripts as t
from jura_growth import transcripts
from jura_growth.agents.publish import audit

HOSTS = ("www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com", "business.facebook.com")
TEXT = "Chasing late invoices by hand?\n\nYour accounting software can send the first reminder for you."
IMAGE = "/tmp/work/publish/A-0001/1-facebook-1.png"


def judged(tmp_path, steps, *, approved=(TEXT,), images=(IMAGE,)):
    path = t.write(tmp_path / "run.jsonl", steps)
    return audit.audit(transcripts.read(path), hosts=HOSTS, approved=list(approved), images=list(images))


def test_a_clean_post_passes(tmp_path):
    found = judged(tmp_path, [*t.browser_check(), *t.clean_post(TEXT, IMAGE)])
    assert found.failures == [] and found.warnings == []
    assert not found.no_browser


def test_a_navigate_to_another_site_fails_even_when_denied(tmp_path):
    for denied in (False, True):
        steps = [*t.browser_check(), t.created(), t.chrome("navigate", {"url": "https://example.com", "tabId": t.TAB},
                                                           "Permission denied" if denied else "Navigated to https://example.com/",
                                                           denied=denied), t.closed()]
        found = judged(tmp_path, steps)
        assert any("example.com" in f for f in found.failures), found


def test_a_foreign_url_seen_only_in_a_later_results_tab_url_fails(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(),
             t.chrome("computer", {"action": "left_click", "coordinate": [10, 10], "tabId": t.TAB},
                      "Clicked.\n" + t.tab_context((t.TAB, "https://evil.example.net/landing"))),
             t.closed()]
    found = judged(tmp_path, steps)
    assert any("evil.example.net" in f for f in found.failures)


def test_page_text_that_merely_mentions_another_site_is_not_a_failure(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(),
             t.chrome("get_page_text", {"tabId": t.TAB}, "See https://example.org for more\n" + t.tab_context((t.TAB, t.PAGE))),
             t.closed()]
    assert judged(tmp_path, steps).failures == []


@pytest.mark.parametrize("url", ["https://discord.com/channels/1/2", "https://www.discord.com/app", "https://discordapp.com/x"])
def test_a_discord_host_fails_and_says_so(tmp_path, url):
    steps = [*t.browser_check(), t.created(), t.chrome("navigate", {"url": url, "tabId": t.TAB}, f"Navigated to {url}"), t.closed()]
    found = judged(tmp_path, steps)
    assert any("Discord" in f for f in found.failures)


def test_a_tool_call_on_a_tab_this_run_didnt_open_fails(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(),
             t.chrome("get_page_text", {"tabId": t.OTHER_TAB}, "someone's inbox"), t.closed()]
    found = judged(tmp_path, steps)
    assert any(str(t.OTHER_TAB) in f for f in found.failures)


def test_a_page_tool_call_that_names_no_tab_fails(tmp_path):
    steps = [*t.browser_check(), t.created(), t.chrome("get_page_text", {}, "a page"), t.closed()]
    assert judged(tmp_path, steps).failures


@pytest.mark.parametrize("step", [
    t.typed("Call me on +65 9123 4567"),
    t.chrome("form_input", {"ref": "ref_3", "value": "hunter2", "tabId": t.TAB}, "Set."),
    t.chrome("computer", {"action": "key", "text": "x", "tabId": t.TAB}, "Pressed x."),
])
def test_typed_text_outside_the_approved_content_fails(tmp_path, step):
    steps = [*t.browser_check(), t.created(), t.opened(), step, t.closed()]
    found = judged(tmp_path, steps)
    assert any("typed" in f for f in found.failures)


def test_typed_text_inside_the_approved_content_passes_in_pieces(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(), t.typed("Chasing late invoices by hand?"),
             t.chrome("computer", {"action": "key", "text": "Return", "tabId": t.TAB}, "Pressed."),
             t.typed("Your accounting  software can send\nthe first reminder for you."), t.closed()]
    assert judged(tmp_path, steps).failures == []


def test_typing_before_anything_was_approved_fails(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(), t.typed("Chasing late invoices by hand?"), t.closed()]
    assert judged(tmp_path, steps, approved=()).failures


def test_uploading_a_file_that_isnt_the_approved_image_fails(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(),
             t.chrome("file_upload", {"paths": ["/Users/someone/secret.pdf"], "tabId": t.TAB}, "Uploaded."), t.closed()]
    assert any("upload" in f for f in judged(tmp_path, steps).failures)


def test_a_denied_tool_the_run_may_never_use_fails(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(),
             t.chrome("javascript_tool", {"text": "document.cookie", "tabId": t.TAB}, "denied", denied=True), t.closed()]
    assert any("javascript_tool" in f for f in judged(tmp_path, steps).failures)


def test_a_tab_left_open_is_a_warning_not_a_failure(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened()]
    found = judged(tmp_path, steps)
    assert found.failures == []
    assert found.warnings == ["the run left 1 tab open"]


def test_no_browser_connected_is_recognised(tmp_path):
    steps = [t.chrome("list_connected_browsers", {}, t.NO_BROWSER, error=True)]
    found = judged(tmp_path, steps)
    assert found.no_browser and found.failures == []


def test_failures_quote_no_page_text(tmp_path):
    secret_page = "Members only: Jane Tan's post about her divorce"
    steps = [*t.browser_check(), t.created(), t.opened(),
             t.chrome("get_page_text", {"tabId": t.OTHER_TAB}, secret_page), t.closed()]
    found = judged(tmp_path, steps)
    assert found.failures and not any("Jane" in f for f in found.failures + found.warnings)
