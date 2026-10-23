"""Image cards rendered by real headless Chrome, checked by reading each PNG's
header. Skipped when Chrome isn't installed.

Rendered offline (Chrome's host resolver is switched off), so the tests never
touch the network: the Google web fonts don't load and the cards use the
fallback fonts, which doesn't change their size.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from jura_growth.agents.social import render
from jura_growth.cli import cli

pytestmark = pytest.mark.skipif(render.chrome_path() is None, reason="Google Chrome is not installed")

PLATFORM_SIZES = [("linkedin", 1200, 627), ("facebook", 1200, 630), ("instagram", 1080, 1350)]

SPECS = {
    "headline": {
        "layout": "headline",
        "overline": "Automation tip",
        "headline": "Let your accounting software send the first invoice reminder",
        "subtitle": "Write the message once. It goes out for every unpaid invoice.",
    },
    "list": {
        "layout": "list",
        "overline": "AI this week",
        "headline": "Two AI updates worth a look this week",
        "subtitle": "What changed, and what it means for a small team.",
        "items": [
            {"title": "IMDA opens a programme for smaller firms trying AI", "detail": "It starts with documents.", "source": "IMDA"},
            {"title": "Sheets suggests formulas from a plain sentence", "detail": "Describe the sum you want.", "source": "Example News"},
        ],
    },
    "tool": {"layout": "tool", "overline": "From the toolbox", "tool": "quote-builder"},
}


@pytest.fixture
def site(tmp_path, monkeypatch):
    folder = tmp_path / "site" / "src" / "apps"
    folder.mkdir(parents=True)
    (folder / "registry.json").write_text(
        json.dumps(
            [{"slug": "quote-builder", "name": "Quote builder", "description": "Turn a job into a clean PDF quote in a few minutes.",
              "category": "Sales", "tier": "browser", "status": "live", "added": "2026-10-20", "prd": "APP-001"}]
        )
    )
    monkeypatch.setenv("JURA_SITE_REPO", str(tmp_path / "site"))


def test_png_size_reads_the_header(tmp_path):
    not_png = tmp_path / "x.png"
    not_png.write_bytes(b"GIF89a" + b"\0" * 30)
    with pytest.raises(render.RenderError):
        render.png_size(not_png)


@pytest.mark.parametrize("layout", sorted(SPECS))
def test_each_layout_at_each_platform_size(layout, site, tmp_path):
    spec, problems = render.CardSpec.parse(SPECS[layout])
    assert not problems
    made = render.render_spec(spec, PLATFORM_SIZES, tmp_path / "out", offline=True)
    for name, width, height in PLATFORM_SIZES:
        assert len(made[name]) == 1
        assert render.png_size(made[name][0]) == (width, height)


def test_instagram_carousel(site, tmp_path):
    spec, _ = render.CardSpec.parse(SPECS["list"])
    made = render.render_spec(spec, [("instagram", 1080, 1350)], tmp_path / "out", carousel={"instagram": 5}, offline=True)
    files = made["instagram"]
    assert [f.name for f in files] == [f"instagram-{n}-of-3-1080x1350.png" for n in (1, 2, 3)]
    assert all(render.png_size(f) == (1080, 1350) for f in files)


def test_setup_images(tmp_path):
    made = render.render_setup(tmp_path / "setup", offline=True)
    sizes = {f.name: render.png_size(f) for f in made}
    assert sizes == {
        "profile-1080x1080.png": (1080, 1080),
        "profile-green-1080x1080.png": (1080, 1080),
        "linkedin-cover-1128x191.png": (1128, 191),
        "facebook-cover-1640x624.png": (1640, 624),
    }


def test_render_command_checks_the_words_first(site, tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"layout": "headline", "headline": "Send it now!"}))
    result = CliRunner().invoke(cli, ["social", "render", str(spec), "--out", str(tmp_path / "o"), "--offline"])
    assert result.exit_code == 1 and "exclamation" in result.output
    spec.write_text(json.dumps(SPECS["headline"]))
    result = CliRunner().invoke(
        cli, ["social", "render", str(spec), "--out", str(tmp_path / "o"), "--size", "linkedin", "--size", "600x600", "--offline"]
    )
    assert result.exit_code == 0, result.output
    assert "1200×627" in result.output and "600×600" in result.output


def test_templates_use_design_system_tokens_only():
    """No raw colour values in the card templates: every colour is a token."""
    import re

    for path in render.TEMPLATES.iterdir():
        if path.suffix in (".css", ".html"):
            text = path.read_text()
            assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), path.name
            assert not re.search(r"\brgba?\(", text), path.name
    page = render.build_html(render.CardSpec(layout="headline", headline="A card"), 1200, 627)
    assert (render.design_system() / "styles.css").as_uri() in page
    assert 'aria-label="Jura Solutions"' in page  # the design system's own logo asset, inlined
