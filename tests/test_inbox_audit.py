"""The transcript audit's inbox rules (technical review B1, as a table; IW-S3).

Each row is a probe the tech lead ran against the audit as it stood. The publish rules, the default,
stay as they were: `tests/test_publish_audit.py` doesn't change.
"""

from __future__ import annotations

import pytest

import publish_transcripts as t
from jura_growth import transcripts
from jura_growth.agents.inbox_browser import scope as watch_scope
from jura_growth.agents.publish import audit, hosts

TEXT = "Thanks for asking. Levi will come back to you today."
HOSTS = (*hosts.BROWSER_HOSTS["facebook"], *hosts.BROWSER_HOSTS["instagram"])
THREAD = "https://www.instagram.com/direct/t/1234567/"
HOME = "https://www.facebook.com/jurasolutionssg"
REPLY = audit.AuditRules(next_word="inbox reply-next", stopped_word="inbox stopped", done_word="inbox reply-done",
                         tool_word="inbox reply", one_line=True, place_check=hosts.same_place)


def judged(tmp_path, steps, *, approved=(), rules=None, places=()):
    path = t.write(tmp_path / "run.jsonl", steps)
    return audit.audit(transcripts.read(path), hosts=HOSTS, approved=list(approved), images=[], places=list(places),
                       **({"rules": rules} if rules else {}))


def watched(tmp_path, *steps):
    """A watch run's own tab with `steps` on it, under the watch's rules."""
    return judged(tmp_path, [t.created(), t.opened(HOME), *steps, t.closed()], rules=watch_scope.WATCH_RULES)


def reply_claim() -> dict:
    return t.bash("jura-growth inbox reply-next --json", '{"due": true, "approval": "A-0001", "text": "' + TEXT + '"}')


def replied(tmp_path, *steps):
    """A reply run that claimed, opened the thread and did `steps` there."""
    return judged(tmp_path, [reply_claim(), t.created(), t.opened(THREAD), *steps, t.closed()],
                  approved=[TEXT], rules=REPLY, places=[THREAD])


def in_thread(tool: str, given: dict) -> dict:
    return t.page(tool, given, "ok", url=THREAD)


def click() -> dict:
    return in_thread("computer", {"action": "left_click", "ref": "ref_30"})


def typing(text: str) -> dict:
    return in_thread("computer", {"action": "type", "text": text})


def press(name: str) -> dict:
    return in_thread("computer", {"action": "key", "text": name})


# --- the watch: read_only ----------------------------------------------------------------------


def test_iw_s3_a_watch_that_only_reads_passes(tmp_path):
    found = watched(tmp_path, t.page("get_page_text", {}, "a comment"), t.page("read_page", {}, "a tree"),
                    t.page("find", {"query": "comments"}, "ref_1"))
    assert found.ok, found.failures


@pytest.mark.parametrize("action", ["left_click", "right_click", "double_click", "triple_click", "left_click_drag"])
def test_iw_s3_a2_a_click_fails_a_watch_run(tmp_path, action):
    """A click can be Like, Hide, Delete or Block (E6), and the transcript can't say which."""
    found = watched(tmp_path, t.page("computer", {"action": action, "ref": "ref_1"}, "Clicked."))
    assert not found.ok


def test_iw_s3_a9_a_click_after_reading_fails_a_watch_run(tmp_path):
    found = watched(tmp_path, t.page("get_page_text", {}, "a comment"),
                    t.page("computer", {"action": "left_click", "ref": "ref_1"}, "Clicked."))
    assert not found.ok


def test_iw_s3_a_denied_click_still_fails_a_watch_run(tmp_path):
    """The attempt is the finding: hostile text asked for it, whether or not Claude Code allowed it."""
    found = watched(tmp_path, t.page("computer", {"action": "left_click", "ref": "ref_1"}, "Denied", denied=True))
    assert not found.ok


@pytest.mark.parametrize("given", [
    {"action": "key", "text": "Return"},
    {"action": "type", "text": "hello"},
    {"text": "no action named"},
])
def test_iw_s3_keys_and_typing_fail_a_watch_run(tmp_path, given):
    assert not watched(tmp_path, t.page("computer", given, "ok")).ok


