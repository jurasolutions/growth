"""Group joins as the Jura Page (browser publishing PRD SC4; ticket BP-06; dataset D10).

Seam S7: `publish done <A-id> --outcome …` and `publish note-rules`, through click's runner with
a claimed join, as the publish run calls them. Rows traced: AC-P4.1, AC-P4.2 (the command half),
AC-P4.3 (the handler, for every item kind), AC-P4.4 and X10. The whole run (S10) is in
`test_publish_join_run.py`.
"""

from __future__ import annotations

import json

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, db, pause
from jura_growth.agents.community import groups as community_groups
from jura_growth.agents.publish import items


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    pw.community_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


def claimed_join(conn, monkeypatch, group_id: int | None = None):
    """An approved join, claimed by a publish run (whose id is now the current run)."""
    join, request = pw.join_item(conn, group_id)
    pw.decide(conn, request)
    run = pw.run(conn, monkeypatch=monkeypatch)
    handed = pw.next_item(conn, run)
    assert handed.approval is not None and handed.approval.id == request.id, handed.why
    return items.get(conn, join.id), request


def group_row(conn, item) -> dict:
    return community_groups.get(conn, item.ref_id)


def requests(conn) -> list[str]:
    return [r["id"] for r in db.rows(conn, "SELECT id FROM approvals ORDER BY id")]


# --- AC-P4.1 a join with no questions -------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["requested", "member", "declined"])
def test_a_join_records_its_outcome_and_join_status_and_raises_nothing(conn, world, monkeypatch, discord_double, outcome):
    join, request = claimed_join(conn, monkeypatch)
    before = requests(conn)

    result = pw.invoke("publish", "done", request.id, "--outcome", outcome)

    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, join.id)
    assert row["state"] == "done" and row["outcome"] == outcome
    assert group_row(conn, join)["join_status"] == outcome
    assert requests(conn) == before  # no second request
    assert discord_double.contents("alerts") == []
    assert not pause.is_paused(conn, "publish")


def test_a_join_may_carry_the_groups_url_on_facebooks_own_host(conn, world, monkeypatch):
    join, request = claimed_join(conn, monkeypatch)
    wrong = pw.invoke("publish", "done", request.id, "--outcome", "requested", "--url", "https://facebook.com.evil.test/g")
    assert wrong.exit_code != 0 and "refused" in wrong.output
    assert pw.item_row(conn, join.id)["state"] == "claimed"
    url = join.content["target_url"]
    assert pw.invoke("publish", "done", request.id, "--outcome", "requested", "--url", url).exit_code == 0
    assert pw.item_row(conn, join.id)["post_url"] == url


def test_an_outcome_needs_a_claimed_item(conn, world):
    join, request = pw.join_item(conn)
    pw.decide(conn, request)
    unclaimed = pw.invoke("publish", "done", request.id, "--outcome", "requested")
    assert unclaimed.exit_code != 0 and "isn't claimed" in unclaimed.output
    assert pw.item_row(conn, join.id)["state"] == "ready"


def test_a_social_post_takes_no_join_outcome_and_an_outcome_no_live_text_file(conn, world, monkeypatch, tmp_path):
    social, social_request = pw.approved(conn, monkeypatch)
    assert pw.next_item(conn, pw.run(conn, monkeypatch=monkeypatch)).approval.id == social_request.id
    refused = pw.invoke("publish", "done", social_request.id, "--outcome", "member")
    assert refused.exit_code != 0 and "is for a join" in refused.output
    live = tmp_path / "live.txt"
    live.write_text("x")
    both = pw.invoke("publish", "done", social_request.id, "--outcome", "member", "--live-text-file", str(live))
    assert both.exit_code == 2
    assert pw.item_row(conn, social.id)["state"] == "claimed"


# --- AC-P4.4 member sets joined_as = page; rules still need a decision -------------------------------


