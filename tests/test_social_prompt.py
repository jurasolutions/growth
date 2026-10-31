"""What the headless social run is told (DP4, technical B4, functional B4).

The prompt holds no word range: `jura-growth social today` prints them from `config/social.yaml`, so
there is one source of truth and a run that follows the prompt can't fail the gate on a stale
number. Whether a real post has insight is Ting Yu's judgement (UAT L3); this checks that it is asked
for, and that the prompt agrees with the checker.
"""

import json
import re

import pytest

from jura_growth import brand_check, paths
from jura_growth.agents.social import render, visuals
from jura_growth.agents.social.settings import load

PROMPT = (paths.REPO_ROOT / "prompts" / "social.md").read_text(encoding="utf-8")
DOCS = (paths.REPO_ROOT / "docs" / "social.md").read_text(encoding="utf-8")
FLAT = re.sub(r"\s+", " ", PROMPT)


@pytest.mark.parametrize("text", [PROMPT, DOCS], ids=["prompt", "docs"])
@pytest.mark.parametrize(
    "stale",
    ["60–120", "50–120", "One or two sources", "copies it from", "Up to 8", "up to 8 hashtags", "Mondays and Thursdays"],
)
def test_nothing_stale_survives(text, stale):
    assert stale not in text


def test_the_prompt_holds_no_word_range():
    """Every word range lives in the config and reaches the run through `today`."""
    assert not re.search(r"(?<![\d-])\d{2,3}\s*(?:–|-|to)\s*\d{2,3}\b", PROMPT)
    assert not re.search(r"aim[^.\n]*\d", PROMPT, re.I)
    assert not re.search(r"\b\d{2,3} words\b", PROMPT.replace("12 words or fewer", ""))
    assert "`jura-growth social today`" in PROMPT and "word range" in FLAT


@pytest.mark.parametrize(
    "ask",
    ["insight", "what happened", "in specifics", "why now", "what changes for a small business", "concrete example", "one thing to do this week"],
)
def test_the_prompt_asks_for_insight_in_four_parts(ask):
    assert ask in FLAT.lower()


@pytest.mark.parametrize(
    "rule",
    [
        "Quote at most a short phrase",
        "No exclamation marks, no emoji, no em dashes",
        "No urgency",
        "AI-powered",
        "this, not that",
        "Never put a digit",
        "Plain text only",
        "Hashtags go together on the last line",
        "No hard sell",
        "Check the official page for current eligibility.",
        "Never imply Jura can secure, apply for or guarantee funding",
        "politics and elections",
        "Facts need a source",
        "Open every page you cite",
        'Write "Link in bio"',
    ],
)
def test_every_existing_brand_rule_stays(rule):
    assert rule in FLAT


def test_an_example_in_a_post_carries_no_invented_figure():
    assert "never invent how much time or money" in FLAT.lower()


@pytest.mark.parametrize(
    "rule",
    [
        "Figures come only from a source",
        "never illustrative",
        "the same way in every post",
        "`source` is the publisher, written as it is in `sources.md`",
    ],
)
def test_the_prompt_ties_a_figure_to_a_source(rule):
    assert rule in FLAT


def test_ai_news_asks_for_an_announcement_and_an_independent_report():
    row = next(line for line in PROMPT.splitlines() if line.startswith("| `ai-news`"))
    assert "company's own announcement" in row and "independent report" in row and "another site" in row


def test_the_prompt_says_which_visual_suits_each_theme():
    settings = load()
    guidance = PROMPT[PROMPT.index("### The picture"):PROMPT.index("## 6.")]
    for theme in settings.themes.values():
        if theme.layout == "headline":
            assert f"`{theme.id}`" in guidance, theme.id
    for kind in visuals.KINDS:
        assert f"`{kind}`" in guidance


@pytest.mark.parametrize(
    "phrase, limit",
    [
        ("labels at most {} characters", visuals.LIMITS["label"]),
        ("points at most {}", visuals.LIMITS["point"]),
        ("`caption` at most {}", visuals.LIMITS["caption"]),
        ("`value` at most {}", visuals.LIMITS["value"]),
        ("`label` at most {}", visuals.LIMITS["figure_label"]),
        ("`source` at most {}", visuals.LIMITS["source"]),
    ],
)
def test_the_prompts_limits_match_the_code(phrase, limit):
    assert phrase.format(limit) in FLAT


def _examples() -> list[dict]:
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", PROMPT, re.S)]


def _is_figure(data: dict) -> bool:
    return (data.get("visual") or {}).get("type") == "figure"


def test_each_example_card_is_a_card_the_gate_would_take():
    examples = [data for data in _examples() if not _is_figure(data)]
    assert {(data["layout"], (data.get("visual") or {}).get("type")) for data in examples} == {
        ("headline", "flow"), ("headline", "compare"), ("list", None),
    }
    for data in examples:
        spec, problems = render.CardSpec.parse(data, default_overline="Automation tip")
        assert not problems, problems
        result = brand_check.check(spec.body(), headings=spec.headings(), channel_name="social-card", sources=["https://www.example.com/a"])
        assert result.passed, result.reasons()


def test_no_example_card_carries_a_figure_a_run_could_copy():
    """A model copies what it sees. The figure example holds placeholders, and a run that left
    them in would be refused, because a figure is a number. No other example holds a number."""
    for data in _examples():
        assert not brand_check.figures_in(json.dumps(data)), data
    assert "%" not in "".join(re.findall(r"```json\n(.*?)```", PROMPT, re.S))
    placeholder = next(data for data in _examples() if _is_figure(data))
    _, problems = render.CardSpec.parse(placeholder)
    assert any("a figure is a number" in p for p in problems), problems


def test_the_prompt_names_every_kind_of_refusal_a_card_can_get():
    for phrase in ("card items", "`visual`", "`icon`", "two different sites"):
        assert phrase in FLAT


@pytest.mark.parametrize("text", [PROMPT, DOCS], ids=["prompt", "docs"])
def test_the_rule_the_checker_dropped_is_gone(text):
    """The checker no longer reads "were" as "we're", so the warning only put a figure in front of
    the run. A model copies what it sees."""
    assert '"were"' not in text and "86%" not in text


def test_a_concrete_example_reads_as_a_picture_and_never_as_a_client():
    assert 'Picture a clinic' in FLAT
    assert "never as something that happened to a real business or client" in FLAT


def test_item_titles_follow_the_headlines_rules():
    assert "Titles follow the headline's rules" in FLAT
    assert "`proper_nouns`: names the sentence-case check should accept in the headline and the item titles" in FLAT


@pytest.mark.parametrize("prompt", ["social.md", "scout.md", "community.md", "app-factory.md"])
def test_every_writing_prompt_says_a_digit_never_sits_beside_jura(prompt):
    text = re.sub(r"\s+", " ", (paths.REPO_ROOT / "prompts" / prompt).read_text(encoding="utf-8"))
    assert 'in a sentence that contains "we", "our", "us" or "Jura"' in text
    assert "not a date, a year or a compound" in text


def test_the_prompt_warns_of_the_other_ways_to_fail_the_gate():
    assert '"half", "twice" or "double"' in FLAT
    assert "reads as a web address" in FLAT


@pytest.mark.parametrize("text", [FLAT, re.sub(r"\s+", " ", DOCS)], ids=["prompt", "docs"])
def test_the_tie_is_described_as_the_code_applies_it(text):
    assert "in digits or in words" in text
