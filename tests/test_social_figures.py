"""A figure on a picture is tied to the post (technical B5, functional S1, test strategy R2).

The numbers rule lets a figure through once a post has any third-party source, so these checks hold
the card to what the post and its sources state: a figure's value appears in every variant, and
its source is the publisher on a line of `sources.md`. Neither proves the figure true. Ting Yu reads
both on the approval card.

Every figure in this file is a placeholder for a test, and no fixture here reaches a live card.
"""

import json
from datetime import date

import pytest

from jura_growth import paths
from jura_growth.agents.social import drafts, submit
from jura_growth.agents.social.settings import load
from test_social import IMDA, NEWS, SHEETS, env, write  # noqa: F401 - env is a fixture

DAY = "2026-10-27"  # the `env` fixture's Tuesday, pinned to `automation-tip`
SOURCES = f"- {IMDA} | IMDA | 2026-10-26 | A survey of smaller firms\n- {SHEETS} | Example News | 2026-10-26 | Sheets adds suggestions\n"
ITEMS = [
    {"title": "Read the survey yourself", "detail": "It asks smaller firms what they tried first.", "icon": "search", "source": "IMDA"},
    {"title": "Start with one task", "detail": "Pick the job your team repeats most often.", "icon": "list-checks"},
]
PERCENT = "11%"


def variants(value: str = PERCENT) -> dict:
    sentence = f"IMDA says {value} of the firms it asked tried this first."
    return {
        "facebook.md": NEWS["facebook.md"].replace("Two AI updates worth knowing about this week.", sentence),
        "instagram.md": NEWS["instagram.md"].replace("Two AI updates worth knowing about this week.", sentence),
    }


def figure(**changes) -> dict:
    return {"type": "figure", "value": PERCENT, "label": "of the firms asked tried this first", "source": "IMDA", **changes}


def flow(*labels) -> dict:
    icons = ["inbox", "search", "send", "check"]
    return {"type": "flow", "steps": [{"icon": icons[i], "label": label} for i, label in enumerate(labels)]}


def card(visual, *, items=ITEMS, **changes) -> str:
    return json.dumps({"layout": "headline", "headline": "A plain headline about the survey", "visual": visual, "items": items, **changes})


def folder(spec: str, **changes):
    files = {**NEWS, **variants(), "sources.md": SOURCES, "card.json": spec, **changes}
    return write(paths.work_dir("social") / DAY, files)


def run(conn, where):
    return submit.submit(conn, where, offline=True)


def test_a_figure_stated_in_every_post_and_named_in_the_sources_is_delivered(env, conn):
    outcome = run(conn, folder(card(figure())))
    assert outcome.status == "delivered", outcome.text()
    page = env["shots"][0][1]
    assert PERCENT in page and "Source: IMDA" in page


@pytest.mark.parametrize(
    "visual, reason",
    [
        (figure(source=""), "a figure needs its source"),
        (figure(source="Gartner"), 'source "Gartner"'),
        (figure(source="sources"), 'source "sources"'),  # a word in a title is no publisher
        (figure(value="many"), "a figure is a number"),
    ],
)
def test_a_figure_with_no_real_source_is_refused(env, conn, visual, reason):
    outcome = run(conn, folder(card(visual)))
    assert outcome.status == "invalid" and reason in outcome.text(), outcome.text()
    assert "didn't use your regeneration" in outcome.text()


def test_a_figure_on_a_post_with_no_sources_is_refused(env, conn):
    files = {"sources.md": ""}
    outcome = run(conn, folder(card(figure()), **files))
    assert outcome.status == "invalid" and 'source "IMDA"' in outcome.text(), outcome.text()


@pytest.mark.parametrize("platform", ["facebook", "instagram"])
def test_a_figure_missing_from_one_variant_is_refused(env, conn, platform):
    other = {f"{platform}.md": variants()[f"{platform}.md"].replace(PERCENT, "some")}
    outcome = run(conn, folder(card(figure()), **other))
    assert outcome.status == "invalid" and f'{platform}.md' in outcome.text() and PERCENT in outcome.text(), outcome.text()


