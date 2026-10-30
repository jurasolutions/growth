"""The publish run's transcript audit (BP §4.7, AC-P9.3; seam S11). Pure.

After every publish run, `job.after_run` reads the run's stream-json transcript through
`transcripts.read()` and hands it here with the hosts the run may be on (`scope.browser_hosts()`),
the approved content of what it claimed and the image copies `publish next` wrote. The audit
judges what the browser was asked to do and what it reported back, never what the model says it
did. It walks the calls in transcript order:

- **Hosts.** Every URL a Chrome tool was asked to open (`navigate` and any `url` input), and the
  URL of every tab this run opened as any later result reports it, must pass
  `hosts.url_problem`: `https://`, no user name or port, on one of the hosts. So a click that
  lands on another site fails the run even without a `navigate`. A Discord host is named as
  such. A new tab's own `chrome://newtab/` and `about:blank` are fine. An attempt fails even when
  it was denied (rehearsal R3). URLs inside page text are not tab URLs, and are ignored. While
  the fixture platform is on (`site`, BP-07), every address must be on the fixture site instead.
- **Places.** For a group item (a join, its answers, a group post), every such URL must also be
  the item's own group address or a page under it (`places`, `hosts.within`): never another
  group, the Page's own timeline or any other Facebook page (code review 06, B1). The finding
  names no address. On the fixture site the same path rule holds.
- **Tab addresses fail closed.** Every page-tool result on a tab this run opened must report that
  tab's address in the extension's own tab context, which ends the result: a JSON block with
  `tabId` and `url` starting on a line of its own, or trailing `tabId <n>: "<title>" (<url>)`
  lines, or, for `navigate` only, its opening "Navigated to <url>". Nothing earlier in a result
  counts, so tab JSON planted in page text can't clear a tab (code review 03, S-10). A result
  that doesn't end that way fails the run: an address the audit can't read is one it can't
  clear. The block is read from the last `TAIL_CHARS` characters, at most `MAX_DEPTH` deep, and
  never raises, whatever the page holds (B3).
- **Tabs.** A page tool call must name a tab this run opened with `tabs_create_mcp`. A tab it
  opened and didn't close is a warning.
- **Typing, judged whole.** What is typed is gathered per field, in order: `form_input` sets its
  `ref`'s field; `computer` `type` (and any `key` that types a character) adds to the focused
  field, a click or Tab or Escape moves to a new one, and Return or Space add a space. Each
  field's text, after Unicode NFC and collapsing whitespace, must be one of the approved texts:
  never a fragment, a reordering or a mix, and never the same approved text in two fields. Only
  a field left part-typed by a `publish stopped`
  may hold the start of one. An editing key (Backspace, Delete, the arrows) on a field that
  already holds text fails the run, and so does anything typed before `publish next` handed out
  an item.
- **Uploads.** `file_upload` may send only the claimed item's own image copies, path for path,
  each once and in the approved order, in one call or several (an Instagram carousel's slides
  are approved in order, BP-04). A run that went on to `publish done --url`, recorded or refused,
  must have sent every copy; a run that stopped part-way may have sent only the first few. A
  failed or denied upload sends nothing, though a wrong path, a repeat or a slide out of order
  fails the run even when the call failed.
- **Nothing after a stop.** After a `publish stopped` call, a click, a key, typing, a form input,
  an upload or a navigation fails the run. Reading the page, a screenshot and closing the tab
  are fine.
- **Never-tools.** Any call to a tool the run may never use (`scope.DENIED_TOOLS`), denied or not.

Findings name tools, tab ids, hosts and lengths, never page text, an address's path or what was
typed, because they reach #alerts and the run update (BP §4.7).

`no_browser` says the browser check itself (`list_connected_browsers`, `tabs_context_mcp` or
`tabs_create_mcp`) found no connected browser: the AC-P9.4 outcome. Page text saying so doesn't
count.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Iterator

from jura_growth import transcripts
from jura_growth.agents.publish import hosts as hosts_mod
from jura_growth.agents.publish.fixture import Fixture
from jura_growth.agents.publish.scope import CHROME, DENIED_TOOLS
from jura_growth.agents.publish.text import normal

NO_BROWSER = re.compile(r"no browsers are connected|browser extension is not connected", re.I)
BLANK_TABS = ("chrome://newtab/", "chrome://newtab", "about:blank")
DISCORD = ("discord.com", "discordapp.com", "discord.gg", "discord.new", "discordapp.net", "discord.media")
# Tools that don't act on a page, so they name no tab and report no page.
TABLESS = {"tabs_context_mcp", "tabs_create_mcp", "list_connected_browsers"}
# `computer` actions.
CLICKS = {"left_click", "right_click", "double_click", "triple_click", "middle_click", "left_click_drag"}
LOOKS = {"screenshot", "scroll", "scroll_to", "wait", "hover", "zoom"}
# `computer` keys: ones that add a space, ones that leave the field, ones that edit what's there.
SPACE_KEYS = {"return", "enter", "kp_enter", "shift+return", "shift+enter", "space"}
LEAVE_KEYS = {"tab", "escape", "esc"}
EDIT_KEYS = {"backspace", "delete", "up", "down", "left", "right", "arrowup", "arrowdown", "arrowleft", "arrowright",
             "home", "end", "pageup", "pagedown", "page_up", "page_down"}
# Page actions that may not follow a stop.
ACTS_AFTER_STOP = {"form_input", "file_upload", "upload_image", "navigate"}
URL_KEYS = ("url", "uri", "href", "link")
TAIL_CHARS = 20_000  # how far from a result's end its tab context may start
MAX_DEPTH = 16  # the deepest JSON tab context read; anything deeper is unreadable
TAIL_CANDIDATES = 50  # lines starting with { or [ tried, from the end
# The extension's own tab line: `  • tabId <n>: "<title>" ("<url>")` (rehearsal R1, 2026-10-30). The title
# is page-controlled; the address is the last `("…")` on the line and never holds a quote or a space, so a
# `(` in the address can't move the capture, and a line without both quotes is unreadable and fails
# closed (code review rehearsal-fixes, SEC-B1).
_TAB_LINE = re.compile(r'^\s*\u2022\s*tabId (\d+): ".*" \("([^"\s]*)"\)\s*$')
_REMINDER_OPEN, _REMINDER_CLOSE = "<system-reminder>", "</system-reminder>"
_CREATED = re.compile(r"tab\s*id\D{0,3}(\d+)", re.I)
_NAVIGATED = re.compile(r"\s*Navigated to (\S+)")
_HANDED_OUT = re.compile(r'"due"\s*:\s*true|^A-[0-9]+ · ', re.M)


@dataclass
class Audit:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    no_browser: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass
class _Fields:
    """What was typed, field by field, in order."""

    typed: dict[str, list[str]] = field(default_factory=dict)
    focus: int = 0

    def key(self) -> str:
        return f"focus-{self.focus}"

    def add(self, name: str, text: str) -> None:
        self.typed.setdefault(name, []).append(text)

    def holds_text(self, name: str) -> bool:
        return bool(normal("".join(self.typed.get(name, []))))


@dataclass
class _Uploads:
    """The claimed item's image copies in their approved order, and those sent so far."""

    order: list[str]
    sent: list[str] = field(default_factory=list)

    def attempt(self, path: str, ok: bool, fail) -> None:
        """Judge one path of a `file_upload` call: off the copies, a repeat or out of order fails
        whether or not the call succeeded; only a call that succeeded sends it (code review 04, S1)."""
        if path not in self.order:
            fail("file_upload tried to send a file that isn't the claimed item's image copy")
        elif path in self.sent:
            fail(f"file_upload sent image {self.order.index(path) + 1} of the claimed item more than once")
        else:
            if path != self.order[len(self.sent)]:
                fail("file_upload sent the claimed item's images out of their approved order")
            if ok:
                self.sent.append(path)


