"""PC3: every card at both sizes in real Chrome, with nothing overflowing.

If Chrome isn't there, these fail (reviews/test-strategy.md §2). Every render here is
offline, so the Google web fonts don't load and the fallback fonts draw the cards. The same matrix
with the real fonts is a recorded check, because the suite stays off the network (PRD §4).

The words are prose at each field's limit, plus a long unbroken word where a field could hold one.
They carry no figure that could be mistaken for a result: this is a layout test, and nothing here
reaches a live card.
"""

from __future__ import annotations

import concurrent.futures

import pytest

from jura_growth.agents.social import render, visuals
from card_probe import FIT_FLOOR, probe, text_of

SIZES = [("facebook", 1200, 630), ("instagram", 1080, 1350)]
L = visuals.LIMITS
R = render.LIMITS
LONG_WORD = "Internationalisationsprogramme"  # 30 unbroken characters, under the label limit


def _step(icon: str, label: str) -> dict:
    return {"icon": icon, "label": label}


FULL = {"overline": text_of(R["overline"], first="Overline"), "headline": text_of(R["headline"]), "subtitle": text_of(R["subtitle"], first="What")}
SHORT = {"overline": "AI news", "headline": "A short headline", "subtitle": "A short line."}
ICONS = ["inbox", "search", "workflow", "send"]


def flow(count: int, *, label: str) -> dict:
    return {"type": "flow", "caption": text_of(L["caption"], first="How"), "steps": [_step(ICONS[i], label) for i in range(count)]}


def compare(points: int, *, point: str, label: str) -> dict:
    side = lambda icon: {"icon": icon, "label": label, "points": [point] * points}  # noqa: E731
    return {"type": "compare", "caption": text_of(L["caption"], first="What"), "left": side("clock"), "right": side("zap")}


def figure(value: str, *, label: str, source: str) -> dict:
    return {"type": "figure", "caption": text_of(L["caption"], first="What"), "value": value, "label": label, "source": source}


LABEL = text_of(L["label"], first="Step")
POINT = text_of(L["point"], first="Point")
FIG_LABEL = text_of(L["figure_label"], first="of")
FIG_SOURCE = text_of(L["source"], first="Source")
MANY_ITEMS = [
    {"title": text_of(R["item"], first="Item"), "detail": text_of(R["detail"], first="Detail"), "source": text_of(R["source"], first="Source"), "icon": ICONS[i % 4]}
    for i in range(5)
]

CASES = {
    "flow-3-short": {"layout": "headline", **SHORT, "visual": {"type": "flow", "steps": [_step(ICONS[i], "Step") for i in range(3)]}},
    "flow-3-full": {"layout": "headline", **FULL, "visual": flow(3, label=LABEL)},
    "flow-4-full": {"layout": "headline", **FULL, "visual": flow(4, label=LABEL)},
    "flow-4-long-word": {"layout": "headline", **FULL, "visual": flow(4, label=LONG_WORD)},
    "compare-2-short": {"layout": "headline", **SHORT, "visual": {
        "type": "compare", "left": {"icon": "clock", "label": "Before", "points": ["Slow", "By hand"]},
        "right": {"icon": "zap", "label": "After", "points": ["Quick", "On its own"]}}},
    "compare-2-full": {"layout": "headline", **FULL, "visual": compare(2, point=POINT, label=LABEL)},
    "compare-3-full": {"layout": "headline", **FULL, "visual": compare(3, point=POINT, label=LABEL)},
    "compare-3-long-word": {"layout": "headline", **FULL, "visual": compare(3, point=LONG_WORD, label=LONG_WORD)},
    "figure-ring-short": {"layout": "headline", **SHORT, "visual": {"type": "figure", "value": "50%", "label": "A sample", "source": "Sample"}},
    "figure-ring-full": {"layout": "headline", **FULL, "visual": figure("99.5%", label=FIG_LABEL, source=FIG_SOURCE)},
    "figure-ring-whole": {"layout": "headline", **FULL, "visual": figure("100%", label=FIG_LABEL, source=FIG_SOURCE)},
    "figure-no-ring-full": {"layout": "headline", **FULL, "visual": figure("000,000.00x", label=FIG_LABEL, source=FIG_SOURCE)},
    "list-2-short": {"layout": "list", **SHORT, "items": [{"title": "One thing", "icon": "mail"}, {"title": "Another thing", "icon": "phone"}]},
    "list-5-full": {"layout": "list", **FULL, "items": MANY_ITEMS},
    "list-5-no-icons": {"layout": "list", **FULL, "items": [{"title": item["title"]} for item in MANY_ITEMS]},
    "headline-only": {"layout": "headline", **FULL},
}


def _spec(data: dict) -> render.CardSpec:
    spec, problems = render.CardSpec.parse(data)
    assert not problems, problems
    return spec


def _slide() -> render.CardSpec:
    """The longest carousel slide: the last of five, every field full."""
    spec = _spec({"layout": "headline", **FULL, "items": MANY_ITEMS[:4], "visual": flow(3, label=LABEL)})
    return spec.slides(5)[-1]


def _cases() -> dict[str, render.CardSpec]:
    specs = {name: _spec(data) for name, data in CASES.items()}
    specs["slide-full"] = _slide()
    return specs


@pytest.fixture(scope="module")
def probes(tmp_path_factory):
    """All of them at once: each card takes three Chrome runs."""
    folder = tmp_path_factory.mktemp("cards")
    jobs = [(name, spec, size) for name, spec in _cases().items() for size in SIZES]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        running = {
            (name, size[0]): pool.submit(probe, spec, size[1], size[2], folder / f"{name}-{size[0]}.png")
            for name, spec, size in jobs
        }
        return {key: future.result() for key, future in running.items()}


@pytest.mark.parametrize("size", [size[0] for size in SIZES])
@pytest.mark.parametrize("name", [*CASES, "slide-full"])
def test_nothing_overflows_at_either_size(probes, name, size):
    result = probes[name, size]
    assert result.problems() == [], f"{name} at {size}, data-fit {result.fit}"


@pytest.mark.parametrize("name", ["flow-3-short", "compare-2-short", "figure-ring-short", "list-2-short"])
@pytest.mark.parametrize("size", [size[0] for size in SIZES])
def test_a_short_card_needs_no_shrinking(probes, name, size):
    assert probes[name, size].fit == 1


@pytest.mark.parametrize("size", [size[0] for size in SIZES])
def test_fit_measures_the_page_the_picture_gets(probes, size):
    """Chrome's window is shorter than the picture, in the pass `fit()` runs in, and the card's own
    height doesn't follow it. So what `fit()` measured is what gets drawn."""
    result = probes["flow-3-full", size]
    assert result.inner_height < result.height
    assert result.foot_top_first_pass == result.foot_top


@pytest.mark.parametrize("name", [*CASES, "slide-full"])
def test_type_stays_above_the_design_systems_minimum(probes, name):
    """The design system's smallest caption anywhere is 12px (README §4). Shrinking never takes
    a card's type below it, even at each field's limit."""
    for size in SIZES:
        assert probes[name, size[0]].smallest_type >= 12, (name, size[0])


def test_the_probes_floor_is_the_one_card_js_uses():
    assert f"scale > {FIT_FLOOR}" in (render.TEMPLATES / "card.js").read_text(encoding="utf-8")
