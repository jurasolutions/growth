"""Joins as the Jura Page through the whole publish job, with the fake `claude` binary (seam S10;
datasets D10 and T; ticket BP-06).

`runner.run("publish")` in process; the fake plays Chrome calls and real `jura-growth publish …`
subprocesses. Rows traced: AC-P4.1, AC-P4.2, AC-P4.3 (the join screen) and AC-P11.1 (the Page as
the joining identity) end to end, and AC-P5.1 line 4 through S10.
"""

from __future__ import annotations

import json

import pytest

import publish_fake
import publish_transcripts as t
import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, db, pause, runner
from jura_growth.agents.community import groups as community_groups
from jura_growth.agents.publish import items
from test_publish_run import alerts, browser, chrome, claim

JOIN_PAGE = "Join group\nJoining as Jura Solutions"



# --- typed reads: each asserts the row is there (pyright; code review 06, S5) ---------------------------


def record_of(conn, approval_id: str) -> approvals.Approval:
    found = approvals.get(conn, approval_id)
    assert found is not None, approval_id
    return found


def item_of(conn, number: int | None) -> items.Item:
    assert number is not None
    found = items.get(conn, number)
    assert found is not None, number
    return found


def group_of(conn, group_id: int) -> dict:
    found = community_groups.get(conn, group_id)
    assert found is not None, group_id
    return found


def row_of(conn, number: int) -> dict:
    found = pw.item_row(conn, number)
    assert found is not None, number
    return found

@pytest.fixture
def fake(tmp_path, monkeypatch):
    found = publish_fake.install(tmp_path, monkeypatch)
    found.community(lambda data: data.update(browser=True))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)
    return found


@pytest.fixture
def approved_join(conn, fake, monkeypatch):
    join, request = pw.join_item(conn)
    assert pw.decide(conn, request, monkeypatch=monkeypatch).answer == "recorded"
    return join, request


def group_url(join: items.Item) -> str:
    return join.content["target_url"]


def at_group(join, *steps) -> list[dict]:
    """Open a tab at the group and read the join screen, then `steps` on that page."""
    url = group_url(join)
    return browser(t.created(), t.opened(url), t.page("get_page_text", {}, JOIN_PAGE, url=url),
                   *[{**step, "result": step["result"].replace(t.PAGE, url)} for step in steps])


def escape(join) -> dict:
    return t.page("computer", {"action": "key", "text": "Escape"}, "Pressed Escape.", url=group_url(join))


def click(ref: str, text: str = "Clicked.") -> dict:
    return t.page("computer", {"action": "left_click", "ref": ref}, text)


def run():
    return runner.run("publish", ignore_schedule=True)


def done(*words: str) -> dict:
    return {"cli": ["publish", "done", "{A}", *words]}


def item_row(conn, found) -> dict:
    return row_of(conn, found.id)


# --- AC-P4.1 a group with no questions -------------------------------------------------------------------


def test_an_approved_join_with_no_questions_is_requested_on_its_single_approval(conn, fake, approved_join, discord_double):
    join, request = approved_join
    fake.scenario([*claim(), *at_group(join, click("ref_7", "Clicked Join group.")),
                   done("--outcome", "requested", "--url", group_url(join)), chrome(t.closed())],
                  "OK: join requested for {A}")

    outcome = run()

    assert outcome.status == "ok", outcome
    handed = json.loads(fake.cli[0]["output"])
    assert handed["step"] == "join the group" and handed["approval"] == request.id
    row = item_row(conn, join)
    assert row["state"] == "done" and row["outcome"] == "requested"
    assert group_of(conn, join.ref_id)["join_status"] == "requested"
    assert db.scalar(conn, "SELECT count(*) FROM approvals") == 1  # no second request
    assert alerts(discord_double) == [] and not pause.is_paused(conn, "publish")
    [update] = discord_double.contents("community")  # a group item's run updates go to #community (§5.9)
    assert discord_double.contents("social-drafts") == []
    assert request.id in update and "join requested" in update and "1 post" not in update


def test_a_broken_channel_hook_still_posts_the_update_to_the_default_channel(
        conn, fake, approved_join, monkeypatch, discord_double):
    from jura_growth.agents import publish

    def broken(conn, run):
        raise RuntimeError("no channel")

    monkeypatch.setattr(publish, "run_update_channel", broken)
    join, request = approved_join
    fake.scenario([*claim(), *at_group(join, click("ref_7", "Clicked Join group.")),
                   done("--outcome", "requested"), chrome(t.closed())], "OK")

    run()

    [update] = discord_double.contents("social-drafts")
    assert request.id in update
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'run.after_run_error'") == 1


# --- AC-P4.2 a group with membership questions ---------------------------------------------------------------


def questions_run(join) -> list[dict]:
    return [
        *claim(),
        *at_group(join, click("ref_7", "Clicked Join group."),
                  t.page("get_page_text", {}, "Answer membership questions\nWhy do you want to join?")),
        chrome(escape(join)),  # the form closed, nothing submitted
        {"write": "q.json", "text": json.dumps(pw.QUESTIONS)},
        done("--outcome", "questions", "--file", "{WORK}/q.json"),
        chrome(t.closed()),
    ]


