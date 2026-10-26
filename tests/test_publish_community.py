"""Community posts and group joins in the publish queue, with no browser (BP-02b).

Test strategy v3 §4.2 and §4.3, the BP-02b rows: X7 (the `community_groups` columns), AC-P3.4 (the
`group-join` deadlines), AC-P1.3 (community fields and answers), AC-P5.1 lines 2 to 5 and 8 to 10,
and AC-P5.3's `community.browser` switch, at the claim (`claim.next_item`, seam S7) and at the
kinds' `content()` and `deadlines()`. The gate matrix runs through `gate_adapter_community_post.py`,
`gate_adapter_group_join.py` and `gate_adapter_group_join_answers.py`. The clock is BP's default,
Tue 2026-11-10 (ISO week 46, Mon 2026-11-09 to Sun 2026-11-15).
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import agents, approvals, cards, config, db, pause, paths, runner
from jura_growth.agents import community, publish
from jura_growth.agents.community import groups as community_groups
from jura_growth.agents.community import plan
from jura_growth.agents.publish import items, kinds, limits
from sweep import AWKWARD, KEYCHAIN_VALUE, NAMED_ADDRESS, PHONE, RESEND_KEY, assert_clean, outbox_dir, planted
from sweep import d2_secrets  # noqa: F401 - a fixture


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    pw.community_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


# --- X7 the community_groups migration adds only ---------------------------------------------------


def _columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_the_community_groups_migration_changes_no_existing_row(tmp_path, monkeypatch):
    current = community.MIGRATIONS
    older = tmp_path / "community-migrations"
    older.mkdir()
    for name in ("0001_community.sql", "0002_confirmed_days.sql"):
        shutil.copy(current / name, older / name)
    monkeypatch.setattr(community, "MIGRATIONS", older)
    path = tmp_path / "before.db"
    old = db.connect(path)
    for number, flag in ((1, 1), (2, 0)):  # a legacy joined group and one never joined
        old.execute(
            "INSERT INTO community_groups (id, name, slug, url, url_key, promo_rules, fit, fit_reason, joined, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'no links', 'good fit', 'owners', ?, '2026-11-02', '2026-11-02')",
            (number, f"G{number}", f"g{number}", f"https://www.facebook.com/groups/g{number}", f"facebook.com/groups/g{number}", flag),
        )
    old.commit()
    columns = _columns(old, "community_groups")
    before = sorted(tuple(r) for r in old.execute("SELECT * FROM community_groups"))
    old.close()
    monkeypatch.setattr(community, "MIGRATIONS", current)
    new = db.connect(path)
    try:
        after = sorted(tuple(r) for r in new.execute(f"SELECT {', '.join(columns)} FROM community_groups"))
        assert after == before
        read = {r["id"]: (r["joined_as"], r["pages_allowed"], r["join_status"])
                for r in db.rows(new, "SELECT * FROM community_groups")}
        assert read == {1: ("profile", "unknown", None), 2: ("none", "unknown", None)}
    finally:
        new.close()


def test_community_set_records_how_a_group_was_joined(conn, world):
    """BP §4.3: Ting Yu can join as the Page by hand and run `community set <id> joined_as=page`."""
    legacy = pw.group(conn, joined_as=None)
    conn.commit()
    assert db.one(conn, "SELECT joined_as FROM community_groups WHERE id = ?", (legacy,))["joined_as"] == "profile"
    for value, joined in (("page", 1), ("none", 0), ("profile", 1)):
        result = pw.invoke("community", "set", str(legacy), f"joined_as={value}")
        assert result.exit_code == 0, result.output
        row = db.one(conn, "SELECT joined_as, joined FROM community_groups WHERE id = ?", (legacy,))
        assert (row["joined_as"], row["joined"]) == (value, joined)
    assert pw.invoke("community", "set", str(legacy), "joined=no").exit_code == 0
    assert db.one(conn, "SELECT joined_as FROM community_groups WHERE id = ?", (legacy,))["joined_as"] == "none"
    refused = pw.invoke("community", "set", str(legacy), "joined_as=friend")
    assert refused.exit_code != 0 and "joined_as must be none, profile or page" in refused.output


# --- items and requests from `community publish-plan` (SC1, BP §5.4) -------------------------------


def _plan_week(conn) -> dict[str, int]:
    """Three planned posts this week: in a group joined as the Page, a legacy group (joined as
    Ting Yu) and a Page group that only takes personal profiles."""
    page = pw.group(conn)
    legacy = pw.group(conn, joined_as=None)
    profiles_only = pw.group(conn, pages_allowed="no")
    posts = {"page": pw.planned(conn, page), "legacy": pw.planned(conn, legacy, day=pw.DAY + timedelta(days=1)),
             "profiles only": pw.planned(conn, profiles_only, day=pw.DAY + timedelta(days=2))}
    conn.commit()
    return posts


def test_publish_plan_raises_a_community_post_request_only_in_groups_joined_as_the_page(conn, world, discord_double):
    posts = _plan_week(conn)
    result = pw.invoke("community", "publish-plan", "--week", "2026-W46")
    assert result.exit_code == 0, result.output
    made = db.rows(conn, "SELECT * FROM publish_items WHERE kind = 'community_post'")
    assert [int(r["ref"]) for r in made] == [posts["page"]]
    [request] = approvals.pending(conn, "community-post")
    assert request.subject == items.subject_of(made[0]["id"]) and f"{request.id}" in result.output
    [card] = discord_double.posts("approvals")
    assert request.id in card.content and "decide by Tue 10 Nov, 18:00 SGT" in card.content
    assert "the Jura Solutions Facebook Page" in card.content and "facebook.com/groups/sg-owners-" in card.content
    assert pw.GROUP_TEXT in card.content
    again = pw.invoke("community", "publish-plan", "--week", "2026-W46")
    assert again.exit_code == 0 and db.scalar(conn, "SELECT count(*) FROM publish_items") == 1
    assert len(approvals.pending(conn, "community-post")) == 1


def test_with_community_browser_off_publish_plan_raises_nothing(conn, world, monkeypatch, discord_double):
    pw.community_config(monkeypatch, browser=False)
    _plan_week(conn)
    assert pw.invoke("community", "publish-plan", "--week", "2026-W46").exit_code == 0
    assert db.scalar(conn, "SELECT count(*) FROM publish_items") == 0
    assert approvals.pending(conn) == []


def test_a_community_posts_deadlines_are_the_end_of_the_window_on_its_day(conn, world):
    found, request = pw.community_item(conn, day=pw.DAY + timedelta(days=2))
    assert request.decide_by == "2026-11-12T18:00:00+08:00"
    assert pw.decide(conn, request).answer == "recorded"
    assert approvals.get(conn, request.id).use_by == "2026-11-12T18:00:00+08:00"


# --- AC-P3.4 a join's deadlines, and the answers step's ---------------------------------------


def test_a_join_proposed_monday_is_decided_by_sunday_18_00(conn, world, monkeypatch):
    pw.at(monkeypatch, "2026-11-09T07:45:00+08:00")
    group = pw.not_joined(conn)
    result = pw.invoke("community", "propose-join", str(group))
    assert result.exit_code == 0, result.output
    [request] = approvals.pending(conn, "group-join")
    assert request.decide_by == "2026-11-15T18:00:00+08:00" and request.id in result.output
    pw.at(monkeypatch, "2026-11-12T09:30:00+08:00")
    assert pw.decide(conn, request).answer == "recorded"
    assert approvals.get(conn, request.id).use_by == "2026-11-15T18:00:00+08:00"


def test_a_join_proposed_after_sundays_window_counts_in_the_next_week(conn, world, monkeypatch):
    """The week's last chance to act ends Sunday 18:00, so a proposal after it belongs to the next
    ISO week: decided by the next Sunday, and counted against that week's cap."""
    pw.at(monkeypatch, "2026-11-15T18:30:00+08:00")
    found, request = pw.join_item(conn)
    assert found.day == "2026-11-16" and request.decide_by == "2026-11-22T18:00:00+08:00"
    assert items.proposals_in_week(conn, date(2026, 11, 16)) == 1
    assert items.proposals_in_week(conn, date(2026, 11, 15)) == 0


