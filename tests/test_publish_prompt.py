"""`prompts/publish.md` (BP §5.8; AC-P9.4 and AC-P11.1, the prompt half).

The steps are read as a numbered list: the browser check comes before `publish next`, and the
identity check before any typing. One heading per item kind and platform, the ones not yet
enabled marked as such.
"""

from __future__ import annotations

import re

import pytest

from jura_growth import paths

PROMPT = (paths.REPO_ROOT / "prompts" / "publish.md").read_text(encoding="utf-8")


def steps() -> list[str]:
    section = PROMPT.split("## Steps", 1)[1].split("\n## ", 1)[0]
    return [m.group(1) for m in re.finditer(r"^\d+\. (.+(?:\n(?!\d+\. ).+)*)", section, re.M)]


def first(pattern: str) -> int:
    for number, step in enumerate(steps()):
        if re.search(pattern, step, re.I | re.S):
            return number
    raise AssertionError(f"no step matches {pattern!r}")


def test_the_browser_check_comes_before_the_claim():
    assert first(r"list_connected_browsers") < first(r"run `jura-growth publish next --json`")
    assert first(r"tabs_context_mcp") < first(r"run `jura-growth publish next --json`")
    assert re.search(r"SKIP:", steps()[first(r"list_connected_browsers")])


def test_the_identity_check_comes_before_any_typing_and_stops_on_a_mismatch():
    identity = first(r"posting identity")
    assert identity < first(r"\btype\b")
    assert "publish stopped" in steps()[identity] and "--reason wrong-identity" in steps()[identity]


def test_the_run_opens_its_own_tab_and_closes_it():
    assert first(r"tabs_create_mcp") < first(r"navigate")
    assert first(r"tabs_close_mcp") > first(r"jura-growth publish done")


def test_every_stop_reason_is_named():
    from jura_growth.agents.publish.commands import STOP_REASONS

    for reason in STOP_REASONS:
        assert f"`{reason}`" in PROMPT, reason


def test_one_heading_per_item_kind_and_platform_with_the_later_ones_marked():
    headings = re.findall(r"^### (.+)$", PROMPT, re.M)
    for enabled in ("Social post: Facebook Page", "Social post: Instagram", "Social post: LinkedIn company page"):
        found = [h for h in headings if h.startswith(enabled)]
        assert len(found) == 1 and "not yet" not in found[0], enabled
    for later in ("community post",):
        found = [h for h in headings if later.lower() in h.lower()]
        assert found and all("not yet enabled" in h for h in found), later


# --- BP-04: a section per social platform -----------------------------------------------------------


SOCIAL = {"facebook": "Social post: Facebook Page", "instagram": "Social post: Instagram",
          "linkedin": "Social post: LinkedIn company page"}


def section(heading: str) -> str:
    return PROMPT.split(f"### {heading}", 1)[1].split("\n### ", 1)[0]


def part(text: str, label: str) -> str:
    """The `- **<label>:** ...` bullet of a section, with its continuation lines."""
    match = re.search(rf"^- \*\*{label}:\*\*(.+(?:\n(?!- \*\*).+)*)", text, re.M)
    assert match, label
    return " ".join(match.group(1).split())  # the prompt wraps lines anywhere


@pytest.mark.parametrize("platform", list(SOCIAL))
def test_each_social_section_says_where_who_how_and_the_permalink(platform):
    text = section(SOCIAL[platform])
    for label in ("Target", "Identity", "Post", "Permalink", "Stop signals"):
        part(text, label)
    assert "posting_identity" in part(text, "Identity")


@pytest.mark.parametrize("platform", list(SOCIAL))
def test_a_social_section_names_only_its_own_browser_hosts(platform):
    from jura_growth.agents.publish import hosts

    named = set(re.findall(r"`(?:https://)?((?:[a-z0-9-]+\.)+(?:com|net|in|gg))[/`]", section(SOCIAL[platform])))
    assert named, platform
    assert named <= set(hosts.BROWSER_HOSTS[platform]), named - set(hosts.BROWSER_HOSTS[platform])


@pytest.mark.parametrize("platform", list(SOCIAL))
def test_a_social_sections_stop_signals_use_only_the_closed_reasons(platform):
    from jura_growth.agents.publish.commands import STOP_REASONS

    signals = part(section(SOCIAL[platform]), "Stop signals")
    reasons = set(re.findall(r"`([a-z-]+)`", signals))
    assert reasons and reasons <= set(STOP_REASONS), reasons - set(STOP_REASONS)
    assert "wrong-identity" in reasons and "login" in reasons


@pytest.mark.parametrize("platform", ["instagram", "linkedin"])
def test_the_new_identity_checks_never_switch_and_stop_on_a_mismatch(platform):
    identity = part(section(SOCIAL[platform]), "Identity")
    assert "wrong identity" in identity.lower()
    assert re.search(r"switch", identity, re.I)  # names the switch control it must not use


