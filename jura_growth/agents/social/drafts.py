"""Reading a submission folder: a variant for each platform still to draft,
`sources.md` and the card spec `card.json`. A file for a platform that is
switched off (`linkedin.md`, since 2026-10-29) is never read.

    facebook.md   instagram.md   plain text, exactly as posted
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

from jura_growth import brand_check
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


def _card_depth(card: render.CardSpec | None, theme: Theme) -> list[str]:
    """A post carries a picture and something to read on it (Ting Yu, 2026-10-31)."""
    if card is None:
        return []
    problems = []
    if theme.needs_visual and card.layout != theme.layout:
        problems.append(f"{theme.label} uses the {theme.layout} layout, not {card.layout}")
    if theme.carousel and card.carousel is False:
        problems.append(f"{theme.label} goes out as a carousel on Instagram: take `\"carousel\": false` out of card.json")
    with_detail = [item for item in card.items if item.detail]
    if len(with_detail) < theme.min_items:
        problems.append(
            f"{theme.label} needs at least {theme.min_items} card items with a detail, one Instagram slide each; "
            f"found {len(with_detail)}"
        )
    if theme.needs_visual and card.layout == "headline" and card.visual is None:
        problems.append(f"{theme.label} needs a `visual` on its card: a flow, a compare or a figure")
    if theme.needs_visual:
        bare = [str(index) for index, item in enumerate(card.items) if not item.icon]
        if bare:
            problems.append(f"give every card item an `icon` (items {', '.join(bare)} have none)")
    return problems


def states_figure(post: str, figure: str) -> bool:
    """Whether `post` states this figure, with both read the way the numbers rule reads them. So "1%"
    isn't in "11%", "3" isn't in "3.5", and a date, a clock time, a link or a hashtag states nothing."""
    wanted = brand_check.figures_in(figure)
    if wanted:
        stated = {brand_check.figure_key(found) for found in brand_check.figures_in(post)}
        return all(brand_check.figure_key(found) in stated for found in wanted)
    # A value that is no figure on its own ("2026", "forty"): the words themselves, outside any link.
    prose = post
    for link in brand_check.find_links(post):
        prose = prose.replace(link, " ")
    return re.search(rf"(?<![\w.,$]){re.escape(figure)}(?![\w%]|[.,]\d)", prose, re.I) is not None


def _publishers(sub: Submission) -> set[str]:
    """The publisher on each `sources.md` line: `- URL | Publisher | YYYY-MM-DD | Title`."""
    fields = [source.line.split("|") for source in sub.sources]
    return {found[1].strip().casefold() for found in fields if len(found) > 1 and found[1].strip()}


def _card_evidence(sub: Submission) -> list[str]:
    """The picture states nothing the post and its sources don't. This doesn't prove a figure
    true: the numbers rule passes any figure once a post has a source, so this ties it to what
    Ting Yu reads on the approval card, the post and its sources."""
    card = sub.card
    if card is None or card.layout == "tool":  # a tool card's words come from the site's registry
        return []
    problems = []
    publishers = _publishers(sub)
    labels = [(f"items[{index}].source", item.source) for index, item in enumerate(card.items) if item.source]
    if card.visual is not None and card.visual.source:
        labels.append(("visual.source", card.visual.source))
    for where, label in labels:
        if label.casefold() not in publishers:
            problems.append(f'{where}: source "{label}" is not the publisher on any line of sources.md; name it as that line does')
    figures = {brand_check.figure_key(found): found for found in reversed(brand_check.figures_in("\n".join(card.printed_words())))}
    value = card.visual.value if card.visual is not None else ""
    for platform, text in sub.variants.items():
        stated = {brand_check.figure_key(found) for found in brand_check.figures_in(text)}
        missing = [found for key, found in figures.items() if key not in stated]
        if value and not states_figure(text, value) and value not in missing:
            missing.insert(0, value)
        problems += [
            f'the card says "{found}" and {platform}.md doesn\'t: every post states each figure on the card, written the same way'
            for found in missing
        ]
    return problems


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
    hosts = {brand_check.host_of(source.url).removeprefix("www.") for source in sub.sources}
    if count >= theme.min_sources and len(hosts) < theme.min_hosts:
        problems.append(
            f"{theme.label} needs sources on {theme.min_hosts} different sites (the company's own announcement and "
            f"one independent report); found {len(hosts)}"
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
    problems += _card_depth(sub.card, theme)
    problems += _card_evidence(sub)
    return problems
