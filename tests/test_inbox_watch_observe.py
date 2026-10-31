"""`inbox observe` and `inbox watch-targets`: what a watch run may record (technical review N1).

The conversation text a watch reads is hostile, so every field is checked here, and nothing a page
said leaves this seam except a person's own stored words. Rows: IW-W3, IW-W5 (N2's two tellings and F7),
IW-A10 (look-alike targets), IW-A13 (a flood), F12's baseline, S8 (counts), B2's uncounted comments.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import inbox_watch_world as w
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import caps, config, db, log, timeutil
from jura_growth.agents.inbox import report, store, watch
from jura_growth.cli import cli


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    w.pw.at(monkeypatch, w.TEN)


def items(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM inbox_items ORDER BY id")


def seen(conn, *observations, run_id: int = 2, first: bool = False):
    """Record `observations` in run `run_id`, by default after an earlier run read every surface."""
    if not first:
        w.baseline(conn)
    return watch.observe(conn, run_id, list(observations))


# --- the record -------------------------------------------------------------------------------


def test_iw_w5_a_message_is_recorded_with_its_people_and_place(conn):
    result = seen(conn, w.dm())
    assert result.recorded == 1
    row = items(conn)[0]
    assert (row["source"], row["sender_name"], row["text"]) == ("instagram-dm", "Priya Nair", w.SAID)
    assert row["target"] == w.THREAD
    assert row["sender_domain"] == "instagram.com"
    assert row["state"] == store.OBSERVED


def test_iw_w5_running_a_watch_twice_records_nothing_new(conn):
    assert seen(conn, w.dm(), w.comment()).recorded == 2
    again = watch.observe(conn, 3, [w.dm(), w.comment()])
    assert (again.recorded, again.duplicates) == (0, 2)
    assert len(items(conn)) == 2


@pytest.mark.parametrize("telling", [
    w.SAID + "  ",
    "do you work with clinics in tampines?",
    "Do you work with clinics in Tampines ?",
    "Do you work with clinics in Tampines?\n\n",
    "Do you work with clinics in Tampines 😊",
])
def test_iw_w5_two_tellings_of_one_message_are_one_item(conn, telling):
    """N2: a model reads the page, so spacing, case and emoji vary between runs."""
    seen(conn, w.dm())
    assert watch.observe(conn, 3, [w.dm(telling)]).recorded == 0


def test_iw_w5_two_see_more_cuts_of_one_comment_are_one_item(conn):
    words = "Could you tell me whether your automation works for a clinic with three branches and a shared booking system that we built " * 2
    seen(conn, w.comment(words, url=w.FB_POST))
    cut = words[:150] + "… See more"
    assert watch.observe(conn, 3, [w.comment(cut, url=w.FB_POST)]).recorded == 0
    assert watch.observe(conn, 4, [w.comment(words[:170] + "... see more", url=w.FB_POST)]).recorded == 0


def test_iw_w5_hello_on_monday_and_thursday_are_two_items(conn):
    """F7: the thread as read holds both, so the second has occurrence 2."""
    seen(conn, w.dm("Hello?", occurrence=1))
    assert watch.observe(conn, 3, [w.dm("Hello?", occurrence=1), w.dm("Hello?", occurrence=2)]).recorded == 1
    assert len(items(conn)) == 2


def test_iw_w5_the_same_words_twice_in_one_file_are_two_items_even_if_it_forgot_to_count(conn):
    assert seen(conn, w.dm("Hello?"), w.dm("Hello?")).recorded == 2


def test_iw_w5_the_comment_id_in_the_permalink_is_the_key(conn):
    """Two people's identical words, or one person's edit: the comment id decides."""
    seen(conn, w.comment("Nice", url=w.FB_POST + "?comment_id=111"))
    assert watch.observe(conn, 3, [w.comment("Nice", url=w.FB_POST + "?comment_id=222")]).recorded == 1
    edited = w.comment("Nice, edited now", url=w.FB_POST + "?comment_id=111")
    assert watch.observe(conn, 4, [edited]).recorded == 0


def test_iw_w5_instagrams_comment_address_gives_its_id_and_its_post(conn):
    seen(conn, w.comment("Hi", url="https://www.instagram.com/p/C0de/c/555/", source="instagram-comment"))
    row = items(conn)[0]
    thread = json.loads(row["thread_json"])
    assert thread["comment_id"] == "555"
    assert thread["thread"] == "/p/C0de"


def test_iw_w5_a_comment_seen_with_an_id_and_again_without_is_one_item(conn):
    """Notifications link the comment; the post page may show the same words with no link."""
    seen(conn, w.comment("How much?", url=w.FB_POST + "?comment_id=111"))
    assert watch.observe(conn, 3, [w.comment("How much?", url=w.FB_POST)]).recorded == 0
    other_way = watch.observe(conn, 4, [w.comment("And for clinics?", url=w.FB_POST)])
    assert other_way.recorded == 1
    assert watch.observe(conn, 5, [w.comment("And for clinics?", url=w.FB_POST + "?comment_id=333")]).recorded == 0


def test_iw_w5_hosts_of_one_platform_are_one_thread(conn):
    seen(conn, w.comment("How much?", url="https://www.facebook.com/jurasolutionssg/posts/1"))
    assert watch.observe(conn, 3, [w.comment("How much?", url="https://m.facebook.com/jurasolutionssg/posts/1/")]).recorded == 0


def test_iw_w5_a_business_suite_thread_is_its_selected_item(conn):
    one = "https://business.facebook.com/latest/inbox/all?selected_item_id=100&asset_id=7"
    two = "https://business.facebook.com/latest/inbox/all?selected_item_id=200&asset_id=7"
    seen(conn, w.dm("Hi", url=one, source="facebook-dm", surface_name="facebook-inbox"))
    assert watch.observe(conn, 3, [w.dm("Hi", url=two, source="facebook-dm", surface_name="facebook-inbox")]).recorded == 1
    assert items(conn)[0]["conversation"] != items(conn)[1]["conversation"]


def test_iw_f7_an_empty_text_hashes_its_attachment_and_occurrence(conn):
    seen(conn, w.dm("", attachment="voice-note"), w.dm("", attachment="voice-note"), w.dm("", attachment="sticker"))
    assert len(items(conn)) == 3
    assert watch.observe(conn, 3, [w.dm("", attachment="voice-note", occurrence=2)]).recorded == 0


def test_iw_f7_emoji_alone_is_a_real_message(conn):
    seen(conn, w.dm("👍"), w.dm("🎉"))
    assert len(items(conn)) == 2


def test_iw_f8_one_person_in_one_thread_is_one_conversation(conn):
    seen(conn, w.dm("Hi"), w.dm("How much?"), w.dm("Hi", author="Someone Else"))
    first, second, third = items(conn)
    assert first["conversation"] == second["conversation"] != third["conversation"]


# --- what's refused -----------------------------------------------------------------------------


@pytest.mark.parametrize("change, reason", [
    ({"source": "email"}, "source"),
    ({"source": "post-stats"}, "source"),
    ({"source": 7}, "source"),
    ({"surface": "somewhere"}, "surface"),
    ({"surface": "facebook-inbox"}, "surface"),  # an Instagram message from Facebook's inbox
    ({"author": 12}, "author"),
    ({"text": ["a"]}, "text"),
    ({"text": ""}, "no text"),
    ({"occurrence": 0}, "occurrence"),
    ({"occurrence": "two"}, "occurrence"),
    ({"occurrence": True}, "occurrence"),
])
def test_iw_n1_a_bad_field_is_refused_with_a_fixed_reason(conn, change, reason):
    result = seen(conn, {**w.dm(), **change})
    assert result.recorded == 0
    assert len(result.refused) == 1 and reason in result.refused[0]["reason"]


def test_iw_n1_a_refusal_never_repeats_what_it_was_given(conn):
    result = seen(conn, {"type": "PLANTED"}, {**w.dm(), "source": "PLANTED"}, "PLANTED", {**w.post_read("P-PLANTED")})
    assert len(result.refused) == 4
    assert "PLANTED" not in json.dumps(result.refused)


def test_iw_n1_one_bad_observation_doesnt_stop_the_rest(conn):
    result = seen(conn, {"type": "nonsense"}, w.dm(), 7, w.comment())
    assert result.recorded == 2 and len(result.refused) == 2


def test_iw_n3_the_pages_own_words_are_not_a_reaction(conn):
    result = seen(conn, w.comment("Thanks for asking", author="Jura Solutions"),
                  w.comment("Thanks", author="jura solutions "),
                  w.dm("Hi", author="jura_solutions"))
    assert result.recorded == 0 and result.own == 3
    assert items(conn) == []


def test_iw_n1_the_text_is_capped_and_cleaned(conn):
    seen(conn, w.dm("x\x1b[31m" + "y" * (caps.INBOX_TEXT_CHARS + 100)))
    row = items(conn)[0]
    assert len(row["text"]) == caps.INBOX_TEXT_CHARS and row["text_cut"] == 1
    assert "\x1b" not in row["text"]


# --- A10: look-alike targets -------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://www.facebook.com.evil.test/jurasolutionssg/posts/1",
    "https://faceb00k.com/jurasolutionssg/posts/1",
    "https://www.facebook.com@evil.test/jurasolutionssg/posts/1",
    "https://evil.test\\@www.facebook.com/jurasolutionssg/posts/1",
    "http://www.facebook.com/jurasolutionssg/posts/1",
    "https://www.facebook.com:8443/jurasolutionssg/posts/1",
    "https://l.facebook.com/l.php?u=https://evil.test",
    "https://xn--facebook-5ya.com/jurasolutionssg/posts/1",
    "javascript:alert(1)",
    "https://www.facebook.com/somebody-else/posts/1",
    "https://www.facebook.com/jurasolutionssg/posts/1\n",
    "https://www.facebook.com/jurasolutionssg/posts/1 [click](https://evil.test)",
    "https://www.facebook.com/jurasolutionssg/../somebody-else/posts/1",
    "https://www.instagram.com/jura_solutions/",  # another platform's address
    "",
    None,
    7,
])
def test_iw_a10_a_look_alike_target_keeps_the_person_but_no_target(conn, url):
    result = seen(conn, w.comment("Hello there", url=url))
    assert result.recorded == 1
    row = items(conn)[0]
    assert row["target"] == ""
    assert row["sender_name"] == "Mei Ling" and row["text"] == "Hello there"
    settled = watch.settle(conn, 2, "hello there", trusted=True)
    assert settled.states == {store.NEEDS_HAND_REPLY: 1}
    assert store.get(conn, row["id"])["state"] == store.NEEDS_HAND_REPLY


def test_iw_a10_a_targetless_person_is_reported_with_a_way_to_find_them(conn, discord_double):
    seen(conn, w.comment("Hello there", url="https://evil.test/x"))
    watch.settle(conn, 2, "hello there", trusted=True)
    report.report_due(conn)
    posted = discord_double.contents("mission-control")[0]
    assert "Hello there" in posted and "evil.test" not in posted
    assert "by hand" in posted


@pytest.mark.parametrize("url", [
    w.COMMENT,
    "https://m.facebook.com/jurasolutionssg/posts/1",
    "https://www.facebook.com/groups/123/posts/456/?comment_id=7",
    "https://www.facebook.com/permalink.php?story_fbid=1&id=2",
    "https://business.facebook.com/latest/inbox/all?selected_item_id=5",
    "https://www.facebook.com/messages/t/123/",
])
def test_iw_a10_a_real_facebook_address_stays(conn, url):
    seen(conn, w.comment(url=url))
    assert items(conn)[0]["target"] == url


@pytest.mark.parametrize("url", ["https://www.instagram.com/p/C0de/", "https://www.instagram.com/reel/C0de/c/1/",
                                 "https://www.instagram.com/direct/t/123/", "https://www.instagram.com/jura_solutions/p/C0de/"])
def test_iw_a10_a_real_instagram_address_stays(conn, url):
    seen(conn, w.comment(url=url, source="instagram-comment"))
    assert items(conn)[0]["target"] == url


def test_iw_a10_a_run_landing_on_a_look_alike_fails_the_audit(tmp_path):
    import publish_transcripts as t
    from jura_growth import transcripts
    from jura_growth.agents.inbox_browser import scope
    from jura_growth.agents.publish import audit

    path = t.write(tmp_path / "run.jsonl", [t.created(), t.opened("https://www.facebook.com.evil.test/x"), t.closed()])
    found = audit.audit(transcripts.read(path), hosts=scope.hosts(), approved=[], images=[], rules=scope.WATCH_RULES)
    assert not found.ok


# --- F12: the first read is a baseline ---------------------------------------------------------


def test_iw_f12_the_first_read_of_a_surface_is_a_silent_baseline_for_old_messages(conn, discord_double):
    result = seen(conn, w.dm("Old", age_hours=100), w.dm("Answered", age_hours=2, answered=True), first=True)
    assert result.baseline == 2
    assert {i["state"] for i in items(conn)} == {store.BASELINE}
    assert report.report_due(conn) == 0
    assert discord_double.contents("mission-control") == []


def test_iw_f12_a_fresh_unanswered_message_on_the_first_read_still_counts(conn):
    result = seen(conn, w.dm("Fresh", age_hours=47), first=True)
    assert result.recorded == 1 and result.baseline == 0
    assert items(conn)[0]["state"] == store.OBSERVED


def test_iw_f12_an_unknown_age_on_the_first_read_is_reported_with_no_draft(conn):
    """It might be fresh, and a person is never hidden, so it is told. It gets no card."""
    seen(conn, w.dm("Who knows", age_hours=None), first=True)
    watch.settle(conn, 2, "who knows", trusted=True)
    row = items(conn)[0]
    assert row["state"] == store.REPORTED and row["stale"] == 1


def test_iw_f12_after_the_first_read_an_old_message_is_reported_with_no_draft(conn):
    seen(conn, w.dm("Old news", age_hours=72))
    watch.settle(conn, 2, "old news", trusted=True)
    row = items(conn)[0]
    assert row["state"] == store.REPORTED and row["stale"] == 1
    assert "48 hours" in row["note"]


def test_iw_f12_a_message_the_page_already_answered_is_reported_and_closed(conn):
    seen(conn, w.dm("Hi", answered=True))
    watch.settle(conn, 2, "hi", trusted=True)
    assert items(conn)[0]["state"] == "answered-by-hand"


def test_iw_f12_a_bad_age_reads_as_unknown(conn):
    seen(conn, w.dm("Hi", age_hours=-3), w.dm("There", age_hours="soon"), w.dm("Again", age_hours=True))
    assert all(json.loads(i["thread_json"])["age_hours"] is None for i in items(conn))


def test_iw_r5_a_baseline_is_not_counted_as_todays_reactions(conn):
    seen(conn, w.dm("Old", age_hours=100), first=True)
    assert store.day_counts(conn, timeutil.today_str())["reactions"] == 0


# --- W3 and F6: which posts --------------------------------------------------------------------


def test_iw_w3_targets_are_published_posts_on_both_platforms(conn):
    facebook = w.published(conn)[0]
    instagram = w.published(conn, platform="instagram", url="https://www.instagram.com/p/C0de/")[0]
    conn.execute("INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, "
                 "state, created_at) VALUES ('P-0099', 'social_post', 'facebook', '99', 'https://www.facebook.com/x', "
                 "'Jura', '{}', '2026-11-09', 'ready', '2026-11-09T07:00:00+08:00')")
    found = watch.targets(conn)["posts"]
    assert {post["item"] for post in found} == {facebook, instagram}
    assert {post["platform"] for post in found} == {"facebook", "instagram"}
    assert all(post["url"] for post in found)


def test_iw_w3_a_community_post_in_a_group_is_a_target(conn):
    label = w.published(conn, url="https://www.facebook.com/groups/123/posts/456/", kind="community_post")[0]
    assert [post["item"] for post in watch.targets(conn)["posts"]] == [label]
    assert watch.observe(conn, 10, [w.post_read(label, reactions=1)]).posts == 1


def test_iw_w3_a_join_is_not_a_target(conn):
    w.published(conn, kind="community_join")
    assert watch.targets(conn)["posts"] == []


def test_iw_w3_a_linkedin_post_is_not_a_target(conn):
    w.published(conn, platform="linkedin", url="https://www.linkedin.com/feed/update/urn:li:activity:1/")
    assert watch.targets(conn)["posts"] == []


@pytest.mark.parametrize("days, shown", [(29, True), (30, True), (31, False)])
def test_iw_f6_the_look_back_is_30_days(conn, days, shown):
    w.published(conn, days_ago=days)
    assert bool(watch.targets(conn)["posts"]) is shown


def test_iw_w3_20_posts_are_all_read_in_three_runs_of_8(conn):
    """The Given/When/Then in the functional review."""
    labels = w.published(conn, 20)
    read: list[str] = []
    for run_id in (10, 11, 12):
        posts = watch.targets(conn)["posts"]
        assert len(posts) == 8
        read += [post["item"] for post in posts]
        result = watch.observe(conn, run_id, [w.post_read(post["item"], reactions=1) for post in posts])
        assert result.posts == 8
    assert len(read) == 24
    assert set(read) == set(labels)


def test_iw_w3_config_may_lower_the_cap_and_never_raise_it(conn, monkeypatch):
    real = config.agent_config
    w.published(conn, 10)
    monkeypatch.setattr(config, "agent_config", lambda a: {**real(a), "watch_posts_per_run": 3} if a == "inbox" else real(a))
    assert len(watch.targets(conn)["posts"]) == 3
    monkeypatch.setattr(config, "agent_config", lambda a: {**real(a), "watch_posts_per_run": 99} if a == "inbox" else real(a))
    assert len(watch.targets(conn)["posts"]) == 8


def test_iw_w3_no_run_opens_more_than_the_cap(conn):
    labels = w.published(conn, 10)
    result = watch.observe(conn, 10, [w.post_read(label) for label in labels])
    assert result.posts == 8 and len(result.refused) == 2


def test_iw_w3_an_observed_post_must_be_one_jura_published(conn):
    w.published(conn, days_ago=40)
    result = watch.observe(conn, 10, [w.post_read("P-0001"), w.post_read("P-9999"), w.post_read("not a label")])
    assert result.posts == 0 and len(result.refused) == 3


def test_iw_w3_a_post_read_twice_in_a_run_counts_once_against_the_cap(conn):
    label = w.published(conn)[0]
    assert watch.observe(conn, 10, [w.post_read(label), w.post_read(label, reactions=2)]).refused == []


# --- W3, S8: the counts ---------------------------------------------------------------------------


def told(conn, run_id: int) -> str:
    """What this run's counts say, for the one message it posts."""
    return "\n".join(watch.post_lines(conn, run_id))


