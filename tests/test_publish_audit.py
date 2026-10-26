"""The publish run's transcript audit (AC-P9.3; seam S11; dataset T).

Pure: a transcript file read through `transcripts.read()`, the hosts the run may be on and the
approved content in; failures and warnings out. Code review 03: B2 (typing judged as the whole
text per field, and never before the claim), S-2 (one host check), S-7 (tab addresses fail
closed), S-8 (uploads of the claimed item's copies only), S-9 (nothing after a stop).
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


def start() -> list[dict]:
    """The browser check and the claim, before anything is typed."""
    return [*t.browser_check(), t.claimed(text=TEXT)]


def in_tab(*steps) -> list[dict]:
    return [*start(), t.created(), t.opened(), *steps, t.closed()]


def failed_with(found, word: str) -> bool:
    return any(word in f for f in found.failures)


def test_a_clean_post_passes(tmp_path):
    found = judged(tmp_path, [*start(), *t.clean_post(TEXT, IMAGE)])
    assert found.failures == [] and found.warnings == []
    assert not found.no_browser


# --- hosts (AC-P9.3; S-2) ----------------------------------------------------------------------------


def test_a_navigate_to_another_site_fails_even_when_denied(tmp_path):
    for denied in (False, True):
        steps = in_tab(t.chrome("navigate", {"url": "https://example.com", "tabId": t.TAB},
                                "Permission denied" if denied else "Navigated to https://example.com/\n" + t.tab_context((t.TAB, "https://example.com/")),
                                denied=denied))
        assert failed_with(judged(tmp_path, steps), "example.com")


def test_a_foreign_url_seen_only_in_a_later_results_tab_url_fails(tmp_path):
    steps = in_tab(t.page("computer", {"action": "left_click", "coordinate": [10, 10]}, "Clicked.", url="https://evil.example.net/landing"))
    assert failed_with(judged(tmp_path, steps), "evil.example.net")


@pytest.mark.parametrize("url", ["https://www.facebook.com:8443/jura", "https://jura@www.facebook.com/x", "http://www.facebook.com/x"])
def test_a_publish_host_with_a_port_user_or_plain_http_fails_as_publish_done_would(tmp_path, url):
    steps = in_tab(t.chrome("navigate", {"url": url, "tabId": t.TAB}, f"Navigated to {url}\n" + t.tab_context((t.TAB, url))))
    assert judged(tmp_path, steps).failures


def test_page_text_that_merely_mentions_another_site_is_not_a_failure(tmp_path):
    steps = in_tab(t.page("get_page_text", {}, "See https://example.org for more"))
    assert judged(tmp_path, steps).failures == []


@pytest.mark.parametrize("url", ["https://discord.com/channels/1/2", "https://www.discord.com/app", "https://discordapp.com/x"])
def test_a_discord_host_fails_and_says_so(tmp_path, url):
    steps = in_tab(t.chrome("navigate", {"url": url, "tabId": t.TAB}, f"Navigated to {url}"))
    assert failed_with(judged(tmp_path, steps), "Discord")


# --- tab addresses fail closed (S-7) -----------------------------------------------------------------


def test_a_tab_report_in_a_shape_the_audit_cant_read_fails_the_run(tmp_path):
    steps = in_tab(t.chrome("computer", {"action": "left_click", "coordinate": [10, 10], "tabId": t.TAB},
                            "Clicked. Tab 4101 now at https://evil.example.net/x"))
    assert failed_with(judged(tmp_path, steps), "couldn't read")


def test_a_page_tool_result_with_no_tab_address_fails_the_run(tmp_path):
    steps = in_tab(t.chrome("get_page_text", {"tabId": t.TAB}, "a page with no tab context at all"))
    assert failed_with(judged(tmp_path, steps), "couldn't read")


# --- tabs ---------------------------------------------------------------------------------------------


def test_a_tool_call_on_a_tab_this_run_didnt_open_fails(tmp_path):
    steps = in_tab(t.page("get_page_text", {}, "someone's inbox", tab=t.OTHER_TAB))
    assert failed_with(judged(tmp_path, steps), str(t.OTHER_TAB))


def test_a_page_tool_call_that_names_no_tab_fails(tmp_path):
    steps = in_tab(t.chrome("get_page_text", {}, "a page\n" + t.tab_context((t.TAB, t.PAGE))))
    assert judged(tmp_path, steps).failures


def test_a_tab_left_open_is_a_warning_not_a_failure(tmp_path):
    steps = [*start(), t.created(), t.opened()]
    found = judged(tmp_path, steps)
    assert found.failures == []
    assert found.warnings == ["the run left 1 tab open"]


# --- typing (AC-P9.3; B2) -----------------------------------------------------------------------------


@pytest.mark.parametrize("step", [
    t.typed("Call me on +65 9123 4567"),
    t.page("form_input", {"ref": "ref_3", "value": "hunter2"}, "Set."),
    t.key("x"),
])
def test_typed_text_outside_the_approved_content_fails(tmp_path, step):
    assert failed_with(judged(tmp_path, in_tab(step)), "typed")


def test_text_typed_one_character_at_a_time_is_judged_as_a_whole(tmp_path):
    steps = in_tab(*(t.typed(ch) for ch in "hunter secret"))
    assert failed_with(judged(tmp_path, steps), "typed")


def test_approved_words_typed_out_of_order_fail(tmp_path):
    steps = in_tab(t.typed("Your accounting software can send the first reminder for you."),
                   t.typed("Chasing late invoices by hand?"))
    assert failed_with(judged(tmp_path, steps), "typed")


def test_only_part_of_the_approved_text_as_the_whole_post_fails(tmp_path):
    steps = in_tab(t.typed("send the first reminder"), t.page("computer", {"action": "left_click", "ref": "ref_30"}, "Clicked Post."))
    assert failed_with(judged(tmp_path, steps), "typed")


def test_the_approved_text_typed_in_order_across_calls_with_return_between_paragraphs_passes(tmp_path):
    steps = in_tab(t.typed("Chasing late invoices by hand?"), t.key("Return"), t.key("Return"),
                   t.typed("Your accounting  software can send\nthe first reminder for you."))
    assert judged(tmp_path, steps).failures == []


def test_editing_text_after_typing_it_fails(tmp_path):
    steps = in_tab(t.typed("Chasing late invoices by hand?x"), t.key("BackSpace"),
                   t.typed("\n\nYour accounting software can send the first reminder for you."))
    assert failed_with(judged(tmp_path, steps), "edited")


def test_typing_before_the_claim_fails_even_the_approved_text(tmp_path):
    steps = [*t.browser_check(), t.created(), t.opened(), t.typed(TEXT), t.claimed(text=TEXT), t.closed()]
    assert failed_with(judged(tmp_path, steps), "before")


def test_typing_when_nothing_was_claimed_fails(tmp_path):
    steps = [*t.browser_check(), t.nothing_due(), t.created(), t.opened(), t.typed(TEXT), t.closed()]
    assert failed_with(judged(tmp_path, steps, approved=()), "before")


def test_a_field_left_part_typed_by_a_stop_passes(tmp_path):
    steps = in_tab(t.typed("Chasing late invoices"), t.stopped())
    assert judged(tmp_path, steps).failures == []


def test_two_form_fields_are_judged_one_by_one(tmp_path):
    answers = ("We automate invoices for small firms.", "Yes")
    steps = in_tab(t.page("form_input", {"ref": "q1", "value": answers[0]}, "Set."),
                   t.page("form_input", {"ref": "q2", "value": answers[1]}, "Set."))
    assert judged(tmp_path, steps, approved=answers).failures == []


# --- uploads (S-8) ------------------------------------------------------------------------------------


def test_uploading_a_file_that_isnt_the_approved_image_fails(tmp_path):
    steps = in_tab(t.page("file_upload", {"paths": ["/Users/someone/secret.pdf"]}, "Uploaded."))
    assert failed_with(judged(tmp_path, steps), "upload")


def test_an_upload_path_that_only_looks_like_a_copy_fails(tmp_path):
    steps = in_tab(t.page("file_upload", {"paths": ["/tmp/work/publish/A-0001/../../../.env"]}, "Uploaded."))
    assert failed_with(judged(tmp_path, steps), "upload")


# --- uploads: every image, once, in the approved order (BP-04, Instagram carousel days) ---------------


SLIDES = tuple(f"/tmp/work/publish/A-0001/{n}-instagram-{n}-of-3-1080x1350.png" for n in (1, 2, 3))
IG_POST = "https://www.instagram.com/p/C0deAbc123/"


def upload(*paths: str) -> dict:
    return t.page("file_upload", {"paths": list(paths), "ref": "ref_20"}, f"Uploaded {len(paths)} files.")


def done(url: str = IG_POST) -> dict:
    return t.bash(f"jura-growth publish done A-0001 --url {url} --live-text-file /tmp/work/publish/A-0001-live.txt",
                  "A-0001: posted")


def carousel(*steps) -> list[dict]:
    """A carousel post: identity checked, `steps` for the slides, the caption, Share, then done."""
    return in_tab(t.page("get_page_text", {}, "jura.solutions\nEdit profile"), *steps, t.typed(TEXT),
                  t.page("computer", {"action": "left_click", "ref": "ref_31"}, "Clicked Share."), done())


@pytest.mark.parametrize("steps", [
    [upload(*SLIDES)],
    [upload(SLIDES[0]), upload(SLIDES[1]), upload(SLIDES[2])],
    [upload(SLIDES[0], SLIDES[1]), upload(SLIDES[2])],
], ids=["one call", "one call per slide", "two calls"])
def test_every_carousel_slide_uploaded_once_in_order_passes(tmp_path, steps):
    assert judged(tmp_path, carousel(*steps), images=SLIDES).failures == []


@pytest.mark.parametrize("steps, word", [
    ([upload(SLIDES[0], SLIDES[2], SLIDES[1])], "order"),
    ([upload(SLIDES[1]), upload(SLIDES[0]), upload(SLIDES[2])], "order"),
    ([upload(*SLIDES), upload(SLIDES[2])], "more than once"),
    ([upload(SLIDES[0], SLIDES[0], SLIDES[1], SLIDES[2])], "more than once"),
    ([upload(SLIDES[0], SLIDES[1])], "2 of its 3"),
    ([], "0 of its 3"),
], ids=["swapped", "first two swapped across calls", "last again", "first twice", "one missing", "none"])
def test_slides_out_of_order_repeated_or_missing_from_a_recorded_post_fail(tmp_path, steps, word):
    found = judged(tmp_path, carousel(*steps), images=SLIDES)
    assert failed_with(found, word), found.failures
    assert not any("/tmp/work" in f for f in found.failures)  # findings never quote a path


@pytest.mark.parametrize("flags", [{"error": True}, {"denied": True}], ids=["errored", "denied"])
def test_a_slide_whose_upload_failed_never_counts_as_sent(tmp_path, flags):
    """Code review 04, S1: slides 1 and 2 sent, slide 3's upload failed, then `publish done`."""
    third = t.page("file_upload", {"paths": [SLIDES[2]], "ref": "ref_20"}, "Upload failed.", **flags)
    found = judged(tmp_path, carousel(upload(SLIDES[0], SLIDES[1]), third), images=SLIDES)
    assert failed_with(found, "2 of its 3"), found.failures