def test_iw_s3_a_form_input_fails_a_watch_run_even_with_nothing_typed(tmp_path):
    assert not watched(tmp_path, t.page("form_input", {"ref": "ref_1", "value": ""}, "ok")).ok


@pytest.mark.parametrize("tool", ["file_upload", "upload_image"])
def test_iw_s3_an_upload_fails_a_watch_run(tmp_path, tool):
    assert not watched(tmp_path, t.page(tool, {"paths": ["/tmp/x.png"]}, "ok")).ok


@pytest.mark.parametrize("action", ["screenshot", "scroll", "wait", "hover"])
def test_iw_b1_looks_stay_allowed_in_the_second_layer(tmp_path, action):
    """`computer` is denied by name today (B2). ADR 0006 records allowing it as a one-line change, so
    `read_only` must let a look through and catch everything else."""
    assert watched(tmp_path, t.page("computer", {"action": action}, "ok")).ok


def test_iw_s3_findings_name_the_watch_and_hold_no_page_text(tmp_path):
    found = watched(tmp_path, t.page("javascript_tool", {"text": "PLANTED PAGE WORDS"}, "PLANTED PAGE WORDS"),
                    t.opened("https://evil.test/PLANTED-PATH"))
    joined = " ".join(found.failures)
    assert "inbox watch" in joined
    assert "publish" not in joined
    assert "PLANTED" not in joined


def test_iw_s3_the_watch_may_open_only_its_hosts(tmp_path):
    assert not watched(tmp_path, t.opened("https://www.linkedin.com/feed/")).ok
    assert not watched(tmp_path, t.opened("https://l.facebook.com/l.php?u=https://evil.test")).ok
    assert watched(tmp_path, t.opened("https://business.facebook.com/latest/inbox/all")).ok
    assert watched(tmp_path, t.opened("https://www.instagram.com/direct/inbox/")).ok


# --- a reply run: the claim word -----------------------------------------------------------------


def test_iw_b1_a3_a_reply_run_claims_through_its_own_command(tmp_path):
    found = replied(tmp_path, click(), typing(TEXT), press("Return"))
    assert found.ok, found.failures


def test_iw_b1_typing_before_the_reply_claim_fails(tmp_path):
    found = judged(tmp_path, [t.created(), t.opened(THREAD), typing(TEXT), reply_claim(), t.closed()],
                   approved=[TEXT], rules=REPLY, places=[THREAD])
    assert not found.ok


def test_iw_b1_the_publish_claim_word_claims_nothing_for_a_reply_run(tmp_path):
    found = judged(tmp_path, [t.claimed(text=TEXT), t.created(), t.opened(THREAD), typing(TEXT), t.closed()],
                   approved=[TEXT], rules=REPLY, places=[THREAD])
    assert not found.ok


def test_iw_b1_nothing_acts_after_the_reply_runs_own_stop_word(tmp_path):
    found = replied(tmp_path, t.bash("jura-growth inbox stopped --reason login", "stopped"), click())
    assert not found.ok
    assert any("after inbox stopped" in failure for failure in found.failures)


# --- a reply run: one_line ----------------------------------------------------------------------


def test_iw_b1_a4_the_whole_text_then_return_passes(tmp_path):
    assert replied(tmp_path, typing(TEXT), press("Return")).ok


def test_iw_b1_a5_return_in_the_middle_fails(tmp_path):
    """In a DM each Return sends, so a fragment would go out."""
    half = len(TEXT) // 2
    found = replied(tmp_path, typing(TEXT[:half]), press("Return"), typing(TEXT[half:]))
    assert not found.ok


def test_iw_b1_a5_passes_under_the_publish_rules_which_is_why_the_rule_exists(tmp_path):
    half = len(TEXT) // 2
    steps = [t.claimed(text=TEXT), t.created(), t.opened(t.PAGE), t.typed(TEXT[:half]), t.key("Return"),
             t.typed(TEXT[half:]), t.closed()]
    path = t.write(tmp_path / "run.jsonl", steps)
    joined = TEXT[:half] + " " + TEXT[half:]
    assert audit.audit(transcripts.read(path), hosts=HOSTS, approved=[joined], images=[]).ok


