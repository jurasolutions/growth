"""Block 2: the email, its fixed parts, the token, and the `email` channel rules."""

import json

import pytest
from click.testing import CliRunner

from jura_growth import brand_check, db, pause
from jura_growth.agents.outreach import compose, queue as queue_mod
from jura_growth.agents.scout import registry, settings
from jura_growth.cli import cli

from test_scout_support import add, lead_data, scout_env, seed  # noqa: F401

# Cross-checked with openssl:
#   echo -n info@acme-aircon.sg | shasum -a 256
#   echo -n <hash> | openssl dgst -sha256 -hmac jura-test-secret-2026 -binary | openssl base64 | tr '+/' '-_' | tr -d =
VECTOR_EMAIL = "  Info@Acme-Aircon.SG "
VECTOR_SECRET = "jura-test-secret-2026"
VECTOR_HASH = "3e7f8903444b297047849d51c51d0872460db95817c314d72ea201f381258ba8"
VECTOR_SIG = "EP0Tuk-Ys4HLJC8W75A3xVyxnI3_pNqXpJlcQGS38ns"
VECTOR_URL = f"https://jurasolutions.sg/unsubscribe?t={VECTOR_HASH}.{VECTOR_SIG}"


def test_unsubscribe_token_vector():
    assert compose.unsubscribe_token(VECTOR_EMAIL, VECTOR_SECRET) == f"{VECTOR_HASH}.{VECTOR_SIG}"
    assert compose.unsubscribe_url(VECTOR_EMAIL, VECTOR_SECRET) == VECTOR_URL
    assert "=" not in VECTOR_SIG


def test_unsubscribe_link_command(monkeypatch):
    assert CliRunner().invoke(cli, ["outreach", "unsubscribe-link", "info@acme-aircon.sg"]).exit_code != 0
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", VECTOR_SECRET)
    result = CliRunner().invoke(cli, ["outreach", "unsubscribe-link", "info@acme-aircon.sg"])
    assert result.exit_code == 0 and result.output.strip() == VECTOR_URL


def test_list_unsubscribe_headers():
    headers = compose.list_unsubscribe_headers(VECTOR_URL)
    assert headers["List-Unsubscribe"] == f"<{VECTOR_URL}>, <mailto:levi@jurasolutions.sg?subject=unsubscribe>"
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


# --- composing -------------------------------------------------------------


def make(body, *, subject="A free quote builder for Acme Aircon", company="Acme Aircon", secret=VECTOR_SECRET):
    return compose.compose(subject=subject, body=body, company=company, site="acmeaircon.sg", email="info@acmeaircon.sg", secret=secret)


REFERENCE = (
    "Hi there,\n\n"
    "I was looking at Acme Aircon's aircon servicing packages and saw that customers request quotes "
    "through a form and wait for a reply. We've made a free quote builder that turns a job into a "
    "clean PDF quote in a few minutes: jurasolutions.sg/apps/quote-builder\n\n"
    "It's one of a growing set of small tools at jurasolutions.sg/apps. No sign-up, and what you "
    "type stays in your browser.\n\n"
    "We're Jura Solutions, a small automation consultancy (jurasolutions.sg). If part of your week feels "
    "like copying the same details between systems, I'd be glad to hear about it on a 30-minute call."
)


def test_code_adds_signature_and_footer():
    email = make(REFERENCE + "\n\nLevi Ting\nJura Solutions")
    assert email.text.count(compose.SIGNATURE) == 1 and email.text.count("Levi Ting") == 1
    assert "You're receiving this because Acme Aircon lists this address for business enquiries on acmeaircon.sg." in email.text
    assert f'Unsubscribe here: {compose.unsubscribe_url("info@acmeaircon.sg", VECTOR_SECRET)}, or reply "unsubscribe".' in email.text
    assert "acmeaircon.sg" not in email.check_text  # the gate sees "its website"


def test_html_has_utm_on_jura_links_only_and_no_pixel():
    email = make(REFERENCE)
    assert email.html.lower().count("<img") == 1 and f'src="{settings.MARK_URL}"' in email.html
    assert 'href="https://jurasolutions.sg/apps/quote-builder?utm_source=outreach&amp;utm_medium=email&amp;utm_campaign=scout"' in email.html
    assert 'href="https://jurasolutions.sg/apps?utm_source=outreach' in email.html
    unsubscribe = compose.unsubscribe_url("info@acmeaircon.sg", VECTOR_SECRET)
    assert f'href="{unsubscribe}"' in email.html  # no UTM on the unsubscribe link
    assert "utm_" not in email.text  # the plain text stays readable
    assert 'href="https://acmeaircon.sg' not in email.html
    assert compose.with_utm("https://example.com/x") == "https://example.com/x"


