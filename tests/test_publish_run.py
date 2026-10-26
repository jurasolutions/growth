"""The whole publish job with the fake `claude` binary (seam S10; datasets D11 and T).

`runner.run("publish")` in process; the fake plays a scenario of Chrome calls and real
`jura-growth publish ...` subprocesses. Rows traced: AC-P2.1 and AC-P2.2 (S10), AC-P5.3 (S10),
AC-P6.1, AC-P8.1, AC-P9.3, AC-P9.4, AC-P10.1 (S10), AC-P11.1 (S10), and the sweep over the
run updates and #alerts posts.
"""

from __future__ import annotations

import json
import os

import pytest

import publish_fake
import publish_transcripts as t
import publish_world as pw
import sweep
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, db, pause, paths, runner
from jura_growth.agents import publish

POST = t.POST
LOGIN = "https://www.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2Fjura-test-page"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    found = publish_fake.install(tmp_path, monkeypatch)
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    pw.at(monkeypatch, pw.TEN)
    return found


@pytest.fixture
def approved(conn, fake, monkeypatch):
    pw.at(monkeypatch, pw.MORNING)
    found, approval = pw.approved(conn, monkeypatch)
    pw.at(monkeypatch, pw.TEN)
    return found, approval


def claim() -> list[dict]:
    return [*t.browser_check(), {"cli": ["publish", "next", "--json"]}]


def chrome(step: dict) -> dict:
    """A `publish_transcripts` step as a fake scenario step."""
    return {"chrome": step["name"].removeprefix(t.CHROME), "input": step["input"], "result": step["result"],
            "error": step["error"], "denied": step["denied"]}


def browser(*steps: dict) -> list[dict]:
    return [chrome(s) for s in steps]


def post_steps(live_text: str = "{TEXT}") -> list[dict]:
    return [
        *browser(t.created(), t.opened(), t.page("get_page_text", {}, "Jura Solutions\nCreate post"),
                 t.page("computer", {"action": "left_click", "ref": "ref_12"}, "Clicked.")),
        chrome(t.typed("{TEXT}")),
        chrome(t.page("file_upload", {"paths": ["{IMG1}"]}, "Uploaded 1 file.")),
        *browser(t.page("computer", {"action": "left_click", "ref": "ref_30"}, "Clicked Post."), t.opened(POST)),
        chrome(t.page("get_page_text", {}, live_text, url=POST)),
        {"write": "{A}-live.txt", "text": live_text},
        {"cli": ["publish", "done", "{A}", "--url", POST, "--live-text-file", "{WORK}/{A}-live.txt"]},
        chrome(t.closed()),
    ]


def run():
    return runner.run("publish", ignore_schedule=True)


def outbox() -> list[dict]:
    folder = sweep.outbox_dir()
    found = []
    for file in sorted(folder.glob("*")) if folder.exists() else []:
        found += [json.loads(line) for line in file.read_text().splitlines() if line.strip()]
    return found


def alerts(double) -> list[str]:
    """#alerts posts from this process (the double) and from the fake's subprocesses (the outbox)."""
    return double.contents("alerts") + [r.get("content", "") for r in outbox() if r.get("channel") == "alerts"]


def item(conn, found) -> dict:
    return pw.item_row(conn, found.id)


def run_row(conn) -> dict:
    return db.one(conn, "SELECT * FROM runs WHERE job = 'publish' ORDER BY id DESC LIMIT 1")


# --- a clean post (AC-P2.2, AC-P7.1 through the run, AC-P8.1) ---------------------------------------


