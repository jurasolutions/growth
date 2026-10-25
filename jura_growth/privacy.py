"""Personal data in Discord (mission control PRD §4.4).

Discord is a third-party service outside Singapore, so every message passes
through `for_discord()` before it is posted. `discord.post()` applies it to
every message too, so a builder that forgets is still covered.

- **Allowed:** company names, domains, industries, scores, public source URLs,
  role addresses (info@, hello@, enquiries@ ...), community groups, and the
  text of Jura's own posts and emails.
- **Masked:** an address that names a person reads `j***@example.com.sg`. The
  message builder puts its source page beside it, so Ting Yu can check it there.
- **Never:** phone numbers, a prospect's personal name, the body of a reply,
  bounce or complaint, Ting Yu's own contact details, anything from
  `personal-finance/`.

Secrets go first, through `config.redact()`.

A name or a reply body can't be recognised by its shape, so the process tells
this module what it knows:

- `remember_address(email)` learns the name in a named address (`jane.tan@`
  gives Jane and Tan). Every address in the text being masked teaches the same.
- `never_show(text)` registers a value read in memory, such as a reply's body,
  that must never be posted.
- `load_for_masking(conn)` is what the one-pager, run updates and approval cards
  call once before they build anything: it loads the Keychain values
  (`config.load_secrets_for_masking()`) and the named addresses the plug-ins
  hold. A plug-in shares them through an optional hook,
  `named_addresses(conn) -> list[str]`, found with `getattr` like `digest()`.

`config.reset_caches()` forgets all of it.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Iterable

from jura_growth import config

# Shared inboxes, not people. Covers every role the scout classifies
# (tests/test_privacy.py checks that it does), plus system senders.
ROLE_LOCAL_PARTS = frozenset(
    """
    info enquiry enquiries enquire inquiry inquiries sales hello contact admin
    office general mail team reception service services support help booking bookings book
    orders order sales.sg sg singapore accounts account billing cs customerservice
    customer.service customercare care ask operations ops marketing projects quote quotes
    quotation rental events catering reservations reservation studio clinic frontdesk
    front.desk admissions enrol enroll hr careers jobs privacy dpo abuse noreply no-reply
    donotreply postmaster webmaster mailer-daemon bounce bounces notifications
    """.split()
)

EMAIL_RE = re.compile(
    r"(?<![\w.+%-])([A-Za-z0-9][\w.+%-]*)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})"
)
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
# Singapore numbers (8 digits starting 3, 6, 8 or 9, with or without +65), then any
# other number written with a + country code.
PHONE_RE = re.compile(
    r"(?<![\w+])(?:(?:\+65|\(\+?65\)|65)[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?![\w])"
    r"|(?<![\w+])\+\d{1,3}(?:[\s.-]?\(?\d{1,4}\)?){2,5}(?![\w])"
)
FINANCE_LINE_RE = re.compile(r"^.*personal[-_ ]finance.*$", re.I | re.M)
# A name part as short as these would mask ordinary words.
MIN_NAME_PART = 3
# Shorter registered values (a reply line such as "Thanks") would mask ordinary words.
MIN_NEVER = 8
NOT_NAMES = frozenset("the and for you our not are was can has had all any new one two".split())

NAME = "[name removed]"
PHONE = "[phone removed]"
REMOVED = "[removed]"
FINANCE = "[removed: personal finance]"

_never: set[str] = set()
_people: set[str] = set()  # name parts, lower-cased


def for_discord(text: str) -> str:
    """`text` as it may appear in Discord: secrets masked, then personal data."""
    text = config.redact(text)
    for value in sorted(_never, key=len, reverse=True):
        text = re.sub(re.escape(value), REMOVED, text, flags=re.I)
    text = FINANCE_LINE_RE.sub(FINANCE, text)
    names = set(_people)
    for match in EMAIL_RE.finditer(text):
        names |= _name_parts(match.group(0))
    text = EMAIL_RE.sub(lambda m: masked_address(m.group(0)), text)
    text = PHONE_RE.sub(lambda m: PHONE if _digits(m.group(0)) >= 8 else m.group(0), text)
    return _outside_urls(text, lambda part: _mask_names(part, names))


def masked_address(email: str) -> str:
    """A role address as it is; an address that names a person as `j***@domain`."""
    if is_role_address(email):
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def is_role_address(email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    base = re.sub(r"[\d_.-]+$", "", local) or local
    return local in ROLE_LOCAL_PARTS or base in ROLE_LOCAL_PARTS


def never_show(*values: str) -> None:
    """Values this process read that must never reach Discord, such as a reply's body."""
    cleaned = (v.strip().rstrip(".!?,;:").strip() for v in values if v)
    _never.update(v for v in cleaned if len(v) >= MIN_NEVER)


def remember_address(email: str) -> None:
    """Learn the personal name in a named address, so it is masked wherever it appears."""
    _people.update(_name_parts(email))


def remember_people(conn: sqlite3.Connection | None) -> None:
    """Learn the named addresses the plug-ins hold. Never fails: a plug-in error leaves what is known."""
    if conn is None:
        return
    from jura_growth import agents

    for module in agents.plugins():
        hook = getattr(module, "named_addresses", None)
        if not hook:
            continue
        try:
            addresses: Iterable[str] = hook(conn) or []
        except (sqlite3.Error, RuntimeError, ValueError):
            continue
        for address in addresses:
            remember_address(address)


def load_for_masking(conn: sqlite3.Connection | None) -> None:
    """Once before building a one-pager, a run update or an approval card."""
    config.load_secrets_for_masking()
    remember_people(conn)


def reset() -> None:
    _never.clear()
    _people.clear()


config.on_reset(reset)


# --- helpers -------------------------------------------------------------------


def _name_parts(email: str) -> set[str]:
    if is_role_address(email):
        return set()
    local = email.split("@", 1)[0].lower()
    parts = {p for p in re.split(r"[^a-z]+", local) if len(p) >= MIN_NAME_PART}
    return parts - NOT_NAMES


def _mask_names(text: str, names: set[str]) -> str:
    if not names:
        return text
    word = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.sub(rf"\b(?:{word})(?:[\s.-]+(?:{word}))*\b", NAME, text, flags=re.I)


def _outside_urls(text: str, change) -> str:
    out, last = [], 0
    for match in URL_RE.finditer(text):
        out += [change(text[last : match.start()]), match.group(0)]
        last = match.end()
    out.append(change(text[last:]))
    return "".join(out)


def _digits(text: str) -> int:
    return sum(c.isdigit() for c in text)
