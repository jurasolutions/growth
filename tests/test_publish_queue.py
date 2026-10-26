"""The publish queue commands, with no browser (BP-02a; test strategy v3 §4.2, seam S7).

`publish next`, `done`, `stopped`, `queue` and `resolve` through click's `CliRunner`, the claim
through `claim.next_item`, the `after_run` hook through `runner.run()` (S9), the digest hook, and
the migration (X7). The clock is BP's default, Tue 2026-11-10; Facebook is in `browser` mode.
"""

from __future__ import annotations

import json
import threading
from datetime import date

import pytest

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import agents, approvals, db, digest, headless, pause, paths, runner, timeutil
from jura_growth.agents import publish
from jura_growth.agents.publish import claim, items
from runner_support import settings_with


@pytest.fixture
def world(monkeypatch):
    pw.social_config(monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)


def next_json(*extra):
    result = pw.invoke("publish", "next", "--json", *extra)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def state(conn, found) -> str:
    return pw.item_row(conn, found.id)["state"]


def used(conn, approval) -> bool:
    return bool(approvals.get(conn, approval.id).used_at)


# --- AC-P2.1 nothing due unless approved ----------------------------------------------------


@pytest.mark.parametrize("status", ["pending", "skipped", "expired", "superseded"])
def test_an_item_whose_request_isnt_approved_is_never_due(conn, world, monkeypatch, status):
    found, request = pw.item(conn)
    if status == "skipped":
        pw.decide(conn, request, "skip")
    elif status == "expired":
        pw.at(monkeypatch, "2026-11-10T18:00:00+08:00")
        approvals.expire_due(conn)
        pw.at(monkeypatch, pw.TEN)
    elif status == "superseded":
        conn.execute("UPDATE social_posts SET text = text || ' (changed)' WHERE id = ?", (found.ref_id,))
        approvals.expire_due(conn)
    assert approvals.get(conn, request.id).status == status
    result = pw.invoke("publish", "next")
    assert result.exit_code == 0 and result.output.startswith("nothing due")
    assert db.scalar(conn, "SELECT count(*) FROM publish_items WHERE claimed_at IS NOT NULL") == 0
    assert db.scalar(conn, "SELECT count(*) FROM approvals WHERE used_at IS NOT NULL") == 0
    assert next_json() == {"due": False, "reasons": next_json()["reasons"]}


# --- AC-P2.2 the claim and the item, in one committed transaction ----------------------------


