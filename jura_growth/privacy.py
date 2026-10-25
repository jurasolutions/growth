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
(so "Hi Jane," too) are still masked: until MC-06 drops drafts that name a
person, a preview may read "[name removed]" where a word looked like a name.

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
# Short words that a name part never masks.
NOT_NAMES = frozenset(
    """
    an as at be by do go he hi if in is it me my no of oh on or ok so to up us we
    the and for you our not are was can has had all any new one two
    """.split()
)
MIN_NAME_PART = 2

NAME = "[name removed]"
PHONE = "[phone removed]"
REMOVED = "[removed]"
FINANCE = "[removed: personal finance]"

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