def test_a_membership_joins_the_group_as_the_page_but_posts_wait_for_a_rules_decision(conn, world, monkeypatch):
    join, request = claimed_join(conn, monkeypatch)
    assert pw.invoke("publish", "done", request.id, "--outcome", "member").exit_code == 0
    group = group_row(conn, join)
    assert group["joined_as"] == "page" and group["joined"] == 1 and group["pages_allowed"] == "yes"
    assert group["rules_confirmed"] == 0

    post = pw.planned(conn, join.ref_id)
    made = items.create_community_post(conn, post, run_id=None)
    assert made.approval is not None, made.why
    pw.decide(conn, made.approval)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    handed = pw.next_item(conn, pw.run(conn))
    assert handed.item is None and any("rules aren't confirmed" in why for why in handed.why), handed.why
    assert approvals.get(conn, made.approval.id).used_at is None


def test_a_request_records_that_the_group_allows_pages_and_is_not_proposed_again(conn, world, monkeypatch):
    join, request = claimed_join(conn, monkeypatch)
    assert pw.invoke("publish", "done", request.id, "--outcome", "requested").exit_code == 0
    group = group_row(conn, join)
    assert group["pages_allowed"] == "yes" and group["joined_as"] == "none"
    again = items.create_join(conn, join.ref_id, run_id=None)
    assert again.approval is None and "already requested" in again.why


# --- AC-P4.2 membership questions: nothing submitted, the answers become their own item ------------------

BAD_ANSWERS = [
    {"question": "Why do you want to join?", "answer": "We have saved 40 clients 300 hours this year!"},
    {"question": "Do you agree to the group rules?", "answer": "Yes."},
]


def q_file(tmp_path, answers=None, name: str = "q.json"):
    path = tmp_path / name
    path.write_text(json.dumps(pw.QUESTIONS if answers is None else answers), encoding="utf-8")
    return str(path)


def answers_items(conn, join) -> list[dict]:
    return db.rows(conn, "SELECT * FROM publish_items WHERE kind = 'community_join_answers' AND parent_item = ?", (join.id,))


def test_questions_record_the_join_and_raise_the_answers_as_their_own_item_and_card(
        conn, world, monkeypatch, discord_double, tmp_path):
    join, request = claimed_join(conn, monkeypatch)

    result = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path))

    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, join.id)
    assert row["state"] == "done" and row["outcome"] == "questions"
    [answers] = answers_items(conn, join)
    assert json.loads(answers["content_json"])["answers"] == pw.QUESTIONS and answers["state"] == "ready"
    second = approvals.pending(conn)
    assert [r.kind for r in second] == ["group-join"] and second[0].subject == items.subject_of(answers["id"])
    assert second[0].id in result.output
    card = discord_double.contents("approvals")
    assert card and "Why do you want to join?" in card[-1] and pw.QUESTIONS[0]["answer"] in card[-1]
    assert approvals.get(conn, request.id).used_at  # the join's own approval stays used
    assert group_row(conn, join)["join_status"] is None  # nothing was submitted
    assert discord_double.contents("alerts") == []
    assert not pause.is_paused(conn, "publish")


def test_answers_that_fail_the_brand_gate_raise_nothing_and_may_be_fixed_once(conn, world, monkeypatch, discord_double, tmp_path):
    join, request = claimed_join(conn, monkeypatch)

    failed = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, BAD_ANSWERS))

    assert failed.exit_code == 1
    assert "brand check" in failed.output and "exclamation" in failed.output.lower()
    assert pw.item_row(conn, join.id)["outcome"] == "questions"  # the questions were met all the same
    assert answers_items(conn, join) == [] and approvals.pending(conn) == []
    assert discord_double.contents("alerts") == [] and not pause.is_paused(conn, "publish")

    fixed = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, name="q2.json"))
    assert fixed.exit_code == 0, fixed.output
    assert len(answers_items(conn, join)) == 1 and len(approvals.pending(conn)) == 1