def test_publish_next_claims_the_approval_and_the_item_before_it_prints(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    run = pw.run(conn, monkeypatch=monkeypatch)
    handed = next_json()
    assert handed["due"] is True and handed["approval"] == request.id and handed["item"] == found.label
    assert handed["kind"] == "social-post" and handed["platform"] == "facebook"
    assert handed["target_url"] == pw.PAGE_URL and handed["posting_identity"] == "the Jura Solutions Facebook Page"
    assert handed["text"] == pw.TEXT and handed["day"] == "2026-11-10"
    assert pw.fresh_state(request.id) == {"used_at": "2026-11-10T10:00:00+08:00", "used_by_run": run, "state": "claimed"}
    events = [e for e in pw_events(conn, "approval.used")]
    assert len(events) == 1


def pw_events(conn, kind):
    return [json.loads(r["payload_json"]) for r in conn.execute("SELECT payload_json FROM events WHERE kind = ?", (kind,))]


def test_publish_next_copies_the_items_images_into_the_runs_scratch_folder(conn, world, monkeypatch):
    """X8 (copy)."""
    images = [pw.image("facebook-1.png"), pw.image("facebook-2.png", pw.png(extra=b"two"))]
    _, request = pw.approved(conn, monkeypatch, images=images)
    handed = next_json()
    copies = [pw.Path(p) for p in handed["images"]]
    assert [c.name for c in copies] == ["1-facebook-1.png", "2-facebook-2.png"]
    assert all(paths.is_within(c, paths.work_dir("publish")) for c in copies)
    assert [c.read_bytes() for c in copies] == [i.read_bytes() for i in images]


def test_an_image_that_changes_on_disk_after_approval_is_never_handed_out(conn, world, monkeypatch):
    image = pw.image("facebook-1.png")
    _, request = pw.approved(conn, monkeypatch, images=[image])
    image.write_bytes(pw.png(extra=b"swapped"))
    assert next_json()["due"] is False
    assert approvals.get(conn, request.id).status == "superseded"


def test_two_publish_next_calls_racing_for_one_item_give_one_claim(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    barrier = threading.Barrier(2)
    results: list = []

    def race():
        own = db.connect(migrate_now=False)
        try:
            barrier.wait()
            results.append(claim.next_item(own))
        finally:
            own.close()

    threads = [threading.Thread(target=race) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(r.item is not None for r in results) == [False, True]
    assert len(pw_events(conn, "approval.used")) == 1
    assert state(conn, found) == "claimed"


# --- AC-P2.3 skip wins until the claim ------------------------------------------------------


def test_a_skip_after_approval_withdraws_the_item_and_records_the_social_skip(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    assert pw.decide(conn, request, "skip").answer == "recorded"
    assert state(conn, found) == "withdrawn"
    assert db.one(conn, "SELECT date, platform FROM social_skips") == {"date": "2026-11-10", "platform": "facebook"}
    assert db.scalar(conn, "SELECT status FROM social_posts WHERE id = ?", (found.ref_id,)) == "skipped"
    assert next_json()["due"] is False


def test_a_skip_after_the_claim_answers_already_used(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    next_json()
    answer = pw.decide(conn, request, "skip")
    assert answer.answer == "already-used"
    assert state(conn, found) == "claimed"
    assert db.rows(conn, "SELECT * FROM social_skips") == []


# --- AC-P3 deadlines --------------------------------------------------------------------------


def test_claimable_at_17_59_59(conn, world, monkeypatch):
    _, request = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, "2026-11-10T17:59:59+08:00")
    assert next_json()["approval"] == request.id


@pytest.mark.parametrize("moment", ["2026-11-10T18:00:00+08:00", "2026-11-11T09:00:00+08:00"])
def test_at_18_00_or_the_next_morning_nothing_is_claimed_and_the_request_is_expired(conn, world, monkeypatch, moment):
    found, request = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, moment)
    assert next_json()["due"] is False
    record = approvals.get(conn, request.id)
    assert record.status == "expired" and record.used_at is None
    assert state(conn, found) == "withdrawn"


def test_an_approve_recorded_at_18_02_is_expired_whatever_discords_time(conn, world, monkeypatch):
    found, request = pw.item(conn)
    pw.at(monkeypatch, "2026-11-10T18:02:00+08:00")
    answer = approvals.decide(conn, request.id, "approve", actor=f"discord:{pw.CONTROL_ID}",
                              origin=pw.Origin.ssh(), source_ref="1700000000000000000:dlv-1759", args={})
    assert answer.answer == "expired"
    assert approvals.get(conn, request.id).decided_at is None


@pytest.mark.parametrize("window, deadline", [({"start": "10:00", "end": "16:00"}, "16:00"), ({"start": "08:00", "end": "20:00"}, "18:00")])
def test_the_deadlines_are_the_end_of_the_configured_window(conn, world, monkeypatch, window, deadline):
    publish_config(monkeypatch, window=window)
    pw.at(monkeypatch, pw.MORNING)
    _, request = pw.item(conn)
    assert request.decide_by == f"2026-11-10T{deadline}:00+08:00"
    pw.decide(conn, request)
    assert approvals.get(conn, request.id).use_by == f"2026-11-10T{deadline}:00+08:00"


def publish_config(monkeypatch, **values):
    from jura_growth import config

    real = config.agent_config
    current = real  # keep the social patch

    def patched(agent):
        return dict(values) if agent == "publish" else current(agent)

    monkeypatch.setattr(config, "agent_config", patched)


# --- AC-P5.1 the limits at publish next (lines 1, 6, 7 and 11) ---------------------------------


def test_line_1_a_second_facebook_item_for_the_same_day_is_refused(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    next_json()
    assert pw.invoke("publish", "stopped", request.id, "--reason", "login").exit_code == 0
    pause.resume(conn, "publish")
    second = items.create_social(conn, found.ref_id, run_id=None)
    pw.decide(conn, second.approval)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    refused = next_json()
    assert refused["due"] is False
    assert any("facebook already had its post claimed for 2026-11-10" in r for r in refused["reasons"])
    assert not used(conn, second.approval)


def test_line_6_the_gap_is_measured_between_the_runs_start_times(conn, world, monkeypatch):
    pw.social_config(monkeypatch, browser=("facebook", "linkedin"))
    pw.approved(conn, monkeypatch)
    _, second = pw.approved(conn, monkeypatch, "linkedin")
    pw.at(monkeypatch, "2026-11-10T10:03:00+08:00")
    first = pw.run(conn, "2026-11-10T10:00:00+08:00")
    assert pw.next_item(conn, first).item is not None
    pw.at(monkeypatch, "2026-11-10T10:21:00+08:00")
    early = pw.run(conn, "2026-11-10T10:15:00+08:00")
    refused = pw.next_item(conn, early)
    assert refused.item is None and "10:00" in refused.why[0] and "10:20" in refused.why[0]
    assert not used(conn, second)
    later = pw.run(conn, "2026-11-10T10:20:00+08:00")
    assert pw.next_item(conn, later).approval.id == second.id


@pytest.mark.parametrize("moment, claimed", [("2026-11-10T08:59:00+08:00", False), ("2026-11-10T09:00:00+08:00", True),
                                             ("2026-11-10T18:00:00+08:00", False)])
def test_line_7_claims_only_inside_the_posting_window(conn, world, monkeypatch, moment, claimed):
    _, request = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, moment)
    handed = next_json()
    assert handed["due"] is claimed
    if moment.endswith("08:59:00+08:00"):
        assert "outside the posting window (09:00 to 18:00 SGT)" in handed["reasons"][0]
        assert approvals.get(conn, request.id).status == "approved" and not used(conn, request)


def test_line_11_a_second_publish_next_in_the_same_run_is_refused(conn, world, monkeypatch):
    pw.social_config(monkeypatch, browser=("facebook", "linkedin"))
    pw.approved(conn, monkeypatch)
    _, second = pw.approved(conn, monkeypatch, "linkedin")
    pw.run(conn, monkeypatch=monkeypatch)
    assert next_json()["due"] is True
    refused = next_json()
    assert refused["due"] is False and "this run has already claimed its 1 item" in refused["reasons"][0]
    assert not used(conn, second)


# --- AC-P5.2 a crashed or stopped claim still counts ----------------------------------------------


@pytest.mark.parametrize("ending", ["stopped", "unknown"])
def test_a_claim_that_ended_badly_still_counts_against_the_day(conn, world, monkeypatch, ending):
    found, request = pw.approved(conn, monkeypatch)
    run = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    if ending == "stopped":
        pw.invoke("publish", "stopped", request.id, "--reason", "captcha")
    else:
        publish.after_run(conn, "publish", run, runner.Outcome("ok"))
    pause.resume(conn, "publish")
    monkeypatch.delenv("JURA_GROWTH_RUN_ID")
    second = items.create_social(conn, found.ref_id, run_id=None)
    pw.decide(conn, second.approval)
    pw.at(monkeypatch, "2026-11-10T11:00:00+08:00")
    assert next_json()["due"] is False
    assert pw.item_row(conn, found.id)["state"] == ending


# --- AC-P5.3 kill switches: nothing claimed, the approval not consumed -------------------------


@pytest.mark.parametrize("brake", ["PAUSE file", "pause publish", "pause all", "auto-pause", "publish_mode draft"])
def test_a_kill_switch_claims_nothing_and_keeps_the_approval(conn, world, monkeypatch, brake):
    found, request = pw.approved(conn, monkeypatch)
    if brake == "PAUSE file":
        paths.pause_file().write_text("stop\n")
    elif brake == "pause publish":
        pw.invoke("pause", "publish")
    elif brake == "pause all":
        pw.invoke("pause", "all")
    elif brake == "auto-pause":
        for _ in range(3):
            run = pw.run(conn)
            conn.execute("UPDATE runs SET status = 'failed', finished_at = ? WHERE id = ?", (timeutil.stamp(), run))
        assert pause.check_auto_pause(conn, "publish")
    else:
        pw.social_config(monkeypatch, browser=())
    handed = next_json()
    assert handed["due"] is False
    assert state(conn, found) == "ready"
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None


# --- AC-P6.1 publish stopped --------------------------------------------------------------------


def test_publish_stopped_marks_the_item_pauses_publish_and_alerts(conn, world, monkeypatch, discord_double):
    found, request = pw.approved(conn, monkeypatch)
    next_json()
    shot = paths.work_dir("publish") / "login.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(pw.PNG)
    result = pw.invoke("publish", "stopped", request.id, "--reason", "login", "--screenshot", str(shot))
    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert row["state"] == "stopped" and row["stop_reason"] == "login"
    assert pause.is_paused(conn, "publish")
    [alert] = [c for c in discord_double.contents("alerts") if request.id in c]
    assert "login" in alert and str(shot) in alert
    _, other = pw.approved(conn, monkeypatch, "facebook", day=date(2026, 11, 11))
    pw.at(monkeypatch, "2026-11-11T10:00:00+08:00")
    assert next_json()["due"] is False
    pw.invoke("resume", "publish")
    assert next_json()["approval"] == other.id


def test_a_screenshot_outside_the_scratch_folder_is_not_named(conn, world, monkeypatch, discord_double, tmp_path):
    _, request = pw.approved(conn, monkeypatch)
    next_json()
    elsewhere = tmp_path / "elsewhere.png"
    elsewhere.write_bytes(pw.PNG)
    assert pw.invoke("publish", "stopped", request.id, "--reason", "login", "--screenshot", str(elsewhere)).exit_code == 0
    [alert] = [c for c in discord_double.contents("alerts") if request.id in c]
    assert str(elsewhere) not in alert


@pytest.mark.parametrize("command", ["done", "stopped"])
def test_done_and_stopped_need_a_claimed_item(conn, world, monkeypatch, command):
    _, request = pw.approved(conn, monkeypatch)
    args = ["--url", pw.PAGE_URL + "/posts/1", "--live-text-file", live_file(pw.TEXT)] if command == "done" else ["--reason", "login"]
    result = pw.invoke("publish", command, request.id, *args)
    assert result.exit_code == 1 and "isn't claimed" in result.output


# --- AC-P6.3 and AC-P10.2 a headless run can't resume or resolve ------------------------------


@pytest.mark.parametrize("words", [("resume", "publish"), ("publish", "resolve", "A-0001", "not-posted")])
def test_a_headless_run_cant_resume_or_resolve(conn, world, monkeypatch, words):
    monkeypatch.setenv("JURA_GROWTH_JOB", "social")
    monkeypatch.setenv("JURA_GROWTH_AGENT", "social")
    result = pw.invoke(*words)
    assert result.exit_code == 2 and "refused:" in result.output


# --- AC-P7 done, the URL and the live text -------------------------------------------------------


def live_file(text: str) -> str:
    path = paths.work_dir("publish") / "live.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_publish_done_records_the_post_its_url_and_the_run(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    run = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    url = "https://www.facebook.com/jura-test-page/posts/123456"
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["outcome"], row["post_url"], row["live_text_matches"]) == ("done", "posted", url, 1)
    post = db.one(conn, "SELECT status, published_url, published_at FROM social_posts WHERE id = ?", (found.ref_id,))
    assert post == {"status": "published", "published_url": url, "published_at": "2026-11-10T10:00:00+08:00"}
    assert approvals.get(conn, request.id).used_by_run == run
    assert not pause.is_paused(conn, "publish")


@pytest.mark.parametrize("url", [
    "https://facebook.com.evil.test/jura/posts/1",
    "https://www.facebook.com@evil.test/jura/posts/1",
    "https://evil.test/www.facebook.com/posts/1",
    "javascript:alert(1)",
    "http://www.facebook.com/jura/posts/1",
    "https:///posts/1",
    "https://www.facebook.com:8443/jura/posts/1",
])
def test_a_url_off_the_platforms_hosts_exits_1_and_records_nothing(conn, world, monkeypatch, url):
    found, request = pw.approved(conn, monkeypatch)
    next_json()
    result = pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT))
    assert result.exit_code == 1
    assert pw.item_row(conn, found.id)["state"] == "claimed"


