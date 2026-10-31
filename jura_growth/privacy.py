"""Personal data in Discord (mission control PRD §4.4).

Discord is a third-party service outside Singapore. `discord.post()` passes
every message through `for_discord()`, so a builder that forgets is covered.

- **Allowed:** company names, domains, industries, scores, public source URLs,
  role addresses (info@, hello@, enquiries@ ...), community groups, and the
  text of Jura's own posts and emails.
- **Masked:** an address that names a person reads `j***@example.com.sg`. The
  builder puts its source page beside it, so Ting Yu can check it there.
- **Never:** phone numbers, a prospect's personal name, the body of a reply,
  bounce or complaint, Ting Yu's own contact details, anything from
  `personal-finance/`.

Secrets go first, through `config.redact()`.

**Jura's own copy.** A builder names the parts of a message that are Jura's
own outgoing text (an email draft, a social post) with `own_copy`. There a
registered reply line and Ting Yu's sender address are left as written.
Secrets, phone numbers, prospects' named addresses and every learned name
(so "Hi Jane," too) are still masked. Since MC-06 the `email` brand channel
drops an outreach draft that greets a person or names the person behind a
named address, so an email preview shows its draft exactly.

**What the process knows.** A name or a reply body can't be recognised by its
shape, so the process says what it knows:

- `remember_address(email)` learns the name in a named address (`jane.tan@`
  gives Jane and Tan). Every named address in the text being masked teaches the
  same. A full name ("jane tan", any case) is masked everywhere; a single part
  only when it is written as a name (Jane, JANE), not as a word (jane).
- `remember_company(name)` keeps a company's name whole, so "Tan Holdings" is
  never read as Mr Tan. `remember_name(name)` does the same for a name that is
  not a prospect's: Ting Yu's own, which signs Jura's emails and posts.
- `remember_owner(email)` marks Ting Yu's own address: removed everywhere
  except Jura's own copy, where his sender address belongs.
- `never_show(text)` registers a value read in memory, such as a reply's body.
- `learn(conn)` asks the plug-ins through an optional hook,
  `privacy_terms(conn) -> {"named_addresses": [...], "companies": [...],
  "owner_addresses": [...], "kept_names": [...]}`. It reads the database only,
  never the Keychain, so `discord.post()` calls it on every post. Without a
  connection it opens `growth.db` read-only itself, if there is one.
- `load_for_masking(conn)` is `learn(conn)` plus the Keychain values
  (`config.load_secrets_for_masking()`), for builders whose text was written by
  another process: today `discord.alert()`, the digest and `discord post`.

**Known limit.** A name that appears in no address the engine holds ("Jane
Lim" behind `jl@`) can't be recognised. Builders keep such fields out of
messages in the first place.

`config.reset_caches()` forgets everything learned.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Callable, Iterable

from jura_growth import agents, config, paths, role_addresses

# The at sign as written, URL-encoded, or as an HTML entity.
AT = r"(?:@|%40|&#64;|&#x40;)"
EMAIL_RE = re.compile(
    rf"(?<![\w.+%-])([\w][\w.+%-]*?){AT}([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{{2,}})", re.I
)
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
# Singapore numbers: 8 digits starting 3, 6, 8 or 9, written 4-4, 4-2-2, 2-2-2-2 (one kind
# of separator) or digit by digit, with or without +65. Then any other number written with a
# + country code. Separators: space, dot, hyphen and the dashes.
SEP = r"[\s.\-\u2010-\u2015]"
PHONE_RE = re.compile(
    rf"(?<![\w+.])(?:(?:\+?65|\(\+?65\)){SEP}?)?"
    rf"(?:[3689]\d{{3}}{SEP}?\d{{4}}|[3689]\d{{3}}({SEP})\d{{2}}\1\d{{2}}"
    rf"|[3689]\d({SEP})\d{{2}}\2\d{{2}}\2\d{{2}}|[3689](?: \d){{7}})(?![\w])"
    rf"|(?<![\w+])\+\d{{1,3}}(?:{SEP}?\(?\d{{1,4}}\)?){{2,5}}(?![\w])"
)
FULL_WIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
FINANCE_LINE_RE = re.compile(r"^.*personal(?:[-_ ]|%2d)?finance.*$", re.I | re.M)
# Words an address never teaches as a name: short words, the shared-inbox vocabulary, and what
# Jura's own posts say every day. The scout calls any address that isn't an exact role "named", so
# `ai.ling@` or `sales.singapore@` would otherwise mask "AI" or "Singapore" in every post, and a
# post that a card would mask is refused (`social/checks.py`). The other parts of the address are
# still learned. A person's name that is one of these ("Ai" in Ai Ling) isn't masked on its own.
NOT_NAMES = role_addresses.words() | frozenset(
    """
    an as at be by do go he hi if in is it me my no of oh on or ok so to up us we
    the and for you our not are was can has had all any new one two
    ai automation automate automated automates automating tool tools toolbox software app apps
    business businesses small team teams work workflow workflows invoice invoices data
    this week from finding findings fun fact facts good read reading worth news tip tips
    """.split()
)
MIN_NAME_PART = 2

NAME = "[name removed]"
PHONE = "[phone removed]"
ADDRESS = "[address removed]"
# A person named with a title: "Ms Tan Mei Ling", "Mr Lim's", "Dr. Wong", "Mdm Siti".
# Title case only: upper-case "MS" and "DR" are MS Excel and DR forms, not people.
HONORIFIC_NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Mdm|Miss|Madam|Mister|Dr|Prof)\b\.?\s+"
    r"(?P<name>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,3})"
)
# Software that follows a title-like word ("Ms Excel"): never a person (re-review R3).
PRODUCT_WORDS = frozenset({"excel", "word", "teams", "office", "outlook", "powerpoint", "access", "project",
                           "dynamics", "sharepoint", "onenote", "visio", "publisher", "forms", "365", "windows"})
REMOVED = "[removed]"
FINANCE = "[removed: personal finance]"
# What masking leaves behind, to find where it acted. Secrets go first, through `config.redact()`.
MASK_RE = re.compile("|".join([*(re.escape(mark) for mark in (NAME, PHONE, ADDRESS, REMOVED, FINANCE, "[redacted]")), r"\S\*\*\*@\S+"]))

_never: set[str] = set()
_name_groups: set[frozenset[str]] = set()  # the name parts of each named address learned
_companies: set[str] = set()  # kept whole: never read as a person's name
_kept_names: set[str] = set()  # names that are not a prospect's (Ting Yu's own)
_owner: set[str] = set()  # Ting Yu's addresses, lower-cased


def for_discord(text: str, *, own_copy: Iterable[str] = ()) -> str:
    """`text` as it may appear in Discord: secrets masked, then personal data.

    `own_copy` names substrings of `text` that are Jura's own outgoing text."""
    text = config.redact(text)
    own = [config.redact(c) for c in own_copy if c and c.strip()]
    groups = set(_name_groups)
    for match in EMAIL_RE.finditer(text):
        address = _plain(match.group(0))
        if address.lower() not in _owner:
            parts = _name_parts(address)
            if parts:
                groups.add(frozenset(parts))
    names = _NameMatcher(groups, _companies | _kept_names)
    return "".join(_mask(part, is_own, names) for part, is_own in _split(text, own))


