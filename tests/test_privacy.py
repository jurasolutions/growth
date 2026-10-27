"""`privacy.for_discord()`: the personal-data rule in MC §4.4, on top of `config.redact()`.

One row per planted item in dataset D3 (test strategy v3 §3), then the parts that make it work:
names learned from named addresses, Jura's own copy, values a process registers, and what the
plug-ins share.
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
        ("https://x.sg/?email=jane.tan%40example.com.sg", "https://x.sg/?email=j***%40example.com.sg"),
        ("write to jane.tan&#64;example.com.sg", "write to j***&#64;example.com.sg"),
        ("_jane.tan@example.com.sg", "_***@example.com.sg"),
        # Allowed: role addresses and system senders.
        ("info@example.com.sg", "info@example.com.sg"),
        ("hello@example.com.sg and enquiries@example.com.sg", "hello@example.com.sg and enquiries@example.com.sg"),
        ("sales2@example.com.sg", "sales2@example.com.sg"),
        ("privacy@example.com.sg", "privacy@example.com.sg"),
        ("hrithik.tan@example.com.sg", "h***@example.com.sg"),
        # Never: phone numbers, in the shapes Singapore numbers are written.
        ("call +65 9123 4567 today", "call [phone removed] today"),
        ("call +6591234567 today", "call [phone removed] today"),
        ("office 6123 4567.", "office [phone removed]."),
        ("mobile (65) 8123-4567", "mobile [phone removed]"),
        ("hp: 9123-4567", "hp: [phone removed]"),
        ("call 9123.4567", "call [phone removed]"),
        ("call 91 23 45 67", "call [phone removed]"),
        ("call ９１２３ ４５６７", "call [phone removed]"),
        ("call 9123 45 67", "call [phone removed]"),
        ("call 9123–4567", "call [phone removed]"),
        ("call 9 1 2 3 4 5 6 7", "call [phone removed]"),
        ("whatsapp https://wa.me/6591234567", "whatsapp https://wa.me/[phone removed]"),
        ("abroad +44 20 7946 0958", "abroad [phone removed]"),
        # Never: anything from personal-finance/.
        ("ok\nread personal-finance/data/tally.db: balance\nnext", "ok\n[removed: personal finance]\nnext"),
        ("ok\nsee personalfinance notes\nnext", "ok\n[removed: personal finance]\nnext"),
        ("ok\nhttps://x/personal%2Dfinance/a\nnext", "ok\n[removed: personal finance]\nnext"),
        # A prospect's personal name, learned from the named address in the same text.
        ("Hi Jane, (jane.tan@example.com.sg)", "Hi [name removed], (j***@example.com.sg)"),
        ("Jane Tan runs it: jane.tan@example.com.sg", "[name removed] runs it: j***@example.com.sg"),
        # Allowed and untouched.
        (
            "Example Pte Ltd (example.com.sg), logistics, score 78, run 2026-11-10T11:05:00+08:00, US$0.42",
            "Example Pte Ltd (example.com.sg), logistics, score 78, run 2026-11-10T11:05:00+08:00, US$0.42",
        ),
        ("https://www.facebook.com/groups/912345678901234/", "https://www.facebook.com/groups/912345678901234/"),
        ("slots 9.30 10.30 11.30, 2026-10-25", "slots 9.30 10.30 11.30, 2026-10-25"),
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


def test_a_line_holding_the_finance_placeholder_is_still_dropped_whole():
    # Code review 03, S-Sec1: the placeholder never shelters the rest of its line.
    line = "[removed: personal finance] DBS 1234-5678-9012-3456 balance and [removed: personal finance]/data/tally.db"
    assert privacy.for_discord(f"ok\n{line}\nnext") == "ok\n[removed: personal finance]\nnext"


# --- names ----------------------------------------------------------------------------


def test_a_name_from_a_known_named_address_is_masked_anywhere():
    privacy.remember_address("jane.tan@example.com.sg")

    assert privacy.for_discord("summary: wrote to Jane Tan at Example") == "summary: wrote to [name removed] at Example"
    assert privacy.for_discord("Hi Jane,") == "Hi [name removed],"
    assert privacy.for_discord("JANE TAN called") == "[name removed] called"


@pytest.mark.parametrize(
    "address, text, expected",
    [
        ("li.na@example.com.sg", "Li Na runs ops", "[name removed] runs ops"),
        ("wei.ng@example.com.sg", "Wei Ng replied", "[name removed] replied"),
        ("ho.mei@example.com.sg", "ask Ho", "ask [name removed]"),
    ],
    ids=["li", "ng", "ho"],
)
def test_two_letter_surnames_are_masked(address, text, expected):
    privacy.remember_address(address)

    assert privacy.for_discord(text) == expected


def test_a_name_part_in_lower_case_is_an_ordinary_word():
    privacy.remember_address("mark.tan@example.com.sg")

    assert privacy.for_discord("mark it done, tan coloured") == "mark it done, tan coloured"
    assert privacy.for_discord("mark tan wrote") == "[name removed] wrote"


def test_a_known_company_name_is_never_masked_as_a_person():
    privacy.remember_address("mark.tan@tanholdings.sg")
    privacy.remember_company("Tan Holdings Pte Ltd")

    assert privacy.for_discord("New lead: Tan Holdings Pte Ltd, Mark Tan is the director") == (
        "New lead: Tan Holdings Pte Ltd, [name removed] is the director"
    )


def test_names_are_not_masked_inside_a_source_url():
    privacy.remember_address("jane.tan@example.com.sg")

    assert privacy.for_discord("listed on https://example.com.sg/team/jane-tan") == (
        "listed on https://example.com.sg/team/jane-tan"
    )


def test_a_role_address_teaches_no_name():
    privacy.remember_address("sales@example.com.sg")

    assert privacy.for_discord("Sales went up") == "Sales went up"


# --- Jura's own copy -------------------------------------------------------------------


def test_jura_s_own_copy_keeps_its_wording():
    privacy.remember_company("Tan Holdings Pte Ltd")
    privacy.never_show("Thank you for the note")
    post = "Your calendar, Tan Holdings Pte Ltd: thank you for the note."

    assert privacy.for_discord(f"Draft:\n{post}", own_copy=[post]) == f"Draft:\n{post}"


def test_jura_s_own_copy_still_loses_a_learned_first_name():
    # Review 02 round 2, blocking: "Hi Jane," went out in a shadow preview.
    privacy.remember_address("jane.tan@example.com.sg")
    draft = "Hi Jane,\n\nI read on the Example site..."

    assert privacy.for_discord(draft, own_copy=[draft]) == "Hi [name removed],\n\nI read on the Example site..."


@pytest.mark.parametrize("own", [True, False], ids=["own-copy", "other-text"])
def test_ting_yus_name_is_never_masked_as_a_prospect(own):
    # Review 02 round 2, S2: contacts ting.lim@ and yu.hui@ must not cost Ting Yu his name.
    privacy.remember_address("ting.lim@example.com.sg")
    privacy.remember_address("yu.hui@example.com.sg")
    privacy.remember_name("Ting Yu")
    text = "Thanks for reading. Ting Yu, Jura Solutions"

    assert privacy.for_discord(text, own_copy=[text] if own else []) == text
    assert privacy.for_discord("Ting Lim and Yu Hui replied") == "[name removed] and [name removed] replied"


def test_jura_s_own_copy_still_loses_secrets_phones_and_full_names(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY_OUTREACH", "re_uat_9Xq7Lm2Pz")
    config.reset_caches()
    privacy.remember_address("jane.tan@example.com.sg")
    draft = "Hi Jane Tan, key re_uat_9Xq7Lm2Pz, call 9123 4567, or jane.tan@example.com.sg"

    assert privacy.for_discord(draft, own_copy=[draft]) == (
        "Hi [name removed], key [redacted], call [phone removed], or j***@example.com.sg"
    )


# --- Ting Yu's own contact details -----------------------------------------------------


def test_ting_yus_address_is_removed_outside_jura_s_own_email():
    privacy.remember_owner("tingyu@jurasolutions.sg")

    assert privacy.for_discord("Ting Yu: tingyu@jurasolutions.sg, +65 8765 4321") == "Ting Yu: [removed], [phone removed]"


def test_ting_yus_sender_address_stays_in_a_preview_of_jura_s_own_email():
    privacy.remember_owner("tingyu@jurasolutions.sg")
    email = "From: Ting Yu <tingyu@jurasolutions.sg>\nHello Example team,"

    assert privacy.for_discord(f"Shadow:\n{email}", own_copy=[email]) == f"Shadow:\n{email}"


# --- what the process registers --------------------------------------------------------


def test_a_registered_reply_body_never_appears():
    privacy.never_show("Please take us off your list")

    assert privacy.for_discord("they wrote: please take us off your list.") == "they wrote: [removed]."
    assert privacy.for_discord("they wrote: PLEASE  take us off\nyour list") == "they wrote: [removed]"


@pytest.mark.parametrize("body", ["550 5.1.1 jane.tan@example.com.sg: user unknown", "This message is spam"])
def test_registered_bounce_and_complaint_bodies_never_appear(body):
    privacy.never_show(body)

    assert body not in privacy.for_discord(f"details: {body}")


def test_what_the_process_learned_is_forgotten_on_reset():
    privacy.never_show("Please take us off your list")
    privacy.remember_address("jane.tan@example.com.sg")
    privacy.remember_owner("tingyu@jurasolutions.sg")

    config.reset_caches()

    assert privacy.for_discord("Jane: Please take us off your list") == "Jane: Please take us off your list"
    assert privacy.for_discord("tingyu@jurasolutions.sg") == "t***@jurasolutions.sg"


# --- what the plug-ins share -----------------------------------------------------------


def contact(conn, email="jane.tan@example.com.sg", company="Example Pte Ltd"):
    conn.execute(
        "INSERT INTO leads (id, company, display_name, domain, website, industry, score, score_reasons, channel,"
        " status, created_at, updated_at) VALUES (1, ?, 'Example', 'example.com.sg',"
        " 'https://example.com.sg', 'logistics', 78, '[]', 'email', 'new', 'x', 'x')",
        (company,),
    )
    conn.execute(
        "INSERT INTO contacts (lead_id, email, email_hash, source_url, kind, mx_ok, verified_at, created_at)"
        f" VALUES (1, ?, 'h', '{SOURCE}', 'named', 1, 'x', 'x')",
        (email,),
    )


def test_learning_reads_named_contacts_and_companies_from_the_plugins(conn):
    contact(conn, "mark.tan@example.com.sg", "Tan Holdings Pte Ltd")

    privacy.learn(conn)

    assert privacy.for_discord("Mark Tan of Tan Holdings Pte Ltd") == "[name removed] of Tan Holdings Pte Ltd"


def test_learning_reads_ting_yus_sender_address_from_the_outreach_settings(conn):
    privacy.learn(conn)

    assert privacy.for_discord("from tingyu@jurasolutions.sg") == "from [removed]"


def test_learning_keeps_ting_yus_signature_name(conn):
    contact(conn, "yu.hui@example.com.sg")

    privacy.learn(conn)

    assert privacy.for_discord("Ting Yu, Jura Solutions; Yu Hui replied") == "Ting Yu, Jura Solutions; [name removed] replied"


def test_learning_without_a_connection_reads_the_database_itself(conn):
    # Review 02 round 2, N2: MC-03's lock-skip run update posts with conn=None.
    contact(conn)
    conn.commit()

    privacy.learn(None)

    assert privacy.for_discord("Jane Tan said no") == "[name removed] said no"


def test_learning_without_a_connection_or_a_database_is_quiet():
    privacy.learn(None)  # no growth.db yet

    assert privacy.for_discord("Jane Tan") == "Jane Tan"


def test_learning_never_asks_the_keychain(conn, monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "keychain:jura-growth-uat")
    looked_up = []
    monkeypatch.setattr(config, "_keychain", lambda service: looked_up.append(service) or "kc_uat_44Lw")
    config.reset_caches()

    privacy.learn(conn)

    assert looked_up == []


def test_loading_for_masking_loads_keychain_values_too(conn, monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "keychain:jura-growth-uat")
    monkeypatch.setattr(config, "_keychain", lambda service: "kc_uat_44Lw")
    config.reset_caches()

    privacy.load_for_masking(conn)

    assert privacy.for_discord("value kc_uat_44Lw") == "value [redacted]"


def test_a_plugin_whose_hook_fails_never_stops_a_message(conn, monkeypatch):
    from jura_growth.agents import scout

    def broken(c):
        raise KeyError("no such column")

    monkeypatch.setattr(scout, "privacy_terms", broken)
    privacy.remember_address("jane.tan@example.com.sg")

    privacy.learn(conn)

    assert privacy.for_discord("Jane Tan") == "[name removed]"


def test_db_migrate_is_enough_for_learning(conn):
    db.migrate(conn)
    privacy.learn(conn)  # no rows: nothing learned, nothing raised
    assert privacy.for_discord("Jane Tan") == "Jane Tan"
