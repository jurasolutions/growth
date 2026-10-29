"""Publishing for a platform that is switched off (LinkedIn, since Ting Yu's decision of 2026-10-29:
"drop the linkedin updates").

A platform with `enabled: false` in `config/social.yaml` gets no publish item, no approval card and
no browser host, even when its `publish_mode` still says `browser`; an item approved before it was
switched off is never claimed. Each check has a twin showing that a switched-on platform still gets
all of these, so the switch itself stays covered.
"""

from __future__ import annotations

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
    found, _ = pw.approved(conn, monkeypatch, "linkedin")
    linkedin_off(monkeypatch, browser=("linkedin",))
    requests = db.scalar(conn, "SELECT count(*) FROM approvals")

    assert "turned off" in (kinds.switched_off(conn, found) or "")
    result = claim.next_item(conn)
    assert result.item is None
    assert any("turned off" in why for why in result.why), result.why
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == requests  # no new card
    after = items.get(conn, found.id)
    assert after is not None and after.state != "claimed"
    assert scope.enabled_platforms() == ()
