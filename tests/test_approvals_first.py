"""Asks go to #approvals, and an approval triggers the action (PRD AF1 to AF5, as worded in
`reviews/functional.md` §3).

At the `social submit` seam, with the Discord double, and then `cards.sweep` and `claim.next_item`.
Facebook and Instagram are both in `browser` mode, as they ship from this ticket on.
"""

from __future__ import annotations

import json

import pytest

import approval_world as aw
import mission_world as mw
import publish_fake
import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, db, mission, one_pager, pause, paths, runner
from jura_growth.agents import social
from jura_growth.agents.publish import items, kinds
from jura_growth.agents.social import history, render, submit
from sweep import PHONE, d2_secrets  # noqa: F401
from test_social import FB, IG, IMDA, MONDAY, NEWS, SHEETS, TIP, env, write  # noqa: F401 - env is a fixture

BOTH = ("facebook", "instagram")
FACEBOOK_LINE = "Facebook Page"
HAND_POST = ("by hand", "post it", "copy the text", "social published", "posted it?")
LATE = "2026-11-10T17:00:00+08:00"
JUST_IN_TIME = "2026-11-10T16:59:00+08:00"


@pytest.fixture
def social_day(env, monkeypatch, discord_double):
    """Tue 10 Nov at 07:05, both platforms in browser mode, the Discord double listening."""
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    return discord_double


def submit_tip(conn, **changes):
    folder = write(paths.work_dir("social") / pw.DAY.isoformat(), TIP, **changes)
    return submit.submit(conn, folder, offline=True)


def every_message(double) -> list[str]:
    assert double.requests, "the double saw nothing, so this checked nothing"
    return [text.lower() for r in double.requests for text in [r.content or ""]]


def assert_nothing_asks_to_post_by_hand(double) -> None:
    for message in every_message(double):
        for phrase in HAND_POST:
            assert phrase not in message, f"{phrase!r} in: {message[:300]}"


def card_of(double, platform_label: str):
    [card] = [p for p in double.posts("approvals") if platform_label in (p.content or "")]
    return card


# --- AF1: one card, the exact text, every image in order, its sources ----------------------------


def test_each_platform_gets_one_card_and_social_drafts_hears_nothing(conn, social_day):
    outcome = submit_tip(conn)
    assert outcome.status == "delivered", outcome.text()
    assert [r["platform"] for r in db.rows(conn, "SELECT platform FROM publish_items ORDER BY id")] == list(BOTH)
    assert len(social_day.posts("approvals")) == 2

    facebook, instagram = card_of(social_day, FACEBOOK_LINE), card_of(social_day, "Instagram")
    assert FB.strip() in (facebook.content or "") and [name for name, _ in facebook.files] == ["facebook-1200x630.png"]
    assert IG.strip() in (instagram.content or "")
    assert [name for name, _ in instagram.files] == [f"instagram-{n}-of-3-1080x1350.png" for n in (1, 2, 3)]

    assert social_day.posts("social-drafts") == []  # no post text, no image, no words asking him to post
    assert_nothing_asks_to_post_by_hand(social_day)


def test_a_card_carries_the_sources_the_post_relies_on(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, MONDAY)
    pw.social_config(monkeypatch, browser=BOTH)
    folder = write(paths.work_dir("social") / "2026-10-26", NEWS)
    assert submit.submit(conn, folder, offline=True).status == "delivered"
    instagram = card_of(discord_double, "Instagram").content or ""
    assert f"Sources: <{IMDA}>, <{SHEETS}>" in instagram
    assert all(IMDA in (card.content or "") for card in discord_double.posts("approvals"))
    slides = [name for name, _ in card_of(discord_double, "Instagram").files]
    assert slides == [f"instagram-{n}-of-3-1080x1350.png" for n in (1, 2, 3)]


def test_a_card_names_the_headline_and_the_title_is_not_hashed(conn, social_day):
    submit_tip(conn)
    [first, *_] = approvals.pending(conn)
    assert "Let your accounting software send the first invoice reminder" in (social_day.posts("approvals")[0].content or "")
    conn.execute("UPDATE social_posts SET qa_json = '{}'")
    registered = approvals.kinds()[first.kind]
    assert approvals.content_hash(registered.kind.content(conn, first.subject)) == first.content_hash


