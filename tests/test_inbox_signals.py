"""What the inbox tells him with no person writing, and what it won't let him miss (ticket 04). Rows:
IW-W4 and IW-R5. In this file `s7`, `s12` and `s14` are the functional review's S numbers.

D1 is the stub in `tests/d1_stub.py`, answering the real SQL. Discord is the double. Nothing here reaches a
real service.
"""

from __future__ import annotations

import json

import httpx
import pytest

import d1_stub
import sweep
from discord_double import discord_double  # noqa: F401 - a fixture
from inbox_world import raw_mail
from jura_growth import approvals, db, digest, paths
from jura_growth.agents.inbox import job, report, signals, store, triage
from test_inbox_email_reply import DRAFT, HOLDING, arrives, box, carded, sent, triaged  # noqa: F401
from test_scout_support import decide, fake_d1, scout_env  # noqa: F401

MORNING = "2026-10-27T08:05:00+08:00"  # a Tuesday, so yesterday is Monday 26 October


def usage(*rows: tuple[str, str, int, int]) -> list[dict]:
    return [{"app_slug": slug, "day": day, "opens": opens, "completions": done} for slug, day, opens, done in rows]


def d1_with(monkeypatch, rows: list[dict]) -> list:
    stub = d1_stub.D1(app_usage=rows)
    return fake_d1(monkeypatch, lambda request: _answer(stub, request))


def _answer(stub, request) -> httpx.Response:
    status, body = stub.answer(json.loads(request.content))
    return httpx.Response(status, json=body)


def at(monkeypatch, moment: str) -> None:
    monkeypatch.setenv("JURA_GROWTH_NOW", moment)


