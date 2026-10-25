"""`discord.post()` is the last line of defence (MC §4.3, AC-M11.3).

It masks secrets in its content before it computes the dedupe hash, using only the values the
process has already loaded: it never asks the Keychain itself.
"""

import json
import subprocess

import pytest

from discord_double import discord_double  # noqa: F401 - a fixture
from jura_growth import config, db, discord, paths, timeutil

RESEND_KEY = "re_uat_9Xq7Lm2Pz"
KEYCHAIN_VALUE = "kc_uat_44Lw"


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    """A temp env file with a plain secret and a `keychain:` reference, and a Keychain double.
    Returns the Keychain services looked up. Any real `security` call fails the test."""
    env = tmp_path / "uat.env"
    env.write_text(
        f"RESEND_API_KEY_OUTREACH={RESEND_KEY}\n"
        "UNSUBSCRIBE_SECRET=keychain:jura-growth-uat\n"
        "CONTROL_DISCORD_USER_ID=111\n"
    )
    env.chmod(0o600)
    monkeypatch.setenv("JURA_GROWTH_ENV_FILE", str(env))
    looked_up = []

    def keychain(service):
        looked_up.append(service)
        return KEYCHAIN_VALUE if service == "jura-growth-uat" else None

    def no_security(*args, **kwargs):
        raise AssertionError(f"a real subprocess ran: {args[0] if args else kwargs}")

    monkeypatch.setattr(config, "_keychain", keychain)
    monkeypatch.setattr(subprocess, "run", no_security)
    config.reset_caches()
    return looked_up


def outbox_text() -> str:
    path = paths.data_dir() / "discord-outbox" / f"{timeutil.today_str()}.jsonl"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- the double proves itself ------------------------------------------------


def test_the_double_records_what_discord_would_receive(conn, discord_double):
    result = discord.post(conn, "alerts", "marker-001 hello", username="Jura growth · test")

    assert result.delivered
    [request] = discord_double.posts("alerts")
    assert request.content == "marker-001 hello"
    assert request.allowed_mentions == {"parse": []}
    assert request.username == "Jura growth · test"
    assert request.url.startswith("https://discord.invalid/api/webhooks/")


def test_the_double_records_attachments(conn, discord_double, tmp_path):
    image = tmp_path / "grid.png"
    image.write_bytes(b"\x89PNG fake bytes")

    discord.post(conn, "alerts", "with a file", files=[image])

    [request] = discord_double.posts("alerts")
    assert request.content == "with a file"
    assert request.files == [("grid.png", b"\x89PNG fake bytes")]


@pytest.mark.parametrize("mode", ["500", "429", "unreachable"])
def test_a_refusing_double_sends_the_message_to_the_outbox(conn, discord_double, mode):
    discord_double.mode = mode

    result = discord.post(conn, "alerts", "refused message")

    assert not result.delivered and "saved to outbox" in result.reason
    assert discord_double.posts("alerts")  # it was tried
    assert "refused message" in outbox_text()


# --- AC-M11.3: redact before the hash, no Keychain lookup ------------------------


def test_post_masks_a_configured_secret_in_what_it_sends(conn, discord_double, secrets):
    discord.post(conn, "alerts", f"the key is {RESEND_KEY}, keep it safe")

    assert discord_double.contents("alerts") == ["the key is [redacted], keep it safe"]


def test_post_masks_a_keychain_value_the_process_already_read(conn, discord_double, secrets):
    assert config.secret("UNSUBSCRIBE_SECRET") == KEYCHAIN_VALUE

    discord.post(conn, "alerts", f"unsubscribe secret {KEYCHAIN_VALUE}")

    assert discord_double.contents("alerts") == ["unsubscribe secret [redacted]"]


def test_post_makes_no_keychain_lookup_of_its_own(conn, discord_double, secrets):
    discord.post(conn, "alerts", f"nothing secret here, {RESEND_KEY} aside")

    assert secrets == []
    assert discord_double.contents("alerts") == ["nothing secret here, [redacted] aside"]


