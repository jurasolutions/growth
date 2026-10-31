"""The sweep over approval cards (AC-M11.1, AC-M12.1 owned by ticket 02; run here for 04b's cards).

Datasets D2 (secrets) and D3 (personal data) are planted in everything a card reads: the
preview's title, reason and text, an attached text file, and the follow-up line a failed edit
posts. Cards, edits and follow-ups then go through the Discord double, and `assert_clean` finds
none of it.
"""

from __future__ import annotations

import pytest

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, discord, paths, timeutil
from sweep import NAMED_ADDRESS, SOURCE_PAGE, assert_clean, d2_secrets, outbox_dir, planted  # noqa: F401


@pytest.fixture(autouse=True)
def _secrets(d2_secrets):
    """Every test here runs with the D2 env file and the Keychain double."""


def contact_lead(conn) -> None:
    """A lead whose named contact teaches the masking who Jane Tan is."""
    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
        " status, created_at, updated_at) VALUES (233, 'Example Pte Ltd', 'Example', 'example.com.sg',"
        " 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', ?, ?)",
        (timeutil.stamp(), timeutil.stamp()),
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        " VALUES (233, ?, 'h', ?, 'named', 1, ?, ?)",
        (NAMED_ADDRESS, SOURCE_PAGE, timeutil.stamp(), timeutil.stamp()),
    )


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    contact_lead(conn)
    text = planted().text()
    attachment = paths.data_dir() / "work" / "cards" / "planted.txt"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text(text)

    def preview(self, conn, subject):
        return approvals.Preview(title=f"For {NAMED_ADDRESS}: {text.splitlines()[1]}", text=self.world.items[subject],
                                 reason=f"asked by {text}", files=(attachment,))

    monkeypatch.setattr(aw.FakeKind, "preview", preview)
    return world


def test_a_posted_card_carries_nothing_planted(conn, world, discord_double):
    aw.request(conn, aw.KIND, world.item(planted().text()))
    assert cards.sweep(conn) == 1
    assert_clean(discord_double, outbox_dir(), planted())


def test_an_edited_card_and_a_follow_up_line_carry_nothing_planted(conn, world, discord_double, monkeypatch):
    first = aw.request(conn, aw.KIND, world.item(planted().text()))
    second = aw.request(conn, aw.KIND, world.item(planted().text() + " (two)"))
    cards.sweep(conn)
    aw.approve(conn, first)
    cards.sweep(conn)  # an edit
    discord_double.mode = "edit-fails"
    aw.skip(conn, second)
    cards.sweep(conn)  # a follow-up line
    methods = [r.method for r in discord_double.requests]
    assert methods.count("PATCH") == 2 and methods.count("POST") == 3
    assert_clean(discord_double, outbox_dir(), planted())


def test_a_card_that_failed_to_post_leaves_nothing_planted_in_the_outbox(conn, world, discord_double):
    aw.request(conn, aw.KIND, world.item(planted().text()))
    discord_double.mode = "500"
    cards.sweep(conn)
    assert list(outbox_dir().glob("*.jsonl"))
    assert_clean(discord_double, outbox_dir(), planted())


# --- feed lines (AC-M11, required by `reviews/technical.md`, ticket 02) ------------------------


FEED = "community"


@pytest.fixture
def feed_world(world, monkeypatch):
    """The fake kind reports to a feed, and every word it can add there is planted."""
    text = planted().text()
    monkeypatch.setattr(aw.FakeKind, "feed_channel", FEED, raising=False)
    monkeypatch.setattr(aw.FakeKind, "feed_approved", lambda self, conn, subject: text, raising=False)
    monkeypatch.setattr(aw.FakeKind, "superseded_note", lambda self, conn, subject: text, raising=False)
    return world


def test_a_feed_line_for_every_change_carries_nothing_planted(conn, feed_world, discord_double, monkeypatch):
    world = feed_world
    approved = aw.request(conn, aw.KIND, world.item("approved"))
    skipped = aw.request(conn, aw.KIND, world.item("skipped"))
    lapsed = aw.request(conn, aw.KIND, world.item("lapsed"))
    gone = aw.request(conn, aw.KIND, world.item("gone"))
    cards.sweep(conn)
    aw.approve(conn, approved)
    aw.skip(conn, skipped)
    del world.items[gone.subject]
    approvals.expire_due(conn)
    cards.sweep(conn)
    aw.at(monkeypatch, lapsed.decide_by)
    approvals.expire_due(conn)
    cards.sweep(conn)
    lines = discord_double.contents(FEED)
    assert len(lines) == 4
    assert sum(planted().marker in line for line in lines) == 2  # the next step, and the closing note
    assert_clean(discord_double, outbox_dir(), planted())


def test_a_feed_line_whose_title_falls_back_to_the_requests_reason_carries_nothing_planted(conn, feed_world, discord_double, monkeypatch):
    text = planted().text()

    def preview(self, conn, subject):
        return approvals.Preview(title="", text="body", reason="a test asked")

    monkeypatch.setattr(aw.FakeKind, "preview", preview)
    approval = approvals.request(conn, aw.KIND, feed_world.item("fallback"), reason=f"asked by {text}", run_id=None)
    cards.sweep(conn)
    aw.skip(conn, approval)
    cards.sweep(conn)
    [line] = discord_double.contents(FEED)
    assert planted().marker in line
    assert_clean(discord_double, outbox_dir(), planted())


def test_a_feed_line_from_a_card_that_split_carries_nothing_planted(conn, feed_world, discord_double, monkeypatch):
    long = "\n".join(f"line {n} " + "x" * 70 for n in range(60))
    approval = aw.request(conn, aw.KIND, feed_world.item(planted().text() + "\n" + long))
    cards.sweep(conn)
    assert len(discord_double.posts("approvals")) >= 2
    aw.approve(conn, approval)
    cards.sweep(conn)
    assert len(discord_double.contents(FEED)) == 1
    assert_clean(discord_double, outbox_dir(), planted())


def test_a_feed_line_saved_to_the_outbox_carries_nothing_planted(conn, feed_world, discord_double, monkeypatch):
    approval = aw.request(conn, aw.KIND, feed_world.item(planted().text()))
    cards.sweep(conn)
    aw.approve(conn, approval)
    real = discord.post

    def feed_down(conn, channel, *args, **kwargs):
        discord_double.mode = "500" if channel == FEED else "accept"
        try:
            return real(conn, channel, *args, **kwargs)
        finally:
            discord_double.mode = "accept"

    monkeypatch.setattr(discord, "post", feed_down)
    cards.sweep(conn)
    assert list(outbox_dir().glob("*.jsonl"))
    assert_clean(discord_double, outbox_dir(), planted())
