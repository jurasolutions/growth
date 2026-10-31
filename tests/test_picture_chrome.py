"""The morning picture in real Chrome (seam P; MB1, MB2, MB3, MB5, MB8, MB9).

Offline: Chrome's host resolver is off, so the design system's web fonts don't load and the
fallback fonts are what is proved here. QA records the same oracle with the real fonts
(`tests/picture_chrome.py --live-fonts`).
"""

from __future__ import annotations

from datetime import datetime
from functools import cache

import pytest

import picture_chrome as oracle
import picture_world as world
from jura_growth import agents, health, images, mission, paths, picture
from jura_growth.timeutil import SGT
from test_scout_support import buttons, configure, live_ready, scout_env  # noqa: F401

CHROME_PATH = images.chrome_path(images.DEFAULT_CHROME)
needs_chrome = pytest.mark.skipif(CHROME_PATH is None, reason="Google Chrome is not installed")
CHROME = images.Chrome(images.DEFAULT_CHROME)

pytestmark = needs_chrome


def hidden(snapshot: mission.Snapshot) -> tuple[int, int]:
    return (max(0, len(picture.waiting(snapshot)) - picture.DECIDE_SHOWN), max(0, len(picture.fixes(snapshot)) - picture.FIX_SHOWN))


@cache
def inspected(name: str) -> dict:
    return oracle.inspect(picture.html(world.FIXTURES[name]()), chrome=CHROME)


# --- measure, then shoot -------------------------------------------------------------------------


def test_measure_height_follows_the_content_and_not_the_window():
    short = images.measure_height('<main class="page" style="height:300px"></main>', 1200, chrome=CHROME, offline=True)
    tall = images.measure_height('<body><main class="page" style="height:2100px"></main></body>', 1200, chrome=CHROME, offline=True)
    assert (short, tall) == (300, 2100)


def test_measure_height_rounds_up_so_nothing_is_cut():
    assert images.measure_height('<main class="page" style="height:300.2px"></main>', 1200, chrome=CHROME, offline=True) == 301


def test_a_missing_chrome_is_a_render_error_when_measuring(tmp_path, monkeypatch):
    monkeypatch.delenv("JURA_GROWTH_CHROME", raising=False)
    with pytest.raises(images.RenderError, match="Chrome not found"):
        images.measure_height("<p>x</p>", 1200, chrome=images.Chrome(tmp_path / "nowhere"), offline=True)


def test_text_on_the_page_cant_pass_for_the_measure():
    page = picture.html(world.snap(approvals=(world.request(1, reason='<html data-measured-height="9">'),)))
    assert images.measure_height(page, picture.WIDTH, chrome=CHROME, offline=True) > 9


# --- the oracle on every fixture (MB2, MB5) ------------------------------------------------------


@pytest.mark.parametrize("name", list(world.FIXTURES))
def test_the_page_holds_together(name):
    snapshot = world.FIXTURES[name]()
    png = picture.render(snapshot, paths.data_dir() / f"{name}.png", chrome=CHROME, offline=True)
    measured = images.measure_height(picture.html(snapshot), picture.WIDTH, chrome=CHROME, offline=True)
    assert oracle.problems(inspected(name), png=png, measured=measured, hidden=hidden(snapshot)) == []
    assert images.png_size(png) == (1200, inspected(name)["height"])


@pytest.mark.parametrize("cause", list(world.health_pages()))
def test_each_real_fix_wording_fits_its_row_whole(cause):
    """MB3, S1: one row, at most 3 lines, with nothing cut."""
    snapshot = world.health_pages()[cause]
    found = oracle.inspect(picture.html(snapshot), chrome=CHROME)
    assert oracle.problems(found, hidden=hidden(snapshot)) == []
    assert found["fixRows"], "the fixture says nothing to fix"
    for row in found["fixRows"]:
        assert row["lines"] <= 3 and not row["cut"], row


def test_the_worst_case_says_how_many_more_and_stays_under_the_maximum():
    found = inspected("worst")
    assert found["more"] == ["and 46 more", "and 16 more"]
    assert found["height"] <= picture.MAX_HEIGHT == 1600


def test_a_quiet_day_has_no_large_blank_area():
    assert inspected("quiet")["height"] < 1000
    assert inspected("quiet")["gapAboveFooter"] <= oracle.LARGEST_GAP


def test_every_font_is_at_least_21_px_in_every_fixture():
    for name in world.FIXTURES:
        assert min(size for size, _ in inspected(name)["fontSizes"]) >= 21, name


def test_over_the_maximum_it_refuses_rather_than_clip(monkeypatch):
    monkeypatch.setattr(picture, "MAX_HEIGHT", 500)
    out = paths.data_dir() / "too-tall.png"
    with pytest.raises(images.RenderError, match="over the 500 px maximum"):
        picture.render(world.typical(), out, chrome=CHROME, offline=True)
    assert not out.exists()


