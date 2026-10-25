"""A reply's body never reaches Discord (MC §4.4, AC-M12.1 for reply rows).

The reply check reads a reply's own words in memory, to look for "unsubscribe", and stores
none of it. It registers what it read with `privacy.never_show`, so nothing posted later in the
same process can carry it, even an error that quotes it.
"""

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import discord
from jura_growth.agents.outreach import sync
from sweep import MARKER, REPLY, Planted, assert_clean, outbox_dir
from test_outreach_sync import live_sends
from test_scout_support import at, imap_env, reply_message, scout_env  # noqa: F401 - scout_env is autouse


def test_a_reply_body_read_by_the_reply_check_never_reaches_discord(conn, monkeypatch, discord_double):
    seeded, _ = live_sends(conn, monkeypatch, 1)
    message = reply_message(
        seeded[0]["email"], when="2026-10-26T14:00:00+08:00", body=f"{REPLY}.\nBest regards", subject="Re: your note to us"
    )
    imap_env(monkeypatch, [message])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)
    discord.alert(conn, f"{MARKER} parsing failed near: {REPLY.lower()} (Re: your note to us)", agent="outreach")

    assert discord_double.posts("outreach-replies")
    assert_clean(discord_double, outbox_dir(), Planted(personal=(REPLY, "Re: your note to us")))


def test_a_short_reply_line_is_not_registered(conn, monkeypatch, discord_double):
    # Review 02, finding 9: a sign-off such as "Best regards" must not blank later posts.
    seeded, _ = live_sends(conn, monkeypatch, 1)
    imap_env(monkeypatch, [reply_message(seeded[0]["email"], when="2026-10-26T14:00:00+08:00", body="Interesting.\nBest regards")])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)
    discord.alert(conn, "Best regards from the digest", agent="outreach")

    assert discord_double.contents("alerts")[-1] == "**outreach**: Best regards from the digest"


def test_a_shadow_preview_that_names_the_contact_is_clean(conn, monkeypatch, discord_double):
    # Review 02, blocking finding 1: a shadow draft naming the contact, nothing seeded by hand.
    from jura_growth.agents.outreach import queue as queue_mod
    from jura_growth.agents.outreach import send
    from test_scout_support import MONDAY_10AM, body_for, seed

    at(monkeypatch, MONDAY_10AM)
    named = {"email": "jane.tan@alderlogistics.sg", "source_url": "https://www.alderlogistics.sg/contact", "enquiry_contact": True}
    seeded = seed(conn, 1, queue=False, contact=named)
    body = body_for("Alder Logistics").replace("Hi there,", "Hi there,\n\nJane Tan mentioned the paper orders.")
    queued = queue_mod.queue(
        conn, seeded["lead_id"], {"subject": "A free delivery order maker for Alder Logistics", "body": body, "tool": "delivery-order-maker"}
    )
    assert queued.status == "queued", queued.reasons

    assert send.send_due(conn).summary.startswith("SHADOW message")

    [content] = discord_double.contents("outreach-sent")
    assert "[name removed] mentioned the paper orders." in content
    assert "We've made a free delivery order maker" in content  # Jura's own words, as written
    assert_clean(discord_double, outbox_dir(), Planted(marker="**SHADOW** (not sent)", personal=("Jane Tan", named["email"])))
