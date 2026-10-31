"""Publish items for social posts and their `social-post` requests (BP-02a).

AC-P1.1 to AC-P1.4, X6 and the card sweep, at the `social submit` seam (S7) with the Discord double
(S5), and the kind's `content()` table (AC-P1.3, G9's social fields).
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, config, db, paths
from jura_growth.agents.publish import items, kinds
from jura_growth.agents.social import submit
from jura_growth.agents.social.settings import SettingsError, load
from sweep import PHONE, RESEND_KEY, assert_clean, d2_secrets, outbox_dir, planted  # noqa: F401
from test_social import FB, TIP, env, write  # noqa: F401 - env is a fixture


@pytest.fixture
def social(env, monkeypatch, discord_double):
    """Tue 10 Nov at 07:05, Facebook in browser mode, the Discord double listening."""
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    return discord_double


def submit_tip(conn, **changes):
    folder = write(paths.work_dir("social") / pw.DAY.isoformat(), TIP, **changes)
    return submit.submit(conn, folder, offline=True)


def social_posts(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM approvals WHERE kind = 'social-post' ORDER BY id")


# --- settings: publish_mode is draft or browser (expand and contract) ------------------------


def test_publish_mode_is_draft_or_browser_and_auto_is_gone(monkeypatch):
    assert {p.publish_mode for p in load().platforms.values()} == {"draft"}
    pw.social_config(monkeypatch, browser=("facebook",))
    settings = load()
    assert settings.platforms["facebook"].publish_mode == "browser"
    assert settings.platforms["facebook"].page_url == pw.PAGE_URL
    assert settings.platforms["linkedin"].publish_mode == "draft"
    real = config.agent_config

    def with_auto(agent):
        base = dict(real(agent))
        if agent == "social":
            base["platforms"] = {**base["platforms"], "facebook": {**base["platforms"]["facebook"], "publish_mode": "auto"}}
        return base

    monkeypatch.setattr(config, "agent_config", with_auto)
    with pytest.raises(SettingsError, match="draft.*browser"):
        load()


def test_every_platform_ships_in_draft_mode():
    raw = config.agent_config("social")["platforms"]
    assert {spec["publish_mode"] for spec in raw.values()} == {"draft"}


# --- AC-P1.1 a request per item ------------------------------------------------------------


def test_submit_raises_one_social_post_request_for_facebook_only(conn, social):
    outcome = submit_tip(conn)
    assert outcome.status == "delivered", outcome.text()

    rows = db.rows(conn, "SELECT * FROM publish_items")
    assert [(r["kind"], r["platform"], r["day"], r["state"]) for r in rows] == [("social_post", "facebook", "2026-11-10", "ready")]
    [request] = approvals.pending(conn)
    assert request.kind == "social-post" and request.subject == f"publish_item:{rows[0]['id']}"

    [card] = social.posts("approvals")
    lines = card.content.split("\n")
    assert lines[0] == f"**{request.id} · social post** · decide by Tue 10 Nov, 17:00 SGT"
    assert "Facebook Page" in card.content and pw.PAGE_URL in card.content
    assert "Tue 10 Nov 2026" in card.content
    assert FB.strip() in card.content  # the exact text
    assert "Links in the text: <https://jurasolutions.sg>" in card.content
    assert "Brand check: passed on attempt 1 of 2" in card.content
    assert [name for name, _ in card.files] == ["facebook-1200x630.png"]


def test_a_browser_platform_stays_out_of_social_drafts_and_a_draft_platform_gets_its_hand_post(conn, social):
    """AF1 and AF5: the post's text and images stay on its card, and draft mode keeps hand-posting."""
    submit_tip(conn)
    assert len(approvals.pending(conn)) == 1
    drafts = social.posts("social-drafts")
    assert [p for p in drafts if (p.content or "").startswith("**Facebook Page**")] == []
    assert not any(FB.strip() in (p.content or "") for p in drafts)
    assert not any(name.startswith("facebook") for p in drafts for name, _ in p.files)
    instagram = [p for p in social.posts("social-drafts") if (p.content or "").startswith("**Instagram**")]
    assert len(instagram) == 1 and instagram[0].files and "post it by hand" in instagram[0].content


