"""Scoring and hiring evidence for the scout's shortlist (PRD §5.2a).

- `WEIGHTS` is the §5.2a table. A score breakdown gives points per factor,
  each from 0 to its weight, adding up to the candidate's score.
- Hiring evidence is a list of postings, `{url, title, seen, duties}`, on a
  known job board or the company's own site (code review P4). It is evidence
  only: no address is ever taken from it (contact.job_ad_problem).
- A comparison is one line on why a kept lead beat the day's other candidates.
- A person's name (with a title), phone number or email address in a posting's
  title or duties, or in a comparison, is removed on intake (`privacy.strip_personal`),
  so it is never stored or posted (code review P2).

Every check raises `LeadError` (from leads.py), so a bad record is a usage
error and changes nothing.
"""

from __future__ import annotations

import re
from datetime import date

from jura_growth import privacy, timeutil
from jura_growth.agents.scout import contact

WEIGHTS: dict[str, int] = {
    "industry_fit": 20,
    "size_fit": 15,
    "hiring_signals": 30,  # job boards and careers pages
    "paperwork_signals": 20,  # seen on the company's own site
    "specific_observations": 5,  # how specific and checkable
    "enquiry_address": 10,  # a published enquiry address
}

EVIDENCE_MAX = 10
DUTIES_MAX = 8
TITLE_CHARS = 150
DUTY_CHARS = 160
COMPARISON_CHARS = 280


class ScoringError(ValueError):
    """Raised as `leads.LeadError` by the callers."""


def _one_line(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


REMOVED_NOTE = "removed a person's name, phone number or email address from {where}; postings are evidence about roles, never people"


def _clean(text: str) -> tuple[str, bool]:
    return privacy.strip_personal(text)


def breakdown(value, score: int, *, evidence: list, has_email: bool) -> dict[str, int] | None:
    """The validated breakdown, or None when there is none."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ScoringError("`score_breakdown` must be an object with the §5.2a factors")
    unknown = sorted(set(value) - set(WEIGHTS))
    if unknown:
        raise ScoringError(f"`score_breakdown` has an unknown factor: {', '.join(unknown)} (factors: {', '.join(WEIGHTS)})")
    missing = [name for name in WEIGHTS if name not in value]
    if missing:
        raise ScoringError(f"`score_breakdown` is missing {', '.join(missing)}")
    parts: dict[str, int] = {}
    for name, weight in WEIGHTS.items():
        points = value[name]
        if isinstance(points, bool) or not isinstance(points, int):
            raise ScoringError(f"`score_breakdown`: {name} must be a whole number")
        if not 0 <= points <= weight:
            raise ScoringError(f"`score_breakdown`: {name} is {points}; at most {weight}")
        parts[name] = points
    total = sum(parts.values())
    if total != score:
        raise ScoringError(f"`score_breakdown` adds up to {total}, not the score {score}")
    if parts["hiring_signals"] and not evidence:
        raise ScoringError("`score_breakdown`: hiring_signals needs hiring evidence (`hiring_evidence`)")
    if parts["enquiry_address"] and not has_email:
        raise ScoringError("`score_breakdown`: enquiry_address needs a published address in `contact`")
    return parts


def hiring_evidence(value, domain: str | None = None) -> tuple[list[dict], list[str]]:
    """The validated postings and any notes. Each needs an http(s) URL on a known
    job board or the company's own site (`domain`), a title, the date seen (a real
    YYYY-MM-DD date, not in the future) and the duties it names."""
    if value is None:
        return [], []
    if not isinstance(value, list):
        raise ScoringError("`hiring_evidence` must be a list of {url, title, seen, duties}")
    notes = []
    if len(value) > EVIDENCE_MAX:
        notes.append(f"kept the first {EVIDENCE_MAX} hiring postings")
        value = value[:EVIDENCE_MAX]
    today = date.fromisoformat(timeutil.today_str())
    found = []
    for n, item in enumerate(value, start=1):
        where = f"`hiring_evidence` item {n}"
        if not isinstance(item, dict):
            raise ScoringError(f"{where} must be an object: {{url, title, seen, duties}}")
        url = str(item.get("url") or "").strip()
        if not re.fullmatch(r"https?://[^\s/]+\.[^\s/]+\S*", url, re.I):
            raise ScoringError(f"{where}: `url` must be the posting's http(s) address, with no spaces")
        host = contact.host_of(url)
        if not (contact.is_job_board(host) or (domain and contact.on_domain(url, domain))):
            raise ScoringError(
                f"{where}: {url} must be on a known job board or the company's own site ({domain or 'its website'}); "
                "a posting elsewhere can't be checked"
            )
        title = _one_line(item.get("title"))
        if not title:
            raise ScoringError(f"{where}: `title` is the job title the posting gives")
        if len(title) > TITLE_CHARS:
            raise ScoringError(f"{where}: `title` is longer than {TITLE_CHARS} characters")
        seen = str(item.get("seen") or "").strip()
        try:
            day = date.fromisoformat(seen)
        except ValueError:
            raise ScoringError(f"{where}: `seen` is the date you read it, as YYYY-MM-DD") from None
        if day > today:
            raise ScoringError(f"{where}: `seen` {seen} is in the future")
        duties = item.get("duties")
        if duties is None:
            duties = []
        if isinstance(duties, str):
            duties = [duties]
        if not isinstance(duties, list) or not all(isinstance(d, str) for d in duties):
            raise ScoringError(f"{where}: `duties` is a list of the duties the posting names")
        duties = [_one_line(d) for d in duties if _one_line(d)][:DUTIES_MAX]
        if any(len(d) > DUTY_CHARS for d in duties):
            raise ScoringError(f"{where}: keep each duty under {DUTY_CHARS} characters")
        title, removed = _clean(title)
        cleaned = [_clean(d) for d in duties]
        duties = [d for d, _ in cleaned]
        if removed or any(r for _, r in cleaned):
            notes.append(REMOVED_NOTE.format(where=where))
        found.append({"url": url, "title": title, "seen": seen, "duties": duties})
    return found, notes


def comparison(value) -> tuple[str | None, list[str]]:
    """The comparison line, with any person's details removed, and any notes."""
    text = _one_line(value)
    if not text:
        return None, []
    if len(text) > COMPARISON_CHARS or "\n" in str(value).strip():
        raise ScoringError(f"`comparison` is one line of at most {COMPARISON_CHARS} characters")
    text, removed = _clean(text)
    return text, [REMOVED_NOTE.format(where="`comparison`")] if removed else []


def strongest(evidence: list[dict]) -> dict | None:
    """The posting to show first: the most recently seen, then the one naming
    the most duties. Current hiring counts most (§5.2a point 2)."""
    if not evidence:
        return None
    return max(evidence, key=lambda e: (e.get("seen") or "", len(e.get("duties") or [])))


def describe(posting: dict | None) -> str:
    """`Admin assistant, seen 2026-10-20: key in orders; prepare invoices (<url>)`."""
    if not posting:
        return ""
    duties = "; ".join(posting.get("duties") or [])
    return f"{posting['title']}, seen {posting['seen']}" + (f": {duties}" if duties else "") + f" ({posting['url']})"
