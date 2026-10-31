"""The picture on an image card (PRD PC1, PC2, as worded in reviews/functional.md §3).

`CardSpec.parse` and `visuals.parse` are the seam for what a card may hold, `build_html` for what
reaches the page, and `submit.submit` for what the brand check sees. Drawing them in Chrome is in
test_social_cards_real_chrome.py. The figures here are placeholders, and none reaches a live card.
"""

import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest
from click.testing import CliRunner

from jura_growth import paths
from jura_growth.agents.social import render, submit, visuals
from jura_growth.cli import cli
from test_social import IMDA, NEWS, SHEETS, TIP, env, write  # noqa: F401 - env is a fixture


def steps(count: int, icon: str = "mail") -> list[dict]:
    return [{"icon": icon, "label": f"Step {'abcdef'[i]}"} for i in range(count)]


def side(points: int = 2, icon: str = "clock", label: str = "Before") -> dict:
    return {"icon": icon, "label": label, "points": [f"Point {'abc'[i % 3]}" for i in range(points)]}


FLOW = {"type": "flow", "steps": steps(3)}
COMPARE = {"type": "compare", "left": side(), "right": side(label="After")}
FIGURE = {"type": "figure", "value": "11%", "label": "of the firms asked", "source": "IMDA"}


# --- what a visual may hold -----------------------------------------------------


@pytest.mark.parametrize(
    "visual",
    [
        FLOW,
        {**FLOW, "steps": steps(4)},
        COMPARE,
        {**COMPARE, "left": side(3), "right": side(3, label="After")},
        FIGURE,
        {**FIGURE, "value": "3.5x"},
    ],
)
def test_each_kind_at_its_sizes_parses(visual):
    parsed, problems = visuals.parse(visual)
    assert not problems and parsed.kind == visual["type"]


@pytest.mark.parametrize(
    "visual, reason",
    [
        ("a string", "must be an object"),
        ({"type": "photo"}, "visual.type must be one of flow, compare, figure"),
        ({"type": "flow", "steps": steps(2)}, "3 to 4 steps; found 2"),
        ({"type": "flow", "steps": steps(5)}, "3 to 4 steps; found 5"),
        ({"type": "flow"}, "3 to 4 steps; found 0"),
        ({"type": "flow", "steps": ["a", "b", "c"]}, "must be an object with an icon and a label"),
        ({"type": "flow", "steps": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}, "needs an icon"),
        ({"type": "flow", "steps": [{"icon": "mail"}] * 3}, "needs a label"),
        ({"type": "compare", "left": side(1), "right": side()}, "visual.left has 2 to 3 points; found 1"),
        ({"type": "compare", "left": side(), "right": side(4)}, "visual.right has 2 to 3 points; found 4"),
        ({"type": "compare", "left": side()}, "visual.right must be an object"),
        ({**FIGURE, "value": ""}, "a figure needs its value"),
        ({**FIGURE, "label": ""}, "a figure needs its label"),
        ({**FIGURE, "source": ""}, "a figure needs its source"),
        ({**FIGURE, "value": "a lot"}, "a figure is a number"),
        ({**FIGURE, "value": "1" * 13}, "keep it to 12"),
        ({**FIGURE, "caption": "x" * 61}, "keep it to 60"),
        ({"type": "flow", "steps": [{"icon": "mail", "label": "x" * 33}] * 3}, "keep it to 32"),
    ],
)
def test_what_a_visual_refuses(visual, reason):
    _, problems = visuals.parse(visual)
    assert any(reason in p for p in problems), problems


def test_a_visual_goes_on_the_headline_layout_only():
    _, problems = render.CardSpec.parse({"layout": "list", "headline": "A list", "items": ["One", "Two"], "visual": FLOW})
    assert any("headline layout" in p for p in problems)


# --- the ring -------------------------------------------------------------------


@pytest.mark.parametrize("rule", [".visual-caption", ".figure-source"])
def test_a_mono_caption_is_small_and_uppercase_as_the_design_system_says(rule):
    """`design-system/README.md`: IBM Plex Mono is "small and uppercase, never for reading"."""
    css = (Path(render.__file__).parent / "templates" / "card.css").read_text(encoding="utf-8")
    body = re.search(re.escape(rule) + r"\s*\{([^}]*)\}", css).group(1)
    assert "var(--font-mono)" in body and "text-transform: uppercase" in body


