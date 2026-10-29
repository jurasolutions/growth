"""`config/social.yaml`, read into typed settings.

The PRD values are the defaults, so a missing key never breaks a run. The hard
limits (the 14-day no-repeat window, one post per platform per day) live in
`jura_growth/caps.py` and are not settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from jura_growth import config, images

PLATFORMS = ("linkedin", "facebook", "instagram")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
LAYOUTS = ("headline", "list", "tool")
# `draft`: Ting Yu posts by hand from #social-drafts. `browser`: each draft that
# passes the brand gate becomes a publish item with its own approval request, and
# the publish job posts it once he approves (browser publishing PRD §5.10). The
# old `auto` (API publishing) was dropped (BP §3.3).
PUBLISH_MODES = ("draft", "browser")
DEFAULT_IDENTITIES = {
    "linkedin": "the Jura Solutions LinkedIn company page",
    "facebook": "the Jura Solutions Facebook Page",
    "instagram": "the Jura Solutions Instagram account",
}
DEFAULT_CHROME = images.DEFAULT_CHROME  # one path for the cards and the one-pager grid


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    brief: str
    layout: str = "headline"
    news: bool = False
    min_sources: int = 0
    max_sources: int = 3
    max_source_age_days: int | None = None
    needs_tool: bool = False


@dataclass(frozen=True)
class Platform:
    name: str
    label: str
    words: tuple[int, int]
    hashtags_max: int
    links: str  # "post": links in the post; "bio": "Link in bio", no URL
    width: int
    height: int
    enabled: bool = True
    carousel_days: tuple[str, ...] = ()
    carousel_max: int = 1
    publish_mode: str = "draft"
    page_url: str | None = None  # the page a browser run posts to, once Ting Yu sets it
    identity: str = ""  # the posting identity the run must see before typing

    @property
    def browser(self) -> bool:
        """Posted through the browser: switched on and in `browser` mode. A platform that is
        switched off (`enabled: false`) never is, whatever its `publish_mode` says."""
        return self.enabled and self.publish_mode == "browser"

    @property
    def size(self) -> str:
        return f"{self.width}x{self.height}"

    def carousel_on(self, day: date) -> bool:
        return self.carousel_max > 1 and WEEKDAYS[day.weekday()] in self.carousel_days


@dataclass(frozen=True)
class Settings:
    weekends: bool
    site: str
    rhythm: dict[str, str]
    themes: dict[str, Theme]
    platforms: dict[str, Platform]
    eligibility_line: str
    max_quote_words: int
    blocked_topics: tuple[str, ...]
    verify_links: bool
    chrome: str
    virtual_time_budget_ms: int
    render_timeout_seconds: int
    warnings: tuple[str, ...] = field(default=())

    def theme(self, theme_id: str) -> Theme:
        try:
            return self.themes[theme_id]
        except KeyError:
            raise SettingsError(f"unknown theme {theme_id!r}; known: {', '.join(self.themes)}") from None

    def enabled_platforms(self) -> list[Platform]:
        return [p for p in self.platforms.values() if p.enabled]


DEFAULT_THEMES = {
    "ai-this-week": dict(
        label="AI this week",
        brief="2–3 developments that matter to a small business, with links.",
        layout="list", news=True, min_sources=2, max_sources=3, max_source_age_days=7,
    ),
    "automation-tip": dict(label="Automation tip", brief="One small thing a team can automate this week.", max_sources=2),
    "from-the-toolbox": dict(
        label="From the toolbox", brief="The newest or most-used tool, with a link to try it.",
        layout="tool", needs_tool=True, max_sources=0,
    ),
    "industry-pattern": dict(
        label="Industry pattern",
        brief="How a business in one industry handles a task by hand, and what automating it looks like.",
        layout="list", max_sources=2,
    ),
    "explainer": dict(
        label="Explainer",
        brief="One term in plain English, or a Singapore scheme explained with the official link.",
        max_sources=2,
    ),
    "light": dict(label="Weekend", brief="A question to the audience, or a pointer to a good free resource.", max_sources=1),
}
DEFAULT_RHYTHM = {
    "mon": "ai-this-week", "tue": "automation-tip", "wed": "from-the-toolbox",
    "thu": "industry-pattern", "fri": "explainer", "sat": "light", "sun": "light",
}
DEFAULT_PLATFORMS = {
    "linkedin": dict(label="LinkedIn page", words=[120, 220], hashtags_max=3, links="post", image={"width": 1200, "height": 627}),
    "facebook": dict(label="Facebook Page", words=[60, 120], hashtags_max=2, links="post", image={"width": 1200, "height": 630}),
    "instagram": dict(
        label="Instagram", words=[50, 120], hashtags_max=8, links="bio", image={"width": 1080, "height": 1350},
        carousel={"days": ["mon", "thu"], "max_slides": 5},
    ),
}


def load() -> Settings:
    raw = config.agent_config("social") or {}
    warnings: list[str] = []

    themes = {}
    for theme_id, spec in {**DEFAULT_THEMES, **(raw.get("themes") or {})}.items():
        spec = {**DEFAULT_THEMES.get(theme_id, {}), **(spec or {})}
        layout = spec.get("layout", "headline")
        if layout not in LAYOUTS:
            raise SettingsError(f"theme {theme_id}: layout must be one of {LAYOUTS}")
        themes[theme_id] = Theme(
            id=theme_id,
            label=str(spec.get("label", theme_id)),
            brief=str(spec.get("brief", "")),
            layout=layout,
            news=bool(spec.get("news", False)),
            min_sources=int(spec.get("min_sources", 0)),
            max_sources=int(spec.get("max_sources", 3)),
            max_source_age_days=spec.get("max_source_age_days"),
            needs_tool=bool(spec.get("needs_tool", False)),
        )

    rhythm = {**DEFAULT_RHYTHM, **(raw.get("rhythm") or {})}
    for day, theme_id in rhythm.items():
        if day not in WEEKDAYS:
            raise SettingsError(f"rhythm: {day!r} is not one of {WEEKDAYS}")
        if theme_id not in themes:
            raise SettingsError(f"rhythm: {day} uses unknown theme {theme_id!r}")

    platforms = {}
    for name in PLATFORMS:
        spec = {**DEFAULT_PLATFORMS[name], **((raw.get("platforms") or {}).get(name) or {})}
        words = spec.get("words", DEFAULT_PLATFORMS[name]["words"])
        image = spec.get("image") or DEFAULT_PLATFORMS[name]["image"]
        carousel = spec.get("carousel") or {}
        mode = str(spec.get("publish_mode", "draft"))
        if mode not in PUBLISH_MODES:
            raise SettingsError(f"platforms.{name}.publish_mode must be draft or browser, not {mode!r}")
        page_url = spec.get("page_url") or None  # checked against the platform's hosts when an item is made
        links = spec.get("links", "post")
        if links not in ("post", "bio"):
            raise SettingsError(f"platforms.{name}.links must be 'post' or 'bio'")
        platforms[name] = Platform(
            name=name,
            label=str(spec.get("label", name)),
            words=(int(words[0]), int(words[1])),
            hashtags_max=int(spec.get("hashtags_max", 3)),
            links=links,
            width=int(image["width"]),
            height=int(image["height"]),
            enabled=bool(spec.get("enabled", True)),
            carousel_days=tuple(carousel.get("days", ())),
            carousel_max=max(1, min(int(carousel.get("max_slides", 1)), 10)),
            publish_mode=mode,
            page_url=str(page_url) if page_url else None,
            identity=str(spec.get("identity") or DEFAULT_IDENTITIES[name]),
        )

    render = raw.get("render") or {}
    return Settings(
        weekends=bool(raw.get("weekends", True)),
        site=str(raw.get("site", "https://jurasolutions.sg")).rstrip("/"),
        rhythm=rhythm,
        themes=themes,
        platforms=platforms,
        eligibility_line=str(raw.get("eligibility_line", "Check the official page for current eligibility.")),
        max_quote_words=int(raw.get("max_quote_words", 12)),
        blocked_topics=tuple(raw.get("blocked_topics") or ()),
        verify_links=bool(raw.get("verify_links", True)),
        chrome=str(render.get("chrome", DEFAULT_CHROME)),
        virtual_time_budget_ms=int(render.get("virtual_time_budget_ms", 8000)),
        render_timeout_seconds=int(render.get("timeout_seconds", 60)),
        warnings=tuple(warnings),
    )
