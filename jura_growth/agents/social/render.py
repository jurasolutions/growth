"""Image cards: HTML templates built on the design system, rendered to PNG by
headless Google Chrome.

The templates (`templates/*.html`) link `design-system/styles.css` by file URL,
so every colour, font, weight, radius and space is a design-system token;
`templates/card.css` only lays out the canvas. The logo is the design system's
own SVG asset, inlined so its wordmark uses the page's web fonts.

A card spec is JSON (see docs/social.md):

    {
      "layout": "headline" | "list" | "tool",
      "overline": "Automation tip",          optional, defaults to the theme label
      "headline": "Send the reminder before anyone has to remember it",
      "subtitle": "One rule in your accounting tool does it.",
      "items": ["...", {"title": "...", "detail": "...", "source": "IMDA"}],
      "tool": "quote-builder",                tool layout: a live toolbox slug
      "carousel": true | false,               optional, Instagram only
      "proper_nouns": ["Acme"]                optional, for the sentence-case check
    }

Each PNG's size is read back from its header and must match exactly.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from jura_growth import images, paths
from jura_growth.agents.social import toolbox
from jura_growth.agents.social.settings import LAYOUTS, Settings, load

TEMPLATES = Path(__file__).parent / "templates"

SIZES = {
    "linkedin": (1200, 627),
    "facebook": (1200, 630),
    "instagram": (1080, 1350),
    "profile": (1080, 1080),
    "linkedin-cover": (1128, 191),
    "facebook-cover": (1640, 624),
}
LIMITS = {"overline": 32, "headline": 90, "subtitle": 150, "caption": 60, "item": 90, "detail": 220, "source": 40}
MAX_ITEMS = 5


class RenderError(RuntimeError):
    pass


def design_system() -> Path:
    return paths.JURA_ROOT / "design-system"


# --- the card spec -----------------------------------------------------------


@dataclass
class Item:
    title: str
    detail: str = ""
    source: str = ""


@dataclass
class CardSpec:
    layout: str
    headline: str
    subtitle: str = ""
    overline: str = ""
    caption: str = ""
    items: list[Item] = field(default_factory=list)
    tool: str | None = None
    carousel: bool | None = None
    proper_nouns: list[str] = field(default_factory=list)
    tool_info: toolbox.Tool | None = None

    @classmethod
    def parse(cls, data: dict, *, default_overline: str = "") -> tuple["CardSpec | None", list[str]]:
        problems: list[str] = []
        if not isinstance(data, dict):
            return None, ["the card spec must be a JSON object"]
        layout = data.get("layout")
        if layout not in LAYOUTS:
            problems.append(f"layout must be one of {', '.join(LAYOUTS)}")
        items = []
        for index, raw in enumerate(data.get("items") or []):
            if isinstance(raw, str):
                items.append(Item(raw.strip()))
            elif isinstance(raw, dict) and str(raw.get("title", "")).strip():
                items.append(Item(str(raw["title"]).strip(), str(raw.get("detail", "")).strip(), str(raw.get("source", "")).strip()))
            else:
                problems.append(f"items[{index}] must be a string or an object with a title")
        spec = cls(
            layout=layout or "headline",
            headline=str(data.get("headline", "")).strip(),
            subtitle=str(data.get("subtitle", "")).strip(),
            overline=str(data.get("overline") or default_overline).strip(),
            caption=str(data.get("caption", "")).strip(),
            items=items,
            tool=(str(data["tool"]).strip() or None) if data.get("tool") else None,
            carousel=data.get("carousel"),
            proper_nouns=[str(n) for n in data.get("proper_nouns") or []],
        )
        if spec.layout == "tool":
            if not spec.tool:
                problems.append("the tool layout needs a `tool` slug from the toolbox registry")
            else:
                spec.tool_info = toolbox.find(spec.tool)
                if not spec.tool_info:
                    problems.append(f"tool {spec.tool!r} is not a live tool in {toolbox.registry_path()}")
            if spec.tool_info and not spec.headline:
                spec.headline = spec.tool_info.name
            if spec.tool_info and not spec.subtitle:
                spec.subtitle = spec.tool_info.description
        if not spec.headline:
            problems.append("headline is required")
        if spec.layout == "list" and not 2 <= len(spec.items) <= MAX_ITEMS:
            problems.append(f"the list layout takes 2 to {MAX_ITEMS} items")
        if spec.layout != "list" and len(spec.items) > MAX_ITEMS - 1:
            problems.append(f"at most {MAX_ITEMS - 1} carousel items besides the cover")
        for name in ("overline", "headline", "subtitle", "caption"):
            value = getattr(spec, name)
            if len(value) > LIMITS[name]:
                problems.append(f"{name} is {len(value)} characters; keep it to {LIMITS[name]}")
        for index, item in enumerate(spec.items):
            for name, limit in (("title", LIMITS["item"]), ("detail", LIMITS["detail"]), ("source", LIMITS["source"])):
                if len(getattr(item, name)) > limit:
                    problems.append(f"items[{index}].{name} is {len(getattr(item, name))} characters; keep it to {limit}")
        return spec, problems

    def headings(self) -> list[str]:
        """Text the brand checker treats as headings (sentence case, no questions)."""
        found = [self.headline] + [item.title for item in self.items]
        if self.overline:
            found.append(self.overline)
        return [h for h in found if h]

    def body(self) -> str:
        """Every other word the card prints, including the tool card's fixed
        strings, for the brand checker."""
        parts = [self.subtitle, self.caption] + [item.detail for item in self.items] + [item.source for item in self.items]
        if self.layout == "tool":
            parts += list(tool_strings(self.tool_info).values())
        return "\n".join(p for p in parts if p)

    def as_dict(self) -> dict:
        out = {"layout": self.layout, "overline": self.overline, "headline": self.headline, "subtitle": self.subtitle}
        if self.caption:
            out["caption"] = self.caption
        if self.items:
            out["items"] = [item.__dict__ for item in self.items]
        if self.tool:
            out["tool"] = self.tool
        if self.carousel is not None:
            out["carousel"] = self.carousel
        return out

    def slides(self, max_slides: int) -> list["CardSpec"]:
        """An Instagram carousel: this card as the cover, then one slide per
        item, at most `max_slides` in all."""
        if max_slides <= 1 or not self.items:
            return [self]
        items = self.items[: max_slides - 1]
        total = len(items) + 1
        slides = [self]
        for number, item in enumerate(items, start=2):
            slides.append(
                CardSpec(
                    layout="headline",
                    headline=item.title,
                    subtitle=item.detail,
                    overline=f"{number:02d} / {total:02d}" + (f" · {self.overline}" if self.overline else ""),
                    caption=f"Source: {item.source}" if item.source else "",
                    proper_nouns=self.proper_nouns,
                )
            )
        return slides


# --- HTML --------------------------------------------------------------------


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _asset(name: str) -> str:
    """A design-system SVG asset, inlined."""
    svg = (design_system() / "assets" / name).read_text(encoding="utf-8")
    return re.sub(r"^\s*<\?xml[^>]*>\s*", "", svg)


def _fill(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        raw, escaped = match.group(1), match.group(2)
        if raw:
            return values.get(raw, "")
        return html.escape(values.get(escaped, ""), quote=True)

    return re.sub(r"\{\{\{(\w+)\}\}\}|\{\{(\w+)\}\}", replace, template)


def _text(value: str) -> str:
    """Escaped text with hyphenated words kept on one line ("follow-up")."""
    escaped = html.escape(value, quote=True)
    return re.sub(r"\b(\w+(?:-\w+)+)\b", r'<span class="nw">\1</span>', escaped)


def format_class(width: int, height: int) -> str:
    ratio = width / height
    if ratio >= 3.2:
        return "fmt-banner"
    if ratio >= 2.3:
        return "fmt-cover"
    if ratio >= 1.4:
        return "fmt-landscape"
    if ratio >= 0.95:
        return "fmt-square"
    return "fmt-portrait"


def build_html(spec: CardSpec, width: int, height: int, *, settings: Settings | None = None, mode: str = "") -> str:
    settings = settings or load()
    site_host = re.sub(r"^https?://", "", settings.site)
    template = (TEMPLATES / f"{spec.layout}.html").read_text(encoding="utf-8")
    values = {
        "ds_styles": _file_url(design_system() / "styles.css"),
        "card_css": _file_url(TEMPLATES / "card.css"),
        "card_js": _file_url(TEMPLATES / "card.js"),
        "classes": " ".join(c for c in (format_class(width, height), f"layout-{spec.layout}", mode) if c),
        "width": str(width),
        "height": str(height),
        "overline": spec.overline,
        "headline": _text(spec.headline),
        "subtitle": _text(spec.subtitle),
        "site": site_host,
        "lockup": _asset("logo-lockup.svg"),
        "mark": _asset("logo-mark.svg"),
        "mark_white": _asset("logo-mark-white.svg"),
        "caption": spec.caption,
        "items": "",
    }
    if spec.layout == "list":
        values["items"] = "\n".join(
            f'<li><span class="num">{index:02d}</span><span class="text">{_text(item.title)}</span></li>'
            for index, item in enumerate(spec.items, start=1)
        )
    if spec.layout == "tool":
        info = spec.tool_info or toolbox.Tool(slug=spec.tool or "", name=spec.headline, description=spec.subtitle)
        fixed = tool_strings(info)
        tags = [info.category] if info.category else []
        tags.append(fixed["tier"])
        values.update(
            tags="".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags),
            tool_url=f"{site_host}/apps/{info.slug}",
            tool_name=info.name,
            button=fixed["button"],
            note=fixed["note"],
        )
    return _fill(template, values)


def tool_strings(info: toolbox.Tool | None) -> dict[str, str]:
    """The tool card's fixed words. Browser-tier tools keep what you type in
    the browser (app-factory PRD §5.3); AI tools send it to be read."""
    browser = info is None or info.tier == "browser"
    return {
        "tier": "Runs in your browser" if browser else "AI tool",
        "button": "Try it free",
        "note": "No account needed. What you type stays in your browser." if browser else "No account needed.",
    }


# --- Chrome ------------------------------------------------------------------


def chrome_path(settings: Settings | None = None) -> Path | None:
    settings = settings or load()
    candidate = Path(os.environ.get("JURA_GROWTH_CHROME") or settings.chrome)
    return candidate if candidate.exists() and os.access(candidate, os.X_OK) else None


def png_size(path: Path) -> tuple[int, int]:
    """(width, height) from the PNG's IHDR chunk."""
    size = images.png_size(path)
    if size is None:
        raise RenderError(f"{path} is not a PNG")
    return size