def test_iw_w3_first_sight_is_silent_then_a_rise_is_told_then_nothing(conn):
    label = w.published(conn)[0]
    watch.observe(conn, 1, [w.post_read(label, reactions=2)])
    assert told(conn, 1) == ""
    watch.observe(conn, 2, [w.post_read(label, reactions=5)])
    line = told(conn, 2)
    assert "3 new reactions, now 5" in line and label in line
    watch.observe(conn, 3, [w.post_read(label, reactions=5)])
    assert told(conn, 3) == ""


def test_iw_w3_a_fall_says_nothing_and_a_later_rise_counts_from_the_fall(conn):
    label = w.published(conn)[0]
    watch.observe(conn, 1, [w.post_read(label, reactions=5)])
    told(conn, 1)
    watch.observe(conn, 2, [w.post_read(label, reactions=3)])
    assert told(conn, 2) == ""
    watch.observe(conn, 3, [w.post_read(label, reactions=4)])
    assert "1 new reaction, now 4" in told(conn, 3)


def test_iw_s8_shares_count_and_comment_counts_are_not_reported_as_a_rise(conn):
    label = w.published(conn)[0]
    watch.observe(conn, 1, [w.post_read(label, shares=1, comments=0)])
    told(conn, 1)
    watch.observe(conn, 2, [w.post_read(label, shares=3, comments=0)])
    assert "2 new shares, now 3" in told(conn, 2)
    assert "comment" not in told(conn, 2)


