"""Passing and failing examples for every brand-check rule (foundation PRD §5.6)."""

import pytest
import yaml

from jura_growth import paths
from jura_growth.brand_check import check, figures_in, find_links, sentence_case_problem


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
        # Round 2, R2-B1: "of us/you/them" counts people unless "the" comes first
        "There are twelve of us at Jura.",
        "We have helped forty of them go live.",
        "Forty of you have booked a call with us.",
        "We have helped two or three of them.",
        # Round 2, R2-S1: after a possessive, a verb-like word is a noun
        "Our forty sync jobs run each night.",
        "Our twelve work streams run in parallel.",
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


# Figures that used to read as a date, a compound or a year (code review of ticket 01, B1).
@pytest.mark.parametrize(
    "text",
    [
        "We helped 62 marketing teams.",  # "marketing" read as a month
        "Jura served 40 junior staff.",
        "We handled 30 decisions a day.",
        "Our 12 mayors renewed.",
        "We cut errors by 62-percent.",  # read as a compound, like "2-step"
        "We are 10-times faster.",
        "We made a 5-million dollar saving.",
        "We are 10x-faster.",
        "We cut errors by sixty-percent.",
        "We cut errors by two-thirds.",
        "Jura has 2000 shops on its books.",  # read as a year
        "In May 5 firms joined us.",
        "Nine in ten of our clients renew.",  # a ratio in words
        "One out of five of our clients renews.",
    ],
)
def test_a_figure_about_jura_cannot_pass_as_a_date_a_compound_or_a_year(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize(
    "text",
    [
        "62 marketing teams use it.",
        "Marketing 62% faster.",
        "A 62-percent drop in errors.",
        "10-times faster than before.",
        "A 5-million dollar saving.",
        "2000 shops use it.",
        "1900 owners use it.",
        "Nine in ten firms tried it.",
        "Nine in ten owners agree.",
        "9 in 10 owners agree.",
        "Two-thirds of owners agree.",
        "A third of owners agree.",
        "5 million shops use it.",
        "5-million shops use it.",
        # Code review 01, round 2: a year's shape with a noun off the old list, and fused counts.
        "2000 small shops use it.",
        "1999 local owners use it.",
        "2000 Singapore shops use it.",
        "Over 2000 shops use it.",
        "It runs in 2000 shops.",
        "Used by 2000 shops.",
        "100-plus firms use it.",
        "50-odd firms use it.",
        "A 500-strong client base grows.",
        "A 500-client base grows.",
        "A 6-figure saving.",
        # Code review 01, round 3: a figure with a thousands comma, fused to a noun.
        "A 5,000-user rollout.",
        "A 2,000-store chain.",
        "A 12,000-person survey.",
        "A 12,400-hour project.",
        # R3-S1: a year's shape before "of" counts, so a claim split over two sentences fails.
        "We help shops. 2000 of them renew.",
    ],
)
def test_a_figure_with_no_source_cannot_pass_as_a_date_a_compound_or_a_year(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize(
    "text",
    [
        "Posted on 5 March 2026.",
        "Posted on 5 Mar.",
        "Posted on March 5, 2026.",
        "Posted on Sept 3.",
        "Posted on 3rd September.",
        "Filed on 31 December 2025.",
        "Filed in Oct 2026.",
        "It opens on 1 May.",
        "It opens in May 2026.",
        "It opened on Jan. 9.",
        "In 2026 this changed.",
        "In 2026 the rules changed.",
        "2026 brings new rules.",
        "2026 was a long year.",
        "The 2026 budget is out.",
        "It began in 1950.",
    ],
)
def test_real_dates_and_years_still_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize(
    "text",
    [
        "Book a 30-minute call.",
        "A 2-step handover works.",
        "Buy 3rd-party tools with care.",
        "It is a 3-way match.",
        "Start with a 30-day trial.",
        "A 45-minute call maps one process.",
        "Pick 3, then test them.",
        "A 2 in 1 laptop works.",
        "Ask a third party to check it.",
        "We check in once a quarter.",
        "We take on one third-party tool at a time.",
    ],
)
def test_honest_compounds_and_small_counts_still_pass(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_a_trailing_comma_is_not_part_of_a_figure():
    assert figures_in("Pick 3, then test them. Over 1,000, mostly small firms.") == ["3", "1,000"]


def test_a_statutory_rate_with_a_source_still_passes_with_a_compound_beside_it():
    source = "https://www.iras.gov.sg/taxes/gst"
    text = f"GST is charged at 9% on a 30-day invoice (source: {source})."
    result = check(text, channel_name="news", sources=[source])
    assert result.passed, result.reasons()


# In a sentence about Jura, any digit fails unless it is an approved claim or the channel's own
# allowance. There are no shapes to enumerate: a date, a year, a compound and a name are refused
# with the rest, and the writer is told the same (prompts/social.md). A false refusal costs one
# rewrite, and a miss is a made-up client count.
@pytest.mark.parametrize(
    "text",
    [
        # Code review 01, round 2, must fail.
        "We helped 2000 small shops.",
        "Jura served 1999 local owners.",
        "Our 2000 happy owners stay.",
        "We served 2000 retail shops in Singapore.",
        "Our 2000 Singapore shops stay.",
        "We served 100-plus firms.",
        "We served 50-odd firms.",
        "Our 500-strong client base grows.",
        "We have a 500-client base.",
        "We deliver 6-figure savings.",
        # A year gets no exemption here. The review listed the first three as passing; the
        # conductor's decision on that review refuses them.
        "We updated the 2026 tax rates.",
        "Our 2026 tax rates guide is free.",
        "We can look at your 2026 business plan.",
        "We wrote our 2026 plans.",
        "We opened in 2026.",
        # Nor a compound, a date, a time or a name.
        "Our 45-minute call maps one process.",
        "We offer a 30-day trial.",
        "We use a 2-step handover.",
        "We buy 3rd-party tools.",
        "We met on 5 March 2026.",
        "Our office closes on 1 May.",
        "We open at 9:30am.",
        "We use GPT-5.",
        "Jura works 24/7.",
        "Tell us about step 1.",
        "We keep it for 30 days.",
        # The prompt's own wording: an approved claim doesn't excuse the rest of the sentence.
        "We automate 80%+ of the manual steps for 62 firms.",
    ],
)
def test_any_digit_in_a_sentence_about_jura_fails(text):
    assert "numbers" in rules(check(text)), check(text).reasons()


@pytest.mark.parametrize(
    "text",
    [
        "We automate 80%+ of the manual steps in a process.",
        "Jura helps you automate 80%+ of the manual steps.",
        "We read more at https://jurasolutions.sg/apps/a1 on the site.",
        "Write to us at team1@jurasolutions.sg for a copy.",
        "We take the nine-to-five admin off your plate.",
        "The two of us will call.",
    ],
)
def test_an_approved_claim_or_a_link_in_a_sentence_about_jura_passes(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_a_sentence_about_jura_is_read_alone():
    """The next sentence may carry a date of its own."""
    assert "numbers" not in rules(check("We read every answer. It closes on 30 May."))


@pytest.mark.parametrize(
    "text",
    [
        "We'd be glad to hear how it works on a 30-minute call.",
        "We could talk it through on a 30-minute intro call.",
        "Our 30-minute chat is a good start.",
    ],
)
def test_the_email_channel_allows_its_call_and_no_other_channel_does(text):
    assert "numbers" not in rules(check(text, channel_name="email")), check(text, channel_name="email").reasons()
    assert "numbers" in rules(check(text))


@pytest.mark.parametrize(
    "text",
    [
        "We helped 62 firms on a 30-minute call.",
        "We offer a 45-minute call.",
        "We offer a 30-day trial.",
        "We helped 2000 small shops.",
    ],
)
def test_the_email_channels_allowance_is_only_its_call(text):
    assert "numbers" in rules(check(text, channel_name="email")), check(text, channel_name="email").reasons()


@pytest.mark.parametrize(
    "text",
    [
        # Code review 01, round 2, must pass: none is about Jura.
        "Your 2026 business plan is due.",
        "The 2026 rates apply to you.",
        "In 2026 prices rose.",
        "Budget 2026 grants open soon.",
        "Plan your 2026 sales target.",
        "Book a 30-minute call.",
        # R2-S2: a position in a list, or a rate over time, is no share.
        "Step 2 out of 3.",
        # Round 3: these must keep passing beside the thousands-comma fix.
        "A 3rd-party tool.",
        "A 2-step handover works.",
        "Pick 3, then test them.",
        "Version 1.2-beta is out.",
        # A known limit, pinned: this can't be told from "The 2026 rates" without reading its meaning,
        # it doesn't name Jura, and it passes on main too. Ting Yu's read of the card is the control.
        "The 2000 shops use it.",
        "Page 2 of 3 is next.",
        "It sends one in five minutes.",
    ],
)
def test_a_year_or_a_position_not_about_jura_still_passes(text):
    assert "numbers" not in rules(check(text)), check(text).reasons()


def test_a_share_with_a_list_word_elsewhere_in_the_sentence_is_still_a_share():
    assert "numbers" in rules(check("Each step shows nine in ten owners agree."))