def test_a_clean_post_claims_before_any_page_tool_posts_and_reports_once(conn, fake, approved, discord_double):
    found, approval = approved
    fake.scenario([*claim(), *post_steps()], "OK: posted {A} " + POST)

    outcome = run()

    assert fake.started
    assert "--chrome" in fake.argv
    assert outcome.status == "ok", outcome
    claims = fake.claims  # what a second connection saw when `publish next` returned
    assert claims["used_at"] and claims["state"] == "claimed"
    assert claims["used_by_run"] == run_row(conn)["id"]
    row = item(conn, found)
    assert row["state"] == "done" and row["outcome"] == "posted" and row["post_url"] == POST
    assert row["live_text_matches"] == 1
    assert db.one(conn, "SELECT status, published_url FROM social_posts WHERE id = ?", (found.ref_id,)) == {
        "status": "published", "published_url": POST}
    updates = discord_double.contents("social-drafts")
    assert len(updates) == 1
    assert approval.id in updates[0] and "Facebook" in updates[0] and "posted" in updates[0] and POST in updates[0]
    assert "Chasing late invoices" not in updates[0]  # never the page's or the post's text
    assert alerts(discord_double) == []
    assert not pause.is_paused(conn, "publish")


def test_the_run_has_no_add_dir_and_its_images_were_copied_to_scratch(conn, fake, approved):
    fake.scenario([*claim(), *post_steps()], "OK: posted")
    run()
    assert "--add-dir" not in fake.argv
    handed = json.loads(fake.cli[0]["output"])
    assert handed["images"] and all(paths.is_within(p, paths.work_dir("publish")) for p in handed["images"])


# --- AC-P2.1 (S10): nothing due inside the run --------------------------------------------------------


def test_nothing_due_inside_the_run_ends_skip_with_no_page_call_and_no_update(conn, fake, monkeypatch, discord_double):
    pw.at(monkeypatch, pw.MORNING)
    pw.item(conn)  # pending, never approved
    pw.at(monkeypatch, pw.TEN)
    monkeypatch.setattr(publish, "precheck", lambda job, conn: None)  # as if it raced the precheck
    fake.scenario(claim(), "SKIP: nothing due")

    outcome = run()

    assert fake.started and outcome.status == "ok"
    assert json.loads(fake.cli[0]["output"])["due"] is False
    assert db.scalar(conn, "SELECT count(*) FROM publish_items WHERE claimed_at IS NOT NULL") == 0
    assert discord_double.contents("social-drafts") == []  # claimed-only


# --- AC-P5.3 (S10): every switch keeps Claude from starting -----------------------------------------


@pytest.mark.parametrize("switch", ["pause file", "pause publish", "pause all", "auto-pause", "draft mode"])
def test_a_kill_switch_never_starts_claude_and_keeps_the_approval(conn, fake, approved, monkeypatch, tmp_path, switch):
    found, approval = approved
    if switch == "pause file":
        (tmp_path / "PAUSE").write_text("stop")
    elif switch == "pause publish":
        pause.pause(conn, "publish", "by hand", notify=False)
    elif switch == "pause all":
        pause.pause(conn, "all", "by hand", notify=False)
    elif switch == "auto-pause":
        for _ in range(3):
            run_id = pw.run(conn, "2026-11-10T09:00:00+08:00")
            conn.execute("UPDATE runs SET status = 'failed', finished_at = started_at WHERE id = ?", (run_id,))
        assert pause.check_auto_pause(conn, "publish")
    else:
        fake.social(lambda data: data["platforms"]["facebook"].update(publish_mode="draft"))
    fake.scenario([*claim(), *post_steps()])

    run()

    assert not fake.started, f"claude started under {switch}"
    assert approvals.get(conn, approval.id).used_at is None
    assert item(conn, found)["state"] in ("ready", "withdrawn")


# --- AC-P6.1 and AC-P11.1 (S10): stop signals ----------------------------------------------------------


def stopped_scenario(reason: str, page_url: str, page_text: str) -> list[dict]:
    return [
        *claim(), *browser(t.created()),
        {"chrome": "navigate", "input": {"url": t.PAGE, "tabId": t.TAB}, "result": f"Navigated to {page_url}\n" + t.tab_context((t.TAB, page_url))},
        chrome(t.page("get_page_text", {}, page_text, url=page_url)),
        chrome(t.page("computer", {"action": "screenshot"}, "Screenshot taken.", url=page_url)),
        {"cli": ["publish", "stopped", "{A}", "--reason", reason]},
        chrome(t.closed()),
    ]


