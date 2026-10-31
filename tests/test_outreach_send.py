"""Blocks 3 and 4: the send run. Window, holidays, caps, warm-up, spacing,
per-company rule, suppression, shadow versus live, Resend errors."""

import json
import random
import threading
from datetime import timedelta

import httpx
import pytest

from jura_growth import db, paths, pause, runner, suppression, timeutil
from jura_growth.agents.outreach import compose, send, store
from jura_growth.agents.scout import registry

from test_scout_support import (  # noqa: F401
    MONDAY_10AM,
    approve_due,
    at,
    configure,
    d1_env,
    fake_d1,
    fake_resend,
    live_ready,
    outbox,
    scout_env,
    seed,
)


def status_of(conn, message_id):
    return db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message_id,))


def fake_sent(conn, n, *, mode, when, lead_id=None):
    """`n` past sends, one per made-up company (one first email per company is enforced)."""
    stamp = timeutil.stamp(when)
    for i in range(n):
        lead = dummy_lead(conn, f"history{i}-{mode}-{stamp[:10]}.sg")
        conn.execute(
            "INSERT INTO outreach_messages (lead_id, kind, subject, draft_body, body_text, body_html, mode, send_after, "
            "queued_at, sent_at, status) VALUES (?, 'first', 's', 'b', 't', 'h', ?, ?, ?, ?, ?)",
            (lead, mode, stamp[:10], stamp, stamp, "sent" if mode == "live" else "shadow"),
        )


def dummy_lead(conn, domain="history.sg"):
    now = timeutil.stamp()
    return conn.execute(
        "INSERT INTO leads (company, display_name, domain, website, industry, score, score_reasons, channel, status, "
        "created_at, updated_at) VALUES ('History', 'History', ?, 'https://history.sg', 'x', 70, '[]', 'none', 'no_contact', ?, ?)",
        (domain, now, now),
    ).lastrowid


# --- the window ------------------------------------------------------------


@pytest.mark.parametrize(
    "moment, why",
    [
        ("2026-10-26T09:29:00+08:00", "before the send window"),
        ("2026-10-26T16:31:00+08:00", "after the send window"),
        ("2026-10-31T11:00:00+08:00", "not a business day (weekend)"),
        ("2026-11-09T11:00:00+08:00", "not a business day (Deepavali"),
    ],
)
def test_outside_the_window_nothing_happens(conn, monkeypatch, moment, why):
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    message = seed(conn, 1)["message_id"]
    at(monkeypatch, moment)
    result = send.send_due(conn)
    assert result.summary is None and why in result.note
    assert status_of(conn, message) == "queued"


def test_window_edges_send(conn, monkeypatch):
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    first, second = seed(conn, 1)["message_id"], seed(conn, 2)["message_id"]
    at(monkeypatch, "2026-10-26T09:30:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW message")
    at(monkeypatch, "2026-10-26T16:30:00+08:00")
    assert send.send_due(conn).summary.startswith("SHADOW message")
    assert {status_of(conn, first), status_of(conn, second)} == {"shadow"}


def test_config_can_narrow_but_not_widen_the_window(monkeypatch):
    configure(monkeypatch, send={"window": {"start": "08:00", "end": "18:00"}})
    from jura_growth.agents.scout import settings

    assert settings.window() == ((9, 30), (16, 30))
    configure(monkeypatch, send={"window": {"start": "10:00", "end": "15:00"}})
    assert settings.window() == ((10, 0), (15, 0))


def test_unsent_mail_rolls_to_the_next_business_day(conn, monkeypatch):
    at(monkeypatch, "2026-10-30T16:00:00+08:00")  # Friday
    message = seed(conn, 1)["message_id"]
    at(monkeypatch, "2026-10-30T16:35:00+08:00")
    assert send.send_due(conn).summary is None
    at(monkeypatch, "2026-10-31T10:00:00+08:00")  # Saturday
    assert send.send_due(conn).summary is None
    at(monkeypatch, "2026-11-02T09:30:00+08:00")  # Monday
    assert send.send_due(conn).summary
    assert status_of(conn, message) == "shadow"