def _chrome(args: list[str], settings: Settings, *, offline: bool) -> subprocess.CompletedProcess:
    binary = chrome_path(settings)
    if not binary:
        raise RenderError(f"Google Chrome not found at {os.environ.get('JURA_GROWTH_CHROME') or settings.chrome}")
    profile = tempfile.mkdtemp(prefix="jura-chrome-")
    argv = [
        str(binary),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--mute-audio",
        f"--user-data-dir={profile}",
        f"--virtual-time-budget={settings.virtual_time_budget_ms}",
    ]
    if offline:
        argv.append("--host-resolver-rules=MAP * ~NOTFOUND")
    try:
        return subprocess.run(
            argv + args, capture_output=True, text=True, timeout=settings.render_timeout_seconds
        )
    except subprocess.TimeoutExpired as error:
        raise RenderError(f"Chrome took longer than {settings.render_timeout_seconds}s") from error
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def screenshot(page: str, out: Path, width: int, height: int, *, settings: Settings | None = None, offline: bool = False) -> Path:
    settings = settings or load()
    out = paths.writable(Path(out))
    with tempfile.TemporaryDirectory(prefix="jura-card-") as folder:
        source = Path(folder) / "card.html"
        source.write_text(page, encoding="utf-8")
        if out.exists():
            out.unlink()
        result = _chrome(
            [f"--window-size={width},{height}", f"--screenshot={out}", source.as_uri()], settings, offline=offline
        )
    if not out.exists():
        raise RenderError(f"Chrome wrote no image (exit {result.returncode}): {(result.stderr or '')[-300:]}")
    actual = png_size(out)
    if actual != (width, height):
        raise RenderError(f"{out.name} is {actual[0]}×{actual[1]}, expected {width}×{height}")
    return out