def audit(transcript: transcripts.Transcript, *, hosts: tuple[str, ...] | list[str], approved: list[str],
          images: list[str], site: Fixture | None = None, places: tuple[str, ...] | list[str] = ()) -> Audit:
    """`site`: the fixture platform, when it is on (BP-07). Then every address must be on the
    fixture site (`hosts.site_problem`) in place of `hosts`. `places`: the claimed group items'
    own addresses, which every address must also be inside (code review 06, B1)."""
    found = Audit()
    allowed = tuple(h.lower() for h in hosts)
    texts = [normal(text) for text in approved if text and text.strip()]
    uploads = _Uploads([os.path.normpath(path) for path in images])
    created: set[str] = set()
    closed: set[str] = set()
    fields = _Fields()
    claimed = stopped = attempted_done = False

    def fail(text: str) -> None:
        if text not in found.failures:
            found.failures.append(text)

    def check_url(url: str, where: str) -> None:
        problem = _url_problem(url, allowed, site)
        if problem:
            fail(f"{where}: {problem}")
        elif places and url.strip() not in BLANK_TABS and not any(hosts_mod.within(url, place) for place in places):
            fail(f"{where}: an address outside the claimed item's own page")

    def typed(text: str, tool: str, name: str) -> None:
        if not claimed and normal(text):
            fail(f"{tool} typed {len(text)} characters before an item was claimed")
        fields.add(name, text)

    for call in transcript.calls:
        if call.name == "Bash":
            command = str(call.input.get("command", ""))
            if call.ok and "publish next" in command and _HANDED_OUT.search(call.result):
                claimed = True
            if call.ok and "publish stopped" in command:
                stopped = True
            if "publish done" in command and "--url" in command:
                attempted_done = True  # recorded or refused, the run says the post went out
            continue
        if not call.name.startswith(CHROME):
            continue
        tool = call.name.removeprefix(CHROME)
        if tool in TABLESS and NO_BROWSER.search(call.result or call.error_text or ""):
            found.no_browser = True
        if tool in DENIED_TOOLS:
            fail(f"tried {tool}, which a publish run may never use")
        tab = _tab_of(call.input)
        if tool not in TABLESS:
            if tab is None:
                fail(f"a {tool} call named no tab")
            elif tab not in created:
                fail(f"a {tool} call on tab {tab}, which this run didn't open")
        for key in URL_KEYS:
            value = call.input.get(key)
            if isinstance(value, str):
                check_url(value, f"{tool} was asked to open")

        action = str(call.input.get("action", "")) if tool == "computer" else ""
        if stopped and (tool in ACTS_AFTER_STOP or (tool == "computer" and action not in LOOKS)):
            fail(f"{f'{tool} {action}'.strip()} after publish stopped")
        if tool == "form_input":
            value = call.input.get("value")
            name = f"form-{call.input.get('ref', '?')}"
            fields.typed.pop(name, None)  # setting a field replaces what it held
            typed("" if value is None else str(value), tool, name)
        elif tool == "computer":
            _keyboard(call.input, action, fields, typed, fail)
        if tool == "file_upload":
            for path in _paths(call.input):
                uploads.attempt(os.path.normpath(path), bool(call.ok), fail)

        if not call.ok:
            continue
        if tool == "tabs_create_mcp":
            made = _created_tab(call.result)
            if made is not None:
                created.add(made)
            continue
        if tool == "tabs_close_mcp":
            if tab is not None:
                closed.add(tab)
            continue
        if tool in TABLESS or tab not in created:
            continue
        reported = _trailing_tabs(call.result)
        seen = [url for shown, url in reported if shown == tab]
        if tool == "navigate":
            opening = _NAVIGATED.match(call.result)
            seen += [opening.group(1)] if opening else []
        if not seen:
            fail(f"couldn't read the address of tab {tab} from a {tool} result, so it can't be cleared")
        for url in seen:
            check_url(url, f"tab {tab} showed")
        for shown, url in reported:
            if shown != tab and shown in created:
                check_url(url, f"tab {shown} showed")

    filled: dict[str, int] = {}
    for name, pieces in fields.typed.items():
        text = normal("".join(pieces))
        if text in texts:
            filled[text] = filled.get(text, 0) + 1
        if not text or text in texts or (stopped and any(t.startswith(text) for t in texts)):
            continue
        fail(f"a field was typed with {len(text)} characters that aren't the approved content")
    for text, count in filled.items():
        if count > 1:
            fail(f"an approved text ({len(text)} characters) was typed into {count} fields")
    if attempted_done and len(uploads.sent) < len(uploads.order):
        fail(f"the run went on to publish done with {len(uploads.sent)} of its {len(uploads.order)} approved "
             "images sent")

    left = len(created - closed)
    if left:
        found.warnings.append(f"the run left {left} tab{'s' if left != 1 else ''} open")
    return found