@pytest.mark.parametrize("url", ["https://www.facebook.com/jura/posts/1", "https://facebook.com/jura/posts/1",
                                 "https://m.facebook.com/story.php?id=1"])
def test_the_platforms_own_hosts_are_accepted(conn, world, monkeypatch, url):
    _, request = pw.approved(conn, monkeypatch)
    next_json()
    assert pw.invoke("publish", "done", request.id, "--url", url, "--live-text-file", live_file(pw.TEXT)).exit_code == 0


CAFE = "Caf\u00e9 owners: chasing invoices by hand?\n\nMore at https://jurasolutions.sg\n"


@pytest.mark.parametrize("live, matches", [
    (CAFE, True),
    ("  " + CAFE.replace("\n\n", "\n \n\t") + "\n\n", True),  # whitespace collapsed and trimmed
    (CAFE.replace("\u00e9", "e\u0301"), True),  # the same text after NFC
    (CAFE.replace("\u00e9", "e"), False),
    (CAFE.replace("chasing", "chase"), False),
    (CAFE + " Buy now.", False),
])
def test_live_text_is_compared_after_nfc_collapsed_whitespace_and_trimming(conn, world, monkeypatch, discord_double, live, matches):
    found, request = pw.approved(conn, monkeypatch, text=CAFE)
    next_json()
    result = pw.invoke("publish", "done", request.id, "--url", "https://www.facebook.com/jura/posts/9",
                       "--live-text-file", live_file(live))
    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert row["state"] == "done" and row["live_text_matches"] == (1 if matches else 0)
    alerts = [c for c in discord_double.contents("alerts") if request.id in c]
    assert bool(alerts) is (not matches)
    assert bool(pause.is_paused(conn, "publish")) is (not matches)


