"""Each test PASSES when the reviewer's finding reproduces (it asserts the
current, unwanted behaviour). Nothing here touches jurasolutions/data, Discord,
Resend, Cloudflare or the network."""

import json
import sqlite3

from jura_growth import db, pause, paths, suppression
from jura_growth.agents.outreach import queue as queue_mod
from jura_growth.agents.outreach import send, sync
from jura_growth.agents.scout import dnc

from test_scout_support import (  # noqa: F401
    MONDAY_10AM,
    REGISTRY,
    add,
    at,
    configure,
    fake_resend,
    lead_data,
    live_ready,
    scout_env,
    seed,
)
from test_outreach_sync import D1, d1_row, live_sends
from jura_growth.agents.scout import contact
from test_scout_support import fake_d1


# F1: a complaint for an address that is already suppressed never pauses outreach.
def test_f1_complaint_after_unsubscribe_does_not_pause(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    email = seeded[0]["email"]
    # Gmail/Yahoo-style "unsubscribe" first (one-click POST), then the spam complaint webhook.
    table.rows.append(d1_row(email, "unsubscribe", source="unsubscribe-post", with_email=False, created="2026-10-26 11:00:00"))
    sync.run(conn)
    # D1's email_hash is the PRIMARY KEY (docs/scout.md:184), so the complaint can only arrive as an upsert of that row.
    table.rows[:] = [d1_row(email, "complaint", resend_id=seeded[0]["resend_id"], created="2026-10-26 12:00:00")]
    summary = sync.run(conn)
    assert "0 new suppressions" in summary
    assert pause.is_paused(conn, "outreach") is None  # PRD 5.7: any complaint must pause
    assert db.scalar(conn, "SELECT status FROM outreach_messages WHERE id = ?", (seeded[0]["message_id"],)) == "sent"


def test_f1b_complaint_after_reply_unsubscribe_does_not_pause(conn, monkeypatch):
    seeded, table = live_sends(conn, monkeypatch, 1)
    email = seeded[0]["email"]
    suppression.add(conn, email=email, reason="unsubscribe", source="reply")  # what replies._record does
    table.rows.append(d1_row(email, "complaint", resend_id=seeded[0]["resend_id"], created="2026-10-26 12:00:00"))
    sync.run(conn)
    assert pause.is_paused(conn, "outreach") is None


# F2: a past warmup_start skips the warm-up on the first live day.
def test_f2_warmup_start_in_the_past_lifts_day_one_cap_to_20(conn, monkeypatch):
    at(monkeypatch, MONDAY_10AM)
    configure(monkeypatch, send={"warmup_start": "2026-01-01"})
    assert send.daily_cap(conn, "live")[0] == 20  # PRD 5.3 / block 4: first live day at most 5


# F3: the model can call send-due back to back; nothing spaces live sends apart.
def test_f3_back_to_back_send_due_calls_both_send_live(conn, monkeypatch):
    at(monkeypatch, "2026-10-26T08:00:00+08:00")
    seed(conn, 1)
    seed(conn, 2)
    live_ready(monkeypatch)
    sent = fake_resend(monkeypatch)
    at(monkeypatch, MONDAY_10AM)
    assert send.send_due(conn).summary.startswith("sent message")
    assert send.send_due(conn).summary.startswith("sent message")  # same minute
    assert len(sent) == 2


# F4: an address on another company's domain, published on the lead's site, is accepted.
def test_f4_unrelated_domain_address_is_accepted(conn):
    data = lead_data(1, contact={"email": "info@someoneelse.sg", "source_url": "https://www.alderlogistics.sg/partners"})
    outcome = add(conn, data)
    assert outcome.status == "added" and outcome.contact["email"] == "info@someoneelse.sg"


# F4b: a directory not on the deny list passes as the "company website".
def test_f4b_unlisted_directory_passes_as_own_site(conn):
    data = lead_data(
        1,
        website="https://www.sgbizlistings.sg/alder-logistics",
        source_urls=["https://www.sgbizlistings.sg/alder-logistics"],
        contact={"email": "info@alderlogistics.sg", "source_url": "https://www.sgbizlistings.sg/alder-logistics"},
    )
    assert add(conn, data).status == "added"


# F5: a do-not-contact file without the header row silently matches nothing.
def test_f5_headerless_dnc_matches_nothing(conn):
    (paths.inputs_dir() / "do-not-contact.csv").write_text("Alder Logistics,,no\nZOLL Medical Singapore,,no\n")
    assert dnc.match("Alder Logistics Pte Ltd", ["alderlogistics.sg"]) is None
    assert add(conn, lead_data(1)).status == "added"


# F6: "stays in your browser" passes for an ai-tier tool.
def test_f6_browser_claim_passes_for_ai_tier_tool(conn):
    registry = [dict(r) for r in REGISTRY]
    for r in registry:
        if r["slug"] == "receipt-sorter":
            r["status"] = "live"
    (paths.site_repo() / "src" / "apps" / "registry.json").write_text(json.dumps(registry))
    lead = add(conn, lead_data(1, tool="receipt-sorter"))
    body = (
        "Hi there,\n\nI read on the Alder Logistics site that delivery orders are signed on paper and scanned back "
        "each evening. Our free receipt sorter reads a photo of a receipt and files it: jurasolutions.sg/apps/receipt-sorter\n\n"
        "It sits with our other small tools at jurasolutions.sg/apps. Nothing to install, and what you enter stays in your browser.\n\n"
        "If your team spends evenings retyping orders, reply and tell me how it works today."
    )
    result = queue_mod.queue(conn, lead.lead_id, {"subject": "A free receipt sorter for Alder Logistics", "body": body, "tool": "receipt-sorter"})
    assert result.status == "queued", result.reasons


# F7: a D1 created_at stored as an epoch integer is never selected by the sync query.
def test_f7_integer_created_at_never_syncs():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE suppression (email_hash TEXT PRIMARY KEY, created_at)")
    c.execute("INSERT INTO suppression VALUES ('a', 1793000000000)")  # Date.now() style
    c.execute("INSERT INTO suppression VALUES ('b', '2026-10-26 11:00:00')")  # datetime('now') style
    got = [r[0] for r in c.execute("SELECT email_hash FROM suppression WHERE created_at >= ?", ("2026-10-25",))]
    assert got == ["b"]