def test_an_answers_item_raised_tuesday_is_decided_by_friday_18_00(conn, world, monkeypatch):
    found, _ = pw.join_item(conn)
    answers, request = pw.answers_item(conn, found)
    assert answers.parent_item == found.id and answers.kind == "community_join_answers"
    assert request.kind == "group-join" and request.decide_by == "2026-11-13T18:00:00+08:00"
    pw.at(monkeypatch, "2026-11-12T17:00:00+08:00")
    assert pw.decide(conn, request).answer == "recorded"
    assert approvals.get(conn, request.id).use_by == "2026-11-13T18:00:00+08:00"


def test_the_join_and_answers_cards_show_the_group_and_the_exact_answers(conn, world, discord_double):
    join, _ = pw.join_item(conn)
    pw.answers_item(conn, join)
    cards.sweep(conn)
    join_card, answers_card = discord_double.posts("approvals")
    assert "group join" in join_card.content and "facebook.com/groups/sg-owners-" in join_card.content
    assert "decide by Sun 15 Nov, 18:00 SGT" in join_card.content
    for pair in pw.QUESTIONS:
        assert pair["question"] in answers_card.content and pair["answer"] in answers_card.content
    assert "decide by Fri 13 Nov, 18:00 SGT" in answers_card.content


# --- propose-join: which groups, and the weekly cap (BP §5.4) ---------------------------------


