"""Dataset T (test strategy v3 §3): canned stream-json transcripts of publish runs, for the audit
(S11) and the fake `claude` binary (S10).

A transcript is a list of steps. `chrome(tool, input, result)` is one Claude in Chrome call and
its result; `bash(command, output)` one Bash call. `lines(steps, result_text)` turns them into the
JSONL records Claude Code writes with `--output-format stream-json`.

The result texts follow what the 2026-10-25 spike recorded ("Navigated to https://example.com/",
"Created new tab.") plus the tab context the extension adds to a result: a JSON object with
`tabId` and `url` per tab. Rehearsal R1's redacted transcript should replace these once it exists.
"""

from __future__ import annotations

import json
from itertools import count

CHROME = "mcp__claude-in-chrome__"
TAB = 4101  # the tab every clean scenario opens
OTHER_TAB = 777  # a tab the run never opened (one of Ting Yu's own)
PAGE = "https://www.facebook.com/jura-test-page"
POST = "https://www.facebook.com/jura-test-page/posts/123456789"
NO_BROWSER = "No browsers are connected. Open Chrome with the Claude extension signed in."

_ids = count(1)


def chrome(tool: str, input: dict | None = None, result: str = "ok", *, error: bool = False, denied: bool = False) -> dict:
    return {"name": CHROME + tool, "input": input or {}, "result": result, "error": error or denied, "denied": denied}


def bash(command: str, output: str = "") -> dict:
    return {"name": "Bash", "input": {"command": command}, "result": output, "error": False, "denied": False}


def tab_context(*tabs: tuple[int, str]) -> str:
    return json.dumps({"availableTabs": [{"tabId": tab, "title": "Page", "url": url} for tab, url in tabs]})


def created(tab: int = TAB) -> dict:
    return chrome("tabs_create_mcp", {}, f"Created new tab. Tab ID: {tab}\n" + tab_context((tab, "chrome://newtab/")))


def opened(url: str = PAGE, tab: int = TAB) -> dict:
    return chrome("navigate", {"url": url, "tabId": tab}, f"Navigated to {url}\n" + tab_context((tab, url)))


def browser_check() -> list[dict]:
    return [
        chrome("list_connected_browsers", {}, json.dumps({"browsers": [{"name": "Jura"}]})),
        chrome("tabs_context_mcp", {"createIfEmpty": True}, tab_context()),
    ]


def typed(text: str, tab: int = TAB) -> dict:
    return chrome("computer", {"action": "type", "text": text, "tabId": tab}, "Typed.\n" + tab_context((tab, PAGE)))


def closed(tab: int = TAB) -> dict:
    return chrome("tabs_close_mcp", {"tabId": tab}, "Closed tab. 0 tab(s) remain.")


def clean_post(text: str, image: str | None = None) -> list[dict]:
    """The browser half of a clean post: open, check identity, type, upload, publish, read back,
    close."""
    steps = [created(), opened(), chrome("get_page_text", {"tabId": TAB}, "Jura Solutions\nCreate post\n" + tab_context((TAB, PAGE)))]
    steps.append(chrome("find", {"query": "What's on your mind?", "tabId": TAB}, "ref_12 textbox\n" + tab_context((TAB, PAGE))))
    steps.append(chrome("computer", {"action": "left_click", "ref": "ref_12", "tabId": TAB}, "Clicked.\n" + tab_context((TAB, PAGE))))
    steps.append(typed(text))
    if image:
        steps.append(chrome("file_upload", {"paths": [image], "ref": "ref_20", "tabId": TAB}, "Uploaded 1 file."))
    steps.append(chrome("computer", {"action": "key", "text": "Return", "tabId": TAB}, "Pressed Return.\n" + tab_context((TAB, PAGE))))
    steps.append(chrome("navigate", {"url": POST, "tabId": TAB}, f"Navigated to {POST}\n" + tab_context((TAB, POST))))
    steps.append(chrome("get_page_text", {"tabId": TAB}, text + "\n" + tab_context((TAB, POST))))
    steps.append(closed())
    return steps


def lines(steps: list[dict], result_text: str = "OK: done", *, cost: float = 0.09) -> list[str]:
    """The stream-json records for `steps`, ending with the result record."""
    out = [json.dumps({"type": "system", "subtype": "init", "tools": []})]
    denials = []
    for step in steps:
        tool_id = f"toolu_{next(_ids):05d}"
        out.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_id, "name": step["name"], "input": step["input"]}]}}))
        out.append(json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_id, "is_error": step["error"],
             "content": [{"type": "text", "text": step["result"]}]}]}}))
        if step["denied"]:
            denials.append({"tool_name": step["name"], "tool_use_id": tool_id, "tool_input": step["input"]})
    out.append(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": result_text,
                           "total_cost_usd": cost, "num_turns": len(steps), "permission_denials": denials}))
    return out


def write(path, steps: list[dict], result_text: str = "OK: done"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines(steps, result_text)) + "\n", encoding="utf-8")
    return path
