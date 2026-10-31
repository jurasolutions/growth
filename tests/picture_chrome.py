"""Seam P: the morning picture's page in real Chrome (test strategy, the overflow oracle).

`inspect(page)` adds a measuring script to a test copy of the page and reads what it found through
`--dump-dom`. The page itself holds no script. `problems(found, png)` holds the six-part oracle:
an empty list means the fixture passes. `bottom_rows()` is a small PNG decoder, so no new
dependency is needed to look at the picture's last pixels.

QA runs this file directly for the record with real fonts, which no test may do because the fonts
come from the network. Use synthetic data only, with temp data folders exported:

    uv run python tests/picture_chrome.py --live-fonts --out /some/temp/folder
"""

from __future__ import annotations

import base64
import json
import re
import struct
import tempfile
import zlib
from pathlib import Path

from jura_growth import images

MIN_FONT_PX = 21
LARGEST_GAP = 100
_FOUND = re.compile(r'<html[^>]*\bdata-oracle="([^"]+)"')

_ORACLE = r"""
<script id="oracle">
(function () {
  function blockOf(el) {
    while (el && getComputedStyle(el).display === 'inline') el = el.parentElement;
    return el;
  }
  function report() {
    var page = document.querySelector('.page');
    var box = page.getBoundingClientRect();
    var found = {
      token: getComputedStyle(document.documentElement).getPropertyValue('--brand').trim(),
      viewport: [innerWidth, innerHeight],
      height: Math.ceil(box.height),
      headings: [], texts: [], fontSizes: [], rects: [], scrolled: [], clamps: [], fixRows: [], more: [], elements: []
    };
    Array.prototype.forEach.call(document.querySelectorAll('h1, h2, h3'), function (h) {
      var r = h.getBoundingClientRect();
      found.headings.push({ text: h.textContent.trim(), tag: h.tagName,
                            inside: r.top >= box.top && r.bottom <= box.bottom && r.left >= box.left && r.right <= box.right });
    });
    Array.prototype.forEach.call(document.querySelectorAll('.more'), function (m) { found.more.push(m.textContent.trim()); });
    Array.prototype.forEach.call(document.querySelectorAll('img, b, iframe, svg, object, script:not(#oracle)'), function (e) { found.elements.push(e.tagName); });
    var blocks = [];
    var walker = document.createTreeWalker(page, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      if (!node.textContent.trim()) continue;
      var el = node.parentElement;
      found.fontSizes.push([parseFloat(getComputedStyle(el).fontSize), node.textContent.trim().slice(0, 40)]);
      found.texts.push(node.textContent.trim());
      var block = blockOf(el);
      if (blocks.indexOf(block) < 0) blocks.push(block);
      var clamp = el.closest('.clamp');
      var limit = clamp ? clamp.getBoundingClientRect() : null;
      var range = document.createRange();
      range.selectNodeContents(node);
      Array.prototype.forEach.call(range.getClientRects(), function (r) {
        if (!r.width || !r.height) return;
        if (limit && r.top >= limit.bottom - 1) return;  // clamped away
        found.rects.push({ block: blocks.indexOf(block), left: r.left, right: r.right, top: r.top, bottom: r.bottom,
                           text: node.textContent.trim().slice(0, 40) });
      });
    }
    Array.prototype.forEach.call(document.querySelectorAll('.clamp'), function (c) {
      var line = parseFloat(getComputedStyle(c).lineHeight);
      found.clamps.push({ lines: c.clientHeight / line, cut: c.scrollHeight > c.clientHeight + 1, text: c.textContent.slice(0, 40) });
    });
    Array.prototype.forEach.call(document.querySelectorAll('.fix .clamp'), function (c) {
      var line = parseFloat(getComputedStyle(c).lineHeight);
      found.fixRows.push({ lines: c.clientHeight / line, cut: c.scrollHeight > c.clientHeight + 1, text: c.textContent });
    });
    Array.prototype.forEach.call(document.querySelectorAll('body *'), function (e) {
      if (e.id === 'oracle' || e.classList.contains('clamp') || !e.clientWidth || e.closest('.clamp')) return;
      if (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1) {
        found.scrolled.push(e.tagName + '.' + e.className);
      }
    });
    var root = document.documentElement;
    if (root.scrollWidth > root.clientWidth + 1) found.scrolled.push('the whole page, sideways');
    var footer = document.querySelector('footer');
    var above = footer.previousElementSibling;
    var last = above;
    while (last.lastElementChild) last = last.lastElementChild;
    found.gapAboveFooter = footer.getBoundingClientRect().top - last.getBoundingClientRect().bottom;
    found.order = Array.prototype.map.call(document.querySelectorAll('h2, h3'), function (h) { return h.childNodes[0].textContent.trim(); });
    found.first = (function () {
      var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      var n;
      while ((n = w.nextNode())) { if (n.textContent.trim() && n.parentElement.id !== 'oracle') return n.textContent.trim(); }
      return '';
    })();
    root.setAttribute('data-oracle', btoa(unescape(encodeURIComponent(JSON.stringify(found)))));
  }
  addEventListener('load', function () { document.fonts.ready.then(report); });
})();
</script>
"""