@pytest.mark.parametrize("bad", [
    {"reactions": -1}, {"shares": -5}, {"comments": -2}, {"reactions": "many"}, {"reactions": 2.5}, {"reactions": True},
    {"shares": None}, {"reactions": 10**12},
])
def test_iw_a13_a_bad_count_is_refused_and_changes_nothing(conn, bad):
    label = w.published(conn)[0]
    watch.observe(conn, 1, [w.post_read(label, reactions=2)])
    told(conn, 1)
    result = watch.observe(conn, 2, [{**w.post_read(label, reactions=9), **bad}])
    assert len(result.refused) == 1 and result.posts == 0
    assert told(conn, 2) == ""
    assert db.one(conn, "SELECT reactions FROM inbox_watch_posts")["reactions"] == 2


def test_iw_b2_comments_it_couldnt_read_are_counted_not_lost(conn):
    url = "https://www.facebook.com/jurasolutionssg/posts/77"
    label = w.published(conn, url=url)[0]
    w.baseline(conn)
    watch.observe(conn, 2, [w.post_read(label, comments=4), w.comment("One", url=url + "?comment_id=1"),
                            w.comment("Two", url=url + "?comment_id=2")])
    line = told(conn, 2)
    assert "2 comments the watch couldn't read: check by hand" in line
    assert url in line


