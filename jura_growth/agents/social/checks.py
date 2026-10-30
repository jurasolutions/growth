"""Brand-check channels for social posts (rule 10, the channel's own parts).

The core checker (`brand_check.check`) already applies the house rules to every
variant: no exclamation marks, emoji, buzzwords or urgency, the numbers rule,
and links only to jurasolutions.sg or declared sources. These channels add the
platform rules from social PRD §5.3 and the news rules from §4:

    social-linkedin   120–220 words, up to 3 hashtags at the end, links in the post
                      (unused while LinkedIn is switched off, since 2026-10-29)
    social-facebook   60–120 words, 0–2 hashtags at the end, links in the post
    social-instagram  50–120 words, up to 8 hashtags at the end, "Link in bio", no URL
    social-card       the words on an image card: short, no links, no hashtags

On LinkedIn and Facebook every source in `sources.md` must be linked in the
post, and every third-party link must be a declared source. A post that
mentions a grant or scheme carries the eligibility line and (where links are
possible) an official .gov.sg link, and never implies Jura can secure funding.
Quotations stay short. Politics and tragedies are off limits.

Word ranges, hashtag limits and the blocked topics come from
`config/social.yaml`. `jura-growth check --channel social-linkedin --source
<url> --file linkedin.md` runs the same check by hand.
"""

from __future__ import annotations

import re
from functools import partial

from jura_growth import brand_check
from jura_growth.brand_check import Channel, Issue
from jura_growth.agents.social import history
from jura_growth.agents.social.settings import PLATFORMS, Settings, load

