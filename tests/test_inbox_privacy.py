"""The conversation class: what a person wrote may reach Discord on a report or a card, with
their contact details masked (IW-B3, PRD §4). Everywhere else the old rule stands, which
`test_privacy.py` and `test_outreach_privacy.py` prove by staying untouched.
"""

from __future__ import annotations

from discord_double import discord_double  # noqa: F401
from jura_growth import discord, privacy


def test_iw_b3_a_registered_body_is_shown_in_a_conversation_and_masked_elsewhere():
    """IW-B3, probe P1: `never_show` is process-wide and must not blank a conversation."""
    words = "Could you send the price list for clinics"
    privacy.never_show(words)

    assert privacy.for_discord(f"They said: {words}") == "They said: [removed]"
    assert privacy.for_discord(f"They said: {words}", conversation=[words]) == f"They said: {words}"


def test_iw_b3_a_learned_name_is_not_masked_in_a_conversation():
    """IW-B3, probe P2: "Hi Jane," survives, though own copy still masks it."""
    privacy.remember_address("jane.tan@example.com.sg")
    text = "Hi Jane, thanks for writing."

    assert privacy.for_discord(text) == "Hi [name removed], thanks for writing."
    assert privacy.for_discord(text, own_copy=[text]) == "Hi [name removed], thanks for writing."
    assert privacy.for_discord(text, conversation=[text]) == text


def test_iw_b3_the_owners_address_is_kept_in_a_conversation_only():
    """IW-B3, probe P3."""
    privacy.remember_owner("levi@jurasolutions.sg")
    text = "I wrote to levi@jurasolutions.sg last week"

    assert "[removed]" in privacy.for_discord(text)
    assert privacy.for_discord(text, conversation=[text]) == text


def test_iw_b3_iw_a14_a_conversation_still_masks_phones_named_addresses_secrets_and_finance():
    """IW-B3, IW-A14: only names and registered text are let through."""
    secret = "re_abcdefghijklmnop123456"
    text = (
        f"Call +65 9123 4567 or 9123 4567, or write to jane.tan@example.com.sg. My key is {secret}.\n"
        "See personal-finance/data/tally.db"
    )

    shown = privacy.for_discord(text, conversation=[text])

    assert "9123" not in shown and shown.count("[phone removed]") == 2
    assert "jane.tan@" not in shown and "j***@example.com.sg" in shown
    assert secret not in shown and "[redacted]" in shown
    assert "tally.db" not in shown and "[removed: personal finance]" in shown


def test_iw_b3_only_the_named_strings_get_the_class():
    """IW-B3: the frame around a quote keeps the plain rule."""
    privacy.remember_address("jane.tan@example.com.sg")
    quote = "Jane here, hello"

    shown = privacy.for_discord(f"Frame for Jane\n> {quote}", conversation=[quote])

    assert shown == f"Frame for [name removed]\n> {quote}"


def test_iw_b3_a_string_in_both_classes_reads_as_conversation():
    """IW-B3: own copy would mask the name, so the wider class wins for the same words."""
    privacy.remember_address("jane.tan@example.com.sg")
    text = "Hi Jane,"

    assert privacy.for_discord(text, own_copy=[text], conversation=[text]) == text


def test_iw_b3_a_draft_is_unchanged_by_the_class_unless_it_holds_contact_details():
    """IW-B3: §5's refusal becomes `for_discord(draft, conversation=[draft]) != draft`."""
    privacy.remember_address("hope.lee@example.com.sg")
    fine = "Hi Jane,\n\nHope this helps. Levi will come back to you."
    assert privacy.for_discord(fine, conversation=[fine]) == fine

    leaking = "Hi Jane, call me on 9123 4567."
    assert privacy.for_discord(leaking, conversation=[leaking]) != leaking


def test_iw_b3_discord_post_carries_the_class(conn, discord_double):  # noqa: F811
    """IW-B3: the post keeps the words, and the outbox fallback holds them masked."""
    privacy.remember_address("jane.tan@example.com.sg")
    quote = "Hi, Jane here. Call 9123 4567."

    result = discord.post(conn, "mission-control", f"> {quote}", dedupe=False, conversation=[quote])

    assert result.delivered
    assert discord_double.contents("mission-control") == ["> Hi, Jane here. Call [phone removed]."]


def test_iw_b3_an_edit_keeps_the_words_a_card_showed(conn, discord_double):  # noqa: F811
    """IW-B3: `discord.edit` re-masks unless it is told what is conversation."""
    privacy.remember_address("jane.tan@example.com.sg")
    piece = "They said: thanks Jane"

    discord.edit(conn, "approvals", "123", piece, conversation=[piece])
    discord.edit(conn, "approvals", "123", piece)

    edits = [r.content for r in discord_double.requests if r.method == "PATCH"]
    assert edits == [piece, "They said: thanks [name removed]"]