def test_two_posts_differing_only_in_a_secret_dedupe_as_one(conn, discord_double, secrets):
    config.load_secrets_for_masking()

    first = discord.post(conn, "alerts", f"token {RESEND_KEY}")
    second = discord.post(conn, "alerts", f"token {KEYCHAIN_VALUE}")

    assert first.delivered
    assert not second.delivered and second.reason == "already posted today"
    assert discord_double.contents("alerts") == ["token [redacted]"]
    hashes = db.rows(conn, "SELECT content_hash FROM discord_posts")
    assert [h["content_hash"] for h in hashes] == [discord.content_hash("token [redacted]", [])]


def test_the_outbox_gets_the_masked_content(conn, secrets):
    discord.post(conn, "alerts", f"no webhook yet, key {RESEND_KEY}")

    saved = outbox_text()
    assert "no webhook yet, key [redacted]" in saved
    assert RESEND_KEY not in saved


# --- config.load_secrets_for_masking() ------------------------------------------


def test_loading_secrets_for_masking_masks_keychain_values_never_read(secrets):
    assert config.redact(f"seen in a transcript: {KEYCHAIN_VALUE}") == f"seen in a transcript: {KEYCHAIN_VALUE}"

    config.load_secrets_for_masking()

    assert secrets == ["jura-growth-uat"]
    assert config.redact(f"seen in a transcript: {KEYCHAIN_VALUE}") == "seen in a transcript: [redacted]"


def test_loading_secrets_for_masking_happens_once_per_process(secrets):
    config.load_secrets_for_masking()
    config.load_secrets_for_masking()

    assert secrets == ["jura-growth-uat"]


def test_a_keychain_reference_set_only_in_the_environment_is_loaded_too(secrets, monkeypatch):
    monkeypatch.setenv("SOME_EXTRA_TOKEN", "keychain:jura-growth-uat")
    config.reset_caches()

    config.load_secrets_for_masking()

    assert config.redact(KEYCHAIN_VALUE) == "[redacted]"


def test_the_payload_keeps_mentions_off(conn, discord_double):
    discord.post(conn, "alerts", "@everyone look <@123> <@&456>")

    [request] = discord_double.posts("alerts")
    assert request.allowed_mentions == {"parse": []}
    assert json.loads(json.dumps(request.payload()))["allowed_mentions"] == {"parse": []}


# --- what a secret turns into on its way to a message ----------------------------

AWKWARD = 'pw&<"Zq81xT9'  # D2: a value with characters that change when encoded


@pytest.fixture
def awkward(secrets, tmp_path, monkeypatch):
    env = tmp_path / "uat.env"
    env.write_text(env.read_text() + f"OUTREACH_IMAP_PASSWORD='{AWKWARD}'\n")
    config.reset_caches()


@pytest.mark.parametrize(
    "form",
    ["pw%26%3C%22Zq81xT9", "pw%26%3c%22Zq81xT9", "pw&amp;&lt;&quot;Zq81xT9", 'pw&<\\"Zq81xT9'],
    ids=["url-encoded", "url-encoded-lower-case", "html-escaped", "json-escaped"],
)
def test_an_encoded_secret_is_masked(awkward, form):
    assert config.redact(f"https://example.com/?p={form}&x=1") == "https://example.com/?p=[redacted]&x=1"


def test_a_secret_cut_short_at_the_end_of_a_message_is_masked(secrets):
    text = ("x" * 20 + " " + RESEND_KEY)[:30]  # "...x re_uat_9X": cut by a caller's [:n]
    assert config.redact(text).endswith(" [redacted]")


def test_a_secret_cut_short_in_the_middle_of_a_message_is_masked(secrets):
    line = f"- scout `scout-send`: {RESEND_KEY}"[:-4]  # the digest cuts each error at 200
    assert RESEND_KEY[:9] not in config.redact(f"{line}\n- next line")


def test_the_tail_of_a_secret_left_at_the_start_is_masked(secrets):
    assert config.redact(f"…{RESEND_KEY[5:]} and more") == "…[redacted] and more"


def test_a_short_piece_of_a_secret_is_left_alone(secrets):
    assert config.redact("re_uat is a prefix") == "re_uat is a prefix"


def test_masking_a_webhook_url_leaves_other_urls_alone(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_ALERTS", "https://discord.invalid/api/webhooks/7/tok3nVALUEabc123")
    config.reset_caches()

    text = "see https://example.com/page and https://discord.invalid/api/webhooks/7/tok3nVALUEa"
    assert config.redact(text) == "see https://example.com/page and https://discord.invalid/api/webhooks/7/[redacted]"
