"""Reading a group's promotion rules well enough to plan around them.

Simple rules parse into days: "promo Saturdays only", "self-promotion on
Fridays", "ads on weekends", "posts Mon to Fri only", "no promotion except
Sunday thread". A rule that bans days leaves the others open: "no promotion
on weekends" means promotion Monday to Friday. Some parse into a ban: "no
self-promo", "no links". Rules the parser can't read, including a clause that
both permits and bans days, are still "known": a plan item for that group must
then say in `rules_ok` why its day and content fit the rules.

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
    r"\b(?:no|not allowed|not permitted|prohibited|banned|forbidden|disallowed|strictly no|do not|never|zero|"
    r"don['’]?t|can(?:not|['’]?t)|can not|may not|must not|should not|"
    r"\w+n['’]t(?:\s+be)?(?:\s+(?:allowed|permitted))?)\b",  # isn't (allowed), aren't, won't, mustn't ...
    re.I,
)
# In a clause that names days a bare "not" counts too ("promo on weekdays, not weekends"):
# reading a ban as a permission is the mistake that gets a member removed.
DAY_NEG_RE = re.compile(rf"{NEG_RE.pattern}|\bnot\b", re.I)
EXCEPT_RE = re.compile(r"\b(?:except|other than|apart from|unless|outside of|save for|only)\b", re.I)
ALLOWED_RE = re.compile(r"\b(?:allowed|welcome[ds]?|ok|okay|permitted|fine|encouraged|can|may)\b", re.I)
SUBJECT_RE = re.compile(rf"{PROMO_RE.pattern}|{LINK_RE.pattern}|{POST_RE.pattern}", re.I)
DAY_PHRASE = rf"(?:{DAY}\s*(?:-|–|—|to|through|thru|till|until)\s*{DAY}|{DAY}|weekends?|weekdays?)"
DAY_MENTION_RE = re.compile(rf"\b(?:{DAY_PHRASE}|every day|everyday|daily|any day)\b", re.I)
# "only" excepts days when it sits next to them: "Saturdays only", "only on Fridays"
ONLY_DAYS_RE = re.compile(rf"\bonly\s+(?:(?:on|during|in)\s+)?(?:the\s+)?{DAY_PHRASE}\b|\b{DAY_PHRASE}\s+only\b", re.I)
ALL_DAYS = frozenset(range(7))


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
            parts.append(_posts_only_on(self.post_days))
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


def _day_rule(clause: str) -> str:
    """Whether a clause that names days permits them, bans them, or can't be read.

    "Promo on Saturdays", "No promo except the Sunday thread" and "No promotion,
    Saturdays only" permit their days. "No promotion on weekends" bans them: a ban
    needs every day to come after the negation, with no second subject or permission
    after the first day. Anything else that mixes the two is "unclear":
    "Promo on Fridays, no DMs" (what does the "no" negate?), "No promo on weekends,
    promo Fridays", "No links on weekends unless approved", "every day except
    Sundays". The code can't tell which days are which, so the plan has to say why
    its day fits (rules_ok). Erring this way costs one sentence; reading a ban as a
    permission can get Ting Yu removed from the group.
    """
    negations = list(DAY_NEG_RE.finditer(clause))
    exceptions = list(EXCEPT_RE.finditer(clause))
    if not negations:
        # "every day except Sundays": the days after the exception are banned
        if any(m[0].lower() != "only" and days_in(clause[m.end():]) for m in exceptions):
            return "unclear"
        return "allow"
    if any(days_in(clause[:n.start()]) and days_in(clause[n.end():]) for n in negations):
        return "unclear"
    if exceptions:
        return "allow" if _days_all_excepted(clause, exceptions[0]) else "unclear"
    first_day = DAY_MENTION_RE.search(clause)
    day_start, day_end = first_day.span() if first_day else (len(clause), len(clause))
    if day_start < negations[0].start() or SUBJECT_RE.search(clause, day_end):
        return "unclear"
    if ALLOWED_RE.search(DAY_NEG_RE.sub(" ", clause)):
        return "unclear"
    return "ban"


def _days_all_excepted(clause: str, exception: re.Match) -> bool:
    """True when every day the clause names sits inside its exception: after
    "except" or "unless", or next to "only" ("Saturdays only", "only on Fridays")."""
    if exception[0].lower() == "only":
        beside = ONLY_DAYS_RE.search(clause)
        if not beside:
            return False
        start, end = beside.span()
    else:
        start, end = exception.end(), len(clause)
    return bool(days_in(clause[start:end])) and not days_in(clause[:start] + " " + clause[end:])


def _bans_links_on_every_day(clause: str) -> bool:
    """A negation right before "links" with no day after it: "Promo Saturdays only, no links"."""
    for link in LINK_RE.finditer(clause):
        negations = list(DAY_NEG_RE.finditer(clause, 0, link.start()))
        if not negations:
            continue
        between = clause[negations[-1].end():link.start()]
        if not days_in(between) and not PROMO_RE.search(between) and not days_in(clause[link.end():]):
            return True
    return False


@dataclass
class _DaySets:
    """The days a group's rules permit and ban for one kind of post."""

    permitted: set[int] = field(default_factory=set)
    banned: set[int] = field(default_factory=set)

    def add(self, days: frozenset[int], *, ban: bool) -> None:
        (self.banned if ban else self.permitted).update(days)

    def open_days(self, *, blanket_ban: bool = False) -> set[int] | None:
        """The days left open, or None when no rule names a day. Permitted days lift
        a blanket ban ("No promo. Promo thread on Sundays"); banned days only narrow
        what is left."""
        if self.permitted:
            return self.permitted - self.banned
        if self.banned and not blanket_ban:
            return set(ALL_DAYS - self.banned)
        return None