@pytest.mark.parametrize(
    "value, post, states",
    [
        ("11%", "IMDA says 11% of firms.", True),
        ("11%", "IMDA says 11%.", True),
        ("11%", "IMDA says 111% of firms.", False),  # the digits of another figure
        ("1%", "IMDA says 11% of firms.", False),
        ("3.5", "It took 3.5 days.", True),
        ("3", "It took 3.5 days.", False),
        ("3.5x", "It is 3.5x as fast.", True),
        ("11", "IMDA says 11% of firms.", False),
        # A date, a clock time, a link or a hashtag states no figure.
        ("31", "It was released on 31 October.", False),
        ("45", "It went live at 10:45.", False),
        ("62", "Read it at https://x.example/news/62/flow today.", False),
        ("62", "See #62 for more.", False),
        ("26", "Dated 2026-10-26.", False),
        # Worded the same way, however it is punctuated.
        ("1950s", "It began in the 1950s.", True),
        ("5G", "It runs on 5G.", True),
        ("3D", "It prints in 3D.", True),
        ("2nd", "It is the 2nd version.", True),
        ("3,", "Pick 3, then test them.", True),
        ("1,000", "Over 1,000, mostly small firms.", True),
        ("62%", "It says 62%, and it is new.", True),
        ("62-percent", "A 62 percent drop.", True),
        ("forty", "Forty firms tried it.", True),
        ("Nine in ten", "Nine in ten firms tried it.", True),
        ("Nine in ten", "Most firms tried it.", False),
        # A value the reader sees whole, in a form that is no figure on its own.
        ("2026", "It opened in 2026.", True),
        ("2026", "Read https://x.example/2026 today.", False),
    ],
)
def test_a_figure_is_found_whole(value, post, states):
    assert drafts.states_figure(post, value) is states


@pytest.mark.parametrize(
    "visual, items",
    [
        (flow("It comes in", "Saves 40% of the time", "It goes out"), ITEMS),  # a results figure in a flow label
        (
            {"type": "compare",
             "left": {"icon": "clock", "label": "Before", "points": ["Hours of copying", "Late replies"]},
             "right": {"icon": "zap", "label": "After", "points": ["40% less copying", "Replies the same day"]}},
            ITEMS,
        ),
        (flow("It comes in", "It gets read", "It goes out"), [{**ITEMS[0], "detail": "It cut errors by 40%."}, ITEMS[1]]),
        (flow("It comes in", "It gets read", "It goes out"), [{**ITEMS[0], "title": "A 40% saving"}, ITEMS[1]]),
    ],
)
def test_a_figure_anywhere_else_on_the_card_must_be_in_the_post_too(env, conn, visual, items):
    outcome = run(conn, folder(card(visual, items=items)))
    assert outcome.status == "invalid" and "40%" in outcome.text(), outcome.text()


# Each passed the card tie and the gate before code review 01 (B1): none is in the posts.
@pytest.mark.parametrize(
    "detail, figure",
    [
        ("62 marketing teams use it.", "62"),
        ("40 junior staff saved hours.", "40"),
        ("30 decisions a day handled.", "30"),
        ("Marketing 62% faster.", "62%"),
        ("A 62-percent drop in errors.", "62-percent"),
        ("10-times faster than before.", "10-times"),
        ("A 5-million dollar saving.", "5-million"),
        ("2000 shops use it.", "2000"),
        ("1900 owners use it.", "1900"),
        ("Sixty-two percent of firms tried it.", "Sixty-two percent"),
        ("Nine in ten firms tried it.", "Nine in ten"),
        ("Forty firms saved hours.", "Forty"),
        ("Two-thirds of firms tried it.", "Two-thirds"),
        ("Twice as fast as before.", "Twice"),
        # Code review 01, round 2.
        ("2000 small shops use it.", "2000"),
        ("1999 local owners use it.", "1999"),
        ("100-plus firms use it.", "100-plus"),
        ("50-odd firms use it.", "50-odd"),
        ("A 500-strong client base.", "500-strong"),
        ("A 6-figure saving.", "6-figure"),
        ("A 5,000-user rollout.", "5,000"),
    ],
)
def test_a_figure_in_any_form_is_tied_to_the_post(env, conn, detail, figure):
    items = [{**ITEMS[0], "detail": detail}, ITEMS[1]]
    outcome = run(conn, folder(card(flow("It comes in", "It gets read", "It goes out"), items=items)))
    assert outcome.status == "invalid" and f'"{figure}"' in outcome.text(), outcome.text()