def fonts_loaded(page: str, *, settings: Settings | None = None) -> list[str]:
    """The web font families Chrome actually loaded for `page`."""
    settings = settings or load()
    with tempfile.TemporaryDirectory(prefix="jura-card-") as folder:
        source = Path(folder) / "card.html"
        source.write_text(page, encoding="utf-8")
        result = _chrome(["--window-size=1200,627", "--dump-dom", source.as_uri()], settings, offline=False)
    match = re.search(r'data-fonts="([^"]*)"', result.stdout or "")
    return sorted({f.strip().strip("'\"") for f in (match.group(1).split("|") if match else []) if f.strip()})


EXPECTED_FONTS = ("DM Sans", "IBM Plex Mono", "Outfit")


# --- whole sets --------------------------------------------------------------


def render_spec(
    spec: CardSpec,
    sizes: list[tuple[str, int, int]],
    out_dir: Path,
    *,
    carousel: dict[str, int] | None = None,
    settings: Settings | None = None,
    offline: bool = False,
    prefix: str = "",
) -> dict[str, list[Path]]:
    """Render `spec` at each (name, width, height). `carousel` maps a size name
    to its slide count (Instagram on Mondays and Thursdays)."""
    settings = settings or load()
    carousel = carousel or {}
    made: dict[str, list[Path]] = {}
    for name, width, height in sizes:
        slides = spec.slides(carousel.get(name, 1))
        files = []
        for number, slide in enumerate(slides, start=1):
            suffix = f"-{number}-of-{len(slides)}" if len(slides) > 1 else ""
            target = Path(out_dir) / f"{prefix}{name}{suffix}-{width}x{height}.png"
            screenshot(build_html(slide, width, height, settings=settings), target, width, height, settings=settings, offline=offline)
            files.append(target)
        made[name] = files
    return made