def test_a_failed_upload_retried_in_order_passes(tmp_path):
    first = t.page("file_upload", {"paths": [SLIDES[0]], "ref": "ref_20"}, "Upload failed.", error=True)
    steps = carousel(first, upload(*SLIDES))
    assert judged(tmp_path, steps, images=SLIDES).failures == []


def test_a_failed_upload_out_of_order_or_off_the_copies_still_fails(tmp_path):
    wrong = t.page("file_upload", {"paths": [SLIDES[1]], "ref": "ref_20"}, "Upload failed.", error=True)
    assert failed_with(judged(tmp_path, carousel(wrong, upload(*SLIDES)), images=SLIDES), "order")
    secret = t.page("file_upload", {"paths": ["/Users/someone/.ssh/id_rsa"]}, "Permission denied", denied=True)
    assert failed_with(judged(tmp_path, carousel(secret, upload(*SLIDES)), images=SLIDES), "isn't the claimed item")


def test_a_single_image_post_recorded_without_its_image_fails(tmp_path):
    steps = [*start(), *t.clean_post(TEXT), done(t.POST)]
    assert failed_with(judged(tmp_path, steps), "0 of its 1")


def test_a_stop_after_the_first_slides_leaves_the_rest_unsent_and_passes(tmp_path):
    steps = in_tab(t.page("get_page_text", {}, "jura.solutions\nEdit profile"), upload(SLIDES[0]),
                   t.page("computer", {"action": "screenshot"}, "Screenshot taken."), t.stopped(reason="unidentified"))
    assert judged(tmp_path, steps, images=SLIDES).failures == []


