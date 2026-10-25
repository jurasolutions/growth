"""Posting with `?wait=true` and editing a message in place (MC §4.6 A12; ticket 04b).

Through the Discord double: a waited post returns each message's id, and `edit()` sends a PATCH
for that id, masked like any post, and mentions nobody.
"""

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import discord


def test_a_waited_post_returns_its_message_id_and_what_was_sent(conn, discord_double):
    result = discord.post(conn, "approvals", "**A-0001 · fake** · decide by Tue 10 Nov", dedupe=False, wait=True)
    assert result.delivered
    (post,) = discord_double.posts("approvals")
    assert "wait=true" in post.url
    assert result.message_ids == [post.message_id]
    assert result.pieces == ["**A-0001 · fake** · decide by Tue 10 Nov"]


def test_a_long_waited_post_returns_one_id_per_piece(conn, discord_double):
    text = "\n".join(f"line {n} " + "x" * 90 for n in range(40))
    result = discord.post(conn, "approvals", text, dedupe=False, wait=True)
    posts = discord_double.posts("approvals")
    assert len(posts) == len(result.message_ids) == len(result.pieces) > 1
    assert result.message_ids == [p.message_id for p in posts]


def test_a_post_without_wait_asks_for_no_message_id(conn, discord_double):
    result = discord.post(conn, "approvals", "plain", dedupe=False)
    assert "wait" not in discord_double.posts("approvals")[0].url
    assert result.message_ids == []


def test_edit_patches_the_message_masked_and_mentioning_nobody(conn, discord_double):
    result = discord.edit(conn, "approvals", "1234", "Approved @everyone, call +65 9123 4567")
    assert result.delivered
    (patch,) = [r for r in discord_double.requests if r.method == "PATCH"]
    assert patch.url.endswith("/messages/1234")
    assert patch.channel == "approvals"
    assert "9123" not in (patch.content or "")
    assert patch.allowed_mentions == {"parse": []}
    assert discord_double.posts() == []


def test_an_edit_that_fails_reports_not_delivered_and_writes_no_outbox(conn, discord_double, tmp_path):
    discord_double.mode = "edit-fails"
    result = discord.edit(conn, "approvals", "1234", "Approved")
    assert not result.delivered
    assert "404" in result.reason
    assert not (tmp_path / "data" / "discord-outbox").exists()


def test_an_edit_with_no_webhook_is_not_delivered(conn):
    result = discord.edit(conn, "approvals", "1234", "Approved")
    assert not result.delivered


def test_an_unreachable_discord_fails_the_edit_without_raising(conn, discord_double):
    discord_double.mode = "unreachable"
    assert not discord.edit(conn, "approvals", "1234", "Approved").delivered
