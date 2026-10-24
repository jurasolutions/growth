"""Passing and failing examples for every brand-check rule (foundation PRD §5.6)."""

import pytest
import yaml

from jura_growth import paths
from jura_growth.brand_check import check, find_links, sentence_case_problem


def rules(result):
    return {issue.rule for issue in result.issues}


GOOD_EMAIL = (
    "Hi there,\n\n"
    "I was looking at Acme Aircon's servicing packages and saw that customers request quotes "
    "through a form and wait for a reply. We've made a free quote builder that turns a job into a "
    "clean PDF quote in a few minutes: jurasolutions.sg/apps/quote-builder\n\n"
    "It's one of a growing set of small tools at jurasolutions.sg/apps. No sign-up, and what you "
    "type stays in your browser.\n\n"
    "If part of your week feels like copying the same details between systems, reply and tell me "
    "about it. That's the work we help Singapore teams automate.\n\n"
    "Ting Yu\nJura Solutions · jurasolutions.sg"
)


def test_reference_email_passes():
    result = check(GOOD_EMAIL, subject="A free quote builder for Acme Aircon", proper_nouns=["Acme Aircon"])
    assert result.passed, result.reasons()


# 1. exclamation
def test_exclamation_fails():
    assert "exclamation" in rules(check("Your quotes, sorted!"))


def test_no_exclamation_passes():
    assert "exclamation" not in rules(check("Your quotes, sorted."))


# 2. emoji
@pytest.mark.parametrize("text", ["Quotes made simple 🚀", "Done ✅", "Nice work ⭐", "Thanks :)", "See you ;-)", "Love it <3"])
def test_emoji_and_emoticons_fail(text):
    assert "emoji" in rules(check(text))


@pytest.mark.parametrize("text", ["Note: data stays in your browser.", "Ratio 3:1 is fine.", "Trigger → read → act", "© 2026 Jura Solutions"])
def test_lookalikes_pass(text):
    assert "emoji" not in rules(check(text))


# 3. buzzwords
@pytest.mark.parametrize(
    "text",
    [
        "We leverage AI for your invoices.",
        "A seamless handover.",
        "End to end automation.",
        "Unlocking your team's time.",
        "AI-powered receipts.",
        "An AI powered tool.",
        "Robust workflows.",
        "We empower owners.",
    ],
)
def test_buzzwords_fail(text):
    assert "buzzword" in rules(check(text))


@pytest.mark.parametrize("text", ["Supply chain disruption is in the news.", "Unlocked doors are a security risk.".replace("Unlocked", "Open")])
def test_ordinary_words_pass(text):
    assert "buzzword" not in rules(check(text))


# 4. urgency
@pytest.mark.parametrize("text", ["Limited spots this month.", "Act now to save your week.", "Offer ends soon.", "Only 3 spots left.", "Book now."])
def test_urgency_fails(text):
    assert "urgency" in rules(check(text))


def test_calm_cta_passes():
    assert "urgency" not in rules(check("Book a discovery call when it suits you."))


# 5. rhetorical questions
def test_question_subject_fails():
    assert "question" in rules(check("Body.", subject="Tired of retyping quotes?"))


def test_question_markdown_heading_fails():
    assert "question" in rules(check("# Still copying invoices by hand?\n\nBody text."))


def test_question_in_body_passes():
    result = check("What is one task you would hand over first? Reply and tell us.")
    assert "question" not in rules(result)


# 6. rhythm
def test_em_dash_heavy_fails():
    text = "Quotes — invoices — receipts. All of it — every week."
    assert "rhythm" in rules(check(text))


def test_one_em_dash_passes():
    assert "rhythm" not in rules(check("Quotes and invoices — the usual admin."))


@pytest.mark.parametrize(
    "text",
    [
        "Software does the typing, not your team.",
        "It's a log, not a feed.",
        "This is not just a tool, but a way of working.",
    ],
)
def test_this_not_that_fails(text):
    assert "rhythm" in rules(check(text))


def test_plain_negative_passes():
    assert "rhythm" not in rules(check("We do not store your receipts."))


# 7. numbers
def test_approved_claim_passes():
    result = check("We help you automate 80%+ of the manual steps in a process.")
    assert result.passed, result.reasons()