def test_iw_b2_the_uncounted_line_says_it_once_until_the_number_rises(conn):
    url = "https://www.facebook.com/jurasolutionssg/posts/77"
    label = w.published(conn, url=url)[0]
    w.baseline(conn)
    watch.observe(conn, 2, [w.post_read(label, comments=2)])
    assert "2 comments" in told(conn, 2)
    watch.observe(conn, 3, [w.post_read(label, comments=2)])
    assert told(conn, 3) == ""
    watch.observe(conn, 4, [w.post_read(label, comments=3)])
    assert "3 comments" in told(conn, 4)


def test_iw_s8_the_pages_own_comments_dont_read_as_unread(conn):
    url = "https://www.facebook.com/jurasolutionssg/posts/77"
    label = w.published(conn, url=url)[0]
    w.baseline(conn)
    watch.observe(conn, 2, [w.post_read(label, comments=3, page_comments=3)])
    assert told(conn, 2) == ""


def test_iw_f12_on_the_very_first_read_of_posts_unread_comments_are_silent(conn):
    """The first run would otherwise list every old post's comments."""
    label = w.published(conn)[0]
    watch.observe(conn, 2, [w.post_read(label, comments=9)])
    assert told(conn, 2) == ""


def test_iw_s4_a_post_that_has_gone_is_a_reaction_and_leaves_the_targets(conn):
    label = w.published(conn)[0]
    watch.observe(conn, 1, [w.post_read(label, reactions=1)])
    told(conn, 1)
    result = watch.observe(conn, 2, [{"type": "post", "item": label, "gone": True}])
    assert result.posts == 1
    assert "isn't there any more" in told(conn, 2)
    assert watch.targets(conn)["posts"] == []
    watch.observe(conn, 3, [{"type": "post", "item": label, "gone": True}])
    assert told(conn, 3) == ""