def long_post(words: int = 280) -> str:
    sentence = "Most small teams chase late invoices the same way and it costs them a Friday afternoon every single week."
    lines, count = [], 0
    while count < words:
        lines.append(sentence)
        count += len(sentence.split())
    return "\n\n".join(lines) + "\n\nMore small automations like this: https://jurasolutions.sg\n\n#SmallBusiness #Automation\n"


def test_a_280_word_post_splits_its_card_cleanly_with_the_pictures_beside_the_answer(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    text = long_post()
    pw.item(conn, "facebook", text=text)
    cards.sweep(conn)
    posts = discord_double.posts("approvals")
    assert len(posts) == 2
    assert all((p.content or "").count("```") % 2 == 0 for p in posts)
    assert posts[0].files and posts[1].files == []
    assert (posts[0].content or "").startswith("**A-0001 · social post** · decide by")
    shown = [line for p in posts for line in (p.content or "").split("\n")]
    assert [line for line in shown if line in text.split("\n") and line] == [line for line in text.split("\n") if line]


# --- what the card can't show can't be approved (code review 02, SP-B1) ----------------------------


def phone_post(text: str = FB) -> str:
    return text.replace("for you.", f"for you. Call {PHONE} to ask.", 1)


def test_a_post_the_card_would_mask_fails_the_gate_and_uses_the_regeneration(conn, social_day):
    outcome = submit_tip(conn, **{"facebook.md": phone_post()})
    assert outcome.status == "retry" and "attempt 1 of 2" in outcome.text()
    [reason] = [line for line in outcome.lines if "approval card" in line]
    assert PHONE not in reason and "[phone removed]" in reason  # it says where, masked
    assert db.rows(conn, "SELECT * FROM publish_items") == [] and social_day.posts("approvals") == []


def test_a_second_failure_drops_that_variant_and_the_other_platform_still_gets_its_card(conn, social_day):
    submit_tip(conn, **{"facebook.md": phone_post()})
    outcome = submit_tip(conn, **{"facebook.md": phone_post()})
    assert outcome.status == "partial" and outcome.variants["facebook"].status == "dropped"
    [card] = social_day.posts("approvals")
    assert "Instagram" in (card.content or "")
    assert not any("removed]" in (post.content or "") for post in social_day.posts("approvals"))


def test_a_card_never_shows_a_post_with_words_masked_even_past_the_gate(conn, env, monkeypatch, discord_double):
    """A name can be learned between the gate and the card, and a row can change under an item."""
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    _, request = pw.item(conn, "facebook", text=f"Call us on {PHONE} about your invoices.\n\nhttps://jurasolutions.sg\n")
    assert cards.sweep(conn) == 0
    assert discord_double.posts("approvals") == []
    assert approvals.get(conn, request.id).posted_at is None  # the one-pager lists it
    assert aw.events(conn, "approval.card_refused")[0]["approval"] == request.id


def test_jura_s_own_sender_address_stays_on_the_card_through_its_edit(conn, env, monkeypatch, discord_double):
    from jura_growth import privacy

    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    address = "tingyu@jurasolutions.sg"
    monkeypatch.setattr(privacy, "learn", lambda conn=None, **_: privacy.remember_owner(address))
    _, approval = pw.item(conn, "facebook", text=f"Write to {address} about your invoices.\n\nhttps://jurasolutions.sg\n")
    cards.sweep(conn)
    [card] = discord_double.posts("approvals")
    assert address in (card.content or "")
    pw.decide(conn, approval, monkeypatch=monkeypatch)
    cards.sweep(conn)
    [edit] = [r for r in discord_double.requests if r.method == "PATCH"]
    assert address in (edit.content or "")
    [line] = [c for c in discord_double.contents("social-drafts") if approval.id in c]
    assert address not in line  # the feed line isn't Jura's copy


# --- AF2: approved in time, posted in time ---------------------------------------------------------


def test_a_card_is_decided_by_1700_and_used_by_1800(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, second = approvals.pending(conn)
    assert first.decide_by == "2026-11-10T17:00:00+08:00" == second.decide_by
    assert "decide by Tue 10 Nov, 17:00 SGT" in (social_day.posts("approvals")[0].content or "")
    pw.at(monkeypatch, JUST_IN_TIME)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    assert approvals.get(conn, first.id).use_by == "2026-11-10T18:00:00+08:00"


def test_both_approved_at_1659_both_go_out_before_1800(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, second = approvals.pending(conn)
    pw.at(monkeypatch, JUST_IN_TIME)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.decide(conn, second, monkeypatch=monkeypatch)
    claimed = []
    for slot in ("17:00", "17:20", "17:40"):
        pw.at(monkeypatch, f"2026-11-10T{slot}:00+08:00")
        pw.run(conn, monkeypatch=monkeypatch)
        found = pw.next_item(conn)
        if found.item is not None:
            claimed.append((slot, found.item.platform))
    assert claimed == [("17:00", "facebook"), ("17:20", "instagram")]


def test_a_tap_at_1701_answers_expired_and_nothing_goes_out(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, "2026-11-10T17:01:00+08:00")
    assert pw.decide(conn, first, monkeypatch=monkeypatch).answer == approvals.EXPIRED
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None


def test_nothing_unapproved_goes_out(conn, social_day, monkeypatch):
    submit_tip(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert db.rows(conn, "SELECT * FROM approvals WHERE used_at IS NOT NULL") == []


def test_a_pause_stops_an_approved_post(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pause.pause(conn, "publish", "a test", notify=False)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None


def test_a_post_that_changes_after_the_decide_by_refuses_without_breaking_the_run(conn, social_day, monkeypatch):
    """`approvals.use` raises the new request at once, past the decide-by too. It must not raise
    on a deadline already gone: the run would fail with an approved post in its hands."""
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, JUST_IN_TIME)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    conn.execute("UPDATE social_posts SET text = text || ' Changed.' WHERE platform = 'facebook'")
    pw.at(monkeypatch, "2026-11-10T17:10:00+08:00")
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert db.rows(conn, "SELECT * FROM approvals WHERE used_at IS NOT NULL") == []
    assert approvals.get(conn, first.id).status == approvals.SUPERSEDED
    [fresh] = [a for a in approvals.pending(conn) if a.subject == first.subject]
    assert fresh.decide_by == "2026-11-10T18:00:00+08:00"  # the replacement has until the window's end


@pytest.mark.parametrize(("moment", "words"), [
    ("2026-11-10T17:39:00+08:00", "It goes out on a publish run today, by 18:00 SGT."),
    ("2026-11-10T17:40:00+08:00", "No publish run is left today, so this lapses at 18:00 SGT."),
    ("2026-11-10T17:45:00+08:00", "No publish run is left today, so this lapses at 18:00 SGT."),
])
def test_a_replacement_approved_late_never_promises_a_post_with_no_run_left(conn, social_day, monkeypatch, moment, words):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.at(monkeypatch, JUST_IN_TIME)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    conn.execute("UPDATE social_posts SET text = text || ' Changed.' WHERE platform = 'facebook'")
    pw.at(monkeypatch, "2026-11-10T17:20:00+08:00")
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    [fresh] = [a for a in approvals.pending(conn) if a.subject == first.subject]
    cards.sweep(conn)
    pw.at(monkeypatch, moment)
    assert pw.decide(conn, fresh, monkeypatch=monkeypatch).answer == "recorded"
    cards.sweep(conn)
    [line] = [m for m in social_day.contents("social-drafts") if fresh.id in m]
    assert words in line and ("goes out" in words) == ("goes out" in line)


# --- AF3: browser mode with no card gets a note, and never a request to post -----------------------


def test_no_page_url_gets_a_note_saying_so(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH, urls={"facebook": None})
    assert submit_tip(conn).status == "delivered"
    assert [card for card in discord_double.posts("approvals") if FACEBOOK_LINE in (card.content or "")] == []
    [note] = discord_double.contents("social-drafts")
    assert "facebook" in note and "page_url" in note
    assert FB.strip() not in note
    assert_nothing_asks_to_post_by_hand(discord_double)


def test_a_submit_after_the_decide_by_gets_a_note_and_no_card(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, LATE)
    pw.social_config(monkeypatch, browser=BOTH)
    assert submit_tip(conn).status == "delivered"
    assert discord_double.posts("approvals") == [] and approvals.pending(conn) == []
    [note] = discord_double.contents("social-drafts")
    assert "17:00" in note and "facebook" in note and "instagram" in note
    assert_nothing_asks_to_post_by_hand(discord_double)


def test_a_render_failure_gets_a_note_no_card_and_an_alert(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)

    def fails(*args, **kwargs):
        raise render.RenderError("Chrome went away")

    monkeypatch.setattr(render, "render_spec", fails)
    assert submit_tip(conn).status == "delivered"
    assert discord_double.posts("approvals") == [] and db.rows(conn, "SELECT * FROM publish_items") == []
    [note] = discord_double.contents("social-drafts")
    assert "no image" in note.lower() and "facebook" in note and "instagram" in note
    assert any("not rendered" in alert for alert in discord_double.contents("alerts"))
    assert_nothing_asks_to_post_by_hand(discord_double)


def test_a_card_whose_words_fail_twice_means_no_picture_and_no_approval_card(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    spec = json.loads(TIP["card.json"])
    spec["headline"] = "Leverage your accounting software for the first reminder"
    bad = json.dumps(spec)
    assert submit_tip(conn, **{"card.json": bad}).status == "retry"
    assert submit_tip(conn, **{"card.json": bad}).status == "partial"
    assert discord_double.posts("approvals") == [] and db.rows(conn, "SELECT * FROM publish_items") == []
    notes = discord_double.contents("social-drafts")
    assert any("no image" in note.lower() for note in notes)
    assert_nothing_asks_to_post_by_hand(discord_double)


def test_no_image_means_no_item_and_no_request_on_either_platform(conn, env, monkeypatch):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    for platform in BOTH:
        made = items.create_social(conn, pw.draft(conn, platform, images=[]), run_id=None)
        assert made.item is None and made.approval is None and "no image" in made.why
    assert approvals.pending(conn) == []


# --- AF4: a run that can't reach a decision doesn't start ------------------------------------------


@pytest.mark.parametrize(("moment", "expected"), [
    (JUST_IN_TIME, None),
    (LATE, "17:00"),
    ("2026-11-10T19:00:00+08:00", "17:00"),
])
def test_the_precheck_tests_against_the_decide_by(conn, env, monkeypatch, moment, expected):
    pw.at(monkeypatch, moment)
    pw.social_config(monkeypatch, browser=BOTH)
    answer = social.precheck("social", conn)
    assert answer is None if expected is None else expected in answer


def test_a_platform_in_draft_mode_still_runs_late(conn, env, monkeypatch):
    pw.at(monkeypatch, "2026-11-10T19:00:00+08:00")
    pw.social_config(monkeypatch, browser=("instagram",))
    assert social.precheck("social", conn) is None


def test_a_late_run_skips_before_claude_starts_and_says_why(conn, env, monkeypatch, discord_double, tmp_path):
    fake = publish_fake.install(tmp_path, monkeypatch)  # a stand-in, so a broken precheck can't start the real one
    pw.at(monkeypatch, LATE)
    pw.social_config(monkeypatch, browser=BOTH)
    outcome = runner.run("social")
    assert outcome.status == "skipped" and "17:00" in outcome.summary
    assert not fake.started
    assert any("17:00" in message for message in discord_double.contents("social-drafts"))


# --- AF5: draft mode is still the way back ---------------------------------------------------------


@pytest.mark.parametrize(("browser", "by_hand"), [
    (("instagram",), ["facebook"]),
    (("facebook",), ["instagram"]),
    ((), ["facebook", "instagram"]),
])
def test_hand_posting_text_appears_only_for_a_platform_in_draft_mode(conn, env, monkeypatch, discord_double, browser, by_hand):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=browser)
    assert submit_tip(conn).status == "delivered"

    labels = {"facebook": FACEBOOK_LINE, "instagram": "Instagram"}
    drafts = discord_double.posts("social-drafts")
    posted_by_hand = [p for p in drafts if "post it by hand" in (p.content or "")]
    assert sorted(p.content.split("**")[1] for p in posted_by_hand) == sorted(labels[name] for name in by_hand)
    assert all(p.files for p in posted_by_hand)
    assert len(discord_double.posts("approvals")) == len(browser)
    for name in browser:
        assert not any(labels[name] in (p.content or "").split("\n")[0] for p in drafts)


def test_going_back_to_draft_mode_with_a_card_open_posts_nothing_and_the_next_day_is_by_hand(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, second = approvals.pending(conn)
    pw.at(monkeypatch, pw.TEN)
    pw.social_config(monkeypatch, browser=())
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert db.rows(conn, "SELECT * FROM approvals WHERE used_at IS NOT NULL") == []

    pw.at(monkeypatch, "2026-11-13T07:05:00+08:00")
    social_day.requests.clear()
    folder = write(paths.work_dir("social") / "2026-11-13", TIP)
    assert submit.submit(conn, folder, offline=True, theme_id="automation-tip").status == "delivered"
    assert social_day.posts("approvals") == []
    assert len([p for p in social_day.posts("social-drafts") if "post it by hand" in (p.content or "")]) == 2


# --- the digest says where a draft really is (technical N11, functional S11) -----------------------


def test_a_browser_draft_with_a_card_waits_in_approvals(conn, social_day):
    submit_tip(conn)
    line = social.digest(conn, "2026-11-10")["lines"][0]
    assert "2 drafts waiting in #approvals (facebook, instagram)" in line


def test_a_browser_draft_with_no_card_says_so(conn, env, monkeypatch):
    pw.at(monkeypatch, LATE)
    pw.social_config(monkeypatch, browser=BOTH)
    assert submit_tip(conn).status == "delivered"
    line = social.digest(conn, "2026-11-10")["lines"][0]
    assert "#approvals" not in line and "no card" in line and "facebook" in line


def test_a_draft_mode_platform_waits_in_social_drafts(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=("instagram",))
    submit_tip(conn)
    line = social.digest(conn, "2026-11-10")["lines"][0]
    assert "1 draft waiting in #approvals (instagram)" in line
    assert "1 draft waiting in #social-drafts (facebook)" in line


def test_merge_day_a_draft_written_before_browser_mode_says_no_card(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=())
    submit_tip(conn)
    pw.social_config(monkeypatch, browser=BOTH)
    line = social.digest(conn, "2026-11-10")["lines"][0]
    assert "no card" in line and "#approvals" not in line


# --- what the feed hears on a social day (FD1, FD2; functional S6, S8; E2E-1, E2E-4) ---------------


HEADLINE = "Let your accounting software send the first invoice reminder"


def feed_lines(double) -> list[str]:
    return double.contents("social-drafts")


def test_an_approved_post_is_named_by_its_headline_and_says_what_happens_next(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    cards.sweep(conn)
    [line] = feed_lines(social_day)
    assert line.startswith(f"**{first.id} approved**") and HEADLINE in line
    assert line.endswith("It goes out on a publish run today, by 18:00 SGT. The run's update here gives the post's address.")
    assert "Publishing is paused" not in line


def test_an_approval_while_publishing_is_paused_says_so(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    pause.pause(conn, "publish", "a test", notify=False)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    cards.sweep(conn)
    [line] = feed_lines(social_day)
    assert line.endswith("Publishing is paused, so nothing goes out until you resume it.")


def test_a_social_day_from_approval_to_the_run_gives_one_line_each_and_none_on_the_claim(conn, social_day, monkeypatch):
    submit_tip(conn)
    first, second = approvals.pending(conn)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.decide(conn, second, "skip", monkeypatch=monkeypatch)
    cards.sweep(conn)
    assert [line.split(" · ")[0] for line in feed_lines(social_day)] == [f"**{first.id} approved**", f"**{second.id} skipped**"]

    pw.at(monkeypatch, pw.TEN)
    pw.run(conn, monkeypatch=monkeypatch)
    found = pw.next_item(conn)
    assert found.item is not None and found.item.platform == "facebook"
    cards.sweep(conn)
    assert len(feed_lines(social_day)) == 2
    assert_nothing_asks_to_post_by_hand(social_day)


def test_a_skip_drops_that_platform_for_the_day_and_says_so_on_the_card(conn, social_day, monkeypatch):
    submit_tip(conn)
    _, second = approvals.pending(conn)
    pw.decide(conn, second, "skip", monkeypatch=monkeypatch)
    assert "instagram" in history.skipped_platforms(conn, pw.DAY)


# --- a refused card is said out loud, and nothing says otherwise (round 2, R2-B2) --------------------


UNREADABLE = "Discord would mask part of the post, so its card can't show the exact text"


def refuse_facebook(monkeypatch) -> None:
    """The gate has passed, and then the kind finds Facebook's card can't show the post."""
    real = kinds.SocialPost.card_problem

    def problem(self, conn, subject):
        return UNREADABLE if items.of(conn, subject).platform == "facebook" else real(self, conn, subject)

    monkeypatch.setattr(kinds.SocialPost, "card_problem", problem)


def test_a_refused_card_posts_one_note_saying_why_and_the_rest_of_the_day_carries_on(conn, social_day, monkeypatch):
    refuse_facebook(monkeypatch)
    submit_tip(conn)
    cards.sweep(conn)
    cards.sweep(conn)
    first, _ = approvals.pending(conn)
    every = [(r.channel, r.content or "") for r in social_day.requests]
    [note] = [text for channel, text in every if first.id in text and channel != "approvals"]
    assert [channel for channel, text in every if text == note] == ["social-drafts"]
    assert UNREADABLE in note and "lapses" in note and "Tue 10 Nov, 17:00" in note
    assert FB.strip() not in note
    assert len(social_day.posts("approvals")) == 1  # Instagram's
    assert_nothing_asks_to_post_by_hand(social_day)
    assert len(aw.events(conn, "approval.card_refused")) == 1


def test_submit_tells_the_truth_about_a_refused_card(conn, social_day, monkeypatch):
    refuse_facebook(monkeypatch)
    outcome = submit_tip(conn)
    first, second = approvals.pending(conn)
    assert outcome.lines[0].startswith("Delivered, with no card for facebook")
    assert f"Approval requested: facebook as {first.id} in #approvals" not in outcome.text()
    assert f"No approval card for facebook ({first.id}): {UNREADABLE}" in outcome.text()
    assert f"Approval requested: instagram as {second.id} in #approvals" in outcome.text()


def test_submit_tells_the_truth_when_discord_didnt_take_the_card(conn, social_day):
    social_day.mode = "500"
    outcome = submit_tip(conn)
    first, _ = approvals.pending(conn)
    assert outcome.lines[0].startswith("Delivered, with no card for facebook, instagram")
    assert f"{first.id}: its card goes to #approvals once Discord takes it" in outcome.text()
    assert f"as {first.id} in #approvals" not in outcome.text()


def test_the_digest_tells_the_truth_about_a_refused_card(conn, social_day, monkeypatch):
    refuse_facebook(monkeypatch)
    submit_tip(conn)
    line = social.digest(conn, "2026-11-10")["lines"][0]
    assert "1 draft waiting in #approvals (instagram)" in line and "1 draft with no card (facebook)" in line


def test_the_one_pager_tells_the_truth_about_a_refused_card(conn, social_day, monkeypatch):
    refuse_facebook(monkeypatch)
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    conn.commit()
    text = one_pager.text(mission.read(mw.source(now="2026-11-10T08:00:00+08:00")))
    assert f"{first.id} (social-post) has no card: {UNREADABLE}" in text
    assert not any(first.id in line and "heartbeat" in line for line in text.splitlines())


def test_the_one_pager_still_expects_the_heartbeat_for_a_card_discord_didnt_take(conn, social_day):
    social_day.mode = "500"
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    conn.commit()
    social_day.mode = "accept"
    text = one_pager.text(mission.read(mw.source(now="2026-11-10T08:00:00+08:00")))
    assert any(first.id in line and "heartbeat" in line for line in text.splitlines())


def test_a_typed_approval_of_a_post_with_no_card_is_refused_and_can_be_skipped(conn, env, monkeypatch, discord_double):
    """The one way left to approve words he hasn't read. The refusal stays inside the kind."""
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=BOTH)
    _, request = pw.item(conn, "facebook", text=f"Call us on {PHONE} about your invoices.\n\nhttps://jurasolutions.sg\n")
    cards.sweep(conn)
    answer = pw.decide(conn, request, monkeypatch=monkeypatch)
    assert answer.answer == approvals.REFUSED and "can't show the exact text" in answer.text
    assert approvals.get(conn, request.id).status == approvals.PENDING
    pw.at(monkeypatch, pw.TEN)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert pw.decide(conn, request, "skip", monkeypatch=monkeypatch).answer == "recorded"


def test_a_post_whose_card_went_out_whole_can_still_be_approved_if_a_name_is_learned_after(conn, social_day, monkeypatch):
    """He read it. Learning a lead's name at 09:00 doesn't unread it."""
    submit_tip(conn)
    first, _ = approvals.pending(conn)
    monkeypatch.setattr(kinds.SocialPost, "card_problem", lambda self, conn, subject: UNREADABLE)
    assert pw.decide(conn, first, monkeypatch=monkeypatch).answer == "recorded"


# --- the config as it ships (test strategy R1, R3, E2E-1) -------------------------------------------


def test_a_day_on_the_shipped_config_asks_in_approvals_and_posts_only_what_was_approved(conn, env, monkeypatch, discord_double):
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    folder = write(paths.work_dir("social") / "2026-10-27", TIP)
    assert submit.submit(conn, folder, offline=True).status == "delivered"
    first, second = approvals.pending(conn)
    posts = discord_double.posts("approvals")
    assert len(posts) == 2
    assert "https://www.facebook.com/jurasolutionssg" in (posts[0].content or "")
    assert "https://www.instagram.com/jura_solutions/" in (posts[1].content or "")
    assert discord_double.posts("social-drafts") == []

    pw.at(monkeypatch, "2026-10-27T10:00:00+08:00")
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None  # nothing goes out while both wait

    pw.decide(conn, first, monkeypatch=monkeypatch)
    pw.decide(conn, second, "skip", monkeypatch=monkeypatch)
    cards.sweep(conn)
    found = pw.next_item(conn)
    assert found.item is not None and found.item.platform == "facebook"
    cards.sweep(conn)
    assert [line.split(" · ")[0] for line in discord_double.contents("social-drafts")] == [
        f"**{first.id} approved**", f"**{second.id} skipped**"]
    assert [row["platform"] for row in db.rows(conn, "SELECT platform FROM publish_items WHERE state = 'claimed'")] == ["facebook"]
    assert_nothing_asks_to_post_by_hand(discord_double)


@pytest.mark.parametrize("state", ["pending", "skipped", "expired", "superseded", "paused"])
def test_on_the_shipped_config_a_request_that_isnt_approved_hands_out_nothing(conn, env, monkeypatch, discord_double, state):
    """R1: nothing goes out in any state but approved, for either platform."""
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    folder = write(paths.work_dir("social") / "2026-10-27", TIP)
    assert submit.submit(conn, folder, offline=True).status == "delivered"
    requests = approvals.pending(conn)
    assert [approvals.kinds()[r.kind].agent for r in requests] == ["publish", "publish"]
    at_ten = "2026-10-27T10:00:00+08:00"
    if state == "skipped":
        for request in requests:
            pw.decide(conn, request, "skip", monkeypatch=monkeypatch)
    elif state == "expired":
        at_ten = "2026-10-27T17:01:00+08:00"
        pw.at(monkeypatch, at_ten)
        for request in requests:
            assert pw.decide(conn, request, monkeypatch=monkeypatch).answer == approvals.EXPIRED
    elif state == "superseded":
        for request in requests:
            pw.decide(conn, request, monkeypatch=monkeypatch)
        conn.execute("UPDATE social_posts SET text = text || ' Changed.'")
    elif state == "paused":
        for request in requests:
            pw.decide(conn, request, monkeypatch=monkeypatch)
        pause.pause(conn, "publish", "a test", notify=False)
    pw.at(monkeypatch, at_ten)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert db.rows(conn, "SELECT * FROM approvals WHERE used_at IS NOT NULL") == []
    assert db.rows(conn, "SELECT * FROM publish_items WHERE state = 'claimed'") == []


def test_a_late_run_on_the_shipped_config_skips_before_claude_starts(conn, env, monkeypatch):
    pw.at(monkeypatch, "2026-10-27T17:00:00+08:00")
    assert "17:00" in social.precheck("social", conn)