@pytest.mark.parametrize(
    "value, ring",
    [
        ("11%", True),
        ("0%", True),
        ("100%", True),
        ("99.5%", True),
        ("120%", False),  # no ring can be more than full
        ("99.99%", False),  # too long to sit inside one
        ("3.5x", False),
        ("11", False),
    ],
)
def test_a_percentage_draws_a_ring(value, ring):
    parsed, problems = visuals.parse({**FIGURE, "value": value})
    assert not problems
    assert ('class="ring"' in visuals.render(parsed)) is ring


def test_the_ring_fills_to_the_figure():
    parsed, _ = visuals.parse({**FIGURE, "value": "50%"})
    filled, whole = re.search(r'stroke-dasharray="([\d.]+) ([\d.]+)"', visuals.render(parsed)).groups()
    assert float(filled) == pytest.approx(float(whole) / 2, abs=0.01)


# --- icons ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["rocket", "Mail", " mail", "mail.svg", "../../etc/passwd", "../icons/mail", "", "MAIL"])
def test_an_icon_off_the_list_is_refused(name):
    assert visuals.icon_problem(name, "visual.steps[0].icon")


@pytest.mark.parametrize("field", ["steps", "item"])
def test_a_card_with_an_icon_off_the_list_is_refused(field):
    if field == "steps":
        data = {"layout": "headline", "headline": "A card", "visual": {"type": "flow", "steps": steps(3, icon="rocket")}}
    else:
        data = {"layout": "headline", "headline": "A card", "items": [{"title": "One", "detail": "D", "icon": "../mail"}]}
    _, problems = render.CardSpec.parse(data)
    assert any("not one of the icons" in p for p in problems), problems


def test_the_plan_lists_exactly_the_vendored_icons():
    names = visuals.icon_names()
    assert "mail" in names and "rocket" not in names
    assert names == sorted(path.stem for path in visuals.ICONS.glob("*.svg"))


@pytest.mark.parametrize("name", visuals.icon_names())
def test_each_vendored_icon_is_lucide_safe_and_at_the_design_systems_stroke(name):
    svg = visuals.icon_svg(name)
    root = ElementTree.fromstring(svg)
    assert root.tag.endswith("svg")
    assert root.get("stroke-width") == "1.75"
    assert root.get("stroke") == "currentColor" and root.get("fill") == "none"
    assert f"lucide-{name}" in root.get("class")
    every = list(root.iter())
    assert not {element.tag.rsplit("}", 1)[-1] for element in every} & {"script", "style", "foreignObject", "image", "use", "a"}
    for element in every:
        assert not [key for key in element.attrib if key.startswith("on") or key.endswith("href") or key == "style"], name


def test_the_icon_licence_is_vendored_with_them():
    assert "Lucide Contributors" in (visuals.ICONS / "LICENSE").read_text(encoding="utf-8")


# --- nothing a card says runs in the page ---------------------------------------------


BAD = '<img src=x onerror=alert(1)><script>alert(2)</script>"'
VISUAL_FIELDS = [
    lambda text: {"type": "flow", "caption": text, "steps": steps(3)},
    lambda text: {"type": "flow", "steps": [{"icon": "mail", "label": text}, *steps(2)]},
    lambda text: {"type": "compare", "left": {**side(), "label": text}, "right": side()},
    lambda text: {"type": "compare", "left": {**side(), "points": [text, "Point"]}, "right": side()},
    lambda text: {**FIGURE, "label": text},
    lambda text: {**FIGURE, "source": text[:40]},
]


@pytest.mark.parametrize("make", VISUAL_FIELDS)
def test_a_visuals_words_come_out_escaped(make):
    text = BAD[:30]  # short enough for every field's limit
    visual, _ = visuals.parse(make(text))
    page = visuals.render(visual)
    assert "<img" not in page and "<script" not in page and "&lt;" in page