@pytest.mark.parametrize("why, given", [
    ("already joined as the Jura Page", {"joined_as": "page", "joined": 1}),
    ("only personal profiles can join or post", {"pages_allowed": "no"}),
    ("isn't a good fit", {"fit": "possible"}),
    ("was removed", {"removed": 1, "fit": "skip"}),
    ("a join is already requested", {"join_status": "requested"}),
])
def test_propose_join_refuses_a_group_that_cant_be_joined_as_the_page(conn, world, why, given):
    group = pw.not_joined(conn, **given)
    conn.commit()
    result = pw.invoke("community", "propose-join", str(group))
    assert result.exit_code == 1 and why in result.output
    assert approvals.pending(conn) == []


def test_a_legacy_group_joined_as_ting_yu_can_be_proposed_for_a_page_join(conn, world):
    group = pw.group(conn, joined_as=None)
    conn.commit()
    assert pw.invoke("community", "propose-join", str(group)).exit_code == 0
    assert len(approvals.pending(conn, "group-join")) == 1


def test_propose_join_stops_at_the_weekly_cap_and_never_twice_for_one_group(conn, world, monkeypatch):
    groups = [pw.not_joined(conn) for _ in range(4)]
    conn.commit()
    for group in groups[:3]:
        assert pw.invoke("community", "propose-join", str(group)).exit_code == 0
    again = pw.invoke("community", "propose-join", str(groups[0]))
    assert again.exit_code == 1 and "already has a join waiting" in again.output
    capped = pw.invoke("community", "propose-join", str(groups[3]))
    assert capped.exit_code == 1 and "3 joins proposed in 2026-W46" in capped.output
    pw.at(monkeypatch, "2026-11-16T07:45:00+08:00")  # Monday of the next ISO week
    assert pw.invoke("community", "propose-join", str(groups[3])).exit_code == 0


def test_with_community_browser_off_propose_join_raises_nothing(conn, world, monkeypatch):
    pw.community_config(monkeypatch, browser=False)
    group = pw.not_joined(conn)
    conn.commit()
    result = pw.invoke("community", "propose-join", str(group))
    assert result.exit_code == 1 and "community.browser is off" in result.output
    assert approvals.pending(conn) == []


@pytest.mark.parametrize("configured, cap", [(None, 3), (10, 3), (2, 2), (0, 0)])
def test_joins_per_week_in_community_yaml_may_only_lower_the_cap(world, monkeypatch, configured, cap):
    """AC-P5.4 for BP §5.10's `joins_per_week`."""
    pw.community_config(monkeypatch, joins_per_week=configured)
    assert limits.community_joins_per_week() == cap


def test_the_shipped_community_config_keeps_browser_off_and_the_hard_join_cap():
    shipped = yaml.safe_load((paths.REPO_ROOT / "config" / "community.yaml").read_text())
    assert shipped["browser"] is False and shipped["joins_per_week"] == 3


# --- AC-P1.3 one field changed at a time (G9's community fields and answers) -------------------------


