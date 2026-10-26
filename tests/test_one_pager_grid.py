"""The one-pager's 14-day grid PNG (MC §5.4 item 7; X14; ticket MC-09).

The grid is an HTML page built from a `mission.Snapshot` on design-system tokens, rendered by
real headless Chrome through the core helper in `jura_growth/images.py` (moved out of the social
agent, ticket review T6). The HTML is checked before rendering; the PNG by reading its header.
Rendered offline (Chrome's host resolver is switched off), so nothing reaches the network.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from jura_growth import images, paths
from jura_growth.timeutil import SGT

CHROME = images.chrome_path(images.DEFAULT_CHROME)
needs_chrome = pytest.mark.skipif(CHROME is None, reason="Google Chrome is not installed")


# --- the core render helper (T6) ----------------------------------------------------------


def test_the_core_and_the_one_pager_import_no_agent():
    for module in ("one_pager.py", "images.py"):
        text = (paths.REPO_ROOT / "jura_growth" / module).read_text(encoding="utf-8")
        assert "jura_growth.agents." not in text, module
        imports = [line for line in text.splitlines() if line.startswith(("import ", "from "))]
        assert not [line for line in imports if "agents" in line], module


def test_chrome_path_takes_the_path_it_is_given(tmp_path, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_CHROME", raising=False)
    assert images.chrome_path(tmp_path / "no-chrome-here") is None
    fake = tmp_path / "chrome"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert images.chrome_path(fake) == fake


def test_a_missing_chrome_is_a_render_error(tmp_path, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_CHROME", raising=False)
    with pytest.raises(images.RenderError, match="Chrome not found"):
        images.screenshot("<p>x</p>", paths.data_dir() / "x.png", 100, 100,
                          chrome=images.Chrome(tmp_path / "nowhere"), offline=True)


@needs_chrome
def test_the_core_helper_renders_a_png_of_the_size_asked(monkeypatch):
    out = images.screenshot(f'<link rel="stylesheet" href="{(images.design_system() / "styles.css").as_uri()}"><p>Hello</p>',
                            paths.data_dir() / "hello.png", 320, 200, chrome=images.Chrome(CHROME), offline=True)
    assert images.png_size(out) == (320, 200)
