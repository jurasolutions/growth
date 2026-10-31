"""Shared inboxes (info@, sales@ ...) as opposed to addresses that name a person.

One vocabulary for the scout's contact rules (`agents/scout/contact.py`) and
for what may appear in Discord (`privacy.py`).
"""

from __future__ import annotations

import re

# Enquiry role addresses, in order of preference.
ENQUIRY_ROLES = ("info", "enquiry", "enquiries", "enquire", "inquiry", "inquiries", "sales", "hello", "contact", "admin")
OTHER_ROLES = (
    "office", "general", "mail", "team", "reception", "service", "services", "support", "help",
    "booking", "bookings", "book", "orders", "order", "sales.sg", "sg", "singapore", "accounts",
    "account", "billing", "cs", "customerservice", "customer.service", "customercare", "care",
    "ask", "operations", "ops", "marketing", "projects", "quote", "quotes", "quotation",
    "rental", "events", "catering", "reservations", "reservation", "studio", "clinic",
    "frontdesk", "front.desk", "admissions", "enrol", "enroll", "hr", "careers", "jobs",
)
# Shared inboxes that are not for enquiries: system senders and policy desks.
NOT_FOR_ENQUIRIES = ("careers", "career", "jobs", "job", "hr", "recruit", "recruitment", "recruiting", "talent",
                     "hiring", "apply", "resume", "resumes", "cv", "privacy", "dpo", "abuse", "noreply", "no-reply", "donotreply", "postmaster", "webmaster")


def words() -> frozenset[str]:
    """Every word in the shared-inbox vocabulary: "sales.singapore@" names no person."""
    roles = (*ENQUIRY_ROLES, *OTHER_ROLES, *NOT_FOR_ENQUIRIES)
    return frozenset(word for role in roles for word in re.split(r"[^a-z]+", role) if word)


def local_part(email: str) -> str:
    return email.split("@", 1)[0].lower()


def base(local: str) -> str:
    """The local part without a trailing number or separator (sales2 -> sales)."""
    return re.sub(r"[\d_.-]+$", "", local) or local


def is_role(email: str) -> bool:
    """An enquiry or other role address (the scout's `role` kind)."""
    local = local_part(email)
    roles = (*ENQUIRY_ROLES, *OTHER_ROLES)
    return local in roles or base(local) in roles


def is_enquiry_role(email: str) -> bool:
    local = local_part(email)
    return local in ENQUIRY_ROLES or base(local) in ENQUIRY_ROLES


def not_for_enquiries(email: str) -> bool:
    """The word whole, or before a separator or number (careers2@, jobs.sg@), so a
    business name that starts with one (cvlogistics@, talentdance@) is still an address."""
    local = local_part(email)
    return any(re.fullmatch(rf"{re.escape(word)}(?:[\d._+-].*)?", local) for word in NOT_FOR_ENQUIRIES)


def is_shared_inbox(email: str) -> bool:
    """Any address that doesn't name a person: a role address or a system sender.

    Matched whole (or without a trailing number), never by prefix: `hr` is a
    shared inbox, `hrithik.tan` is a person."""
    local = local_part(email)
    words = (*ENQUIRY_ROLES, *OTHER_ROLES, *NOT_FOR_ENQUIRIES)
    return local in words or base(local) in words