def test_nfc_equivalent_text_matches():
    from jura_growth.agents.publish import commands

    assert commands.same_text("Café au lait", "Café  au\nlait ")
    assert not commands.same_text("Cafe au lait", "Café au lait")


# --- AC-P10.1 after_run settles an open claim ------------------------------------------------------


def publish_job(monkeypatch):
    settings_with(monkeypatch, jobs={"publish-test": {"agent": "publish", "kind": "command", "command": ["publish", "next"],
                                                      "schedule": {"daily": "10:00"}}})


def test_after_run_settles_a_claim_left_open_as_unknown(conn, world, monkeypatch, discord_double):
    found, request = pw.approved(conn, monkeypatch)
    publish_job(monkeypatch)
    outcome = runner.run("publish-test", ignore_schedule=True)
    assert outcome.status == "failed"
    row = pw.item_row(conn, found.id)
    assert row["state"] == "unknown"
    assert pause.is_paused(conn, "publish")
    [alert] = [c for c in discord_double.contents("alerts") if request.id in c]
    assert f"/growth publish resolve {request.id} posted --url <url>" in alert
    assert f"/growth publish resolve {request.id} not-posted" in alert
    pause.resume(conn, "publish")
    assert next_json()["due"] is False
    assert pw.item_row(conn, found.id)["state"] == "unknown"