def test_answers_that_fail_twice_are_dropped(conn, world, monkeypatch, tmp_path):
    join, request = claimed_join(conn, monkeypatch)
    for _ in range(2):
        pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, BAD_ANSWERS))
    third = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, name="q3.json"))
    assert third.exit_code == 1 and "dropped" in third.output
    assert answers_items(conn, join) == [] and approvals.pending(conn) == []


def test_only_the_run_that_met_the_questions_may_send_its_answers_again(conn, world, monkeypatch, tmp_path):
    join, request = claimed_join(conn, monkeypatch)
    pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, BAD_ANSWERS))
    pw.run(conn, monkeypatch=monkeypatch)  # a later run
    later = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, name="q2.json"))
    assert later.exit_code != 0 and "isn't claimed" in later.output
    assert answers_items(conn, join) == []


def test_answers_already_raised_are_not_raised_again_by_the_outcome(conn, world, monkeypatch, tmp_path):
    join, request = claimed_join(conn, monkeypatch)
    pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path))
    again = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, name="q2.json"))
    assert again.exit_code != 0 and "isn't claimed" in again.output
    assert len(answers_items(conn, join)) == 1


@pytest.mark.parametrize("given", [
    "not json",
    json.dumps({"questions": "Why?"}),
    json.dumps([{"question": "Why do you want to join?"}]),
    json.dumps([]),
    json.dumps([{"question": "Q", "answer": "A" * 1001}]),
    json.dumps([{"question": f"Q{n}", "answer": "Yes."} for n in range(11)]),
], ids=["not json", "not a list", "no answer", "empty", "answer too long", "too many"])
def test_a_questions_file_that_cant_be_read_records_nothing(conn, world, monkeypatch, tmp_path, given):
    join, request = claimed_join(conn, monkeypatch)
    path = tmp_path / "q.json"
    path.write_text(given, encoding="utf-8")
    result = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", str(path))
    assert result.exit_code != 0
    assert pw.item_row(conn, join.id)["state"] == "claimed" and answers_items(conn, join) == []


def test_the_questions_file_may_wrap_the_list(conn, world, monkeypatch, tmp_path):
    join, request = claimed_join(conn, monkeypatch)
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"questions": pw.QUESTIONS}), encoding="utf-8")
    assert pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", str(path)).exit_code == 0
    assert len(answers_items(conn, join)) == 1


def test_questions_need_their_file_and_only_questions_take_one(conn, world, monkeypatch, tmp_path):
    join, request = claimed_join(conn, monkeypatch)
    assert pw.invoke("publish", "done", request.id, "--outcome", "questions").exit_code == 2
    assert pw.invoke("publish", "done", request.id, "--outcome", "member", "--file", q_file(tmp_path)).exit_code == 2
    assert pw.item_row(conn, join.id)["state"] == "claimed"


def test_new_questions_met_while_submitting_answers_raise_fresh_answers_for_the_same_join(conn, world, monkeypatch, tmp_path):
    answers, request = claimed_answers(conn, monkeypatch)
    changed = [{"question": "Which industry are you in?", "answer": "We help small teams automate their admin."}]
    result = pw.invoke("publish", "done", request.id, "--outcome", "questions", "--file", q_file(tmp_path, changed))
    assert result.exit_code == 0, result.output
    assert pw.item_row(conn, answers.id)["outcome"] == "questions"
    fresh = [row for row in answers_items(conn, items.get(conn, answers.parent_item)) if row["id"] != answers.id]
    assert len(fresh) == 1 and json.loads(fresh[0]["content_json"])["answers"] == changed


def test_approved_answers_submitted_record_the_join_status(conn, world, monkeypatch):
    answers, request = claimed_answers(conn, monkeypatch)
    assert pw.invoke("publish", "done", request.id, "--outcome", "requested").exit_code == 0
    assert pw.item_row(conn, answers.id)["outcome"] == "requested"
    assert community_groups.get(conn, answers.ref_id)["join_status"] == "requested"


# --- X10 note-rules raises one group-rules request for the rules seen inside the group ------------------

SEEN = "No selling on weekdays.\nPromotion only on Saturdays, one post a week."


