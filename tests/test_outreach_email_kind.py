"""The `outreach-email` approval kind (MC §4.6, §5.7; ticket 06).

What its hash covers (AC-M8.9), and its two clocks (X2, X3): decide-by 16:30 on the next
business day, use-by 16:30 on the third business day after approval.
"""

import json
import time
from datetime import datetime

import pytest

from jura_growth import approvals, config, db
from jura_growth.agents.outreach import approval as outreach_approval
from jura_growth.agents.outreach import send

from test_scout_support import MONDAY_10AM, at, scout_env, seed  # noqa: F401

KIND = outreach_approval.KIND


def kind():
    return approvals.kinds()[KIND].kind


def hash_of(conn, message_id):
    content = kind().content(conn, outreach_approval.subject_of(message_id))
    return approvals.content_hash(content) if content is not None else None


def test_the_plugin_declares_the_outreach_email_kind():
    registered = approvals.kinds()[KIND]
    assert registered.agent == "outreach" and registered.kind.name == "outreach-email"


def test_a_subject_names_one_message():
    assert outreach_approval.subject_of(412) == "outreach_message:412"
    assert outreach_approval.message_id("outreach_message:412") == 412
    assert outreach_approval.message_id("outreach_message:4x") is None
    assert outreach_approval.message_id("publish_item:42") is None


# --- what the hash covers (AC-M8.9) -------------------------------------------------


def test_content_is_canonical_json_of_recipient_subject_and_draft(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    seeded = seed(conn, 1)
    content = kind().content(conn, outreach_approval.subject_of(seeded["message_id"]))
    message = db.one(conn, "SELECT subject, draft_body FROM outreach_messages WHERE id = ?", (seeded["message_id"],))
    assert json.loads(content) == {"to": "info@alderlogistics.sg", "subject": message["subject"], "body": message["draft_body"]}
    assert content == json.dumps(json.loads(content), sort_keys=True, ensure_ascii=False).encode("utf-8")
    assert "unsubscribe" not in content.decode("utf-8")


def test_a_new_unsubscribe_token_in_the_footer_still_matches(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    before = hash_of(conn, message)
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "a-new-secret")
    config.reset_caches()
    conn.execute("UPDATE outreach_messages SET body_text = body_text || ' token changed' WHERE id = ?", (message,))
    assert hash_of(conn, message) == before


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE contacts SET email = 'infx@alderlogistics.sg' WHERE lead_id = (SELECT lead_id FROM outreach_messages WHERE id = :id)",
        "UPDATE outreach_messages SET subject = subject || '.' WHERE id = :id",
        "UPDATE outreach_messages SET draft_body = replace(draft_body, 'Hi there', 'Hi therf') WHERE id = :id",
    ],
    ids=["recipient", "subject", "draft_body"],
)
def test_one_character_changed_in_recipient_subject_or_draft_doesnt_match(conn, monkeypatch, change):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    before = hash_of(conn, message)
    conn.execute(change, {"id": message})
    assert hash_of(conn, message) not in (None, before)


def test_the_hash_covers_the_exact_bytes_so_unicode_forms_differ(conn, monkeypatch):
    """Code review 06, Sec2: no normalisation, so different bytes never match."""
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    conn.execute("UPDATE outreach_messages SET subject = ? WHERE id = ?", ("Café quotes", message))
    composed = hash_of(conn, message)
    conn.execute("UPDATE outreach_messages SET subject = ? WHERE id = ?", ("Café quotes", message))
    assert hash_of(conn, message) != composed


@pytest.mark.parametrize("status", ["cancelled", "skipped", "dropped", "sent", "failed"])
def test_a_message_that_wont_go_out_is_gone(conn, monkeypatch, status):
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    conn.execute("UPDATE outreach_messages SET status = ? WHERE id = ?", (status, message))
    assert hash_of(conn, message) is None


def test_a_message_that_doesnt_exist_is_gone(conn):
    assert kind().content(conn, "outreach_message:99999") is None
    assert kind().content(conn, "not-a-subject") is None


def test_a_shadow_sent_message_keeps_its_content_so_its_approval_lapses_rather_than_supersedes(conn, monkeypatch):
    """AC-M8.10: after a switch back to shadow, an approved email shadow-sent keeps its
    approval unused until its use-by."""
    at(monkeypatch, MONDAY_10AM)
    message = seed(conn, 1)["message_id"]
    before = hash_of(conn, message)
    assert send.send_due(conn).summary.startswith("SHADOW")
    assert hash_of(conn, message) == before


# --- deadlines (X2, X3) -------------------------------------------------------------


def sgt(text):
    return datetime.fromisoformat(text)


DEADLINES = [
    # (now, decide_by, use_by). Sun 8 Nov is Deepavali, Mon 9 Nov its observed holiday.
    ("2026-11-06T09:12:00+08:00", "2026-11-10T16:30:00+08:00", "2026-11-12T16:30:00+08:00"),
    ("2026-11-10T10:00:00+08:00", "2026-11-11T16:30:00+08:00", "2026-11-13T16:30:00+08:00"),
    ("2026-11-12T23:59:00+08:00", "2026-11-13T16:30:00+08:00", "2026-11-17T16:30:00+08:00"),
    ("2026-11-07T11:00:00+08:00", "2026-11-10T16:30:00+08:00", "2026-11-12T16:30:00+08:00"),
    # 17:00 UTC on Thu 5 Nov is 01:00 SGT on Fri 6 Nov: the SGT day counts.
    ("2026-11-05T17:00:00+00:00", "2026-11-10T16:30:00+08:00", "2026-11-12T16:30:00+08:00"),
]


@pytest.fixture(params=["Asia/Singapore", "UTC", "America/New_York"])
def machine_tz(request, monkeypatch):
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize("now, decide_by, use_by", DEADLINES)
def test_deadlines_at_the_reference_dates_whatever_the_machine_time_zone(machine_tz, now, decide_by, use_by):
    found = kind().deadlines(None, "outreach_message:1", sgt(now))
    assert (found.decide_by, found.use_by) == (sgt(decide_by), sgt(use_by))
    assert found.decide_by.utcoffset() == sgt(decide_by).utcoffset()


def with_deadlines(monkeypatch, **values):
    patched = dict(config.settings())
    patched["approvals"] = {**(patched.get("approvals") or {}), "deadlines": {KIND: values}}
    monkeypatch.setattr(config, "settings", lambda: patched)


def test_a_configured_use_by_may_shorten_the_deadline(monkeypatch):
    with_deadlines(monkeypatch, use_by_business_days=1)
    found = kind().deadlines(None, "outreach_message:1", sgt("2026-11-10T10:00:00+08:00"))
    assert found.use_by == sgt("2026-11-11T16:30:00+08:00")


def test_a_configured_deadline_never_lengthens_or_drops_below_one_business_day(monkeypatch):
    with_deadlines(monkeypatch, decide_by_business_days=9, use_by_business_days=30)
    found = kind().deadlines(None, "outreach_message:1", sgt("2026-11-10T10:00:00+08:00"))
    assert (found.decide_by, found.use_by) == (sgt("2026-11-11T16:30:00+08:00"), sgt("2026-11-13T16:30:00+08:00"))
    with_deadlines(monkeypatch, decide_by_business_days=0, use_by_business_days=-2)
    found = kind().deadlines(None, "outreach_message:1", sgt("2026-11-10T10:00:00+08:00"))
    assert (found.decide_by, found.use_by) == (sgt("2026-11-11T16:30:00+08:00"), sgt("2026-11-11T16:30:00+08:00"))