def test_approved_claim_without_plus_fails():
    assert "numbers" in rules(check("We automate 80% of the manual steps."))


@pytest.mark.parametrize(
    "text",
    [
        "We've saved clients 12,400 hours.",
        "Trusted by 90+ companies.",
        "Our clients see an average ROI of 340%.",
        "Your automation goes live in 14 days, guaranteed.",
        "Jura has helped 2000 businesses.",
        "We cut reconciliation time by half.",
        "Teams save 10 hours a week.",
    ],
)
def test_unevidenced_figures_fail(text):
    assert "numbers" in rules(check(text))


@pytest.mark.parametrize(
    "text",
    [
        "Add up to 3 receipts. Clear, flat photos work best.",
        "Please use a logo under 1 MB.",
        "Quotes are valid for 30 days by default.",
        "1 free try left today",
        "Posted on 24 October 2026 at 9:30am.",
        "See APP-001 and quote Q-20261024-01.",
        "Five small things to automate this week.",
        "3 tips for month-end.",
    ],
)
def test_neutral_figures_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_statutory_rate_with_official_source_passes():
    source = "https://www.iras.gov.sg/taxes/goods-services-tax-(gst)"
    text = f"GST is charged at 9% (source: {source})."
    result = check(text, channel_name="news", sources=[source])
    assert result.passed, result.reasons()


def test_statutory_rate_without_source_fails():
    assert "numbers" in rules(check("GST is charged at 9%."))


def test_news_figure_with_source_passes_on_news_channel():
    text = "A survey found 61% of firms plan to adopt AI tools this year. https://example.com/report"
    result = check(text, channel_name="news", sources=["https://example.com/report"])
    assert "numbers" not in rules(result) and "links" not in rules(result), result.reasons()


def test_news_figure_about_jura_still_fails():
    text = "We grew 50% this year, according to https://example.com/report"
    assert "numbers" in rules(check(text, channel_name="news", sources=["https://example.com/report"]))


def test_unsourced_statistic_fails():
    assert "numbers" in rules(check("Most SMEs spend 15 hours on admin."))


