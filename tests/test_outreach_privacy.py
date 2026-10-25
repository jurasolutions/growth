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
        seeded[0]["email"], when="2026-10-26T14:00:00+08:00", body=f"{REPLY}.\nThanks", subject="Re: your note to us"
    )
    imap_env(monkeypatch, [message])
    at(monkeypatch, "2026-10-26T16:45:00+08:00")

    sync.run(conn)
    discord.alert(conn, f"{MARKER} parsing failed near: {REPLY.lower()} (Re: your note to us)", agent="outreach")

    assert discord_double.posts("outreach-replies")
    assert_clean(discord_double, outbox_dir(), Planted(personal=(REPLY, "Re: your note to us")))
