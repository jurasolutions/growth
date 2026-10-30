"""Go-live safety with config/scout.yaml exactly as it ships (live since 2026-10-31).

The other outreach tests start from a shadow baseline (`test_scout_support.TEST_BASELINE`), so
these are the ones that run the shipped file: live mode, the waived legal review, and
levi@jurasolutions.sg. The machine's own pre-conditions (the .env secrets, do-not-contact.csv
and D1) are faked, as `live_ready` does; Resend and D1 are doubles.

They check that going live changes nothing about the guards: every live send still needs a
claimed approval (MC §4.6 A6), the warm-up holds day 1 to 5 emails, and nothing goes out
outside the 09:30-16:30 business-day window.
"""

import json

import yaml

from jura_growth import config, db, paths
from jura_growth.agents.outreach import approval, send
from jura_growth.agents.scout import settings

from test_scout_support import (  # noqa: F401
    MONDAY_10AM,
    at,
    decide,
    fake_resend,
    live_ready,
    outreach_requests,
    scout_env,
    seed,
)

SHIPPED_SCOUT = paths.REPO_ROOT / "config" / "scout.yaml"


def shipped_and_ready(monkeypatch) -> list:
    """The shipped scout config, with the machine's pre-conditions met. Returns Resend's calls."""
    live_ready(monkeypatch)
    shipped = yaml.safe_load(SHIPPED_SCOUT.read_text(encoding="utf-8"))
    monkeypatch.setattr(config, "agent_config", lambda agent: shipped if agent == "scout" else {})
    return fake_resend(monkeypatch)


def status_of(conn, message_id):
    return db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (message_id,))


def test_the_shipped_config_is_live_once_the_machine_is_ready(monkeypatch):
    shipped_and_ready(monkeypatch)
    assert settings.mode() == "live"
    assert send.live_problems() == []


def test_no_live_email_goes_out_before_ting_yu_approves_it(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    sent = shipped_and_ready(monkeypatch)

    send.send_due(conn)  # nothing approved yet: it raises the request and sends nothing

    assert sent == []
    assert status_of(conn, message) == "queued"
    assert [a.status for a in outreach_requests(conn)] == ["pending"]
    assert approval.claimed(conn, message) is None


def test_a_skipped_email_is_never_sent(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    sent = shipped_and_ready(monkeypatch)
    send.send_due(conn)
    for request in outreach_requests(conn, "pending"):
        decide(conn, request, "skip", monkeypatch)

    at(monkeypatch, "2026-10-26T10:10:00+08:00")
    send.send_due(conn)

    assert sent == []
    assert status_of(conn, message) == "cancelled"  # a skip cancels the email
    assert approval.claimed(conn, message) is None


def test_an_approved_email_is_claimed_then_sent_from_levi(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    sent = shipped_and_ready(monkeypatch)
    send.send_due(conn)
    for request in outreach_requests(conn, "pending"):
        decide(conn, request, "approve", monkeypatch)

    at(monkeypatch, "2026-10-26T10:10:00+08:00")
    result = send.send_due(conn)

    assert result.summary.startswith(f"sent message {message}")
    assert len(sent) == 1
    assert approval.claimed(conn, message) is not None
    payload = json.loads(sent[0].content)
    assert payload["from"] == '"Ting Yu, Jura Solutions" <levi@jurasolutions.sg>'
    assert payload["reply_to"] == "info@jurasolutions.sg"


def test_warm_up_day_one_sends_five_even_when_more_are_approved(conn, monkeypatch):
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    for n in range(1, 9):
        seed(conn, n)
    sent = shipped_and_ready(monkeypatch)
    assert settings.per_day() == 20
    assert send.daily_cap(conn, "live") == (5, "warm-up day 1, 5 a day; daily cap 5")

    # Every 10-minute slot of the day, approving whatever is waiting before each one.
    for slot in range(43):  # 09:30 to 16:30
        hour, minute = divmod(9 * 60 + 30 + slot * 10, 60)
        at(monkeypatch, f"2026-10-26T{hour:02d}:{minute:02d}:00+08:00")
        approval.raise_due(conn)
        for request in outreach_requests(conn, "pending"):
            decide(conn, request, "approve", monkeypatch)
        send.send_due(conn)

    assert len(sent) == 5
    assert db.scalar(conn, "SELECT count(*) FROM outreach_messages WHERE status = 'sent' AND mode = 'live'") == 5
    assert send.quota(conn, "live")[0] == 0


def test_an_approved_email_waits_outside_the_window(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    sent = shipped_and_ready(monkeypatch)
    assert settings.window() == ((9, 30), (16, 30))
    send.send_due(conn)
    for request in outreach_requests(conn, "pending"):
        decide(conn, request, "approve", monkeypatch)

    for moment in (
        "2026-10-26T16:31:00+08:00",  # Monday, after the window
        "2026-10-27T09:29:00+08:00",  # Tuesday, before it
        "2026-10-31T10:00:00+08:00",  # Saturday
    ):
        at(monkeypatch, moment)
        result = send.send_due(conn)
        assert result.summary is None and "nothing to do" in result.note, (moment, result)

    assert sent == []
    assert status_of(conn, message) == "queued"