def test_linkedin_and_instagram_in_draft_mode_raise_nothing(conn, social):
    submit_tip(conn)
    assert [r["platform"] for r in db.rows(conn, "SELECT platform FROM publish_items")] == ["facebook"]
    assert len(social_posts(conn)) == 1


# --- AC-P1.2 the brand gate ---------------------------------------------------------------


def test_a_variant_that_fails_the_brand_gate_gets_no_item_and_no_request(conn, social):
    bad = FB.replace("for you.", "for you!")
    assert submit_tip(conn, **{"facebook.md": bad}).status == "retry"
    assert db.rows(conn, "SELECT * FROM publish_items") == [] and social_posts(conn) == []
    outcome = submit_tip(conn, **{"facebook.md": bad})
    assert outcome.status == "partial" and outcome.variants["facebook"].status == "dropped"
    assert db.rows(conn, "SELECT * FROM publish_items") == [] and social_posts(conn) == []
    assert social.posts("approvals") == []


# --- AC-P1.4 drafts written before browser mode --------------------------------------------


def test_drafts_written_before_a_platform_moved_to_browser_get_no_item(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, browser=())
    assert submit_tip(conn).status == "delivered"
    pw.social_config(monkeypatch, browser=("facebook",))
    assert submit_tip(conn).status == "nothing"
    pw.at(monkeypatch, pw.TEN)
    assert pw.next_item(conn).item is None
    assert db.rows(conn, "SELECT * FROM publish_items") == [] and social_posts(conn) == []


# --- X6 weekends ---------------------------------------------------------------------------


def test_a_saturday_draft_on_a_browser_platform_raises_a_request(conn, social, monkeypatch):
    pw.at(monkeypatch, "2026-11-14T07:05:00+08:00")
    folder = write(paths.work_dir("social") / "2026-11-14", TIP)
    assert submit.submit(conn, folder, offline=True, theme_id="automation-tip").status == "delivered"
    [request] = approvals.pending(conn)
    assert request.decide_by == "2026-11-14T17:00:00+08:00"


# --- browser mode with nothing to post to --------------------------------------------------


