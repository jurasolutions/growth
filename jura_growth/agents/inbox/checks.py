"""The brand channels for a reply to someone who wrote in: `inbox-email` and `inbox-social` (rule 10).

The core gate already covers the voice and the links it can see. A draft answers a stranger and may
be steered by what they wrote, so these go further: every word that could be a link must be Jura's,
every figure must be an approved claim or their own, no price and no promise, and a greeting may use
only a name they gave. Judgement isn't here. Whether the draft is any good is the prompt's job and
Ting Yu's, who reads every one.

The context `triage` passes: `sender_name`, `their_words`, `public`, `platform`, `high`.
"""

from __future__ import annotations

import re
import unicodedata

from jura_growth import brand_check
from jura_growth.agents.outreach import compose
from jura_growth.brand_check import Channel, Issue

EMAIL_WORDS_UNDER = 180
SOCIAL_WORDS_UNDER = 80
HIGH_WORDS_MAX = 60  # a holding reply (D9)

_LINE_BREAK = re.compile(r"[\r\n\x0b\x0c\x85  ]")
# Anything shaped like a domain, in any script and with any top-level domain: the core's list of
# top-level domains is for ordinary copy, and doesn't see `evil.test` or a Cyrillic look-alike.
_DOMAIN_SHAPED = re.compile(r"[^\W_][\w-]*(?:\.[^\W_][\w-]*)*\.[^\W\d_]{2,}", re.U)
_PRICE = re.compile(
    r"(?:S\$|US\$|\$|£|€|\bSGD\b|\bUSD\b|\bRM\b)\s?\d|\d\s?(?:dollars?|bucks|sgd|usd)\b", re.I,
)
_PROMISE = re.compile(
    r"\b(?:i|we)\b[^.?!\n]{0,40}\b(?:promise|refund|compensate|reimburse|waive)\w*"
    r"|\bguarantee\w*|\bpromise\w*|\bfull refund\b|\bmoney back\b|\bfor free\b|\bfree of charge\b|\bdiscount\w*",
    re.I,
)
_ASKS_TO_POST = re.compile(
    r"\b(?:post|leave|drop|share|comment|put|write|give|tell)\b[^.?!\n]{0,40}"
    r"\b(?:phone|mobile|whatsapp|(?:your|a|contact) number|(?:your |home |office )address|your email)\b",
    re.I,
)
_LEVI = re.compile(r"\bLevi\b")


def words_in(text: str) -> int:
    return len(text.split())


def _links(text: str, ctx: dict) -> list[Issue]:
    found = []
    for match in _DOMAIN_SHAPED.finditer(text):
        word = match.group(0)
        if not word.isascii() or not brand_check.is_jura(word):
            found.append(Issue("channel", "Links and addresses in a reply are only ever Jura's own", word))
    if ctx.get("public") and ctx.get("platform") == "instagram" and brand_check.find_links(text):
        found.append(Issue("channel", "Links in an Instagram comment can't be clicked: invite a DM instead"))
    return found


def _figures(text: str, ctx: dict) -> list[Issue]:
    theirs = ctx.get("their_words") or ""
    found = []
    price = _PRICE.search(text)
    if price:
        found.append(Issue("channel", "Quote no price figure: invite a private chat with Levi instead", price.group(0)))
    for figure in brand_check.figures(text):
        if not re.search(rf"(?<![\d.,]){re.escape(figure)}(?![\d])", theirs):
            found.append(Issue("channel", "A figure in a reply is an approved claim or their own, nothing else", figure))
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
        if not _LEVI.search(text):
            issues.append(Issue("channel", "A high-priority draft is a holding reply: say Levi will reply personally"))
        if words_in(text) > HIGH_WORDS_MAX:
            issues.append(Issue("channel", f"A high-priority draft is a short holding reply, at most {HIGH_WORDS_MAX} words"))
    return issues


def check_email(text: str, ctx: dict) -> list[Issue]:
    issues = _shared(text, ctx)
    words = words_in(text)
    if words >= EMAIL_WORDS_UNDER:
        issues.append(Issue("channel", f"An email reply is under {EMAIL_WORDS_UNDER} words; this is {words}"))
    return issues


def check_social(text: str, ctx: dict) -> list[Issue]:
    issues = _shared(text, ctx)
    words = words_in(text)
    if words >= SOCIAL_WORDS_UNDER:
        issues.append(Issue("channel", f"A social reply is under {SOCIAL_WORDS_UNDER} words; this is {words}"))
    if _LINE_BREAK.search(text):
        issues.append(Issue("channel", "A social reply is one paragraph with no line breaks: Enter sends in a DM"))
    asks = _ASKS_TO_POST.search(text) if ctx.get("public") else None
    if asks:
        issues.append(Issue("channel", "Never ask anyone to post contact details in public: invite a DM or an email", asks.group(0)))
    return issues


def channels() -> dict[str, Channel]:
    return {
        "inbox-email": Channel("inbox-email", check=check_email, description="A reply by email: under 180 words, Jura's links only"),
        "inbox-social": Channel("inbox-social", check=check_social, description="A reply on Facebook or Instagram: under 80 words, one paragraph"),
    }