def usage_items(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM inbox_items WHERE source = ? ORDER BY id", (store.APP_USAGE,))


def warnings(conn) -> list[dict]:
    return db.rows(conn, "SELECT * FROM events WHERE kind = 'inbox.usage_unavailable'")


# --- W4 and S14 ----------------------------------------------------------------------------------------


def test_iw_w4_the_first_check_after_08_00_reports_yesterdays_opens_per_app(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    d1_with(monkeypatch, usage(("quote-builder", "2026-10-26", 3, 1), ("paynow-qr", "2026-10-26", 1, 0)))

    job.precheck(conn)

    [post] = [text for text in discord_double.contents(report.CHANNEL) if "App usage" in text]
    assert "Mon 26 Oct" in post and "quote-builder 3 opens, 1 completion" in post and "paynow-qr 1 open" in post
    assert "I-" in post


def test_iw_w4_once_a_day_however_many_checks_run(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    calls = d1_with(monkeypatch, usage(("quote-builder", "2026-10-26", 3, 1)))
    job.precheck(conn)
    at(monkeypatch, "2026-10-27T08:20:00+08:00")
    job.precheck(conn)
    at(monkeypatch, "2026-10-27T15:20:00+08:00")
    job.precheck(conn)
    assert len(usage_items(conn)) == 1
    assert len([call for call in calls if "app_usage" in call["sql"]]) == 1


@pytest.mark.parametrize("moment, reported", [("2026-10-27T07:45:00+08:00", 0), ("2026-10-27T07:59:00+08:00", 0), ("2026-10-27T08:00:00+08:00", 1)])
def test_iw_w4_not_before_08_00(conn, box, monkeypatch, discord_double, moment, reported):
    at(monkeypatch, moment)
    d1_with(monkeypatch, usage(("quote-builder", "2026-10-26", 3, 1)))
    signals.report_usage(conn)
    assert len(usage_items(conn)) == reported


def test_iw_w4_no_opens_no_message(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    d1_with(monkeypatch, usage(("quote-builder", "2026-10-26", 0, 0)))
    signals.report_usage(conn)
    assert usage_items(conn) == []


def test_iw_w4_today_isnt_reported_until_its_over(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    d1_with(monkeypatch, usage(("quote-builder", "2026-10-27", 9, 9)))
    signals.report_usage(conn)
    assert usage_items(conn) == []


def test_iw_w4_yesterday_is_singapores_yesterday(conn, box, monkeypatch, discord_double):
    """08:30 SGT on the 27th is 00:30 UTC on the 27th, and 16:30 UTC the day before would still be the 27th here."""
    at(monkeypatch, "2026-10-27T00:30:00+00:00")
    d1_with(monkeypatch, usage(("quote-builder", "2026-10-26", 2, 0)))
    signals.report_usage(conn)
    assert "Mon 26 Oct" in usage_items(conn)[0]["note"]


@pytest.mark.parametrize("how", ["unset", "down"])
def test_iw_w4_d1_unavailable_or_unset_is_one_warning_a_day_and_never_a_failure(conn, box, monkeypatch, discord_double, how):
    at(monkeypatch, MORNING)
    if how == "unset":
        for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "D1_DATABASE_ID"):
            monkeypatch.delenv(name, raising=False)
    else:
        fake_d1(monkeypatch, lambda request: httpx.Response(500, json={"success": False}))

    for moment in (MORNING, "2026-10-27T08:20:00+08:00", "2026-10-27T17:00:00+08:00"):
        at(monkeypatch, moment)
        signals.report_usage(conn)
    assert len(warnings(conn)) == 1
    assert discord_double.contents("alerts") == []
    assert store.with_prefix(conn, store.PROBLEM) == []

    at(monkeypatch, "2026-10-28T08:05:00+08:00")
    signals.report_usage(conn)
    assert len(warnings(conn)) == 2


def test_iw_s14_each_unreported_day_at_most_seven_on_one_message(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    d1_with(monkeypatch, usage(("a-app", "2026-10-26", 1, 0)))
    signals.report_usage(conn)

    at(monkeypatch, "2026-11-10T08:05:00+08:00")  # the Mac was off for two weeks
    days = [f"2026-11-{day:02d}" for day in range(1, 10)]
    d1_with(monkeypatch, usage(*[("a-app", day, 2, 1) for day in days], ("a-app", "2026-10-30", 5, 5)))
    signals.report_usage(conn)

    newest = usage_items(conn)[-1]
    assert len(usage_items(conn)) == 2
    for shown in ("Tue 3 Nov", "Mon 9 Nov"):
        assert shown in newest["note"]
    assert "Mon 2 Nov" not in newest["note"] and "Fri 30 Oct" not in newest["note"]


def test_iw_s14_a_day_already_reported_isnt_reported_again(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    rows = usage(("a-app", "2026-10-26", 1, 0), ("a-app", "2026-10-27", 2, 0))
    d1_with(monkeypatch, rows)
    signals.report_usage(conn)
    assert "Mon 26 Oct" in usage_items(conn)[0]["note"]

    at(monkeypatch, "2026-10-28T08:05:00+08:00")
    signals.report_usage(conn)
    newest = usage_items(conn)[-1]["note"]
    assert "Tue 27 Oct" in newest and "Mon 26 Oct" not in newest


def test_iw_s14_a_day_failed_on_comes_with_the_next_report(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    fake_d1(monkeypatch, lambda request: httpx.Response(500, json={"success": False}))
    signals.report_usage(conn)

    at(monkeypatch, "2026-10-28T08:05:00+08:00")
    d1_with(monkeypatch, usage(("a-app", "2026-10-26", 1, 0), ("a-app", "2026-10-27", 2, 0)))
    signals.report_usage(conn)
    [found] = usage_items(conn)
    assert "Mon 26 Oct" in found["note"] and "Tue 27 Oct" in found["note"]


def test_iw_r1_a_full_week_of_every_app_is_still_one_message(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    days = [f"2026-10-{day}" for day in range(20, 27)]
    rows = [(f"{'long-app-name-' * 3}{number}", day, 1000 + number, 1000) for number in range(40) for day in days]
    d1_with(monkeypatch, usage(*rows))
    job.precheck(conn)
    posts = [text for text in discord_double.contents(report.CHANNEL) if "App usage" in text]
    assert len(posts) == 1 and len(posts[0]) <= 2000


def test_iw_a13_a_bad_row_from_the_website_is_dropped_not_shown(conn, box, monkeypatch, discord_double):
    at(monkeypatch, MORNING)
    rows = usage(("good-app", "2026-10-26", 1, 0))
    rows += [{"app_slug": "<@&123> **bold**", "day": "2026-10-26", "opens": 5, "completions": 0},
             {"app_slug": "negative", "day": "2026-10-26", "opens": -5, "completions": 0},
             {"app_slug": "words", "day": "2026-10-26", "opens": "many", "completions": 0}]
    fake_d1(monkeypatch, rows)
    signals.report_usage(conn)
    note = usage_items(conn)[0]["note"]
    assert "good-app 1 open" in note and "<@" not in note and "negative" not in note and "many" not in note


# --- S12 -----------------------------------------------------------------------------------------------


def complaint(conn, domains=("acme.example",)) -> None:
    conn.execute("INSERT INTO events (ts, agent, level, kind, payload_json) VALUES (?, 'outreach', 'info', 'outreach.suppressed', ?)",
                 ("2026-10-26T16:45:00+08:00", json.dumps({"reason": "complaint", "source": "resend", "domains": list(domains), "message": 1})))


def test_iw_s12_a_spam_complaint_gets_a_high_report_with_no_draft(conn, box, monkeypatch, discord_double):
    signals.report_complaints(conn)  # the first check starts from now
    complaint(conn)
    conn.commit()
    job.precheck(conn)

    [post] = [text for text in discord_double.contents(report.CHANNEL) if "complaint" in text]
    assert "high priority" in post and "acme.example" in post
    [item] = db.rows(conn, "SELECT * FROM inbox_items WHERE source = ?", (store.EMAIL_SIGNAL,))
    assert item["priority"] == "high" and item["draft"] is None
    assert approvals.latest(conn, "email-reply", f"inbox_item:{item['id']}") is None


def test_iw_s12_a_complaint_is_reported_once(conn, box, monkeypatch, discord_double):
    signals.report_complaints(conn)  # the first check starts from now
    complaint(conn)
    conn.commit()
    signals.report_complaints(conn)
    signals.report_complaints(conn)
    assert len(db.rows(conn, "SELECT * FROM inbox_items WHERE source = ?", (store.EMAIL_SIGNAL,))) == 1
    complaint(conn, ("other.example",))
    conn.commit()
    signals.report_complaints(conn)
    assert len(db.rows(conn, "SELECT * FROM inbox_items WHERE source = ?", (store.EMAIL_SIGNAL,))) == 2


def test_iw_s12_a_click_or_a_bounce_gets_no_message_of_its_own(conn, box, monkeypatch, discord_double):
    conn.execute("INSERT INTO events (ts, agent, level, kind, payload_json) VALUES (?, 'outreach', 'info', 'outreach.suppressed', ?)",
                 ("2026-10-26T16:45:00+08:00", json.dumps({"reason": "bounce", "source": "resend", "domains": [], "message": 1})))
    conn.commit()
    signals.report_complaints(conn)
    assert db.rows(conn, "SELECT * FROM inbox_items WHERE source = ?", (store.EMAIL_SIGNAL,)) == []


# --- S7 ------------------------------------------------------------------------------------------------


def alerts(discord_double) -> list[str]:
    return discord_double.contents("alerts")


def test_iw_s7_a_high_item_goes_to_alerts_at_once_with_none_of_their_words(conn, box, sent, discord_double):
    item, record = carded(conn, box, raw_mail(body="Priya-Words-Here I want a refund"), draft=HOLDING, kind="complaint", priority="high")
    report.alert_high(conn)

    [line] = alerts(discord_double)
    assert store.label(item["id"]) in line and record.id in line and "clinic.example" in line
    assert "Priya-Words-Here" not in line and "Priya" not in line and "refund" not in line
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 1


def test_iw_s7_it_goes_again_at_24_hours_if_undecided(conn, box, sent, discord_double, monkeypatch):
    item, _ = carded(conn, box, draft=HOLDING, kind="complaint", priority="high")
    report.alert_high(conn)

    at(monkeypatch, "2026-10-27T09:59:00+08:00")
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 1

    at(monkeypatch, "2026-10-27T10:01:00+08:00")
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 2 and "still undecided" in alerts(discord_double)[1]
    at(monkeypatch, "2026-10-28T10:30:00+08:00")
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 2  # once more, and no more


@pytest.mark.parametrize("decision", ["skip", "approve"])
def test_iw_s7_decided_means_no_repeat(conn, box, sent, discord_double, monkeypatch, decision):
    _, record = carded(conn, box, draft=HOLDING, kind="complaint", priority="high")
    report.alert_high(conn)
    decide(conn, record, decision, monkeypatch)
    at(monkeypatch, "2026-10-27T11:00:00+08:00")
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 1


def test_iw_s7_a_refused_alert_goes_again_at_the_next_check(conn, box, sent, discord_double):
    carded(conn, box, draft=HOLDING, kind="complaint", priority="high")
    discord_double.mode = "500"
    report.alert_high(conn)
    assert db.scalar(conn, "SELECT alerted_at FROM inbox_items") is None
    discord_double.mode = "accept"
    discord_double.requests.clear()
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 1
    assert db.scalar(conn, "SELECT alerted_at FROM inbox_items") is not None


def test_iw_s7_a_normal_item_is_not_an_alert(conn, box, sent, discord_double):
    carded(conn, box)
    report.alert_high(conn)
    assert alerts(discord_double) == []


def test_iw_s7_the_precheck_and_a_run_send_it(conn, box, sent, discord_double):
    carded(conn, box, draft=HOLDING, kind="complaint", priority="high")
    job.precheck(conn)
    assert len(alerts(discord_double)) == 1


def test_iw_s7_a_conversation_is_one_alert(conn, box, sent, discord_double):
    first = arrives(conn, box, raw_mail(body="How much?"))
    second = arrives(conn, box, raw_mail(body="Refund me or else."))
    assert first["conversation"] == second["conversation"]
    triaged(conn, second, draft=HOLDING, kind="complaint", priority="high")
    report.alert_high(conn)
    assert len(alerts(discord_double)) == 1


# --- R5 ------------------------------------------------------------------------------------------------


def test_iw_r5_the_digest_counts_what_the_one_pager_counts(conn, box, monkeypatch, discord_double):
    """A person writing is a reaction. The engine's own messages aren't, on either page."""
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    arrives(conn, box, raw_mail())
    for source, key in ((store.RUN_MESSAGE, "a"), (store.APP_USAGE, "b"), (store.ENGINE_NOTE, "c"), (store.EMAIL_SIGNAL, "d")):
        store.record(conn, store.Reaction(source=source, key=key, conversation=key, state=store.REPORTED, note="fixed words"))
    assert store.day_counts(conn, "2026-10-26")["reactions"] == 1
    assert store.reactions_since(conn, "2026-10-26T00:00:00+08:00") == 1


def test_iw_r5_only_counts_reach_the_daily_summary_and_the_brief(conn, box, sent, discord_double):
    carded(conn, box, raw_mail(f"{sweep.PERSON} <{sweep.NAMED_ADDRESS}>", body=f"Call {sweep.PHONE}. {sweep.MARKER}", subject="Words in a subject"))
    other = arrives(conn, box, raw_mail("Other Person <other@else.example>", body="Thanks a lot", subject="Another"))
    triage.submit(conn, {"id": store.label(other["id"]), "class": "thanks"})
    report.report_due(conn)

    summary = digest.run(conn, "2026-10-26", post=False)

    text = (paths.data_dir() / "daily-summary.json").read_text()
    for value in (sweep.PERSON, sweep.NAMED_ADDRESS, sweep.PHONE, sweep.MARKER, "Words in a subject", "Other Person", DRAFT[:20], "clinic.example"):
        assert value not in text
    assert summary["figures"]["inbox_reactions"] == 2
    assert summary["figures"]["inbox_waiting"] == 1
    assert "1 waiting on you" in " ".join(summary["lines"])
    assert "reaction" in summary["brief_line"]
