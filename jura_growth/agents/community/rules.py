"""Reading a group's promotion rules well enough to plan around them.

No group is plannable until Ting Yu has said which days are open, typed in his
`group-rules` decision in #approvals (`/growth approve A-nnnn promo_days=...
post_days=...`, then `confirm_days`), whatever its rules text says. Code never
reads days out of English rules: day, frequency and holiday rules are too easy
to invert or miss, and a forbidden day
can get Ting Yu removed from the group. `mentions_timing` only flags rules that
seem to talk about timing, as a hint to read them carefully; it never opens a day.

Rules that name no day still parse into bans or permissions: "no self-promo",
"no links", "self-promotion is welcome". A links ban stated beside a day rule is
kept too, because confirming days doesn't confirm links. Rules the parser can't
read are still "known": a plan item for that group must then say in `rules_ok`
why its day and content fit the rules.

Empty rules, or "unknown" / "not stated", mean unknown: the post carries no
link (community scout PRD §5.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "weds": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}
DAY = r"(?:monday|mon|tuesday|tues|tue|wednesday|weds|wed|thursday|thurs|thur|thu|friday|fri|saturday|sat|sunday|sun)s?"
DAY_RE = re.compile(rf"\b{DAY}\b", re.I)
RANGE_RE = re.compile(rf"\b(?P<a>{DAY})\s*(?:-|–|—|to|through|thru|till|until)\s*(?P<b>{DAY})\b", re.I)
GROUPS_RE = re.compile(r"\b(?P<g>weekends?|weekdays?|every day|everyday|daily|any day)\b", re.I)
ANY_DAY_RE = re.compile(rf"{RANGE_RE.pattern}|{DAY_RE.pattern}|{GROUPS_RE.pattern}", re.I)
# Deliberately loose, because it only drives a hint: day names inside hashtags
# (#FridayPromo), wknd/wkend, weeknights, "week days", frequency and holidays.
TIMING_RE = re.compile(
    rf"(?:mon|tues|wednes|thurs|fri|satur|sun)day|{ANY_DAY_RE.pattern}"
    r"|\bw(?:ee)?ke?nds?\b|\bweek\s*(?:days?|nights?|ends?)\b"
    r"|\b(?:once|twice|\d+\s*(?:x|times))\s+(?:a|per|each|every)\b|\b(?:weekly|fortnightly|monthly)\b"
    r"|\bmonths?\b|\bholidays?\b|\bthreads?\b|\b\d{1,2}(?:st|nd|rd|th)\b",
    re.I,
)
TIMING_HINT = "the rules mention timing, so check the day against them"
ALL_DAYS = frozenset(range(7))

UNKNOWN_RE = re.compile(
    r"^\s*(?:unknown|not (?:publicly )?(?:stated|known|found|listed)|none (?:found|stated|listed)|"
    r"no (?:public|stated|published) rules|n/?a|tbc|to be confirmed)\b",
    re.I,
)
PROMO_RE = re.compile(
    r"\b(?:promo(?:s|tion(?:s|al)?)?|self[- ]?promo(?:tion(?:al)?)?|advert(?:s|ising|isements?)?|ads?|"
    r"selling|sales posts?|marketing|business posts?|plugs?|shameless plugs?|soliciting|solicitation)\b",
    re.I,
)
LINK_RE = re.compile(r"\b(?:links?|urls?)\b", re.I)
NEG_RE = re.compile(
    r"\b(?:no|not allowed|not permitted|prohibited|banned|forbidden|disallowed|strictly no|do not|never|zero|"
    r"don['’]?t|can(?:not|['’]?t)|can not|may not|must not|should not|"
    r"\w+n['’]t(?:\s+be)?(?:\s+(?:allowed|permitted))?)\b",  # isn't (allowed), aren't, won't, mustn't ...
    re.I,
)
LINK_NEG_RE = re.compile(rf"{NEG_RE.pattern}|\bnot\b", re.I)
CLAUSE_BREAK_RE = re.compile(r"[,:;()–—]|\s-\s|\b(?:but|and)\b", re.I)
ALLOWED_RE = re.compile(r"\b(?:allowed|welcome[ds]?|ok|okay|permitted|fine|encouraged|can|may)\b", re.I)
CONFIRM_HINT = (
    "confirm its rules in #approvals: jura-growth community set <id> rules_confirmed=yes, "
    "then /growth approve A-nnnn promo_days=... post_days=..."
)
UNCONFIRMED = f"no post until Ting Yu confirms the open days ({CONFIRM_HINT})"


@dataclass
class Rules:
    text: str
    known: bool
    parsed: bool
    promo_days: frozenset[int] | None = None  # promotion only on these days; None = no day limit
    post_days: frozenset[int] | None = None  # any post only on these days; None = no day limit
    no_promo: bool = False
    no_links: bool = False
    promo_allowed: bool = False  # rules say promotion is fine
    mentions_timing: bool = False  # a hint for whoever reads the rules; never opens a day
    days_confirmed: bool = False  # promo_days and post_days come from Ting Yu (`confirm_days`)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "known": self.known,
            "parsed": self.parsed,
            "promo_days": day_names(self.promo_days),
            "post_days": day_names(self.post_days),
            "no_promo": self.no_promo,
            "no_links": self.no_links,
            "promo_allowed": self.promo_allowed,
            "mentions_timing": self.mentions_timing,
            "days_confirmed": self.days_confirmed,
        }

    def summary(self) -> str:
        if not self.days_confirmed:
            return UNCONFIRMED
        if not self.known:
            return "rules unknown: value post, no link"
        if not self.parsed:
            return "rules could not be read in code; state why the day and post fit them (rules_ok)"
        parts = []
        if self.post_days is not None:
            parts.append(_posts_only_on(self.post_days))
        if self.no_promo:
            parts.append("no promotion")
        elif self.promo_days is not None:
            parts.append("promotion only on " + ", ".join(day_names(self.promo_days) or []))
        elif self.promo_allowed:
            parts.append("promotion allowed")
        if self.no_links:
            parts.append("no links")
        return "; ".join(parts) or "no restriction found"


def day_names(days: frozenset[int] | None) -> list[str] | None:
    return None if days is None else [WEEKDAYS[d] for d in sorted(days)]


def _posts_only_on(days: frozenset[int]) -> str:
    return "posts only on " + ", ".join(day_names(days) or []) if days else "no posts on any day"


def _day(token: str) -> int:
    word = token.lower().rstrip(".")
    if word not in DAY_NAMES and word.endswith("s"):
        word = word[:-1]
    return DAY_NAMES[word]


def days_in(clause: str) -> frozenset[int] | None:
    found: set[int] = set()
    remaining = clause
    for m in RANGE_RE.finditer(clause):
        a, b = _day(m["a"]), _day(m["b"])
        span = range(a, b + 1) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        found.update(span)
        remaining = remaining.replace(m.group(0), " ")
    for m in DAY_RE.finditer(remaining):
        found.add(_day(m.group(0)))
    for m in GROUPS_RE.finditer(remaining):
        word = m["g"].lower()
        if word.startswith("weekend"):
            found.update({5, 6})
        elif word.startswith("weekday"):
            found.update(range(5))
        else:
            found.update(ALL_DAYS)
    return frozenset(found) if found else None


def read_days(value: str) -> frozenset[int] | None:
    """Days as Ting Yu types them in a `group-rules` decision: "any" (no day limit),
    "none", or days like "sat,sun", "mon-fri", "weekdays". Anything else is refused."""
    text = value.strip().lower()
    if text in ("any", "no limit"):
        return None
    if text in ("none", "no day", "never"):
        return frozenset()
    days = days_in(text)
    leftover = re.sub(r"[\s,/&]+|\band\b", "", ANY_DAY_RE.sub(" ", text))
    if not days or leftover:
        raise ValueError(f"can't read {value!r} as days; use any, none, or days like sat,sun or mon-fri")
    return days


def days_text(days: frozenset[int] | None) -> str:
    """The stored form of `read_days`' result."""
    return "any" if days is None else ",".join(day_names(days) or []) or "none"


