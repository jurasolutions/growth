"""The brand gate for a reply to someone (`inbox-email`, `inbox-social`), at `brand_check.check`.
Judgement can't fail on a double, so what can be enforced in code is enforced here (functional
review's table for E3 to E5). Ids are as in test_inbox_mail.py.
"""

from __future__ import annotations

import pytest

from jura_growth import brand_check

GOOD = "We help with invoices and the copying between systems that follows. The first step is a short discovery call."
THEM = {"sender_name": "Priya Nair", "their_words": "Do you do invoices? We have 12 staff."}


def issues(text: str, channel: str = "inbox-email", **context) -> list[str]:
    return brand_check.check(text, channel_name=channel, context={**THEM, **context}).reasons()


def test_iw_e4_a_plain_answer_passes_on_both_channels():
    """IW-E4."""
    assert issues(GOOD) == []
    assert issues(GOOD, "inbox-social") == []
    assert issues(GOOD, "inbox-social", public=True, platform="facebook") == []


# --- length and shape --------------------------------------------------------------------


@pytest.mark.parametrize("channel, words, passes", [
    ("inbox-email", 179, True), ("inbox-email", 180, False),
    ("inbox-social", 79, True), ("inbox-social", 80, False),
])
def test_iw_e4_each_channels_length_is_under_its_limit(channel, words, passes):
    """IW-E4, PRD §5: under 180 words on email, under 80 on social."""
    assert (issues(" ".join(["word"] * words), channel) == []) is passes


def test_iw_a11_an_email_may_have_paragraphs():
    """IW-E4: only a DM's Enter sends."""
    assert issues("Hi Priya,\n\nYes, we can help with that.\n\nLevi will write back this week.") == []


@pytest.mark.parametrize("line_break", ["\n", "\r", "\r\n", " ", " ", "\u0085", "\x0b", "\x0c"])
def test_iw_a11_a_social_draft_refuses_every_line_break(line_break):
    """IW-A11: Enter sends in a DM, so a fragment would go out."""
    found = issues(f"Yes, we can help with that.{line_break}Levi will write back.", "inbox-social")
    assert any("one paragraph" in reason for reason in found)


# --- E4: only Jura's links, and only what can be evidenced ---------------------------------


@pytest.mark.parametrize("link", [
    "jurasolutions.sg.evil.test",
    "jurasolutions.sg@evil.test",
    "https://jurasolutions.sg@evil.test/path",
    "https://jurasolutions.sg.evil.test/",
    "jurаsolutions.sg",  # a Cyrillic look-alike
    "evil.test",
    "bit.ly/abc",
    "https://bit.ly/abc",
    "xn--jursolutions-q8a.sg",
    "[jurasolutions.sg](https://evil.test)",
])
@pytest.mark.parametrize("channel", ["inbox-email", "inbox-social"])
def test_iw_a11_a_draft_link_must_be_juras(link, channel):
    """IW-A11, IW-E4: every link shape in the adversarial table."""
    assert issues(f"Have a look at {link} when you can.", channel) != []


@pytest.mark.parametrize("link", ["https://jurasolutions.sg/apps", "jurasolutions.sg", "www.jurasolutions.sg/apps/quote"])
def test_iw_e4_juras_own_links_pass(link):
    """IW-E4."""
    assert issues(f"Have a look at {link} when you can.") == []


def test_iw_e4_juras_own_address_passes_and_anothers_doesnt():
    """IW-E3: inviting an email is the move to a private channel."""
    assert issues("Please write to info@jurasolutions.sg and Levi will answer.") == []
    assert issues("Please write to levi@elsewhere.example and he will answer.") != []


@pytest.mark.parametrize("text", [
    "We have saved 340 hours for a client like you.",
    "A first automation takes 14 days.",
    "We can do 30 invoices a minute.",
])
def test_iw_e4_a_figure_not_in_the_approved_claims_is_refused(text):
    """IW-E4: the numbers rule, stricter than posts, since nothing here cites a source."""
    assert any("figure" in reason.lower() or "number" in reason.lower() for reason in issues(text))


def test_iw_e4_an_approved_claim_and_their_own_figure_pass():
    """IW-E4: the numbers rule stops invention, and repeating what they said invents nothing."""
    assert issues("Most first automations go live within weeks.") == []
    assert issues("With 12 staff, that sounds like a lot of retyping.") == []


