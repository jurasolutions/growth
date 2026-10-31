"""The brand channels for a reply to someone who wrote in: `inbox-email` and `inbox-social` (rule 10).

The core gate already covers the voice and the links it can see. A draft answers a stranger and may
be steered by what they wrote, so these go further: every word that could be a link must be Jura's,
read as a browser would read it, every figure must be an approved claim, no price and no promise, and
a greeting may use only a name they gave. Judgement isn't here. Whether the draft is any good is the prompt's job and
Ting Yu's, who reads every one.

The context `triage` passes: `sender_name`, `their_words`, `public`, `platform`, `high`.
"""

from __future__ import annotations

import re
import unicodedata

from jura_growth import brand_check, caps
from jura_growth.agents.outreach import compose
from jura_growth.brand_check import Channel, Issue

EMAIL_WORDS_UNDER = 180
SOCIAL_WORDS_UNDER = 80
HIGH_WORDS_MAX = 60  # a holding reply (D9)

_LINE_BREAK = re.compile(r"[\r\n\x0b\x0c\x85  ]")
# Anything shaped like a domain, in any script and with any top-level domain: the core's list of
# top-level domains is for ordinary copy, and doesn't see `evil.test` or a Cyrillic look-alike.
_DOMAIN_SHAPED = re.compile(r"[^\W_][\w-]*(?:\.[^\W_][\w-]*)*\.[^\W\d_]{2,}", re.U)
# Dots a browser reads as dots that aren't `.`, past what NFKC already folds.
_UNICODE_DOTS = str.maketrans({"\u3002": ".", "\uff0e": ".", "\uff61": "."})
_RETYPED_TLD = rf"(?:{brand_check.TLDS}|test)\b"
# A link a reader can retype: `evil[.]com`, `evil(dot)com`, `evil dot com`, `evil . com`.
_RETYPED = re.compile(
    rf"[\w-]+\s*(?:\[\s*(?:\.|dot)\s*\]|\(\s*(?:\.|dot)\s*\)|\{{\s*(?:\.|dot)\s*\}})\s*[a-z]{{2,}}"
    rf"|[\w-]+\s+(?:dot|\.)\s+{_RETYPED_TLD}",
    re.I,
)
_HANDLE = re.compile(r"(?<![\w.@])@[A-Za-z0-9_][A-Za-z0-9_.]+")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_FULL_DATE = re.compile(
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{brand_check.MONTHS}\s+\d{{4}}\b|\b{brand_check.MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",
    re.I,
)
_PRICE = re.compile(
    r"(?:S\$|US\$|\$|£|€|\bSGD\b|\bUSD\b|\bRM\b)\s?\d|\d\s?(?:dollars?|bucks|sgd|usd)\b", re.I,
)
_PROMISE = re.compile(
    r"\b(?:i|we)\b(?:['’]ll| will| can| could| would| shall)?\s+(?:[a-z]+\s+){0,3}?(?:refund|compensate|reimburse|waive)\w*"
    r"|\bguarantee\w*|\bpromise\w*|\bfull refund\b|\bmoney back\b|\bpay you back\b|\bback in full\b|\bfor free\b|\bfree of charge\b"
    r"|\bdiscount\w*|\b(?:fixed|sorted|resolved|done|ready|delivered|finished)\s+by\b",
    re.I,
)
# E3: in public, any mention at all. An email address is only refused when it is asked to be posted,
# since the prompt invites an email to Jura.
_CONTACT_DETAILS = re.compile(r"\b(?:phone|mobile|whatsapp|(?:your|a|contact) number|(?:your |home |office )address)\b", re.I)
_ASKS_FOR_EMAIL = re.compile(r"\b(?:post|leave|drop|share|comment|put|write|give|tell|reply)\b[^.?!\n]{0,40}\byour email\b", re.I)
_LEVI = re.compile(r"\bLevi\b")
_LEVI_WILL = re.compile(r"\bLevi\b[^.?!\n]{0,20}(?:\bwill\b|['’]ll\b)")
_I_WILL_REPLY = re.compile(r"\bI(?:['’]ll| will)\b[^.?!\n]{0,30}\b(?:reply|write|come back|get back|respond|answer|call|follow up)\b")


def words_in(text: str) -> int:
    return len(text.split())


def promises_a_reply(draft: str) -> bool:
    """F10: whether this draft says Levi will come back, in his own voice or the Page's."""
    return bool(_LEVI_WILL.search(draft) or _I_WILL_REPLY.search(draft))


def _as_a_browser_reads_it(text: str) -> str:
    """Look-alike letters and dots folded, invisible characters gone."""
    folded = unicodedata.normalize("NFKC", text).translate(_UNICODE_DOTS)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def _links(text: str, ctx: dict) -> list[Issue]:
    found = []
    invisible = sorted({f"U+{ord(ch):04X}" for ch in text if unicodedata.category(ch) in ("Cf", "Co", "Cn")})
    if invisible:
        found.append(Issue("channel", "A reply holds no invisible characters, because they can hide a link", ", ".join(invisible)))
    plain = _as_a_browser_reads_it(text)
    for match in _DOMAIN_SHAPED.finditer(plain):
        word = match.group(0)
        if not word.isascii() or not brand_check.is_jura(word):
            found.append(Issue("channel", "Links and addresses in a reply are only ever Jura's own", word))
    for pattern, shown in ((_RETYPED, "a link spelled out to be retyped"), (_HANDLE, "an @handle")):
        match = pattern.search(plain)
        if match:
            found.append(Issue("channel", f"A reply doesn't send anyone elsewhere with {shown}", match.group(0)))
    if ctx.get("public") and ctx.get("platform") == "instagram" and brand_check.find_links(text):
        found.append(Issue("channel", "Links in an Instagram comment can't be clicked: invite a DM instead"))
    return found


def holds_a_link(text: str) -> bool:
    """Whether the draft's link rule would refuse `text` (S1): a subject the card and Resend both carry."""
    return bool(_links(text, {}))


def _figures(text: str, ctx: dict) -> list[Issue]:
    # Their own figure is let through here so a small count can be said back to them. The core rule
    # still refuses anything larger, so the prompt doesn't offer this.
    theirs = ctx.get("their_words") or ""
    found = []
    price = _PRICE.search(text)
    if price:
        found.append(Issue("channel", "Quote no price figure: invite a private chat with Levi instead", price.group(0)))
    without_links = text
    for link in brand_check.find_links(text):
        without_links = without_links.replace(link, " ")
    for figure in [*brand_check.figures(text), *_YEAR.findall(_FULL_DATE.sub(" ", without_links))]:
        if not re.search(rf"(?<![\d.,]){re.escape(figure)}(?![\d])", theirs):
            found.append(Issue("channel", "A figure in a reply is an approved claim, nothing else", figure))
    numerals = [ch for ch in text if not ch.isascii() and unicodedata.numeric(ch, None) is not None]
    if numerals:
        found.append(Issue("channel", "A figure in a reply is an approved claim, nothing else", "".join(numerals)))
    return found


def _name(text: str, ctx: dict) -> list[Issue]:
    greeting = compose.greets_a_person(text, None)
    if not greeting:
        return []
    matched = compose.GREETING_TO_RE.match(greeting)
    who = matched.group("who") if matched else ""
    given = f"{ctx.get('sender_name') or ''} {ctx.get('their_words') or ''}".casefold()
    missing = [word for word in re.findall(r"[^\W\d_]+", who) if not re.search(rf"\b{re.escape(word.casefold())}\b", given)]
    if not missing:
        return []
    return [Issue("channel", "Use a name only if they gave it: write “Hi there,” otherwise", greeting)]


def _english(text: str) -> list[Issue]:
    letters = [ch for ch in text if ch.isalpha()]
    latin = sum(1 for ch in letters if unicodedata.name(ch, "").startswith("LATIN"))
    if letters and latin / len(letters) < 0.8:
        return [Issue("channel", "Draft in English, whatever they wrote in: the report says they wrote in another language")]
    return []


def _shared(text: str, ctx: dict) -> list[Issue]:
    issues = _links(text, ctx) + _figures(text, ctx) + _name(text, ctx) + _english(text)
    promise = _PROMISE.search(text)
    if promise:
        issues.append(Issue("channel", "Make no promise, refund or discount: only Levi can, in a personal reply", promise.group(0)))
    if ctx.get("high"):
        if words_in(text) > HIGH_WORDS_MAX:
            issues.append(Issue("channel", f"A high-priority draft is a short holding reply, at most {HIGH_WORDS_MAX} words"))
    return issues


def _too_long(text: str, limit: int, what: str) -> list[Issue]:
    if len(text) <= limit:
        return []
    return [Issue("channel", f"{what} is at most {limit} characters; this is {len(text)}")]


def check_email(text: str, ctx: dict) -> list[Issue]:
    """Levi signs an email, so on a holding reply he says he will reply."""
    issues = _shared(text, ctx) + _too_long(text, caps.INBOX_EMAIL_DRAFT_CHARS, "An email reply")
    if text.count("\n") >= caps.INBOX_EMAIL_DRAFT_LINES:
        issues.append(Issue("channel", f"An email reply is at most {caps.INBOX_EMAIL_DRAFT_LINES} lines, so its card stays one message"))
    words = words_in(text)
    if words >= EMAIL_WORDS_UNDER:
        issues.append(Issue("channel", f"An email reply is under {EMAIL_WORDS_UNDER} words; this is {words}"))
    if ctx.get("high") and not (_I_WILL_REPLY.search(text) or _LEVI.search(text)):
        issues.append(Issue("channel", "A high-priority draft is a holding reply: say you'll reply personally"))
    return issues


def check_social(text: str, ctx: dict) -> list[Issue]:
    """The Page speaks on social, so a holding reply says Levi will reply."""
    issues = _shared(text, ctx) + _too_long(text, caps.INBOX_SOCIAL_DRAFT_CHARS, "A social reply")
    words = words_in(text)
    if ctx.get("high") and not _LEVI.search(text):
        issues.append(Issue("channel", "A high-priority draft is a holding reply: say Levi will reply personally"))
    if words >= SOCIAL_WORDS_UNDER:
        issues.append(Issue("channel", f"A social reply is under {SOCIAL_WORDS_UNDER} words; this is {words}"))
    if _LINE_BREAK.search(text):
        issues.append(Issue("channel", "A social reply is one paragraph with no line breaks: Enter sends in a DM"))
    asks = (_CONTACT_DETAILS.search(text) or _ASKS_FOR_EMAIL.search(text)) if ctx.get("public") else None
    if asks:
        issues.append(Issue("channel", "Never ask anyone to post contact details in public: invite a DM or an email", asks.group(0)))
    return issues


def channels() -> dict[str, Channel]:
    return {
        "inbox-email": Channel("inbox-email", check=check_email, description="A reply by email: under 180 words, Jura's links only"),
        "inbox-social": Channel("inbox-social", check=check_social, description="A reply on Facebook or Instagram: under 80 words, one paragraph"),
    }
