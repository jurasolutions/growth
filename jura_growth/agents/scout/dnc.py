"""The do-not-contact list, `inputs/do-not-contact.csv`. Ting Yu writes it by
hand; the scout only reads it.

Columns: `company`, `domain`, `reason` (any may be blank; extra columns are
ignored). A row matches a company when its name appears, as whole words, in
the company's name ("Fujifilm" matches "FUJIFILM Business Innovation
Singapore Pte Ltd"), or when its domain is the company's domain or a parent of
it. Matching errs on the side of not contacting.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from jura_growth import paths

LEGAL_SUFFIXES = (
    "pte ltd",
    "pte limited",
    "private limited",
    "sdn bhd",
    "ltd",
    "limited",
    "llp",
    "llc",
    "inc",
    "corp",
    "corporation",
    "co",
)


@dataclass
class Entry:
    company: str
    domain: str
    reason: str


def path() -> Path:
    return paths.inputs_dir() / "do-not-contact.csv"


def exists() -> bool:
    return path().exists()


def normalise_name(name: str) -> str:
    value = (name or "").lower().replace("&", " and ")
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if value.endswith(" " + suffix):
                value = value[: -len(suffix) - 1].strip()
                changed = True
    return value


def normalise_domain(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.split("/", 1)[0].split("@")[-1]
    return value.removeprefix("www.").strip(".")


def entries() -> list[Entry]:
    if not exists():
        return []
    found = []
    with open(path(), encoding="utf-8-sig", newline="") as handle:
        lines = [line for line in handle if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    for row in reader:
        row = {str(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        company = row.get("company") or row.get("name") or ""
        domain = row.get("domain") or row.get("website") or ""
        if company or domain:
            found.append(Entry(company, normalise_domain(domain), row.get("reason", "")))
    return found


def _domain_matches(candidate: str, listed: str) -> bool:
    return bool(candidate and listed) and (candidate == listed or candidate.endswith("." + listed))


def match(company: str | None, domains: list[str] | tuple[str, ...] = ()) -> Entry | None:
    """The do-not-contact row that covers this company, or None."""
    name = normalise_name(company or "")
    candidates = [normalise_domain(d) for d in domains if d]
    for entry in entries():
        if entry.domain and any(_domain_matches(d, entry.domain) for d in candidates):
            return entry
        listed = normalise_name(entry.company)
        if listed and name and re.search(rf"(?:^|\s){re.escape(listed)}(?:\s|$)", name):
            return entry
    return None