# A figure written in words is still a figure (code review 01 B3).
@pytest.mark.parametrize(
    "text",
    [
        "We have helped twelve businesses go live.",
        "Jura has served forty clients across Singapore.",
    ],
)
def test_spelled_out_figures_about_jura_fail(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize(
    "text",
    [
        "Most SMEs spend fifteen hours on admin.",
        "Twelve businesses go live each month.",
        "Owners lose thirty hours to retyping.",
    ],
)
def test_spelled_out_figures_need_a_source_like_digits(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


def approved_claim_texts():
    data = yaml.safe_load((paths.config_dir() / "approved_claims.yaml").read_text(encoding="utf-8"))
    return [claim["text"] for claim in data["claims"]]


@pytest.mark.parametrize(
    "text",
    [
        "Most first automations go live within weeks.",
        "Start with one process.",
        "We start with one process and a short call.",
        *approved_claim_texts(),
    ],
)
def test_one_and_approved_claims_still_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_spelled_out_news_figure_with_source_passes_on_news_channel():
    text = "A survey found forty firms plan to adopt AI tools this year. https://example.com/report"
    result = check(text, channel_name="news", sources=["https://example.com/report"])
    assert "numbers" not in rules(result), result.reasons()


# The rule flags a number word that counts a following noun (G2 decision).
@pytest.mark.parametrize(
    "text",
    [
        "Tell us which of the two you would hand over first.",
        "We can start with one or two.",
        "Those two are where we start.",
    ],
)
def test_number_word_counting_nothing_passes(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_number_word_counting_through_of_fails():
    assert "numbers" in rules(check("We've helped twelve of the region's firms."))


@pytest.mark.parametrize(
    "text",
    [
        "Forty-five owners asked the same question.",
        "Twenty one owners asked the same question.",
        "Two thousand owners read the guide.",
        "A hundred and fifty owners asked.",
        "Two dozen owners asked the same question.",
        "We have a dozen clients.",
        "We have helped a hundred businesses.",
        "Jura has one hundred clients.",
    ],
)
def test_compound_number_words_are_read_in_full(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


# Code review 04 probes: each of these passed on the first version of the rule.
@pytest.mark.parametrize(
    "text",
    [
        # B1: "per cent" written as two words
        "We cut admin by forty per cent.",
        "Jura automates ninety per cent of your invoicing.",
        "Our clients see a hundred per cent accuracy.",
        "Most SMEs lose thirty per cent of their week to admin.",
        # S1: hedged counts
        "We have helped twelve or more businesses.",
        "Jura has served forty or so clients.",
        "We start with two or three processes.",
        # S2: approximate scales
        "We have helped a couple of dozen businesses.",
        "We have helped several hundred businesses.",
        "We have helped a few dozen businesses.",
    ],
)
def test_review_04_spelled_out_figures_fail(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize(
    "text",
    [
        # S4: the number counts no noun
        "We'd like to meet the two of you.",
        "These two matter most to us.",
        "Both of these work, and the two fit together for us.",
        # "one or two" hedges towards "one", which G2 allows
        "We start with one or two processes.",
    ],
)
def test_review_04_number_words_counting_nothing_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize("text", ["We have helped ſixty businesses.", "Jura has ſeven clients."])
def test_unicode_lookalike_number_words_do_not_crash(text):
    check(text)


# Hyphenated compounds are words, the way "2-step" and "9-to-5" already are.
@pytest.mark.parametrize(
    "text",
    [
        "We take the nine-to-five admin off your plate.",
        "We use a three-step handover.",
        "Our forty-five-minute call maps one process.",
    ],
)
def test_hyphenated_number_compounds_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


# 8. sentence case
@pytest.mark.parametrize("value", ["Free Quote Builder", "Tell Us How You Quote Today", "Open Quote File", "Quote Builder", "download PDF"])
def test_title_case_fails(value):
    assert sentence_case_problem(value)


@pytest.mark.parametrize(
    "value",
    [
        "Quote builder",
        "Download PDF",
        "Download Excel",
        "Tell us how you quote today",
        "A free quote builder for Acme Aircon",
        "Quotes, jobs and invoices, entered once",
        "Explainer: What PayNow is",
        "iPhone receipts work too",
    ],
)
def test_sentence_case_passes(value):
    assert sentence_case_problem(value) is None


def test_button_title_case_fails_in_check():
    assert "sentence-case" in rules(check("", buttons=["Save Quote File"]))


# 9. links
def test_jura_links_pass():
    assert "links" not in rules(check("Try it at https://jurasolutions.sg/apps/quote-builder?utm_source=email or jurasolutions.sg/apps."))


def test_other_links_fail_on_general_channel():
    assert "links" in rules(check("See https://example.com for more."))


def test_bare_domain_fails_on_general_channel():
    assert "links" in rules(check("See example.com for more."))


def test_undeclared_source_fails_on_news_channel():
    result = check("See https://other.example.org/x", channel_name="news", sources=["https://example.com/report"])
    assert "links" in rules(result)


def test_email_addresses_are_not_links():
    assert "links" not in rules(check("Reply to info@jurasolutions.sg or write to them at hello@acme.sg."))


def test_find_links():
    links = find_links("Go to jurasolutions.sg/apps, [the report](https://example.com/r) or www.iras.gov.sg.")
    assert "jurasolutions.sg/apps" in links
    assert "https://example.com/r" in links
    assert "www.iras.gov.sg" in links


# 10. channel
def test_unknown_channel_is_an_error():
    with pytest.raises(ValueError):
        check("text", channel_name="no-such-channel")


def test_were_and_us_are_not_jura():
    text = "A survey found 86% of owners were using AI, and US firms led. https://example.com/survey"
    result = check(text, channel_name="news", sources=["https://example.com/survey"])
    assert "numbers" not in rules(result), result.reasons()
    assert "numbers" in rules(check("We're now trusted by 40 firms.", channel_name="news", sources=["https://example.com/survey"]))
    assert "numbers" in rules(check("Tell us about the 12,000 invoices we filed."))


def test_news_links_must_be_declared():
    assert "links" in rules(check("See https://example.com/report", channel_name="news"))


@pytest.mark.parametrize("text", ["Use a number, like 120 or 120.50.", "Use a percentage from 0 to 100.", "Enter an amount such as 1,250.00."])
def test_input_hints_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_input_hint_does_not_excuse_a_claim():
    assert "numbers" in rules(check("Use our tool, like 300 clients do."))
