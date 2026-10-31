"""The reply rules `inbox-check` and the 16:45 check share (`outreach/replies.py`): who counts as
a lead's reply, and what counts as asking to be removed (IW-F1, IW-F2).
"""

from __future__ import annotations

import pytest

from jura_growth import db, suppression
from jura_growth.agents.outreach import replies, sync

from test_outreach_sync import live_sends
from test_scout_support import at, imap_env, reply_message, scout_env  # noqa: F401


def lead_status(conn, lead_id):
    return db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead_id,))


# --- F1: what counts as asking to be removed -------------------------------


@pytest.mark.parametrize(
    "subject, words, word",
    [
        ("Re: A free tool", "Please remove me", "remove"),
        ("Re: A free tool", "STOP", "stop"),
        ("Re: A free tool", "Please remove us from your list.", "remove"),
        ("Re: A free tool", "Could you remove me from your list?", "remove"),
        ("Re: A free tool", "How do I stop these emails?", "stop"),
        ("Re: A free tool", "unsubscribe", "unsubscribe"),
        ("Re: A free tool", " ".join(["word"] * 40) + " unsubscribe " + " ".join(["word"] * 40), "unsubscribe"),
        ("stop", " ".join(["word"] * 40), "stop"),
        ("Remove me", "", "remove"),
        ("Unsubscribe", "Thanks", "unsubscribe"),
    ],
)
def test_iw_f1_these_ask_to_be_removed(subject, words, word):
    """IW-F1: `unsubscribe` anywhere; `remove` or `stop` in the subject or in 12 words or fewer."""
    assert word in replies.opt_out_reason(subject, words)


@pytest.mark.parametrize(
    "subject, words",
    [
        ("Re: A free tool", "How do we stop retyping invoices?"),
        ("Re: A free tool", "Could you remove the second page?"),
        ("Re: A free tool", "We would like to stop retyping invoices by hand every evening, so could we talk this week?"),
        ("Re: A free tool", "Thanks, this is useful. Can we talk on Thursday?"),
        ("How do we stop retyping invoices?", "Tell me more"),
        ("Re: A free tool", ""),
        ("Re: A free tool", "unstoppable removed"),
    ],
)
def test_iw_f1_these_do_not(subject, words):
    """IW-F1: the functional table's real question must not suppress anyone, however short."""
    assert replies.opt_out_reason(subject, words) is None


def test_iw_f1_a_real_question_cancels_follow_ups_and_suppresses_nothing_at_16_45(conn, monkeypatch):
    """IW-F1: both checks use the one rule."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    imap_env(monkeypatch, [reply_message(lead["email"], when="2026-10-26T15:00:00+08:00",
                                         body="How do we stop retyping invoices?")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)

    assert suppression.is_suppressed(conn, lead["email"]) is None
    assert lead_status(conn, lead["lead_id"]) == "replied"


# --- F2: a colleague's reply counts -----------------------------------------


def test_iw_f2_a_colleague_on_the_leads_domain_is_the_leads_reply(conn, monkeypatch):
    """IW-F2, IW-W6: `info@acme` was emailed and `jane@acme` answers."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    colleague = f"jane@{lead['domain']}"
    imap_env(monkeypatch, [reply_message(colleague, when="2026-10-26T15:00:00+08:00", body="Yes, tell me more.")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    assert "1 reply detected" in sync.run(conn)

    assert lead_status(conn, lead["lead_id"]) == "replied"
    assert suppression.is_suppressed(conn, colleague) is None


def test_iw_f2_a_colleagues_opt_out_suppresses_that_sender_and_stops_the_lead(conn, monkeypatch):
    """IW-F2: it suppresses the person who asked, not the address we wrote to."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    colleague = f"jane@{lead['domain']}"
    imap_env(monkeypatch, [reply_message(colleague, when="2026-10-26T15:00:00+08:00", body="Please remove me")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)

    assert suppression.is_suppressed(conn, colleague) == "unsubscribe"
    assert suppression.is_suppressed(conn, lead["email"]) is None
    assert lead_status(conn, lead["lead_id"]) == "unsubscribed"


def test_iw_f2_free_mail_is_not_a_company_domain(conn, monkeypatch):
    """IW-F2: a lead that publishes a gmail address doesn't own gmail.com."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    conn.execute("UPDATE leads SET domain = 'gmail.com' WHERE id = ?", (lead["lead_id"],))
    imap_env(monkeypatch, [reply_message("stranger@gmail.com", when="2026-10-26T15:00:00+08:00", body="Hello there")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    assert "0 replies detected" in sync.run(conn)
    assert lead_status(conn, lead["lead_id"]) != "replied"


def test_iw_f2_a_message_older_than_the_first_email_is_not_a_reply(conn, monkeypatch):
    """IW-F2: the first-sent rule holds for a colleague too."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    imap_env(monkeypatch, [reply_message(f"jane@{lead['domain']}", when="2026-10-20T15:00:00+08:00", body="Earlier note")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    assert "0 replies detected" in sync.run(conn)


# --- the shared text reader --------------------------------------------------


def test_iw_a12_a_bad_charset_doesnt_stop_a_reply_being_read(conn, monkeypatch):
    """IW-A12: `_own_text` once raised LookupError on a charset Python doesn't know."""
    seeded, _ = live_sends(conn, monkeypatch, 1)
    lead = seeded[0]
    raw = (
        f"From: Someone <{lead['email']}>\nSubject: Re: A free tool\nDate: Mon, 26 Oct 2026 15:00:00 +0800\n"
        "Message-ID: <bad-charset@example.test>\nContent-Type: text/plain; charset=not-a-charset\n\n"
        "Please remove me\n"
    ).encode()
    imap_env(monkeypatch, [raw])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)

    assert suppression.is_suppressed(conn, lead["email"]) == "unsubscribe"
