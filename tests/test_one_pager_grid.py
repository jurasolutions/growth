"""The one-pager's 14-day grid PNG (MC §5.4 item 7; X14; ticket MC-09).

The grid is an HTML page built from a `mission.Snapshot` on design-system tokens, rendered by
real headless Chrome through the core helper in `jura_growth/images.py` (moved out of the social
agent, ticket review T6). The HTML is checked before rendering; the PNG by reading its header.
Rendered offline (Chrome's host resolver is switched off), so nothing reaches the network.
"""

from __future__ import annotations

import html as html_mod
import re

import pytest

import fortnight
import mission_world as world
from jura_growth import images, mission, one_pager, paths, slots

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


# --- the grid page (X14, checked on the HTML before rendering) --------------------------------

FORTNIGHT_NOW = "2026-11-10T11:05:00+08:00"
TOKENS = images.design_system() / "tokens"


@pytest.fixture
def snapshot(conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FORTNIGHT_NOW)
    world.load_fortnight(conn)
    return mission.read(world.source(FORTNIGHT_NOW))


def cells(page: str) -> list[dict]:
    """Each grid cell: its job, day, status and the text it shows."""
    found = []
    for match in re.finditer(r'<td class="cell[^"]*" data-job="([^"]*)" data-day="([^"]*)" data-status="([^"]*)">(.*?)</td>', page, re.S):
        job, day, status, inner = match.groups()
        found.append({"job": html_mod.unescape(job), "day": day, "status": status,
                      "text": " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", inner)).split())})
    return found


def visible(page: str) -> str:
    return " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def test_one_cell_per_job_per_day(snapshot):
    found = cells(one_pager.grid_html(snapshot))
    assert len(found) == len(fortnight.JOBS) * 14
    assert {(c["job"], c["day"]) for c in found} == {(job, day.isoformat()) for job in fortnight.JOBS for day in snapshot.days}


def test_scout_send_and_publish_collapse_to_one_cell_with_the_worst_status_and_its_count(snapshot):
    today = {c["job"]: c for c in cells(one_pager.grid_html(snapshot)) if c["day"] == "2026-11-10"}
    # 43 scout-send slots today: 2 missed, 7 ok, 1 skipped, 33 upcoming (MC-08's Today line).
    assert (today["scout-send"]["status"], today["scout-send"]["text"]) == ("missed", "Miss 2")
    assert today["publish"]["status"] == "ok" and today["publish"]["text"] == "OK 7"
    assert (today["app-factory"]["status"], today["app-factory"]["text"]) == ("ok", "OK")  # one slot: no count
    assert (today["community"]["status"], today["community"]["text"]) == ("none", one_pager.GRID_NO_SLOT)


def test_every_status_shows_as_text_as_well_as_colour(snapshot):
    found = cells(one_pager.grid_html(snapshot))
    statuses = {c["status"] for c in found}
    assert set(slots.WORST_FIRST) <= statuses, set(slots.WORST_FIRST) - statuses  # the fortnight has every status
    for cell in found:
        if cell["status"] == "none":
            assert cell["text"] == one_pager.GRID_NO_SLOT
        else:
            assert cell["text"].split()[0] == one_pager.GRID_LABELS[cell["status"]][0], cell
    labels = [one_pager.GRID_LABELS[status][0] for status in slots.WORST_FIRST]
    assert len(set(labels)) == len(labels), "two statuses share a label"


def test_the_legend_names_every_status_with_its_label(snapshot):
    page = one_pager.grid_html(snapshot)
    legend = visible(page.split('<footer class="legend"', 1)[1])
    for status in slots.WORST_FIRST:
        label, meaning = one_pager.GRID_LABELS[status]
        assert f"{label} {meaning}" in legend, status
    assert f"{one_pager.GRID_NO_SLOT} no slot that day" in legend


def _defined_tokens() -> set[str]:
    return {name for path in TOKENS.glob("*.css") for name in re.findall(r"(--[\w-]+)\s*:", path.read_text(encoding="utf-8"))}


def test_the_grid_uses_design_system_tokens_only(snapshot):
    page = one_pager.grid_html(snapshot)
    assert (images.design_system() / "styles.css").as_uri() in page
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", page), "a raw hex colour"
    assert not re.search(r"\b(rgba?|hsla?)\(", page), "a raw colour function"
    used = set(re.findall(r"var\((--[\w-]+)\)", page))
    assert used and used <= _defined_tokens(), used - _defined_tokens()
    families = re.findall(r"font-family\s*:\s*([^;}\"]+)", page)
    assert families and all(family.strip().startswith("var(--font-") for family in families), families
    assert "<script" not in page and "lucide" not in page.lower()  # no second icon set


def test_the_header_says_what_the_grid_covers(snapshot):
    assert "14 days to Tue 10 Nov, as of 11:05 SGT" in visible(one_pager.grid_html(snapshot))


def test_without_a_database_the_grid_says_so(monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-11-10T08:00:00+08:00")
    page = one_pager.grid_html(mission.read(world.source()))
    assert cells(page) == []
    assert "Nothing recorded yet: growth.db doesn't exist" in visible(page)


# --- the PNG (X14), through the core helper and real Chrome ---------------------------------------


@needs_chrome
def test_the_grid_png_is_a_valid_png_of_the_expected_size(snapshot):
    out = one_pager.render_grid(snapshot, paths.data_dir() / "grid.png", chrome=images.Chrome(CHROME), offline=True)
    width, height = one_pager.grid_size(snapshot)
    assert images.png_size(out) == (width, height)
    assert width == one_pager.GRID_WIDTH and height > 400
    assert images.pixels_only(out.read_bytes()) is not None
