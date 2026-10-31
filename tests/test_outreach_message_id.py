"""Outreach sends set and keep a `Message-ID` (inbox watch F2; code review 01, R-3), so an answer from
any address finds its lead, and it changes nothing an approved email says (ADR 0003).
Resend is `httpx.MockTransport` with assertions on the JSON request.
"""

from __future__ import annotations

import json

import httpx
import pytest

import approval_world as aw
from inbox_world import mailbox_env, raw_mail, trust_servers
from jura_growth import approvals, db
from jura_growth.agents.inbox import store
from jura_growth.agents.outreach import approval, compose, queue, replies
from jura_growth.agents.outreach import send as outreach_send
from test_scout_support import approve_due, at, fake_resend, live_ready, scout_env, seed  # noqa: F401


def bodies(requests: list) -> list[dict]:
    return [json.loads(request.content) for request in requests]


def _captured_outreach(conn, monkeypatch) -> tuple[dict, dict, list]:
    """One lead's first email, approved and sent live, with what Resend was asked."""
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    lead = seed(conn, 1)
    live_ready(monkeypatch)
    captured = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    assert outreach_send.send_due(conn).summary.startswith("sent message")
    return lead, json.loads(captured[0].content), captured


def test_iw_f2_an_outreach_send_sets_a_message_id_and_keeps_it_with_the_lead(conn, scout_env, monkeypatch):  # noqa: F811
    """IW-F2, code review 01 R-3."""
    lead, body, _ = _captured_outreach(conn, monkeypatch)

    message_id = body["headers"]["Message-ID"]
    assert replies.message_ids(message_id) == [message_id] and message_id.endswith("@hello.jurasolutions.sg>")
    assert store.lead_of_outgoing(conn, [message_id]) == lead["lead_id"]
    assert store.is_outgoing(conn, message_id), "kept in the claim, before Resend is called"


def test_iw_f2_the_header_changes_nothing_an_approved_email_says(conn, scout_env, monkeypatch):  # noqa: F811
    """Ticket: exactly the headers it had, plus one, and the same words. What the approval hash covers
    (`to`, subject, draft, frame) reads nothing from `resend_payload`, so it can't move with this header."""
    _, body, _ = _captured_outreach(conn, monkeypatch)
    message = db.rows(conn, "SELECT * FROM outreach_messages")[0]
    lead = db.rows(conn, "SELECT * FROM leads")[0]
    _, row = queue.recipient(conn, lead["id"])
    email = queue.build(conn, lead, row, subject=message["subject"], body=message["draft_body"])

    without = outreach_send.resend_payload(message, row, email)
    with_id = outreach_send.resend_payload(message, row, email, message_id="<x@y.example>")

    assert {k: v for k, v in with_id.items() if k != "headers"} == {k: v for k, v in without.items() if k != "headers"}
    assert with_id["headers"] == {**without["headers"], "Message-ID": "<x@y.example>"}
    assert set(without["headers"]) == {"List-Unsubscribe", "List-Unsubscribe-Post"}
    assert body["text"] == email.text and body["html"] == email.html and body["subject"] == email.subject
    assert "Message-ID" not in body["text"] and body["headers"]["Message-ID"] not in body["html"]


def test_iw_f2_a_live_outreach_approval_still_matches_and_is_claimed(conn, scout_env, monkeypatch):  # noqa: F811
    """Ticket: a request raised and approved goes out under its own hash, and none is superseded."""
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    lead = seed(conn, 1)
    live_ready(monkeypatch)
    captured = fake_resend(monkeypatch)
    approve_due(conn, monkeypatch)
    [record] = [approvals.Approval.from_row(r) for r in conn.execute("SELECT * FROM approvals WHERE kind = 'outreach-email'")]
    before = record.content_hash
    frame_before = compose.frame_fingerprint()
    message = db.rows(conn, "SELECT * FROM outreach_messages")[0]
    assert approval.content_hash_of(lead["email"], message["subject"], message["draft_body"]) == before

    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    outreach_send.send_due(conn)

    assert len(captured) == 1
    done = aw.get(conn, record.id)
    assert done.status == "approved" and done.used_at and done.content_hash == before
    assert compose.frame_fingerprint() == frame_before
    assert aw.events(conn, "approval.superseded") == []


def test_iw_f2_a_retry_of_an_outreach_send_carries_the_same_id(conn, scout_env, monkeypatch):  # noqa: F811
    """IW-F2: one action instance, one id, under its one key."""
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    seed(conn, 1)
    live_ready(monkeypatch)
    answers = iter([httpx.Response(500, json={"message": "down"}), httpx.Response(200, json={"id": "re-2"})])
    captured = fake_resend(monkeypatch, lambda request: next(answers))
    approve_due(conn, monkeypatch)
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    outreach_send.send_due(conn)
    at(monkeypatch, "2026-10-26T10:10:00+08:00")
    outreach_send.send_due(conn)

    first, second = bodies(captured)
    assert first["headers"]["Message-ID"] == second["headers"]["Message-ID"]


def test_iw_f2_someone_elsewhere_answering_outreach_is_that_leads_reply_at_1645(conn, scout_env, monkeypatch):  # noqa: F811
    """IW-F2, ticket: `_batch` uses the lookup too, so a paused inbox doesn't lose it."""
    lead, body, _ = _captured_outreach(conn, monkeypatch)
    mailbox_env(monkeypatch, [raw_mail("Their agency <helper@agency.example>", when="2026-10-26T11:00:00+08:00", body="Answering for them.",
                                       In_Reply_To=body["headers"]["Message-ID"])])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    found = replies.check(conn)

    assert [r["lead_id"] for r in found.replies] == [lead["lead_id"]]
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead["lead_id"],)) == "replied"


@pytest.mark.parametrize("sender, extra", [
    ("Mailer <mailer-daemon@agency.example>", {}),
    ("Their agency <helper@agency.example>", {"Authentication_Results": "mx.example.test; dkim=fail; spf=fail; dmarc=fail"}),
    ("Levi <levi@jurasolutions.sg>", {}),
], ids=["a bounce", "a stated failure", "our own copy"])
def test_iw_f2_naming_our_mail_isnt_enough_for_mail_no_person_there_wrote(conn, scout_env, monkeypatch, sender, extra):  # noqa: F811
    """IW-F2, code review 01 P-2 and S-4: a bounce quotes the id too, and so does our own BCC copy."""
    lead, body, _ = _captured_outreach(conn, monkeypatch)
    trust_servers(monkeypatch)
    mailbox_env(monkeypatch, [raw_mail(sender, when="2026-10-26T11:00:00+08:00", body="Delivery failed.",
                                       References=body["headers"]["Message-ID"], **extra)])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    found = replies.check(conn)

    assert found.replies == [] and db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead["lead_id"],)) != "replied"
