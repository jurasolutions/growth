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
from jura_growth import approvals, brand_check, cards, paths, privacy
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


# --- the reason names every masked word, so one regeneration can fix them all (round 2, R2-B1) ------


LONG = "Most small teams chase late invoices the same way, and it costs them a Friday afternoon every week. "


def reasons(text: str, channel: str = "social-facebook") -> list[str]:
    found = brand_check.check(text, channel_name=channel, sources=[], context={"theme": {"id": "automation-tip"}})
    return [str(issue) for issue in found.issues if "approval card" in issue.message]


def test_a_mask_far_along_a_line_is_quoted_where_it_is():
    [reason] = reasons(LONG * 3 + "Call 8123 4567 today.")
    assert "[phone removed] today" in reason and "8123" not in reason


def test_every_masked_place_gets_its_own_reason_on_any_line():
    privacy.remember_address("mark.lee@example.com.sg")
    text = (f"Call 8123 4567 today.\n\n{LONG}Firms with 3000-4000 employees.\n\n{LONG}{LONG}Mark your calendar.\n\n"
            f"Write to jane.tan@example.com about it. {LONG}See https://www.example.com/news/article-98765432 for more.")
    found = reasons(text)
    assert len(found) == 5
    for words in ("[phone removed] today", "with [phone removed] employees", "[name removed] your calendar", "j***@example.com", "article-[phone removed]"):
        assert sum(words in reason for reason in found) == 1, words
    for value in ("8123", "3000-4000", "Mark your", "jane.tan", "98765432"):
        assert not any(value in reason for reason in found), value


def test_each_reason_says_what_to_do_about_that_kind_of_mask():
    privacy.remember_address("mark.lee@example.com.sg")
    [link] = reasons("See https://www.example.com/news/article-98765432 for more.")
    assert "link" in link and "phone number" not in link
    [phone] = reasons("Firms with 3000-4000 employees.")
    assert "3,000 to 4,000" in phone
    [name] = reasons("Mark your calendar.")
    assert "name" in name and "ordinary word" in name
    [address] = reasons("Write to jane.tan@example.com about it.")
    assert "address" in address


def test_a_window_stays_short_and_inside_its_line():
    [reason] = reasons("Before this line.\n" + LONG * 3 + "Call 8123 4567 today. " + LONG * 3 + "\nAfter this line.")
    assert "Before this line" not in reason and "After this line" not in reason
    assert len(reason.split("“")[1]) < 120


def test_the_same_words_twice_are_said_once():
    assert len(reasons("Call 8123 4567 today.\n\nCall 8123 4567 today.")) == 1


def test_masking_nobody_can_place_still_fails_with_a_reason(monkeypatch):
    monkeypatch.setattr(privacy, "own_copy_as_shown", lambda text: text + " changed")
    assert reasons("A small note.")


def test_the_prompt_says_what_the_run_can_see_for_itself():
    prompt = " ".join((paths.REPO_ROOT / "prompts" / "social.md").read_text(encoding="utf-8").split())
    for words in ("no phone numbers", "3,000 to 4,000", "long run of digits"):
        assert words in prompt, words
