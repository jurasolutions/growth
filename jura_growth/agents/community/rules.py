"""Reading a group's promotion rules well enough to plan around them.

Simple rules parse into days: "promo Saturdays only", "self-promotion on
Fridays", "ads on weekends", "posts Mon to Fri only", "no promotion except
Sunday thread". Some parse into a ban: "no self-promo", "no links". Rules the
parser can't read are still "known": a plan item for that group must then
say in `rules_ok` why its day and content fit the rules.

Empty rules, or "unknown" / "not stated", mean unknown: the post carries no
link (community scout PRD §5.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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
POST_RE = re.compile(r"\bpost(?:s|ing)?\b", re.I)
NEG_RE = re.compile(
    r"\b(?:no|not allowed|not permitted|prohibited|banned|forbidden|disallowed|strictly no|don'?t|do not|never|zero)\b",
    re.I,
)
EXCEPT_RE = re.compile(r"\b(?:except|other than|apart from|unless|outside of|save for|only)\b", re.I)
ALLOWED_RE = re.compile(r"\b(?:allowed|welcome[ds]?|ok|okay|permitted|fine|encouraged|can|may)\b", re.I)


@dataclass
class Rules:
    text: str
    known: bool
    parsed: bool
    promo_days: frozenset[int] | None = None  # promotion only on these days; None = no day limit stated
    post_days: frozenset[int] | None = None  # any post only on these days; None = no day limit stated
    no_promo: bool = False
    no_links: bool = False
    promo_allowed: bool = False  # rules say promotion is fine (any day, or on promo_days)
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
        }

    def summary(self) -> str:
        if not self.known:
            return "rules unknown: value post, no link"
        if not self.parsed:
            return "rules could not be read in code; state why the day and post fit them (rules_ok)"
        parts = []
        if self.post_days is not None:
            parts.append("posts only on " + ", ".join(day_names(self.post_days)))
        if self.no_promo:
            parts.append("no promotion")
        elif self.promo_days is not None:
            parts.append("promotion only on " + ", ".join(day_names(self.promo_days)))
        elif self.promo_allowed:
            parts.append("promotion allowed")
        if self.no_links:
            parts.append("no links")
        return "; ".join(parts) or "no restriction found"


def day_names(days: frozenset[int] | None) -> list[str] | None:
    return None if days is None else [WEEKDAYS[d] for d in sorted(days)]


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
            found.update(range(7))
    return frozenset(found) if found else None


def parse(text: str | None) -> Rules:
    raw = (text or "").strip()
    if not raw or UNKNOWN_RE.match(raw):
        return Rules(raw, known=False, parsed=True)
    rules = Rules(raw, known=True, parsed=False)
    promo_days: set[int] = set()
    post_days: set[int] = set()
    for clause in re.split(r"[.;\n]+|\s\|\s", raw):
        clause = clause.strip()
        if not clause:
            continue
        days = days_in(clause)
        promo = bool(PROMO_RE.search(clause))
        link = bool(LINK_RE.search(clause))
        negative = bool(NEG_RE.search(clause))
        if promo:
            if days:
                promo_days |= days
                rules.promo_allowed = True
                rules.parsed = True
            elif negative:
                rules.no_promo = True
                rules.parsed = True
            elif ALLOWED_RE.search(clause):
                rules.promo_allowed = True
                rules.parsed = True
        if link:
            if days and not promo:
                promo_days |= days
                rules.parsed = True
            elif negative and not days:
                rules.no_links = True
                rules.parsed = True
            elif ALLOWED_RE.search(clause) and not promo:
                rules.parsed = True
        if not promo and not link and POST_RE.search(clause) and days:
            post_days |= days
            rules.parsed = True
    if promo_days:
        rules.promo_days = frozenset(promo_days)
        rules.no_promo = False
    if post_days:
        rules.post_days = frozenset(post_days)
    return rules


def day_problem(rules: Rules, weekday: int, *, promotional: bool) -> str | None:
    """Why a post on `weekday` breaks the rules, or None."""
    if rules.post_days is not None and weekday not in rules.post_days:
        return f"the group allows posts only on {', '.join(day_names(rules.post_days))}"
    if promotional and rules.promo_days is not None and weekday not in rules.promo_days:
        return f"the group allows promotion only on {', '.join(day_names(rules.promo_days))}"
    return None
