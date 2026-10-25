"""The brand and compliance checker. Every piece of outgoing text passes here
before it can be sent or posted (foundation PRD §5.6, from
`design-system/README.md` §3).

The rules, in order:

 1. exclamation     no exclamation marks
 2. emoji           no emoji, pictographs or text emoticons
 3. buzzword        nothing from config/buzzwords.txt
 4. urgency         no manufactured urgency ("limited spots", "act now", ...)
 5. question        no rhetorical questions as headings or subject lines
 6. rhythm          at most one em dash per 60 words; no "this, not that"
 7. numbers         a figure in a claim about Jura or its results must be in
                    config/approved_claims.yaml (see `_numbers` for the rest)
 8. sentence-case   subject lines, headings and buttons in sentence case
 9. links           links only to jurasolutions.sg, plus declared sources on
                    channels that carry news
10. channel         each channel's own required parts, defined by the agent
                    that owns the channel

`check()` returns every issue it finds, so one regeneration can fix them all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Iterable, NamedTuple
from urllib.parse import urlsplit

import yaml

from jura_growth import config, paths

JURA_HOSTS = ("jurasolutions.sg",)


@dataclass
class Issue:
    rule: str
    message: str
    excerpt: str = ""

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}" + (f": “{self.excerpt}”" if self.excerpt else "")


@dataclass
class Result:
    issues: list[Issue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues

    def reasons(self) -> list[str]:
        return [str(issue) for issue in self.issues]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues": [issue.__dict__ for issue in self.issues],
        }


@dataclass
class Channel:
    """A place text goes. `allow_sources` lets third-party source links through
    (news); `check` adds the channel's own rules."""

    name: str
    allow_sources: bool = False
    check: Callable[[str, dict], list[Issue]] | None = None
    description: str = ""


# --- the channel registry --------------------------------------------------

_CORE_CHANNELS = {
    "general": Channel("general", description="Anything carrying the Jura name, no third-party links"),
    "news": Channel("news", allow_sources=True, description="Copy that cites third-party sources"),
}


def channels() -> dict[str, Channel]:
    from jura_growth import agents

    found = dict(_CORE_CHANNELS)
    for module in agents.plugins():
        provider = getattr(module, "channels", None)
        if provider:
            found.update(provider())
    return found


def channel(name: str | None) -> Channel:
    every = channels()
    if name is None:
        return every["general"]
    if name not in every:
        raise ValueError(f"unknown channel {name!r}; known: {', '.join(sorted(every))}")
    return every[name]


# --- entry point -----------------------------------------------------------


def check(
    text: str,
    *,
    subject: str | None = None,
    headings: Iterable[str] = (),
    buttons: Iterable[str] = (),
    channel_name: str | None = None,
    sources: Iterable[str] = (),
    proper_nouns: Iterable[str] = (),
    context: dict | None = None,
) -> Result:
    chosen = channel(channel_name)
    sources = [s for s in sources if s]
    headings = list(headings) + _markdown_headings(text)
    buttons = list(buttons)
    nouns = _proper_nouns() | {n for name in proper_nouns for n in _words(name)}

    everything = "\n".join([subject or "", *headings, *buttons, text])
    plain = _strip_links(everything)

    issues: list[Issue] = []
    issues += _exclamation(plain)
    issues += _emoji(plain)
    issues += _buzzwords(plain)
    issues += _urgency(plain)
    issues += _questions(subject, headings)
    issues += _rhythm(_strip_links(text))
    issues += _numbers(everything, chosen, sources)
    issues += _sentence_case(subject, headings, buttons, nouns)
    issues += _links(everything, chosen, sources)
    if chosen.check:
        ctx = dict(context or {})
        ctx.update(subject=subject, headings=headings, buttons=buttons, sources=sources)
        issues += chosen.check(text, ctx)
    return Result(_dedupe(issues))


# --- shared text helpers ---------------------------------------------------