def test_a_login_wall_stops_the_item_pauses_publish_and_alerts_once_with_the_run(conn, fake, approved, discord_double):
    found, approval = approved
    fake.scenario(stopped_scenario("login", LOGIN, "Log in to Facebook\nEmail or phone\nPassword"), "FAIL: {A} login")

    outcome = run()

    assert outcome.status == "failed"
    assert run_row(conn)["status"] == "failed"
    assert item(conn, found)["state"] == "stopped" and item(conn, found)["stop_reason"] == "login"
    assert pause.is_paused(conn, "publish")
    sent = alerts(discord_double)
    assert len(sent) == 1, sent  # one alert per stop (code review 03, S-4)
    assert approval.id in sent[0] and "login or password prompt" in sent[0]
    assert f"run {run_row(conn)['id']}" in sent[0]  # no screenshot file: the run's transcript (decision 4)
    update = discord_double.contents("social-drafts")
    assert len(update) == 1 and approval.id in update[0] and "stopped" in update[0] and "login" in update[0]
    assert "Password" not in update[0]
    assert not [c for c in fake.cli if c["cli"][:2] == ["publish", "done"]]

    fake.scenario([*claim(), *post_steps()])  # the next slot
    run()
    assert not fake.started  # paused until `resume publish`


def test_the_wrong_identity_stops_before_any_typing(conn, fake, approved, discord_double):
    found, _ = approved
    fake.scenario(stopped_scenario("wrong-identity", t.PAGE, "Create post\nPosting as Somebody Else"), "FAIL: {A} wrong posting identity")

    run()

    row = item(conn, found)
    assert row["state"] == "stopped" and row["stop_reason"] == "wrong-identity"
    assert pause.is_paused(conn, "publish")
    record = (paths.data_dir() / "transcripts").rglob("*-publish.jsonl")
    typed = [line for path in record for line in path.read_text().splitlines() if '"action": "type"' in line]
    assert typed == []


# --- AC-P10.1 (S10): a claim left open -------------------------------------------------------------------


def test_a_claim_with_neither_done_nor_stopped_becomes_unknown_and_names_both_resolve_forms(conn, fake, approved, discord_double):
    found, approval = approved
    fake.scenario([*claim(), *browser(t.created(), t.opened(), t.closed())], "OK: I think it worked")

    outcome = run()

    assert outcome.status == "failed"
    assert item(conn, found)["state"] == "unknown"
    assert pause.is_paused(conn, "publish")
    posted = [a for a in alerts(discord_double) if approval.id in a]
    assert posted
    assert f"/growth publish resolve {approval.id} posted --url <url>" in posted[0]
    assert f"/growth publish resolve {approval.id} not-posted" in posted[0]
    update = discord_double.contents("social-drafts")
    assert len(update) == 1 and "unknown" in update[0]


# --- AC-P9.3 (S10): the audit fails the run -----------------------------------------------------------


def test_a_navigation_off_the_hosts_fails_the_run_pauses_publish_and_alerts(conn, fake, approved, discord_double):
    found, approval = approved
    steps = [*claim(), *post_steps()]
    steps.insert(len(claim()) + 2, chrome(t.opened("https://example.com/")))
    fake.scenario(steps, "OK: posted {A}")

    outcome = run()

    assert outcome.status == "failed"
    assert "example.com" in outcome.error
    assert run_row(conn)["status"] == "failed"
    assert pause.is_paused(conn, "publish")
    assert any("example.com" in a for a in alerts(discord_double))
    assert item(conn, found)["state"] == "done"  # it did post; the audit judges the run, not the item


def test_a_tab_left_open_is_a_warning_in_the_run_update(conn, fake, approved, discord_double):
    steps = [*claim(), *post_steps()][:-1]  # no tabs_close_mcp
    fake.scenario(steps, "OK: posted")

    outcome = run()

    assert outcome.status == "ok"
    update = discord_double.contents("social-drafts")
    assert len(update) == 1 and "left 1 tab open" in update[0]
    assert not pause.is_paused(conn, "publish")


