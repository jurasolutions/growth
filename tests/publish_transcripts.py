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


def page(tool: str, input: dict, text: str = "ok", url: str = PAGE, tab: int = TAB, **flags) -> dict:
    """A page tool call on `tab`, whose result reports the tab's address, as the extension does."""
    return chrome(tool, {**input, "tabId": tab}, f"{text}\n" + tab_context((tab, url)), **flags)


def typed(text: str, tab: int = TAB) -> dict:
    return page("computer", {"action": "type", "text": text}, "Typed.", tab=tab)


def key(name: str, tab: int = TAB) -> dict:
    return page("computer", {"action": "key", "text": name}, f"Pressed {name}.", tab=tab)


def claimed(approval: str = "A-0001", text: str = "the approved text") -> dict:
    """`publish next --json` handing out an item: the claim, as the audit sees it."""
    return bash("jura-growth publish next --json", json.dumps({"due": True, "approval": approval, "text": text}))


def nothing_due() -> dict:
    return bash("jura-growth publish next --json", json.dumps({"due": False, "reasons": ["no item is waiting"]}))


def stopped(approval: str = "A-0001", reason: str = "login") -> dict:
    return bash(f"jura-growth publish stopped {approval} --reason {reason}", f"{approval}: stopped ({reason}); publish is paused")


def closed(tab: int = TAB) -> dict:
    return chrome("tabs_close_mcp", {"tabId": tab}, "Closed tab. 0 tab(s) remain.")


def clean_post(text: str, image: str | None = None) -> list[dict]:
    """The browser half of a clean post: open, check identity, type, upload, publish, read back,
    close."""
    steps = [created(), opened(), page("get_page_text", {}, "Jura Solutions\nCreate post")]
    steps.append(page("find", {"query": "What's on your mind?"}, "ref_12 textbox"))
    steps.append(page("computer", {"action": "left_click", "ref": "ref_12"}, "Clicked."))
    steps.append(typed(text))
    if image:
        steps.append(page("file_upload", {"paths": [image], "ref": "ref_20"}, "Uploaded 1 file."))
    steps.append(page("computer", {"action": "left_click", "ref": "ref_30"}, "Clicked Post."))
    steps.append(opened(POST))
    steps.append(page("get_page_text", {}, text, url=POST))
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


# Page content that once crashed the audit's JSON reader (code review 03, B3): nested arrays a few
# thousand characters long, and an object nested 5,000 deep. A comment on the Page can carry either.
ARRAY_BOMB = "[" * 3000 + "]" * 3000
OBJECT_BOMB = '{"a":' * 5000 + "1" + "}" * 5000
