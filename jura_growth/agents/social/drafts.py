"""Reading a submission folder: the three platform variants, `sources.md` and
the card spec `card.json`.

    linkedin.md   facebook.md   instagram.md   plain text, exactly as posted
    sources.md    one source per line: URL, then publisher, date and title
    card.json     the image card spec (render.CardSpec)

Every http(s) URL in `sources.md` is a source. A news theme needs a
published date (YYYY-MM-DD) on each source's line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from jura_growth.agents.social import render
from jura_growth.agents.social.settings import Theme

# Same stopping characters as brand_check.find_links, so a source and the link
# in the post compare equal.
URL_RE = re.compile(r"https?://[^\s<>()\[\]\"'`|]+", re.I)
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


@dataclass
class Source:
    url: str
    line: str
    published: date | None = None


@dataclass
class Submission:
    folder: Path
    variants: dict[str, str] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    sources_text: str = ""
    card: render.CardSpec | None = None
    card_raw: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def urls(self) -> list[str]:
        return [s.url for s in self.sources]


def parse_sources(text: str) -> list[Source]:
    return _parse(text)[0]


def _parse(text: str) -> tuple[list[Source], list[str]]:
    found: list[Source] = []
    bracketed: list[str] = []
    seen = set()
    for line in text.splitlines():
        for match in URL_RE.finditer(line):
            url = match.group(0).rstrip(".,;:")
            if line[match.end():match.end() + 1] == "(":
                bracketed.append(url)
            if url in seen:
                continue
            seen.add(url)
            when = DATE_RE.search(line)
            published = None
            if when:
                try:
                    published = date.fromisoformat(when.group(1))
                except ValueError:
                    published = None
            found.append(Source(url, line.strip(), published))
    return found, bracketed


def load(folder: Path, platforms: list[str], *, theme: Theme) -> Submission:
    folder = Path(folder)
    sub = Submission(folder)
    if not folder.is_dir():
        sub.problems.append(f"{folder} is not a folder")
        return sub

    for platform in platforms:
        path = folder / f"{platform}.md"
        if not path.exists():
            sub.problems.append(f"{path.name} is missing")
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            sub.problems.append(f"{path.name} is empty")
        sub.variants[platform] = text

    sources_path = folder / "sources.md"
    if sources_path.exists():
        sub.sources_text = sources_path.read_text(encoding="utf-8")
        sub.sources, bracketed = _parse(sub.sources_text)
        for url in bracketed:
            sub.problems.append(
                f"a source address with brackets doesn't survive the link check ({url}(...); "
                "use another address for that page"
            )
    elif theme.news or theme.min_sources:
        sub.problems.append("sources.md is missing")

    card_path = folder / "card.json"
    if card_path.exists():
        sub.card_raw = card_path.read_text(encoding="utf-8")
    sub.card, problems = render.load_spec(card_path, default_overline=theme.label)
    sub.problems += [f"card.json: {p}" for p in problems]
    return sub


def theme_problems(sub: Submission, theme: Theme, today: date) -> list[str]:
    """What the day's theme needs from the sources and the card."""
    problems = []
    count = len(sub.sources)
    if count < theme.min_sources:
        problems.append(f"{theme.label} needs at least {theme.min_sources} sources in sources.md; found {count}")
    if count > theme.max_sources:
        problems.append(
            f"{theme.label} takes at most {theme.max_sources} sources; found {count} "
            "(list only what the post relies on, and link each one)"
        )
    if theme.news:
        for source in sub.sources:
            if source.published is None:
                problems.append(f"add the published date (YYYY-MM-DD) to the line for {source.url}")
            elif source.published > today:
                problems.append(f"{source.url} is dated in the future ({source.published})")
            elif theme.max_source_age_days is not None and (today - source.published).days > theme.max_source_age_days:
                problems.append(
                    f"{source.url} is from {source.published}; {theme.label} uses stories from the last "
                    f"{theme.max_source_age_days} days"
                )
    if sub.card and theme.needs_tool and sub.card.layout != "tool":
        problems.append(f"{theme.label} uses the tool card (layout \"tool\")")
    return problems
