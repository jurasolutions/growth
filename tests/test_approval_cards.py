"""Approval cards in #approvals (MC §4.6 A12, §5.6; ticket 04b).

AC-M5.2 (the posting sweep and `posted_at`), AC-M5.3 (the first line edited in place), AC-M5.5
(eleven files refused before posting) and gate case G28, through `cards.sweep()` (A12's
`post_unposted`) with the fake kind and the Discord double.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, discord, locks, paths


@pytest.fixture
def world(conn, monkeypatch):
    world = aw.install(monkeypatch)
    aw.prepare(conn)
    aw.at(monkeypatch, aw.NOW)
    return world


def raised(conn, world, text="Quotes that write themselves"):
    return aw.request(conn, aw.KIND, world.item(text))


def patches(double):
    return [r for r in double.requests if r.method == "PATCH"]


# --- posting (AC-M5.2, G28) ----------------------------------------------------------


def test_a_pending_request_is_posted_once_and_marked_posted(conn, world, discord_double):
    approval = raised(conn, world)
    assert cards.sweep(conn) == 1
    (card,) = discord_double.posts("approvals")
    assert "wait=true" in card.url
    record = aw.get(conn, approval.id)
    assert record.posted_at == aw.NOW
    assert record.message_id == card.message_id
    assert cards.sweep(conn) == 0
    assert len(discord_double.posts("approvals")) == 1
    (posted,) = aw.events(conn, "approval.posted")
    assert posted["approval"] == approval.id and posted["message_id"] == card.message_id


def test_the_card_says_what_why_when_and_how_to_answer(conn, world, discord_double):
    approval = raised(conn, world)
    cards.sweep(conn)
    (card,) = discord_double.contents("approvals")
    lines = card.splitlines()
    # No code: decisions come only from #approvals through Dispatch (ADR 0004).
    assert lines[0] == f"**{approval.id} · fake** · decide by Thu 12 Nov, 10:02 SGT"
    assert approval.content_hash[:6] not in card
    assert lines[1] == f"fake item {approval.subject}"
    assert lines[2] == "Why: a test asked"
    assert "Quotes that write themselves" in lines
    # The fake kind takes decision arguments, so the answer is typed.
    assert lines[-1] == f"Answer: /growth approve {approval.id} promo_days=… post_days=…, or /growth skip {approval.id}"


def test_a_kind_without_decision_arguments_offers_approve_and_skip(conn, world, discord_double, monkeypatch):
    monkeypatch.setattr(aw.FakeKind, "decision_args", ())
    approval = raised(conn, world)
    cards.sweep(conn)
    assert discord_double.contents("approvals")[0].splitlines()[-1] == f"Answer: Approve / Skip, or /growth approve {approval.id}"


def test_cards_mention_nobody(conn, world, discord_double):
    raised(conn, world, "Hello @everyone and <@123>")
    cards.sweep(conn)
    (card,) = discord_double.posts("approvals")
    assert card.allowed_mentions == {"parse": []}


def test_a_post_that_fails_after_the_commit_is_posted_once_by_the_next_sweep(conn, world, discord_double):
    approval = raised(conn, world)
    discord_double.mode = "500"
    assert cards.sweep(conn) == 0
    assert aw.get(conn, approval.id).posted_at is None
    discord_double.mode = "accept"
    discord_double.requests.clear()
    assert cards.sweep(conn) == 1
    assert cards.sweep(conn) == 0
    assert len(discord_double.posts("approvals")) == 1
    assert aw.get(conn, approval.id).posted_at is not None


def test_with_no_approvals_webhook_nothing_is_posted_or_saved_and_it_stays_unposted(conn, world, tmp_path):
    approval = raised(conn, world)
    assert cards.sweep(conn) == 0
    assert aw.get(conn, approval.id).posted_at is None
    assert not (tmp_path / "data" / "discord-outbox").exists()


def test_only_pending_requests_are_posted(conn, world, discord_double):
    approval = raised(conn, world)
    aw.approve(conn, approval)
    skipped = raised(conn, world, "another")
    aw.skip(conn, skipped)
    assert cards.sweep(conn) == 0
    assert discord_double.posts() == []


def test_a_request_whose_kind_isnt_loaded_is_left_unposted(conn, world, discord_double, monkeypatch):
    approval = raised(conn, world)
    monkeypatch.setattr(approvals.agents, "plugins", aw.REAL_PLUGINS)
    assert cards.sweep(conn) == 0
    assert aw.get(conn, approval.id).posted_at is None


def test_a_second_sweep_running_at_the_same_time_posts_nothing(conn, world, discord_double):
    raised(conn, world)
    with locks.held("approval-cards") as acquired:
        assert acquired
        assert cards.sweep(conn) == 0
    assert discord_double.posts() == []
    assert cards.sweep(conn) == 1


# --- files (AC-M5.5) -------------------------------------------------------------------


def _images(count: int):
    folder = paths.data_dir() / "work" / "cards"
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for n in range(count):
        path = folder / f"note-{n}.txt"
        path.write_text(f"attachment {n}")
        made.append(path)
    return tuple(made)


def _with_files(monkeypatch, files):
    real = aw.FakeKind.preview

    def preview(self, conn, subject):
        shown = real(self, conn, subject)
        return approvals.Preview(title=shown.title, text=shown.text, reason=shown.reason, files=files)

    monkeypatch.setattr(aw.FakeKind, "preview", preview)


def test_a_card_with_eleven_files_is_refused_before_anything_is_posted(conn, world, discord_double, monkeypatch):
    _with_files(monkeypatch, _images(11))
    approval = raised(conn, world)
    assert cards.sweep(conn) == 0
    assert discord_double.requests == []
    assert aw.get(conn, approval.id).posted_at is None
    (refused,) = aw.events(conn, "approval.card_refused")
    assert refused["approval"] == approval.id and "11 files" in refused["why"]


def test_a_card_with_ten_files_attaches_all_ten(conn, world, discord_double, monkeypatch):
    _with_files(monkeypatch, _images(10))
    raised(conn, world)
    assert cards.sweep(conn) == 1
    (card,) = discord_double.posts("approvals")
    assert len(card.files) == 10


# --- edits in place (AC-M5.3, G28) -----------------------------------------------------


def posted(conn, world, double, text="Quotes that write themselves"):
    approval = raised(conn, world, text)
    cards.sweep(conn)
    (card,) = double.posts("approvals")
    double.requests.clear()
    return aw.get(conn, approval.id), card


def edited_to(double, card) -> str:
    (patch,) = patches(double)
    # With post_buttons on, an edit also sends `?with_components=true` to clear or keep the buttons.
    assert patch.url.split("?", 1)[0].endswith(f"/messages/{card.message_id}")
    assert double.posts() == [], "an edit posts no new message"
    return patch.content or ""


def test_an_approval_edits_the_first_line_and_keeps_the_rest(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    content = edited_to(discord_double, card)
    assert content.splitlines()[0] == f"**{approval.id} · fake** · Approved by Ting Yu, 10:02 SGT"
    assert content.splitlines()[1:] == (card.content or "").splitlines()[1:]


def test_a_skip_edits_the_card(conn, world, discord_double, monkeypatch):
    approval, card = posted(conn, world, discord_double)
    aw.at(monkeypatch, "2026-11-10T10:05:00+08:00")
    aw.skip(conn, approval)
    cards.sweep(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Skipped by Ting Yu, 10:05 SGT"


def test_a_lapse_edits_the_card(conn, world, discord_double, monkeypatch):
    approval, card = posted(conn, world, discord_double)
    now = aw.at(monkeypatch, approval.decide_by)
    approvals.expire_due(conn, now)
    cards.sweep(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Expired: not approved in time"


def test_a_supersede_edits_the_card_and_names_the_new_request(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    world.items[approval.subject] += " (changed)"
    newer = aw.request(conn, aw.KIND, approval.subject)
    cards.sweep(conn)
    (patch,) = patches(discord_double)
    assert patch.content.splitlines()[0] == f"**{approval.id} · fake** · Superseded: the content changed; see {newer.id}"
    # The new request gets its own card.
    (new_card,) = discord_double.posts("approvals")
    assert new_card.content.startswith(f"**{newer.id} · fake**")


def test_an_item_that_is_gone_edits_the_card(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    del world.items[approval.subject]
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Superseded: the item is gone"


def test_a_claim_edits_the_card_once_more(conn, world, discord_double, monkeypatch):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    aw.at(monkeypatch, "2026-11-10T10:30:00+08:00")
    assert world.act(conn, approval.subject, run_id=aw.run(conn)) is None
    cards.sweep(conn)
    assert edited_to(discord_double, card).splitlines()[0] == (
        f"**{approval.id} · fake** · Approved by Ting Yu, 10:02 SGT · claimed at 10:30 SGT"
    )


def test_a_card_is_edited_once_per_change(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    cards.sweep(conn)
    cards.sweep(conn)
    assert len(patches(discord_double)) == 1


def test_a_failed_edit_posts_one_follow_up_line_instead(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    discord_double.mode = "edit-fails"
    cards.sweep(conn)
    cards.sweep(conn)
    assert len(patches(discord_double)) == 1
    (follow_up,) = discord_double.posts("approvals")
    assert follow_up.content == f"{approval.id}: Approved by Ting Yu, 10:02 SGT (the card couldn't be edited)."
    assert follow_up.allowed_mentions == {"parse": []}


def test_an_unchanged_card_is_never_edited(conn, world, discord_double):
    posted(conn, world, discord_double)
    cards.sweep(conn)
    assert discord_double.requests == []


# --- the kind's own words for a supersede (Sp1; MC-06 fills them for outreach) ---------


def test_a_kind_may_say_why_its_item_was_superseded(conn, world, discord_double, monkeypatch):
    monkeypatch.setattr(aw.FakeKind, "superseded_note", lambda self, conn, subject: "lead unsubscribed", raising=False)
    approval, card = posted(conn, world, discord_double)
    del world.items[approval.subject]
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Superseded: lead unsubscribed"


def test_a_failing_supersede_note_falls_back_to_the_cores_reason(conn, world, discord_double, monkeypatch):
    def broken(self, conn, subject):
        raise RuntimeError("no lead")

    monkeypatch.setattr(aw.FakeKind, "superseded_note", broken, raising=False)
    approval, card = posted(conn, world, discord_double)
    del world.items[approval.subject]
    approvals.expire_due(conn)
    cards.sweep(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Superseded: the item is gone"
    assert aw.events(conn, "approval.card_note_error")


# --- sweep_safely: for callers whose own work must stand ------------------------------


def test_a_failing_sweep_is_logged_never_raised(conn, world, monkeypatch):
    monkeypatch.setattr(cards, "_edit_changed", lambda conn: (_ for _ in ()).throw(RuntimeError("sweep broke")))
    monkeypatch.setattr(cards.discord, "webhook", lambda channel: "https://discord.invalid/x")
    assert cards.sweep_safely(conn) == 0
    (error,) = aw.events(conn, "approval.cards_error")
    assert "sweep broke" in error["error"]


def test_editing_only_posts_no_new_card(conn, world, discord_double):
    raised(conn, world)
    assert cards.sweep(conn, post=False) == 0
    assert discord_double.requests == []


def test_decide_by_and_use_by_one_second_apart_still_post_the_card(conn, world, discord_double):
    world.decide_in = timedelta(seconds=1)
    raised(conn, world)
    assert cards.sweep(conn) == 1


# --- a long card (technical review B2, N7; functional B1) ------------------------------------


def _long_post(monkeypatch, files=()):
    lines = [f"line {n:03d} " + "x" * 70 for n in range(60)]
    text = "```\n" + "\n".join(lines) + "\n```"

    def preview(self, conn, subject):
        return approvals.Preview(title="a long post", text=text, reason="a test asked", files=tuple(files))

    monkeypatch.setattr(aw.FakeKind, "preview", preview)
    return lines


def test_a_long_card_splits_with_its_fence_balanced_and_its_images_on_the_first_piece(conn, world, discord_double, monkeypatch):
    lines = _long_post(monkeypatch, files=_images(3))
    raised(conn, world)
    assert cards.sweep(conn) == 1
    posts = discord_double.posts("approvals")
    assert len(posts) >= 2
    assert [name for name, _ in posts[0].files] == [f"note-{n}.txt" for n in range(3)]
    assert all(p.files == [] for p in posts[1:])
    assert all((p.content or "").count("```") % 2 == 0 for p in posts)
    shown = [line for p in posts for line in (p.content or "").split("\n")]
    assert [line for line in shown if line.startswith("line ")] == lines


def test_an_edit_of_a_nearly_full_first_piece_keeps_its_closing_fence(conn, world, discord_double, monkeypatch):
    _long_post(monkeypatch)
    approval = raised(conn, world)
    cards.sweep(conn)
    first = discord_double.posts("approvals")[0].content or ""
    assert len(first) <= discord.MAX_CONTENT - cards.HEADER_ROOM
    # The longest first line a card can come to show: a claim, with both times.
    aw.approve(conn, approval)
    cards.sweep(conn)
    (edit,) = patches(discord_double)
    assert (edit.content or "").endswith("\n```") and (edit.content or "").count("```") % 2 == 0
    assert (edit.content or "").split("\n", 1)[1] == first.split("\n", 1)[1]


def test_when_a_later_piece_fails_the_earlier_ones_are_deleted_and_the_next_sweep_posts_it_whole(conn, world, discord_double, monkeypatch):
    _long_post(monkeypatch)
    approval = raised(conn, world)
    discord_double.fail_posts_after = 1
    assert cards.sweep(conn) == 0
    (orphan, *_) = discord_double.posts("approvals")
    deleted = [r for r in discord_double.requests if r.method == "DELETE"]
    assert [r.message_id for r in deleted] == [orphan.message_id]
    assert aw.get(conn, approval.id).posted_at is None

    discord_double.fail_posts_after = None
    discord_double.requests.clear()
    assert cards.sweep(conn) == 1
    assert len(discord_double.posts("approvals")) >= 2
    assert aw.get(conn, approval.id).message_id == discord_double.posts("approvals")[0].message_id


def test_a_failed_delete_holds_nothing_up(conn, world, discord_double, monkeypatch):
    _long_post(monkeypatch)
    raised(conn, world)
    discord_double.fail_posts_after = 1
    discord_double.delete_fails = True
    assert cards.sweep(conn) == 0
    assert aw.events(conn, "discord.delete_failed")