def test_iw_r1_one_message_per_run_for_every_post_that_rose(conn, discord_double):
    labels = w.published(conn, 3)
    watch.observe(conn, 1, [w.post_read(label, reactions=1) for label in labels])
    watch.record_run_message(conn, 1, watch.post_lines(conn, 1))
    watch.observe(conn, 2, [w.post_read(label, reactions=4) for label in labels])
    watch.record_run_message(conn, 2, watch.post_lines(conn, 2))
    report.report_due(conn)
    posted = discord_double.contents("mission-control")
    assert len(posted) == 1
    assert all(label in posted[0] for label in labels)
    assert posted[0].count("3 new reactions, now 4") == 3


def test_iw_r1_a_run_with_nothing_to_tell_posts_nothing(conn, discord_double):
    watch.record_run_message(conn, 1, [])
    assert report.report_due(conn) == 0


def test_iw_r1_post_counts_never_go_to_triage(conn):
    watch.record_run_message(conn, 1, ["a line"])
    assert items(conn)[0]["state"] == store.REPORTED


# --- A13: a flood -----------------------------------------------------------------------------


def test_iw_a13_500_messages_are_bounded_and_the_rest_are_told_not_dropped(conn):
    result = seen(conn, *[w.dm(f"Message number {n}", occurrence=1) for n in range(500)])
    assert result.recorded == caps.INBOX_OBSERVATIONS_PER_RUN
    assert result.over_cap == 500 - caps.INBOX_OBSERVATIONS_PER_RUN
    lines = watch.over_cap_lines(conn, 2)
    assert str(result.over_cap) in lines[0] and "next run" in lines[0]


