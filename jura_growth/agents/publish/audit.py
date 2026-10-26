"""The publish run's transcript audit (BP §4.7, AC-P9.3; seam S11). Pure.

After every publish run, `job.after_run` reads the run's stream-json transcript through
`transcripts.read()` and hands it here with the hosts the run may be on (`scope.browser_hosts()`)
and the approved content of what it claimed. The audit judges what the browser was asked to do
and what it reported back, never what the model says it did:

- **Hosts.** Every URL a Chrome tool was asked to open (`navigate` and any `url` input), and the
  URL of every tab this run opened as any later result reports it, must be on one of the hosts.
  So a click that lands on another site fails the run even without a `navigate`. A Discord host
  is named as such. A new tab's own `chrome://newtab/` and `about:blank` are fine. An attempt
  fails even when it was denied (rehearsal R3). URLs inside page text are not tab URLs, and are
  ignored: a page may link anywhere.
- **Tabs.** A page tool call must name a tab this run opened with `tabs_create_mcp`. A tab it
  opened and didn't close is a warning.
- **Typing.** Text typed with `computer` (`type`, or a `key` that isn't a plain editing key) or
  set with `form_input` must be part of the approved text, after Unicode NFC and collapsing
  whitespace. Nothing may be typed before an item is claimed.
- **Uploads.** `file_upload` may send only the approved image copies `publish next` wrote.
- **Never-tools.** Any call to a tool the run may never use (`scope.DENIED_TOOLS`), denied or not.

Findings name tools, tab ids, hosts and lengths, never page text or what was typed, because they
reach #alerts and the run update (BP §4.7). The result formats are the ones the 2026-10-25 spike
recorded plus the tab context the extension adds (`tabId` and `url`, as JSON or as
`tabId <n>: "<title>" (<url>)` lines); rehearsal R1 confirms them.

`no_browser` says the first browser check found no connected browser ("No browsers are connected",
or the extension signed in elsewhere), the AC-P9.4 outcome.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator

from jura_growth import transcripts
from jura_growth.agents.publish.scope import CHROME, DENIED_TOOLS

NO_BROWSER = re.compile(r"no browsers are connected|browser extension is not connected", re.I)
BLANK_TABS = ("chrome://newtab/", "chrome://newtab", "about:blank")
DISCORD = ("discord.com", "discordapp.com", "discord.gg", "discord.new", "discordapp.net", "discord.media")
# Tools that don't act on a page, so they name no tab.
TABLESS = {"tabs_context_mcp", "tabs_create_mcp", "list_connected_browsers"}
# `computer` key presses that edit or submit, and type no text of their own.
KEYS = {"return", "enter", "tab", "escape", "esc", "backspace", "delete", "space", "up", "down", "left", "right",
        "arrowup", "arrowdown", "arrowleft", "arrowright", "home", "end", "pageup", "pagedown", "shift+return",
        "shift+enter"}
URL_KEYS = ("url", "uri", "href", "link")
_TAB_LINE = re.compile(r"tabId\D{0,3}(\d+)\b[^\n]*?\((\S+)\)\s*$", re.M)
_CREATED = re.compile(r"tab\s*id\D{0,3}(\d+)", re.I)
_NAVIGATED = re.compile(r"Navigated to (\S+)")


@dataclass
class Audit:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    no_browser: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures


def audit(transcript: transcripts.Transcript, *, hosts: tuple[str, ...] | list[str], approved: list[str],
          images: list[str]) -> Audit:
    found = Audit()
    allowed = {h.lower() for h in hosts}
    texts = [_normal(text) for text in approved if text and text.strip()]
    created: set[str] = set()
    closed: set[str] = set()

    def fail(text: str) -> None:
        if text not in found.failures:
            found.failures.append(text)

    def check_url(url: str, where: str) -> None:
        problem = _url_problem(url, allowed)
        if problem:
            fail(f"{where}: {problem}")

    for call in transcript.calls:
        if not call.name.startswith(CHROME):
            continue
        tool = call.name.removeprefix(CHROME)
        if NO_BROWSER.search(call.result or call.error_text or ""):
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
        typed = _typed(tool, call.input)
        if typed is not None and _normal(typed):
            if not any(_normal(typed) in text for text in texts):
                fail(f"{tool} typed {len(typed)} characters that aren't in the approved content")
        if tool == "file_upload":
            for path in _paths(call.input):
                if path not in images:
                    fail("file_upload tried to send a file that isn't the approved image")
        if not call.ok:
            continue
        if tool == "tabs_create_mcp":
            made = _created_tab(call.result)
            if made is not None:
                created.add(made)
        if tool == "tabs_close_mcp" and tab is not None:
            closed.add(tab)
        for url in _NAVIGATED.findall(call.result) if tool == "navigate" else ():
            check_url(url, f"tab {tab} went to")
        for shown_tab, url in _tabs(call.result):
            if shown_tab in created:
                check_url(url, f"tab {shown_tab} showed")

    left = len(created - closed)
    if left:
        found.warnings.append(f"the run left {left} tab{'s' if left != 1 else ''} open")
    return found


def _url_problem(url: str, allowed: set[str]) -> str | None:
    text = url.strip().rstrip(".,;")
    if text in BLANK_TABS:
        return None
    host = transcripts.host_of(text)
    if not host:
        return "an address with no host"
    if any(host == d or host.endswith("." + d) for d in DISCORD):
        return f"a Discord host ({host})"
    if not re.match(r"^https://", text, re.I):
        return f"{host}, not over https"
    if host not in allowed:
        return f"{host}, which isn't one of the publish hosts"
    return None


def _tab_of(given: dict) -> str | None:
    for key in ("tabId", "tab_id", "tab"):
        value = given.get(key)
        if isinstance(value, (int, str)) and not isinstance(value, bool) and str(value).strip():
            return str(value).strip()
    return None


def _typed(tool: str, given: dict) -> str | None:
    if tool == "form_input":
        value = given.get("value")
        return value if isinstance(value, str) else (None if value is None else str(value))
    if tool == "computer":
        action = str(given.get("action", ""))
        text = given.get("text")
        if not isinstance(text, str):
            return None
        if action == "type":
            return text
        if action == "key":
            keys = [k for k in text.lower().split() if k]
            return None if keys and all(k in KEYS for k in keys) else text
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
    found = list(_json_tabs(text))
    found += [(tab, url) for tab, url in _TAB_LINE.findall(text)]
    return found


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