def own_copy_as_shown(text: str) -> str:
    """`text`, Jura's own outgoing words, as Discord would show them. Where this differs, Ting Yu
    couldn't read those words on an approval card, so they can't be approved (`social/checks.py`)."""
    return for_discord(text, own_copy=[text])


def _bare(value: str) -> str:
    return re.sub(r"['’]s$", "", value.strip()).lower()


def titled_names(text: str, keep: Iterable[str] = ()) -> list[re.Match]:
    """Every person named with a title in `text` ("Ms Tan Mei Ling", "Mr Lim's"),
    leaving out software ("Ms Excel") and the names in `keep`: a company whose own
    name starts with a title ("Dr Aircon"), or the sender's own name."""
    kept = [k.strip().lower() for k in keep if k and k.strip()]
    found = []
    for match in HONORIFIC_NAME_RE.finditer(text):
        name = _bare(match.group("name"))
        if name.split()[0] in PRODUCT_WORDS:
            continue
        whole = _bare(match.group(0))
        if any(whole in k or name == k for k in kept):
            continue
        found.append(match)
    return found


def strip_personal(text: str, keep: Iterable[str] = ()) -> tuple[str, bool]:
    """`text` with any titled person's name, phone number and email address
    replaced by a placeholder, and whether anything was removed. For text taken
    from a job posting (scout PRD §5.2a point 5), which is stored and posted.
    Names in `keep` (the company's own) stay."""
    out = EMAIL_RE.sub(ADDRESS, text)
    for match in reversed(titled_names(out, keep)):
        out = out[: match.start()] + NAME + out[match.end():]
    out = _mask_phones(out)
    return out, out != text