HASHTAG_RE = re.compile(r"(?<![\w&/#])#([A-Za-z][A-Za-z0-9_]*)")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*")
LINK_IN_BIO_RE = re.compile(r"\blink in (?:our |the )?bio\b", re.I)
MARKDOWN_RE = [
    (re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__"), "bold markers"),
    (re.compile(r"^\s{0,3}#{1,6}\s+\S", re.M), "a markdown heading"),
    (re.compile(r"\[[^\]\n]+\]\([^)\s]+\)"), "a markdown link"),
    (re.compile(r"^\s*>\s", re.M), "a block quote"),
    (re.compile(r"`[^`\n]+`"), "code formatting"),
]
QUOTE_RE = re.compile(r"“([^”]{1,600})”|\"([^\"\n]{1,600})\"")
GRANT_RE = re.compile(
    r"\b(?:grants?|schemes?|subsid(?:y|ies|ised|ized)|co-fund(?:ing|ed|s)?|PSG|EDG|"
    r"Productivity Solutions Grant|Enterprise Development Grant|SkillsFuture|support levels?)\b",
    re.I,
)
JURA_FUNDING_RE = re.compile(
    r"\b(?:jura|we|our team|us)\b[^.?!\n]{0,40}?"
    r"\b(?:secur\w*|get|gets|getting|obtain\w*|claim\w*|apply for|win|qualify for|guarantee\w*|unlock\w*|handle the application)\b"
    r"[^.?!\n]{0,40}?\b(?:grants?|funding|subsid\w+|schemes?|PSG|EDG|co-funding)\b",
    re.I,
)
JURA_APPROVED_RE = re.compile(
    r"\b(?:jura|we|we['’]re|our)\b[^.?!\n]{0,60}?\b(?:pre-approved|approved vendor|PSG vendor|accredited)\b", re.I
)
GUARANTEED_FUNDING_RE = re.compile(r"\bguarantee\w*\s+(?:a\s+|the\s+|your\s+)?(?:grant|funding|subsidy|approval)\b", re.I)


def _settings() -> Settings:
    return load()


# --- text helpers ------------------------------------------------------------


def strip_links(text: str) -> str:
    for link in sorted(set(brand_check.find_links(text)), key=len, reverse=True):
        text = text.replace(link, " ")
    return text


def strip_hashtags(text: str) -> str:
    return HASHTAG_RE.sub(" ", text)


def word_count(text: str) -> int:
    """Words a reader reads: links and hashtags don't count."""
    return len(WORD_RE.findall(strip_hashtags(strip_links(text))))


def hashtags(text: str) -> list[str]:
    return ["#" + m.group(1) for m in HASHTAG_RE.finditer(text)]


def misplaced_hashtags(text: str) -> list[str]:
    """Hashtags outside the trailing block of hashtag-only lines."""
    lines = text.rstrip().splitlines()
    end = len(lines)
    while end > 0 and (not lines[end - 1].strip() or _hashtag_only(lines[end - 1])):
        end -= 1
    body = "\n".join(lines[:end])
    return hashtags(body)


def _hashtag_only(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not HASHTAG_RE.sub("", stripped).strip(" ,·|")


def long_quotes(text: str, limit: int) -> list[str]:
    found = []
    for m in QUOTE_RE.finditer(text):
        quoted = m.group(1) or m.group(2) or ""
        if len(WORD_RE.findall(quoted)) > limit:
            found.append(quoted)
    return found


def contains(text: str, url: str) -> bool:
    key = history.normalise_url(url)
    return any(history.normalise_url(link) == key for link in brand_check.find_links(text))


def blocked_topic_hits(text: str, topics) -> list[str]:
    hits = []
    for topic in topics:
        pattern = r"(?<![\w-])" + r"[\s-]+".join(re.escape(p) for p in topic.split()) + r"(?![\w-])"
        m = re.search(pattern, text, re.I)
        if m:
            hits.append(m.group(0))
    return hits


# --- the platform channels ---------------------------------------------------


def check_post(platform: str, text: str, ctx: dict) -> list[Issue]:
    settings = _settings()
    rules = settings.platforms[platform]
    sources = [s for s in ctx.get("sources") or [] if s]
    theme = ctx.get("theme") or {}
    issues: list[Issue] = []

    for pattern, what in MARKDOWN_RE:
        m = pattern.search(text)
        if m:
            issues.append(Issue("channel", f"Plain text only: {rules.label} doesn't render {what}", m.group(0)[:60]))

    words = word_count(text)
    low, high = rules.words
    if not low <= words <= high:
        issues.append(Issue("channel", f"{rules.label} posts are {low}–{high} words; this is {words}"))

    tags = hashtags(text)
    if len(tags) > rules.hashtags_max:
        limit = "no hashtags" if rules.hashtags_max == 0 else f"at most {rules.hashtags_max} hashtags"
        issues.append(Issue("channel", f"{rules.label}: {limit}; found {len(tags)}", " ".join(tags)))
    stray = misplaced_hashtags(text)
    if stray:
        issues.append(Issue("channel", "Hashtags go together on the last line", " ".join(stray)))

    links = brand_check.find_links(text)
    third_party = [link for link in links if not brand_check.is_jura(link)]
    declared = {history.normalise_url(s) for s in sources}

    if rules.links == "bio":
        if links:
            issues.append(Issue("channel", f"{rules.label} captions carry no links; write “Link in bio” instead", links[0]))
        if not LINK_IN_BIO_RE.search(text):
            issues.append(Issue("channel", f"{rules.label} captions say “Link in bio” where the link would go"))
    else:
        if not links:
            issues.append(Issue("channel", f"{rules.label} posts carry a link in the post (a source or jurasolutions.sg)"))
        if not declared:  # with sources declared, the core links rule already covers this
            for link in third_party:
                issues.append(Issue("channel", "Every third-party link must be listed in sources.md", link))
        for source in sources:
            if not contains(text, source):
                issues.append(Issue("channel", "Link every source you list in sources.md", source))
        tool_url = ctx.get("tool_url")
        if tool_url and not contains(text, tool_url):
            issues.append(Issue("channel", "Link the tool you feature", tool_url))

    if theme.get("news") and not sources:
        issues.append(Issue("channel", "News posts cite their sources (list them in sources.md)"))

    quotes = long_quotes(text, settings.max_quote_words)
    for quoted in quotes:
        issues.append(
            Issue("channel", f"Quote at most a short phrase ({settings.max_quote_words} words); say the rest in your own words", quoted[:80])
        )

    for hit in blocked_topic_hits(strip_links(text), settings.blocked_topics):
        issues.append(Issue("channel", "Off-limits topic for Jura's pages (politics, elections, tragedies)", hit))

    issues += _grant_rules(text, rules.links, settings)
    return issues


def _grant_rules(text: str, link_mode: str, settings: Settings) -> list[Issue]:
    plain = strip_links(text)
    issues = []
    for sentence in brand_check.sentences(plain):
        if GUARANTEED_FUNDING_RE.search(sentence) or JURA_FUNDING_RE.search(sentence) or JURA_APPROVED_RE.search(sentence):
            issues.append(Issue("channel", "Never imply Jura can secure or guarantee funding", sentence.strip()[:120]))
    if not GRANT_RE.search(plain):
        return issues
    line = settings.eligibility_line
    if not re.search(r"\s+".join(re.escape(w) for w in line.split()), text, re.I):
        issues.append(Issue("channel", f"A post about a grant or scheme includes “{line}”"))
    if link_mode == "post":
        official = [
            link for link in brand_check.find_links(text)
            if brand_check.host_of(link).endswith(".gov.sg") or brand_check.host_of(link) == "gov.sg"
        ]
        if not official:
            issues.append(Issue("channel", "A post about a grant or scheme links the official .gov.sg page"))
    return issues


# --- the card channel --------------------------------------------------------


def check_card(text: str, ctx: dict) -> list[Issue]:
    settings = _settings()
    issues: list[Issue] = []
    every = "\n".join([*(ctx.get("headings") or []), text])
    links = brand_check.find_links(every)
    if links:
        issues.append(Issue("channel", "Image cards carry no links (the card prints jurasolutions.sg itself)", links[0]))
    if hashtags(every):
        issues.append(Issue("channel", "Image cards carry no hashtags", " ".join(hashtags(every))))
    for pattern, what in MARKDOWN_RE:
        m = pattern.search(every)
        if m:
            issues.append(Issue("channel", f"Image card text is plain: no {what}", m.group(0)[:60]))
    for hit in blocked_topic_hits(every, settings.blocked_topics):
        issues.append(Issue("channel", "Off-limits topic for Jura's pages (politics, elections, tragedies)", hit))
    return issues


def channels() -> dict[str, Channel]:
    found = {
        f"social-{name}": Channel(
            f"social-{name}",
            allow_sources=True,
            check=partial(check_post, name),
            description=f"Social post for {name} (social PRD §5.3)",
        )
        for name in PLATFORMS
    }
    found["social-card"] = Channel(
        "social-card",
        allow_sources=True,
        check=check_card,
        description="Words on a social image card",
    )
    return found