def rules_file(tmp_path, text: str = SEEN):
    path = tmp_path / "rules.txt"
    path.write_text(text, encoding="utf-8")
    return str(path)


def rules_requests(conn, group_id: int) -> list[approvals.Approval]:
    return [r for r in approvals.pending(conn) if r.kind == "group-rules" and r.subject == f"group:{group_id}"]


def test_note_rules_records_the_rules_seen_and_raises_one_group_rules_request(conn, world, monkeypatch, discord_double, tmp_path):
    join, _ = claimed_join(conn, monkeypatch)
    assert rules_requests(conn, join.ref_id) == []  # the researched rules raised nothing

    result = pw.invoke("publish", "note-rules", str(join.ref_id), "--file", rules_file(tmp_path))

    assert result.exit_code == 0, result.output
    assert group_row(conn, join)["promo_rules"] == SEEN
    [request] = rules_requests(conn, join.ref_id)
    assert request.id in result.output
    assert any("Promotion only on Saturdays" in card for card in discord_double.contents("approvals"))
    again = pw.invoke("publish", "note-rules", str(join.ref_id), "--file", rules_file(tmp_path))
    assert again.exit_code == 0 and len(rules_requests(conn, join.ref_id)) == 1
    assert discord_double.contents("alerts") == [] and not pause.is_paused(conn, "publish")


def test_rules_seen_as_ting_yu_confirmed_them_raise_nothing(conn, world, monkeypatch, tmp_path):
    group_id = pw.not_joined(conn, rules=SEEN, rules_confirmed=1, promo_days="sat", post_days="any")
    join, _ = claimed_join(conn, monkeypatch, group_id)
    result = pw.invoke("publish", "note-rules", str(group_id), "--file", rules_file(tmp_path))
    assert result.exit_code == 0, result.output
    assert rules_requests(conn, group_id) == [] and group_row(conn, join)["rules_confirmed"] == 1


def test_rules_seen_that_differ_from_the_confirmed_ones_clear_the_confirmation(conn, world, monkeypatch, tmp_path):
    group_id = pw.not_joined(conn, rules="Promotion is welcome.", rules_confirmed=1, promo_days="any", post_days="any")
    join, _ = claimed_join(conn, monkeypatch, group_id)
    assert pw.invoke("publish", "note-rules", str(group_id), "--file", rules_file(tmp_path)).exit_code == 0
    group = group_row(conn, join)
    assert group["promo_rules"] == SEEN and group["rules_confirmed"] == 0 and group["promo_days_confirmed"] is None
    assert len(rules_requests(conn, group_id)) == 1


def test_note_rules_only_for_a_group_this_run_claimed_an_item_in(conn, world, monkeypatch, tmp_path):
    join, _ = claimed_join(conn, monkeypatch)
    other = pw.not_joined(conn)
    refused = pw.invoke("publish", "note-rules", str(other), "--file", rules_file(tmp_path))
    assert refused.exit_code != 0 and "claimed" in refused.output
    monkeypatch.delenv("JURA_GROWTH_RUN_ID")
    outside = pw.invoke("publish", "note-rules", str(join.ref_id), "--file", rules_file(tmp_path))
    assert outside.exit_code != 0
    pw.run(conn, monkeypatch=monkeypatch)  # a later run, which claimed nothing
    later = pw.invoke("publish", "note-rules", str(join.ref_id), "--file", rules_file(tmp_path))
    assert later.exit_code != 0
    assert approvals.pending(conn) == [] and group_row(conn, join)["promo_rules"] != SEEN


@pytest.mark.parametrize("text", ["   \n", "x" * 4001], ids=["empty", "too long"])
def test_a_rules_file_that_is_empty_or_too_long_is_refused(conn, world, monkeypatch, tmp_path, text):
    join, _ = claimed_join(conn, monkeypatch)
    result = pw.invoke("publish", "note-rules", str(join.ref_id), "--file", rules_file(tmp_path, text))
    assert result.exit_code != 0 and approvals.pending(conn) == []


