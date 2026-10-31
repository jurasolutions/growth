"""The picture on an image card: a small diagram drawn from the post's own facts.

Ting Yu, 2026-10-31: "there are no pictures to accompany the post so it looks dull". The design
system (`README.md` §4, Imagery) rules out stock illustration and scenes drawn in SVG, and says
diagrams are fine. So the picture is a diagram, framed like its `MotionPanel`: a quiet grid, a
hairline border and a mono caption saying what it shows. Its icons are Lucide (the design system's
one icon set), vendored in `templates/icons/` so a render needs no network for them.

Three kinds, set under `"visual"` in `card.json`:

    flow     3 to 4 steps, each an icon and a label, the last one in the brand green.
             How the thing in the story works, or what happens to a job.
    compare  two columns of 2 to 3 short points, each with an icon and a label.
             Before and after, or what changes and what doesn't.
    figure   one figure from a source, with what it counts and who says so. A percentage gets
             a ring. The numbers rule still applies: it comes from a source the post links,
             and `drafts.theme_problems` holds its value and its source to the post.

`words()` gives the brand checker every word a visual prints, so nothing on the picture skips it.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

ICONS = Path(__file__).parent / "templates" / "icons"
KINDS = ("flow", "compare", "figure")
LIMITS = {"label": 32, "caption": 60, "value": 12, "figure_label": 90, "source": 40, "point": 60}
STEPS = (3, 4)
POINTS = (2, 3)
_PERCENT = re.compile(r"^(\d{1,3}(?:\.\d+)?)%$")
_STROKE = re.compile(r'stroke-width="[^"]*"')
RING_RADIUS = 42  # in the ring's own 100-unit box
RING_CHARS = 5  # the longest value that still fits inside the ring: "99.5%"


def icon_names() -> list[str]:
    return sorted(path.stem for path in ICONS.glob("*.svg"))


def icon_svg(name: str) -> str:
    """A Lucide icon at the design system's 1.75 stroke, sized and coloured by its parent."""
    svg = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    return _STROKE.sub('stroke-width="1.75"', svg, count=1)


def icon_problem(name: str, where: str) -> str | None:
    """Why `name` can't be used. Checked against the folder's listing, so a name is never a path."""
    if name not in icon_names():
        return f'{where} "{name}" is not one of the icons `jura-growth social today` lists'
    return None


@dataclass
class Step:
    icon: str
    label: str


@dataclass
class Column:
    icon: str
    label: str
    points: list[str] = field(default_factory=list)


@dataclass
class Visual:
    kind: str
    caption: str = ""
    steps: list[Step] = field(default_factory=list)
    left: Column | None = None
    right: Column | None = None
    value: str = ""
    label: str = ""
    source: str = ""

    def words(self) -> list[str]:
        """Every word this visual prints, for the brand checker."""
        return [word for word in [*self.statements(), self.source] if word]

    def statements(self) -> list[str]:
        """What this visual says, without the name of its source."""
        found = [self.caption, self.value, self.label]
        found += [step.label for step in self.steps]
        for column in (self.left, self.right):
            if column:
                found += [column.label, *column.points]
        return [word for word in found if word]

    def as_dict(self) -> dict:
        out: dict = {"type": self.kind}
        if self.caption:
            out["caption"] = self.caption
        if self.kind == "flow":
            out["steps"] = [step.__dict__ for step in self.steps]
        elif self.kind == "compare":
            out["left"] = self.left.__dict__ if self.left else None
            out["right"] = self.right.__dict__ if self.right else None
        else:
            out.update(value=self.value, label=self.label, source=self.source)
        return out


def _clean(data: dict, key: str) -> str:
    return str(data.get(key, "") or "").strip()


def _too_long(problems: list[str], where: str, value: str, limit: int) -> None:
    if len(value) > limit:
        problems.append(f"{where} is {len(value)} characters; keep it to {limit}")


def _icon_label(data, where: str, problems: list[str]) -> tuple[str, str]:
    if not isinstance(data, dict):
        problems.append(f"{where} must be an object with an icon and a label")
        return "", ""
    icon, label = _clean(data, "icon"), _clean(data, "label")
    if not icon:
        problems.append(f"{where} needs an icon")
    else:
        wrong = icon_problem(icon, f"{where}.icon")
        if wrong:
            problems.append(wrong)
    if not label:
        problems.append(f"{where} needs a label")
    _too_long(problems, f"{where}.label", label, LIMITS["label"])
    return icon, label