def test_shadow_without_secret_still_composes():
    email = make(REFERENCE, secret="")
    assert compose.NO_SECRET_SIG in email.text


# --- ten generated-style emails that pass ----------------------------------

TOOLS = {"quote-builder", "invoice-checker", "timesheet-tidy", "delivery-order-maker", "booking-sheet"}

PASSING = [
    ("Acme Aircon", "A free quote builder for Acme Aircon", "quote-builder", ["Customers request quotes through a form"], REFERENCE),
    (
        "Lim Brothers Logistics",
        "A delivery order maker for Lim Brothers Logistics",
        "delivery-order-maker",
        ["Delivery orders signed on paper"],
        "Hi there,\n\nI read on the Lim Brothers Logistics site that delivery orders are signed on paper and scanned "
        "back to the office at the end of each day. We've made a free delivery order maker that fills in the order "
        "from a few details and keeps it as a PDF: jurasolutions.sg/apps/delivery-order-maker\n\nYou'll find it with "
        "our other small tools at jurasolutions.sg/apps. There's nothing to install, and what you enter stays in your "
        "browser.\n\nIf your team spends evenings retyping orders, that's the kind of work we help automate "
        "(jurasolutions.sg). I'd be glad to hear how it works today on a 30-minute call.",
    ),
    (
        "Bright Smile Dental",
        "A simple booking sheet for Bright Smile Dental",
        "booking-sheet",
        ["Appointments by phone only"],
        "Hello,\n\nBright Smile Dental's appointments page asks patients to call during opening hours to book or change "
        "a visit. We've built a free booking sheet that keeps the day's appointments in one tidy table you can print or "
        "share: jurasolutions.sg/apps/booking-sheet\n\nIt sits alongside our other free tools at jurasolutions.sg/apps, "
        "and nothing you type leaves your browser.\n\nWe help clinics in Singapore automate the admin side "
        "(jurasolutions.sg). If the front desk spends much of the day between the phone and the paper diary, I'd be "
        "glad to hear about it on a 30-minute call.",
    ),
    (
        "Tan & Co",
        "A free invoice checker for Tan & Co",
        "invoice-checker",
        ["Clients email receipts and invoices for bookkeeping"],
        "Hi there,\n\nTan & Co's services page says clients send their receipts and invoices by email each month for "
        "bookkeeping. Our free invoice checker reads an invoice and flags missing details before it goes into the "
        "books: jurasolutions.sg/apps/invoice-checker\n\nThere are a few more small tools at jurasolutions.sg/apps. "
        "No sign-up is needed.\n\nIf your team still keys in client documents by hand, I'd be glad to hear how "
        "month-end works for you on a 30-minute call. There's more about us at jurasolutions.sg.",
    ),
    (
        "Blue Harbour Events",
        "A timesheet tool for Blue Harbour Events crews",
        "timesheet-tidy",
        ["Crew hours logged on paper timesheets"],
        "Hi there,\n\nI saw on Blue Harbour Events' careers page that event crew log their hours on paper timesheets "
        "that someone types up after each show. Our free timesheet tool turns those hours into a clean summary for "
        "payroll: jurasolutions.sg/apps/timesheet-tidy\n\nYou can try it and the rest of our small tools at "
        "jurasolutions.sg/apps without signing up.\n\nThat's the kind of process we automate for teams in "
        "Singapore (jurasolutions.sg). If payroll week means chasing crew for their hours, a 30-minute call is a good "
        "place to start.",
    ),
    (
        "Sunrise Renovation",
        "A quote builder for Sunrise Renovation",
        "quote-builder",
        ["Homeowners send floor plans by WhatsApp for a quotation"],
        "Hi,\n\nSunrise Renovation's site invites homeowners to send floor plans by WhatsApp for a quotation. We've "
        "made a free quote builder that turns your rates and a job's details into a tidy PDF quote: "
        "jurasolutions.sg/apps/quote-builder\n\nIt's part of a small set of free tools at jurasolutions.sg/apps, and "
        "your rates stay in your browser.\n\nWe help Singapore firms automate that kind of repeat work, and there's "
        "more at jurasolutions.sg. If preparing quotations eats into your evenings, book a 30-minute call and tell me "
        "about it.",
    ),
    (
        "Golden Wok Group",
        "An order sheet for Golden Wok catering",
        "delivery-order-maker",
        ["Corporate catering orders by email"],
        "Hi there,\n\nGolden Wok's catering page asks corporate customers to email their orders, which your team then "
        "confirms by hand. We've built a free order tool that turns an order into a clear PDF confirmation: "
        "jurasolutions.sg/apps/delivery-order-maker\n\nIt's one of the free tools at jurasolutions.sg/apps. No sign-up, "
        "and nothing leaves your browser.\n\nWe help F&B teams in Singapore automate the rest (jurasolutions.sg). If "
        "orders arrive by email and WhatsApp and get copied into a spreadsheet, I'd be glad to hear how on a 30-minute "
        "call.",
    ),
    (
        "Peak Property",
        "A viewing booking sheet for Peak Property",
        "booking-sheet",
        ["Viewings arranged by phone"],
        "Hello,\n\nPeak Property's listings ask buyers to call an agent to arrange a viewing. Our free booking sheet "
        "keeps the week's viewings in one place, ready to print or share with the team: "
        "jurasolutions.sg/apps/booking-sheet\n\nYou'll find more small tools at jurasolutions.sg/apps. Everything you "
        "type stays in your browser.\n\nWe help agencies automate the admin around their listings, and you can read "
        "how at jurasolutions.sg. If arranging viewings means a lot of back and forth, I'd be glad to talk it through "
        "on a 30-minute call.",
    ),
    (
        "Bright Minds Learning Centre",
        "A timesheet tool for Bright Minds tutors",
        "timesheet-tidy",
        ["Part-time tutors paid by the lesson"],
        "Hi there,\n\nBright Minds Learning Centre's website lists part-time tutors who are paid by the lesson, with "
        "hours sent in on a form each month. Our free timesheet tool adds those hours up into a summary you can hand "
        "to payroll: jurasolutions.sg/apps/timesheet-tidy\n\nIt's one of a growing set of free tools at "
        "jurasolutions.sg/apps. There's no sign-up.\n\nThat's the sort of task we help education centres automate "
        "(jurasolutions.sg). If month-end means adding up tutor hours by hand, I'd be glad to hear how it works now on "
        "a 30-minute call.",
    ),
    (
        "Kim Seng Hardware",
        "A free delivery order maker for Kim Seng Hardware",
        "delivery-order-maker",
        ["Trade customers fax or email purchase orders"],
        "Hi there,\n\nKim Seng Hardware's ordering page asks trade customers to fax or email a purchase order before "
        "each delivery. We've made a free delivery order maker that turns an order into a clean PDF your drivers can "
        "carry: jurasolutions.sg/apps/delivery-order-maker\n\nThe rest of our small tools are at jurasolutions.sg/apps. "
        "No sign-up, and your data stays in your browser.\n\nWe help wholesalers in Singapore automate the step after "
        "that (jurasolutions.sg). If orders get retyped into your accounting system, a 30-minute call is a good start.",
    ),
]