def test_iw_a13_the_rest_arrive_on_the_next_run(conn):
    many = [w.dm(f"Message number {n}") for n in range(50)]
    seen(conn, *many)
    again = watch.observe(conn, 3, many)
    assert again.recorded == 10 and again.duplicates == 40 and again.over_cap == 0


def test_iw_a13_a_baseline_doesnt_use_up_the_cap(conn):
    result = seen(conn, *[w.dm(f"Old {n}", age_hours=500) for n in range(100)], first=True)
    assert result.baseline == 100 and result.over_cap == 0


def test_iw_n1_the_cap_can_be_lowered(conn, monkeypatch):
    real = config.agent_config
    monkeypatch.setattr(config, "agent_config", lambda a: {**real(a), "observations_per_run": 2} if a == "inbox" else real(a))
    assert seen(conn, w.dm("a"), w.dm("b"), w.dm("c")).recorded == 2


# --- the commands --------------------------------------------------------------------------------


def invoke(*args):
    return CliRunner().invoke(cli, list(args))


def test_iw_n1_observe_takes_a_file_in_scratch_and_prints_counts_only(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_RUN_ID", str(log.start_run(conn, "inbox-browser", "inbox-watch")))
    w.baseline(conn)
    path = tmp_path / "seen.json"
    path.write_text(json.dumps([w.dm(), {"type": "PLANTED"}]), encoding="utf-8")
    result = invoke("inbox", "observe", "--file", str(path))
    assert result.exit_code == 0, result.output
    printed = json.loads(result.output)
    assert printed["recorded"] == 1 and len(printed["refused"]) == 1
    assert w.SAID not in result.output and "PLANTED" not in result.output
    assert "Priya" not in result.output


def test_iw_n1_inside_a_run_observe_refuses_a_file_outside_scratch(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_RUN_ID", "2")
    monkeypatch.setenv("JURA_GROWTH_JOB", "inbox-watch")
    monkeypatch.setenv("JURA_GROWTH_AGENT", "inbox-browser")
    path = tmp_path / "seen.json"
    path.write_text("[]", encoding="utf-8")
    result = invoke("inbox", "observe", "--file", str(path))
    assert result.exit_code != 0
    assert "may only use files" in result.output


def test_iw_n1_observe_has_no_inline_text_option():
    from jura_growth.agents.inbox.commands import inbox_group

    names = {opt for param in inbox_group.commands["observe"].params for opt in param.opts}
    assert names == {"--file"}


def test_iw_n1_outside_a_run_observe_is_refused(conn, tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("[]", encoding="utf-8")
    result = invoke("inbox", "observe", "--file", str(path))
    assert result.exit_code != 0 and "watch run" in result.output


@pytest.mark.parametrize("body", ["not json at all PLANTED", '{"a": 1}', "\xff"])
def test_iw_n1_a_file_that_isnt_a_json_list_is_refused_with_no_quote(conn, monkeypatch, tmp_path, body):
    monkeypatch.setenv("JURA_GROWTH_RUN_ID", "2")
    path = tmp_path / "seen.json"
    path.write_bytes(body.encode("latin-1"))
    result = invoke("inbox", "observe", "--file", str(path))
    assert result.exit_code != 0
    assert "PLANTED" not in result.output


def test_iw_a13_a_huge_file_is_refused_whole_and_says_to_split_it(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("JURA_GROWTH_RUN_ID", "2")
    path = tmp_path / "seen.json"
    path.write_text(json.dumps([w.dm("y" * 1000) for _ in range(watch.OBSERVE_FILE_BYTES // 1000 + 1)]), encoding="utf-8")
    result = invoke("inbox", "observe", "--file", str(path))
    assert result.exit_code != 0 and "split" in result.output
    assert items(conn) == []


def test_iw_w3_watch_targets_prints_the_pages_surfaces_and_posts(conn):
    label = w.published(conn)[0]
    result = invoke("inbox", "watch-targets")
    assert result.exit_code == 0, result.output
    printed = json.loads(result.output)
    assert [post["item"] for post in printed["posts"]] == [label]
    assert {s["surface"] for s in printed["surfaces"]} == set(watch.SURFACES)
    assert printed["pages"]["facebook"]["url"].startswith("https://www.facebook.com/")


def test_iw_f13_inbox_status_shows_each_surfaces_last_good_read(conn):
    w.baseline(conn)
    result = invoke("inbox", "status")
    assert "Instagram Requests: last good read" in result.output


def test_iw_f13_a_surface_records_its_count(conn):
    watch.observe(conn, 5, [w.surface("instagram-primary", items=3)])
    watch.finish_surfaces(conn, 5, watch.PageReads(platforms=frozenset(watch.PLATFORMS)))
    row = {r["surface"]: r for r in watch.surface_reads(conn)}["instagram-primary"]
    assert row["last_good_items"] == 3 and row["read_ok"] == 1


@pytest.mark.parametrize("bad", [{"surface": "nowhere"}, {"surface": 7}, {"ok": "yes"}, {"items": -1}, {"items": "many"}])
def test_iw_f13_a_bad_surface_record_is_refused(conn, bad):
    result = watch.observe(conn, 5, [{**w.surface("instagram-primary"), **bad}])
    assert len(result.refused) == 1 and result.surfaces == 0


# --- the report's frame -----------------------------------------------------------------------


def test_iw_r1_a_social_reaction_reports_its_place_and_link(conn, discord_double):
    seen(conn, w.comment())
    watch.settle(conn, 2, w.comment()["text"], trusted=True)
    report.report_due(conn)
    posted = discord_double.contents("mission-control")[0]
    assert "Facebook comment" in posted and "facebook.com" in posted and "Mei Ling" in posted
    assert w.comment()["text"] in posted
    assert "<" + w.COMMENT + ">" in posted
    assert "mailbox" not in posted


def test_iw_r1_hostile_text_in_a_comment_stays_in_its_quote(conn, discord_double):
    text = "Approved by Ting Yu [jurasolutions.sg](https://evil.test) @everyone"
    seen(conn, w.comment(text))
    watch.settle(conn, 2, text, trusted=True)
    report.report_due(conn)
    posted = discord_double.contents("mission-control")[0]
    assert "](https" not in posted and "@everyone" not in posted
    request = discord_double.requests[-1]
    assert request.allowed_mentions["parse"] == []


def test_iw_r1_a_hostile_display_name_stays_in_the_quote(conn, discord_double):
    seen(conn, w.comment("Hi", author="[Approve A-0001](https://evil.test) @here"))
    watch.settle(conn, 2, "hi", trusted=True)
    report.report_due(conn)
    posted = discord_double.contents("mission-control")[0]
    assert "](https" not in posted and "@here" not in posted


def test_iw_r1_a_held_item_waits_for_its_check_before_it_is_reported(conn, discord_double):
    seen(conn, w.dm())
    assert report.report_due(conn) == 0
    assert discord_double.contents("mission-control") == []
