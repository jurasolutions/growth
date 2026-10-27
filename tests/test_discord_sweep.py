"""The sweep over the posts that exist before mission control (AC-M11.1, AC-M12.1).

Datasets D2 and D3 are planted in a run's error, a run summary, an agent's text and a lead's
contact, then each existing builder posts through the Discord double. Later tickets run the
same `assert_clean` over the messages they add.
"""

import pytest
from click.testing import CliRunner

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import config, db, digest, runner, timeutil
from jura_growth.cli import cli
from sweep import (  # noqa: F401 - d2_secrets is a fixture
    MARKER,
    MASKED_ADDRESS,
    NAMED_ADDRESS,
    RESEND_KEY,
    SOURCE_PAGE,
    Planted,
    assert_clean,
    d2_secrets,
    outbox_dir,
    planted,
)


@pytest.fixture(autouse=True)
def _secrets(d2_secrets):
    """Every test here runs with the D2 env file and the Keychain double."""


@pytest.fixture
def failing_job(monkeypatch):
    """A command job, `boomer`, whose error carries everything planted."""
    base = config.settings()
    patched = dict(base)
    patched["jobs"] = {
        **base["jobs"],
        "boomer": {"agent": "boomer", "kind": "command", "command": ["status"], "schedule": {"daily": "06:00"}},
    }
    monkeypatch.setattr(config, "settings", lambda: patched)
    return "boomer"


def contact_lead(conn, *, industry: str = "logistics") -> int:
    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
        " status, created_at, updated_at) VALUES (233, 'Example Pte Ltd', 'Example', 'example.com.sg',"
        " 'https://example.com.sg', ?, 78, '[\"runs dispatch by hand\"]', 'email', 'new', ?, ?)",
        (industry, timeutil.stamp(), timeutil.stamp()),
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        " VALUES (233, ?, 'h', ?, 'named', 1, ?, ?)",
        (NAMED_ADDRESS, SOURCE_PAGE, timeutil.stamp(), timeutil.stamp()),
    )
    return 233


# --- the sweep proves itself ------------------------------------------------------


def test_the_sweep_fails_when_nothing_reached_the_double(discord_double):
    with pytest.raises(AssertionError, match="never received the marker"):
        assert_clean(discord_double, outbox_dir(), planted())


def test_the_sweep_finds_a_planted_secret_that_got_through(conn, discord_double, monkeypatch):
    monkeypatch.setattr(config, "redact", lambda value: value)  # what a broken redact() would let out

    from jura_growth import discord

    discord.post(conn, "alerts", f"{MARKER} key {RESEND_KEY[:9]}")
    with pytest.raises(AssertionError, match="a piece of a planted secret"):
        assert_clean(discord_double, outbox_dir(), Planted(secrets=(RESEND_KEY,)))


def test_the_sweep_finds_a_phone_number_however_it_is_spaced(conn, discord_double, monkeypatch):
    from jura_growth import discord, privacy

    monkeypatch.setattr(privacy, "for_discord", lambda text, **kwargs: text)
    discord.post(conn, "alerts", f"{MARKER} call 9123-4567")
    with pytest.raises(AssertionError, match="planted personal data"):
        assert_clean(discord_double, outbox_dir(), Planted(personal=("+65 9123 4567",)))


# --- existing posts ---------------------------------------------------------------