# --- shadow ----------------------------------------------------------------


def test_shadow_send_records_and_posts_without_resend(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    result = send.send_due(conn)  # resend_client is the blocked one: any call would fail the test
    assert result.summary == f"SHADOW message {seeded['message_id']} to alderlogistics.sg; suppression not synced from D1 (not configured; shadow mode carries on)"
    row = db.one(conn, "SELECT * FROM outreach_messages WHERE id = ?", (seeded["message_id"],))
    assert row["status"] == "shadow" and row["mode"] == "shadow" and row["sent_at"] and row["resend_id"] is None
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded["lead_id"],)) == "shadow_sent"
    assert db.scalar(conn, "SELECT count(*) FROM contacted_domains") == 0
    post = outbox("outreach-sent")[-1]["content"]
    assert post.startswith("**SHADOW** (not sent)") and "Subject: A free delivery order maker for Alder Logistics" in post
    assert db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'outreach.d1_missing'") == 1


def test_scout_send_job_is_quiet_when_nothing_to_do(isolated, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    assert runner.run("scout-send").status == "ok"
    with db.session() as c:
        assert db.scalar(c, "SELECT count(*) FROM runs") == 0
        seed(c, 1)
    outcome = runner.run("scout-send")
    assert outcome.status == "ok" and outcome.summary.startswith("SHADOW message 1")
    with db.session() as c:
        assert db.one(c, "SELECT agent, job, status FROM runs") == {"agent": "outreach", "job": "scout-send", "status": "ok"}


def test_paused_outreach_sends_nothing(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    pause.pause(conn, "outreach", "testing", notify=False)
    result = send.send_due(conn)
    assert result.summary is None and "paused" in result.note
    assert status_of(conn, message) == "queued"


def test_unknown_mode_refuses(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seed(conn, 1)
    configure(monkeypatch, mode="loud")
    assert "mode must be shadow or live" in send.send_due(conn).summary


# --- live gating -----------------------------------------------------------


LIVE_CHECKS = [
    ("mode", lambda mp: configure(mp, mode="shadow", legal_review_done=True, sending_domain="hello.jurasolutions.sg"), None),
    ("legal_review_done", lambda mp: configure(mp, mode="live", legal_review_done=False, sending_domain="hello.jurasolutions.sg"), "lawyer"),
    ("sending_domain", lambda mp: configure(mp, mode="live", legal_review_done=True, sending_domain=None), "open question 2"),
    ("sending_domain", lambda mp: configure(mp, mode="live", legal_review_done=True, sending_domain="gmail.com"), "not jurasolutions.sg"),
    ("RESEND_API_KEY_OUTREACH", lambda mp: mp.delenv("RESEND_API_KEY_OUTREACH"), "RESEND_API_KEY_OUTREACH"),
    ("UNSUBSCRIBE_SECRET", lambda mp: mp.delenv("UNSUBSCRIBE_SECRET"), "UNSUBSCRIBE_SECRET"),
    ("do-not-contact.csv", lambda mp: (paths.inputs_dir() / "do-not-contact.csv").unlink(), "do-not-contact.csv"),
    ("D1", lambda mp: mp.delenv("D1_DATABASE_ID"), "D1 is not configured"),
]


@pytest.mark.parametrize("name, breaker, words", LIVE_CHECKS[1:], ids=[c[0] + str(i) for i, c in enumerate(LIVE_CHECKS[1:])])
def test_live_mode_refuses_until_every_precondition_holds(conn, monkeypatch, name, breaker, words):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    breaker(monkeypatch)
    problems = send.live_problems()
    assert len(problems) == 1 and words in problems[0]
    result = send.send_due(conn)
    assert result.summary.startswith("live sending refused") and words in result.summary
    assert not sent and status_of(conn, message) == "queued"
    alerts = [p for p in outbox("alerts") if "Live sending refused" in p["content"]]
    assert len(alerts) == 1
    # refused again in the next slot: no second alert, no run summary
    assert send.send_due(conn).summary is None
    assert len([p for p in outbox("alerts") if "Live sending refused" in p["content"]]) == 1


def test_shadow_mode_never_calls_resend_even_when_ready(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seed(conn, 1)
    live_ready(monkeypatch)
    configure(monkeypatch, mode="shadow", legal_review_done=True, sending_domain="hello.jurasolutions.sg")
    sent = fake_resend(monkeypatch)
    assert send.send_due(conn).summary.startswith("SHADOW")
    assert sent == []


def test_live_send_calls_resend_with_the_right_email(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    d1_calls = live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    result = send.send_due(conn)
    assert result.summary == f"sent message {seeded['message_id']} to alderlogistics.sg"
    assert len(d1_calls) == 1  # suppression synced at the start of the send
    request = sent[0]
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_test_key_not_real_123456"
    assert request.headers["idempotency-key"] == f"jura-outreach-{seeded['message_id']}"
    payload = json.loads(request.content)
    assert payload["from"] == '"Levi Ting, Jura Solutions" <tingyu@hello.jurasolutions.sg>'  # local part from config
    assert payload["to"] == ["info@alderlogistics.sg"] and payload["reply_to"] == "levi@jurasolutions.sg"
    url = compose.unsubscribe_url("info@alderlogistics.sg", "test-secret")
    assert payload["headers"] == {
        "List-Unsubscribe": f"<{url}>, <mailto:levi@jurasolutions.sg?subject=unsubscribe>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    assert url in payload["text"] and "utm_source=outreach" in payload["html"] and "attachments" not in payload
    assert payload["html"].count("<img") == 1 and 'src="https://jurasolutions.sg/email/jura-mark-96.png"' in payload["html"]
    row = db.one(conn, "SELECT * FROM outreach_messages WHERE id = ?", (seeded["message_id"],))
    assert row["status"] == "sent" and row["mode"] == "live" and row["resend_id"] == "re-msg-1"
    assert row["body_text"] == payload["text"]
    assert db.scalar(conn, "SELECT count(*) FROM contacted_domains WHERE domain = 'alderlogistics.sg'") == 1
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded["lead_id"],)) == "contacted"
    assert store.get_state(conn, "first_live_send_at")
    post = outbox("outreach-sent")[-1]["content"]
    assert post.startswith("**Sent** message") and "First line: I read on the Alder Logistics site" in post


# --- caps ------------------------------------------------------------------


def run_slots(conn, monkeypatch, day="2026-10-26", chance=None, start="09:30", end="16:30"):
    """Call send-due at every 10-minute slot of a day; return the summaries."""
    if chance:
        monkeypatch.setattr(send, "chance", chance)
    results = []
    hour, minute = map(int, start.split(":"))
    end_h, end_m = map(int, end.split(":"))
    while (hour, minute) <= (end_h, end_m):
        at(monkeypatch, f"{day}T{hour:02d}:{minute:02d}:00+08:00")
        result = send.send_due(conn)
        if result.summary:
            results.append((f"{hour:02d}:{minute:02d}", result.summary))
        minute += 10
        if minute >= 60:
            hour, minute = hour + 1, minute - 60
    return results


def seed_many(conn, monkeypatch, count, day="2026-10-26"):
    at(monkeypatch, f"{day}T08:00:00+08:00")
    return [seed(conn, n)["message_id"] for n in range(1, count + 1)]


def test_one_email_per_run(conn, monkeypatch):
    seed_many(conn, monkeypatch, 3)
    at(monkeypatch, MONDAY_10AM)
    send.send_due(conn)
    assert db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'shadow'") == 1


def test_warm_up_caps_day_one_at_five(conn, monkeypatch):
    seed_many(conn, monkeypatch, 8)
    sends = run_slots(conn, monkeypatch)
    assert len(sends) == 5
    assert send.quota(conn, "shadow")[0] == 0


def test_per_day_config_lowers_and_cannot_raise(conn, monkeypatch):
    configure(monkeypatch, send={"per_day": 3})
    seed_many(conn, monkeypatch, 6)
    assert len(run_slots(conn, monkeypatch)) == 3
    configure(monkeypatch, send={"per_day": 500})
    from jura_growth.agents.scout import settings

    assert settings.per_day() == 20


def test_warm_up_schedule(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    assert send.daily_cap(conn, "live")[0] == 5
    store.set_state(conn, "first_live_send_at", timeutil.stamp(timeutil.now_sgt() - timedelta(days=6)))
    assert send.daily_cap(conn, "live")[0] == 5
    store.set_state(conn, "first_live_send_at", timeutil.stamp(timeutil.now_sgt() - timedelta(days=7)))
    assert send.daily_cap(conn, "live")[0] == 10
    store.set_state(conn, "first_live_send_at", timeutil.stamp(timeutil.now_sgt() - timedelta(days=14)))
    assert send.daily_cap(conn, "live")[0] == 20
    configure(monkeypatch, send={"warmup_start": "2026-10-20"})
    assert send.daily_cap(conn, "live")[0] == 5  # day 7 counted from the configured start


def test_warmup_start_in_the_past_keeps_the_first_live_day_at_five(conn, monkeypatch):
    # Config may only delay the warm-up, so a past warmup_start never lifts day one.
    at(monkeypatch, MONDAY_10AM)
    configure(monkeypatch, send={"warmup_start": "2026-01-01"})
    assert send.daily_cap(conn, "live")[0] == 5
    store.set_state(conn, "first_live_send_at", "2026-10-23T10:00:00+08:00")
    assert send.daily_cap(conn, "live") == (5, "warm-up day 4, 5 a day; daily cap 5")
    store.set_state(conn, "first_live_send_at", "2026-10-16T10:00:00+08:00")
    assert send.daily_cap(conn, "live")[0] == 10  # day 11, counted from the real first live send


def test_rolling_30_day_cap(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seed(conn, 1)
    store.set_state(conn, "first_shadow_send_at", "2026-01-01T10:00:00+08:00")
    fake_sent(conn, 600, mode="shadow", when=timeutil.now_sgt() - timedelta(days=29))
    left, binding = send.quota(conn, "shadow")
    assert left == 0 and "30-day" in binding
    assert send.send_due(conn).summary is None


def test_rolling_365_day_cap(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seed(conn, 1)
    store.set_state(conn, "first_shadow_send_at", "2025-01-01T10:00:00+08:00")
    configure(monkeypatch, send={"rolling_365_days": 40})
    fake_sent(conn, 40, mode="shadow", when=timeutil.now_sgt() - timedelta(days=200))
    left, binding = send.quota(conn, "shadow")
    assert left == 0 and "365-day" in binding
    assert send.send_due(conn).summary is None


def test_hard_caps_sit_below_the_bulk_thresholds():
    from jura_growth import caps

    assert caps.OUTREACH_PER_DAY < 100 and caps.OUTREACH_ROLLING_30_DAYS < 1000 and caps.OUTREACH_ROLLING_365_DAYS < 10000
    assert caps.OUTREACH_PER_SEND_RUN == 1


def test_shadow_counts_never_eat_into_live_caps(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    fake_sent(conn, 5, mode="shadow", when=timeutil.now_sgt())
    assert send.counts(conn, "live")["today"] == 0 and send.counts(conn, "shadow")["today"] == 5


# --- spacing ---------------------------------------------------------------


def test_slots_left():
    at_ = timeutil.parse
    assert send.slots_left(at_("2026-10-26T09:30:00+08:00")) == 43
    assert send.slots_left(at_("2026-10-26T16:20:00+08:00")) == 2
    assert send.slots_left(at_("2026-10-26T16:30:00+08:00")) == 1


def test_spacing_skips_a_slot_when_the_draw_is_high(conn, monkeypatch):
    seed_many(conn, monkeypatch, 3)
    monkeypatch.setattr(send, "chance", lambda: 0.99)
    at(monkeypatch, "2026-10-26T09:30:00+08:00")
    result = send.send_due(conn)
    assert result.summary is None and "spacing" in result.note
    at(monkeypatch, "2026-10-26T16:30:00+08:00")  # last slot: probability 1
    assert send.send_due(conn).summary


def test_back_to_back_send_due_calls_send_live_only_once(conn, monkeypatch):
    # Live sends stay 10 minutes apart however often send-due is called.
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    seed(conn, 1)
    seed(conn, 2)
    live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    at(monkeypatch, MONDAY_10AM)
    assert send.send_due(conn).summary.startswith("sent message")
    second = send.send_due(conn)  # same minute
    assert second.summary is None
    assert "0 minutes ago" in second.note and "at least 10 minutes apart" in second.note
    at(monkeypatch, "2026-10-26T10:09:00+08:00")
    assert send.send_due(conn).summary is None
    assert len(sent) == 1


def test_the_next_ten_minute_slot_still_sends_live(conn, monkeypatch):
    # The gap is counted in whole clock minutes, so the seconds a send takes
    # never block the next scheduled slot.
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    seed(conn, 1)
    seed(conn, 2)
    live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    at(monkeypatch, "2026-10-26T10:00:04+08:00")
    assert send.send_due(conn).summary.startswith("sent message")
    at(monkeypatch, "2026-10-26T10:10:01+08:00")
    assert send.send_due(conn).summary.startswith("sent message")
    assert len(sent) == 2


def test_shadow_sends_have_no_minimum_gap(conn, monkeypatch):
    seed_many(conn, monkeypatch, 2)
    at(monkeypatch, MONDAY_10AM)
    assert send.send_due(conn).summary.startswith("SHADOW")
    assert send.send_due(conn).summary.startswith("SHADOW")


def _parallel_send_due(monkeypatch, *, per_day=None):
    """Run B starts first and is held in its D1 sync while run A tries to send;
    then B finishes. Returns each run's result and the Resend requests."""
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    setup = db.connect()
    seed(setup, 1)
    seed(setup, 2)
    setup.close()
    live_ready(monkeypatch)
    if per_day is not None:
        configure(monkeypatch, mode="live", legal_review_done=True, sending_domain="hello.jurasolutions.sg", send={"per_day": per_day})
    approver = db.connect()
    approve_due(approver, monkeypatch)  # the approval fixture (AC-M8.12)
    approver.close()
    a_done, b_in_sync = threading.Event(), threading.Event()

    def d1(request):
        if threading.current_thread().name == "B":
            b_in_sync.set()
            a_done.wait(10)
        return httpx.Response(200, json={"success": True, "result": [{"results": []}]})

    fake_d1(monkeypatch, d1)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, MONDAY_10AM)
    results = {}

    def run(name):
        conn = db.connect()
        try:
            results[name] = send.send_due(conn)
        finally:
            conn.close()

    b = threading.Thread(target=run, args=("B",), name="B")
    b.start()
    assert b_in_sync.wait(10)
    run("A")
    a_done.set()
    b.join(10)
    return results, sent


def test_parallel_send_due_calls_send_live_only_once(monkeypatch):
    results, sent = _parallel_send_due(monkeypatch)
    assert len(sent) == 1
    assert results["B"].summary.startswith("sent message")
    assert results["A"].summary is None and "another send-due run is still going" in results["A"].note


def test_parallel_send_due_calls_stay_within_the_daily_cap(monkeypatch):
    results, sent = _parallel_send_due(monkeypatch, per_day=1)
    assert len(sent) == 1


@pytest.mark.parametrize("seed_value", [1, 7, 42, 2026])
def test_first_live_day_sends_at_most_five_spread_across_the_window(conn, monkeypatch, seed_value):
    seed_many(conn, monkeypatch, 9)
    live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    sends = run_slots(conn, monkeypatch, chance=random.Random(seed_value).random)
    assert len(sends) == 5 and len(sent) == 5
    times = [t for t, _ in sends]
    first = int(times[0][:2]) * 60 + int(times[0][3:])
    last = int(times[-1][:2]) * 60 + int(times[-1][3:])
    assert last - first >= 120, times  # spread, not bunched at 09:30
    assert len(set(times)) == 5


# --- per-message checks ----------------------------------------------------


def test_suppressed_address_is_skipped_at_send_time(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    suppression.add(conn, email_hash_value=suppression.email_hash(seeded["email"]), reason="unsubscribe", source="d1:unsubscribe-link")
    result = send.send_due(conn)
    assert "skipped" in result.summary and "suppressed" in result.summary
    assert status_of(conn, seeded["message_id"]) == "skipped"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded["lead_id"],)) == "suppressed"


def test_suppressed_domain_is_skipped_and_the_next_one_sends(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    first, second = seed(conn, 1), seed(conn, 2)
    suppression.add(conn, domain="alderlogistics.sg", reason="manual", source="test")
    result = send.send_due(conn)
    assert result.summary.startswith(f"SHADOW message {second['message_id']}") and "skipped message" in result.summary
    assert status_of(conn, first["message_id"]) == "skipped"


def test_do_not_contact_is_checked_at_send_time(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    (paths.inputs_dir() / "do-not-contact.csv").write_text("company,domain\nAlder Logistics,\n")
    assert "do-not-contact" in send.send_due(conn).summary
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (seeded["lead_id"],)) == "do_not_contact"


def test_contacted_domain_is_never_emailed_twice(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    store.record_contacted(conn, "alderlogistics.sg")
    assert "contacted before" in send.send_due(conn).summary
    assert status_of(conn, seeded["message_id"]) == "skipped"


def test_one_first_email_per_company(conn, monkeypatch):
    from jura_growth.agents.outreach import queue as queue_mod

    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    # shadow: the company keeps one active first email, so a second can't be queued
    assert send.send_due(conn).summary.startswith("SHADOW")
    with pytest.raises(queue_mod.QueueError, match="already has a first email"):
        queue_mod.queue(conn, seeded["lead_id"], {"subject": "Again", "body": "Hi", "tool": "quote-builder"})
    lead = db.one(conn, "SELECT * FROM leads WHERE id = ?", (seeded["lead_id"],))
    row = db.one(conn, "SELECT * FROM contacts WHERE lead_id = ?", (seeded["lead_id"],))
    assert queue_mod.blockers(conn, lead, row, "first") == []  # a shadow send contacted no one

    # live: after a real send, the per-company rule and contacted_domains both refuse a second
    other = seed(conn, 2)
    live_ready(monkeypatch)
    fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    assert send.send_due(conn).summary == f"sent message {other['message_id']} to birchlogistics.sg"
    lead = db.one(conn, "SELECT * FROM leads WHERE id = ?", (other["lead_id"],))
    row = db.one(conn, "SELECT * FROM contacts WHERE lead_id = ?", (other["lead_id"],))
    reasons = " ".join(queue_mod.blockers(conn, lead, row, "first"))
    assert "has had its first email" in reasons and "contacted before" in reasons


def test_brand_gate_runs_again_at_send_time(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    first, second = seed(conn, 1), seed(conn, 2)
    conn.execute("UPDATE outreach_messages SET draft_body = draft_body || ' Act now!' WHERE id = ?", (first["message_id"],))
    result = send.send_due(conn)
    assert "dropped at send time" in result.summary
    assert status_of(conn, first["message_id"]) == "dropped"
    assert any("failed the brand check at send time" in p["content"] for p in outbox("alerts"))
    assert pause.is_paused(conn, "outreach") is None
    conn.execute("UPDATE outreach_messages SET draft_body = draft_body || ' Hurry!' WHERE id = ?", (second["message_id"],))
    send.send_due(conn)
    assert "brand check in a row" in pause.is_paused(conn, "outreach")


def test_missing_registry_holds_the_queue(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    registry.path().unlink()
    result = send.send_due(conn)
    assert result.summary is None and "registry is missing" in result.note
    assert status_of(conn, message) == "queued"


# --- Resend errors and auto-pause ------------------------------------------


@pytest.mark.parametrize(
    "status, body, words",
    [
        (401, {"name": "invalid_api_key", "message": "API key is invalid"}, "auth or domain error"),
        (403, {"name": "validation_error", "message": "The hello.jurasolutions.sg domain is not verified"}, "auth or domain error"),
        (429, {"name": "daily_quota_exceeded", "message": "You have reached your daily email sending quota"}, "quota reached"),
        (422, {"name": "invalid_from_address", "message": "Invalid `from` field"}, "sending domain error"),
    ],
)
def test_resend_auth_quota_and_domain_errors_pause(conn, monkeypatch, status, body, words):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    live_ready(monkeypatch)
    fake_resend(monkeypatch, lambda request: httpx.Response(status, json={"statusCode": status, **body}))
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    result = send.send_due(conn)
    assert "outreach paused" in result.summary
    assert words in pause.is_paused(conn, "outreach")
    assert status_of(conn, message) == "queued"
    assert "re_test_key" not in (result.summary + json.dumps(outbox("alerts")))


def test_resend_server_errors_retry_then_fail(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    live_ready(monkeypatch)
    fake_resend(monkeypatch, lambda request: httpx.Response(500, json={"message": "internal"}))
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    assert "will retry" in send.send_due(conn).summary
    assert "will retry" in send.send_due(conn).summary
    assert status_of(conn, message) == "queued"
    assert "failed" in send.send_due(conn).summary
    assert status_of(conn, message) == "failed"
    assert pause.is_paused(conn, "outreach") is None


def test_resend_bad_request_fails_the_message(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    live_ready(monkeypatch)
    fake_resend(monkeypatch, lambda request: httpx.Response(400, json={"name": "validation_error", "message": "Invalid `to` field"}))
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    send.send_due(conn)
    assert status_of(conn, message) == "failed"


def test_failed_suppression_sync_pauses_before_sending(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    live_ready(monkeypatch)
    fake_d1(monkeypatch, lambda request: httpx.Response(500, json={"success": False, "errors": [{"message": "D1 down"}]}))
    sent = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)  # the approval fixture (AC-M8.12)
    result = send.send_due(conn)
    assert "suppression sync failed" in result.summary
    assert "suppression sync" in pause.is_paused(conn, "outreach")
    assert not sent and status_of(conn, message) == "queued"


def test_failed_sync_pauses_in_shadow_too_when_d1_is_configured(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seed(conn, 1)
    d1_env(monkeypatch)
    fake_d1(monkeypatch, lambda request: httpx.Response(200, json={"success": False, "errors": [{"message": "bad token"}]}))
    send.send_due(conn)
    assert "suppression sync" in pause.is_paused(conn, "outreach")


def test_status_command_lists_live_refusals(isolated, monkeypatch):
    from click.testing import CliRunner

    from jura_growth.cli import cli

    configure(monkeypatch, mode="shadow", legal_review_done=False, sending_domain=None)
    result = CliRunner().invoke(cli, ["outreach", "status"])
    assert result.exit_code == 0
    assert "mode            shadow" in result.output and "legal_review_done" in result.output