# URLs may hold balanced parentheses (IRAS: .../goods-services-tax-(gst)/...).
_URL_CHARS = r"(?:[^\s<>()\[\]\"']|\([^\s<>()\[\]\"']*\))+"
URL_RE = re.compile(rf"\bhttps?://{_URL_CHARS}|\bwww\.{_URL_CHARS}", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
TLDS = "sg|com|net|org|io|ai|co|gov|edu|app|dev|info|biz|me|asia|xyz|tech|my|uk|au|us"
BARE_DOMAIN_RE = re.compile(
    rf"(?<![@\w./-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:{TLDS})(?:\.[a-z]{{2}})?\b(?:/[^\s<>()\[\]\"']*)?",
    re.I,
)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")


def find_links(text: str) -> list[str]:
    """Every URL or bare domain in `text`, excluding email addresses."""
    without_emails = EMAIL_RE.sub(" ", text)
    found = [m.group(2) for m in MD_LINK_RE.finditer(without_emails)]
    remaining = MD_LINK_RE.sub(r"\1", without_emails)
    found += [m.group(0) for m in URL_RE.finditer(remaining)]
    remaining = URL_RE.sub(" ", remaining)
    found += [m.group(0) for m in BARE_DOMAIN_RE.finditer(remaining)]
    return [link.rstrip(".,;:") for link in found]


def host_of(link: str) -> str:
    candidate = link if re.match(r"^https?://", link, re.I) else f"https://{link}"
    return (urlsplit(candidate).hostname or "").lower()


def is_jura(link: str) -> bool:
    host = host_of(link)
    return any(host == h or host.endswith("." + h) for h in JURA_HOSTS)


def _strip_links(text: str) -> str:
    text = MD_LINK_RE.sub(r"\1", text)
    text = EMAIL_RE.sub(" ", text)
    text = URL_RE.sub(" ", text)
    return BARE_DOMAIN_RE.sub(" ", text)


def _markdown_headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", text, re.M)]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][\w'’-]*", text)


def _excerpt(text: str, start: int, end: int, pad: int = 30) -> str:
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    snippet = text[left:right].replace("\n", " ").strip()
    return ("…" if left > 0 else "") + snippet + ("…" if right < len(text) else "")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


# --- 1. exclamation --------------------------------------------------------


def _exclamation(text: str) -> list[Issue]:
    return [
        Issue("exclamation", "No exclamation marks", _excerpt(text, m.start(), m.end()))
        for m in re.finditer(r"!", text)
    ]


# --- 2. emoji --------------------------------------------------------------

EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoticons, transport, flags, supplemental
    "☀-➿"  # misc symbols and dingbats
    "⌚⌛⌨⏏⏩-⏳⏸-⏺"
    "⬅-⬇⬛⬜⭐⭕"
    "〰〽㊗㊙"
    "️⃣"  # variation selector, keycap
    "]"
)
EMOTICON_RE = re.compile(
    r"(?:(?<=\s)|^)"
    r"(?:[:;=][-o*']?[)\](\[dDpP/\\|@3*]|[)\](\[][-o*']?[:;=]|<3|\^_\^|\^\^|[xX]D|o_O|O_o|T_T|>_<|:-?\|)"
    r"(?=\s|$|[.,?])",
    re.M,
)


def _emoji(text: str) -> list[Issue]:
    issues = [
        Issue("emoji", "No emoji", _excerpt(text, m.start(), m.end())) for m in EMOJI_RE.finditer(text)
    ]
    issues += [
        Issue("emoji", "No text emoticons", m.group(0)) for m in EMOTICON_RE.finditer(text)
    ]
    return issues


# --- 3. buzzwords ----------------------------------------------------------


@lru_cache(maxsize=None)
def _buzzword_patterns() -> tuple[tuple[str, re.Pattern], ...]:
    patterns = []
    for word in config.read_lines("buzzwords.txt"):
        parts = [re.escape(p) for p in re.split(r"[\s-]+", word.lower()) if p]
        body = r"[\s-]+".join(parts)
        patterns.append(
            (word, re.compile(rf"(?<![\w-]){body}(?:s|es|d|ed|ing|ly|er|ers)?(?![\w])", re.I))
        )
    return tuple(patterns)