def test_a_live_text_mismatch_alerts_pauses_and_says_so_in_the_update(conn, fake, approved, discord_double):
    found, approval = approved
    fake.scenario([*claim(), *post_steps(live_text="Something else entirely")], "OK: posted")

    run()

    assert item(conn, found)["live_text_matches"] == 0
    assert pause.is_paused(conn, "publish")
    assert any("doesn't match" in a and approval.id in a for a in alerts(discord_double))
    update = discord_double.contents("social-drafts")
    assert len(update) == 1 and "doesn't match" in update[0] and "Something else" not in update[0]


# --- B1 (code review 03): no model text reaches the run row, #alerts or the update -----------------------


PAGE_TEXT = "Visitor comment from the Page wall about invoices"


def test_a_fail_line_after_a_clean_post_is_withheld_everywhere(conn, fake, approved, discord_double):
    found, approval = approved
    fake.scenario([*claim(), *post_steps()], "FAIL: the page said " + PAGE_TEXT)

    outcome = run()

    row = run_row(conn)
    assert outcome.status == "failed" and row["status"] == "failed"
    shown = [row["error"] or "", row["summary"] or "", *alerts(discord_double), *discord_double.contents("social-drafts")]
    assert not [text for text in shown if PAGE_TEXT in text]
    assert approval.id in row["error"] and f"run {row['id']}" in row["error"]
    [alert] = alerts(discord_double)
    assert approval.id in alert and f"run {row['id']}" in alert


@pytest.mark.parametrize("ending", ["OK: " + PAGE_TEXT, "SKIP: " + PAGE_TEXT, "FAIL: " + PAGE_TEXT])
def test_a_run_that_claims_nothing_keeps_no_model_words_either(conn, fake, monkeypatch, discord_double, ending):
    monkeypatch.setattr(publish, "precheck", lambda job, conn: None)
    fake.scenario(claim(), ending)

    run()

    row = run_row(conn)
    shown = [row["error"] or "", row["summary"] or "", *alerts(discord_double), *discord_double.contents("social-drafts")]
    assert not [text for text in shown if PAGE_TEXT in text]
    if ending.startswith("FAIL"):
        assert row["status"] == "failed" and f"run {row['id']}" in row["error"]


# --- S-8 (code review 03): the image copies --------------------------------------------------------


def test_the_image_copies_are_read_only_after_the_claim(conn, fake, approved):
    fake.scenario([*claim(), *post_steps()], "OK: posted")
    run()
    copies = json.loads(fake.cli[0]["output"])["images"]
    assert copies and all(not os.access(path, os.W_OK) for path in copies)


def test_an_image_copy_rewritten_during_the_run_fails_it_and_pauses_publish(conn, fake, approved, discord_double):
    steps = [*claim(), {"tamper": "{IMG1}"}, *post_steps()]
    fake.scenario(steps, "OK: posted")

    outcome = run()

    assert outcome.status == "failed"
    assert "approved image" in outcome.error
    assert pause.is_paused(conn, "publish")


# --- AC-P9.4: no browser connected -------------------------------------------------------------------


NO_BROWSER = [{"chrome": "list_connected_browsers", "input": {}, "result": t.NO_BROWSER, "error": True}]


def no_browser_alerts(double) -> list[str]:
    return [a for a in alerts(double) if "No browser" in a]