def check(body, *, subject, company, tool, observations=(), kind="first", tools=TOOLS):
    email = compose.compose(subject=subject, body=body, company=company, site="example.sg", email="info@example.sg", secret=VECTOR_SECRET)
    return brand_check.check(
        email.check_text,
        subject=email.subject,
        channel_name="email",
        proper_nouns=[company],
        context={"company": company, "observations": list(observations), "tools": tools, "tool": tool, "kind": kind},
    )


@pytest.mark.parametrize("company, subject, tool, observations, body", PASSING, ids=[p[0] for p in PASSING])
def test_generated_emails_pass(company, subject, tool, observations, body):
    result = check(body, subject=subject, company=company, tool=tool, observations=observations)
    assert result.passed, result.reasons()
    assert compose.word_count(compose.tidy_draft(body)) < 150


def test_there_are_ten_passing_samples():
    assert len(PASSING) == 10 and len({p[0] for p in PASSING}) == 10


# --- and ones that fail ----------------------------------------------------


def issues(body=REFERENCE, *, subject="A free quote builder for Acme Aircon", tool="quote-builder", kind="first", observations=()):
    result = check(body, subject=subject, company="Acme Aircon", tool=tool, observations=observations, kind=kind)
    return result.reasons()


def has(reasons, fragment):
    return any(fragment in r for r in reasons)


