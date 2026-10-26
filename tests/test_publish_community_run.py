"""Community posts as the Jura Page through the whole publish job, with the fake `claude` binary
(seam S10; datasets D10 and T; ticket BP-05).

`runner.run("publish")` in process; the fake plays Chrome calls and real `jura-growth …`
subprocesses. Rows traced end to end: AC-P5.1 lines 8, 9 and 10, with the group's open days
confirmed through mission control's `group-rules` decision; AC-P4.3's composer branch; AC-P11.1
(the Page as the group identity, before any typing); AC-P6.2; and the audit holding a post to its
own group (code review 06, B1, for posts). Page text never reaches the run row, `#alerts` or the
run update, which goes to `#community` (BP §5.9).
"""

from __future__ import annotations

import json

import pytest

import publish_fake
import publish_transcripts as t
import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, db, pause, runner
from jura_growth.agents.community import group_rules
from jura_growth.agents.community import groups as community_groups
from jura_growth.agents.publish import items
from jura_growth.origin import Origin
from test_publish_run import alerts, browser, chrome, claim

RULES = "Be kind to each other.\nPromotion only on Saturdays."
COMPOSER = "SG owners\nWrite something...\nPosting as Jura Solutions"
# Page text a group can show; none of it may reach a row, an alert or a run update.
ADMIN_NOTE = "Admin warning: Mrs Tan says call 9123 4567 about this post"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    found = publish_fake.install(tmp_path, monkeypatch)
    found.community(lambda data: data.update(browser=True))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)
    return found


def run():
    return runner.run("publish", ignore_schedule=True)


def group_of(conn, group_id: int) -> dict:
    found = community_groups.get(conn, group_id)
    assert found is not None, group_id
    return found


def record_of(conn, approval_id: str) -> approvals.Approval:
    found = approvals.get(conn, approval_id)
    assert found is not None, approval_id
    return found


def post_row(conn, post_id: int) -> dict:
    found = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (post_id,))
    assert found is not None, post_id
    return found


def confirm_rules(conn, group_id: int, *, promo_days: str, post_days: str) -> None:
    """Ting Yu's `group-rules` decision in #approvals, with the open days typed (MC §5.7)."""
    request = group_rules.request(conn, group_id, reason="rules read inside the group")
    assert request is not None and request.live, request
    decided = approvals.decide(conn, request.id, "approve", actor=f"discord:{pw.CONTROL_ID}", origin=Origin.ssh(),
                               source_ref=None, args={"promo_days": promo_days, "post_days": post_days})
    assert decided.answer == "recorded", decided


def approved_post(conn, group_id: int) -> tuple[items.Item, approvals.Approval]:
    found, request = pw.community_item(conn, group_id)
    assert pw.decide(conn, request).answer == "recorded"
    return found, request


def unconfirmed_group(conn) -> int:
    """A good-fit group joined as the Jura Page, its rules read but not yet confirmed."""
    return pw.group(conn, rules=RULES, rules_confirmed=0, promo_days=None, post_days=None)


def at(url: str, tool: str, given: dict, text: str = "ok") -> dict:
    return chrome(t.page(tool, given, text, url=url))


def post_in(group: str, *, post: str | None = None, typed_at: str | None = None) -> list[dict]:
    """A clean post in the group at `group`: open it, check the composer posts as the Page, type
    the approved text once, post, read the post back on its own address and record it. With
    `typed_at`, the text is typed and posted on that page instead."""
    post = post or f"{group}/posts/1234567890/"
    where = typed_at or group
    return [
        *browser(t.created(), t.opened(group)),
        at(group, "get_page_text", {}, COMPOSER),
        at(where, "computer", {"action": "left_click", "ref": "ref_12"}, "Clicked."),
        at(where, "computer", {"action": "type", "text": "{TEXT}"}, "Typed."),
        at(where, "computer", {"action": "left_click", "ref": "ref_30"}, "Clicked Post."),
        chrome(t.opened(post)),
        at(post, "get_page_text", {}, "{TEXT}"),
        {"write": "{A}-live.txt", "text": "{TEXT}"},
        {"cli": ["publish", "done", "{A}", "--url", post, "--live-text-file", "{WORK}/{A}-live.txt"]},
        chrome(t.closed()),
    ]


# --- AC-P5.1 lines 8 to 10 end to end, with the days from a group-rules decision (U14 in the suite) ----------