def test_no_browser_ends_skip_claims_nothing_and_alerts_once_a_day(conn, fake, approved, monkeypatch, discord_double):
    found, approval = approved
    fake.scenario(NO_BROWSER, "SKIP: no browser connected")

    first = run()
    pw.at(monkeypatch, "2026-11-10T10:20:00+08:00")
    fake.scenario(NO_BROWSER, "SKIP: no browser connected")
    run()

    assert first.status == "ok"
    assert not [c for c in fake.cli if c["cli"][:2] == ["publish", "next"]]
    assert item(conn, found)["state"] == "ready"
    assert approvals.get(conn, approval.id).status == "approved" and approvals.get(conn, approval.id).used_at is None
    assert len(no_browser_alerts(discord_double)) == 1
    assert discord_double.contents("social-drafts") == []

    pw.at(monkeypatch, "2026-11-11T07:05:00+08:00")
    pw.approved(conn, monkeypatch, day=pw.DAY.replace(day=11))
    pw.at(monkeypatch, "2026-11-11T10:00:00+08:00")
    fake.scenario(NO_BROWSER, "SKIP: no browser connected")
    run()
    assert len(no_browser_alerts(discord_double)) == 2


# --- the sweep over this ticket's messages (AC-M11.1, AC-M12.1) ----------------------------------------


def test_nothing_planted_reaches_discord_from_a_publish_run(conn, fake, monkeypatch, tmp_path, discord_double):
    """Every message kind this ticket sends: the run update of a post, a stop, a live-text
    mismatch, an unknown item, the no-browser alert and a run that fails before claiming, each
    with planted page text in its transcript and its model summary (code review 03, B1 and S-6).
    The marker reaches Discord only through the approved post's own card."""
    env = tmp_path / "uat.env"  # the D2 env file without its `keychain:` line: the fake's
    env.write_text("\n".join(line for line in sweep.ENV_FILE.splitlines() if "keychain:" not in line) + "\n")
    env.chmod(0o600)  # subprocesses can't use the Keychain double and must never ask the real one
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    planted = sweep.Planted(secrets=(sweep.RESEND_KEY, sweep.AWKWARD), personal=sweep.PERSONAL)
    page = planted.text()
    said = "FAIL: the page said\n" + page

    def next_day(day: int) -> None:
        pause.resume(conn, "publish")
        pw.at(monkeypatch, f"2026-11-{day}T07:05:00+08:00")
        _, request = pw.item(conn, day=pw.DAY.replace(day=day), text=pw.TEXT + "\n" + sweep.MARKER)
        cards.sweep_safely(conn)  # the card, while the request is pending, as it goes out live
        pw.decide(conn, request, monkeypatch=monkeypatch)
        pw.at(monkeypatch, f"2026-11-{day}T10:00:00+08:00")

    with_page = [chrome(t.page("get_page_text", {}, page))]
    next_day(10)
    fake.scenario([*claim(), *post_steps()[:3], *with_page, *post_steps()[3:]], said)
    run()  # posted, with a FAIL: summary
    next_day(11)
    fake.scenario(stopped_scenario("login", LOGIN, page), said)
    run()  # a stop
    next_day(12)
    fake.scenario([*claim(), *post_steps(live_text=page)], said)
    run()  # a live-text mismatch
    next_day(13)
    fake.scenario([*claim(), *browser(t.created(), t.opened()), *with_page, chrome(t.closed())], said)
    run()  # an unknown item
    next_day(14)
    fake.scenario(NO_BROWSER, "SKIP: " + page)
    run()  # the no-browser alert
    monkeypatch.setattr(publish, "precheck", lambda job, conn: None)
    fake.scenario(browser(*t.browser_check()), said)
    run()  # a failure before any claim

    assert len(discord_double.contents("social-drafts")) == 4
    assert len([a for a in alerts(discord_double) if "No browser" in a]) == 1
    sweep.assert_clean(discord_double, sweep.outbox_dir(), planted)


# --- run_update: claimed-only ---------------------------------------------------------------------------


def test_skips_never_post_a_run_update(conn, fake, approved, monkeypatch, discord_double):
    from jura_growth import locks

    with locks.held("publish") as acquired:  # the lock skip: no connection, no update
        assert acquired
        assert run().summary == locks.STILL_GOING
    monkeypatch.setenv("ANTHROPIC_API_KEY", "set-for-the-test")  # a plain skip with a run row
    assert run().status == "skipped"

    assert not fake.started
    assert discord_double.contents("social-drafts") == []