def test_too_long_fails():
    long_body = REFERENCE + "\n\n" + " ".join(["We map the process first and keep the documentation with you."] * 7)
    assert has(issues(long_body), "keep it under 150")


def test_missing_apps_link_fails():
    body = REFERENCE.replace("small tools at jurasolutions.sg/apps.", "small tools we keep.")
    assert has(issues(body), "jurasolutions.sg/apps exactly once")


def test_two_tool_links_fail():
    body = REFERENCE + " Or try jurasolutions.sg/apps/invoice-checker"
    assert has(issues(body), "exactly one tool")


def test_tool_not_live_fails():
    body = REFERENCE.replace("apps/quote-builder", "apps/receipt-sorter")
    assert has(issues(body, tool=None), "not a live tool")


def test_tool_must_be_the_chosen_one():
    body = REFERENCE.replace("apps/quote-builder", "apps/invoice-checker")
    assert has(issues(body, tool="quote-builder"), "chosen tool")


def test_third_party_link_fails():
    body = REFERENCE.replace("No sign-up,", "Your form at acmeaircon.sg/quote works too. No sign-up,")
    assert has(issues(body), "[links]")


def test_other_jura_links_fail():
    body = REFERENCE + " Book a call at jurasolutions.sg/contact"
    assert has(issues(body), "Only jurasolutions.sg, the tool link")


@pytest.mark.parametrize("subject", ["Re: your quote form", "Fwd: quote builder", "FW: tools"])
def test_reply_or_forward_subject_fails(subject):
    assert has(issues(subject=subject), "No “Re:” or “Fwd:”")


def test_question_subject_fails():
    assert has(issues(subject="Tired of writing quotes by hand?"), "[question]")


def test_title_case_subject_fails():
    assert has(issues(subject="A Free Quote Builder For Acme Aircon"), "[sentence-case]")


def test_empty_subject_fails():
    assert has(issues(subject=""), "needs a subject")


def test_first_line_must_be_about_the_company():
    body = REFERENCE.replace(
        "I was looking at Acme Aircon's aircon servicing packages and saw that customers request quotes through a form and wait for a reply.",
        "We make small free tools for Singapore businesses.",
    )
    assert has(issues(body), "first line should be about this company")
    # an observation keyword from the company's own site is enough
    body2 = REFERENCE.replace("Acme Aircon's aircon servicing packages", "your aircon servicing packages")
    assert not has(issues(body2, observations=["Servicing packages listed with prices"]), "first line")


def test_follow_up_may_refer_back_and_skip_the_tool():
    body = (
        "Hi again,\n\nFollowing up on my note last week about quotes. If it helps, the free tools are all at "
        "jurasolutions.sg/apps, and there's more about us at jurasolutions.sg. I'd be glad to hear about your week "
        "on a 30-minute call."
    )
    assert issues(body, subject="A short follow-up on free tools", tool=None, kind="follow_up") == []


# --- a public job posting (scout PRD §5.2a point 5) ---------------------------

POSTING_SENTENCE = (
    "I was looking at Acme Aircon's aircon servicing packages and saw that customers request quotes "
    "through a form and wait for a reply."
)


def with_posting(sentence: str) -> str:
    return REFERENCE.replace(POSTING_SENTENCE, POSTING_SENTENCE + " " + sentence)


def test_a_factual_mention_of_a_public_job_posting_passes():
    body = with_posting("Your current job posting for an admin assistant lists preparing quotes among the duties.")
    assert issues(body) == []


def test_a_link_to_the_job_posting_fails():
    body = with_posting("I saw the admin assistant posting at mycareersfuture.gov.sg/job/admin-assistant-1a2b.")
    assert has(issues(body), "[links]")


@pytest.mark.parametrize(
    "guess",
    [
        "Your team must be stretched thin.",
        "It sounds like you're short-staffed.",
        "Your admin staff are probably overworked.",
        "I imagine your office is struggling to keep up.",
        "Your team seems understaffed at the moment.",
        "Your staff must be drowning in paperwork.",
        "It looks like your last admin left.",
        # Code review P3: guesses the first check missed.
        "Your team must be overwhelmed.",
        "Your admin team is stretched.",
        "Your team looks busy.",
        "You seem short of hands.",
        "I see your previous admin assistant has moved on.",
    ],
)
def test_a_guess_about_the_company_people_fails(guess):
    body = with_posting("You're hiring an admin assistant. " + guess)
    assert has(issues(body), "about the company's people")