def test_after_run_leaves_a_closed_claim_and_a_quiet_run_alone(conn, world, monkeypatch):
    publish_job(monkeypatch)
    assert runner.run("publish-test", ignore_schedule=True).status == "ok"  # nothing due
    found, request = pw.approved(conn, monkeypatch)
    run = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    pw.invoke("publish", "done", request.id, "--url", "https://www.facebook.com/jura/posts/9", "--live-text-file", live_file(pw.TEXT))
    assert publish.after_run(conn, "publish", run, runner.Outcome("ok")) is None
    assert pw.item_row(conn, found.id)["state"] == "done" and not pause.is_paused(conn, "publish")


# --- AC-P10.2 resolve, from Terminal --------------------------------------------------------------


def unknown_item(conn, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    run = pw.run(conn, monkeypatch=monkeypatch)
    next_json()
    publish.after_run(conn, "publish", run, runner.Outcome("ok"))
    monkeypatch.delenv("JURA_GROWTH_RUN_ID")
    return found, request


def test_resolve_posted_records_the_post(conn, world, monkeypatch):
    found, request = unknown_item(conn, monkeypatch)
    url = "https://www.facebook.com/jura-test-page/posts/77"
    result = pw.invoke("publish", "resolve", request.id, "posted", "--url", url)
    assert result.exit_code == 0, result.output
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["outcome"], row["post_url"]) == ("done", "posted", url)
    assert db.scalar(conn, "SELECT status FROM social_posts WHERE id = ?", (found.ref_id,)) == "published"