# The scroll check: at the given window, can the footer be scrolled into reach?
_SCROLL = r"""
<script id="oracle">
addEventListener('load', function () {
  document.fonts.ready.then(function () {
    scrollTo(0, 1000000);
    var bottom = document.querySelector('footer').getBoundingClientRect().bottom;
    document.documentElement.setAttribute('data-oracle', btoa(JSON.stringify({ bottom: bottom, inner: innerHeight, moved: scrollY })));
  });
});
</script>
"""


def _dump(page: str, script: str, window: tuple[int, int], *, chrome: images.Chrome, offline: bool) -> dict:
    copy = page.replace("</body>", script + "</body>")
    with tempfile.TemporaryDirectory(prefix="jura-picture-") as folder:
        source = Path(folder) / "page.html"
        source.write_text(copy, encoding="utf-8")
        result = images.run_chrome([f"--window-size={window[0]},{window[1]}", "--dump-dom", source.as_uri()], chrome, offline=offline)
    match = _FOUND.search(result.stdout or "")
    assert match, f"the measuring script reported nothing: {(result.stderr or '')[-300:]}"
    return json.loads(base64.b64decode(match.group(1)).decode("utf-8"))


def inspect(page: str, *, chrome: images.Chrome, offline: bool = True) -> dict:
    return _dump(page, _ORACLE, (1200, 2400), chrome=chrome, offline=offline)


def scroll(page: str, *, chrome: images.Chrome, window: tuple[int, int] = (1200, 700), offline: bool = True) -> dict:
    return _dump(page, _SCROLL, window, chrome=chrome, offline=offline)


def _overlaps(rects: list[dict]) -> list[str]:
    found = []
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if a["block"] == b["block"]:
                continue
            across = min(a["right"], b["right"]) - max(a["left"], b["left"])
            down = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
            if across > 2 and down > 2:
                found.append(f"{a['text']!r} overlaps {b['text']!r}")
    return found


def bottom_rows(png: Path, count: int = 20) -> list[bytes]:
    """The last `count` rows of an 8-bit, non-interlaced PNG, as raw pixel bytes."""
    data = Path(png).read_bytes()
    at, idat, depth, colour, width, height = 8, [], 0, 0, 0, 0
    while at < len(data):
        (length,) = struct.unpack(">I", data[at : at + 4])
        kind, body = data[at + 4 : at + 8], data[at + 8 : at + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat.append(body)
        at += 12 + length
    assert depth == 8 and colour in (2, 6), (depth, colour)
    channels = 3 if colour == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = width * channels
    rows, previous = [], bytes(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1 : start + 1 + stride])
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + left) & 255
            elif kind == 2:
                line[x] = (line[x] + up) & 255
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif kind == 4:
                guess = left + up - corner
                nearest = min((abs(guess - left), 0, left), (abs(guess - up), 1, up), (abs(guess - corner), 2, corner))[2]
                line[x] = (line[x] + nearest) & 255
        previous = bytes(line)
        rows.append(previous)
    return rows[-count:]


