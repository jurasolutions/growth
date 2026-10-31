"""Social posts with more to read (PRD DP1 to DP5, as worded in reviews/functional.md §3).

Word ranges are read at the brand channels, with the theme a submit would pass. What a theme needs
from its sources and card is read through `submit.submit`, the highest seam, because a refusal has
to keep the day's regeneration. Screenshots are stubbed here (`env`); real Chrome is in
test_social_cards_real_chrome.py.
"""

import json

import pytest

from jura_growth import brand_check, config, db, paths, timeutil
from jura_growth.agents.social import checks, drafts, history, plan, submit
from jura_growth.agents.social.settings import load
from test_social import IMDA, NEWS, SHEETS, TIP, env, set_config, write  # noqa: F401 - env is a fixture

FRIDAY = "2026-10-30T07:05:00+08:00"
THURSDAY = "2026-10-29T07:05:00+08:00"
# Inside Instagram's default range and under the news theme's.
SHORT_CAPTION = NEWS["instagram.md"].replace("Two AI updates worth knowing about this week.\n\n", "")
TUESDAY_DAY = "2026-10-27"
SOURCES = f"- {IMDA} | IMDA | 2026-10-28 | IMDA opens a new SME AI programme\n- {SHEETS} | Example News | 2026-10-28 | Sheets adds formula suggestions\n"


# --- DP1: word ranges -----------------------------------------------------------


def words(platform: str, count: int) -> str:
    """Text of exactly `count` words for a platform, carrying the link its channel asks for."""
    tail = "Link in bio" if platform == "instagram" else "https://jurasolutions.sg"
    used = 3 if platform == "instagram" else 0
    text = " ".join(["invoice"] * (count - used)) + f" {tail}"
    assert checks.word_count(text) == count
    return text


def word_problem(platform: str, theme_id: str | None, count: int) -> list[str]:
    context = {"theme": {"id": theme_id}} if theme_id else {}
    result = brand_check.check(words(platform, count), channel_name=f"social-{platform}", context=context)
    return [issue.message for issue in result.issues if issue.rule == "channel" and "words here" in issue.message]


@pytest.mark.parametrize(
    "theme_id, platform, low, high",
    [
        ("ai-news", "facebook", 160, 280),
        ("ai-news", "instagram", 130, 240),
        ("ai-this-week", "facebook", 160, 280),
        ("ai-this-week", "instagram", 130, 240),
        ("ai-finding", "facebook", 160, 280),
        ("ai-finding", "instagram", 130, 240),
        ("ai-fun-facts", "facebook", 120, 220),
        ("ai-fun-facts", "instagram", 110, 200),
        ("ai-good-read", "facebook", 120, 220),
        ("ai-good-read", "instagram", 110, 200),
        ("automation-tip", "facebook", 120, 220),
        ("automation-tip", "instagram", 110, 200),
        ("from-the-toolbox", "facebook", 90, 180),
        ("from-the-toolbox", "instagram", 80, 160),
        (None, "facebook", 90, 180),
        (None, "instagram", 80, 160),
    ],
)
def test_each_theme_has_its_own_word_range_on_each_platform(theme_id, platform, low, high):
    assert word_problem(platform, theme_id, low - 1)
    assert not word_problem(platform, theme_id, low)
    assert not word_problem(platform, theme_id, high)
    assert word_problem(platform, theme_id, high + 1)


def test_the_default_settings_match_the_shipped_themes_and_platforms(monkeypatch):
    """A config with no themes or platforms section behaves as the shipped file does (N13)."""
    shipped = load()
    set_config(monkeypatch, themes=None, platforms=None)
    # A missing platforms section means the shipped switches go too, so compare what depth reads.
    defaults = load()
    for theme_id, theme in shipped.themes.items():
        assert defaults.themes[theme_id] == theme, theme_id
    for name in ("facebook", "instagram"):
        for key in ("words", "hashtags_max", "chars_max", "carousel_max"):
            assert getattr(defaults.platforms[name], key) == getattr(shipped.platforms[name], key), (name, key)


# --- N9: Instagram's limits -----------------------------------------------------


def test_instagram_takes_at_most_five_hashtags():
    five = words("instagram", 100) + "\n\n#One #Two #Three #Four #Five"
    six = five + " #Six"
    assert brand_check.check(five, channel_name="social-instagram").passed
    messages = [i.message for i in brand_check.check(six, channel_name="social-instagram").issues]
    assert any("at most 5 hashtags" in m for m in messages)


def test_an_instagram_caption_stops_at_2200_characters():
    tail = "\n\nLink in bio"
    fits = "x" * (2200 - len(tail)) + tail
    over = "x" * (2201 - len(tail)) + tail
    assert not _length_issues(fits)
    assert _length_issues(over)