def answers_run(join, answers: list[str], *, url: str | None = None, outcome: str = "requested") -> list[dict]:
    """The answers typed and submitted on the group's own page, or on `url` (code review 06, R1)."""
    where = url or group_url(join)
    steps = [*claim(), *at_group(join, click("ref_7", "Clicked Join group."))]
    for number, answer in enumerate(answers):
        steps += [chrome(t.page("computer", {"action": "left_click", "ref": f"ref_{20 + number}"}, "Clicked.", url=where)),
                  chrome(t.page("computer", {"action": "type", "text": answer}, "Typed.", url=where))]
    steps += [chrome(t.page("computer", {"action": "left_click", "ref": "ref_40"}, "Clicked Submit.", url=where)),
              done("--outcome", outcome), chrome(t.closed())]
    return steps


def test_questions_submit_nothing_and_a_later_run_submits_exactly_the_approved_answers(
        conn, fake, approved_join, monkeypatch, discord_double):
    join, request = approved_join
    fake.scenario(questions_run(join), "OK: {A} asks membership questions")

    first = run()

    assert first.status == "ok", first
    assert item_row(conn, join)["outcome"] == "questions"
    assert group_of(conn, join.ref_id)["join_status"] is None
    assert alerts(discord_double) == [] and not pause.is_paused(conn, "publish")
    [second] = approvals.pending(conn)
    answers = items.of(conn, second.subject)
    assert answers is not None
    assert second.kind == "group-join" and answers.kind == items.ANSWERS_ITEM and answers.parent_item == join.id
    [update] = discord_double.contents("community")
    assert f"Facebook group {join.ref_id} · membership questions" in update and second.id in update
    assert pw.QUESTIONS[0]["question"] not in update  # never the group's own words
    cards.sweep_safely(conn)  # the run's own command had Discord off; the card goes out on the next sweep
    assert any(second.id in card and pw.QUESTIONS[0]["answer"] in card for card in discord_double.contents("approvals"))

    fake.scenario([*claim(), {"cli": ["publish", "stopped", "{A}", "--reason", "unidentified"]}])
    pw.at(monkeypatch, "2026-11-10T10:40:00+08:00")
    run()
    assert not fake.started  # nothing approved is due: the answers wait for Ting Yu

    assert pw.decide(conn, second).answer == "recorded"
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    fake.scenario(answers_run(join, [pair["answer"] for pair in pw.QUESTIONS]), "OK: answers submitted for {A}")

    later = run()

    assert later.status == "ok", later
    assert json.loads(fake.cli[0]["output"])["answers"] == pw.QUESTIONS
    assert item_row(conn, answers)["outcome"] == "requested"
    assert group_of(conn, join.ref_id)["join_status"] == "requested"
    assert record_of(conn, request.id).used_at and record_of(conn, second.id).used_at
    assert not pause.is_paused(conn, "publish")


def test_typing_at_the_questions_before_the_answers_are_approved_fails_the_run(conn, fake, approved_join, discord_double):
    join, _ = approved_join
    steps = questions_run(join)
    typing = t.page("computer", {"action": "type", "text": pw.QUESTIONS[0]["answer"]}, "Typed.", url=group_url(join))
    steps.insert(steps.index(chrome(escape(join))), chrome(typing))
    fake.scenario(steps, "OK: {A} asks membership questions")

    outcome = run()

    assert outcome.status == "failed"
    assert pause.is_paused(conn, "publish")


def test_answers_other_than_the_approved_ones_fail_the_run(conn, fake, approved_join, monkeypatch):
    join, _ = approved_join
    fake.scenario(questions_run(join), "OK")
    run()
    [second] = approvals.pending(conn)
    pw.decide(conn, second)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    fake.scenario(answers_run(join, ["We automate admin.", "Yes."]), "OK: answers submitted for {A}")

    outcome = run()

    assert outcome.status == "failed" and pause.is_paused(conn, "publish")


# --- code review 06, B1: a group item acts only in its own group -------------------------------------------