def parse(text: str | None) -> Rules:
    raw = (text or "").strip()
    if not raw or UNKNOWN_RE.match(raw):
        return Rules(raw, known=False, parsed=True)
    rules = Rules(raw, known=True, parsed=False)
    promo_sets, post_sets = _DaySets(), _DaySets()
    unclear = False
    for clause in re.split(r"[.;\n]+|\s\|\s", raw):
        clause = clause.strip()
        if not clause:
            continue
        days = days_in(clause) or frozenset()
        promo = bool(PROMO_RE.search(clause))
        link = bool(LINK_RE.search(clause))
        post = bool(POST_RE.search(clause))
        negative = bool(NEG_RE.search(clause))
        if link and days and _bans_links_on_every_day(clause):
            rules.no_links = True  # kept even when the rest of the clause is unclear
        day_rule = _day_rule(clause) if days and (promo or link or post) else None
        if day_rule == "unclear":
            unclear = True
            continue
        ban = day_rule == "ban"
        if days and (promo or link):
            # a link makes a post promotional, so a links rule about days is a promotion rule
            promo_sets.add(days, ban=ban)
            rules.promo_allowed = rules.promo_allowed or (promo and not ban)
            rules.parsed = True
        elif days and post:
            post_sets.add(days, ban=ban)
            rules.parsed = True
        elif promo and negative:
            rules.no_promo = True
            rules.parsed = True
        elif promo and ALLOWED_RE.search(clause):
            rules.promo_allowed = True
            rules.parsed = True
        if link and not days and negative:
            rules.no_links = True
            rules.parsed = True
        elif link and not promo and not days and ALLOWED_RE.search(clause):
            rules.parsed = True
    open_promo = promo_sets.open_days(blanket_ban=rules.no_promo)
    if open_promo:
        rules.promo_days = frozenset(open_promo)
        rules.no_promo = False
    elif open_promo is not None:
        rules.no_promo = True  # every permitted day is also banned
    open_posts = post_sets.open_days()
    if open_posts is not None:
        rules.post_days = frozenset(open_posts)
    if unclear:
        rules.parsed = False
    return rules


def day_problem(rules: Rules, weekday: int, *, promotional: bool) -> str | None:
    """Why a post on `weekday` breaks the rules, or None."""
    if rules.post_days is not None and weekday not in rules.post_days:
        return f"the group allows {_posts_only_on(rules.post_days)}"
    if promotional and rules.promo_days is not None and weekday not in rules.promo_days:
        return f"the group allows promotion only on {', '.join(day_names(rules.promo_days))}"
    return None