def test_browser_mode_without_a_page_url_gets_a_note_and_never_a_request_to_post(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.social_config(monkeypatch, urls={"facebook": None})
    outcome = submit_tip(conn)
    assert outcome.status == "delivered"
    assert db.rows(conn, "SELECT * FROM publish_items") == []
    assert any("page_url" in line for line in outcome.lines)
    assert [m for m in discord_double.contents("social-drafts") if m.startswith("**Facebook Page**")] == []
    assert any("facebook" in m and "page_url" in m for m in discord_double.contents("social-drafts"))
    assert not any("by hand" in m and "Facebook" in m for r in discord_double.requests for m in [r.content or ""])


def test_an_item_is_not_raised_once_its_posting_window_has_closed(conn, monkeypatch):
    pw.social_config(monkeypatch)
    pw.at(monkeypatch, "2026-11-10T18:00:00+08:00")
    post = pw.draft(conn)
    made = items.create_social(conn, post, run_id=None)
    assert made.item is None and "window" in made.why
    assert social_posts(conn) == []


# --- AC-P1.3 the content covers every field ------------------------------------------------


def change_text(conn, post):
    conn.execute("UPDATE social_posts SET text = text || ' (changed)' WHERE id = ?", (post,))


def change_image_bytes(conn, post):
    path = json.loads(db.scalar(conn, "SELECT image_paths FROM social_posts WHERE id = ?", (post,)))[0]
    pw.Path(path).write_bytes(pw.png(extra=b"other"))


def change_image_order(conn, post):
    paths_ = json.loads(db.scalar(conn, "SELECT image_paths FROM social_posts WHERE id = ?", (post,)))
    conn.execute("UPDATE social_posts SET image_paths = ? WHERE id = ?", (json.dumps(list(reversed(paths_))), post))


def change_destination(monkeypatch):
    pw.social_config(monkeypatch, urls={"facebook": "https://www.facebook.com/another-page"})


def change_identity(monkeypatch):
    real = config.agent_config

    def patched(agent):
        base = dict(real(agent))
        if agent == "social":
            platforms = dict(base["platforms"])
            platforms["facebook"] = {**platforms["facebook"], "identity": "Someone else's Page"}
            base["platforms"] = platforms
        return base

    monkeypatch.setattr(config, "agent_config", patched)


def change_day(conn, post):
    conn.execute("UPDATE social_posts SET date = '2026-11-11' WHERE id = ?", (post,))


CHANGES = {
    "text": lambda conn, post, mp: change_text(conn, post),
    "image bytes": lambda conn, post, mp: change_image_bytes(conn, post),
    "image order": lambda conn, post, mp: change_image_order(conn, post),
    "destination": lambda conn, post, mp: change_destination(mp),
    "posting identity": lambda conn, post, mp: change_identity(mp),
    "day": lambda conn, post, mp: change_day(conn, post),
}


@pytest.mark.parametrize("field", list(CHANGES))
def test_any_one_field_changed_supersedes_the_request_and_raises_a_new_one(conn, monkeypatch, field):
    pw.social_config(monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    images = [pw.image("facebook-1.png"), pw.image("facebook-2.png", pw.png(extra=b"two"))]
    found, approval = pw.approved(conn, monkeypatch, images=images)
    kind = kinds.SocialPost()
    before = kind.content(conn, approval.subject)
    assert before is not None and approvals.content_hash(before) == approval.content_hash

    CHANGES[field](conn, found.ref_id, monkeypatch)
    after = kind.content(conn, approval.subject)
    assert after != before

    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert approvals.get(conn, approval.id).status == "superseded"
    [fresh] = [a for a in approvals.pending(conn) if a.subject == approval.subject]
    assert fresh.supersedes == approval.number and fresh.content_hash == approvals.content_hash(after)


def test_a_draft_skipped_or_posted_by_hand_makes_the_item_gone(conn, monkeypatch):
    pw.social_config(monkeypatch, browser=("facebook", "linkedin"))
    pw.at(monkeypatch, pw.TEN)
    first, request = pw.item(conn)
    pw.invoke("social", "skip", "2026-11-10", "facebook")
    assert kinds.SocialPost().content(conn, request.subject) is None
    second, other = pw.item(conn, "linkedin")
    pw.invoke("social", "published", "2026-11-10", "linkedin", "--url", pw.LINKEDIN_URL + "/posts/1")
    assert kinds.SocialPost().content(conn, other.subject) is None
    approvals.expire_due(conn)
    assert {approvals.get(conn, a.id).status for a in (request, other)} == {"superseded"}
    assert cards.status_line(conn, approvals.get(conn, request.id)).startswith("Superseded: skipped")
    assert cards.status_line(conn, approvals.get(conn, other.id)).startswith("Superseded: posted by hand")


# --- the sweep (AC-M11.1, AC-M12.1) over social-post cards and their feed lines ---------------


def test_social_post_cards_and_their_feed_lines_carry_nothing_planted(conn, env, monkeypatch, discord_double, d2_secrets):
    pw.at(monkeypatch, pw.MORNING)
    label = f"Facebook Page {planted().marker} {RESEND_KEY} {PHONE}"
    pw.social_config(monkeypatch)
    real = config.agent_config

    def labelled(agent):
        base = dict(real(agent))
        if agent == "social":
            platforms = dict(base["platforms"])
            platforms["facebook"] = {**platforms["facebook"], "label": label, "identity": f"Jura {RESEND_KEY}"}
            base["platforms"] = platforms
        return base

    monkeypatch.setattr(config, "agent_config", labelled)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    assert submit_tip(conn).status == "delivered"
    # A draft row planted by raw SQL (past the gate), with its own item and card.
    pw.at(monkeypatch, pw.TEN)
    pw.social_config(monkeypatch, browser=("facebook", "linkedin"))
    pw.item(conn, "linkedin", text=planted().text(), day=pw.DAY + timedelta(days=1))
    cards.sweep(conn)
    assert len(discord_double.posts("approvals")) == 2
    [first, *_] = approvals.pending(conn)
    pw.decide(conn, first, monkeypatch=monkeypatch)
    cards.sweep(conn)  # the planted label reaches a feed line
    line = [p for p in discord_double.posts("social-drafts") if planted().marker in (p.content or "")]
    assert line and f"{first.id} approved" in line[0].content
    assert_clean(discord_double, outbox_dir(), planted())