def _keyboard(given: dict, action: str, fields: _Fields, typed, fail) -> None:
    """One `computer` call's effect on the fields."""
    if action in CLICKS:
        fields.focus += 1
        return
    text = given.get("text")
    if not isinstance(text, str):
        return
    if action == "type":
        typed(text, "computer", fields.key())
        return
    if action != "key":
        return
    for key in (k for k in text.split() if k):
        lowered = key.lower()
        if lowered in SPACE_KEYS:
            fields.add(fields.key(), " ")
        elif lowered in LEAVE_KEYS:
            fields.focus += 1
        elif lowered in EDIT_KEYS:
            if fields.holds_text(fields.key()):
                fail(f"computer pressed {key}, which edited text after typing it")
        else:
            typed(key, "computer", fields.key())


def _url_problem(url: str, allowed: tuple[str, ...], site: Fixture | None = None) -> str | None:
    text = url.strip().rstrip(".,;")
    if text in BLANK_TABS:
        return None
    if transcripts.on_domains(text, DISCORD):
        return f"a Discord host ({transcripts.host_of(text)})"
    if site is not None:
        return hosts_mod.site_problem(text, site)
    return hosts_mod.url_problem(text, allowed, "the publish hosts")


def _tab_of(given: dict) -> str | None:
    for key in ("tabId", "tab_id", "tab"):
        value = given.get(key)
        if isinstance(value, (int, str)) and not isinstance(value, bool) and str(value).strip():
            return str(value).strip()
    return None


