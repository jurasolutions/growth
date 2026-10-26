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
  it was denied (rehearsal R3). URLs inside page text are not tab URLs, and are ignored.
- **Tab addresses fail closed.** Every page-tool result on a tab this run opened must report that
  tab's address in a shape read here (`tabId` and `url` as JSON, a `tabId <n>: "<title>" (<url>)`
  line, or `navigate`'s "Navigated to <url>"). A result that doesn't, whatever it says instead,
  fails the run: an address the audit can't read is one it can't clear.
- **Tabs.** A page tool call must name a tab this run opened with `tabs_create_mcp`. A tab it
  opened and didn't close is a warning.
- **Typing, judged whole.** What is typed is gathered per field, in order: `form_input` sets its
  `ref`'s field; `computer` `type` (and any `key` that types a character) adds to the focused
  field, a click or Tab or Escape moves to a new one, and Return or Space add a space. Each
  field's text, after Unicode NFC and collapsing whitespace, must be one of the approved texts:
  never a fragment, a reordering or a mix. Only a field left part-typed by a `publish stopped`
  may hold the start of one. An editing key (Backspace, Delete, the arrows) on a field that
  already holds text fails the run, and so does anything typed before `publish next` handed out
  an item.
- **Uploads.** `file_upload` may send only the claimed item's own image copies, path for path.
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
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator

from jura_growth import transcripts
from jura_growth.agents.publish import hosts as hosts_mod
from jura_growth.agents.publish.scope import CHROME, DENIED_TOOLS

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
_TAB_LINE = re.compile(r"tabId\D{0,3}(\d+)\b[^\n]*?\((\S+)\)\s*$", re.M)
_CREATED = re.compile(r"tab\s*id\D{0,3}(\d+)", re.I)
_NAVIGATED = re.compile(r"Navigated to (\S+)")
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
        return bool(_normal("".join(self.typed.get(name, []))))


def audit(transcript: transcripts.Transcript, *, hosts: tuple[str, ...] | list[str], approved: list[str],
          images: list[str]) -> Audit:
    found = Audit()
    allowed = tuple(h.lower() for h in hosts)
    texts = [_normal(text) for text in approved if text and text.strip()]
    uploads = {os.path.normpath(path) for path in images}
    created: set[str] = set()
    closed: set[str] = set()
    fields = _Fields()
    claimed = stopped = False

    def fail(text: str) -> None:
        if text not in found.failures:
            found.failures.append(text)

    def check_url(url: str, where: str) -> None:
        problem = _url_problem(url, allowed)
        if problem:
            fail(f"{where}: {problem}")

    def typed(text: str, tool: str, name: str) -> None:
        if not claimed and _normal(text):
            fail(f"{tool} typed {len(text)} characters before an item was claimed")
        fields.add(name, text)

    for call in transcript.calls:
        if call.name == "Bash":
            command = str(call.input.get("command", ""))
            if call.ok and "publish next" in command and _HANDED_OUT.search(call.result):
                claimed = True
            if call.ok and "publish stopped" in command:
                stopped = True
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
                if os.path.normpath(path) not in uploads:
                    fail("file_upload tried to send a file that isn't the claimed item's image copy")

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
        seen = [url for shown, url in _tabs(call.result) if shown == tab]
        if tool == "navigate":
            seen += _NAVIGATED.findall(call.result)
        if not seen:
            fail(f"couldn't read the address of tab {tab} from a {tool} result, so it can't be cleared")
        for url in seen:
            check_url(url, f"tab {tab} showed")
        for shown, url in _tabs(call.result):
            if shown != tab and shown in created:
                check_url(url, f"tab {shown} showed")

    for name, pieces in fields.typed.items():
        text = _normal("".join(pieces))
        if not text or text in texts or (stopped and any(t.startswith(text) for t in texts)):
            continue
        fail(f"a field was typed with {len(text)} characters that aren't the approved content")

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


def _url_problem(url: str, allowed: tuple[str, ...]) -> str | None:
    text = url.strip().rstrip(".,;")
    if text in BLANK_TABS:
        return None
    if transcripts.on_domains(text, DISCORD):
        return f"a Discord host ({transcripts.host_of(text)})"
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


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def _created_tab(text: str) -> str | None:
    """The tab `tabs_create_mcp` opened: "Tab ID: <n>" in its text, else the first tab it lists."""
    match = _CREATED.search(text)
    if match:
        return match.group(1)
    for tab, _ in _json_tabs(text):
        return tab
    return None


def _tabs(text: str) -> list[tuple[str, str]]:
    """(tab id, url) pairs a result reports: JSON objects with `tabId` and `url`, and
    `tabId <n>: "<title>" (<url>)` lines."""
    return list(_json_tabs(text)) + [(tab, url) for tab, url in _TAB_LINE.findall(text)]


def _json_tabs(text: str) -> Iterator[tuple[str, str]]:
    for chunk in _json_chunks(text):
        yield from _walk(chunk)


def _json_chunks(text: str) -> Iterator[object]:
    decoder = json.JSONDecoder()
    index = 0
    while True:
        start = min((i for i in (text.find("{", index), text.find("[", index)) if i != -1), default=-1)
        if start == -1:
            return
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            index = start + 1
            continue
        yield value
        index = end


def _walk(value) -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        tab, url = value.get("tabId"), value.get("url")
        if isinstance(tab, (int, str)) and not isinstance(tab, bool) and isinstance(url, str):
            yield str(tab), url
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
