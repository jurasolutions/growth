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

LONG = " And a long neutral sentence after it, so that length can't be what decides this at all."
SIGNATURE = "\nJane Tan\nDirector of Operations\nAcme Logistics Pte Ltd\n10 Anson Road\nacme.example\n"

# The one table: (subject, their own words, suppressed). The rule's own rows, then every case from
# code review 01's rounds under the closed rule. Anything not suppressed goes to triage.
OPT_OUT_TABLE = [
    # unsubscribe
    ("Re: A free tool", "unsubscribe", True),
    ("Re: A free tool", "UNSUBSCRIBE me please" + LONG, True),
    ("Unsubscribe", "Thanks", True),
    # remove me, remove us
    ("Re: A free tool", "Please remove me", True),
    ("Re: A free tool", "Please remove me from your list." + SIGNATURE, True),
    ("Re: A free tool", "Please remove us from your list.", True),
    ("Re: A free tool", "Hi Levi,\nThank you.\nPlease remove me from your list.", True),
    ("Re: A free tool", "please remove\nme", True),
    ("Remove me", "", True),
    ("RE: Fwd: Remove me", "Sent from my phone", True),
    # take me off, take us off
    ("Re: A free tool", "Please take me off your list." + SIGNATURE, True),
    ("Re: A free tool", "Please take us off." + SIGNATURE, True),
    # stop + emailing, contacting, messaging, writing to + anything
    ("Re: A free tool", "Please stop emailing me." + SIGNATURE, True),
    ("Re: A free tool", "Hi Levi,\nThanks,\nbut please stop emailing me.", True),
    ("Re: A free tool", "Please stop contacting us." + SIGNATURE, True),
    ("Re: A free tool", "Please stop emailing this address." + LONG, True),
    ("Re: A free tool", "Stop contacting my team." + LONG, True),
    ("Re: A free tool", "Please stop emailing our office." + LONG, True),
    ("Re: A free tool", "Stop messaging us." + LONG, True),
    ("Re: A free tool", "Please stop writing to me." + LONG, True),
    # The rule says "+ anything", so this suppresses too, and the report names the rule.
    ("Re: A free tool", "How do we stop emailing invoices back and forth?", True),
    # stop sending me, us, this, these, emails to
    ("Re: A free tool", "Stop sending me these." + LONG, True),
    ("Re: A free tool", "Please stop sending us mail." + LONG, True),
    ("Re: A free tool", "Stop sending these." + LONG, True),
    ("Re: A free tool", "Stop sending this." + LONG, True),
    ("Re: A free tool", "Stop sending emails to this address." + LONG, True),
    # do not or don't + email, contact, message + me, us, this address
    ("Re: A free tool", "Do not email me." + LONG, True),
    ("Re: A free tool", "Please don\u2019t email me again." + LONG, True),
    ("Re: A free tool", "Don\u2019t contact us." + LONG, True),
    ("Re: A free tool", "Don't message us." + LONG, True),
    ("Re: A free tool", "Please do not contact this address again." + LONG, True),
    ("Re: A free tool", "Please do not email me the PDF, send it on WhatsApp instead." + LONG, True),
    # opt me out, opt us out, opt out of your
    ("Re: A free tool", "Please opt me out." + LONG, True),
    ("Re: A free tool", "Opt us out." + LONG, True),
    ("Re: A free tool", "I would like to opt out of your emails." + LONG, True),
    ("Re: A free tool", "Customers should be able to opt out of your automated follow-ups." + LONG, True),
    # the whole message, ignoring a greeting and punctuation
    ("Re: A free tool", "STOP", True),
    ("Re: A free tool", "Stop.", True),
    ("Re: A free tool", "STOP?", True),
    ("Re: A free tool", "Please stop!", True),
    ("Re: A free tool", "Hi Levi,\n\nPlease stop.", True),
    ("Re: A free tool", "Hello, stop", True),
    ("Re: A free tool", "Dear Levi Ting:\nRemove.", True),
    ("Re: A free tool", "Good morning,\nunsubscribe", True),
    ("stop", " ".join(["word"] * 40), True),
    ("Stop?", "Sent from my phone", True),
    ("Re: stop", "", True),
    ("Please stop", "Tell me more", True),
    # A footer has their words in it too: no signature is cut, by decision.
    ("Re: A free tool", "Sure, tell me more.\n\nRegards\nJohn\nTo unsubscribe from our newsletter click here", True),
    # Nothing else suppresses: named in the decision.
    ("Re: A free tool", "We want to stop sending manual emails", False),
    ("Re: A free tool", "We want to stop sending manual emails to our suppliers." + LONG, False),
    ("Re: A free tool", "Can our clients opt out", False),
    ("Re: A free tool", "Can our clients opt out of the reminders?" + LONG, False),
    # Round 1's table: real questions.
    ("Re: A free tool", "How do we stop this happening?", False),
    ("Re: A free tool", "How do we stop retyping invoices?", False),
    ("Re: A free tool", "Can your tool stop these duplicate invoices?", False),
    ("Re: A free tool", "Can you remove my old invoices from the system?", False),
    ("Re: A free tool", "Do you stop sending reminders once an invoice is paid?", False),
    ("Re: A free tool", "Could you remove the second page?", False),
    ("Re: A free tool", "Can you stop by on Thursday?", False),
    ("How do we stop this happening?", "Tell me more", False),
    ("Re: Can your tool stop these duplicate invoices?", "Tell me more", False),
    # Round 1's table: opt-outs in other words, which go to triage now.
    ("Re: A free tool", "Can you stop?", False),
    ("Re: A free tool", "Could you please stop?", False),
    ("Re: A free tool", "Can you stop spamming me?", False),
    ("Re: A free tool", "Stop. Who gave you my address?", False),
    ("Re: A free tool", "Please stop. How did you get my email?", False),
    ("Re: A free tool", "How did you get my email? Stop.", False),
    ("Re: A free tool", "How did you get this address? Remove it please.", False),
    ("Re: A free tool", "Can you remove this address?", False),
    ("Re: A free tool", "Could you remove jane@acme.sg from your list?", False),
    ("Re: A free tool", "Please stop or I will report you. Understood?", False),
    ("Re: Can you stop?", "Tell me more", False),
    # Round 2's table: customers describing what they want automated.
    ("Re: A free tool", "We would love to stop sending reminder emails by hand." + LONG, False),
    ("Re: A free tool", "How do I stop emails going to spam?" + LONG, False),
    ("Re: A free tool", "Can you help us stop invoice emails bouncing?" + LONG, False),
    ("Re: A free tool", "We need to stop the marketing emails going out twice." + LONG, False),
    ("Re: A free tool", "With your tool we would have no more emails back and forth with suppliers." + LONG, False),
    ("Re: A free tool", "Can we remove our address from the quotation header?" + LONG, False),
    ("Re: A free tool", "Could you remove my name from the invoice template?" + LONG, False),
    # Round 2's table: opt-outs in other words, which go to triage now.
    ("Re: A free tool", "Hi,\n\nThanks!\n\nStop.", False),
    ("Re: A free tool", "Do not email again." + LONG, False),
    ("Re: A free tool", "Please remove from mailing list." + LONG, False),
    ("Re: A free tool", "Please stop." + SIGNATURE, False),
    # Ordinary mail.
    ("Re: A free tool", "Thanks, this is useful. Can we talk on Thursday?", False),
    ("Re: A free tool", "We would like to stop retyping invoices by hand every evening, so could we talk this week?", False),
    ("Re: A free tool", "Yes, tell me more.\n\nIf you are not the intended recipient, please notify the sender and "
                        "remove this email from your system.", False),
    ("Re: A free tool", "unstoppable removed", False),
    ("Re: A free tool", "Hi Levi,", False),
    ("Re: A free tool", "", False),
    ("Stop retyping invoices", "Tell me more", False),
]


@pytest.mark.parametrize("subject, words, suppressed", OPT_OUT_TABLE)
def test_iw_f1_the_one_closed_opt_out_rule(subject, words, suppressed):
    """IW-F1, IW-E2: the closed rule, by the conductor's decision in code review 01, round 3."""
    assert bool(replies.opt_out_reason(subject, words)) is suppressed


def test_iw_f1_a_reason_is_fixed_words_and_quotes_nothing_they_wrote():
    """IW-F1, IW-N7: it names the rule, and it sits in the report's frame, outside the quote."""
    assert replies.opt_out_reason("Re: hi", "Please remove me [x](https://evil.test)") == 'they wrote "remove me"'
    assert replies.opt_out_reason("Please stop", "") == 'the subject says "please stop"'


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