def _buzzwords(text: str) -> list[Issue]:
    issues = []
    for word, pattern in _buzzword_patterns():
        for m in pattern.finditer(text):
            issues.append(Issue("buzzword", f"Buzzword “{word}”", _excerpt(text, m.start(), m.end())))
    return issues


# --- 4. urgency ------------------------------------------------------------

URGENCY = [
    r"limited (?:spots?|places?|seats?|slots?|time|offer|availability)",
    r"act (?:now|fast|today)",
    r"only today",
    r"today only",
    r"\bhurry\b",
    r"don'?t miss (?:out|this)",
    r"last chance",
    r"(?:ends|ending|expires?|expiring) (?:soon|today|tonight|at midnight)",
    r"while (?:stocks|supplies) last",
    r"before it'?s too late",
    r"\b(?:spots?|places?|seats?|slots?) (?:left|remaining)\b",
    r"\bcount ?down\b",
    r"\b\d+ (?:hours?|days?) left\b",
    r"\b(?:book|buy|sign up|register|call) now\b",
    r"now or never",
    r"once in a lifetime",
    r"time is running out",
    r"first come,? first served",
    r"\bfor a limited\b",
    r"\bdon'?t wait\b",
]
URGENCY_RE = re.compile("|".join(f"(?:{p})" for p in URGENCY), re.I)


def _urgency(text: str) -> list[Issue]:
    return [
        Issue("urgency", "No manufactured urgency", _excerpt(text, m.start(), m.end()))
        for m in URGENCY_RE.finditer(text)
    ]


# --- 5. rhetorical questions -----------------------------------------------


def _questions(subject: str | None, headings: list[str]) -> list[Issue]:
    issues = []
    if subject and "?" in subject:
        issues.append(Issue("question", "Subject lines are statements, not questions", subject))
    for heading in headings:
        if "?" in heading:
            issues.append(Issue("question", "Headings are statements, not questions", heading))
    return issues


# --- 6. rhythm -------------------------------------------------------------

DASH_RE = re.compile(r"—|\s--\s|\s–\s")
THIS_NOT_THAT = [
    re.compile(r",\s+not\s+(?:just\s+|only\s+|merely\s+)?(?:a\s+|an\s+|the\s+)?[\w'’-]+(?:\s+[\w'’-]+){0,3}\s*(?:[.;:?]|$)", re.I | re.M),
    re.compile(r"\bnot\s+(?:just|only|merely)\s+[^.;\n]{1,60}?,?\s+but\b", re.I),
    re.compile(r"\b(?:is|it's|it is|isn'?t|aren'?t)\s+(?:not\s+)?(?:about|just)\s+[^.;\n]{1,60}?[.;]\s*(?:it'?s|it is)\s+about\b", re.I),
    re.compile(r"\bnot\s+because\b[^.\n]{1,60}\bbut\s+because\b", re.I),
]