def test_a_post_goes_out_on_an_open_day_and_the_same_item_is_refused_on_a_closed_one(conn, fake, discord_double):
    group_id = unconfirmed_group(conn)
    found, request = approved_post(conn, group_id)
    group = group_of(conn, group_id)["url"]
    fake.scenario([*claim(), *post_in(group)], "OK: posted {A}")

    run()  # rules not confirmed by Ting Yu: nothing is due, and Claude never starts
    assert not fake.started

    confirm_rules(conn, group_id, promo_days="sat", post_days="wed")  # Tuesday is closed
    run()  # line 8
    assert not fake.started
    record = record_of(conn, request.id)
    assert record.status == approvals.APPROVED and record.used_at is None

    confirm_rules(conn, group_id, promo_days="sat", post_days="any")  # Tuesday is open
    outcome = run()

    assert fake.started and outcome.status == "ok", outcome
    handed = json.loads(fake.cli[0]["output"])
    assert handed["step"] == "community post" and handed["group"] == group_id
    assert handed["posting_identity"] == "the Jura Solutions Facebook Page"  # config/social.yaml
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["outcome"], row["live_text_matches"]) == ("done", "posted", 1)
    post = post_row(conn, found.ref_id)
    assert (post["status"], post["posted_via"]) == ("posted", "browser")
    assert not pause.is_paused(conn, "publish") and alerts(discord_double) == []
    [update] = discord_double.contents("community")  # a group item's update goes to #community (§5.9)
    assert request.id in update and f"Facebook group {group_id}" in update and "1 post" in update
    assert discord_double.contents("social-drafts") == []


def test_a_group_with_its_rules_confirmed_but_its_days_not_never_starts_a_run(conn, fake):
    group_id = pw.group(conn, rules=RULES, rules_confirmed=1, promo_days=None, post_days=None)  # line 9
    _, request = approved_post(conn, group_id)
    fake.scenario([*claim()])

    run()

    assert not fake.started
    assert record_of(conn, request.id).used_at is None


def test_a_group_no_longer_joined_as_the_page_never_starts_a_run(conn, fake):
    group_id = pw.group(conn)
    _, request = approved_post(conn, group_id)
    community_groups.set_fields(conn, group_id, ["joined_as=profile"])  # line 10
    fake.scenario([*claim()])

    run()

    assert not fake.started
    assert record_of(conn, request.id).status == approvals.SUPERSEDED


# --- AC-P4.3, the composer branch -------------------------------------------------------------------------


def test_a_composer_with_no_way_to_post_as_the_page_skips_the_group_without_alert_or_pause(conn, fake, discord_double):
    group_id = pw.group(conn)
    found, request = approved_post(conn, group_id)
    _, waiting = pw.community_item(conn, group_id, day=pw.DAY.replace(day=24))
    group = group_of(conn, group_id)["url"]
    fake.scenario([*claim(), *browser(t.created(), t.opened(group)),
                   at(group, "get_page_text", {}, "Write something...\nPosting as Somebody (only people can post here)"),
                   {"cli": ["publish", "done", "{A}", "--outcome", "pages-not-allowed"]}, chrome(t.closed())],
                  "OK: {A} takes only personal profiles")

    outcome = run()

    assert outcome.status == "ok", outcome
    assert pw.item_row(conn, found.id)["outcome"] == "pages-not-allowed"
    skipped = group_of(conn, group_id)
    assert skipped["pages_allowed"] == "no" and skipped["fit"] == "skip"
    assert record_of(conn, waiting.id).status == approvals.SUPERSEDED
    assert alerts(discord_double) == [] and not pause.is_paused(conn, "publish")
    [update] = discord_double.contents("community")
    assert request.id in update and "only personal profiles" in update


# --- AC-P11.1 the Page as the group identity, before any typing ------------------------------------------------


def test_a_composer_posting_as_someone_else_stops_the_run_before_anything_is_typed(conn, fake, discord_double):
    group_id = pw.group(conn)
    found, request = approved_post(conn, group_id)
    group = group_of(conn, group_id)["url"]
    fake.scenario([*claim(), *browser(t.created(), t.opened(group)),
                   at(group, "get_page_text", {}, "Write something...\nPosting as Ting Yu"),
                   {"cli": ["publish", "stopped", "{A}", "--reason", "wrong-identity"]}, chrome(t.closed())],
                  "FAIL: {A} wrong posting identity")

    outcome = run()

    assert outcome.status == "failed"
    row = pw.item_row(conn, found.id)
    assert row["state"] == "stopped" and row["stop_reason"] == "wrong-identity"
    assert pause.is_paused(conn, "publish")
    assert group_of(conn, group_id)["pages_allowed"] == "unknown"  # a stop, not pages-not-allowed
    assert post_row(conn, found.ref_id)["status"] == "planned"
    [alert] = alerts(discord_double)
    assert request.id in alert and "expected posting identity" in alert