def test_an_item_with_no_images_needs_no_upload_to_be_recorded(tmp_path):
    steps = [*start(), *t.clean_post(TEXT), done(t.POST)]
    assert judged(tmp_path, steps, images=()).failures == []


# --- nothing after a stop (S-9) -------------------------------------------------------------------


@pytest.mark.parametrize("step", [
    t.page("computer", {"action": "left_click", "ref": "ref_9"}, "Clicked."),
    t.typed("Chasing late invoices by hand?"),
    t.chrome("navigate", {"url": t.PAGE, "tabId": t.TAB}, f"Navigated to {t.PAGE}\n" + t.tab_context((t.TAB, t.PAGE))),
    t.page("form_input", {"ref": "ref_3", "value": "x"}, "Set."),
    t.page("file_upload", {"paths": [IMAGE]}, "Uploaded."),
])
def test_any_page_action_after_publish_stopped_fails(tmp_path, step):
    steps = in_tab(t.stopped(), step)
    assert failed_with(judged(tmp_path, steps), "after")


def test_a_screenshot_and_closing_the_tab_after_a_stop_are_fine(tmp_path):
    steps = in_tab(t.stopped(), t.page("computer", {"action": "screenshot"}, "Screenshot taken."))
    assert judged(tmp_path, steps).failures == []