def test_a_general_sentence_about_other_teams_is_not_a_guess():
    body = with_posting("Many teams struggle with paper delivery orders.")
    assert issues(body) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "Your posting, which Ms Tan Mei Ling manages, lists preparing quotes among the duties.",
        "Mr Lim's posting lists preparing quotes among the duties.",
        "I read that Mdm Siti Rahmah handles the quotes.",
        "Dr. Wong mentioned quotes on the posting.",
    ],
)
def test_a_person_named_in_the_email_fails(sentence):
    assert has(issues(with_posting(sentence)), "names a person")


@pytest.mark.parametrize(
    "sentence",
    [
        # Re-review R3 and R4: none of these is about a person, and a false failure can pause outreach.
        "Your posting asks for MS Excel skills to key in orders.",
        "The role keeps records in Google Sheets, Xero and QuickBooks.",
        "If you're busy, a reply next week is fine.",
        "It frees your team for the busy season.",
        "If your team is stretched at month-end, the tool helps.",
        "When you're swamped with orders, it still takes a minute.",
    ],
)
def test_products_and_polite_phrasing_pass(sentence):
    assert issues(with_posting(sentence)) == []


def test_the_company_own_name_is_not_a_person():
    body = REFERENCE.replace("Acme Aircon", "Dr Aircon")
    result = check(body, subject="A free quote builder for Dr Aircon", company="Dr Aircon", tool="quote-builder")
    assert result.passed, result.reasons()


def test_the_sender_may_use_their_own_name():
    """The sender is Levi Ting since the designed email (§5.6a)."""
    assert not has(issues(with_posting("I'm Mr Levi Ting at Jura Solutions.")), "names a person")


def test_body_must_not_carry_its_own_footer():
    body = REFERENCE + "\n\nTo unsubscribe, reply stop."
    assert has(issues(body), "Leave the unsubscribe")


def test_core_rules_still_apply():
    assert has(issues(REFERENCE.replace("on a 30-minute call.", "on a 30-minute call!")), "[exclamation]")
    assert has(issues(REFERENCE.replace("small tools", "seamless tools")), "[buzzword]")
    assert has(issues(REFERENCE + " We've helped 40 companies do this."), "[numbers]")


def test_missing_required_parts_fail_when_checked_raw():
    result = brand_check.check(REFERENCE, subject="A free quote builder", channel_name="email", context={"company": "Acme Aircon"})
    assert has(result.reasons(), "Missing the signature")
    no_footer = REFERENCE + "\n\n" + compose.SIGNATURE + "\n\nThanks."
    reasons = brand_check.check(no_footer, subject="A free quote builder", channel_name="email", context={"company": "Acme Aircon", "tools": TOOLS}).reasons()
    assert has(reasons, "receiving this") and has(reasons, "unsubscribe link") and has(reasons, 'or reply "unsubscribe"')


def test_email_channel_is_registered():
    channel = brand_check.channel("email")
    assert channel.allow_sources is False and channel.check is compose.check_email


# --- queueing --------------------------------------------------------------


def test_queue_runs_the_gate_once_then_drops(conn):
    lead = add(conn, lead_data(1))
    bad = {"subject": "Re: orders", "body": "Hi there,\n\nWe make tools!", "tool": "delivery-order-maker"}
    first = queue_mod.queue(conn, lead.lead_id, bad)
    assert first.status == "retry" and first.reasons
    second = queue_mod.queue(conn, lead.lead_id, bad)
    assert second.status == "dropped"
    row = db.one(conn, "SELECT status, kind FROM outreach_messages")
    assert row == {"status": "dropped", "kind": "first"}
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead.lead_id,)) == "qa_dropped"
    # two failures in a row pause outreach (PRD §5.7)
    assert "brand check in a row" in pause.is_paused(conn, "outreach")


