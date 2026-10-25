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


def test_the_double_records_attachments(conn, discord_double):
    image = paths.outputs_dir() / "grid.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(png())

    discord.post(conn, "alerts", "with a file", files=[image])

    [request] = discord_double.posts("alerts")
    assert request.content == "with a file"
    assert request.files == [("grid.png", png())]


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


def test_a_piece_from_the_middle_of_a_secret_is_masked(secrets):
    # Review 02, finding 8: "..uat_9Xq7Lm.." is 10 characters from the middle of the Resend key.
    assert config.redact(f"seen ..{RESEND_KEY[3:13]}.. here") == "seen ..[redacted].. here"


# --- the dedupe hash covers what the message says, not its masked form -----------


def test_posts_to_different_named_addresses_are_not_deduplicated(conn, discord_double):
    # Review 02, finding 3, and MC §4.4: the hash still covers the full address.
    first = discord.post(conn, "outreach-sent", "Shadow draft to jane.tan@example.com.sg")
    second = discord.post(conn, "outreach-sent", "Shadow draft to john.koh@example.com.sg")

    assert first.delivered and second.delivered
    assert discord_double.contents("outreach-sent") == [
        "Shadow draft to j***@example.com.sg",
        "Shadow draft to j***@example.com.sg",
    ]


# --- attachments ------------------------------------------------------------------


def test_a_text_attachment_and_its_name_are_masked(conn, discord_double, secrets, tmp_path):
    # Review 02, blocking finding 2.
    config.secret("UNSUBSCRIBE_SECRET")
    notes = tmp_path / "jane.tan@example.com.sg notes.txt"
    notes.write_text(f"key {RESEND_KEY}\nkeychain {KEYCHAIN_VALUE}\ncall +65 9123 4567\n")

    discord.post(conn, "alerts", "notes attached", files=[notes])

    [request] = discord_double.posts("alerts")
    [(name, body)] = request.files
    assert name == "j***@example.com.sg notes.txt"
    assert body.decode() == "key [redacted]\nkeychain [redacted]\ncall [phone removed]\n"


def test_an_outbox_record_holds_masked_file_names(conn, secrets, tmp_path):
    notes = tmp_path / "jane.tan@example.com.sg notes.txt"
    notes.write_text("plain notes\n")

    discord.post(conn, "alerts", "notes attached", files=[notes])

    saved = outbox_text()
    assert "jane.tan" not in saved and "j***@example.com.sg notes.txt" in saved


def test_a_file_that_cannot_be_inspected_is_held_back(conn, discord_double, tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7\x00\x01\x02 binary")

    discord.post(conn, "alerts", "with a pdf", files=[pdf])

    [request] = discord_double.posts("alerts")
    assert request.files == []
    assert "report.pdf was not attached" in request.content


def test_a_png_from_outside_the_engines_folders_is_held_back(conn, discord_double, tmp_path):
    image = tmp_path / "elsewhere" / "grid.png"
    image.parent.mkdir()
    image.write_bytes(png())

    discord.post(conn, "alerts", "with an image", files=[image])

    [request] = discord_double.posts("alerts")
    assert request.files == []
    assert "grid.png was not attached" in request.content


def test_an_engine_png_goes_out_without_its_text_chunks(conn, discord_double, secrets):
    image = paths.outputs_dir() / "social" / "grid.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(png(text=f"Comment\x00{RESEND_KEY}".encode()))

    discord.post(conn, "alerts", "with an image", files=[image])

    [request] = discord_double.posts("alerts")
    [(name, body)] = request.files
    assert name == "grid.png"
    assert body == png() and RESEND_KEY.encode() not in body


def png(text: bytes | None = None) -> bytes:
    """A one-pixel PNG, with a tEXt chunk if asked."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    extra = chunk(b"tEXt", text) if text is not None else b""
    pixels = chunk(b"IDAT", zlib.compress(b"\x00\x00"))
    return b"\x89PNG\r\n\x1a\n" + header + extra + pixels + chunk(b"IEND", b"")
