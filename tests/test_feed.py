"""One line in the agent's feed when a decision lands (PRD FD1 to FD4, `reviews/functional.md` §3).

Tested through `cards.sweep()`, with the fake kind and the Discord double (technical review, ticket
02 seams): a test on `feed.line` alone would pin its shape and miss the wiring.
"""

from __future__ import annotations

import pytest

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, discord, feed, locks, paths

FEED = "community"  # any channel the double listens on; the fake kind names it


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    monkeypatch.setattr(aw.FakeKind, "feed_channel", FEED, raising=False)
    monkeypatch.setattr(aw.FakeKind, "feed_approved", "It goes out soon.", raising=False)
    return world


def posted(conn, world, double, text="Quotes that write themselves"):
    approval = aw.request(conn, aw.KIND, world.item(text))
    assert cards.sweep(conn) == 1
    return approval


def lines(double) -> list[str]:
    return double.contents(FEED)


# --- FD1: one line per change, named as the card named it ------------------------------------


def test_an_approval_posts_one_line_with_the_cards_title_and_the_next_step(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    assert lines(discord_double) == []
    aw.approve(conn, approval)
    cards.sweep(conn)
    assert lines(discord_double) == [f"**{approval.id} approved** · fake item {approval.subject}\nIt goes out soon."]


def test_a_skip_posts_one_line(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.skip(conn, approval)
    cards.sweep(conn)
    assert lines(discord_double) == [f"**{approval.id} skipped** · fake item {approval.subject}"]


def test_an_expiry_posts_one_line_saying_why(conn, world, discord_double, monkeypatch):
    approval = posted(conn, world, discord_double)
    aw.at(monkeypatch, approval.decide_by)
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert lines(discord_double) == [f"**{approval.id} expired** · fake item {approval.subject}\nNot approved in time."]


def test_approved_then_lapsed_posts_a_line_for_each_change(conn, world, discord_double, monkeypatch):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    aw.at(monkeypatch, aw.get(conn, approval.id).use_by)
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert [line.split("\n")[0].split(" · ")[0] for line in lines(discord_double)] == [
        f"**{approval.id} approved**", f"**{approval.id} expired**"]
    assert lines(discord_double)[1].endswith("Approved but not used in time.")


def test_approved_then_skipped_posts_a_line_for_each_change(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    aw.skip(conn, approval)
    cards.sweep(conn)
    assert [line.split(" · ")[0] for line in lines(discord_double)] == [
        f"**{approval.id} approved**", f"**{approval.id} skipped**"]


def test_further_sweeps_add_nothing(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    cards.sweep(conn)
    cards.sweep(conn)
    assert len(lines(discord_double)) == 1


def test_an_item_gone_with_nothing_replacing_it_posts_one_line_in_the_cards_words(conn, world, discord_double, monkeypatch):
    approval = posted(conn, world, discord_double)
    monkeypatch.setattr(aw.FakeKind, "superseded_note", lambda self, conn, subject: "lead unsubscribed", raising=False)
    del world.items[approval.subject]
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert lines(discord_double) == [
        f"**{approval.id} withdrawn** · fake item {approval.subject}\nThe request closed: lead unsubscribed."]


def test_a_request_that_never_had_a_card_posts_no_line(conn, world, discord_double, monkeypatch):
    """Amended FD1 (technical N5): the one-pager lists the unposted."""
    approval = aw.request(conn, aw.KIND, world.item())
    aw.skip(conn, approval)  # decided before any sweep, so it never gets a card
    cards.sweep(conn)
    assert discord_double.posts("approvals") == [] and lines(discord_double) == []


def test_a_line_mentions_nobody_notifies_nobody_and_shows_no_link_preview(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    [line] = discord_double.posts(FEED)
    assert line.allowed_mentions == {"parse": []}
    assert line.flags == discord.SUPPRESS_EMBEDS | discord.SUPPRESS_NOTIFICATIONS


# --- FD2: what stays silent --------------------------------------------------------------------


def test_a_request_superseded_with_a_successor_posts_no_line(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    world.items[approval.subject] = "new words"
    fresh = aw.request(conn, aw.KIND, approval.subject)
    assert fresh is not None and fresh.supersedes == approval.number
    cards.sweep(conn)
    assert lines(discord_double) == []


def test_a_request_superseded_on_changed_content_posts_no_line_before_its_successor_exists(conn, world, discord_double):
    """B1: `expire_due()` supersedes without raising, and sweeps straight away."""
    approval = posted(conn, world, discord_double)
    world.items[approval.subject] = "new words"
    approvals.expire_due(conn)
    assert approvals.successor(conn, aw.get(conn, approval.id)) is None
    cards.sweep(conn)
    assert lines(discord_double) == []
    assert aw.get(conn, approval.id).status == approvals.SUPERSEDED


def test_the_content_changing_after_an_approval_posts_no_second_line(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    world.items[approval.subject] = "new words"
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert len(lines(discord_double)) == 1


def test_a_claim_after_an_approval_posts_no_line(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    assert world.act(conn, approval.subject) is None
    cards.sweep(conn)
    assert len(lines(discord_double)) == 1


# --- FD3: applied on decide ---------------------------------------------------------------------


def test_a_decision_claimed_before_the_sweep_reports_as_approved_once(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    assert world.act(conn, approval.subject) is None  # pending to used, as far as the card knows
    cards.sweep(conn)
    cards.sweep(conn)
    assert lines(discord_double) == [f"**{approval.id} approved** · fake item {approval.subject}\nIt goes out soon."]


# --- the next step can read the world ----------------------------------------------------------


def test_a_kind_may_work_out_its_next_step(conn, world, discord_double, monkeypatch):
    monkeypatch.setattr(aw.FakeKind, "feed_approved", lambda self, conn, subject: f"Next for {subject}.", raising=False)
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    assert lines(discord_double)[0].endswith(f"\nNext for {approval.subject}.")


def test_a_failing_next_step_still_posts_the_line(conn, world, discord_double, monkeypatch):
    def broken(self, conn, subject):
        raise RuntimeError("no such row")

    monkeypatch.setattr(aw.FakeKind, "feed_approved", broken, raising=False)
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    assert lines(discord_double) == [f"**{approval.id} approved** · fake item {approval.subject}"]
    assert aw.events(conn, "approval.feed_error")


# --- FD4: a feed failure holds nothing up -------------------------------------------------------


def feed_in_mode(monkeypatch, double, mode: str) -> None:
    """The feed's channel answers in `mode`, and #approvals goes on working."""
    real = discord.post

    def post(conn, channel, *args, **kwargs):
        double.mode = mode if channel == FEED else "accept"
        try:
            return real(conn, channel, *args, **kwargs)
        finally:
            double.mode = "accept"

    monkeypatch.setattr(discord, "post", post)


@pytest.mark.parametrize("mode", ["500", "429", "unreachable"])
def test_a_failing_feed_never_holds_up_the_sweep_or_the_decision(conn, world, discord_double, monkeypatch, mode):
    first = aw.request(conn, aw.KIND, world.item("one"))
    second = aw.request(conn, aw.KIND, world.item("two"))
    cards.sweep(conn)
    aw.approve(conn, first)
    aw.approve(conn, second)
    feed_in_mode(monkeypatch, discord_double, mode)
    cards.sweep(conn)

    shown = {row["approval_id"]: row["shows"] for row in conn.execute("SELECT approval_id, shows FROM approval_cards")}
    assert shown == {first.number: approvals.APPROVED, second.number: approvals.APPROVED}
    assert aw.get(conn, first.id).status == approvals.APPROVED
    outbox = list((paths.data_dir() / "discord-outbox").glob("*.jsonl"))
    assert outbox and sum(1 for _ in outbox[0].open()) == 2


def test_a_post_that_raises_is_logged_and_the_card_still_moves_on(conn, world, discord_double, monkeypatch):
    first = aw.request(conn, aw.KIND, world.item("one"))
    second = aw.request(conn, aw.KIND, world.item("two"))
    cards.sweep(conn)
    aw.approve(conn, first)
    aw.approve(conn, second)
    real = discord.post

    def raises(conn, channel, *args, **kwargs):
        if channel == FEED:
            raise RuntimeError("the feed is on fire")
        return real(conn, channel, *args, **kwargs)

    monkeypatch.setattr(discord, "post", raises)
    cards.sweep(conn)
    assert len(aw.events(conn, "approval.feed_error")) == 2
    shown = {row["approval_id"]: row["shows"] for row in conn.execute("SELECT approval_id, shows FROM approval_cards")}
    assert shown == {first.number: approvals.APPROVED, second.number: approvals.APPROVED}


def test_a_feed_line_waits_at_most_five_seconds(conn, world, discord_double, monkeypatch):
    """N4: Dispatch's call times out at 60 seconds, and a decision's sweep runs inside it."""
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    slept = []
    monkeypatch.setattr(discord.time, "sleep", slept.append)
    monkeypatch.setattr(discord, "_retry_after", lambda response: 10.0)
    feed_in_mode(monkeypatch, discord_double, "429")
    cards.sweep(conn)
    [line] = discord_double.posts(FEED)  # a ten-second wait doesn't fit, so one attempt
    assert line.timeout is not None and max(line.timeout.values()) <= feed.PATIENCE
    assert slept == []


def test_a_short_rate_limit_is_waited_out_inside_the_five_seconds(conn, world, discord_double, monkeypatch):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    feed_in_mode(monkeypatch, discord_double, "429")
    cards.sweep(conn)
    assert len(discord_double.posts(FEED)) == 3  # the double asks for 0.01 seconds each time


def test_ordinary_posts_keep_their_retries(conn, discord_double):
    discord_double.mode = "500"
    assert not discord.post(conn, "alerts", "x", dedupe=False).delivered
    assert len(discord_double.posts("alerts")) == 3


# --- which feed each kind reports to (FD1's table over the real kinds) -----------------------------


FD1_CHANNELS = {
    "social-post": "social-drafts",
    "outreach-email": "outreach-sent",
    "app-build": "app-factory",
    "app-release": "app-factory",
    "group-rules": "community",
    "community-post": "community",
    "group-join": "community",
}


def test_every_real_kind_names_its_feed_and_a_new_kind_fails_here_until_it_does():
    found = {name: feed.channel_for(registered) for name, registered in approvals.kinds().items()}
    assert found == FD1_CHANNELS


def test_every_feed_is_a_channel_discord_knows():
    assert set(FD1_CHANNELS.values()) <= set(discord.channels())


# --- the sweep's other paths (test strategy R4) -----------------------------------------------------


def test_a_failed_edit_gives_one_follow_up_and_still_one_line(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    discord_double.mode = "edit-fails"
    cards.sweep(conn)
    cards.sweep(conn)
    assert [m for m in discord_double.contents("approvals") if "couldn't be edited" in m] != []
    assert len([m for m in discord_double.contents("approvals") if "couldn't be edited" in m]) == 1
    assert len(lines(discord_double)) == 1


def test_a_sweep_that_finds_the_lock_held_posts_no_line_and_the_next_posts_one(conn, world, discord_double):
    approval = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    with locks.held(cards.LOCK) as acquired:
        assert acquired
        cards.sweep(conn)
        assert lines(discord_double) == []
    cards.sweep(conn)
    cards.sweep(conn)
    assert len(lines(discord_double)) == 1