def test_a_join_made_in_another_group_fails_the_run_and_pauses(conn, fake, approved_join, discord_double):
    """R5: the run claimed the join for one group, then joined another and recorded the first."""
    join, _ = approved_join
    other = "https://www.facebook.com/groups/some-other-group"
    fake.scenario([*claim(), *browser(t.created(), t.opened(other), t.page("get_page_text", {}, JOIN_PAGE, url=other),
                                      t.page("computer", {"action": "left_click", "ref": "ref_7"}, "Clicked Join group.",
                                             url=other)),
                   done("--outcome", "requested"), chrome(t.closed())], "OK: join requested for {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert pause.is_paused(conn, "publish")
    assert "outside the claimed item's own page" in outcome.error and "some-other-group" not in outcome.error


def test_answers_posted_on_the_page_timeline_fail_the_run_and_pause(conn, fake, approved_join, monkeypatch):
    """R1: approved answers typed into the Jura Page's own composer and posted there."""
    join, _ = approved_join
    fake.scenario(questions_run(join), "OK")
    run()
    [second] = approvals.pending(conn)
    pw.decide(conn, second)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    fake.scenario(answers_run(join, [pair["answer"] for pair in pw.QUESTIONS], url=t.PAGE, outcome="member"), "OK")

    outcome = run()

    assert outcome.status == "failed" and pause.is_paused(conn, "publish")
    assert "outside the claimed item's own page" in outcome.error


def test_a_join_outcome_url_must_be_the_items_own_group(conn, fake, approved_join):
    join, _ = approved_join
    fake.scenario([*claim(), *at_group(join, click("ref_7", "Clicked Join group.")),
                   done("--outcome", "requested", "--url", "https://www.facebook.com/groups/some-other-group"),
                   done("--outcome", "requested", "--url", group_url(join) + "/?ref=share"), chrome(t.closed())], "OK")

    run()

    assert [c["exit"] for c in fake.cli[1:]] == [1, 0]
    assert "isn't the claimed item's own group" in fake.cli[1]["output"]


def test_the_audit_takes_its_hosts_from_the_claimed_item_never_every_enabled_platform(
        conn, fake, approved_join, monkeypatch):
    """Code review 06, S1 (and 04's B1): with another platform also enabled, a group item's tab on
    that platform's host fails. Hosts from the union of enabled platforms would let it pass."""
    fake.social(lambda data: data["platforms"]["instagram"].update(publish_mode="browser", page_url=pw.INSTAGRAM_URL))
    join, _ = approved_join
    elsewhere = "https://www.instagram.com/jura-test-page"
    fake.scenario([*claim(), *at_group(join, click("ref_7", "Clicked Join group.")),
                   chrome(t.page("get_page_text", {}, "Instagram", url=elsewhere)),
                   done("--outcome", "requested"), chrome(t.closed())], "OK")

    outcome = run()

    assert outcome.status == "failed" and pause.is_paused(conn, "publish")
    assert "www.instagram.com isn't one of the publish hosts" in outcome.error


# --- AC-P4.3 the join screen offers no way to act as the Page --------------------------------------------------


def test_a_join_screen_for_personal_profiles_only_skips_the_group_without_alert_or_pause(
        conn, fake, approved_join, discord_double):
    join, _ = approved_join
    url = group_url(join)
    fake.scenario([*claim(), *browser(t.created(), t.opened(url),
                                      t.page("get_page_text", {}, "Join group\nOnly people can join this group", url=url)),
                   done("--outcome", "pages-not-allowed"), chrome(t.closed())], "OK: {A} takes only personal profiles")

    outcome = run()

    assert outcome.status == "ok", outcome
    group = group_of(conn, join.ref_id)
    assert group["pages_allowed"] == "no" and group["fit"] == "skip"
    assert alerts(discord_double) == [] and not pause.is_paused(conn, "publish")
    assert items.create_join(conn, join.ref_id, run_id=None).item is None


# --- AC-P11.1 the Page as the joining identity ------------------------------------------------------------------


def test_another_joining_identity_stops_the_run_before_anything_is_submitted(conn, fake, approved_join, discord_double):
    join, request = approved_join
    url = group_url(join)
    fake.scenario([*claim(), *browser(t.created(), t.opened(url),
                                      t.page("get_page_text", {}, "Join group\nJoining as Somebody Else", url=url)),
                   {"cli": ["publish", "stopped", "{A}", "--reason", "wrong-identity"]}, chrome(t.closed())],
                  "FAIL: {A} wrong posting identity")

    outcome = run()

    assert outcome.status == "failed"
    row = item_row(conn, join)
    assert row["state"] == "stopped" and row["stop_reason"] == "wrong-identity"
    assert pause.is_paused(conn, "publish")
    assert group_of(conn, join.ref_id)["pages_allowed"] == "unknown"  # a stop, not pages-not-allowed
    [alert] = alerts(discord_double)
    assert request.id in alert and "expected posting identity" in alert


# --- AC-P5.1 line 4 through S10 -------------------------------------------------------------------------------


def test_a_fourth_join_in_the_iso_week_never_starts_a_run(conn, fake, approved_join):
    join, request = approved_join
    for day in ("2026-11-09", "2026-11-10"):
        conn.execute(
            "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, "
            "state, outcome, created_at, claimed_at) VALUES ('P-j', 'community_join', 'facebook', ?, 'u', 'p', '{}', ?, "
            "'done', 'requested', ?, ?)", (str(pw.not_joined(conn)), day, f"{day}T08:00:00+08:00", f"{day}T09:00:00+08:00"))
    conn.execute(
        "INSERT INTO publish_items (label, kind, platform, ref, target_url, posting_identity, content_json, day, state, "
        "outcome, created_at, claimed_at) VALUES ('P-k', 'community_join', 'facebook', ?, 'u', 'p', '{}', '2026-11-09', "
        "'done', 'requested', '2026-11-09T08:00:00+08:00', '2026-11-10T09:00:00+08:00')", (str(pw.not_joined(conn)),))
    fake.scenario([*claim()])

    run()

    assert not fake.started
    record = record_of(conn, request.id)
    assert record.status == "approved" and record.used_at is None