# --- AC-P6.2 a removal or admin warning in the group --------------------------------------------------------------


def test_an_admin_warning_in_the_group_stops_everything_and_skips_the_group_for_good(conn, fake, discord_double):
    group_id = pw.group(conn)
    found, request = approved_post(conn, group_id)
    later = pw.planned(conn, group_id, day=pw.DAY.replace(day=24))
    group = group_of(conn, group_id)["url"]
    fake.scenario([*claim(), *browser(t.created(), t.opened(group)), at(group, "get_page_text", {}, ADMIN_NOTE),
                   {"cli": ["publish", "stopped", "{A}", "--reason", "admin-warning"]}, chrome(t.closed())],
                  f"FAIL: {ADMIN_NOTE}")

    outcome = run()

    assert outcome.status == "failed"
    assert pw.item_row(conn, found.id)["state"] == "stopped" and pause.is_paused(conn, "publish")
    removed = group_of(conn, group_id)
    assert removed["removed"] == 1 and removed["fit"] == "skip"
    assert post_row(conn, later)["status"] == "skipped"
    [alert] = alerts(discord_double)  # the stop's one alert
    assert request.id in alert and f"Group {group_id} is now skipped for good" in alert
    [update] = discord_double.contents("community")
    stored = db.one(conn, "SELECT summary, error FROM runs ORDER BY id DESC LIMIT 1")
    assert stored is not None
    for seen in (alert, update, stored["summary"] or "", stored["error"] or ""):
        assert "9123" not in seen and "Mrs Tan" not in seen


# --- the audit holds a post to its own group (code review 06, B1, for posts) --------------------------------


@pytest.mark.parametrize("where", ["another group", "the page timeline"])
def test_a_post_typed_outside_its_own_group_fails_the_run_and_pauses(conn, fake, where):
    group_id = pw.group(conn)
    approved_post(conn, group_id)
    group = group_of(conn, group_id)["url"]
    elsewhere = {"another group": "https://www.facebook.com/groups/some-other-group", "the page timeline": t.PAGE}[where]
    fake.scenario([*claim(), *post_in(group, typed_at=elsewhere)], "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert pause.is_paused(conn, "publish")
    assert "outside the claimed item's own page" in outcome.error and "some-other-group" not in outcome.error


def test_an_audit_failed_post_names_its_posted_record_as_possibly_wrong_and_keeps_it(conn, fake, discord_double):
    """Code review 05, S1 (R6): the run posts on the Page's timeline, then records its own group's
    address. The record stays (the post may be live, and `planned` would invite a repost), but the
    alert, the run row and the #community line say which record to check."""
    group_id = pw.group(conn)
    found, request = approved_post(conn, group_id)
    group = group_of(conn, group_id)["url"]
    fake.scenario([*claim(), *post_in(group, typed_at=t.PAGE)], "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed" and pause.is_paused(conn, "publish")
    warning = (f"{request.id}'s posted record for group {group_id} may be wrong: check the group, and the "
               f"Page's own timeline")
    assert warning in outcome.error
    [line] = [line for line in outcome.summary.splitlines() if request.id in line]
    assert line.endswith("· the audit failed")
    [alert] = alerts(discord_double)
    assert warning in alert
    [update] = discord_double.contents("community")
    assert "the audit failed" in update
    post = post_row(conn, found.ref_id)  # kept: the post may be live
    assert (post["status"], post["posted_via"]) == ("posted", "browser")
    assert group_of(conn, group_id)["last_posted_at"] == "2026-11-10"


def test_a_clean_post_carries_no_audit_warning(conn, fake):
    group_id = pw.group(conn)
    approved_post(conn, group_id)
    fake.scenario([*claim(), *post_in(group_of(conn, group_id)["url"])], "OK: posted {A}")

    outcome = run()

    assert outcome.status == "ok" and "audit" not in outcome.summary and "may be wrong" not in (outcome.error or "")