def _paths(given: dict) -> list[str]:
    found = given.get("paths") or given.get("path") or given.get("files") or []
    if isinstance(found, str):
        found = [found]
    return [str(p) for p in found] if isinstance(found, list) else [str(found)]


def _created_tab(text: str) -> str | None:
    """The tab `tabs_create_mcp` opened: "Tab ID: <n>" in its text, else the first tab its tab
    context lists."""
    match = _CREATED.search(text[:TAIL_CHARS])
    if match:
        return match.group(1)
    reported = _trailing_tabs(text)
    return reported[0][0] if reported else None


def _trailing_tabs(text: str) -> list[tuple[str, str]]:
    """(tab id, url) pairs in the tab context that ends a result: a JSON block starting on a line
    of its own and running to the end, or trailing `tabId <n>: "<title>" (<url>)` lines. Nothing
    earlier in the result counts. Never raises: anything it can't read gives no pairs."""
    try:
        tail = _without_trailing_reminders(text[-TAIL_CHARS:])
        return _tail_json(tail) or _tail_lines(tail)
    except Exception:  # noqa: BLE001 - page content is never allowed to break the audit
        return []


def _without_trailing_reminders(tail: str) -> str:
    """Drop the `<system-reminder>` blocks the extension appends after the tab context, from the end
    only, in linear time (SEC-N1). Page text always comes before the tab context, and every tab line
    ends with its address, so a page can't put a reminder at the very end."""
    tail = tail.rstrip()
    while tail.endswith(_REMINDER_CLOSE):
        start = tail.rfind(_REMINDER_OPEN)
        if start < 0:
            break
        tail = tail[:start].rstrip()
    return tail


def _tail_json(tail: str) -> list[tuple[str, str]]:
    if not tail.endswith(("}", "]")):
        return []
    starts = [i for i in range(len(tail) - 1, -1, -1) if tail[i] in "{[" and (i == 0 or tail[i - 1] == "\n")]
    for start in starts[:TAIL_CANDIDATES]:
        block = tail[start:]
        if _depth(block) > MAX_DEPTH:
            continue
        try:
            value = json.loads(block)
        except ValueError:
            continue
        return list(_walk(value, MAX_DEPTH))
    return []


def _tail_lines(tail: str) -> list[tuple[str, str]]:
    """The tab lines that run unbroken from the extension's `- Available tabs:` header to the end, or
    none: a title holding a newline can't add a line (code review rehearsal-fixes, RR-N1)."""
    found = []
    for line in reversed(tail.split("\n")):  # never splitlines(): a title may hold U+2028 and friends (SEC-B2)
        if not line.strip():
            continue
        match = _TAB_LINE.search(line)
        if not match:
            return list(reversed(found)) if line.strip() == "- Available tabs:" else []
        found.append((match.group(1), match.group(2)))
    return []


def _depth(block: str) -> int:
    """The deepest nesting of brackets outside strings, without parsing."""
    deepest = level = 0
    in_string = escaped = False
    for ch in block:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            level += 1
            deepest = max(deepest, level)
            if deepest > MAX_DEPTH:
                return deepest
        elif ch in "}]":
            level -= 1
    return deepest


def _walk(value, budget: int) -> Iterator[tuple[str, str]]:
    if budget < 0:
        return
    if isinstance(value, dict):
        tab, url = value.get("tabId"), value.get("url")
        if isinstance(tab, (int, str)) and not isinstance(tab, bool) and isinstance(url, str):
            yield str(tab), url
        for child in value.values():
            yield from _walk(child, budget - 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, budget - 1)