def test_resolve_not_posted_withdraws_the_item_and_leaves_the_draft(conn, world, monkeypatch):
    found, request = unknown_item(conn, monkeypatch)
    assert pw.invoke("publish", "resolve", request.id, "not-posted").exit_code == 0
    row = pw.item_row(conn, found.id)
    assert (row["state"], row["outcome"]) == ("withdrawn", "not-posted")
    assert db.scalar(conn, "SELECT status FROM social_posts WHERE id = ?", (found.ref_id,)) == "draft"


def test_resolve_refuses_a_bad_url_and_an_item_that_isnt_unknown(conn, world, monkeypatch):
    found, request = unknown_item(conn, monkeypatch)
    assert pw.invoke("publish", "resolve", request.id, "posted", "--url", "https://evil.test/x").exit_code == 1
    assert pw.invoke("publish", "resolve", request.id, "posted").exit_code == 1
    assert pw.item_row(conn, found.id)["state"] == "unknown"
    _, other = pw.approved(conn, monkeypatch, "facebook", day=date(2026, 11, 11))
    result = pw.invoke("publish", "resolve", other.id, "not-posted")
    assert result.exit_code == 1 and "isn't unknown" in result.output


@pytest.mark.parametrize("typed", ["P-0001", "publish_item:1", "1", "A-9999"])
def test_g30_resolve_takes_only_an_a_id(conn, world, monkeypatch, typed):
    found, _ = unknown_item(conn, monkeypatch)
    result = pw.invoke("publish", "resolve", typed, "not-posted")
    assert result.exit_code == 1 and "no approval request" in result.output
    assert pw.item_row(conn, found.id)["state"] == "unknown"


# --- publish queue ---------------------------------------------------------------------------------


