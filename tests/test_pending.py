"""`/growth pending`: growth's unfinished work, by who holds the next step (growth-help-pending ticket 01).

Seam S8, as in `test_remote_apps.py`: Dispatch's call through click's `CliRunner`, with the SSH
origin passed in process. The world is `test_app_releases.py`'s: a private `prd/` with the template,
the landing-page repository at `paths.site_repo()`, the clock at Tuesday 10 November 10:02 and Ting
Yu as the control user. A plug-in's `pending(conn)` hook gets the read model's read-only connection.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import types
from pathlib import Path

import pytest
from click.testing import CliRunner

import approval_world as aw
import publish_world as pw
import mission_world as mw
import site_repo
from sweep import d2_secrets  # noqa: F401 - the fixture
from test_app_releases import BRANCH, PREVIEW, PROJECT, TASK, built, handed_off, pages_project, release_requests
from jura_growth import agents, approval_settings, approvals, config, db, headless, locks, mission, paths, remote as remote_mod, timeutil
from jura_growth.agents.apps import backlog, releases
from jura_growth.cli import cli
from jura_growth.origin import Origin

REAL_PRD = paths.JURA_ROOT / "prd"


def remote(words, *, as_json=True, ref=None):
    argv = ["remote", "--actor", aw.CONTROL]
    if ref:
        argv += ["--ref", ref]
    if as_json:
        argv.append("--json")
    return CliRunner().invoke(cli, [*argv, "--", *words], obj={"origin": Origin.ssh()})


def text() -> str:
    """What Dispatch would post."""
    result = remote(["pending"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["exit_code"] == 0 and body["answer"] == "recorded"
    return body["text"]


def section(answer: str, heading: str) -> str:
    """The lines under one heading, up to the next."""
    assert f"**{heading}**" in answer, answer
    return answer.split(f"**{heading}**", 1)[1].split("\n\n", 1)[0]


YOU, GROWTH = "Waiting for you", "Growth is on it"


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    prd = tmp_path / "prd"
    (prd / "templates").mkdir(parents=True)
    (prd / "pending" / "apps").mkdir(parents=True)
    shutil.copy(REAL_PRD / "templates" / "prd-app-template.md", prd / "templates")
    monkeypatch.setenv("JURA_PRD_DIR", str(prd))
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", aw.CONTROL_ID)
    aw.at(monkeypatch, aw.NOW)
    config.reset_caches()
    pages_project(monkeypatch, PROJECT)
    site_repo.make()
    return prd


def tonight(conn):
    """What Ting Yu had on 2026-10-31: APP-005 built, A-0004 approved and unclaimed."""
    mw.approval(conn, 2, "outreach-email", status="skipped", decided_at="2026-11-09T09:30:00+08:00",
                decide_by="2026-11-10T16:30:00+08:00")
    app_id, _ = handed_off(conn, 5)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    assert aw.approve(conn, request, args={}).answer == "recorded"
    return app_id, sha, aw.get(conn, request.id)


# --- AC2: tonight's world ---------------------------------------------------------------------------


def test_tonights_world_says_what_to_send_under_waiting_for_you(conn):
    app_id, _, request = tonight(conn)
    assert (app_id, request.id) == ("APP-005", "A-0004")
    waiting = section(text(), YOU)
    assert "APP-005" in waiting and "A-0004" in waiting
    assert "`/growth apps release-plan APP-005`" in waiting
    assert "Tue 24 Nov" in waiting  # A-0004's use-by: 14 days after the request


# --- AC3: each app state --------------------------------------------------------------------------


def built_waiting(conn, number: int = 5):
    """Built and reported, its `app-release` request still waiting for a decision."""
    app_id, _ = handed_off(conn, number)
    sha = site_repo.branch(BRANCH)
    assert built(app_id, sha).exit_code == 0
    [request] = release_requests(conn)
    return app_id, sha, request


def lines_about(answer: str, word: str) -> list[str]:
    return [line for line in answer.splitlines() if word in line]


def test_a_build_handed_to_dispatch_is_on_growth_with_its_approval_and_how_long_ago(conn, monkeypatch):
    switch_dispatch(monkeypatch, on=True)
    app_id, approval = handed_off(conn, 5)
    aw.at(monkeypatch, aw.later(aw.NOW, hours=3))
    answer = text()
    [line] = lines_about(section(answer, GROWTH), app_id)
    assert approval.id in line and "3 hours ago" in line and "Dispatch" in line
    assert app_id not in section(answer, YOU)


def test_a_build_to_do_by_hand_waits_for_you_when_dispatch_builds_is_off(conn, monkeypatch):
    switch_dispatch(monkeypatch, on=False)
    app_id, approval = handed_off(conn, 5)
    answer = text()
    [line] = lines_about(section(answer, YOU), app_id)
    assert approval.id in line and "by hand" in line and "Build it:" in line
    assert app_id not in section(answer, GROWTH)


def test_a_release_request_still_waiting_is_listed_once_in_the_approvals_lines(conn):
    app_id, _, request = built_waiting(conn)
    answer = text()
    [line] = lines_about(answer, app_id)
    assert line.startswith(f"- {request.id} · {app_id} ") and "decide by" in line
    assert line in section(answer, YOU)
    assert "release-plan" not in answer and answer.count(request.id) == 1


def test_an_approved_release_says_to_send_release_plan(conn):
    app_id, _, request = tonight(conn)
    answer = text()
    [line] = lines_about(answer, app_id)
    assert request.id in line and f"`/growth apps release-plan {app_id}`" in line and "Tue 24 Nov, 10:02 SGT" in line
    assert app_id not in section(answer, GROWTH)


def test_a_claimed_release_says_to_run_the_merge_then_send_released(conn):
    app_id, sha, request = tonight(conn)
    assert CliRunner().invoke(cli, ["apps", "release-plan", app_id]).exit_code == 0
    [line] = lines_about(text(), app_id)
    assert sha[:7] in line and request.id in line and "Run the merge" in line
    assert f"`/growth apps released {app_id} --task {TASK}`" in line


def test_a_claimed_release_main_already_holds_says_only_to_send_released(conn):
    app_id, sha, _ = tonight(conn)
    assert CliRunner().invoke(cli, ["apps", "release-plan", app_id]).exit_code == 0
    site_repo.merge(sha)
    [line] = lines_about(text(), app_id)
    assert f"`/growth apps released {app_id} --task {TASK}`" in line and "Run the merge" not in line


def test_when_git_cant_tell_it_says_to_run_the_merge_and_claims_nothing_about_main(conn, monkeypatch):
    """The usual case before the merge: the task branch's commit hasn't been fetched here."""
    app_id, sha, _ = tonight(conn)
    assert CliRunner().invoke(cli, ["apps", "release-plan", app_id]).exit_code == 0
    monkeypatch.setattr(releases, "on_main", lambda sha: None)
    [line] = lines_about(text(), app_id)
    assert "Run the merge" in line and sha[:7] in line and "doesn't hold" not in line


def test_a_skipped_release_stays_on_its_preview_and_says_so(conn):
    app_id, sha, request = built_waiting(conn)
    assert aw.skip(conn, request).answer == "recorded"
    [line] = lines_about(section(text(), YOU), app_id)
    assert_on_preview(line, app_id, sha, request, "skipped")


@pytest.mark.parametrize("written", [True, False], ids=["the lapse is written", "by the clock alone"])
def test_an_expired_release_stays_on_its_preview_and_says_so(conn, monkeypatch, written):
    app_id, sha, request = built_waiting(conn)
    aw.at(monkeypatch, request.decide_by)
    if written:
        approvals.expire_due(conn, timeutil.parse(request.decide_by))
    [line] = lines_about(section(text(), YOU), app_id)
    assert_on_preview(line, app_id, sha, request, "expired unanswered")
    assert "decide by" not in line


@pytest.mark.parametrize("written", [True, False], ids=["the lapse is written", "by the clock alone"])
def test_a_lapsed_approval_stays_on_its_preview_and_says_so(conn, monkeypatch, written):
    app_id, sha, request = tonight(conn)
    aw.at(monkeypatch, request.use_by)
    if written:
        approvals.expire_due(conn, timeutil.parse(request.use_by))
    [line] = lines_about(section(text(), YOU), app_id)
    assert_on_preview(line, app_id, sha, request, "approved, but its merge was never printed")
    assert "release-plan" not in line


def test_a_released_app_isnt_listed(conn):
    app_id, sha, _ = tonight(conn)
    assert CliRunner().invoke(cli, ["apps", "release-plan", app_id]).exit_code == 0
    site_repo.merge(sha)
    assert CliRunner().invoke(cli, ["apps", "released", app_id, "--task", TASK]).exit_code == 0
    assert app_id not in text()


def test_pending_and_the_one_pager_read_the_same_states(conn, monkeypatch):
    """One classification: an app is in the one-pager's plug-in lines exactly when `pending` holds it."""
    app_id, _, request = built_waiting(conn)
    assert one_pager_says(app_id, aw.NOW) == [] and "release-plan" not in text()
    aw.at(monkeypatch, request.decide_by)
    assert one_pager_says(app_id, request.decide_by) and "stays on its preview" in text()