def test_iw_e4_dates_and_times_arent_figures():
    """IW-E4."""
    assert issues("Levi can talk on 3 Nov at 2pm.") == []


@pytest.mark.parametrize("greeting, passes", [
    ("Hi Priya,", True),
    ("Hello Priya Nair,", True),
    ("Hi there,", True),
    ("Hello,", True),
    ("Dear team,", True),
    ("Hi Jane,", False),
    ("Dear Mr Tan,", False),
])
def test_iw_e4_a_name_they_didnt_give_is_refused(greeting, passes):
    """IW-E4: a first name only if it is in their name or their words."""
    assert (issues(f"{greeting}\n\nYes, we can help with that.") == []) is passes


def test_iw_e4_a_name_they_signed_with_passes():
    """IW-E4."""
    assert issues("Hi Sam,\n\nYes.", sender_name="", their_words="Thanks. Sam") == []


@pytest.mark.parametrize("text", [
    "We promise a full refund within the week.",
    "We guarantee it will work.",
    "We will refund you today.",
    "You can have your money back.",
    "We can do this for free.",
    "We can offer you a discount.",
])
def test_iw_a2_an_injected_promise_is_refused(text):
    """IW-A2, IW-E4."""
    assert any("promise" in reason.lower() for reason in issues(text))


def test_iw_d9_naming_their_refund_isnt_promising_one():
    """IW-D9: a holding reply can say what it is about."""
    assert issues("I am sorry about this. Levi will reply to you personally about your refund.", high=True) == []


def test_iw_e4_voice_rules_still_apply():
    """IW-E4: the core gate runs first."""
    assert any("exclamation" in reason.lower() for reason in issues("Yes we do!"))
    assert any("buzzword" in reason.lower() for reason in issues("We leverage synergy."))


def test_iw_fs13_a_draft_is_in_english():
    """IW-FS13: a message not in English gets an English draft, and the card says so."""
    assert any("English" in reason for reason in issues("你好，我们可以帮助您处理发票，请告诉我们更多。"))
    assert issues("Hi José, yes we can help with your invoices.", their_words="José here") == []


@pytest.mark.parametrize("text", ["It costs S$500 to start.", "From $2,000 a month.", "It is SGD 300.", "About 500 dollars."])
@pytest.mark.parametrize("channel", ["inbox-email", "inbox-social"])
def test_iw_e3_a_price_figure_is_refused(text, channel):
    """IW-E3, IW-E4: there is no pricing to quote from yet, public or private."""
    assert issues(text, channel, their_words="How much is it? S$500? $2,000? SGD 300? 500 dollars?") != []


# --- E3: moving to a private channel --------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Please post your phone number below.",
    "Leave your number here and Levi will call.",
    "Drop your email address in the comments.",
    "Share your address so we can look at it.",
])
def test_iw_e3_a_public_draft_cant_ask_for_contact_details(text):
    """IW-E3."""
    assert issues(text, "inbox-social", public=True, platform="facebook") != []


def test_iw_e3_inviting_a_dm_or_an_email_passes():
    """IW-E3: the general part in public, the rest in private."""
    text = "It depends on the process. Send us a message here, or write to info@jurasolutions.sg, and Levi will take a look."
    assert issues(text, "inbox-social", public=True, platform="facebook") == []


def test_iw_fn3_an_instagram_comment_carries_no_link():
    """IW-FN3: links in an Instagram comment aren't clickable, so it invites a DM instead."""
    text = "Have a look at jurasolutions.sg/apps when you can."
    assert issues(text, "inbox-social", public=True, platform="facebook") == []
    assert issues(text, "inbox-social", public=True, platform="instagram") != []
    assert issues(text, "inbox-social", public=False, platform="instagram") == []


# --- D9: a holding reply ----------------------------------------------------------------------


def test_iw_d9_a_high_draft_is_short_and_names_levi():
    """IW-D9: a short holding reply that promises nothing beyond a personal reply from Levi."""
    assert issues("I am sorry to hear this. Levi will reply to you personally.", high=True) == []
    assert any("reply personally" in reason for reason in issues("I am sorry to hear this.", high=True))
    assert any("short" in reason for reason in issues("Levi will reply. " + " ".join(["word"] * 60), high=True))
    assert issues("Yes, we can help with that.") == []  # only a high draft has to