def problems(found: dict, *, png: Path | None = None, measured: int | None = None, maximum: int = 1600, hidden: tuple[int, int] = (0, 0)) -> list[str]:
    """The six-part oracle (test strategy). `hidden` is what the "and N more" lines must say."""
    out = []
    if not found["token"]:  # 1. an unstyled page can't pass
        out.append("no design-system token resolves")
    outside = [h["text"] for h in found["headings"] if not h["inside"]]  # 2
    if outside:
        out.append(f"headings outside the page: {outside}")
    wanted = [f"and {n} more" for n in hidden if n]
    if found["more"] != wanted:
        out.append(f"'and N more' says {found['more']}, not {wanted}")
    width = found["viewport"][0]  # 3
    left = [r["text"] for r in found["rects"] if r["left"] < -1 or r["right"] > width + 1]
    if left:
        out.append(f"text leaves the page: {left[:3]}")
    if found["scrolled"]:
        out.append(f"scrolling inside: {found['scrolled'][:5]}")
    partial = [c for c in found["clamps"] if abs(c["lines"] - round(c["lines"])) > 0.05]
    if partial:
        out.append(f"a clamp shows part of a line: {partial[:3]}")
    out += _overlaps(found["rects"])[:3]  # 4
    if found["height"] > maximum:  # 5
        out.append(f"the page is {found['height']} px tall, over {maximum}")
    if found["gapAboveFooter"] > LARGEST_GAP:
        out.append(f"a gap of {found['gapAboveFooter']} px above the footer")
    small = [f for f in found["fontSizes"] if f[0] < MIN_FONT_PX]  # MB2
    if small:
        out.append(f"text under {MIN_FONT_PX} px: {small[:3]}")
    if found["elements"]:  # MB8
        out.append(f"elements that must never exist: {found['elements']}")
    if png is not None:
        size = images.png_size(png)
        if size != (width, measured):
            out.append(f"the PNG is {size}, the measure says {measured}")
        rows = bottom_rows(png)  # 6
        plain = rows[0][:4]
        step = len(rows[0]) // width
        if any(row[x : x + step] != rows[0][: step] for row in rows for x in range(0, len(row), step)):
            out.append(f"the PNG's bottom rows aren't plain background (first pixel {plain!r})")
    return out


if __name__ == "__main__":
    import argparse

    import picture_world as world
    from jura_growth import picture

    parser = argparse.ArgumentParser(description="The oracle on every fixture, with real fonts when asked.")
    parser.add_argument("--live-fonts", action="store_true", help="Let Chrome reach Google Fonts. Synthetic data only.")
    parser.add_argument("--out", type=Path, help="Write each fixture's PNG to this folder.")
    options = parser.parse_args()
    chrome = images.Chrome(images.DEFAULT_CHROME)
    offline = not options.live_fonts
    report = {}
    for name, build in world.FIXTURES.items():
        snapshot = build()
        page = picture.html(snapshot)
        found = inspect(page, chrome=chrome, offline=offline)
        png = None
        measured = images.measure_height(page, picture.WIDTH, chrome=chrome, offline=offline)
        if options.out:
            png = picture.render(snapshot, options.out / f"{name.replace(' ', '-')}.png", chrome=chrome, offline=offline)
        requests, fixes = len(picture.waiting(snapshot)), len(picture.fixes(snapshot))
        hidden = (max(0, requests - picture.DECIDE_SHOWN), max(0, fixes - picture.FIX_SHOWN))
        report[name] = {"height": found["height"], "measured": measured, "cut": [c["text"] for c in found["clamps"] if c["cut"]],
                        "problems": problems(found, png=png, measured=measured, hidden=hidden)}
    print(json.dumps(report, indent=2))