def parse(data) -> tuple[Visual | None, list[str]]:
    """The visual in a card spec, and what is wrong with it."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return None, ["visual must be an object"]
    kind = _clean(data, "type")
    if kind not in KINDS:
        return None, [f"visual.type must be one of {', '.join(KINDS)}"]
    visual = Visual(kind=kind, caption=_clean(data, "caption"))
    _too_long(problems, "visual.caption", visual.caption, LIMITS["caption"])
    if kind == "flow":
        raw = data.get("steps")
        raw = raw if isinstance(raw, list) else []
        if not STEPS[0] <= len(raw) <= STEPS[1]:
            problems.append(f"a flow has {STEPS[0]} to {STEPS[1]} steps; found {len(raw)}")
        for index, step in enumerate(raw):
            visual.steps.append(Step(*_icon_label(step, f"visual.steps[{index}]", problems)))
    elif kind == "compare":
        for side in ("left", "right"):
            raw = data.get(side)
            icon, label = _icon_label(raw, f"visual.{side}", problems)
            found = raw.get("points") if isinstance(raw, dict) else None
            points = [str(p).strip() for p in found] if isinstance(found, list) else []
            if not POINTS[0] <= len(points) <= POINTS[1]:
                problems.append(f"visual.{side} has {POINTS[0]} to {POINTS[1]} points; found {len(points)}")
            for index, point in enumerate(points):
                if not point:
                    problems.append(f"visual.{side}.points[{index}] is empty")
                _too_long(problems, f"visual.{side}.points[{index}]", point, LIMITS["point"])
            setattr(visual, side, Column(icon, label, points))
    else:
        visual.value, visual.label, visual.source = _clean(data, "value"), _clean(data, "label"), _clean(data, "source")
        for name, value, limit in (("value", visual.value, LIMITS["value"]), ("label", visual.label, LIMITS["figure_label"]),
                                   ("source", visual.source, LIMITS["source"])):
            if not value:
                problems.append(f"a figure needs its {name}")
            _too_long(problems, f"visual.{name}", value, limit)
        if visual.value and not re.search(r"\d", visual.value):
            problems.append(f'a figure is a number, and visual.value is "{visual.value}"')
    return visual, problems


def _text(value: str) -> str:
    return html.escape(value, quote=True)


def tile(icon: str, *, solid: bool = False) -> str:
    return f'<span class="tile{" tile-solid" if solid else ""}" aria-hidden="true">{icon_svg(icon)}</span>'


def _flow(visual: Visual) -> str:
    last = len(visual.steps) - 1
    steps = "".join(
        f'<li class="step">{tile(step.icon, solid=index == last)}<span class="step-label">{_text(step.label)}</span></li>'
        for index, step in enumerate(visual.steps)
    )
    return f'<ol class="flow flow-{len(visual.steps)}">{steps}</ol>'


def _column(column: Column, *, solid: bool) -> str:
    points = "".join(f'<li>{_text(point)}</li>' for point in column.points)
    return (
        f'<div class="column{" column-after" if solid else ""}"><div class="column-head">{tile(column.icon, solid=solid)}'
        f'<span class="column-label">{_text(column.label)}</span></div><ul class="points">{points}</ul></div>'
    )


def _ring(value: str) -> str:
    """A ring for a short percentage up to 100; anything else stands on its own."""
    match = _PERCENT.match(value)
    if not match or len(value) > RING_CHARS or float(match.group(1)) > 100:
        return ""
    circumference = 2 * 3.14159 * RING_RADIUS
    filled = circumference * float(match.group(1)) / 100
    return (
        '<svg class="ring" viewBox="0 0 100 100" aria-hidden="true">'
        f'<circle class="ring-track" cx="50" cy="50" r="{RING_RADIUS}"/>'
        f'<circle class="ring-fill" cx="50" cy="50" r="{RING_RADIUS}" stroke-dasharray="{filled:.2f} {circumference:.2f}" '
        'transform="rotate(-90 50 50)"/></svg>'
    )


def _figure(visual: Visual) -> str:
    ring = _ring(visual.value)
    tight = " figure-value-tight" if ring and len(visual.value) == RING_CHARS else ""
    value = f'<span class="figure-value{tight}">{_text(visual.value)}</span>'
    shown = f'<span class="figure-ring">{ring}{value}</span>' if ring else value
    return (
        f'<div class="figure{" figure-with-ring" if ring else ""}">{shown}<div class="figure-text">'
        f'<span class="figure-label">{_text(visual.label)}</span>'
        f'<span class="figure-source">Source: {_text(visual.source)}</span></div></div>'
    )


def render(visual: Visual | None) -> str:
    """The panel's HTML, or nothing for a card with no visual."""
    if visual is None:
        return ""
    if visual.kind == "flow":
        body = _flow(visual)
    elif visual.kind == "compare":
        assert visual.left is not None and visual.right is not None  # parse() sets both on a compare
        body = f'<div class="compare">{_column(visual.left, solid=False)}{_column(visual.right, solid=True)}</div>'
    else:
        body = _figure(visual)
    caption = f'<div class="visual-caption">{_text(visual.caption)}</div>' if visual.caption else ""
    return f'<figure class="visual visual-{visual.kind}">{body}{caption}</figure>'