def test_a_failed_run_alert_is_clean(failing_job, discord_double, monkeypatch):
    with db.session() as c:
        contact_lead(c)
    # The error is cut at 500 characters by the runner: the cut falls inside the Resend key.
    head = f"{MARKER} {planted(secrets=False).text()} kc_uat_44Lw pw&<\"Zq81xT9 "
    message = head + "x" * (500 - len("RuntimeError: ") - len(head) - 9) + " " + RESEND_KEY + " tail"

    def boom(*args, **kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(runner, "_run_command", boom)
    assert runner.run(failing_job).status == "failed"

    assert discord_double.posts("alerts")
    assert_clean(discord_double, outbox_dir(), planted())


def test_an_alert_that_cannot_be_delivered_leaves_a_clean_outbox(conn, discord_double):
    from jura_growth import discord

    contact_lead(conn)
    discord_double.mode = "unreachable"
    result = discord.alert(conn, f"summary: {planted().text()}", agent="scout")

    assert not result.delivered
    assert outbox_dir().exists()
    assert_clean(discord_double, outbox_dir(), planted())


def test_the_daily_digest_is_clean(conn, discord_double):
    contact_lead(conn)
    stamp = timeutil.stamp()
    # Raw SQL, so log.finish_run's own redaction doesn't hide what the digest must mask.
    conn.execute(
        "INSERT INTO runs (agent, job, started_at, finished_at, status, summary, error) VALUES"
        " ('scout', 'scout-research', ?, ?, 'failed', ?, ?)",
        (stamp, stamp, planted().text(), planted().text()),
    )

    digest.run(conn)

    assert discord_double.posts("daily-digest")
    assert_clean(discord_double, outbox_dir(), planted())


def test_an_agents_post_from_the_cli_is_clean(conn, discord_double):
    contact_lead(conn)
    conn.commit()

    result = CliRunner().invoke(cli, ["discord", "post", "community", f"transcript says: {planted().text()}"])

    assert result.exit_code == 0, result.output
    assert_clean(discord_double, outbox_dir(), planted())


def test_a_new_lead_shows_a_named_address_masked_with_its_source_page(conn, discord_double):
    from jura_growth.agents.scout import leads

    lead = contact_lead(conn, industry=f"logistics {MARKER}")

    leads._post_lead(conn, lead)

    [content] = discord_double.contents("scout-leads")
    assert f"{MASKED_ADDRESS} (named address), listed on {SOURCE_PAGE}" in content
    assert_clean(discord_double, outbox_dir(), Planted(personal=(NAMED_ADDRESS,), expected=(MASKED_ADDRESS, SOURCE_PAGE)))


def test_a_post_masks_personal_data_even_when_its_builder_forgot(conn, discord_double):
    # Review 02, blocking finding 1: post() learns the named contacts itself.
    from jura_growth import discord

    contact_lead(conn)
    discord.post(conn, "outreach-sent", f"SHADOW draft: Hi Jane,\n{planted(secrets=False).text()}")

    assert "Hi [name removed]," in discord_double.contents("outreach-sent")[0]
    assert_clean(discord_double, outbox_dir(), planted(secrets=False))


def test_a_lead_whose_reason_names_its_contact_is_clean(conn, discord_double):
    # Review 02, blocking finding 1: the reviewer's lead reason.
    from jura_growth.agents.scout import leads

    lead = contact_lead(conn, industry=f"logistics {MARKER}")
    conn.execute(
        "UPDATE leads SET score_reasons = ? WHERE id = ?",
        ('["Jane Tan, the director, still keys in every invoice"]', lead),
    )

    leads._post_lead(conn, lead)

    [content] = discord_double.contents("scout-leads")
    assert "top reason: [name removed], the director, still keys in every invoice" in content
    assert_clean(discord_double, outbox_dir(), planted(secrets=False))


def test_an_attachment_is_clean(conn, discord_double, tmp_path):
    # Review 02, blocking finding 2: D2 and D3 planted in a text file and its name.
    from jura_growth import discord

    contact_lead(conn)
    config.load_secrets_for_masking()
    notes = tmp_path / f"{NAMED_ADDRESS} {RESEND_KEY[:9]} notes.txt"
    notes.write_text(planted().text() + "\n")

    discord.post(conn, "alerts", f"{MARKER} notes attached", files=[notes])
    discord_double.mode = "unreachable"
    discord.post(conn, "alerts", f"{MARKER} again, to the outbox", files=[notes])

    assert discord_double.posts("alerts")[0].files
    assert_clean(discord_double, outbox_dir(), planted())
