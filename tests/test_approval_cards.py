"""Approval cards in #approvals (MC §4.6 A12, §5.6; ticket 04b).

AC-M5.2 (the posting sweep and `posted_at`), AC-M5.3 (the first line edited in place), AC-M5.5
(eleven files refused before posting) and gate case G28, through `approvals.post_unposted()` with
the fake kind and the Discord double.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

import approval_world as aw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, db, locks, paths


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
    assert approvals.post_unposted(conn) == 1
    (card,) = discord_double.posts("approvals")
    assert "wait=true" in card.url
    record = aw.get(conn, approval.id)
    assert record.posted_at == aw.NOW
    assert record.message_id == card.message_id
    assert approvals.post_unposted(conn) == 0
    assert len(discord_double.posts("approvals")) == 1
    (posted,) = aw.events(conn, "approval.posted")
    assert posted["approval"] == approval.id and posted["message_id"] == card.message_id


def test_the_card_says_what_why_when_and_how_to_answer(conn, world, discord_double):
    approval = raised(conn, world)
    approvals.post_unposted(conn)
    (card,) = discord_double.contents("approvals")
    lines = card.splitlines()
    assert lines[0] == f"**{approval.id} · fake** · decide by Thu 12 Nov, 10:02 SGT · code {approval.code}"
    assert lines[1] == f"fake item {approval.subject}"
    assert lines[2] == "Why: a test asked"
    assert "Quotes that write themselves" in lines
    # The fake kind takes decision arguments, so the answer is typed.
    assert lines[-1] == f"Answer: /growth approve {approval.id} promo_days=… post_days=…, or /growth skip {approval.id}"


def test_a_kind_without_decision_arguments_offers_approve_and_skip(conn, world, discord_double, monkeypatch):
    monkeypatch.setattr(aw.FakeKind, "decision_args", ())
    approval = raised(conn, world)
    approvals.post_unposted(conn)
    assert discord_double.contents("approvals")[0].splitlines()[-1] == f"Answer: Approve / Skip, or /growth approve {approval.id}"


def test_cards_mention_nobody(conn, world, discord_double):
    raised(conn, world, "Hello @everyone and <@123>")
    approvals.post_unposted(conn)
    (card,) = discord_double.posts("approvals")
    assert card.allowed_mentions == {"parse": []}


def test_a_post_that_fails_after_the_commit_is_posted_once_by_the_next_sweep(conn, world, discord_double):
    approval = raised(conn, world)
    discord_double.mode = "500"
    assert approvals.post_unposted(conn) == 0
    assert aw.get(conn, approval.id).posted_at is None
    discord_double.mode = "accept"
    discord_double.requests.clear()
    assert approvals.post_unposted(conn) == 1
    assert approvals.post_unposted(conn) == 0
    assert len(discord_double.posts("approvals")) == 1
    assert aw.get(conn, approval.id).posted_at is not None


def test_with_no_approvals_webhook_nothing_is_posted_or_saved_and_it_stays_unposted(conn, world, tmp_path):
    approval = raised(conn, world)
    assert approvals.post_unposted(conn) == 0
    assert aw.get(conn, approval.id).posted_at is None
    assert not (tmp_path / "data" / "discord-outbox").exists()


def test_only_pending_requests_are_posted(conn, world, discord_double):
    approval = raised(conn, world)
    aw.approve(conn, approval)
    skipped = raised(conn, world, "another")
    aw.skip(conn, skipped)
    assert approvals.post_unposted(conn) == 0
    assert discord_double.posts() == []


def test_a_request_whose_kind_isnt_loaded_is_left_unposted(conn, world, discord_double, monkeypatch):
    approval = raised(conn, world)
    monkeypatch.setattr(approvals.agents, "plugins", aw.REAL_PLUGINS)
    assert approvals.post_unposted(conn) == 0
    assert aw.get(conn, approval.id).posted_at is None


def test_a_second_sweep_running_at_the_same_time_posts_nothing(conn, world, discord_double):
    raised(conn, world)
    with locks.held("approval-cards") as acquired:
        assert acquired
        assert approvals.post_unposted(conn) == 0
    assert discord_double.posts() == []
    assert approvals.post_unposted(conn) == 1


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
    assert approvals.post_unposted(conn) == 0
    assert discord_double.requests == []
    assert aw.get(conn, approval.id).posted_at is None
    (refused,) = aw.events(conn, "approval.card_refused")
    assert refused["approval"] == approval.id and "11 files" in refused["why"]


def test_a_card_with_ten_files_attaches_all_ten(conn, world, discord_double, monkeypatch):
    _with_files(monkeypatch, _images(10))
    raised(conn, world)
    assert approvals.post_unposted(conn) == 1
    (card,) = discord_double.posts("approvals")
    assert len(card.files) == 10


# --- edits in place (AC-M5.3, G28) -----------------------------------------------------


def posted(conn, world, double, text="Quotes that write themselves"):
    approval = raised(conn, world, text)
    approvals.post_unposted(conn)
    (card,) = double.posts("approvals")
    double.requests.clear()
    return aw.get(conn, approval.id), card


def edited_to(double, card) -> str:
    (patch,) = patches(double)
    assert patch.url.endswith(f"/messages/{card.message_id}")
    assert double.posts() == [], "an edit posts no new message"
    return patch.content or ""


def test_an_approval_edits_the_first_line_and_keeps_the_rest(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    approvals.post_unposted(conn)
    content = edited_to(discord_double, card)
    assert content.splitlines()[0] == f"**{approval.id} · fake** · Approved by Ting Yu, 10:02 SGT"
    assert content.splitlines()[1:] == (card.content or "").splitlines()[1:]


def test_a_skip_edits_the_card(conn, world, discord_double, monkeypatch):
    approval, card = posted(conn, world, discord_double)
    aw.at(monkeypatch, "2026-11-10T10:05:00+08:00")
    aw.skip(conn, approval)
    approvals.post_unposted(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Skipped by Ting Yu, 10:05 SGT"


def test_a_lapse_edits_the_card(conn, world, discord_double, monkeypatch):
    approval, card = posted(conn, world, discord_double)
    now = aw.at(monkeypatch, approval.decide_by)
    approvals.expire_due(conn, now)
    approvals.post_unposted(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Expired: not approved in time"


def test_a_supersede_edits_the_card_and_names_the_new_request(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    world.items[approval.subject] += " (changed)"
    newer = aw.request(conn, aw.KIND, approval.subject)
    approvals.post_unposted(conn)
    (patch,) = patches(discord_double)
    assert patch.content.splitlines()[0] == f"**{approval.id} · fake** · Superseded: the content changed; see {newer.id}"
    # The new request gets its own card.
    (new_card,) = discord_double.posts("approvals")
    assert new_card.content.startswith(f"**{newer.id} · fake**")


def test_an_item_that_is_gone_edits_the_card(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    del world.items[approval.subject]
    approvals.expire_due(conn)
    approvals.post_unposted(conn)
    assert edited_to(discord_double, card).splitlines()[0] == f"**{approval.id} · fake** · Superseded: the item is gone"


def test_a_claim_edits_the_card_once_more(conn, world, discord_double, monkeypatch):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    aw.at(monkeypatch, "2026-11-10T10:30:00+08:00")
    assert world.act(conn, approval.subject, run_id=aw.run(conn)) is None
    approvals.post_unposted(conn)
    assert edited_to(discord_double, card).splitlines()[0] == (
        f"**{approval.id} · fake** · Approved by Ting Yu, 10:02 SGT · used at 10:30 SGT"
    )


def test_a_card_is_edited_once_per_change(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    approvals.post_unposted(conn)
    approvals.post_unposted(conn)
    assert len(patches(discord_double)) == 1


def test_a_failed_edit_posts_one_follow_up_line_instead(conn, world, discord_double):
    approval, card = posted(conn, world, discord_double)
    aw.approve(conn, approval)
    discord_double.mode = "edit-fails"
    approvals.post_unposted(conn)
    approvals.post_unposted(conn)
    assert len(patches(discord_double)) == 1
    (follow_up,) = discord_double.posts("approvals")
    assert follow_up.content == f"{approval.id}: Approved by Ting Yu, 10:02 SGT (the card couldn't be edited)."
    assert follow_up.allowed_mentions == {"parse": []}


def test_an_unchanged_card_is_never_edited(conn, world, discord_double):
    posted(conn, world, discord_double)
    approvals.post_unposted(conn)
    assert discord_double.requests == []


# --- raising commands sweep at the end (X12) ------------------------------------------


def test_a_raising_command_posts_its_cards_when_it_ends(conn, world, discord_double):
    subject = world.item()

    @approvals.raises_requests
    def queue():
        with db.session() as own:
            aw.request(own, aw.KIND, subject)
        return "queued"

    assert queue() == "queued"
    (card,) = discord_double.posts("approvals")
    assert card.content.startswith("**A-0001 · fake**")


def test_a_raising_command_that_fails_after_committing_still_posts(conn, world, discord_double):
    subject = world.item()

    @approvals.raises_requests
    def queue():
        with db.session() as own:
            aw.request(own, aw.KIND, subject)
        raise RuntimeError("failed after the commit")

    with pytest.raises(RuntimeError, match="after the commit"):
        queue()
    assert len(discord_double.posts("approvals")) == 1


def test_a_failing_sweep_never_changes_what_the_raising_command_returns(conn, world, monkeypatch, capsys):
    monkeypatch.setattr(approvals, "post_unposted", lambda conn: (_ for _ in ()).throw(RuntimeError("sweep broke")))

    @approvals.raises_requests
    def queue():
        return "queued"

    assert queue() == "queued"
    assert "sweep broke" in capsys.readouterr().err


def test_decide_by_and_use_by_one_second_apart_still_post_the_card(conn, world, discord_double):
    world.decide_in = timedelta(seconds=1)
    raised(conn, world)
    assert approvals.post_unposted(conn) == 1