@pytest.mark.parametrize("community_browser", [True, False])
def test_the_facebook_hosts_open_for_group_items_even_with_the_page_in_draft(monkeypatch, community_browser):
    """A join or a group post needs Facebook's hosts whenever `community.browser` is on, even when
    the Facebook Page's own posts stay in `draft` mode."""
    from jura_growth.agents.publish import hosts, scope

    pw.social_config(monkeypatch, browser=())
    pw.community_config(monkeypatch, browser=community_browser)
    expected = tuple(hosts.BROWSER_HOSTS["facebook"]) if community_browser else ()
    assert scope.browser_hosts() == expected
    assert scope.domain_rules() == [f"ClaudeInChromeDomain({host})" for host in expected]


def test_the_publish_run_may_call_note_rules_and_still_nothing_that_decides():
    from jura_growth.agents.publish import scope

    assert "publish note-rules" in scope.COMMANDS
    assert not {"publish resolve", "approve", "skip", "resume"} & set(scope.COMMANDS)


# --- AC-P4.3 pages-not-allowed, for every item kind ---------------------------------------------------


def claimed_answers(conn, monkeypatch):
    join, _ = claimed_join(conn, monkeypatch)
    answers, request = pw.answers_item(conn, join)
    pw.decide(conn, request)
    pw.at(monkeypatch, "2026-11-10T10:30:00+08:00")
    handed = pw.next_item(conn, pw.run(conn, monkeypatch=monkeypatch))
    assert handed.approval is not None and handed.approval.id == request.id, handed.why
    return items.get(conn, answers.id), request


def claimed_post(conn, monkeypatch):
    found, request = pw.community_item(conn)
    pw.decide(conn, request)
    handed = pw.next_item(conn, pw.run(conn, monkeypatch=monkeypatch))
    assert handed.approval is not None and handed.approval.id == request.id, handed.why
    return items.get(conn, found.id), request


@pytest.mark.parametrize("kind", ["join", "answers", "community post"])
def test_pages_not_allowed_skips_the_group_for_good_without_alert_or_pause(conn, world, monkeypatch, discord_double, kind):
    found, request = {"join": claimed_join, "answers": claimed_answers, "community post": claimed_post}[kind](conn, monkeypatch)

    result = pw.invoke("publish", "done", request.id, "--outcome", "pages-not-allowed")

    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert row["state"] == "done" and row["outcome"] == "pages-not-allowed"
    group = community_groups.get(conn, found.content["group"])
    assert group["pages_allowed"] == "no" and group["fit"] == "skip"
    assert group["fit_reason"] == "only personal profiles can join or post"
    assert discord_double.contents("alerts") == []
    assert not pause.is_paused(conn, "publish")
    never = items.create_join(conn, group["id"], run_id=None)
    assert never.approval is None and never.item is None


def test_pages_not_allowed_supersedes_every_item_still_waiting_for_the_group(conn, world, monkeypatch, discord_double):
    found, request = claimed_post(conn, monkeypatch)
    group_id = found.content["group"]
    waiting = items.create_community_post(conn, pw.planned(conn, group_id, day=pw.DAY.replace(day=12)), run_id=None)
    approved = items.create_community_post(conn, pw.planned(conn, group_id, day=pw.DAY.replace(day=13)), run_id=None)
    pw.decide(conn, approved.approval)
    other_group = pw.community_item(conn, day=pw.DAY.replace(day=12))

    assert pw.invoke("publish", "done", request.id, "--outcome", "pages-not-allowed").exit_code == 0

    for made in (waiting, approved):
        record = approvals.get(conn, made.approval.id)
        assert record.status == "superseded", record
        assert pw.item_row(conn, made.item.id)["state"] == "withdrawn"
        assert approvals.kinds()["community-post"].kind.superseded_note(conn, made.item.subject) == (
            "only personal profiles can join or post in the group")
    assert approvals.get(conn, other_group[1].id).status == "pending"
    assert pw.item_row(conn, other_group[0].id)["state"] == "ready"
