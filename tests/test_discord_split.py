"""A long message stays readable when it splits (technical review B2, functional B1).

A social post sits in a code fence on its approval card, and a deep post passes Discord's 2000
characters. `discord.split` keeps every fence balanced, and `discord.post` keeps room in the first
piece and can put the files on it, beside the buttons.
"""

from __future__ import annotations

import pytest

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import discord, paths
from jura_growth.agents.social import checks
from test_social import FB, IG


def post_lines(count: int = 60, width: int = 70) -> list[str]:
    return [f"line {n:03d} " + "x" * width for n in range(count)]


def card(lines: list[str]) -> str:
    return "**A-0001 · social post** · decide by Tue 10 Nov, 17:00 SGT\nTitle\n```\n" + "\n".join(lines) + "\n```\nAnswer: Approve"


def inside(pieces: list[str]) -> list[str]:
    """Every line the pieces show, leaving out the fence lines the split added or kept."""
    return [line for piece in pieces for line in piece.split("\n") if line != "```"]


def test_a_short_message_is_left_alone():
    assert discord.split("one\n```\ntwo\n```") == ["one\n```\ntwo\n```"]


def test_a_message_with_no_fence_splits_at_lines_as_before():
    text = "\n".join(post_lines())
    pieces = discord.split(text)
    assert len(pieces) > 1 and all(len(p) <= discord.MAX_CONTENT for p in pieces)
    assert "\n".join(pieces) == text
    assert not any("```" in p for p in pieces)


def test_each_piece_of_a_split_fence_is_balanced_and_nothing_is_lost():
    lines = post_lines()
    pieces = discord.split(card(lines))
    assert len(pieces) >= 2
    for piece in pieces:
        assert len(piece) <= discord.MAX_CONTENT
        assert piece.count("```") % 2 == 0, piece
    assert inside(pieces) == ["**A-0001 · social post** · decide by Tue 10 Nov, 17:00 SGT", "Title", *lines, "Answer: Approve"]


def test_the_text_after_the_fence_is_plain_on_its_own_piece():
    pieces = discord.split(card(post_lines()))
    assert pieces[-1].endswith("```\nAnswer: Approve")
    assert pieces[-1].startswith("```\n")


@pytest.mark.parametrize("filler", range(1930, 2010))
def test_a_split_near_either_fence_line_leaves_no_empty_block(filler):
    """Move the fence lines across the 2000 boundary one character at a time."""
    head = "h" * (filler - 200)
    text = f"{head}\n" + "\n".join(["a" * 90] * 2) + "\n```\n" + "b" * 90 + "\n```\n" + "c" * 90
    for piece in discord.split(text):
        assert len(piece) <= discord.MAX_CONTENT
        assert piece.count("```") % 2 == 0, piece
        assert "```\n```" not in piece, piece


def test_a_fence_opening_on_the_last_line_of_a_piece_moves_to_the_next():
    head = "h" * 1990
    pieces = discord.split(f"{head}\n```\nbody\n```")
    assert pieces == [head, "```\nbody\n```"]


def test_a_closing_fence_fits_where_its_room_was_kept():
    body = "b" * 1990
    pieces = discord.split(f"```\n{body}\n```\nafter")
    assert pieces[0].endswith("```") and pieces[0].count("```") == 2
    assert len(pieces[0]) <= discord.MAX_CONTENT


def test_a_line_longer_than_a_piece_is_cut_and_stays_fenced():
    long = "z" * 4500
    pieces = discord.split(f"```\n{long}\n```")
    assert len(pieces) == 3
    for piece in pieces:
        assert len(piece) <= discord.MAX_CONTENT
        assert piece.startswith("```\n") and piece.endswith("\n```")
    assert "".join(p.removeprefix("```\n").removesuffix("\n```") for p in pieces) == long


def test_first_piece_room_shortens_only_the_first():
    text = "\n".join(post_lines())
    pieces = discord.split(text, first_room=120)
    assert len(pieces[0]) <= discord.MAX_CONTENT - 120
    assert any(len(p) > discord.MAX_CONTENT - 120 for p in pieces[1:])
    assert "\n".join(pieces) == text


def test_first_piece_room_splits_a_message_that_would_otherwise_just_fit():
    text = "\n".join(["y" * 99] * 19)  # 1899 characters
    assert discord.split(text) == [text]
    assert len(discord.split(text, first_room=120)) == 2


# --- discord.post ---------------------------------------------------------------------------


def engine_png(name: str = "picture.png"):
    import struct
    import zlib

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", 10, 10, 8, 2, 0, 0, 0)
    path = paths.data_dir() / "work" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b""))
    return path


def test_a_post_keeps_first_piece_room_when_asked(conn, discord_double):
    result = discord.post(conn, "approvals", card(post_lines()), dedupe=False, wait=True, first_piece_room=120)
    assert len(result.pieces[0]) <= discord.MAX_CONTENT - 120
    assert all(p.count("```") % 2 == 0 for p in result.pieces)


def test_files_go_on_the_last_piece_by_default(conn, discord_double):
    discord.post(conn, "approvals", card(post_lines()), files=[engine_png()], dedupe=False, wait=True)
    posts = discord_double.posts("approvals")
    assert len(posts) >= 2 and posts[0].files == [] and posts[-1].files


def test_files_first_puts_them_beside_the_buttons(conn, discord_double):
    buttons = [{"type": 1, "components": []}]
    discord.post(conn, "approvals", card(post_lines()), files=[engine_png()], dedupe=False, wait=True,
                 components=buttons, files_first=True)
    posts = discord_double.posts("approvals")
    assert len(posts) >= 2
    assert posts[0].files and posts[0].components == buttons
    assert all(p.files == [] and p.components is None for p in posts[1:])


# --- a post can't close the card's fence ------------------------------------------------------


@pytest.mark.parametrize("line", ["```", "  ```", "```python"])
def test_a_bare_fence_line_in_a_post_is_refused(line):
    found = [what for pattern, what in checks.MARKDOWN_RE if pattern.search(f"First line.\n{line}\nLast line.")]
    assert found == ["a code fence"]


@pytest.mark.parametrize("variant", [FB, IG])
def test_the_fixture_posts_carry_no_fence(variant):
    assert not any(pattern.search(variant) for pattern, what in checks.MARKDOWN_RE)