def _bans_links_on_every_day(clause: str) -> bool:
    """A negation right before "links" that no day narrows: "Promo Saturdays only, no
    links", "No links, promo on Fridays". "No links on weekends" is left to the
    confirmed days."""
    for link in LINK_RE.finditer(clause):
        negations = list(LINK_NEG_RE.finditer(clause, 0, link.start()))
        if not negations:
            continue
        between = clause[negations[-1].end():link.start()]
        if days_in(between) or PROMO_RE.search(between):
            continue
        after = clause[link.end():]
        day = ANY_DAY_RE.search(after)
        gap = after[:day.start()] if day else ""
        if day is None or CLAUSE_BREAK_RE.search(gap) or PROMO_RE.search(gap):
            return True
    return False


def parse(text: str | None) -> Rules:
    raw = (text or "").strip()
    if not raw or UNKNOWN_RE.match(raw):
        return Rules(raw, known=False, parsed=True)
    rules = Rules(raw, known=True, parsed=False, mentions_timing=bool(TIMING_RE.search(raw)))
    for clause in re.split(r"[.;\n]+|\s\|\s", raw):
        clause = clause.strip()
        if not clause:
            continue
        promo = bool(PROMO_RE.search(clause))
        link = bool(LINK_RE.search(clause))
        negative = bool(NEG_RE.search(clause))
        if days_in(clause):
            rules.parsed = True  # read by Ting Yu instead: his confirmed days replace it
            if link and _bans_links_on_every_day(clause):
                rules.no_links = True
            continue
        if promo and negative:
            rules.no_promo = True
            rules.parsed = True
        elif promo and ALLOWED_RE.search(clause):
            rules.promo_allowed = True
            rules.parsed = True
        if link and negative:
            rules.no_links = True
            rules.parsed = True
        elif link and not promo and ALLOWED_RE.search(clause):
            rules.parsed = True
    return rules


def confirm_days(rules: Rules, promo_days: str | None, post_days: str | None) -> Rules:
    """`rules` with the days Ting Yu confirmed (stored `days_text` values), the only days
    that count. Both must be set, or the group has no open day."""
    if promo_days is None or post_days is None:
        return rules
    promo, posts = read_days(promo_days), read_days(post_days)
    return replace(
        rules,
        days_confirmed=True,
        promo_days=promo or None,
        post_days=posts,
        # named days lift a blanket ban ("No promo. Promo thread on Sundays"); none is no promotion
        no_promo=rules.no_promo if promo is None else not promo,
    )


def day_problem(rules: Rules, weekday: int, *, promotional: bool) -> str | None:
    """Why a post on `weekday` breaks the rules, or None."""
    if not rules.days_confirmed:
        return f"Ting Yu hasn't confirmed which days are open for this group ({CONFIRM_HINT})"
    if rules.post_days is not None and weekday not in rules.post_days:
        return f"the group allows {_posts_only_on(rules.post_days)}"
    if promotional and rules.promo_days is not None and weekday not in rules.promo_days:
        return f"the group allows promotion only on {', '.join(day_names(rules.promo_days) or [])}"
    return None