def masked_address(email: str) -> str:
    """A role address as it is; an address that names a person as `j***@domain`
    (keeping the at sign as it was written)."""
    if is_role_address(_plain(email)):
        return email
    match = re.search(AT, email)
    if not match:
        return email
    return f"{email[:1]}***{email[match.start():]}"


def is_role_address(email: str) -> bool:
    return role_addresses.is_shared_inbox(email)


def never_show(*values: str) -> None:
    """Values this process read that must never reach Discord, such as a reply's body."""
    cleaned = (v.strip().rstrip(".!?,;:").strip() for v in values if v)
    _never.update(v for v in cleaned if len(v) >= 8)


def remember_address(email: str) -> None:
    parts = _name_parts(email)
    if parts:
        _name_groups.add(frozenset(parts))


def remember_company(name: str) -> None:
    if name and len(name.strip()) >= 3:
        _companies.add(name.strip())


def remember_name(name: str) -> None:
    """A name that is not a prospect's, kept whole wherever it appears."""
    if name and len(name.strip()) >= 2:
        _kept_names.add(name.strip())


def remember_owner(email: str) -> None:
    if email and "@" in email:
        _owner.add(email.strip().lower())


def learn(conn: sqlite3.Connection | None) -> None:
    """What the plug-ins know: named contacts, companies and Ting Yu's addresses.
    The database only, never the Keychain. A plug-in error leaves what is known.

    Without a connection (a lock-skip run update posts with none), it opens
    `growth.db` read-only for the plug-ins, and does without when it can't."""
    if conn is None:
        ro = _read_only()
        if ro is not None:
            try:
                _learn(ro)
            finally:
                ro.close()
            return
    _learn(conn)


def _read_only() -> sqlite3.Connection | None:
    path = paths.db_path()
    if not path.exists():
        return None
    # Attached with mode=ro: SQLite can then neither write nor roll back a stale
    # journal, so this never repairs growth.db (ADR 0002). Unqualified table names
    # find the attached database, so the plug-ins' queries work unchanged.
    conn = sqlite3.connect(":memory:", uri=True, timeout=1)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("ATTACH DATABASE ? AS growth", (f"{path.resolve().as_uri()}?mode=ro",))
        conn.execute("SELECT 1 FROM growth.sqlite_master LIMIT 1")
    except sqlite3.Error:
        conn.close()
        return None
    return conn


def _learn(conn: sqlite3.Connection | None) -> None:
    for module in agents.plugins():
        hook = getattr(module, "privacy_terms", None)
        if not hook:
            continue
        try:
            terms = hook(conn) or {}
        except Exception:  # noqa: BLE001 - one plug-in never stops a message, as in the digest
            continue
        for address in terms.get("named_addresses", ()):
            remember_address(address)
        for name in terms.get("companies", ()):
            remember_company(name)
        for address in terms.get("owner_addresses", ()):
            remember_owner(address)
        for name in terms.get("kept_names", ()):
            remember_name(name)


def load_for_masking(conn: sqlite3.Connection | None) -> None:
    """For a builder whose text was written by another process."""
    config.load_secrets_for_masking()
    learn(conn)