def test_queue_pass_after_one_fix(conn):
    from test_scout_support import body_for

    lead = add(conn, lead_data(1))
    assert queue_mod.queue(conn, lead.lead_id, {"subject": "Re: orders", "body": body_for("Alder Logistics"), "tool": "delivery-order-maker"}).status == "retry"
    fixed = queue_mod.queue(conn, lead.lead_id, {"subject": "A free delivery order maker for Alder Logistics", "body": body_for("Alder Logistics"), "tool": "delivery-order-maker"})
    assert fixed.status == "queued"
    assert pause.is_paused(conn, "outreach") is None
    message = db.one(conn, "SELECT * FROM outreach_messages WHERE id = ?", (fixed.message_id,))
    from jura_growth import timeutil

    assert message["status"] == "queued" and message["send_after"] == timeutil.today_str()
    assert message["draft_body"].startswith("Hi there,") and compose.SIGNATURE in message["body_text"]
    assert json.loads(message["qa_json"])["queue"]["status"] == "pass"
    assert db.scalar(conn, "SELECT status FROM leads WHERE id = ?", (lead.lead_id,)) == "queued"


def test_queue_refuses_without_a_registry(conn):
    lead = add(conn, lead_data(1))
    registry.path().unlink()
    with pytest.raises(queue_mod.QueueError, match="no tool available"):
        queue_mod.queue(conn, lead.lead_id, {"subject": "A tool", "body": "Hi", "tool": "quote-builder"})


def test_queue_refuses_form_leads_duplicates_and_suppressed(conn):
    from jura_growth import suppression

    form = add(conn, lead_data(1, contact={"form_url": "https://www.alderlogistics.sg/contact"}))
    with pytest.raises(queue_mod.QueueError, match="not emailed"):
        queue_mod.queue(conn, form.lead_id, {"subject": "x", "body": "y"})
    seeded = seed(conn, 2)
    with pytest.raises(queue_mod.QueueError, match="already has a first email"):
        queue_mod.queue(conn, seeded["lead_id"], {"subject": "x", "body": "y", "tool": "quote-builder"})
    other = add(conn, lead_data(3))
    suppression.add(conn, email="info@cedarlogistics.sg", reason="unsubscribe", source="test")
    with pytest.raises(queue_mod.QueueError, match="suppressed"):
        queue_mod.queue(conn, other.lead_id, {"subject": "x", "body": "y", "tool": "quote-builder"})


def test_follow_up_refused_without_reply_detection(conn):
    seeded = seed(conn, 1)
    with pytest.raises(queue_mod.QueueError, match="reply detection"):
        queue_mod.queue(conn, seeded["lead_id"], {"subject": "A short follow-up", "body": "Hi", "kind": "follow_up"})


def test_queue_and_preview_commands(isolated, monkeypatch, conn):
    from test_scout_support import body_for

    lead = add(conn, lead_data(1))
    path = isolated / "email.json"
    path.write_text(json.dumps({"subject": "A free delivery order maker for Alder Logistics", "body": body_for("Alder Logistics"), "tool": "delivery-order-maker"}))
    result = CliRunner().invoke(cli, ["outreach", "queue", "--lead", str(lead.lead_id), "--file", str(path)])
    assert result.exit_code == 0 and "queued message 1" in result.output
    preview = CliRunner().invoke(cli, ["outreach", "preview", "1"])
    assert preview.exit_code == 0
    assert "To:        info@alderlogistics.sg" in preview.output and "Reply-To:  levi@jurasolutions.sg" in preview.output
    assert "List-Unsubscribe-Post: List-Unsubscribe=One-Click" in preview.output
    assert "You're receiving this because Alder Logistics lists this address" in preview.output
    listing = CliRunner().invoke(cli, ["outreach", "queue-list"])
    assert "alderlogistics.sg" in listing.output


def test_every_email_links_the_privacy_notice():
    from jura_growth.agents.outreach import compose

    email = compose.compose(
        subject="A free quote builder for Acme Aircon",
        body="Hi there,\n\nAcme Aircon asks customers to request quotes by form.",
        company="Acme Aircon",
        site="acmeaircon.sg",
        email="info@acmeaircon.sg",
        secret="s",
    )
    assert compose.PRIVACY_URL in email.text
    assert 'href="https://jurasolutions.sg/privacy"' in email.html
    missing = email.check_text.replace(compose.PRIVACY_LINE, "")
    assert any("privacy" in i.message for i in compose.check_email(missing, {"company": "Acme Aircon", "subject": "x"}))
