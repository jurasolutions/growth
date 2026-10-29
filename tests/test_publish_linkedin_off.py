"""Publishing for a platform that is switched off (LinkedIn, since Ting Yu's decision of 2026-10-29:
"drop the linkedin updates").

A platform with `enabled: false` in `config/social.yaml` gets no publish item, no approval card and
no browser host, even when its `publish_mode` still says `browser`; an item approved before it was
switched off is never claimed. Each check has a twin showing that a switched-on platform still gets
all of these, so the switch itself stays covered.
"""

from __future__ import annotations

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, db, paths
from jura_growth.agents.publish import claim, items, kinds, scope
from jura_growth.agents.social import submit
from test_social import TIP, env, write  # noqa: F401 - env is a fixture

EVERY = ("linkedin", "facebook", "instagram")
WITHOUT_LINKEDIN = ("facebook", "instagram")


def linkedin_off(monkeypatch, *, browser=()):
    pw.social_config(monkeypatch, browser=browser, enabled=WITHOUT_LINKEDIN)


def linkedin_on(monkeypatch, *, browser=()):
    pw.social_config(monkeypatch, browser=browser, enabled=EVERY)


# --- hosts ----------------------------------------------------------------------------------------


def test_a_disabled_platform_in_browser_mode_opens_none_of_its_hosts(monkeypatch):
    linkedin_off(monkeypatch, browser=("facebook", "linkedin"))
    assert scope.enabled_platforms() == ("facebook",)
    assert not [rule for rule in scope.domain_rules() if "linkedin" in rule]


def test_an_enabled_platform_in_browser_mode_still_opens_its_hosts(monkeypatch):
    linkedin_on(monkeypatch, browser=("facebook", "linkedin"))
    assert scope.enabled_platforms() == ("facebook", "linkedin")
    assert "ClaudeInChromeDomain(www.linkedin.com)" in scope.domain_rules()


# --- items and cards ------------------------------------------------------------------------------


def test_no_publish_item_or_request_is_made_for_a_disabled_platform(conn, monkeypatch):
    pw.at(monkeypatch, pw.TEN)
    linkedin_off(monkeypatch, browser=("facebook", "linkedin"))
    made = items.create_social(conn, pw.draft(conn, "linkedin"), run_id=None)
    assert made.item is None and made.approval is None
    assert "turned off" in (made.why or "")
    assert db.scalar(conn, "SELECT count(*) FROM publish_items") == 0
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == 0


def test_an_item_and_request_are_still_made_for_an_enabled_platform(conn, monkeypatch):
    pw.at(monkeypatch, pw.TEN)
    linkedin_on(monkeypatch, browser=("linkedin",))
    made = items.create_social(conn, pw.draft(conn, "linkedin"), run_id=None)
    assert made.item is not None and made.approval is not None, made.why


def test_submit_raises_a_card_only_for_the_enabled_platform_in_browser_mode(conn, env, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    linkedin_off(monkeypatch, browser=("facebook", "linkedin"))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    folder = write(paths.work_dir("social") / pw.DAY.isoformat(), TIP)

    assert submit.submit(conn, folder, offline=True).status == "delivered"

    assert [r["platform"] for r in db.rows(conn, "SELECT platform FROM publish_items")] == ["facebook"]
    [request] = approvals.pending(conn)
    assert request.kind == "social-post"
    [card] = discord_double.posts("approvals")
    assert "linkedin" not in (card.content or "").lower()
    assert not [p for p in discord_double.posts("social-drafts") if "linkedin" in (p.content or "").lower()]


# --- claims ---------------------------------------------------------------------------------------


def test_an_item_approved_before_linkedin_was_turned_off_is_never_claimed(conn, monkeypatch):
    pw.at(monkeypatch, pw.TEN)
    linkedin_on(monkeypatch, browser=("linkedin",))
    found, approval = pw.approved(conn, monkeypatch, "linkedin")
    linkedin_off(monkeypatch, browser=("linkedin",))
    requests = db.scalar(conn, "SELECT count(*) FROM approvals")

    assert "turned off" in (kinds.switched_off(conn, found) or "")
    with pytest.raises(approvals.NotApproved, match="turned off"), db.transaction(conn):
        approvals.use(conn, kinds.kind_of(found), found.subject, run_id=None)
    result = claim.next_item(conn)
    assert result.item is None
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == requests  # no new card
    after = items.get(conn, found.id)
    assert after is not None and after.state != "claimed"
    assert scope.enabled_platforms() == ()


def test_a_waiting_card_is_superseded_at_the_next_sync_once_its_platform_is_switched_off(conn, monkeypatch):
    """Review N1: the card doesn't stay live until 18:00. The existing "the item is gone" path
    supersedes it, the item is withdrawn, and no new card is raised."""
    pw.at(monkeypatch, pw.TEN)
    linkedin_on(monkeypatch, browser=("linkedin",))
    found, waiting = pw.item(conn, "linkedin")
    linkedin_off(monkeypatch, browser=("linkedin",))

    with db.transaction(conn):
        assert items.sync(conn) == []
    record = approvals.get(conn, waiting.id)
    assert record is not None and record.status == approvals.SUPERSEDED
    assert approvals.pending(conn) == []
    after = items.get(conn, found.id)
    assert after is not None and after.state == "withdrawn"
    assert "switched off" in (kinds.note(conn, after) or "")


def test_a_waiting_card_stays_live_while_its_platform_is_only_in_draft_mode(conn, monkeypatch):
    """Draft mode keeps its own rule (A13): the card isn't superseded, `use()` refuses it."""
    pw.at(monkeypatch, pw.TEN)
    linkedin_on(monkeypatch, browser=("linkedin",))
    _, waiting = pw.item(conn, "linkedin")
    linkedin_on(monkeypatch, browser=())

    with db.transaction(conn):
        items.sync(conn)
    record = approvals.get(conn, waiting.id)
    assert record is not None and record.status == approvals.PENDING


# --- the upload deny (review S1) -----------------------------------------------------------------


def approved_linkedin_image_and_facebook_text(conn, monkeypatch):
    """LinkedIn on: an approved LinkedIn item with an image and an approved text-only Facebook
    item, committed so the read-only `next_has_image()` sees them."""
    pw.at(monkeypatch, pw.MORNING)
    linkedin_on(monkeypatch, browser=("facebook", "linkedin"))
    pw.approved(conn, monkeypatch, "linkedin")
    pw.approved(conn, monkeypatch, "facebook", images=[])
    conn.commit()
    pw.at(monkeypatch, pw.TEN)


def test_an_approved_item_on_a_switched_off_platform_never_lifts_the_upload_deny(conn, monkeypatch):
    approved_linkedin_image_and_facebook_text(conn, monkeypatch)
    linkedin_off(monkeypatch, browser=("facebook", "linkedin"))
    assert scope.next_has_image() is False
    assert scope.FILE_UPLOAD in scope.permissions().disallowed_tools


def test_an_approved_item_with_an_image_on_a_switched_on_platform_still_lifts_it(conn, monkeypatch):
    approved_linkedin_image_and_facebook_text(conn, monkeypatch)
    assert scope.next_has_image() is True
    assert scope.FILE_UPLOAD not in scope.permissions().disallowed_tools