def reset() -> None:
    _never.clear()
    _name_groups.clear()
    _companies.clear()
    _kept_names.clear()
    _owner.clear()


config.on_reset(reset)


# --- masking -------------------------------------------------------------------


def _mask(text: str, own: bool, names: "_NameMatcher") -> str:
    if not own:
        for value in sorted(_never, key=len, reverse=True):
            # Any spacing: two spaces or a line break between the words still matches.
            words = r"\s+".join(re.escape(w) for w in value.split())
            text = re.sub(words, REMOVED, text, flags=re.I)
    text = FINANCE_LINE_RE.sub(FINANCE, text)
    text = EMAIL_RE.sub(lambda m: _address(m.group(0), own), text)
    text = _mask_phones(text)
    return _outside_urls(text, names.mask)


def _address(written: str, own: bool) -> str:
    if _plain(written).lower() in _owner:
        return written if own else REMOVED
    return masked_address(written)


def _mask_phones(text: str) -> str:
    probe = text.translate(FULL_WIDTH_DIGITS)  # same length, so spans line up
    out, last = [], 0
    for match in PHONE_RE.finditer(probe):
        if sum(c.isdigit() for c in match.group(0)) < 8:
            continue
        out += [text[last : match.start()], PHONE]
        last = match.end()
    out.append(text[last:])
    return "".join(out)


class _NameMatcher:
    def __init__(self, groups: set[frozenset[str]], companies: set[str]):
        parts = {p for group in groups for p in group}
        self.full = self.single = self.companies = None
        if parts:
            word = "|".join(re.escape(p) for p in sorted(parts, key=len, reverse=True))
            self.full = re.compile(rf"\b(?:{word})(?:[\s.-]+(?:{word}))+\b", re.I)
            forms = sorted({f for p in parts for f in (p.title(), p.upper())}, key=len, reverse=True)
            self.single = re.compile(rf"\b(?:{'|'.join(re.escape(f) for f in forms)})\b")
        if companies:
            alternatives = "|".join(re.escape(c) for c in sorted(companies, key=len, reverse=True))
            self.companies = re.compile(rf"\b(?:{alternatives})\b", re.I)

    def mask(self, text: str) -> str:
        if self.full is None:
            return text
        if self.companies is None:
            return self._mask(text)
        out, last = [], 0
        for match in self.companies.finditer(text):
            out += [self._mask(text[last : match.start()]), match.group(0)]
            last = match.end()
        out.append(self._mask(text[last:]))
        return "".join(out)

    def _mask(self, text: str) -> str:
        if self.full is None or self.single is None:
            return text
        return self.single.sub(NAME, self.full.sub(NAME, text))


# --- helpers -------------------------------------------------------------------


def _plain(email: str) -> str:
    return re.sub(AT, "@", email, count=1, flags=re.I)


def _name_parts(email: str) -> set[str]:
    email = _plain(email)
    if is_role_address(email):
        return set()
    local = email.split("@", 1)[0].lower()
    parts = {p for p in re.split(r"[^a-z]+", local) if len(p) >= MIN_NAME_PART}
    return parts - NOT_NAMES


def _split(text: str, own: list[str]) -> list[tuple[str, bool]]:
    """`text` cut into (piece, is Jura's own copy) by where each own-copy string occurs."""
    if not own:
        return [(text, False)]
    pattern = re.compile("|".join(re.escape(c) for c in sorted(set(own), key=len, reverse=True)))
    out, last = [], 0
    for match in pattern.finditer(text):
        out += [(text[last : match.start()], False), (match.group(0), True)]
        last = match.end()
    out.append((text[last:], False))
    return [(piece, is_own) for piece, is_own in out if piece]


def _outside_urls(text: str, change: Callable[[str], str]) -> str:
    out, last = [], 0
    for match in URL_RE.finditer(text):
        out += [change(text[last : match.start()]), match.group(0)]
        last = match.end()
    out.append(change(text[last:]))
    return "".join(out)
