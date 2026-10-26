"""Reading a headless run's stream-json transcript.

`runner._run_claude` keeps every run's transcript at
`data/growth/transcripts/YYYY-MM-DD/<run-id>-<job>.jsonl`. Each line is one
stream-json record: assistant messages carry `tool_use` blocks, user messages
carry the matching `tool_result` blocks, and the final `result` record lists
the permission denials.

Core module (moved from the community plug-in). Used by `jura-growth community audit-run` (no fetches of facebook.com) and by
`jura-growth apps submit-prd` (a cited official source was really fetched), and by the publish
job's audit (`agents/publish/audit.py`), which reads every result's text for the tabs it shows.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from jura_growth import paths

__all__ = ["ToolCall", "Transcript", "find", "read", "for_run", "host_of", "on_domains", "URL_IN_TEXT", "FETCH_COMMAND", "HEREDOC", "DENIAL_TEXT"]

URL_IN_TEXT = re.compile(r"https?://[^\s'\"<>()\\]+|\b(?:[a-z0-9-]+\.)*(?:facebook\.com|fb\.com|fb\.me|fb\.watch|fbcdn\.net|facebook\.net)\b[^\s'\"<>()\\]*", re.I)
FETCH_COMMAND = re.compile(r"\b(?:curl|wget|http|httpie|fetch|lynx|links|w3m|open|python3?|node|ruby|perl|osascript)\b", re.I)
# A heredoc body is data written to a file or stdin, not a command, so it is
# left out before looking for fetch commands (`cat > groups.json <<'EOF' ...`).
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.S)
DENIAL_TEXT = re.compile(r"permission|denied|not allowed|blocked|refused", re.I)
RESULT_CHARS = 200_000


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    ok: bool | None = None  # None until its result is seen
    denied: bool = False
    error_text: str = ""
    result: str = ""  # the result's text, as the tool returned it (RESULT_CHARS at most)

    def urls(self) -> list[str]:
        """URLs this call would open. WebSearch only searches, so it opens none."""
        found: list[str] = []
        for key in ("url", "uri", "href", "link"):
            value = self.input.get(key)
            if isinstance(value, str):
                found.append(value)
        if self.name == "Bash":
            command = HEREDOC.sub(" <<heredoc ", str(self.input.get("command", "")))
            if FETCH_COMMAND.search(command):
                found += URL_IN_TEXT.findall(command)
        elif self.name not in ("WebFetch", "WebSearch") and _looks_like_browser(self.name):
            found += URL_IN_TEXT.findall(json.dumps(self.input))
        return found


@dataclass
class Transcript:
    path: Path
    calls: list[ToolCall] = field(default_factory=list)
    result: dict | None = None

    def by_name(self, name: str) -> list[ToolCall]:
        return [c for c in self.calls if c.name == name]

    def fetched_urls(self) -> list[str]:
        """URLs WebFetch opened successfully in this run."""
        return [c.input["url"] for c in self.by_name("WebFetch") if c.ok and not c.denied and isinstance(c.input.get("url"), str)]


def _looks_like_browser(name: str) -> bool:
    return bool(re.search(r"fetch|navigate|browser|browse|open_url|get_page|read_page|http", name, re.I))


def find(run_id: int) -> Path | None:
    folder = paths.data_dir() / "transcripts"
    matches = sorted(folder.glob(f"*/{int(run_id)}-*.jsonl"))
    return matches[-1] if matches else None


def read(path: Path) -> Transcript:
    transcript = Transcript(path)
    calls: dict[str, ToolCall] = {}
    denied_ids: set[str] = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            kind = record.get("type")
            if kind == "result":
                transcript.result = record
                continue
            if kind == "system" and record.get("subtype") == "permission_denied":
                denied_ids.add(str(record.get("tool_use_id", "")))
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue  # system records carry a plain string here
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    call = ToolCall(str(block.get("id", "")), str(block.get("name", "")), block.get("input") or {})
                    calls[call.id] = call
                    transcript.calls.append(call)
                elif block.get("type") == "tool_result":
                    call = calls.get(str(block.get("tool_use_id", "")))
                    if call is None:
                        continue
                    text = _result_text(block.get("content"))
                    call.result = text[:RESULT_CHARS]
                    call.ok = not block.get("is_error")
                    if not call.ok:
                        call.error_text = text[:300]
                        call.denied = bool(DENIAL_TEXT.search(text[:300]))
    if transcript.result:
        denied_ids |= {str(d.get("tool_use_id", "")) for d in transcript.result.get("permission_denials") or [] if isinstance(d, dict)}
    for tool_use_id in denied_ids:
        call = calls.get(tool_use_id)
        if call is not None:
            call.denied = True
            call.ok = False
    return transcript


def for_run(run_id: int) -> Transcript | None:
    path = find(run_id)
    return read(path) if path else None


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def host_of(url: str) -> str:
    candidate = url if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I) else f"https://{url}"
    try:
        return (urlsplit(candidate).hostname or "").lower()
    except ValueError:
        return ""


def on_domains(url: str, domains: list[str] | tuple[str, ...]) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in domains)