@pytest.mark.parametrize("broken", [
    "Thanks for asking.\nLevi will come back to you today.",
    "Thanks for asking.\r\nLevi will come back to you today.",
    "Thanks for asking. Levi will come back to you today.",
])
def test_iw_b1_a6_a_newline_inside_typed_text_fails(tmp_path, broken):
    found = judged(tmp_path, [reply_claim(), t.created(), t.opened(THREAD), typing(broken), press("Return"), t.closed()],
                   approved=[broken], rules=REPLY, places=[THREAD])
    assert not found.ok


def test_iw_b1_a_newline_in_a_form_input_fails(tmp_path):
    found = replied(tmp_path, in_thread("form_input", {"ref": "ref_1", "value": "one\ntwo"}))
    assert not found.ok


def test_iw_b1_shift_return_fails_even_with_the_whole_text_typed(tmp_path):
    assert not replied(tmp_path, typing(TEXT), press("shift+Return")).ok


def test_iw_b1_a_click_may_be_the_one_send(tmp_path):
    assert replied(tmp_path, click(), typing(TEXT), click()).ok


def test_iw_b1_one_click_opens_the_box_before_the_text_is_typed(tmp_path):
    assert replied(tmp_path, click(), click(), typing(TEXT), press("Return")).ok


@pytest.mark.parametrize("later", [
    [click()],
    [press("Return")],
    [press("Escape")],
    [typing("and one more thing")],
])
def test_iw_b1_a9_nothing_acts_after_the_send(tmp_path, later):
    assert not replied(tmp_path, typing(TEXT), press("Return"), *later).ok


def test_iw_b1_a_look_after_the_send_is_fine(tmp_path):
    found = replied(tmp_path, typing(TEXT), press("Return"), in_thread("computer", {"action": "screenshot"}),
                    in_thread("get_page_text", {}))
    assert found.ok, found.failures


def test_iw_b1_after_reply_done_a_run_may_only_read(tmp_path):
    """Code review 06, SEC-4: a click can be Like, Hide, Delete or Block, and its work is over."""
    done = t.bash("jura-growth inbox reply-done A-0001", "done")
    assert replied(tmp_path, typing(TEXT), press("Return"), done, in_thread("get_page_text", {})).ok
    assert not replied(tmp_path, typing(TEXT), press("Return"), done, click()).ok
    assert not replied(tmp_path, typing(TEXT), press("Return"), done, press("Return")).ok


def test_iw_b1_the_publish_rules_allow_a_click_after_posting(tmp_path):
    """`one_line` is off by default: publish clicks Post and goes on to read the post back."""
    steps = [t.claimed(text=TEXT), t.created(), t.opened(t.PAGE), t.typed(TEXT),
             t.page("computer", {"action": "left_click", "ref": "ref_30"}, "Clicked Post."),
             t.page("computer", {"action": "left_click", "ref": "ref_31"}, "Clicked."), t.closed()]
    path = t.write(tmp_path / "run.jsonl", steps)
    assert audit.audit(transcripts.read(path), hosts=HOSTS, approved=[TEXT], images=[]).ok


# --- a reply run: its own place -----------------------------------------------------------------


def test_iw_b1_a10_a_thread_is_a_place_under_same_place(tmp_path):
    assert replied(tmp_path, typing(TEXT), press("Return")).ok


def test_iw_b1_a10_the_default_place_check_refuses_a_thread(tmp_path):
    """`hosts.within` knows only groups, so without `place_check` a thread is closed, and correctly."""
    rules = audit.AuditRules(next_word="inbox reply-next", one_line=True)
    found = judged(tmp_path, [reply_claim(), t.created(), t.opened(THREAD), typing(TEXT), t.closed()],
                   approved=[TEXT], rules=rules, places=[THREAD])
    assert not found.ok


def test_iw_b1_a10_another_thread_fails_a_reply_run(tmp_path):
    found = replied(tmp_path, t.opened("https://www.instagram.com/direct/t/999/"))
    assert not found.ok