def skipped_build(conn, number: int) -> str:
    app_id, _ = handed_off(conn, number)
    assert built(app_id, site_repo.branch(f"{BRANCH}-{number}"), branch=f"{BRANCH}-{number}").exit_code == 0
    assert aw.skip(conn, release_requests(conn)[-1]).answer == "recorded"
    return app_id


def approved_build(conn, number: int) -> str:
    app_id, _ = handed_off(conn, number)
    assert built(app_id, site_repo.branch(f"{BRANCH}-{number}"), branch=f"{BRANCH}-{number}").exit_code == 0
    assert aw.approve(conn, release_requests(conn)[-1], args={}).answer == "recorded"
    return app_id


@pytest.mark.parametrize("claimed", [False, True], ids=["approved", "claimed"])
def test_six_skipped_builds_dont_push_a_release_out_of_the_answer(conn, claimed):
    """Old skips stay `built` for good, and each line runs long: the release that can still go comes first."""
    for number in range(10, 16):
        skipped_build(conn, number)
    app_id = approved_build(conn, 20)
    if claimed:
        assert CliRunner().invoke(cli, ["apps", "release-plan", app_id]).exit_code == 0
    answer = text()
    assert "(cut" not in answer and len(answer) <= remote_mod.TEXT_LIMIT
    first = section(answer, YOU).strip().splitlines()[0]
    assert app_id in first and ("`/growth apps released" if claimed else "`/growth apps release-plan") in first


def test_preview_lines_show_the_newest_three_then_how_many_more(conn):
    made = [skipped_build(conn, number) for number in range(10, 16)]
    lines = section(text(), YOU).strip().splitlines()
    assert [next(app for app in made if app in line) for line in lines[:3]] == ["APP-015", "APP-014", "APP-013"]
    assert lines[3:] == ["- and 3 more stay on their previews."]


def test_three_preview_lines_show_no_more_line(conn):
    for number in range(10, 13):
        skipped_build(conn, number)
    assert "more stay" not in text()