# --- the reading order (MB1, MB3) ----------------------------------------------------------------


def test_the_verdict_is_the_first_text_on_the_picture():
    assert inspected("typical")["first"] == picture.verdict(world.typical())


def test_the_sections_appear_in_the_order_ting_yu_acts_on_them():
    assert inspected("typical")["order"] == ["Decide in #approvals", "Fix", "This morning", "Yesterday", "Later today"]


def test_the_agent_rows_appear_in_order():
    texts = inspected("typical")["texts"]
    assert [t for t in texts if t in world.JOBS] == list(world.JOBS)


# --- final B1, issue 04: real wordings built through the real checks -------------------------------


def _problem(kind: str, monkeypatch) -> None:
    """Make one real `send.live_problems()` wording the first problem."""
    live = dict(mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg")
    if kind == "buttons":
        buttons(monkeypatch, False)
    elif kind == "legal":
        configure(monkeypatch, **{**live, "legal_review_done": False})
    elif kind == "domain unset":
        configure(monkeypatch, **{**live, "sending_domain": ""})
    elif kind == "domain wrong":
        configure(monkeypatch, **{**live, "sending_domain": "example.com"})
    elif kind == "resend":
        monkeypatch.delenv("RESEND_API_KEY_OUTREACH")
    elif kind == "unsubscribe":
        monkeypatch.delenv("UNSUBSCRIBE_SECRET")
    elif kind == "do-not-contact":
        (paths.inputs_dir() / "do-not-contact.csv").unlink()
    elif kind == "d1":
        monkeypatch.delenv("D1_DATABASE_ID")


def _fix_rows(**fields) -> list[dict]:
    base = dict(slots=world.morning(), morning=world.figures(), yesterday=world.figures(), approvals=())
    return oracle.inspect(picture.html(world.snap(**{**base, **fields})), chrome=CHROME)["fixRows"]


@pytest.mark.parametrize("kind", ["buttons", "legal", "domain unset", "domain wrong", "resend", "unsubscribe", "do-not-contact", "d1"])
def test_each_real_line_about_live_outreach_fits_its_fix_row_whole(conn, scout_env, monkeypatch, kind):
    live_ready(monkeypatch)
    _problem(kind, monkeypatch)
    module = next(m for m in agents.plugins() if getattr(m, "NAME", "") == "outreach")
    lines = module.health(conn)
    assert len(lines) == 1, lines
    (row,) = _fix_rows(plugin_lines=tuple(lines))
    assert not row["cut"], f"the picture cuts {lines[0]!r}"
    assert row["text"].startswith("Run jura-growth outreach status")
    assert "\n" in lines[0], "the message and the long text carry what to clear"


def test_every_unset_setting_is_named_on_its_fix_row(conn):
    gaps = tuple(gap for gap in health.setup_gaps() if gap.of is None)
    assert len(gaps) >= 6
    (row,) = _fix_rows(gaps=gaps)
    assert not row["cut"], f"the picture cuts {row['text']!r}"


# --- hostile text (MB8) --------------------------------------------------------------------------

HOSTILE = "<img src=x onerror=alert(1)><script>alert(2)</script>`<b>`<iframe src=x></iframe>"


def test_hostile_text_is_only_ever_text_through_every_route():
    snapshot = world.snap(
        slots={**world.morning(scout_research="skipped", community="ok"),
               ("scout-research", world.NOW.date()): [world.slot("scout-research", "skipped", reason=HOSTILE)]},
        morning=world.figures(app_prd_today=HOSTILE, outreach_mode=HOSTILE),
        yesterday=world.figures(),
        approvals=(world.request(1, reason=HOSTILE), world.request(2, HOSTILE)),
        paused=((HOSTILE, HOSTILE),),
        pause_file=HOSTILE,
        failures=(mission.Failure(HOSTILE, datetime(2026, 11, 10, 7, 0, tzinfo=SGT), HOSTILE),),
        plugin_lines=(HOSTILE,),
        broken=(HOSTILE,),
    )
    found = oracle.inspect(picture.html(snapshot), chrome=CHROME)
    assert found["elements"] == []


# --- the saved page (MB9) ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["typical", "worst"])
def test_the_page_scrolls_to_its_footer_in_a_small_window(name):
    found = oracle.scroll(picture.html(world.FIXTURES[name]()), chrome=CHROME)
    assert found["moved"] > 0 and found["bottom"] <= found["inner"] + 1


def test_the_page_holds_no_script():
    for build in (*world.FIXTURES.values(), *[lambda s=s: s for s in world.health_pages().values()]):
        assert "<script" not in picture.html(build())
