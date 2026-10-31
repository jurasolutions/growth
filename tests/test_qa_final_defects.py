"""Regression tests for the defects QA filed at f0db1e5 (`reviews/qa-final.md`, tickets 05 to 09)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import publish_world as pw
from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import approvals, cards, config
from test_social import env  # noqa: F401 - a fixture


# --- 09: a typed approval of a refused card, in a new process ---------------------------------------

PICTURE = "Picture a small firm chasing its invoices.\n\nhttps://jurasolutions.sg\n"

# What one SSH call is: a new process that has learned nothing, deciding as Dispatch's call decides.
NEW_PROCESS_DECIDES = """
import json, sys
from jura_growth import approvals, db, privacy
from jura_growth.origin import Origin
assert privacy.for_discord("Picture this") == "Picture this", "this process already knows the name"
conn = db.connect()
answer = approvals.decide(conn, sys.argv[1], "approve", actor="discord:111", origin=Origin.ssh(), source_ref=None, args={})
conn.commit()
print(json.dumps({"answer": answer.answer, "text": answer.text}))
"""


def refused_card(conn, monkeypatch):
    """A post whose card the sweep refused for a name learned from a contact's address, on the
    shipped config, so a second process reads the same content."""
    from uat import seed

    pw.at(monkeypatch, pw.MORNING)
    _, request = pw.item(conn, "facebook", text=PICTURE)
    seed._lead(conn, 1, "Acme Pte Ltd", "acme.example.sg")
    seed._contact(conn, 1, "marta.picture@acme.example.sg", "named", "https://acme.example.sg/contact")
    conn.commit()
    cards.sweep(conn)
    assert approvals.get(conn, request.id).posted_at is None  # the sweep refused the card
    assert cards.refusal(conn, request.id)
    return request


def test_a_typed_approval_of_a_card_refused_for_a_learned_name_is_refused_in_a_new_process(conn, env, monkeypatch, discord_double):
    request = refused_card(conn, monkeypatch)
    conn.commit()
    monkeypatch.setenv("CONTROL_DISCORD_USER_ID", pw.CONTROL_ID)
    ran = subprocess.run([sys.executable, "-c", NEW_PROCESS_DECIDES, request.id], env=dict(os.environ),
                         capture_output=True, text=True, timeout=60)
    assert ran.returncode == 0, ran.stderr
    answer = json.loads(ran.stdout)
    assert answer["answer"] == approvals.REFUSED, answer["text"]
    assert "can't show the exact text" in answer["text"]

    conn.rollback()
    assert approvals.get(conn, request.id).status == approvals.PENDING
    pw.at(monkeypatch, pw.TEN)
    pw.run(conn, monkeypatch=monkeypatch)
    assert pw.next_item(conn).item is None
    assert approvals.get(conn, request.id).used_at is None


def test_a_card_the_sweep_refused_stays_refused_when_the_vocabulary_cannot_be_read(conn, env, monkeypatch, discord_double):
    """The sweep's refusal is on record, so a plug-in that fails to teach the name can't reopen it."""
    from jura_growth import privacy

    request = refused_card(conn, monkeypatch)
    conn.commit()
    privacy.reset()
    config.reset_caches()
    monkeypatch.setattr(privacy, "learn", lambda *a, **k: None)
    answer = pw.decide(conn, request, monkeypatch=monkeypatch)
    assert answer.answer == approvals.REFUSED, answer.text
    assert approvals.get(conn, request.id).status == approvals.PENDING


def test_a_refused_card_can_still_be_skipped(conn, env, monkeypatch, discord_double):
    request = refused_card(conn, monkeypatch)
    conn.commit()
    assert pw.decide(conn, request, "skip", monkeypatch=monkeypatch).answer == "recorded"
    assert approvals.get(conn, request.id).status == approvals.SKIPPED
