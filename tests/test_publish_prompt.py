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
    for later in ("community post", "join"):
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
    return match.group(1)


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
    assert re.search(r"one `file_upload` call", post)
    assert re.search(r"never reorder", post, re.I)


def test_the_permalinks_are_each_platforms_own_post_address():
    assert "www.instagram.com/p/" in part(section(SOCIAL["instagram"]), "Permalink")
    assert "www.linkedin.com/feed/update/urn:li:activity:" in part(section(SOCIAL["linkedin"]), "Permalink")


def test_the_prompt_never_names_a_command_the_run_may_not_use():
    for command in ("publish resolve", "resume", "approve", "skip ", "publish queue"):
        assert f"jura-growth {command}" not in PROMPT
