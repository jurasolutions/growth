"""`privacy.for_discord()`: the personal-data rule in MC §4.4, on top of `config.redact()`.

One row per planted item in dataset D3 (test strategy v3 §3), then the parts that make it work:
names learned from named addresses, values a process registers, and loading once.
"""

import pytest

from jura_growth import config, db, privacy

SOURCE = "https://example.com.sg/team"


@pytest.mark.parametrize(
    "text, expected",
    [
        # Masked: an address that names a person, with its source page kept beside it.
        (f"jane.tan@example.com.sg, listed on {SOURCE}", f"j***@example.com.sg, listed on {SOURCE}"),
        ("Contact: Jane.Tan@Example.com.sg", "Contact: J***@Example.com.sg"),
        ("mailto:jane.tan@example.com.sg", "mailto:j***@example.com.sg"),
        # Allowed: role addresses.
        ("info@example.com.sg", "info@example.com.sg"),
        ("hello@example.com.sg and enquiries@example.com.sg", "hello@example.com.sg and enquiries@example.com.sg"),
        ("sales2@example.com.sg", "sales2@example.com.sg"),
        # Never: phone numbers, in the shapes Singapore numbers are written.
        ("call +65 9123 4567 today", "call [phone removed] today"),
        ("call +6591234567 today", "call [phone removed] today"),
        ("office 6123 4567.", "office [phone removed]."),
        ("mobile (65) 8123-4567", "mobile [phone removed]"),
        ("hp: 9123-4567", "hp: [phone removed]"),
        ("whatsapp https://wa.me/6591234567", "whatsapp https://wa.me/[phone removed]"),
        ("abroad +44 20 7946 0958", "abroad [phone removed]"),
        # Never: Ting Yu's own contact details.
        ("Ting Yu: tingyu@jurasolutions.sg, +65 8765 4321", "Ting Yu: t***@jurasolutions.sg, [phone removed]"),
        # Never: anything from personal-finance/.
        (
            "ok\nread personal-finance/data/tally.db: balance\nnext",
            "ok\n[removed: personal finance]\nnext",
        ),
        # A prospect's personal name, learned from the named address in the same text.
        ("Hi Jane, (jane.tan@example.com.sg)", "Hi [name removed], (j***@example.com.sg)"),
        ("Jane Tan runs it: jane.tan@example.com.sg", "[name removed] runs it: j***@example.com.sg"),
        # Allowed and untouched.
        (
            "Example Pte Ltd (example.com.sg), logistics, score 78, run 2026-11-10T11:05:00+08:00, US$0.42",
            "Example Pte Ltd (example.com.sg), logistics, score 78, run 2026-11-10T11:05:00+08:00, US$0.42",
        ),
        ("https://www.facebook.com/groups/912345678901234/", "https://www.facebook.com/groups/912345678901234/"),
    ],
)
def test_for_discord(text, expected):
    assert privacy.for_discord(text) == expected


def test_it_masks_secrets_first(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY_OUTREACH", "re_uat_9Xq7Lm2Pz")
    config.reset_caches()

    assert privacy.for_discord("key re_uat_9Xq7Lm2Pz") == "key [redacted]"


def test_a_masked_address_keeps_its_first_letter_and_domain():
    assert privacy.masked_address("jane.tan@example.com.sg") == "j***@example.com.sg"
    assert privacy.masked_address("info@example.com.sg") == "info@example.com.sg"


def test_its_output_is_stable_when_masked_again():
    once = privacy.for_discord("Jane Tan, jane.tan@example.com.sg, +65 9123 4567")
    assert privacy.for_discord(once) == once


# --- what the process knows --------------------------------------------------------


def test_a_registered_reply_body_never_appears():
    privacy.never_show("Please take us off your list")

    assert privacy.for_discord("they wrote: please take us off your list.") == "they wrote: [removed]."


@pytest.mark.parametrize("body", ["550 5.1.1 jane.tan@example.com.sg: user unknown", "This message is spam"])
def test_registered_bounce_and_complaint_bodies_never_appear(body):
    privacy.never_show(body)

    assert body not in privacy.for_discord(f"details: {body}")


def test_a_name_from_a_known_named_address_is_masked_anywhere():
    privacy.remember_address("jane.tan@example.com.sg")

    assert privacy.for_discord("summary: wrote to Jane Tan at Example") == "summary: wrote to [name removed] at Example"
    assert privacy.for_discord("Hi Jane,") == "Hi [name removed],"


def test_names_are_not_masked_inside_a_source_url():
    privacy.remember_address("jane.tan@example.com.sg")

    assert privacy.for_discord("listed on https://example.com.sg/team/jane-tan") == (
        "listed on https://example.com.sg/team/jane-tan"
    )


def test_a_role_address_teaches_no_name():
    privacy.remember_address("sales@example.com.sg")

    assert privacy.for_discord("Sales went up") == "Sales went up"


def test_what_the_process_learned_is_forgotten_on_reset():
    privacy.never_show("Please take us off your list")
    privacy.remember_address("jane.tan@example.com.sg")

    config.reset_caches()

    assert privacy.for_discord("Jane: Please take us off your list") == "Jane: Please take us off your list"


def test_loading_for_masking_learns_named_contacts_from_the_plugins(conn):
    db.migrate(conn)
    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
        " status, created_at, updated_at) VALUES (1, 'Example Pte Ltd', 'Example', 'example.com.sg',"
        " 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', 'x', 'x')"
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        f" VALUES (1, 'jane.tan@example.com.sg', 'h', '{SOURCE}', 'named', 1, 'x', 'x')"
    )

    privacy.load_for_masking(conn)

    assert privacy.for_discord("Jane Tan replied") == "[name removed] replied"


def test_loading_for_masking_loads_keychain_values_too(conn, monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "keychain:jura-growth-uat")
    monkeypatch.setattr(config, "_keychain", lambda service: "kc_uat_44Lw")
    config.reset_caches()

    privacy.load_for_masking(conn)

    assert privacy.for_discord("value kc_uat_44Lw") == "value [redacted]"


def test_the_role_list_covers_every_role_the_scout_knows():
    from jura_growth.agents.scout import contact

    for local in (*contact.ENQUIRY_ROLES, *contact.OTHER_ROLES, *contact.NOT_FOR_ENQUIRIES):
        assert privacy.is_role_address(f"{local}@example.com.sg"), local