SETUP_COPY = {
    "headline": "We automate the repetitive parts of running a business",
    "subtitle": "Invoices, timesheets, approvals and the copying between systems.",
    "overline": "Automation consultancy",
}


def render_setup(out_dir: Path, *, settings: Settings | None = None, offline: bool = False) -> list[Path]:
    """Profile and cover images for the setup checklist (PRD §5.5)."""
    settings = settings or load()
    spec = CardSpec(layout="headline", **SETUP_COPY)
    made = []
    plan = [
        ("profile", "profile", "mode-mark"),
        ("profile-green", "profile", "mode-mark mode-dark"),
        ("linkedin-cover", "linkedin-cover", "mode-cover"),
        ("facebook-cover", "facebook-cover", "mode-cover"),
    ]
    for filename, size, mode in plan:
        width, height = SIZES[size]
        target = Path(out_dir) / f"{filename}-{width}x{height}.png"
        made.append(screenshot(build_html(spec, width, height, settings=settings, mode=mode), target, width, height, settings=settings, offline=offline))
    return made


def load_spec(path: Path, *, default_overline: str = "") -> tuple[CardSpec | None, list[str]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{path} not found"]
    except ValueError as error:
        return None, [f"{Path(path).name} is not valid JSON: {error}"]
    return CardSpec.parse(data, default_overline=default_overline)