def test_a_figures_value_comes_out_escaped():
    visual, _ = visuals.parse({**FIGURE, "value": "<b>1</b>"})
    assert "<b>" not in visuals.render(visual)


@pytest.mark.parametrize(
    "item",
    [
        {"title": BAD},
        {"title": "A title", "detail": BAD},
        {"title": "A title", "detail": "Plain", "source": BAD[:30]},
    ],
)
def test_a_slides_words_come_out_escaped(item):
    spec, _ = render.CardSpec.parse({"layout": "headline", "headline": "A card", "items": [item, {"title": "Another"}]})
    for slide in spec.slides(5):
        page = render.build_html(slide, 1080, 1350)
        assert "<img" not in page and "<script>alert" not in page


# --- every word on the picture reaches the brand check -----------------------------------


def _folder(card: dict, **changes):
    return write(paths.work_dir("social") / "2026-10-27", TIP, **{"card.json": json.dumps(card), **changes})


TIP_ITEMS = json.loads(TIP["card.json"])["items"]
BANNED_FIELDS = {
    "flow step": lambda word: {"type": "flow", "steps": [{"icon": "mail", "label": f"We {word} it"}, *steps(2)]},
    "flow caption": lambda word: {"type": "flow", "caption": f"How we {word} it", "steps": steps(3)},
    "compare label": lambda word: {"type": "compare", "left": {**side(), "label": f"We {word} it"}, "right": side()},
    "compare point": lambda word: {"type": "compare", "left": {**side(), "points": [f"We {word} it", "Point"]}, "right": side()},
    "compare right label": lambda word: {"type": "compare", "left": side(), "right": {**side(), "label": f"We {word} it"}},
    "compare right point": lambda word: {"type": "compare", "left": side(), "right": {**side(), "points": [f"We {word} it", "Point"]}},
}


@pytest.mark.parametrize("field", sorted(BANNED_FIELDS))
def test_a_buzzword_on_the_picture_fails_the_social_card_gate(env, conn, field):
    card = {"layout": "headline", "headline": "A plain headline", "items": TIP_ITEMS, "visual": BANNED_FIELDS[field]("leverage")}
    outcome = submit.submit(conn, _folder(card), offline=True)
    assert outcome.status == "retry" and "leverage" in outcome.text().lower(), outcome.text()
    assert "card: retry" in outcome.text()


@pytest.mark.parametrize("field", ["label", "source", "caption"])
def test_a_buzzword_in_a_figures_words_fails_the_social_card_gate(env, conn, field):
    sentence = "IMDA says 11% of the firms it asked tried this first."
    files = {
        "facebook.md": NEWS["facebook.md"].replace("Two AI updates worth knowing about this week.", sentence),
        "instagram.md": NEWS["instagram.md"].replace("Two AI updates worth knowing about this week.", sentence),
    }
    publisher = "Leverage Weekly" if field == "source" else "IMDA"
    sources = f"- {IMDA} | {publisher} | 2026-10-26 | A survey\n- {SHEETS} | Example News | 2026-10-26 | Sheets\n"
    words = {"label": "of the firms leverage this", "caption": "How firms leverage this", "source": publisher}
    visual = {**FIGURE, "source": publisher, field: words[field]}
    card = {"layout": "headline", "headline": "A plain headline", "items": TIP_ITEMS, "visual": visual}
    outcome = submit.submit(conn, _folder(card, **files, **{"sources.md": sources}), offline=True)
    assert outcome.status == "retry" and "card: retry" in outcome.text(), outcome.text()


def test_a_figures_value_reaches_the_social_card_gate(env, conn):
    sentence = "IMDA says 11% of the firms it asked tried this first."
    files = {
        "facebook.md": NEWS["facebook.md"].replace("Two AI updates worth knowing about this week.", sentence),
        "instagram.md": NEWS["instagram.md"].replace("Two AI updates worth knowing about this week.", sentence),
    }
    sources = f"- {IMDA} | IMDA | 2026-10-26 | A survey\n- {SHEETS} | Example News | 2026-10-26 | Sheets\n"
    card = {"layout": "headline", "headline": "A plain headline", "items": TIP_ITEMS, "visual": {**FIGURE, "value": "11%!"}}
    outcome = submit.submit(conn, _folder(card, **files, **{"sources.md": sources}), offline=True)
    assert outcome.status == "retry" and "card: retry" in outcome.text() and "exclamation" in outcome.text().lower(), outcome.text()


