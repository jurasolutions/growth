"""Brand-check a copy file: the website's content files, an app PRD's §5.2.

`jura-growth check-copy <file>` pulls every user-facing string out of a file
and checks each one. Strings under keys that name a heading, title, button or
label are checked as headings (sentence case, not a question); the rest as body
text.

Supported: `.js`/`.jsx`/`.ts` (string literals), `.json` (string values), and
`.md` (the bullet list under a "Copy" heading, as in the app PRD template).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from jura_growth import brand_check

HEADING_KEYS = re.compile(
    r"(heading|title|button|label|cta|primary|secondary|subject|eyebrow|name|tab|action)", re.I
)
SKIP_KEYS = re.compile(r"^(icon|href|slug|id|key|type|tier|status|category|added|prd|className|variant|src)$")
JS_PAIR = re.compile(
    r"""(?:(?P<key>[A-Za-z_$][\w$]*)\s*:\s*)?(?P<q>["'`])(?P<value>(?:\\.|(?!(?P=q)).)*)(?P=q)""",
    re.S,
)


@dataclass
class Item:
    where: str
    text: str
    kind: str  # heading or body


def items_from_js(source: str) -> list[Item]:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"^\s*//.*$", "", source, flags=re.M)
    source = re.sub(r"^\s*import .*$", "", source, flags=re.M)
    found = []
    for match in JS_PAIR.finditer(source):
        key = match.group("key") or ""
        value = _unescape(match.group("value"))
        if not _is_copy(value) or SKIP_KEYS.match(key):
            continue
        line = source.count("\n", 0, match.start()) + 1
        kind = "heading" if key and HEADING_KEYS.search(key) else "body"
        found.append(Item(f"line {line}" + (f" ({key})" if key else ""), value, kind))
    return found


def items_from_json(data, where: str = "") -> list[Item]:
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if SKIP_KEYS.match(str(key)):
                continue
            if isinstance(value, str):
                if _is_copy(value):
                    kind = "heading" if HEADING_KEYS.search(str(key)) else "body"
                    found.append(Item(f"{where}.{key}".lstrip("."), value, kind))
            else:
                found += items_from_json(value, f"{where}.{key}")
    elif isinstance(data, list):
        for index, value in enumerate(data):
            if isinstance(value, str) and _is_copy(value):
                found.append(Item(f"{where}[{index}]", value, "body"))
            else:
                found += items_from_json(value, f"{where}[{index}]")
    return found


def items_from_markdown(source: str) -> list[Item]:
    """Bullets of the form `- Label: "string"` under a heading containing "Copy"."""
    section = re.search(r"^#{2,4}\s+[\d.]*\s*Copy\b.*?$(.*?)(?=^#{1,4}\s)", source, re.S | re.M)
    if not section:
        return []
    found = []
    for line in section.group(1).splitlines():
        bullet = re.match(r"^\s*-\s+(?P<label>[^:]+):\s*(?P<rest>.+)$", line)
        if not bullet:
            continue
        label = bullet.group("label").strip()
        for quoted in re.findall(r"[\"“]([^\"”]+)[\"”]", bullet.group("rest")):
            kind = "heading" if HEADING_KEYS.search(label) or re.search(r"button|heading|title", label, re.I) else "body"
            found.append(Item(label, quoted, kind))
    return found


def _unescape(value: str) -> str:
    value = re.sub(r"\\u\{?([0-9a-fA-F]{4,5})\}?", lambda m: chr(int(m.group(1), 16)), value)
    value = re.sub(r"\$\{[^}]*\}", "{n}", value)  # template interpolation
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": " "}.get(m.group(1), m.group(1)), value)


def _is_copy(value: str) -> bool:
    value = value.strip()
    if len(value) < 2 or not re.search(r"[A-Za-z]{2}", value):
        return False
    if re.fullmatch(r"[#./:\w-]+", value) and " " not in value:
        return False  # paths, ids, class names, single tokens
    if value.startswith(("http://", "https://", "/", "#", "./", "../", "var(", "--")):
        return False
    return True


def extract(path: Path) -> list[Item]:
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return items_from_json(json.loads(source))
    if path.suffix == ".md":
        return items_from_markdown(source)
    return items_from_js(source)


def check_file(path: Path, channel_name: str | None = None) -> list[tuple[Item, brand_check.Result]]:
    results = []
    for item in extract(path):
        if item.kind == "heading":
            result = brand_check.check("", headings=[item.text], channel_name=channel_name)
        else:
            result = brand_check.check(item.text, channel_name=channel_name)
        results.append((item, result))
    return results