def test_instagram_posts_every_carousel_slide_in_the_order_given():
    text = section(SOCIAL["instagram"])
    post = part(text, "Post")
    assert "carousel" in post.lower()
    assert re.search(r"every image", post) and re.search(r"in the order given", post)
    assert re.search(r"never reorder", post, re.I)


UPLOAD_BUTTONS = ("Select from computer", "Photo/video", "media", "photo button", "Add a photo")


@pytest.mark.parametrize("platform", list(SOCIAL))
def test_images_go_up_only_through_the_file_input_never_an_upload_button(platform):
    """Code review 04, S3: clicking an upload button opens a native file picker the extension can't
    see or close. The file input is found with `find` and its ref passed to `file_upload`."""
    post = part(section(SOCIAL[platform]), "Post")
    assert "`find`" in post and "`file_upload`" in post and "ref" in post
    assert re.search(r"never click [^.]*upload button", post, re.I)
    for button in UPLOAD_BUTTONS:
        # an instruction to click one; "never click ..." is the rule itself
        assert not re.search(rf"(?<!never )\bclick\b[^.]*{re.escape(button)}", post, re.I), button
    steps_text = " ".join(" ".join(steps()).split())
    assert "never click an upload button" in steps_text.lower()


def test_slides_may_go_up_in_several_calls_but_always_in_order():
    """N8: five slides may be too large for one call; the audit takes several calls, in order."""
    post = part(section(SOCIAL["instagram"]), "Post")
    assert re.search(r"several `file_upload` calls", post) and re.search(r"first to last", post)


def test_the_permalinks_are_each_platforms_own_post_address():
    instagram = part(section(SOCIAL["instagram"]), "Permalink")
    assert "www.instagram.com/p/" in instagram and "/reel/" in instagram
    linkedin = part(section(SOCIAL["linkedin"]), "Permalink")
    for form in ("urn:li:activity:", "urn:li:share:", "urn:li:ugcPost:"):
        assert form in linkedin, form


def test_every_named_permalink_is_one_publish_done_accepts():
    """The prompt and `hosts.post_problem` agree on what a post's own address is (S4)."""
    from jura_growth.agents.publish import hosts

    for platform in ("instagram", "linkedin"):
        named = re.findall(r"`(https://[^`]+)`", part(section(SOCIAL[platform]), "Permalink"))
        assert named, platform
        for url in named:
            example = (url.replace("<code>", "C0deAbc123").replace("<number>", "7254000000000000000")
                       .replace("…", "jura-solutions_automation", 1).replace("…", "abcd", 1))
            assert hosts.post_problem(platform, example) is None, url


def test_the_prompt_never_names_a_command_the_run_may_not_use():
    for command in ("publish resolve", "resume", "approve", "skip ", "publish queue"):
        assert f"jura-growth {command}" not in PROMPT


# --- the join section (BP-06: AC-P4.1 to AC-P4.3, AC-P11.1 for the joining identity, X10) ------------


def join_section() -> str:
    heading = next(h for h in re.findall(r"^### (.+)$", PROMPT, re.M) if "join" in h.lower())
    assert "not yet enabled" not in heading
    return PROMPT.split(f"### {heading}", 1)[1].split("\n### ", 1)[0]


def test_the_join_checks_the_page_is_the_joining_identity_before_joining_and_stops_otherwise():
    section = join_section()
    identity = section.index("--reason wrong-identity")
    assert identity < section.index("Join group")
    assert identity < section.index("--outcome requested")


def test_no_way_to_act_as_the_page_is_an_outcome_not_a_stop():
    section = join_section()
    assert "jura-growth publish done <A-id> --outcome pages-not-allowed" in section
    assert re.search(r"not a stop", section, re.I)


def test_membership_questions_submit_nothing_and_record_the_drafted_answers():
    section = join_section()
    assert re.search(r"submit nothing", section, re.I) and re.search(r"type nothing", section, re.I)
    assert "jura-growth publish done <A-id> --outcome questions --file" in section
    assert "q.json" in section


def test_approved_answers_are_typed_exactly_and_new_questions_go_back_to_ting_yu():
    section = join_section()
    assert re.search(r"exactly", section) and "answers" in section
    assert section.count("--outcome questions") >= 2  # met at the join, and again if the questions changed


def test_every_join_outcome_is_named_and_rules_seen_are_noted():
    from jura_growth.agents.publish.outcomes import JOIN_OUTCOMES

    section = join_section()
    for outcome in JOIN_OUTCOMES:
        assert f"--outcome {outcome}" in section, outcome
    assert "jura-growth publish note-rules <group> --file" in section


def test_the_steps_send_a_join_to_its_own_section():
    """A join leaves the post's steps before anything is attached, typed or read back."""
    text = steps()[first(r"join section")]
    assert first(r"join section") < first(r"--live-text-file")
    assert text.index("join section") < text.index("file_upload") < text.index("type")