def _identity(monkeypatch, name: str) -> None:
    real = config.agent_config

    def patched(agent):
        base = dict(real(agent))
        if agent == "social":
            platforms = dict(base["platforms"])
            platforms["facebook"] = {**platforms["facebook"], "identity": name}
            base["platforms"] = platforms
        return base

    monkeypatch.setattr(config, "agent_config", patched)


def _post_change(conn, monkeypatch, found, field: str) -> None:
    post = db.one(conn, "SELECT * FROM community_posts WHERE id = ?", (found.ref_id,))
    if field == "text":
        conn.execute("UPDATE community_posts SET text = text || ' Thanks for reading.' WHERE id = ?", (found.ref_id,))
    elif field == "image bytes":
        Path(post["image_path"]).write_bytes(pw.png(extra=b"changed"))
    elif field == "group":
        conn.execute("UPDATE community_posts SET group_id = ? WHERE id = ?", (pw.group(conn), found.ref_id))
    elif field == "destination":
        conn.execute("UPDATE community_groups SET url = url || '-new' WHERE id = ?", (post["group_id"],))
    elif field == "posting identity":
        _identity(monkeypatch, "the Jura Solutions test Page")
    elif field == "day":
        conn.execute("UPDATE community_posts SET planned_day = '2026-11-12' WHERE id = ?", (found.ref_id,))


COMMUNITY_FIELDS = ["text", "image bytes", "group", "destination", "posting identity", "day"]


@pytest.mark.parametrize("field", COMMUNITY_FIELDS)
def test_any_one_community_post_field_changes_its_content(conn, world, monkeypatch, field):
    found, request = pw.community_item(conn, image=pw.image("group.png"))
    kind = approvals.kinds()["community-post"].kind
    before = kind.content(conn, found.subject)
    assert approvals.content_hash(before) == request.content_hash
    _post_change(conn, monkeypatch, found, field)
    after = kind.content(conn, found.subject)
    assert after is not None and after != before


@pytest.mark.parametrize("field", COMMUNITY_FIELDS)
def test_a_changed_approved_community_post_gets_a_fresh_request_on_the_same_item(conn, world, monkeypatch, field):
    """AC-P1.3 (as amended 2026-10-27, and G9): refused, superseded, and a fresh request raised over the
    new content, with the deadlines of the new content's day."""
    found, request = pw.community_item(conn, image=pw.image("group.png"))
    pw.decide(conn, request)
    _post_change(conn, monkeypatch, found, field)
    handed = pw.next_item(conn, pw.run(conn))
    assert handed.item is None
    assert approvals.get(conn, request.id).status == "superseded"
    [fresh] = approvals.pending(conn, "community-post")
    assert fresh.subject == found.subject and fresh.supersedes == request.number
    assert fresh.decide_by == ("2026-11-12T18:00:00+08:00" if field == "day" else "2026-11-10T18:00:00+08:00")
    item = items.get(conn, found.id)
    assert item.state == "ready" and approvals.content_hash(kinds.hashed(item.content)) == fresh.content_hash


@pytest.mark.parametrize("field", ["destination", "posting identity", "answers"])
def test_a_changed_join_or_answers_item_gets_a_fresh_request(conn, world, monkeypatch, field):
    join, _ = pw.join_item(conn)
    answers, request = pw.answers_item(conn, join)
    pw.decide(conn, request)
    if field == "destination":
        conn.execute("UPDATE community_groups SET url = url || '-new' WHERE id = ?", (join.ref_id,))
        pw.next_item(conn, pw.run(conn))
    elif field == "posting identity":
        _identity(monkeypatch, "the Jura Solutions test Page")
        pw.next_item(conn, pw.run(conn))
    else:  # the run reported the questions again, with different answers drafted
        changed = [dict(pw.QUESTIONS[0]), {**pw.QUESTIONS[1], "answer": "Yes, we have read them."}]
        made = items.create_join_answers(conn, join, changed, run_id=None)
        assert made.item.id == answers.id
    assert approvals.get(conn, request.id).status == "superseded"
    [fresh] = [a for a in approvals.pending(conn, "group-join") if a.subject == answers.subject]
    assert fresh.supersedes == request.number and fresh.content_hash != request.content_hash
    assert items.get(conn, answers.id).state == "ready"