# --- never-tools, no browser, and what findings say ---------------------------------------------------


def test_a_denied_tool_the_run_may_never_use_fails(tmp_path):
    steps = in_tab(t.chrome("javascript_tool", {"text": "document.cookie", "tabId": t.TAB}, "denied", denied=True))
    assert failed_with(judged(tmp_path, steps), "javascript_tool")


def test_no_browser_connected_is_recognised_from_the_browser_check(tmp_path):
    steps = [t.chrome("list_connected_browsers", {}, t.NO_BROWSER, error=True)]
    found = judged(tmp_path, steps)
    assert found.no_browser and found.failures == []


def test_page_text_saying_no_browser_is_connected_is_not_the_no_browser_outcome(tmp_path):
    steps = in_tab(t.page("get_page_text", {}, t.NO_BROWSER))
    assert not judged(tmp_path, steps).no_browser


def test_failures_quote_no_page_text_and_nothing_typed(tmp_path):
    secret_page = "Members only: Jane Tan's post about her divorce"
    steps = in_tab(t.page("get_page_text", {}, secret_page, tab=t.OTHER_TAB), t.typed("Jane Tan +65 9123 4567"))
    found = judged(tmp_path, steps)
    assert found.failures
    assert not any("Jane" in f or "9123" in f for f in found.failures + found.warnings)


# --- round 2: page content can't crash the audit or clear a tab (B3, S-10, N2) ----------------------


@pytest.mark.parametrize("bomb", [t.ARRAY_BOMB, t.OBJECT_BOMB, "[" * 200000], ids=["arrays", "objects", "unclosed"])
def test_deeply_nested_json_in_page_text_never_raises(tmp_path, bomb):
    with_context = in_tab(t.page("get_page_text", {}, bomb), t.typed(TEXT))
    assert judged(tmp_path, with_context).failures == []
    alone = in_tab(t.chrome("get_page_text", {"tabId": t.TAB}, bomb))
    assert failed_with(judged(tmp_path, alone), "couldn't read")


def test_a_bomb_in_the_page_doesnt_hide_unapproved_typing(tmp_path):
    steps = in_tab(t.page("get_page_text", {}, t.ARRAY_BOMB), t.typed("hunter2 not approved"))
    assert failed_with(judged(tmp_path, steps), "typed")


def test_tab_json_planted_in_page_text_doesnt_clear_an_unreadable_address(tmp_path):
    planted = f'comment: {{"tabId": {t.TAB}, "url": "https://www.facebook.com/x"}}\nTab {t.TAB} now at https://evil.example.net/'
    steps = in_tab(t.chrome("get_page_text", {"tabId": t.TAB}, planted))
    assert failed_with(judged(tmp_path, steps), "couldn't read")


