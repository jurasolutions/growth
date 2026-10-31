"""Measure a rendered image card in real Chrome, independently of `card.js`.

Why two passes (reviews/test-strategy.md §2). Headless Chrome's window is shorter than `--window-size`
says: at 1200×630 a script sees `innerHeight` 487, and `--dump-dom` reports that shorter page, while
`--screenshot` lays the page out again at full height. So:

1. Run the production page at W×H and read the `data-fit` the real picture gets, and how short
   the window was.
2. Load the same page in a window that really is W×H, with `--fit` forced to that value and `fit()`
   off, and measure every visible element.

A pass means every element sits inside the card and above the footer, and no box's text is wider
than the box. Every run is offline by default: Chrome is a subprocess, so the only thing keeping it
off the network is the resolver rule in `images.run_chrome`.
"""

from __future__ import annotations

import html
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from jura_growth import images
from jura_growth.agents.social import render
from jura_growth.agents.social.settings import load

FIT_FLOOR = 0.56  # where card.js stops shrinking
RING_INSIDE = 0.75  # the ring's inside, as a share of its width: radius 42 of 50, stroke 9

_REPORT_WINDOW = """<script>
(document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(function () {
  var foot = document.querySelector(".foot");
  document.documentElement.setAttribute("data-inner", String(window.innerHeight));
  document.documentElement.setAttribute("data-foot-top", String(foot ? foot.getBoundingClientRect().top : -1));
});
</script>"""

_MEASURE = """<script>
(document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(function () {
  var card = document.querySelector(".card").getBoundingClientRect();
  var foot = document.querySelector(".foot").getBoundingClientRect();
  var main = document.querySelector(".main");
  var out = {inner: window.innerHeight, footTop: foot.top, cardBottom: card.bottom, footBottom: foot.bottom, outside: [], wide: [], smallest: 999,
             mainOverflow: main.scrollHeight - main.clientHeight};
  function name(el) { return el.tagName.toLowerCase() + (el.getAttribute("class") ? "." + el.getAttribute("class").split(" ").join(".") : ""); }
  main.querySelectorAll("*").forEach(function (el) {
    var svgPart = el.closest("svg") && el.tagName.toLowerCase() !== "svg";
    var style = getComputedStyle(el);
    if (svgPart || style.display === "none" || style.visibility === "hidden") return;
    var box = el.getBoundingClientRect();
    if (!box.width || !box.height) return;
    if (box.left < card.left - 0.5 || box.right > card.right + 0.5 || box.top < card.top - 0.5 || box.bottom > foot.top + 0.5) {
      out.outside.push(name(el) + " " + [box.left, box.top, box.right, box.bottom].map(Math.round).join(","));
    }
    var hasText = Array.prototype.some.call(el.childNodes, function (n) { return n.nodeType === 3 && n.textContent.trim(); });
    if (hasText) out.smallest = Math.min(out.smallest, parseFloat(style.fontSize));
    if (hasText && style.display !== "inline" && el.clientWidth && el.scrollWidth > el.clientWidth + 1) {
      out.wide.push(name(el) + " " + el.scrollWidth + ">" + el.clientWidth);
    }
    var parent = el.parentElement.getBoundingClientRect();
    if (el !== main && (box.left < parent.left - 0.5 || box.right > parent.right + 0.5)) {
      out.wide.push(name(el) + " sticks out of its parent: " + [box.left, box.right, parent.left, parent.right].map(Math.round).join(","));
    }
  });
  var ring = document.querySelector(".figure-ring");
  if (ring) {
    var value = ring.querySelector(".figure-value").getBoundingClientRect();
    out.ringText = value.width / ring.getBoundingClientRect().width;
  }
  document.documentElement.setAttribute("data-probe", JSON.stringify(out));
});
</script>"""


@dataclass
class Probe:
    width: int
    height: int
    fit: float
    inner_height: int
    outside: list[str] = field(default_factory=list)
    wide: list[str] = field(default_factory=list)
    main_overflow: float = 0
    smallest_type: float = 0
    png: tuple[int, int] | None = None
    foot_top_first_pass: float = 0
    foot_top: float = 0
    foot_bottom: float = 0
    ring_text: float = 0  # the figure's width as a share of its ring's

    def problems(self) -> list[str]:
        found = [f"outside the card or below the footer: {what}" for what in self.outside]
        found += [f"text wider than its box: {what}" for what in self.wide]
        if self.main_overflow > 1:
            found.append(f"the main area overflows by {self.main_overflow}px")
        if self.fit <= FIT_FLOOR:
            found.append(f"shrunk to the floor: data-fit {self.fit}")
        if self.foot_bottom > self.height + 0.5:
            found.append(f"the footer ends at {self.foot_bottom}, below the {self.height}px card")
        if self.ring_text > RING_INSIDE:
            found.append(f"the figure touches its ring: {self.ring_text:.2f} of the ring's width")
        if self.png != (self.width, self.height):
            found.append(f"the PNG is {self.png}, not {self.width}×{self.height}")
        return found


def _chrome() -> images.Chrome:
    settings = load()
    return images.Chrome(settings.chrome, settings.virtual_time_budget_ms, settings.render_timeout_seconds)


def _dump(page: str, width: int, height: int, *, offline: bool) -> str:
    with tempfile.TemporaryDirectory(prefix="jura-probe-") as folder:
        source = Path(folder) / "card.html"
        source.write_text(page, encoding="utf-8")
        result = images.run_chrome([f"--window-size={width},{height}", "--dump-dom", source.as_uri()], _chrome(), offline=offline)
    return result.stdout or ""


def _attribute(dom: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', dom)
    if not match:
        raise AssertionError(f"{name} is not in the page: {dom[:200]}")
    return html.unescape(match.group(1))


def probe(spec: render.CardSpec, width: int, height: int, out: Path, *, offline: bool = True) -> Probe:
    page = render.build_html(spec, width, height)
    first = _dump(page.replace("</body>", _REPORT_WINDOW + "</body>"), width, height, offline=offline)
    fit = float(_attribute(first, "data-fit"))
    inner = int(_attribute(first, "data-inner"))

    forced = re.sub(r'<script src="[^"]*card\.js"></script>', "", page)
    forced = forced.replace('<div class="card">', f'<div class="card" style="--fit: {fit}">')
    measured = json.loads(_attribute(_dump(forced.replace("</body>", _MEASURE + "</body>"), width, height + (height - inner), offline=offline), "data-probe"))
    if measured["inner"] != height:
        raise AssertionError(f"the second pass saw a window {measured['inner']}px high, not {height}px")

    image = images.screenshot(page, Path(out), width, height, chrome=_chrome(), offline=offline)
    return Probe(
        width, height, fit, inner,
        outside=measured["outside"], wide=measured["wide"], main_overflow=measured["mainOverflow"],
        smallest_type=measured["smallest"], png=images.png_size(image),
        foot_top_first_pass=float(_attribute(first, "data-foot-top")), foot_top=measured["footTop"], foot_bottom=measured["footBottom"], ring_text=measured.get("ringText", 0),
    )


def text_of(length: int, *, first: str = "Your") -> str:
    """Plain prose of exactly `length` characters, in sentence case, with no figures."""
    words = ("the team keeps its records and reads each answer before anything goes out to a customer "
             "while someone who knows the work checks what changed and why it matters here ").split()
    out = first
    index = 0
    while len(out) < length:
        out += " " + words[index % len(words)]
        index += 1
    out = out[:length]
    return out if out[-1] != " " else out[:-1] + "s"