def _length_issues(text: str) -> list[str]:
    result = brand_check.check(text, channel_name="social-instagram")
    return [i.message for i in result.issues if "characters" in i.message]


def test_facebook_has_no_character_ceiling():
    text = "x" * 3000 + " https://jurasolutions.sg"
    result = brand_check.check(text, channel_name="social-facebook")
    assert not [i.message for i in result.issues if "characters" in i.message]


# --- the submission, through submit -----------------------------------------------


def run(conn, folder, **kwargs):
    return submit.submit(conn, folder, offline=True, **kwargs)


ICONS = ["landmark", "file-check", "mail", "phone", "search"]
FLOW = {"type": "flow", "steps": [{"icon": "inbox", "label": "It comes in"}, {"icon": "search", "label": "It gets read"}, {"icon": "send", "label": "It goes out"}]}


def card_items(count: int, *, icons: bool = True, detail: bool = True) -> list[dict]:
    found = []
    for index in range(count):
        item = {"title": f"Point {'abcde'[index]} worth keeping", "source": "IMDA"}
        if detail:
            item["detail"] = "One or two plain sentences that say what changes for you."
        if icons:
            item["icon"] = ICONS[index]
        found.append(item)
    return found


def headline_card(items: int = 3, **changes) -> str:
    card = {"layout": "headline", "headline": "A plain headline about the story", "subtitle": "What changes for a small team.",
            "visual": FLOW, "items": card_items(items), **changes}
    return json.dumps({k: v for k, v in card.items() if v is not None})


def list_card(items: int = 3, **changes) -> str:
    card = {"layout": "list", "headline": "Three things worth a look", "subtitle": "What changed, and what it means.",
            "items": card_items(items), **changes}
    return json.dumps(card)


def submission(tmp_day: str, *, card: str, sources: str = SOURCES, **changes):
    return write(paths.work_dir("social") / tmp_day, NEWS, **{"sources.md": sources, "card.json": card, **changes})


def submissions(conn) -> int:
    return db.scalar(conn, "SELECT count(*) FROM social_submissions")