def test_publish_queue_lists_items_their_state_and_their_a_ids(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    _, waiting = pw.item(conn, "facebook", day=date(2026, 11, 11))
    text = pw.invoke("publish", "queue").output
    assert f"{found.label}  {request.id}  facebook  2026-11-10  ready (approved)" in text
    assert f"{waiting.id}" in text and "ready (pending)" in text
    listed = json.loads(pw.invoke("publish", "queue", "--json").output)
    assert [(i["item"], i["approval"], i["state"], i["request"]) for i in listed["items"]][0] == (
        found.label, request.id, "ready", "approved")


# --- AC-P8.3 the digest ----------------------------------------------------------------------------


def test_the_digest_counts_the_days_posted_skipped_expired_and_stopped(conn, world, monkeypatch):
    pw.social_config(monkeypatch, browser=("facebook", "linkedin", "instagram"))
    posted, a = pw.approved(conn, monkeypatch, "facebook")
    stopped, b = pw.approved(conn, monkeypatch, "linkedin")
    skipped, c = pw.approved(conn, monkeypatch, "instagram")
    pw.decide(conn, c, "skip")
    pw.run(conn, "2026-11-10T10:00:00+08:00", monkeypatch)
    next_json()
    pw.invoke("publish", "done", a.id, "--url", "https://www.facebook.com/jura/posts/1", "--live-text-file", live_file(pw.TEXT))
    pw.at(monkeypatch, "2026-11-10T10:30:00+08:00")
    pw.run(conn, "2026-11-10T10:30:00+08:00", monkeypatch)
    next_json()
    pw.invoke("publish", "stopped", b.id, "--reason", "checkpoint")
    expiring, d = pw.item(conn, "facebook", day=date(2026, 11, 12))
    pw.at(monkeypatch, "2026-11-12T18:00:00+08:00")
    approvals.expire_due(conn)
    part = publish.digest(conn, "2026-11-10")
    assert part["figures"] == {"publish_posted": 1, "publish_skipped": 1, "publish_expired": 0, "publish_stopped": 1}
    assert part["lines"] == ["Publishing: 1 posted, 1 skipped, 0 expired, 1 stopped"]
    assert publish.digest(conn, "2026-11-12")["figures"]["publish_expired"] == 1
    assert publish.digest(conn, "2026-11-09") == {"figures": {}, "lines": [], "brief": []}
    assert "Publishing: 1 posted" in "\n".join(digest.build(conn, "2026-11-10")["lines"])


# --- X7 the migration adds only -----------------------------------------------------------------------


def test_the_publish_items_migration_changes_no_existing_row(tmp_path, monkeypatch):
    path = tmp_path / "before.db"
    real = agents.plugins
    without = tuple(m for m in real() if getattr(m, "NAME", "") != "publish")
    monkeypatch.setattr(agents, "plugins", lambda: without)
    old = db.connect(path)
    pw.draft(old)
    old.execute("INSERT INTO runs (agent, job, started_at, status) VALUES ('social', 'social', '2026-11-10T07:00:00+08:00', 'ok')")
    before = snapshot(old)
    old.close()
    monkeypatch.setattr(agents, "plugins", real)
    new = db.connect(path)
    try:
        after = snapshot(new)
        kept = {table: rows for table, rows in after.items() if table in before and table != "schema_migrations"}
        assert kept == {table: rows for table, rows in before.items() if table != "schema_migrations"}
        assert "publish_items" in after and after["publish_items"] == []
        assert "publish/0001_publish_items.sql" in {r[0] for r in after["schema_migrations"]} - {r[0] for r in before["schema_migrations"]}
    finally:
        new.close()


def snapshot(conn) -> dict:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    found = {t: sorted(tuple(r) for r in conn.execute(f"SELECT * FROM {t}")) for t in tables if t != "schema_migrations"}
    found["schema_migrations"] = sorted((r[0],) for r in conn.execute("SELECT id FROM schema_migrations"))
    return found


def test_publish_items_holds_no_approval_state():
    """G31: no column named for a decision, an approver, a deadline or the claim."""
    sql = (publish.MIGRATIONS / "0001_publish_items.sql").read_text().lower()
    for word in ("decided", "approved", "approver", "decide_by", "use_by", "used_at"):
        assert word not in sql


# --- AC-M4.7 the publish plug-in failed to load ---------------------------------------------------


def test_with_the_publish_plug_in_missing_a_social_post_approval_fails_closed(conn, world, monkeypatch):
    found, request = pw.approved(conn, monkeypatch)
    real = agents.plugins
    monkeypatch.setattr(agents, "plugins", lambda: tuple(m for m in real() if getattr(m, "NAME", None) != "publish"))
    with pytest.raises(approvals.NotApproved) as refused:
        with db.transaction(conn):
            approvals.use(conn, "social-post", found.subject, run_id=None)
    assert refused.value.reason == "unknown-kind"
    pw.at(monkeypatch, "2026-11-11T10:00:00+08:00")
    assert approvals.expire_due(conn) == []
    record = approvals.get(conn, request.id)
    assert record.status == "approved" and record.used_at is None


# --- claimable(): the read-only form, for BP-03's precheck ----------------------------------------


def everything(conn) -> dict:
    return {table: db.rows(conn, f"SELECT * FROM {table} ORDER BY rowid") for table in ("approvals", "publish_items", "events")}


def test_claimable_lists_what_publish_next_would_claim_and_writes_nothing(conn, world, monkeypatch):
    pw.item(conn, "facebook", day=date(2026, 11, 11))
    found, request = pw.approved(conn, monkeypatch)
    before = everything(conn)
    assert [i.id for i in claim.claimable(conn)] == [found.id]
    assert everything(conn) == before
    assert not (paths.work_dir("publish") / request.id).exists()
    pw.at(monkeypatch, "2026-11-10T08:59:00+08:00")
    assert claim.claimable(conn) == []
    pw.at(monkeypatch, pw.TEN)
    pw.invoke("pause", "publish")
    assert claim.claimable(conn) == []
    pw.invoke("resume", "publish")
    conn.execute("UPDATE social_posts SET text = text || ' (changed)' WHERE id = ?", (found.ref_id,))
    before = everything(conn)
    assert claim.claimable(conn) == []  # use() would supersede it: rolled back
    assert everything(conn) == before
    assert approvals.get(conn, request.id).status == "approved"