def test_a_link_or_a_hashtag_on_the_picture_fails(env, conn):
    visual = {"type": "flow", "steps": [{"icon": "mail", "label": "See example.com"}, {"icon": "mail", "label": "Read #this"}, *steps(1)]}
    card = {"layout": "headline", "headline": "A plain headline", "items": TIP_ITEMS, "visual": visual}
    outcome = submit.submit(conn, _folder(card), offline=True)
    assert outcome.status == "retry" and "card: retry" in outcome.text()
    assert "hashtag" in outcome.text()


def test_the_render_command_checks_a_visuals_words_too(env, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"layout": "headline", "headline": "A card", "visual": BANNED_FIELDS["flow step"]("leverage")}))
    result = CliRunner().invoke(cli, ["social", "render", str(spec), "--out", str(tmp_path / "o"), "--offline"])
    assert result.exit_code == 1 and "leverage" in result.output.lower()


# --- themes ------------------------------------------------------------------------------


def test_every_item_on_a_list_theme_needs_an_icon(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-26T07:05:00+08:00")
    card = json.loads(NEWS["card.json"])
    del card["items"][1]["icon"]
    outcome = submit.submit(conn, write(paths.work_dir("social") / "2026-10-26", NEWS, **{"card.json": json.dumps(card)}), offline=True)
    assert outcome.status == "invalid" and "`icon`" in outcome.text()


def test_a_headline_theme_needs_a_visual(env, conn):
    card = json.loads(TIP["card.json"])
    del card["visual"]
    outcome = submit.submit(conn, _folder(card), offline=True)
    assert outcome.status == "invalid" and "needs a `visual`" in outcome.text()


def test_a_list_theme_needs_no_visual(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-26T07:05:00+08:00")
    outcome = submit.submit(conn, write(paths.work_dir("social") / "2026-10-26", NEWS), offline=True)
    assert outcome.status == "delivered", outcome.text()


def test_a_list_card_draws_its_icons_and_a_slide_leads_with_its_icon(env):
    spec, problems = render.CardSpec.parse(json.loads(NEWS["card.json"]))
    assert not problems
    page = render.build_html(spec, 1080, 1350)
    assert page.count('class="tile"') == 2 and 'class="num"' not in page
    slide = spec.slides(5)[1]
    page = render.build_html(slide, 1080, 1350)
    assert "has-tile" in page and "lucide-landmark" in page


# --- tokens and rendering rules ------------------------------------------------------------


def _defined_in_design_system() -> set[str]:
    found: set[str] = set()
    for path in (render.design_system() / "tokens").glob("*.css"):
        found |= set(re.findall(r"(--[\w-]+)\s*:", path.read_text(encoding="utf-8")))
    return found


def test_every_variable_the_card_uses_is_defined():
    """A misspelt token draws as nothing, silently. A card's own names are set in `card.css`, or on
    the body by the templates."""
    css = (render.TEMPLATES / "card.css").read_text(encoding="utf-8")
    templates = "".join(path.read_text(encoding="utf-8") for path in render.TEMPLATES.glob("*.html"))
    own = set(re.findall(r"(--[\w-]+)\s*:", css + templates))
    used = set(re.findall(r"var\((--[\w-]+)", css))
    assert not used - own - _defined_in_design_system()


def test_the_icons_hold_no_raw_colour_either():
    for path in visuals.ICONS.glob("*.svg"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(", text), path.name


def test_a_render_in_the_suite_cannot_reach_the_network(monkeypatch, tmp_path):
    """Chrome is a subprocess, outside the network guard, so this rule is all that holds it."""
    import subprocess

    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    from jura_growth import images

    fake_chrome = tmp_path / "chrome"
    fake_chrome.write_text("#!/bin/sh\n")
    fake_chrome.chmod(0o755)
    images.run_chrome(["--version"], images.Chrome(fake_chrome), offline=True)
    assert "--host-resolver-rules=MAP * ~NOTFOUND" in seen["argv"]