def test_ai_news_with_two_sources_on_two_hosts_is_delivered(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    outcome = run(conn, submission("2026-10-30", card=headline_card()))
    assert outcome.status == "delivered", outcome.text()


def test_ai_news_with_one_source_is_refused_and_keeps_the_regeneration(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    one = f"- {IMDA} | IMDA | 2026-10-28 | IMDA opens a new SME AI programme\n"
    outcome = run(conn, submission("2026-10-30", card=headline_card(), sources=one))
    assert outcome.status == "invalid" and outcome.exit_code == 2
    assert "at least 2 sources" in outcome.text() and "didn't use your regeneration" in outcome.text()
    assert submissions(conn) == 0


def test_ai_news_with_two_sources_on_one_host_is_refused(env, conn, monkeypatch):
    """Both pages sit on one site, with or without its www, so the second report isn't independent."""
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    same_site = SHEETS.replace("www.example.com", "example.com").replace("sheets-ai", "more-ai")
    both = f"- {SHEETS} | Example News | 2026-10-28 | One\n- {same_site} | Example News | 2026-10-28 | Two\n"
    outcome = run(conn, submission("2026-10-30", card=headline_card(), sources=both))
    assert outcome.status == "invalid" and "2 different sites" in outcome.text()
    assert submissions(conn) == 0


def test_a_query_string_does_not_make_a_second_host(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    first, second = "https://example.com?a=1", "https://www.example.com?a=2"
    both = f"- {first} | IMDA | 2026-10-28 | One\n- {second} | IMDA | 2026-10-28 | Two\n"
    facebook = NEWS["facebook.md"].replace(IMDA, first).replace(SHEETS, second)
    outcome = run(conn, submission("2026-10-30", card=headline_card(), sources=both, **{"facebook.md": facebook}))
    assert outcome.status == "invalid" and "found 1" in outcome.text(), outcome.text()


def test_a_subdomain_counts_as_another_host(env, conn, monkeypatch):
    """The PRD's word is hosts, and telling a company's blog from its site needs a list of public
    suffixes. Independence stays a prompt rule, and Ting Yu's eye on the card."""
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    first, second = "https://example.com/news", "https://blog.example.com/news"
    both = f"- {first} | Example News | 2026-10-28 | One\n- {second} | Example News | 2026-10-28 | Two\n"
    facebook = NEWS["facebook.md"].replace(IMDA, first).replace(SHEETS, second)
    card = json.loads(headline_card())
    for item in card["items"]:
        item["source"] = "Example News"
    outcome = run(conn, submission("2026-10-30", card=json.dumps(card), sources=both, **{"facebook.md": facebook}))
    assert outcome.status == "delivered", outcome.text()


def test_ai_news_takes_at_most_three_sources(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    four = "".join(f"- https://site{n}.example.com/a | IMDA | 2026-10-28 | Story\n" for n in range(4))
    outcome = run(conn, submission("2026-10-30", card=headline_card(), sources=four))
    assert outcome.status == "invalid" and "at most 3 sources; found 4" in outcome.text(), outcome.text()
    assert submissions(conn) == 0


def test_two_hosts_is_a_rule_for_ai_news_only(env, conn, monkeypatch):
    """`ai-this-week` may list two pages of one publisher."""
    settings = load()
    assert settings.theme("ai-news").min_hosts == 2
    assert settings.theme("ai-this-week").min_hosts == 0
    assert settings.theme("ai-finding").min_hosts == 0


MIN_ITEMS = [
    ("ai-news", 3, headline_card),
    ("ai-finding", 3, headline_card),
    ("ai-this-week", 2, list_card),
    ("ai-fun-facts", 3, list_card),
    ("ai-good-read", 2, headline_card),
    ("automation-tip", 2, headline_card),
]


def theme_folder(theme_id: str, card: str, day: str = "2026-10-28"):
    """Sources dated inside every theme's window; `ai-good-read` takes exactly one."""
    if theme_id == "ai-good-read":
        one = f"- {IMDA} | IMDA | 2026-10-26 | A long read\n"
        return write(paths.work_dir("social") / day, NEWS, **{"sources.md": one, "card.json": card, "facebook.md": NEWS["facebook.md"].replace(SHEETS, IMDA)})
    both = SOURCES.replace("2026-10-28", "2026-10-27")
    return write(paths.work_dir("social") / day, NEWS, **{"sources.md": both, "card.json": card})


@pytest.mark.parametrize("theme_id, count, card", MIN_ITEMS)
def test_each_theme_refuses_one_item_short_and_takes_its_minimum_on_any_day(env, conn, monkeypatch, theme_id, count, card):
    """A Wednesday, which is no carousel day: the theme alone gives Instagram its slides."""
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-28T07:05:00+08:00")
    one_bare = json.loads(card(count))
    del one_bare["items"][0]["detail"]
    short = run(conn, theme_folder(theme_id, json.dumps(one_bare)), theme_id=theme_id)
    assert short.status == "invalid" and f"at least {count} card items" in short.text(), short.text()
    assert submissions(conn) == 0
    outcome = run(conn, theme_folder(theme_id, card(count)), theme_id=theme_id)
    assert outcome.status == "delivered", outcome.text()
    names = [f.name for f in outcome.images["instagram"]]
    assert names == [f"instagram-{n}-of-{count + 1}-1080x1350.png" for n in range(1, count + 2)]
    assert [f.name for f in outcome.images["facebook"]] == ["facebook-1200x630.png"]


def test_on_a_tuesday_ai_news_goes_out_with_the_cover_first(env, conn):
    """Tuesday is no carousel day, and the cover is the card itself, then one slide per item."""
    both = SOURCES.replace("2026-10-28", "2026-10-26")
    outcome = run(conn, submission(TUESDAY_DAY, card=headline_card(), sources=both), theme_id="ai-news")
    assert outcome.status == "delivered", outcome.text()
    assert [f.name for f in outcome.images["instagram"]] == [f"instagram-{n}-of-4-1080x1350.png" for n in range(1, 5)]
    pages = [page for out, page in env["shots"] if out.name.startswith("instagram")]
    assert "A plain headline about the story" in pages[0] and "visual-flow" in pages[0]
    for number, page in enumerate(pages[1:], start=2):
        assert f"{number:02d} / 04" in page and f"Point {'abc'[number - 2]} worth keeping" in page
        assert "visual-flow" not in page and "has-tile" in page


@pytest.mark.parametrize("theme_id, count, card", MIN_ITEMS)
def test_an_item_with_no_icon_is_refused_on_every_theme(env, conn, monkeypatch, theme_id, count, card):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-28T07:05:00+08:00")
    one_bare = json.loads(card(count))
    del one_bare["items"][0]["icon"]
    outcome = run(conn, theme_folder(theme_id, json.dumps(one_bare)), theme_id=theme_id)
    assert outcome.status == "invalid" and "`icon`" in outcome.text(), outcome.text()
    assert submissions(conn) == 0


def test_items_with_no_detail_do_not_count(env, conn):
    card = json.dumps({"layout": "headline", "headline": "A plain headline about the story", "visual": FLOW,
                       "items": card_items(2, detail=False)})
    outcome = run(conn, write(paths.work_dir("social") / TUESDAY_DAY, TIP, **{"card.json": card}))
    assert outcome.status == "invalid" and "found 0" in outcome.text()


def test_a_list_of_five_items_gets_the_cover_and_four_slides(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-28T07:05:00+08:00")
    outcome = run(conn, theme_folder("ai-fun-facts", list_card(5)), theme_id="ai-fun-facts")
    assert outcome.status == "delivered", outcome.text()
    assert len(outcome.images["instagram"]) == 5


def test_from_the_toolbox_needs_no_items_and_one_image(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", "2026-10-28T07:05:00+08:00")
    url = "https://jurasolutions.sg/apps/quote-builder"
    facebook = NEWS["facebook.md"].replace(IMDA, url).replace(SHEETS, url)
    files = {**NEWS, "facebook.md": facebook, "sources.md": "", "card.json": json.dumps({"layout": "tool", "tool": "quote-builder"})}
    # 163 words sits inside the toolbox's default range, and 130 inside Instagram's.
    outcome = run(conn, write(paths.work_dir("social") / "2026-10-28", files))
    assert outcome.status == "delivered", outcome.text()
    assert [f.name for f in outcome.images["instagram"]] == ["instagram-1080x1350.png"]


# --- N8: no way around the picture or the carousel ----------------------------------


def test_a_card_cannot_turn_the_carousel_off_on_a_carousel_theme(env, conn):
    card = json.loads(TIP["card.json"])
    outcome = run(conn, write(paths.work_dir("social") / TUESDAY_DAY, TIP, **{"card.json": json.dumps({**card, "carousel": False})}))
    assert outcome.status == "invalid" and "carousel" in outcome.text()
    assert submissions(conn) == 0


def test_a_card_may_turn_the_weekday_carousel_off_on_the_toolbox_theme(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", THURSDAY)
    url = "https://jurasolutions.sg/apps/quote-builder"
    facebook = NEWS["facebook.md"].replace(IMDA, url).replace(SHEETS, url)
    card = json.dumps({"layout": "tool", "tool": "quote-builder", "carousel": False})
    files = {**NEWS, "facebook.md": facebook, "sources.md": "", "card.json": card}
    outcome = run(conn, write(paths.work_dir("social") / "2026-10-29", files), theme_id="from-the-toolbox")
    assert outcome.status == "delivered", outcome.text()


@pytest.mark.parametrize(
    "theme_id, card",
    [
        ("automation-tip", list_card(3)),  # a list has no diagram, so a headline theme can't use one
        ("ai-this-week", headline_card(3)),
        ("automation-tip", json.dumps({"layout": "tool", "tool": "quote-builder"})),
    ],
)
def test_a_card_must_use_its_themes_layout(env, conn, theme_id, card):
    outcome = run(conn, theme_folder(theme_id, card, TUESDAY_DAY), theme_id=theme_id)
    assert outcome.status == "invalid" and "layout" in outcome.text(), outcome.text()
    assert submissions(conn) == 0


# --- DP5: what uses the regeneration ------------------------------------------------


def test_a_word_miss_uses_the_regeneration(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    outcome = run(conn, submission("2026-10-30", card=headline_card(), **{"instagram.md": SHORT_CAPTION}))
    assert outcome.status == "retry" and "attempt 1 of 2" in outcome.text() and "130–240 words" in outcome.text()
    assert submissions(conn) == 1


def test_a_shortfall_then_a_word_miss_then_a_pass(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    short = run(conn, submission("2026-10-30", card=headline_card(2)))
    assert short.status == "invalid" and submissions(conn) == 0
    miss = run(conn, submission("2026-10-30", card=headline_card(), **{"instagram.md": SHORT_CAPTION}))
    assert miss.status == "retry" and submissions(conn) == 1
    final = run(conn, submission("2026-10-30", card=headline_card()))
    assert final.status == "delivered", final.text()
    assert submissions(conn) == 2
    assert history.gated_attempts(conn, timeutil.today()) == 2


# --- what the run is told -------------------------------------------------------------


def test_the_plan_prints_each_themes_own_ranges_and_needs(env, conn, monkeypatch):
    monkeypatch.setenv("JURA_GROWTH_NOW", FRIDAY)
    set_config(monkeypatch, rhythm=config.agent_config("social")["rhythm"])
    text = plan.render_text(plan.build(conn, timeutil.today()))
    assert "Theme: ai-news" in text
    assert "facebook 160–280, instagram 130–240" in text
    assert "at least 3, one Instagram slide each" in text and "2 different sites" in text
    # A fallback's needs are printed beside it, so taking one doesn't cost the regeneration.
    good_read = next(line for line in text.splitlines() if line.strip().startswith("ai-good-read:"))
    assert "facebook 120–220, instagram 110–200" in good_read and "at least 2" in good_read
    assert "up to 5 hashtags" in text and "2200 characters" in text


def test_theme_problems_names_nothing_for_a_clean_submission(tmp_path):
    settings = load()
    theme = settings.theme("automation-tip")
    write(tmp_path, TIP)
    sub = drafts.load(tmp_path, ["facebook", "instagram"], theme=theme)
    assert not sub.problems
    assert drafts.theme_problems(sub, theme, timeutil.today()) == []

