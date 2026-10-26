"""Emails greet the company, never a person (MC §4.4, AC-M12.2; ticket 06).

The `email` brand channel drops a draft that greets a person by name, or that names the person a
named address belongs to, so an approval card shows the email exactly as it will go out and never
needs masking.
"""

import pytest

from jura_growth import brand_check
from jura_growth.agents.outreach import compose, queue as queue_mod

from test_outreach_email import REFERENCE, TOOLS, VECTOR_SECRET
from test_scout_support import at, body_for, scout_env, seed  # noqa: F401

GREET = "Greet the company, not a person"


def reasons(body, *, to="info@acme-aircon.sg", company="Acme Aircon"):
    email = compose.compose(subject="A free quote builder for Acme Aircon", body=body, company=company, site="acme-aircon.sg",
                            email=to, secret=VECTOR_SECRET)
    assert email.to == to.strip().lower()
    return brand_check.check(
        email.check_text,
        subject=email.subject,
        channel_name="email",
        proper_nouns=[company],
        context={"company": company, "observations": [], "tools": TOOLS, "tool": "quote-builder", "kind": "first", "recipient": email.to},
    ).reasons()


def greets(line: str) -> str:
    return REFERENCE.replace(REFERENCE.split("\n")[0], line, 1)


def test_the_reference_email_greets_the_company_and_passes():
    assert REFERENCE.split("\n")[0] == "Hi there,"
    assert reasons(REFERENCE) == []


@pytest.mark.parametrize("line", ["Hi Jane,", "Hello Jane Tan,", "Dear Mr Tan,", "Hi Jane.", "Good morning Priya,", "Hey Ahmad,"])
def test_a_draft_that_greets_a_person_is_refused(line):
    found = reasons(greets(line))
    assert any(GREET in r for r in found), found


@pytest.mark.parametrize(
    "line",
    ["Hi there,", "Hello,", "Hi,", "Hello Acme Aircon team,", "Hi team,", "Dear Sir or Madam,", "Hello everyone,", "Hi Acme Aircon,",
     "Good afternoon,"],
)
def test_a_draft_that_greets_the_company_passes(line):
    assert not any(GREET in r for r in reasons(greets(line)))


def test_a_draft_that_names_the_person_behind_a_named_address_is_refused():
    body = REFERENCE.replace("Hi there,", "Hi there,\n\nJane Tan mentioned the paper orders.", 1)
    found = reasons(body, to="jane.tan@acme-aircon.sg")
    assert any("names the person" in r for r in found), found
    assert not any("names the person" in r for r in reasons(body.replace("Jane Tan mentioned", "Someone mentioned")))


def test_a_role_address_teaches_no_name():
    body = REFERENCE.replace("Hi there,", "Hi there,\n\nThe sales team mentioned the paper orders.", 1)
    assert not any("names the person" in r for r in reasons(body, to="sales@acme-aircon.sg"))


def test_queue_drops_a_draft_that_greets_a_person_so_no_card_can_show_it(conn, monkeypatch):
    """AC-M12.2 through the real gate: one regeneration, then the item drops."""
    at(monkeypatch, "2026-10-26T10:00:00+08:00")
    seeded = seed(conn, 1, queue=False)
    data = {"subject": "A free delivery order maker for Alder Logistics",
            "body": body_for("Alder Logistics").replace("Hi there,", "Hi Jane,"), "tool": "delivery-order-maker"}
    first = queue_mod.queue(conn, seeded["lead_id"], data)
    assert first.status == "retry" and any(GREET in r for r in first.reasons)
    assert queue_mod.queue(conn, seeded["lead_id"], data).status == "dropped"