def test_the_same_answers_reported_again_keep_their_request(conn, world):
    join, _ = pw.join_item(conn)
    answers, request = pw.answers_item(conn, join)
    again = items.create_join_answers(conn, join, pw.QUESTIONS, run_id=None)
    assert again.item.id == answers.id and again.approval.id == request.id


@pytest.mark.parametrize("gone", ["posted by hand", "community removed", "pages not allowed", "skipped"])
def test_a_community_post_that_is_gone_supersedes_with_no_new_request(conn, world, gone):
    found, request = pw.community_item(conn)
    post = db.one(conn, "SELECT group_id FROM community_posts WHERE id = ?", (found.ref_id,))
    if gone == "posted by hand":
        plan.mark_posted(conn, found.ref_id, "https://www.facebook.com/groups/x/posts/1")
    elif gone == "community removed":
        community_groups.remove(conn, post["group_id"], "an admin removed a post")
    elif gone == "pages not allowed":
        conn.execute("UPDATE community_groups SET pages_allowed = 'no' WHERE id = ?", (post["group_id"],))
    else:
        conn.execute("UPDATE community_posts SET status = 'skipped' WHERE id = ?", (found.ref_id,))
    approvals.expire_due(conn)
    assert approvals.get(conn, request.id).status == "superseded"
    assert approvals.pending(conn) == []
    assert approvals.kinds()["community-post"].kind.superseded_note(conn, found.subject) == {
        "posted by hand": "posted by hand", "community removed": "the group was removed",
        "pages not allowed": "only personal profiles can join or post in this group", "skipped": "skipped by hand",
    }[gone]


# --- the claim: what `publish next` hands out ----------------------------------------------------


