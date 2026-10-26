"""`prompts/publish.md` (BP §5.8; AC-P9.4 and AC-P11.1, the prompt half).

The steps are read as a numbered list: the browser check comes before `publish next`, and the
identity check before any typing. One heading per item kind and platform, the ones not yet
enabled marked as such.
"""

from __future__ import annotations

import re

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
    assert any("Facebook Page" in h and "not yet" not in h for h in headings)
    for later in ("Instagram", "LinkedIn", "community post", "join"):
        found = [h for h in headings if later.lower() in h.lower()]
        assert found and all("not yet enabled" in h for h in found), later


def test_the_prompt_never_names_a_command_the_run_may_not_use():
    for command in ("publish resolve", "resume", "approve", "skip ", "publish queue"):
        assert f"jura-growth {command}" not in PROMPT