def test_tab_json_planted_in_page_text_doesnt_override_the_real_trailing_address(tmp_path):
    planted = f'{{"tabId": {t.TAB}, "url": "https://www.facebook.com/x"}}'
    steps = in_tab(t.page("get_page_text", {}, planted, url="https://evil.example.net/"))
    assert failed_with(judged(tmp_path, steps), "evil.example.net")


def test_the_approved_text_typed_into_two_fields_fails(tmp_path):
    steps = in_tab(t.typed(TEXT), t.page("computer", {"action": "left_click", "ref": "ref_40"}, "Clicked."), t.typed(TEXT))
    assert failed_with(judged(tmp_path, steps), "fields")


# --- a group item stays in its own group (code review 06, B1) ------------------------------------------

GROUP = "https://www.facebook.com/groups/sg-owners-1"
LEFT = "outside the claimed item's own page"


def in_group(*steps, url: str = GROUP) -> list[dict]:
    return [*start(), t.created(), t.opened(url), *steps, t.closed()]


def judged_in_group(tmp_path, steps):
    path = t.write(tmp_path / "run.jsonl", steps)
    return audit.audit(transcripts.read(path), hosts=HOSTS, approved=[], images=[], places=[GROUP])


@pytest.mark.parametrize("url", [GROUP, GROUP + "/", GROUP + "?ref=share", GROUP + "/members",
                                 "https://m.facebook.com/groups/sg-owners-1"])
def test_a_group_item_may_act_anywhere_inside_its_own_group(tmp_path, url):
    steps = in_group(t.page("computer", {"action": "left_click", "ref": "ref_7"}, "Clicked Join group.", url=url))
    assert judged_in_group(tmp_path, steps).failures == []


@pytest.mark.parametrize("url", [
    t.PAGE,  # the Jura Page's own timeline (R1)
    "https://www.facebook.com/groups/some-other-group",  # another group (R5)
    "https://www.facebook.com/groups/sg-owners-10",  # a group whose address starts the same
    "https://www.facebook.com/",
])
def test_a_group_item_whose_tab_leaves_its_group_fails(tmp_path, url):
    steps = in_group(t.page("computer", {"action": "left_click", "ref": "ref_7"}, "Clicked.", url=url))
    found = judged_in_group(tmp_path, steps)
    assert failed_with(found, LEFT)
    assert not any(word in f for f in found.failures for word in ("sg-owners", "some-other-group", "jura-test-page"))


def test_a_group_item_that_navigates_out_of_its_group_fails_even_when_denied(tmp_path):
    other = "https://www.facebook.com/groups/some-other-group"
    steps = in_group(t.chrome("navigate", {"url": other, "tabId": t.TAB}, "Permission denied", denied=True))
    assert failed_with(judged_in_group(tmp_path, steps), LEFT)


@pytest.mark.parametrize("path, ok", [("/groups/rehearsal-1", True), ("/groups/rehearsal-1/members", True),
                                      ("/groups/rehearsal-2", False), ("/jura-test-page", False)])
def test_on_the_fixture_site_a_group_item_stays_in_its_own_group_too(tmp_path, path, ok):
    """BP-07's fixture replaces the hosts, never the group-path rule: the rehearsal's group
    addresses are fixture paths, held to the same check."""
    from jura_growth.agents.publish.fixture import Fixture

    site = Fixture("http", "publish-fixture.localhost", 8765)
    group = site.base + "/groups/rehearsal-1"
    steps = [*start(), t.created(), t.opened(group),
             t.page("computer", {"action": "left_click", "ref": "ref_7"}, "Clicked.", url=site.base + path), t.closed()]
    found = audit.audit(transcripts.read(t.write(tmp_path / "run.jsonl", steps)), hosts=HOSTS, approved=[], images=[],
                        site=site, places=[group])
    assert (found.failures == []) is ok, found.failures
    if not ok:
        assert failed_with(found, LEFT)


def test_a_blank_new_tab_is_fine_for_a_group_item(tmp_path):
    assert judged_in_group(tmp_path, in_group()).failures == []