def next_json():
    result = pw.invoke("publish", "next", "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_an_approved_community_post_is_claimed_with_its_text_and_image(conn, world, monkeypatch):
    found, request = pw.community_item(conn, text=pw.PROMO_TEXT, image=pw.image("group.png"))
    pw.decide(conn, request)
    pw.run(conn, monkeypatch=monkeypatch)
    handed = next_json()
    assert handed["due"] is True and handed["approval"] == request.id and handed["kind"] == "community-post"
    assert handed["text"] == pw.PROMO_TEXT and handed["posting_identity"] == "the Jura Solutions Facebook Page"
    assert handed["target_url"].startswith("https://www.facebook.com/groups/sg-owners-")
    [copy] = handed["images"]
    assert Path(copy).read_bytes() == pw.PNG and paths.is_within(Path(copy), paths.work_dir("publish"))
    assert items.get(conn, found.id).state == "claimed" and approvals.get(conn, request.id).used_at


def test_an_approved_join_and_its_approved_answers_are_handed_out(conn, world, monkeypatch):
    join, request = pw.join_item(conn)
    pw.decide(conn, request)
    pw.run(conn, monkeypatch=monkeypatch)
    handed = next_json()
    assert handed["kind"] == "group-join" and handed["approval"] == request.id and handed["answers"] is None
    answers, second = pw.answers_item(conn, items.get(conn, join.id))
    pw.decide(conn, second)
    pw.at(monkeypatch, "2026-11-10T10:30:00+08:00")
    pw.run(conn, monkeypatch=monkeypatch)
    handed = next_json()
    assert handed["approval"] == second.id and handed["answers"] == pw.QUESTIONS
    assert approvals.get(conn, request.id).used_at  # raising the answers never touched the used join approval


def _claimed_post(conn, group_id: int, day: str) -> None:
    """A community post in `group_id` claimed by a run at 09:00 on `day` (it went out)."""
    post = pw.planned(conn, group_id, day=date.fromisoformat(day), status="posted")
    conn.execute(
        "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, state, "
        "outcome, created_at, claimed_at) VALUES ('P-x', 'community_post', 'facebook', ?, 'u', 'p', ?, ?, 'done', 'posted', ?, ?)",
        (str(post), json.dumps({"group": group_id}), day, f"{day}T08:00:00+08:00", f"{day}T09:00:00+08:00"),
    )
    conn.execute("UPDATE community_posts SET posted_at = NULL WHERE id = ?", (post,))


def _claimed_join(conn, group_id: int, day: str) -> None:
    conn.execute(
        "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, state, "
        "outcome, created_at, claimed_at) VALUES ('P-j', 'community_join', 'facebook', ?, 'u', 'p', '{}', ?, 'done', "
        "'requested', ?, ?)", (str(group_id), day, f"{day}T08:00:00+08:00", f"{day}T09:00:00+08:00"),
    )


def _refused(conn, request, why: str) -> None:
    handed = pw.next_item(conn, pw.run(conn))
    assert handed.item is None, handed
    assert any(why in reason for reason in handed.why), handed.why
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None


def _claimed(conn, request) -> None:
    handed = pw.next_item(conn, pw.run(conn))
    assert handed.approval is not None and handed.approval.id == request.id, handed.why


@pytest.mark.parametrize("when, refused", [("2026-11-15T17:00:00+08:00", True), ("2026-11-16T09:00:00+08:00", False)])
def test_line_2_a_fourth_group_in_the_iso_week_is_refused(conn, world, monkeypatch, when, refused):
    for day in ("2026-11-09", "2026-11-10", "2026-11-11"):
        _claimed_post(conn, pw.group(conn), day)
    pw.at(monkeypatch, when)
    found, request = pw.community_item(conn, day=date.fromisoformat(when[:10]))
    pw.decide(conn, request)
    if refused:
        _refused(conn, request, "3 groups posted to in 2026-W46 already; the cap is 3 a week")
    else:
        _claimed(conn, request)


def test_line_3_a_second_community_post_on_the_same_day_is_refused(conn, world):
    _claimed_post(conn, pw.group(conn), "2026-11-10")
    _, request = pw.community_item(conn)
    pw.decide(conn, request)
    _refused(conn, request, "a community post already went out today; the cap is 1 a day")


def test_line_3_a_post_made_by_hand_today_counts_too(conn, world):
    other = pw.planned(conn, pw.group(conn))
    plan.mark_posted(conn, other, "https://www.facebook.com/groups/x/posts/2")
    _, request = pw.community_item(conn)
    pw.decide(conn, request)
    _refused(conn, request, "a community post already went out today")


@pytest.mark.parametrize("when, refused", [("2026-11-12T10:00:00+08:00", True), ("2026-11-16T10:00:00+08:00", False)])
def test_line_4_a_fourth_join_in_the_week_is_refused(conn, world, monkeypatch, when, refused):
    """The claim's own cap, whatever was proposed: here the item is raised before the three claims
    are seeded, so `propose-join`'s cap (tested above) doesn't stop it first."""
    pw.at(monkeypatch, when)
    _, request = pw.join_item(conn)
    pw.decide(conn, request)
    for day in ("2026-11-09", "2026-11-10", "2026-11-11"):
        _claimed_join(conn, pw.not_joined(conn), day)
    if refused:
        _refused(conn, request, "3 joins claimed in 2026-W46 already; the cap is 3 a week")
    else:
        _claimed(conn, request)


def test_line_4_the_answers_step_is_not_a_fourth_join(conn, world, monkeypatch):
    join, request = pw.join_item(conn)
    pw.decide(conn, request)
    _claimed(conn, request)
    for day in ("2026-11-09", "2026-11-10"):
        _claimed_join(conn, pw.not_joined(conn), day)
    _, answers = pw.answers_item(conn, items.get(conn, join.id))
    pw.decide(conn, answers)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    _claimed(conn, answers)


@pytest.mark.parametrize("last, refused", [("2026-10-28", True), ("2026-10-27", False)])
def test_line_5_a_group_posted_to_13_days_ago_is_refused_and_14_allowed(conn, world, last, refused):
    group = pw.group(conn, last_posted_at=f"{last}T11:00:00+08:00")
    _, request = pw.community_item(conn, group)
    pw.decide(conn, request)
    if refused:
        _refused(conn, request, f"the group was posted to on {last}; no group within 14 days of its last post")
    else:
        _claimed(conn, request)


def test_line_5_a_claim_in_the_group_13_days_ago_counts_like_a_post(conn, world):
    group = pw.group(conn)
    _claimed_post(conn, group, "2026-10-28")
    _, request = pw.community_item(conn, group)
    pw.decide(conn, request)
    _refused(conn, request, "the group was posted to on 2026-10-28")


@pytest.mark.parametrize("given, text, why", [
    ({"post_days": "sat,sun"}, pw.GROUP_TEXT, "the group allows posts only on sat, sun"),
    ({"promo_days": "sat"}, pw.PROMO_TEXT, "the group allows promotion only on sat"),
])
def test_line_8_a_day_the_confirmed_rules_close_is_refused(conn, world, given, text, why):
    _, request = pw.community_item(conn, pw.group(conn, **given), text=text)
    pw.decide(conn, request)
    _refused(conn, request, f"Tue 10 Nov breaks the group's rules: {why}")


def test_line_8_a_value_post_on_a_day_closed_only_to_promotion_is_claimed(conn, world):
    _, request = pw.community_item(conn, pw.group(conn, promo_days="sat"))
    pw.decide(conn, request)
    _claimed(conn, request)


def test_line_9_rules_confirmed_but_days_unconfirmed_is_refused(conn, world):
    _, request = pw.community_item(conn, pw.group(conn, promo_days=None, post_days=None))
    pw.decide(conn, request)
    _refused(conn, request, "open days not confirmed")


def test_rules_not_confirmed_are_refused(conn, world):
    _, request = pw.community_item(conn, pw.group(conn, rules_confirmed=0))
    pw.decide(conn, request)
    _refused(conn, request, "the group's rules aren't confirmed by Ting Yu")


@pytest.mark.parametrize("joined_as", ["profile", "none"])
def test_line_10_a_group_not_joined_as_the_page_is_refused(conn, world, joined_as):
    group = pw.group(conn)
    _, request = pw.community_item(conn, group)
    pw.decide(conn, request)
    conn.execute("UPDATE community_groups SET joined_as_set = ? WHERE id = ?", (joined_as, group))
    _refused(conn, request, "its group isn't joined as the Jura Page")


def test_a_group_no_longer_a_good_fit_is_refused(conn, world):
    group = pw.group(conn)
    _, request = pw.community_item(conn, group)
    pw.decide(conn, request)
    conn.execute("UPDATE community_groups SET fit = 'possible' WHERE id = ?", (group,))
    _refused(conn, request, "its group isn't a good fit")


@pytest.mark.parametrize("given, why", [
    ({"joined_as_set": "page"}, "its group is already joined as the Jura Page"),
    ({"join_status": "requested"}, "its group's join is already requested"),
    ({"join_status": "member"}, "its group's join is already member"),
])
def test_a_join_for_a_group_already_joined_or_requested_is_refused(conn, world, given, why):
    join, request = pw.join_item(conn)
    pw.decide(conn, request)
    [(column, value)] = given.items()
    conn.execute(f"UPDATE community_groups SET {column} = ? WHERE id = ?", (value, join.ref_id))
    _refused(conn, request, why)


def test_a_join_is_claimable_until_its_sunday_18_00(conn, world, monkeypatch):
    pw.at(monkeypatch, "2026-11-09T09:30:00+08:00")
    _, request = pw.join_item(conn)
    pw.decide(conn, request)
    pw.at(monkeypatch, "2026-11-15T17:59:59+08:00")
    _claimed(conn, request)


def test_a_join_unclaimed_at_sunday_18_00_is_expired(conn, world, monkeypatch):
    pw.at(monkeypatch, "2026-11-09T09:30:00+08:00")
    found, request = pw.join_item(conn)
    pw.decide(conn, request)
    pw.at(monkeypatch, "2026-11-16T09:30:00+08:00")
    assert pw.next_item(conn, pw.run(conn)).item is None
    assert approvals.get(conn, request.id).status == "expired" and items.get(conn, found.id).state == "withdrawn"


# --- AC-P5.3 the community switch ---------------------------------------------------------------


@pytest.mark.parametrize("which", ["community post", "join", "answers"])
def test_with_community_browser_off_nothing_is_claimed_and_the_approval_is_kept(conn, world, monkeypatch, which):
    if which == "community post":
        _, request = pw.community_item(conn)
    elif which == "join":
        _, request = pw.join_item(conn)
    else:
        _, request = pw.answers_item(conn)
    pw.decide(conn, request)
    pw.community_config(monkeypatch, browser=False)
    handed = pw.next_item(conn, pw.run(conn))
    assert handed.item is None and any("community.browser is off" in reason for reason in handed.why)
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None
    pw.community_config(monkeypatch, browser=True)
    pw.at(monkeypatch, "2026-11-10T10:30:00+08:00")
    _claimed(conn, request)


# --- the other publish commands on a community item ---------------------------------------------


def test_a_stop_signal_on_a_community_item_stops_it_and_pauses_publish(conn, world, monkeypatch, discord_double):
    found, request = pw.community_item(conn)
    pw.decide(conn, request)
    assert next_json()["due"] is True
    result = pw.invoke("publish", "stopped", request.id, "--reason", "admin-warning")
    assert result.exit_code == 0, result.output
    assert items.get(conn, found.id).state == "stopped" and pause.is_paused(conn, "publish")
    assert any(request.id in post.content for post in discord_double.posts("alerts"))


def test_publish_done_isnt_taken_for_a_community_item_yet(conn, world, monkeypatch, tmp_path):
    found, request = pw.community_item(conn)
    pw.decide(conn, request)
    next_json()
    live = tmp_path / "live.txt"
    live.write_text(pw.GROUP_TEXT)
    result = pw.invoke("publish", "done", request.id, "--url", "https://www.facebook.com/groups/x/posts/1",
                       "--live-text-file", str(live))
    assert result.exit_code == 1 and "social posts only" in result.output
    assert items.get(conn, found.id).state == "claimed"


def test_an_unknown_community_item_is_settled_as_not_posted(conn, world, monkeypatch):
    found, request = pw.join_item(conn)
    pw.decide(conn, request)
    run = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    publish.after_run(conn, "publish", run, runner.Outcome("ok"))
    assert items.get(conn, found.id).state == "unknown"
    refused = pw.invoke("publish", "resolve", request.id, "posted", "--url", "https://www.facebook.com/groups/x")
    assert refused.exit_code == 1 and "not-posted" in refused.output
    assert pw.invoke("publish", "resolve", request.id, "not-posted").exit_code == 0
    assert items.get(conn, found.id).state == "withdrawn"


# --- AC-M4.7 the publish plug-in failed to load ---------------------------------------------------


@pytest.mark.parametrize("which", ["community post", "join", "answers"])
def test_with_the_publish_plug_in_missing_a_community_approval_fails_closed(conn, world, monkeypatch, which):
    build = {"community post": pw.community_item, "join": pw.join_item, "answers": pw.answers_item}[which]
    found, request = build(conn)
    pw.decide(conn, request)
    real = agents.plugins
    monkeypatch.setattr(agents, "plugins", lambda: tuple(m for m in real() if getattr(m, "NAME", None) != "publish"))
    with pytest.raises(approvals.NotApproved) as refused:
        with db.transaction(conn):
            approvals.use(conn, request.kind, found.subject, run_id=None)
    assert refused.value.reason == "unknown-kind"
    pw.at(monkeypatch, "2026-11-23T10:00:00+08:00")  # past every deadline
    assert approvals.expire_due(conn) == []
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None


# --- the sweep (AC-M11.1, AC-M12.1) over community-post and group-join cards, answers included ------


def test_community_and_join_cards_carry_nothing_planted(conn, world, discord_double, d2_secrets):
    marked = planted()
    posted_in = pw.group(conn)
    conn.execute("UPDATE community_groups SET name = ?, promo_rules = ? WHERE id = ?",
                 (f"Owners {marked.marker} {RESEND_KEY}", f"Promotion is welcome. {PHONE}", posted_in))
    pw.community_item(conn, posted_in, text=marked.text())
    joining = pw.not_joined(conn)
    conn.execute("UPDATE community_groups SET fit_reason = ? WHERE id = ?",
                 (f"Owners asking {marked.marker} {KEYCHAIN_VALUE} {NAMED_ADDRESS}", joining))
    join, _ = pw.join_item(conn, joining)
    answers = [{"question": f"Why join? {marked.marker}", "answer": marked.text()},
               {"question": f"Your email? {NAMED_ADDRESS}", "answer": f"{PHONE} {AWKWARD}"}]
    pw.answers_item(conn, join, answers)
    conn.commit()
    cards.sweep(conn)
    assert len(discord_double.posts("approvals")) == 3
    assert_clean(discord_double, outbox_dir(), marked)