def test_a_preview_line_comes_after_the_other_next_steps(conn):
    skipped_build(conn, 10)
    label, _ = item(conn, 1, state="unknown", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    lines = section(text(), YOU).strip().splitlines()
    assert label in lines[0] and "APP-010" in lines[1]


@pytest.mark.parametrize("how", ["superseded", "none on record"])
def test_a_built_app_with_no_live_request_gets_its_own_line_and_the_one_pager_stays_as_it_was(conn, how):
    app_id, sha, request = built_waiting(conn)
    if how == "superseded":
        conn.execute("UPDATE approvals SET status = 'superseded', closed_at = ?, close_reason = 'x' WHERE id = ?", (aw.NOW, request.number))
    else:
        conn.execute("DELETE FROM approvals WHERE id = ?", (request.number,))
    answer = text()
    assert not answer.startswith("Nothing pending")
    [line] = lines_about(section(answer, YOU), app_id)
    assert "has no release request on record" in line
    assert f"`/growth apps built {app_id} --task {TASK} --branch {BRANCH} --sha {sha} --preview {PREVIEW}`" in line
    assert one_pager_says(app_id, aw.NOW) == []


def assert_on_preview(line, app_id, sha, request, why):
    assert f"{request.id} {why}" in line and PREVIEW in line
    assert f"`/growth apps built {app_id} --task {TASK} --branch {BRANCH} --sha {sha} --preview {PREVIEW}`" in line


def one_pager_says(app_id: str, now: str) -> list[str]:
    return [line for line in mission.read(mw.source(now=now)).plugin_lines if app_id in line and "Build handoff" not in line]


def switch_dispatch(monkeypatch, *, on: bool) -> None:
    monkeypatch.setattr(approval_settings, "switch", lambda name: on if name == "dispatch_builds" else False)


# --- AC4: publish items ---------------------------------------------------------------------------


def item(conn, number: int, *, state: str = "ready", kind: str = "social_post", platform: str = "facebook", day: str = "2026-11-10",
         run_id: int | None = None, request_status: str | None = "pending", used: bool = False) -> tuple[str, str]:
    """A publish item by raw SQL, and its request. Returns (its P-nnnn label, its A-nnnn)."""
    label = f"P-{number:04d}"
    conn.execute(
        "INSERT INTO publish_items (id, label, kind, platform, ref, target_url, posting_identity, content_json, day, state, run_id, created_at)"
        " VALUES (?, ?, ?, ?, '1', 'https://www.facebook.com/x', 'the Page', '{}', ?, ?, ?, ?)",
        (number, label, kind, platform, day, state, run_id, aw.NOW),
    )
    approval = 500 + number
    decided = (aw.NOW, aw.CONTROL, "ssh") if request_status in ("approved", "skipped") else (None, None, None)
    conn.execute(
        "INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by, used_at,"
        " decided_at, decided_by, decided_origin) VALUES (?, ?, ?, ?, ?, 'a test asked', ?, ?, ?, ?, ?, ?)",
        (approval, "social-post", f"publish_item:{number}", f"{approval:064x}", request_status, aw.NOW,
         aw.later(aw.NOW, hours=5), aw.NOW if used else None, *decided),
    )
    return label, approvals.format_id(approval)


def run_row(conn, status: str) -> int:
    return conn.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('publish', 'publish', ?, ?)", (aw.NOW, status)).lastrowid


def test_a_publish_item_whose_outcome_is_unknown_waits_for_you_with_both_commands(conn):
    label, approval = item(conn, 1, state="unknown", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    answer = text()
    [line] = lines_about(section(answer, YOU), label)
    assert "facebook" in line and "2026-11-10" in line and "unknown" in line
    assert f"`/growth publish resolve {approval} posted --url <url>`" in line
    assert f"`/growth publish resolve {approval} not-posted`" in line


def test_a_join_whose_outcome_is_unknown_can_only_be_settled_as_not_posted(conn):
    label, approval = item(conn, 1, state="unknown", kind="community_join", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    [line] = lines_about(section(text(), YOU), label)
    assert f"`/growth publish resolve {approval} not-posted`" in line and "--url" not in line


@pytest.mark.parametrize("status", ["pending", "approved"])
def test_a_ready_item_is_on_growth_with_its_label_platform_and_day(conn, status):
    label, _ = item(conn, 1, platform="instagram", day="2026-11-12", request_status=status)
    [line] = lines_about(section(text(), GROWTH), label)
    assert line == f"- {label}, instagram, 2026-11-12: ready (request {status})"


def test_an_item_a_running_run_has_claimed_is_on_growth(conn):
    label, _ = item(conn, 1, state="claimed", run_id=run_row(conn, "running"), request_status="approved", used=True)
    [line] = lines_about(section(text(), GROWTH), label)
    assert line == f"- {label}, facebook, 2026-11-10: claimed"


def test_a_claim_no_run_will_close_waits_for_you_with_resolve(conn):
    label, approval = item(conn, 1, state="claimed", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    answer = text()
    [line] = lines_about(section(answer, YOU), label)
    assert f"`/growth publish resolve {approval} not-posted`" in line
    assert label not in section(answer, GROWTH)


def test_done_stopped_and_withdrawn_items_arent_listed(conn):
    for number, state in enumerate(("done", "stopped", "withdrawn"), start=1):
        item(conn, number, state=state, request_status="skipped")
    assert text().startswith("Nothing pending")


def test_seven_open_items_show_five_then_how_many_more(conn):
    labels = [item(conn, number)[0] for number in range(1, 8)]
    growth = section(text(), GROWTH)
    assert [label for label in labels if label in growth] == labels[:5]
    assert "- and 2 more: send `/growth publish queue`" in growth


# --- AC4: the counts ------------------------------------------------------------------------------


def post(conn, number: int, *, day: str = "2026-11-10", platform: str = "facebook", status: str = "draft") -> None:
    conn.execute("INSERT INTO social_posts (id, date, theme, platform, text, status, created_at) VALUES (?, ?, 't', ?, 'x', ?, ?)",
                 (number, day, platform, status, aw.NOW))


def planned_post(conn, number: int, *, day: str | None = "2026-11-10", kind: str = "post", status: str = "planned") -> None:
    conn.execute("INSERT INTO community_posts (id, week, planned_day, kind, text, status, created_at) VALUES (?, '2026-W46', ?, ?, 'x', ?, ?)",
                 (number, day, kind, status, aw.NOW))


def email(conn, number: int, *, status: str = "queued") -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("INSERT INTO outreach_messages (id, lead_id, kind, subject, draft_body, body_text, body_html, send_after, queued_at, status)"
                 " VALUES (?, ?, 'first', 's', 'd', 't', 'h', '2026-11-10', ?, ?)", (number, number, aw.NOW, status))


def test_queued_emails_are_counted_on_growth(conn):
    for number in (1, 2):
        email(conn, number)
    email(conn, 3, status="sent")
    assert "- 2 outreach emails queued." in section(text(), GROWTH)


def test_one_queued_email_reads_in_the_singular(conn):
    email(conn, 1)
    assert "- 1 outreach email queued." in section(text(), GROWTH)


def test_social_drafts_for_today_onward_are_counted_on_growth(conn, monkeypatch):
    pw.social_config(monkeypatch, browser=())  # draft mode: a row with no request is his to post
    post(conn, 1)
    post(conn, 2, platform="instagram", day="2026-11-11")
    post(conn, 3, day="2026-11-09")  # yesterday's, past
    post(conn, 4, day="2026-11-12", status="published")
    post(conn, 5, day="2026-11-12", platform="myspace")  # a platform that isn't switched on is never going out
    assert "- 2 social drafts for today onward." in section(text(), GROWTH)


def test_community_posts_planned_for_today_onward_are_counted_on_growth(conn):
    planned_post(conn, 1)
    planned_post(conn, 2, day="2026-11-14")
    planned_post(conn, 3, day="2026-11-09")
    planned_post(conn, 4, day="2026-11-14", status="posted")
    planned_post(conn, 5, day=None, kind="reply_idea")
    assert "- 2 community posts planned for today onward." in section(text(), GROWTH)


def test_no_count_shows_when_it_is_zero(conn):
    email(conn, 1, status="sent")
    post(conn, 1, status="skipped")
    planned_post(conn, 1, status="skipped")
    assert text().startswith("Nothing pending")


# --- AC4: the ideas line ----------------------------------------------------------------------------


def ideas_sent(*names: str) -> None:
    with backlog.locked():
        rows = backlog.load()
        for number, name in enumerate(names):
            rows.append({"name": name, "slug": name.lower().replace(" ", "-"), "does": name, "status": "idea", "source": "ting-yu",
                         "added": f"2026-10-{20 + number}"})
        backlog.save(rows)


def test_your_ideas_in_the_backlog_are_counted_with_the_next_ones_name(conn):
    ideas_sent("Petty cash log", "Site visit report")
    assert "- 2 of your ideas wait in the backlog for the app factory. The next is Petty cash log." in section(text(), GROWTH)


def test_one_idea_reads_in_the_singular(conn):
    ideas_sent("Petty cash log")
    assert "- 1 of your ideas waits in the backlog for the app factory. The next is Petty cash log." in section(text(), GROWTH)


def test_the_seed_backlog_has_no_ideas_of_yours(conn):
    assert "backlog" not in text()


SHAPES = {
    "an empty file": "",
    "apps isn't a list": "apps: oops\n",
    "a typo in the key, over a real idea": "app:\n  - name: Petty cash log\n    source: ting-yu\n    status: idea\n",
    "a top-level list of strings": "- just\n- strings\n",
    "a row that isn't a mapping": "apps:\n  - just a string\n  - name: Petty cash log\n    source: ting-yu\n",
    "a row with no name": "apps:\n  - source: ting-yu\n    status: idea\n",
}


@pytest.mark.parametrize("body", SHAPES.values(), ids=SHAPES.keys())
def test_a_backlog_of_the_wrong_shape_reads_as_unreadable_and_not_as_no_ideas(conn, body):
    paths.writable(backlog.path()).write_text(body, encoding="utf-8")
    assert_couldnt_read(text(), "The app backlog couldn't be read")


def test_a_backlog_with_an_empty_list_is_read_and_has_no_ideas(conn):
    paths.writable(backlog.path()).write_text("apps: []\n", encoding="utf-8")
    assert text().startswith("Nothing pending")


def test_the_writers_load_stays_as_lenient_as_it_was():
    paths.writable(backlog.path()).write_text("apps: oops\n", encoding="utf-8")
    assert backlog.load() == []


def test_a_backlog_that_cant_be_read_hides_nothing_else_and_says_so(conn):
    app_id, _, request = tonight(conn)
    paths.writable(backlog.path()).write_text("apps: [unclosed", encoding="utf-8")
    answer = text()
    assert "The app backlog couldn't be read" in answer
    assert "nothing pending" not in answer.lower()
    assert app_id in section(answer, YOU) and request.id in section(answer, YOU)


# --- approval requests, and their cap ---------------------------------------------------------------


def waiting_request(conn, number: int, *, hours: int) -> None:
    mw.approval(conn, number, "outreach-email", decide_by=aw.later(aw.NOW, hours=hours))


def test_requests_waiting_are_listed_soonest_to_lapse_first_with_a_title_and_decide_by(conn):
    waiting_request(conn, 11, hours=30)
    waiting_request(conn, 12, hours=2)
    lines = section(text(), YOU).strip().splitlines()
    assert lines[0] == "- A-0012 · a test asked · decide by Tue 10 Nov, 12:02 SGT"  # no message on record: the row's own words
    assert lines[1] == "- A-0011 · a test asked · decide by Wed 11 Nov, 16:02 SGT"


def test_a_request_past_its_decide_by_isnt_waiting_though_nothing_wrote_its_lapse(conn):
    waiting_request(conn, 11, hours=-1)
    assert "A-0011" not in text()


def test_seven_requests_show_the_five_soonest_then_how_many_more(conn):
    for number in range(1, 8):
        waiting_request(conn, number, hours=20 - number)
    answer = section(text(), YOU)
    assert [approvals.format_id(n) in answer for n in range(7, 0, -1)] == [True] * 5 + [False] * 2
    assert "- and 2 more: send `/growth approvals`" in answer


def test_pending_and_approvals_agree_on_what_is_waiting(conn):
    for number in range(1, 5):
        waiting_request(conn, number, hours=9 - number)
    waiting_request(conn, 5, hours=-1)
    listed = [line.split(" · ")[0] for line in json.loads(remote(["approvals"]).output)["text"].splitlines() if line.startswith("A-")]
    assert [line.split(" · ")[0].removeprefix("- ") for line in section(text(), YOU).strip().splitlines() if line.startswith("- A-")] == listed


DECIDE = "- Decide in #approvals, or send `/growth approve A-nnnn` or `/growth skip A-nnnn`."


def test_requests_say_how_to_decide_them_on_one_line_after_them(conn):
    waiting_request(conn, 11, hours=30)
    waiting_request(conn, 12, hours=2)
    lines = section(text(), YOU).strip().splitlines()
    assert [line.split(" · ")[0] for line in lines[:2]] == ["- A-0012", "- A-0011"]
    assert lines[2:] == [DECIDE]


def test_the_decide_line_follows_the_cap_line_and_comes_before_anything_else(conn):
    tonight(conn)
    for number in range(11, 18):
        waiting_request(conn, number, hours=number)
    lines = section(text(), YOU).strip().splitlines()
    assert lines[5] == "- and 2 more: send `/growth approvals`"
    assert lines[6] == DECIDE
    assert "APP-005" in lines[7]


@pytest.mark.parametrize("world_with", ["nothing", "an approved release", "a request past its decide-by"])
def test_no_requests_means_no_decide_line(conn, world_with):
    if world_with == "an approved release":
        tonight(conn)
    elif world_with == "a request past its decide-by":
        waiting_request(conn, 11, hours=-1)
    assert "Decide in" not in text()


def test_requests_that_cant_be_read_have_no_decide_line(conn):
    conn.execute("DROP TABLE approvals")
    assert "Decide in" not in text()


def test_the_decide_line_survives_a_cut(conn):
    for number in range(1, 8):
        waiting_request(conn, 100 + number, hours=number)
    for number in range(1, 41):
        item(conn, number, state="unknown", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    answer = text()
    assert len(answer) <= remote_mod.TEXT_LIMIT and re.search(r"\(cut: \d+ more lines?\)$", answer)
    assert answer.splitlines()[6:8] == ["- and 2 more: send `/growth approvals`", DECIDE]


def test_the_contract_says_what_pending_does(conn):
    row = next(line for line in (paths.REPO_ROOT / "docs" / "dispatch-contract.md").read_text(encoding="utf-8").splitlines()
               if line.startswith("| `pending` |"))
    assert "no backlog lock" in row and "takes no lock" not in row
    assert "`**Couldn't be read**`" in row and "JSONL mirror" in row


def test_five_requests_show_no_more_line(conn):
    for number in range(1, 6):
        waiting_request(conn, number, hours=number)
    assert "more:" not in text()


# --- AC5: nothing open, and what couldn't be read ----------------------------------------------------


def fake_plugin(monkeypatch, **hooks) -> None:
    real = agents.plugins()
    monkeypatch.setattr(agents, "plugins", lambda: (*real, types.SimpleNamespace(**hooks)))


def assert_couldnt_read(answer: str, *words: str) -> None:
    assert "nothing pending" not in answer.lower(), answer
    assert "**Couldn't be read**" in answer, answer
    for word in words:
        assert word in section(answer, "Couldn't be read"), answer


def test_nothing_open_answers_plainly(conn):
    assert text() == "Nothing pending. Nothing is waiting for you, and growth has nothing under way."


def test_a_missing_database_says_so_and_not_nothing_pending():
    assert not paths.db_path().exists()
    result = CliRunner().invoke(cli, ["pending"])
    assert result.exit_code == 0
    assert_couldnt_read(result.output, "growth.db doesn't exist yet")


def test_a_missing_database_through_remote_says_so_too():
    assert_couldnt_read(text(), "growth.db doesn't exist yet")


def test_a_missing_approvals_table_says_so(conn):
    conn.execute("DROP TABLE approvals")
    assert_couldnt_read(text(), "Approval requests couldn't be read", "no such table: approvals")


@pytest.mark.parametrize("table, plugin", [("publish_items", "publish"), ("outreach_messages", "outreach"), ("social_posts", "social"),
                                           ("community_posts", "community"), ("app_builds", "app-factory")])
def test_a_missing_table_says_which_and_keeps_the_rest(conn, table, plugin):
    waiting_request(conn, 11, hours=2)
    conn.execute(f"DROP TABLE {table}")
    answer = text()
    assert_couldnt_read(answer, f"{plugin}: its pending work couldn't be read", f"no such table: {table}")
    assert "A-0011" in section(answer, YOU)


def test_a_builds_table_without_the_release_columns_says_so(conn):
    conn.execute("ALTER TABLE app_builds DROP COLUMN head_sha")
    assert_couldnt_read(text(), "app-factory: its pending work couldn't be read", "head_sha")


def test_a_plugin_that_raises_is_one_line_and_the_others_still_answer(conn, monkeypatch):
    def broken(read_only):
        raise RuntimeError("something private")

    email(conn, 1)
    fake_plugin(monkeypatch, NAME="builder", pending=broken)
    answer = text()
    assert_couldnt_read(answer, "builder: its pending work couldn't be read (RuntimeError)")
    assert "something private" not in answer
    assert "1 outreach email queued" in section(answer, GROWTH)


def test_a_plugin_that_doesnt_return_items_is_one_line(conn, monkeypatch):
    fake_plugin(monkeypatch, NAME="builder", pending=lambda read_only: ["a bare string"])
    assert_couldnt_read(text(), "builder: its pending work couldn't be read (TypeError)")


def test_a_plugin_that_failed_to_load_says_so(conn, monkeypatch):
    monkeypatch.setitem(agents.BROKEN, "scout", "ImportError: no module")
    assert_couldnt_read(text(), "scout: its plug-in didn't load")


def test_a_lock_in_a_hook_makes_the_whole_answer_say_so(conn, monkeypatch):
    def locked(read_only):
        raise sqlite3.OperationalError("database is locked")

    fake_plugin(monkeypatch, NAME="builder", pending=locked)
    answer = text()
    assert_couldnt_read(answer, "growth.db has an unfinished write", "`/growth status`")
    assert "builder" not in answer


def test_a_held_lock_on_the_database_says_so(conn, monkeypatch):
    monkeypatch.setattr(mission, "BUSY_TIMEOUT", 0)
    conn.execute("BEGIN EXCLUSIVE")
    try:
        result = CliRunner().invoke(cli, ["pending"])
    finally:
        conn.execute("ROLLBACK")
    assert result.exit_code == 0
    assert_couldnt_read(result.output, "growth.db has an unfinished write")


def test_a_file_that_isnt_a_database_says_so(conn):
    conn.close()
    paths.db_path().write_bytes(b"not a database, and long enough to be read as one" * 40)
    result = CliRunner().invoke(cli, ["pending"])
    assert result.exit_code == 0
    assert_couldnt_read(result.output, "growth.db couldn't be read", "`/growth status`")


def test_a_request_with_a_decide_by_that_doesnt_parse_says_so_and_keeps_the_rest(conn):
    mw.approval(conn, 11, "outreach-email", decide_by="not a time")
    email(conn, 1)
    answer = text()
    assert_couldnt_read(answer, "Approval requests couldn't be read (ValueError)")
    assert "1 outreach email queued" in section(answer, GROWTH)


@pytest.mark.parametrize("command", ["pending", "help"])
def test_neither_command_spends_dispatchs_window_waiting_on_a_lock(conn, monkeypatch, command):
    """Dispatch gives a command 60 seconds, and the masking and the audit line each open growth.db.
    At 30 seconds each, the answer that says growth.db is locked would never get back."""
    waits = []

    def connect(path=None, *, migrate_now=True, wait=None):
        waits.append(wait)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "connect", connect)
    result = remote([command])
    assert result.exit_code == 0, result.output
    assert len(waits) >= 2 and set(waits) == {db.SHORT_WAIT}, waits


def test_a_hot_journal_says_so_and_isnt_rolled_back(tmp_path):
    folders = mw.watched()
    mw.hot_journal(paths.db_path(), tmp_path / "d4")
    before = mw.stat_snapshot(*folders)
    result = CliRunner().invoke(cli, ["pending"])
    assert result.exit_code == 0
    assert_couldnt_read(result.output, "growth.db has an unfinished write")
    assert mw.stat_snapshot(*folders) == before


def test_a_hook_gets_a_connection_that_cant_write(conn, monkeypatch):
    def writes(read_only):
        read_only.execute("DELETE FROM approvals")
        return []

    waiting_request(conn, 11, hours=2)
    fake_plugin(monkeypatch, NAME="writer", pending=writes)
    answer = text()
    assert_couldnt_read(answer, "writer: its pending work couldn't be read")
    assert "A-0011" in section(answer, YOU)


# --- AC6: the live state isn't changed ------------------------------------------------------------


def rows_by_table(conn) -> dict[str, int]:
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}


def busy_world(conn, monkeypatch):
    switch_dispatch(monkeypatch, on=True)
    app_id, sha, request = tonight(conn)
    handed_off(conn, 6)
    waiting_request(conn, 21, hours=2)
    item(conn, 1, state="unknown", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    item(conn, 2, request_status="approved")
    email(conn, 1)
    post(conn, 1)
    planned_post(conn, 1)
    ideas_sent("Petty cash log")
    return app_id, sha, request


def test_pending_writes_nothing_at_all_on_its_own(conn, monkeypatch):
    busy_world(conn, monkeypatch)
    before, rows = mw.stat_snapshot(*mw.watched()), rows_by_table(conn)
    result = CliRunner().invoke(cli, ["pending"])
    assert result.exit_code == 0 and "APP-005" in result.output
    assert mw.stat_snapshot(*mw.watched()) == before
    assert rows_by_table(conn) == rows


def every_row(conn) -> dict[str, list[tuple]]:
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")] for table in tables}


def other_files(folders) -> dict[str, tuple]:
    """Every file but growth.db and the JSONL mirror, the two places its own event goes."""
    return {path: stat for path, stat in mw.stat_snapshot(*folders).items()
            if "growth.db" not in path and f"{os.sep}runs" not in path}


def test_through_remote_only_its_own_event_is_written(conn, monkeypatch):
    busy_world(conn, monkeypatch)
    folders = mw.watched()
    rows, files = every_row(conn), other_files(folders)
    assert "APP-005" in text()
    after = every_row(conn)
    assert after["events"][:-1] == rows["events"]  # an UPDATE anywhere would show here, not only a new row
    assert {table: found for table, found in after.items() if table != "events"} == {table: found for table, found in rows.items() if table != "events"}
    assert other_files(folders) == files
    assert conn.execute("SELECT kind FROM events ORDER BY id DESC LIMIT 1").fetchone()[0] == "remote.command"


# --- remote leaves a database that is missing or mid-write alone (code review 01) ---------------------


def test_a_second_send_on_a_missing_database_still_says_so_and_no_database_appears():
    assert_couldnt_read(text(), "growth.db doesn't exist yet")
    assert not paths.db_path().exists()
    assert_couldnt_read(text(), "growth.db doesn't exist yet")
    assert not paths.db_path().exists()
    assert [event["words"] for event in aw.mirrored("remote.command")] == [["pending"], ["pending"]]


def test_a_refused_pending_on_a_missing_database_leaves_it_missing_too():
    result = remote(["pending", "now"])
    assert result.exit_code == 2
    assert not paths.db_path().exists()
    assert aw.mirrored("remote.command")[-1]["words"] == ["pending", "now"]


def test_a_hot_journal_stays_in_place_through_remote(tmp_path):
    mw.watched()
    target = paths.db_path()
    mw.hot_journal(target, tmp_path / "d4")
    journal = Path(f"{target}-journal")
    before = (target.read_bytes(), journal.read_bytes())
    assert_couldnt_read(text(), "growth.db has an unfinished write")
    assert (target.read_bytes(), journal.read_bytes()) == before
    assert aw.mirrored("remote.command")[-1]["words"] == ["pending"]


def test_a_held_lock_through_remote_opens_nothing_read_write(conn, monkeypatch):
    monkeypatch.setattr(mission, "BUSY_TIMEOUT", 0)
    opened = []
    real = db.connect
    monkeypatch.setattr(db, "connect", lambda *args, **kwargs: opened.append(kwargs) or real(*args, **kwargs))
    conn.execute("BEGIN EXCLUSIVE")
    try:
        answer = text()
    finally:
        conn.execute("ROLLBACK")
    assert_couldnt_read(answer, "growth.db has an unfinished write")
    assert opened == []
    assert aw.mirrored("remote.command")[-1]["words"] == ["pending"]


def empty_file() -> None:
    paths.db_path().parent.mkdir(parents=True, exist_ok=True)
    paths.db_path().write_bytes(b"")


# QA 01, defect 02: a send mustn't turn "couldn't be read" into nothing to do.


def test_pending_on_an_empty_database_file_writes_nothing_to_it():
    empty_file()
    text()
    assert paths.db_path().stat().st_size == 0
    assert aw.mirrored("remote.command")[-1]["words"] == ["pending"]


def test_a_second_pending_on_an_empty_database_file_still_says_what_couldnt_be_read():
    empty_file()
    assert_couldnt_read(text(), "approvals")
    assert_couldnt_read(text(), "approvals")
    assert paths.db_path().stat().st_size == 0


def test_an_empty_database_file_is_one_line_and_not_one_for_each_table():
    empty_file()
    for answer in (text(), CliRunner().invoke(cli, ["pending"]).output.strip()):
        assert answer == ("**Couldn't be read**\n"
                          "- Pending work couldn't be read: growth.db is an empty file, with no approvals or anything else in it.")


def test_help_on_a_missing_database_leaves_it_missing():
    assert remote(["help"]).exit_code == 0
    assert not paths.db_path().exists()
    assert aw.mirrored("remote.command")[-1]["words"] == ["help"]


def test_pending_after_help_on_a_missing_database_still_says_so():
    assert remote(["help"]).exit_code == 0
    assert_couldnt_read(text(), "growth.db doesn't exist yet")


def test_help_on_an_empty_database_file_writes_nothing_to_it():
    empty_file()
    result = remote(["help"])
    assert result.exit_code == 0 and "/growth <command>" in result.output
    assert paths.db_path().stat().st_size == 0
    assert aw.mirrored("remote.command")[-1]["words"] == ["help"]


def test_help_leaves_a_hot_journal_in_place(tmp_path):
    mw.watched()
    target = paths.db_path()
    mw.hot_journal(target, tmp_path / "d4")
    journal = Path(f"{target}-journal")
    before = (target.read_bytes(), journal.read_bytes())
    assert remote(["help"]).exit_code == 0
    assert (target.read_bytes(), journal.read_bytes()) == before
    assert aw.mirrored("remote.command")[-1]["words"] == ["help"]


def test_a_refused_help_leaves_a_missing_database_missing_too():
    assert remote(["help", "me"]).exit_code == 2
    assert not paths.db_path().exists()


def test_help_on_a_healthy_database_still_writes_its_row(conn):
    assert remote(["help"]).exit_code == 0
    (event,) = aw.events(conn, "remote.command")
    assert event["words"] == ["help"]


OTHER_COMMANDS = sorted(set(remote_mod.ALLOWLIST) - {"help", "pending"})


@pytest.mark.parametrize("damage", [lambda: None, empty_file], ids=["missing", "empty"])
@pytest.mark.parametrize("name", OTHER_COMMANDS)
def test_only_pending_and_help_leave_the_database_alone(name, damage):
    damage()
    assert remote_mod._leave_database_alone(name.split()) is False


def test_a_command_that_doesnt_open_the_database_itself_still_gets_it_opened_for_its_event():
    """A refused command runs nothing, so only `remote` can have opened it: this goes red without the
    guard that limits the branch to `pending` and `help`, where `status`, which opens it anyway, can't."""
    assert remote(["run", "social"]).exit_code == 2
    assert paths.db_path().exists()
    connection = db.connect()
    try:
        (event,) = aw.events(connection, "remote.command")
    finally:
        connection.close()
    assert event["words"] == ["run", "social"]


def test_a_lapse_by_the_clock_writes_nothing(conn, monkeypatch):
    _, _, request = tonight(conn)
    aw.at(monkeypatch, request.use_by)
    assert "stays on its preview" in text()
    assert aw.get(conn, request.id).status == "approved"


def test_reading_the_backlog_takes_no_lock_and_waits_for_none(conn, monkeypatch):
    ideas_sent("Petty cash log")
    before = backlog.path().read_bytes()

    def refuse(*args, **kwargs):
        raise AssertionError("pending took a lock")

    with backlog.locked():  # another writer holds it: a reader that wanted it would wait 30 seconds, then fail
        monkeypatch.setattr(locks, "waiting", refuse)
        monkeypatch.setattr(locks, "held", refuse)
        result = CliRunner().invoke(cli, ["pending"])
    assert result.exit_code == 0 and "Petty cash log" in result.output
    assert backlog.path().read_bytes() == before


def test_reading_the_seed_backlog_doesnt_write_the_file(conn):
    assert not backlog.path().exists()
    assert CliRunner().invoke(cli, ["pending"]).exit_code == 0
    assert not backlog.path().exists()


def test_claimed_is_not_claimed_by_asking(conn):
    """The trap in tonight's world: `pending` names `release-plan`, and never runs it."""
    app_id, _, request = tonight(conn)
    assert f"apps release-plan {app_id}" in text()
    assert aw.get(conn, request.id).used_at is None


# --- AC7: the contract ------------------------------------------------------------------------------


def test_pending_answers_recorded_in_the_contract_shape_and_writes_one_event(conn):
    result = remote(["pending"], ref="m1:d1")
    body = json.loads(result.output)
    assert result.exit_code == 0
    assert set(body) == {"contract", "ok", "answer", "exit_code", "text"}
    assert body["contract"] == 1 and body["ok"] is True and body["answer"] == "recorded" and body["exit_code"] == 0
    (event,) = aw.events(conn, "remote.command")
    assert event["words"] == ["pending"] and event["ref"] == "m1:d1" and event["actor"] == aw.CONTROL


def test_what_couldnt_be_read_still_answers_exit_0_and_recorded(conn):
    conn.execute("DROP TABLE publish_items")
    body = json.loads(remote(["pending"]).output)
    assert body["exit_code"] == 0 and body["answer"] == "recorded" and "no such table" in body["text"]


def test_words_after_pending_are_refused(conn):
    result = remote(["pending", "now"])
    body = json.loads(result.output)
    assert result.exit_code == 2 and body["answer"] == "refused" and body["text"].startswith("refused:")


# --- AC8: scheduled runs can't send either command ----------------------------------------------------


JOBS = sorted(config.settings()["jobs"])


@pytest.mark.parametrize("command", ["help", "pending"])
@pytest.mark.parametrize("job", JOBS)
def test_no_job_may_use_either_command(job, command):
    assert not headless.may_use(job, command)
    assert command not in headless.permissions(job).commands


@pytest.mark.parametrize("command", ["help", "pending"])
@pytest.mark.parametrize("job", JOBS)
def test_a_run_is_refused_either_command_with_exit_2(monkeypatch, job, command):
    monkeypatch.setenv("JURA_GROWTH_JOB", job)
    result = CliRunner().invoke(cli, [command])
    assert result.exit_code == 2 and "refused:" in result.output
    assert "Waiting for you" not in result.output and "/growth <command>" not in result.output


@pytest.mark.parametrize("command", ["help", "pending"])
@pytest.mark.parametrize("job", [job for job in JOBS if config.settings()["jobs"][job]["kind"] == "claude"])
def test_claude_code_is_told_to_refuse_either_command_too(job, command):
    allowed, disallowed = headless.claude_rules(job)
    assert f"Bash(jura-growth {command})" in disallowed and f"Bash(jura-growth {command})" not in allowed
    assert "Bash(jura-growth --help)" in allowed  # the help flag stays open: it runs no command


# --- the cut: the urgent part survives -----------------------------------------------------------------


def test_a_long_list_is_cut_to_the_limit_and_the_urgent_part_survives(conn, monkeypatch):
    switch_dispatch(monkeypatch, on=True)
    app_id, _, request = tonight(conn)
    for number in range(1, 8):
        waiting_request(conn, 100 + number, hours=number)
    for number in range(1, 41):
        item(conn, number, state="unknown", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    handed_off(conn, 6)
    email(conn, 1)
    answer = text()
    assert len(answer) <= remote_mod.TEXT_LIMIT
    assert re.search(r"\(cut: \d+ more lines?\)$", answer)
    lines = answer.splitlines()
    assert lines[0] == "**Waiting for you**"
    assert [line.split(" · ")[0] for line in lines[1:6]] == [f"- A-{100 + n:04d}" for n in range(1, 6)]
    assert lines[6:8] == ["- and 2 more: send `/growth approvals`", DECIDE]
    assert app_id in lines[8] and request.id in lines[8] and "`/growth apps release-plan APP-005`" in lines[8]
    assert GROWTH not in answer  # what growth holds is what gives way


def test_what_couldnt_be_read_comes_before_a_long_list(conn, monkeypatch):
    for number in range(1, 41):
        item(conn, number, state="unknown", run_id=run_row(conn, "failed"), request_status="approved", used=True)
    conn.execute("DROP TABLE outreach_messages")
    answer = text()
    assert len(answer) <= remote_mod.TEXT_LIMIT
    assert answer.startswith("**Couldn't be read**\n- outreach: its pending work couldn't be read")


# --- the order, the masking and the voice ------------------------------------------------------------------


def test_each_group_runs_from_the_most_urgent_down(conn, monkeypatch):
    busy_world(conn, monkeypatch)
    answer = text()
    waiting = section(answer, YOU).strip().splitlines()
    assert ["A-0021" in waiting[0], waiting[1] == DECIDE, "APP-005" in waiting[2], "P-0001" in waiting[3]] == [True] * 4
    growth = section(answer, GROWTH).strip().splitlines()
    assert "APP-006" in growth[0] and "P-0002" in growth[1]
    assert [line for line in growth[2:5]] == ["- 1 community post planned for today onward.", "- 1 outreach email queued.",
                                              "- 1 social draft for today onward."]
    assert "Petty cash log" in growth[5]


def test_the_answer_is_masked_and_mentions_are_defused(conn, monkeypatch, d2_secrets):
    from sweep import RESEND_KEY

    fake_plugin(monkeypatch, NAME="builder", pending=lambda read_only: [
        agents.PendingItem(agents.YOU, f"Key {RESEND_KEY} for @everyone and <@123>, from tan.meiling@acme.sg")])
    answer = text()
    assert RESEND_KEY not in answer and "@everyone" not in answer and "<@123>" not in answer and "tan.meiling" not in answer


def raw_request(conn, number: int, kind: str, subject: str, reason: str) -> None:
    conn.execute("INSERT INTO approvals (id, kind, subject, content_hash, status, reason, requested_at, decide_by)"
                 " VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
                 (number, kind, subject, f"{number:064x}", reason, aw.NOW, aw.later(aw.NOW, hours=5)))


@pytest.mark.parametrize("padding", [65, 72, 77, 84, 90])
def test_an_address_across_the_cut_in_a_title_is_still_masked(conn, padding):
    """`group-rules`' real title, with a scraped group name: a cut address would no longer match a mask."""
    from jura_growth.agents.community import groups

    name = "G" * padding + " email jane.tan@gmail.com or 9123 4567 for the rules of this group, thanks"
    state, group_id, messages = groups.add(conn, {
        "channel": "facebook", "name": name, "url": "https://www.facebook.com/groups/x/", "fit": "good fit", "fit_reason": "r",
        "promo_rules": "not stated in public sources", "source_urls": ["https://example.com/x"]})
    assert state == "added", messages
    raw_request(conn, 8, "group-rules", f"group:{group_id}", "r")
    [line] = lines_about(text(), "A-0008")
    assert "Group" in line and "jane.tan" not in line and "jane" not in line and "9123" not in line


@pytest.mark.parametrize("padding", [78, 84, 90, 96])
def test_an_address_across_the_cut_in_a_requests_own_words_is_still_masked(conn, padding):
    raw_request(conn, 7, "no-such-kind", "no-such-kind:7", "x" * padding + " jane.tan@gmail.com and more words after it, past the cut")
    [line] = lines_about(text(), "A-0007")
    assert "xxx" in line and "jane" not in line


def test_a_title_masked_on_the_bare_command_too(conn):
    raw_request(conn, 7, "no-such-kind", "no-such-kind:7", "x" * 84 + " jane.tan@gmail.com and more words after it")
    assert "jane" not in CliRunner().invoke(cli, ["pending"]).output


def test_a_named_person_is_masked_even_when_remotes_own_load_meets_a_lock(conn, monkeypatch):
    def connect(path=None, *, migrate_now=True, wait=None):
        raise sqlite3.OperationalError("database is locked")

    fake_plugin(monkeypatch, NAME="builder", pending=lambda read_only: [agents.PendingItem(agents.YOU, "Ask Tan Mei Ling about it.")],
                privacy_terms=lambda read_only: {"named_addresses": ["tan.mei.ling@acme.sg"]})
    monkeypatch.setattr(db, "connect", connect)
    answer = text()
    assert "Ask" in answer and "Mei Ling" not in answer


def test_an_items_lines_stay_on_one_line(conn, monkeypatch):
    switch_dispatch(monkeypatch, on=False)
    app_id, _ = handed_off(conn, 5)
    [line] = lines_about(text(), app_id)
    assert "by hand" in line and "Build it:" in line


def test_the_voice_rules_hold_in_a_busy_answer(conn, monkeypatch):
    busy_world(conn, monkeypatch)
    answer = text()
    assert "!" not in answer
    assert {ch for ch in answer if not ch.isascii()} <= {"·", "…"}


def test_pending_names_no_agent_in_the_core():
    source = (paths.REPO_ROOT / "jura_growth" / "pending.py").read_text(encoding="utf-8")
    assert not re.search(r"(from|import) jura_growth\.agents\.\w+", source)
