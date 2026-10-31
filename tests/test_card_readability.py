"""What the approval card can't show can't be approved (code review 02, SP-B1, SEC-B1; the
conductor's decision). Discord masks phones, named addresses and learned names even in Jura's own
copy (`privacy.py`), and that stays. So a post or a picture's words that the layer would change fail
the brand gate, judged by what the layer actually does and nothing else.
"""

from __future__ import annotations

import pytest

import gate_adapter_community_post
import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, brand_check, cards, privacy
from test_social import env  # noqa: F401 - a fixture


def masked_issues(text: str, channel: str = "social-facebook") -> list[str]:
    found = brand_check.check(text, channel_name=channel, sources=[], context={"theme": {"id": "automation-tip"}})
    return [issue.message for issue in found.issues if "approval card" in issue.message]


@pytest.mark.parametrize("words", [
    "Call 8123 4567 today.",
    "Call +65 9123 4567 today.",
    "Write to jane.tan@example.com about it.",
    "See https://www.example.com/tech/story-81234567 for more.",
])
def test_words_the_masking_layer_changes_fail_the_gate(words):
    assert masked_issues(f"A small note. {words}")


@pytest.mark.parametrize("words", [
    "Sam Altman said the model ships this month.",
    "Dr Tan Mei Ling leads the programme.",
    "Write to hello@example.com about it.",
    "Grant schemes change often.",
    "It costs 3 hours a week.",
])
def test_words_the_masking_layer_leaves_alone_are_not_refused(words):
    """A public figure in a news story is judged by what the layer does: it knows only the names
    in addresses the engine holds."""
    assert masked_issues(f"A small note. {words}") == []


def test_a_name_learned_from_a_lead_is_refused_and_a_different_name_is_not():
    privacy.remember_address("sam.lim@example.com.sg")
    assert masked_issues("Sam Altman said the model ships this month.")
    assert masked_issues("Mira Murati said the model ships this month.") == []


def test_a_word_that_is_also_a_learned_name_is_refused_only_when_written_as_a_name():
    privacy.remember_address("mark.lee@example.com.sg")
    assert masked_issues("Mark your calendar for it.")  # the honest cost: this is a false refusal
    assert masked_issues("Put a mark on your calendar for it.") == []


def test_jura_s_own_sender_address_is_not_refused():
    privacy.remember_owner("tingyu@jurasolutions.sg")
    assert masked_issues("Write to tingyu@jurasolutions.sg about it.") == []


def test_the_reason_shows_the_line_as_masked_and_never_the_value():
    found = brand_check.check("Call 8123 4567 today.", channel_name="social-facebook", sources=[],
                              context={"theme": {"id": "automation-tip"}})
    [text] = [str(issue) for issue in found.issues if "approval card" in issue.message]
    assert "8123" not in text and "[phone removed]" in text


def test_the_card_channel_refuses_the_same_words():
    assert masked_issues("Call 8123 4567 today.", "social-card")


# --- a fence that reached a card anyway can't close the card's own ----------------------------------


def test_a_social_post_past_the_gate_can_not_close_its_cards_fence(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=("facebook",))
    pw.item(conn, "facebook", text="First words ```\nnot the card's own note\n``` last words.\n")
    cards.sweep(conn)
    [card] = discord_double.contents("approvals")
    assert card.count("```") == 2


def test_a_community_post_can_not_close_its_cards_fence(conn, monkeypatch, tmp_path):
    gate = gate_adapter_community_post.ADAPTER(conn=conn, monkeypatch=monkeypatch, tmp_path=tmp_path)
    subject = gate.item()
    conn.execute("UPDATE community_posts SET text = text || ' ``` a fence'")
    text = approvals.kinds()[gate.kind].kind.preview(conn, subject).text
    assert text.count("```") == 2