@pytest.mark.parametrize(
    "detail, in_post",
    [
        ("In the 1950s it was a lab idea.", "In the 1950s it was a lab idea."),
        ("It runs on 5G.", "It runs on 5G."),
        ("The 3D model comes first.", "The 3D model comes first."),
        ("Pick 3, then test them.", "Pick 3, then test them."),
        ("Over 1,000, mostly small firms.", "Over 1,000, mostly small firms."),
        ("Nine in ten firms tried it.", "Nine in ten firms tried it."),
        ("Forty firms tried it.", "Forty firms tried it."),
    ],
)
def test_a_figure_worded_the_same_way_in_every_post_passes(env, conn, detail, in_post):
    items = [{**ITEMS[0], "detail": detail}, ITEMS[1]]
    changes = {name: text.replace("Picture a small clinic", f"{in_post} Picture a small clinic") for name, text in variants().items()}
    outcome = run(conn, folder(card(flow("It comes in", "It gets read", "It goes out"), items=items), **changes))
    assert outcome.status == "delivered", outcome.text()


def test_a_date_or_a_link_in_the_post_does_not_meet_the_tie(env, conn):
    items = [{**ITEMS[0], "detail": "31 firms tried it."}, ITEMS[1]]
    changes = {name: text.replace("Picture a small clinic", "It came out on 31 October. Picture a small clinic") for name, text in variants().items()}
    outcome = run(conn, folder(card(flow("It comes in", "It gets read", "It goes out"), items=items), **changes))
    assert outcome.status == "invalid" and '"31"' in outcome.text(), outcome.text()


def test_a_small_number_word_on_a_card_needs_no_tie(env, conn):
    items = [{**ITEMS[0], "title": "Two AI updates worth a look"}, ITEMS[1]]
    outcome = run(conn, folder(card(flow("It comes in", "It gets read", "It goes out"), items=items)))
    assert outcome.status == "delivered", outcome.text()


def test_a_figure_elsewhere_on_the_card_passes_once_every_post_states_it(env, conn):
    visual = flow("It comes in", "It gets read", f"{PERCENT} tried this first")
    outcome = run(conn, folder(card(visual)))
    assert outcome.status == "delivered", outcome.text()


def test_a_year_or_a_name_with_a_number_is_not_a_figure(env, conn):
    items = [{**ITEMS[0], "detail": "A survey from 2026, run on GPT-5."}, ITEMS[1]]
    outcome = run(conn, folder(card(flow("It comes in", "It gets read", "It goes out"), items=items)))
    assert outcome.status == "delivered", outcome.text()


def test_a_figure_about_jura_fails_the_card_check(env, conn):
    outcome = run(conn, folder(card(figure(label=f"Jura saves {PERCENT} for you"))))
    assert outcome.status == "retry" and "figure about Jura" in outcome.text(), outcome.text()


def test_a_source_label_on_an_item_must_be_a_publisher_too(env, conn):
    items = [{**ITEMS[0], "source": "Gartner"}, ITEMS[1]]
    outcome = run(conn, folder(card(flow("It comes in", "It gets read", "It goes out"), items=items)))
    assert outcome.status == "invalid" and 'source "Gartner"' in outcome.text(), outcome.text()


def test_theme_problems_reads_the_source_line_case_insensitively(tmp_path):
    theme = load().theme("automation-tip")
    files = {**NEWS, **variants(), "sources.md": SOURCES, "card.json": card(figure(source="imda"))}
    sub = drafts.load(write(tmp_path, files), ["facebook", "instagram"], theme=theme)
    assert drafts.theme_problems(sub, theme, date(2026, 10, 27)) == []