def _rhythm(text: str) -> list[Issue]:
    issues = []
    words = len(re.findall(r"\b\w+\b", text))
    dashes = len(DASH_RE.findall(text))
    allowed = max(1, words // 60)
    if dashes > allowed:
        issues.append(
            Issue("rhythm", f"{dashes} em dashes in {words} words; keep to one per 60 words")
        )
    for pattern in THIS_NOT_THAT:
        for m in pattern.finditer(text):
            issues.append(
                Issue("rhythm", "Rewrite the “this, not that” construction", _excerpt(text, m.start(), m.end()))
            )
    return issues


# --- 7. numbers ------------------------------------------------------------
#
# Figures that never count: dates, times, years, identifiers (APP-001, A4),
# anything inside a URL or email address, and the approved claim phrases.
#
# For each remaining figure, by sentence:
#   - a sentence about Jura (Jura, we, our, us) must use an approved claim;
#   - on a channel that carries news, a figure in a sentence not about Jura is
#     allowed when the text cites a third-party source;
#   - a statutory rate (GST, CPF, levy, tax) is allowed with an official
#     .gov.sg source link;
#   - a figure next to results language (saved, faster, ROI, clients, %,
#     revenue, go live...) needs one of the above;
#   - otherwise, an interface quantity ("up to 3 files", "4 MB", "30 days")
#     or a small count ("5 tips") is fine, and anything else needs a source.
#
# A figure written in words follows the same rules, read to its value: from
# "two" up, when it counts a following noun ("twelve businesses", "forty of
# our clients", "a dozen firms"). "One", "a" on its own, a number word that
# counts nothing ("one or two", "the two you picked") and a hyphenated
# compound ("two-step", "nine-to-five") are not figures.
#
# The visitor's own inputs are never brand-checked, so they never reach here.

MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
EXEMPT_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:?\d{2}|Z)?)?\b"),
    re.compile(r"\b\d{4}-W\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}(?:\s+\d{{4}})?\b", re.I),
    re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b", re.I),
    re.compile(rf"\b{MONTHS}\s+\d{{4}}\b", re.I),
    re.compile(r"\b\d{1,2}:\d{2}\s?(?:am|pm|sgt)?\b", re.I),
    re.compile(r"\b\d{1,2}\.\d{2}\s?(?:am|pm)\b", re.I),
    re.compile(r"\b\d{1,2}\s?(?:am|pm)\b", re.I),
    # a year, unless it counts something ("2000 businesses" is a claim)
    re.compile(
        r"\b(?:19|20)\d{2}\b(?!\s*[%+]|\s+(?:[a-z]+\s+)?(?:businesses|clients|companies|customers|"
        r"users|people|teams|firms|smes|hours|jobs|invoices|receipts|documents|emails|leads|"
        r"projects|automations|staff|employees|members|downloads|visitors|orders)\b)",
        re.I,
    ),
    re.compile(r"\b(?:Q[1-4]|H[12]|FY\d{2,4})\b"),
    # identifiers: letters fused to digits (APP-001, A4, GPT-5, B2B, T-0042)
    re.compile(r"\b[A-Za-z]{1,10}-?\d+(?:[-.]\d+)*[A-Za-z]*\b"),
    re.compile(r"\b\d+[A-Za-z]*-[A-Za-z]+\b"),  # 2-step, 3-way
]
FIGURE_RE = re.compile(
    r"(?:S\$|US\$|\$|SGD\s?|USD\s?)?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|per\s?cent)|x\b|k\b|m\b|bn\b)?\+?",
    re.I,
)
# A count this small ("5 tips", "five tips") needs no source outside a claim.
SMALL_COUNT_MAX = 12
# Quantities with no exact value: flagged only in a claim about Jura or its results.
SCALE_WORDS = {"dozen": 12, "hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_SCALES = "|".join(SCALE_WORDS)
VAGUE_FIGURE_RE = re.compile(
    rf"\b(?:dozens|hundreds|thousands|millions|billions|twice|double|triple|tenfold|half"
    rf"|(?:several|many|some|a\s+few|a\s+couple\s+of)\s+(?:{_SCALES}))\b(?!-)",
    re.I | re.A,
)
# Exact figures written as words: "twelve", "forty-five", "a dozen", "a hundred
# and fifty", "two thousand". Each is read to its value. ASCII only, so a
# lookalike letter ("ſixty") never reaches the value lookup.
_UNITS = "one two three four five six seven eight nine".split()
_TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
NUMBER_WORDS = (
    {word: value for value, word in enumerate(_UNITS + _TEENS, start=1)}
    | {word: 10 * tens for tens, word in enumerate(_TENS, start=2)}
)
_LARGE_SCALES = "|".join(word for word, value in SCALE_WORDS.items() if value >= 1_000)
_BELOW_100 = rf"(?:(?:{'|'.join(_TENS)})(?:[\s-]+(?:{'|'.join(_UNITS)}))?|{'|'.join(_TEENS)}|{'|'.join(_UNITS)})"
_BELOW_1000 = rf"(?:(?:an?|{_BELOW_100})\s+hundred(?:\s+(?:and\s+)?{_BELOW_100})?|{_BELOW_100})"
_CARDINAL = (
    rf"(?:(?:an?|{_BELOW_1000})\s+(?:{_LARGE_SCALES})(?:\s+(?:and\s+)?{_BELOW_1000})?"
    rf"|(?:an?|{_BELOW_100})\s+dozen"
    rf"|{_BELOW_1000})"
)
CARDINAL_WORDS_RE = re.compile(rf"\b{_CARDINAL}\b", re.I | re.A)
# Whether a number word counts a noun ("twelve businesses", "twelve of our
# clients", "forty per cent") is read from the words after it:
#   - a hedge is skipped to reach the noun ("twelve or more businesses",
#     "two or three processes"), but "one or two" hedges towards "one" and
#     claims nothing;
#   - "the two of you", "the three of us" count no figure; without "the" in
#     front ("twelve of us", "forty of them") it is a count like any other;
#   - a common verb after "the two", "these two", "both", "all" is a verb
#     ("these two matter most"), but after a possessive it is a noun ("our
#     forty sync jobs");
#   - any word in COUNTS_NOTHING_AFTER means it counts nothing ("the two you
#     picked", "those two are").
# Known limits: a noun before the number ("a team of five"), "zero", ordinals
# ("our fortieth client"), other verbs after a number ("two businesses I spoke
# to" counts, as it should; "the two overlap" counts too) and suffix compounds
# ("forty-odd", "twenty-plus", shared with the digit path).
NEXT_WORD_RE = re.compile(r"\s+([A-Za-z][\w'’]*)", re.A)
HEDGE_RE = re.compile(rf"\s+or\s+(?:more|so|fewer|less|over|{_CARDINAL})\b", re.I | re.A)
ONE_OR_BEFORE_RE = re.compile(r"\bone\s+or\s+$", re.I)
OF_PEOPLE_RE = re.compile(r"\s+of\s+(?:you|us|them)\b", re.I)
THE_BEFORE_RE = re.compile(r"\bthe\s+$", re.I)
DETERMINER_BEFORE_RE = re.compile(r"\b(?:the|these|those|both|all)\s+$", re.I)
VERBS_AFTER_A_NUMBER = frozenset(
    "matter work fit go come seem stand belong sit differ happen apply help need make take share "
    "look run show mean cover connect talk sync link add cost".split()
)
COUNTS_NOTHING_AFTER = frozenset(
    """
    a an the and or nor but so yet than then if
    to in on at by for from with into onto about after before over under between
    is are was were be been being am has have had do does did
    will would can could should shall may might must
    i you he she it we they me him her us them this that these those who whom which what whose
    my your his its our their o'clock pm
    """.split()
)
# "we're" needs its apostrophe ("were", "well" and "wed" are not Jura), and
# "us" is lower case only ("US" is the country).
JURA_SELF_RE = re.compile(r"\b(?:jura|we|we['’](?:ve|re|ll|d)|our|ours|(?-i:us))\b", re.I)
RESULT_RE = re.compile(
    r"%|\bper ?cent\b|\bpercent\b|\b(?:sav(?:e|es|ed|ing|ings)|faster|quicker|cut|cuts|reduc\w*|"
    r"increas\w*|boost\w*|grow\w*|improv\w*|roi|return on|revenue|profit\w*|clients?|customers?|"
    r"businesses|companies|firms|efficien\w*|productiv\w*|accura\w*|errors?|mistakes|"
    r"guarantee\w*|go(?:es)? live|launch\w*|turnaround|deliver\w*|results?|outcomes?|trusted)\b",
    re.I,
)
STATUTORY_RE = re.compile(r"\b(?:gst|cpf|levy|levies|tax|iras|mom|statutory|sdl|contribution rate)\b", re.I)
INTERFACE_UNIT_RE = re.compile(
    r"^\s*(?:free\s+|more\s+|new\s+)?(?:mb|kb|gb|px|pixels?|files?|receipts?|photos?|images?|tries|try|"
    r"items?|lines?|characters?|chars|words?|pages?|decimal places?|digits?|columns?|rows?|"
    r"days?|weeks?|months?|minutes?|seconds?|steps?|questions?|fields?|tools?|tips?|ways?|"
    r"things?|ideas?|platforms?|posts?|groups?|templates?|layouts?|cards?|slides?|"
    r"places?|categories|formats?|pdfs?|documents?|docs?|invoices?|quotes?|quotations?|"
    r"contacts?|entries|records?|sheets?|tabs?)\b",
    re.I,
)


INPUT_HINT_RE = re.compile(
    r"^\s*(?:use|enter|type|add|pick|choose|set|write)\b[^.]*\b(?:like|for example|e\.g\.|such as|from \d|between \d|up to \d)",
    re.I,
)


@lru_cache(maxsize=None)
def approved_phrases() -> tuple[str, ...]:
    path = paths.config_dir() / "approved_claims.yaml"
    if not path.exists():
        return ()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    phrases = []
    for claim in data.get("claims", []):
        phrases += claim.get("match", [])
    return tuple(phrases)


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _without_exempt(text: str) -> str:
    for link in sorted(set(find_links(text)), key=len, reverse=True):
        text = text.replace(link, " " * len(link))
    text = EMAIL_RE.sub(lambda m: " " * len(m.group(0)), text)
    for phrase in approved_phrases():
        pattern = re.compile(r"\s+".join(re.escape(p) for p in phrase.split()), re.I)
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    for pattern in EXEMPT_PATTERNS:
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def _numbers(text: str, chosen: Channel, sources: list[str]) -> list[Issue]:
    links = find_links(text) + list(sources)
    third_party = [link for link in links if not is_jura(link)]
    official = any(host_of(link).endswith(".gov.sg") or host_of(link) == "gov.sg" for link in links)
    news_ok = chosen.allow_sources and bool(third_party)

    issues = []
    cleaned = _without_exempt(text)
    for sentence in sentences(cleaned):
        figures = [
            _Figure(m, m.group(0).strip(), _is_small_count(m.group(0).strip()))
            for m in FIGURE_RE.finditer(sentence)
            if re.search(r"\d", m.group(0))
        ]
        figures += [
            _Figure(m, m.group(0), value <= SMALL_COUNT_MAX)
            for m in CARDINAL_WORDS_RE.finditer(sentence)
            if (value := _number_value(m.group(0))) >= 2 and _counts_a_noun(sentence, m, value)
        ]
        words = list(VAGUE_FIGURE_RE.finditer(sentence))
        if not figures and not words:
            continue
        about_jura = bool(JURA_SELF_RE.search(sentence))
        results = bool(RESULT_RE.search(sentence))
        statutory = bool(STATUTORY_RE.search(sentence)) and official
        # "Use a number, like 120.50." Example inputs in a form hint are not claims.
        input_hint = bool(INPUT_HINT_RE.search(sentence)) and not results

        for m, figure, small in figures:
            if statutory and not about_jura:
                continue
            if about_jura:
                issues.append(Issue("numbers", "A figure about Jura must be an approved claim", sentence.strip()))
            elif news_ok:
                continue
            elif results:
                issues.append(Issue("numbers", f"“{figure}” in a results claim with no source", sentence.strip()))
            elif _is_interface_quantity(sentence, m) or small or input_hint:
                continue
            else:
                issues.append(Issue("numbers", f"“{figure}” needs a source", sentence.strip()))
        for m in words:
            if about_jura or (results and not news_ok):
                issues.append(Issue("numbers", f"“{m.group(0)}” reads as an unevidenced figure", sentence.strip()))
    return _dedupe(issues)


def _is_interface_quantity(sentence: str, match: re.Match) -> bool:
    return bool(INTERFACE_UNIT_RE.match(sentence[match.end():]))


class _Figure(NamedTuple):
    match: re.Match
    text: str
    small: bool


def _number_value(phrase: str) -> int:
    """"a hundred and fifty" -> 150, "forty-five" -> 45, "two dozen" -> 24."""
    total = current = 0
    for word in re.findall(r"[a-z]+", phrase.lower()):
        if word in ("a", "an"):
            current = 1
        elif word in SCALE_WORDS and SCALE_WORDS[word] < 1_000:  # dozen, hundred
            current = (current or 1) * SCALE_WORDS[word]
        elif word in SCALE_WORDS:
            total += (current or 1) * SCALE_WORDS[word]
            current = 0
        elif word != "and":
            current += NUMBER_WORDS[word]
    return total + current


def _counts_a_noun(sentence: str, match: re.Match, value: int) -> bool:
    before, start = sentence[: match.start()], match.end()
    # Fused by a hyphen ("two-step", "nine-to-five"), it is part of a word,
    # as "2-step" and "9-to-5" are for digits.
    if before.endswith("-") or sentence[start : start + 1] == "-":
        return False
    if value == 2 and ONE_OR_BEFORE_RE.search(before):
        return False
    hedge = HEDGE_RE.match(sentence, start)
    if hedge:
        start = hedge.end()
    if THE_BEFORE_RE.search(before) and OF_PEOPLE_RE.match(sentence, start):
        return False
    following = NEXT_WORD_RE.match(sentence, start)
    if not following:
        return False
    word = following.group(1).lower().replace("’", "'")
    if word in VERBS_AFTER_A_NUMBER and DETERMINER_BEFORE_RE.search(before):
        return False
    return word not in COUNTS_NOTHING_AFTER and word not in NUMBER_WORDS and word not in SCALE_WORDS


def _is_small_count(figure: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", figure)) and int(figure) <= SMALL_COUNT_MAX


def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen, unique = set(), []
    for issue in issues:
        key = (issue.rule, issue.message, issue.excerpt)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


# --- 8. sentence case ------------------------------------------------------


@lru_cache(maxsize=None)
def _proper_nouns() -> frozenset[str]:
    return frozenset(config.read_lines("proper_nouns.txt"))


def _sentence_case(subject, headings, buttons, nouns) -> list[Issue]:
    issues = []
    labelled = [("Subject line", subject)] if subject else []
    labelled += [("Heading", h) for h in headings] + [("Button", b) for b in buttons]
    for label, value in labelled:
        problem = sentence_case_problem(value, nouns)
        if problem:
            issues.append(Issue("sentence-case", f"{label} should be sentence case ({problem})", value))
    return issues


def sentence_case_problem(value: str, nouns: Iterable[str] = ()) -> str | None:
    nouns = set(nouns) | _proper_nouns()
    clauses = re.split(r"[:—]\s*", value)
    words = _words(value)
    if not words:
        return None
    first = words[0]
    if first[0].islower() and not re.match(r"^[a-z]+[A-Z]", first):  # allow iPhone, eBay
        return "starts in lower case"
    rest = []
    for clause in clauses:
        rest += _words(clause)[1:]
    considered = [w for w in rest if not _case_exempt(w, nouns)]
    capitalised = [w for w in considered if w[0].isupper()]
    if not capitalised:
        return None
    if len(considered) <= 2 and len(capitalised) == len(considered):
        return "reads as Title Case"
    if len(capitalised) >= 2 and len(capitalised) * 2 > len(considered):
        return "reads as Title Case"
    return None


def _case_exempt(word: str, nouns: set[str]) -> bool:
    bare = word.strip("'’-")
    if len(bare) >= 2 and (bare.isupper() or bare.removesuffix("s").isupper()):
        return True
    if any(ch.isdigit() for ch in bare):
        return True
    if bare in nouns or bare.rstrip("s") in nouns or bare.removesuffix("'s") in nouns:
        return True
    return False


# --- 9. links --------------------------------------------------------------


def _normalise(link: str) -> str:
    candidate = link if re.match(r"^https?://", link, re.I) else f"https://{link}"
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


def _links(text: str, chosen: Channel, sources: list[str]) -> list[Issue]:
    declared = {_normalise(s) for s in sources}
    issues = []
    for link in find_links(text):
        if is_jura(link):
            continue
        if not chosen.allow_sources:
            issues.append(Issue("links", "Links only to jurasolutions.sg on this channel", link))
        elif not declared:
            issues.append(Issue("links", "Declare each third-party link as a cited source", link))
        elif _normalise(link) not in declared:
            issues.append(Issue("links", "Link is not one of the cited sources", link))
    return issues
