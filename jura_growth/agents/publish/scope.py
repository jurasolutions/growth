"""What the publish run may do: its commands and its Chrome tools (BP §4.7, AC-P9.2, ADR 0005).

- **Commands:** `publish next`, `publish done` and `publish stopped`. BP-06 adds `publish
  note-rules`. Nothing else, so `publish resolve`, `resume` and every decision stay Ting Yu's.
- **Tab tools by name:** `tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp` and
  `list_connected_browsers`. They read and open tabs, never a page.
- **Page tools only by domain:** one `ClaudeInChromeDomain(<host>)` rule per host of each platform
  this build drives (`hosts.BROWSER_PLATFORMS`) that is in `browser` mode in `config/social.yaml`.
  No page tool is allowed by name: a tool-name allow covers every site.
- **Denied by name:** the scripting, network, console, shortcut, recording, browser-switching,
  batch and resize tools, `upload_image`, web search and fetch, and `file_upload` unless the item
  `publish next` would hand out now has an image.

Every list here is a deny or a narrowing. Nothing in config can add a host or a tool.
"""

from __future__ import annotations

import json
import sqlite3

from jura_growth import paths, timeutil
from jura_growth.agents.publish import hosts

CHROME = "mcp__claude-in-chrome__"
COMMANDS = ("publish next", "publish done", "publish stopped")
TAB_TOOLS = ("tabs_context_mcp", "tabs_create_mcp", "tabs_close_mcp", "list_connected_browsers")
DENIED_TOOLS = (
    "javascript_tool", "read_network_requests", "read_console_messages", "shortcuts_execute", "shortcuts_list",
    "gif_creator", "switch_browser", "select_browser", "browser_batch", "resize_window", "upload_image",
)
DENIED_OTHER = ("WebSearch", "WebFetch")
FILE_UPLOAD = CHROME + "file_upload"


def enabled_platforms() -> tuple[str, ...]:
    """The platforms a publish run may open: driven by this build and in `browser` mode."""
    from jura_growth.agents.social.settings import load

    platforms = load().platforms
    return tuple(name for name in hosts.BROWSER_PLATFORMS if name in platforms and platforms[name].browser)


def browser_hosts() -> tuple[str, ...]:
    return tuple(dict.fromkeys(host for name in enabled_platforms() for host in hosts.BROWSER_HOSTS[name]))


def domain_rules() -> list[str]:
    return [f"ClaudeInChromeDomain({host})" for host in browser_hosts()]


def permissions():
    from jura_growth.headless import Permissions

    denied = [CHROME + tool for tool in DENIED_TOOLS] + list(DENIED_OTHER)
    if not next_has_image():
        denied.append(FILE_UPLOAD)
    return Permissions(
        commands=COMMANDS,
        allowed_tools=(*(CHROME + tool for tool in TAB_TOOLS), *domain_rules()),
        disallowed_tools=tuple(denied),
    )


def next_has_image() -> bool:
    """Whether an approved, unclaimed item for today carries an image: the item `publish next`
    could hand out. Read-only, and False (deny the upload) when growth.db can't be read."""
    path = paths.db_path()
    if not path.exists():
        return False
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return False
    try:
        rows = conn.execute(
            "SELECT p.content_json FROM publish_items p WHERE p.state = 'ready' AND p.day = ? AND EXISTS ("
            "SELECT 1 FROM approvals a WHERE a.subject = 'publish_item:' || p.id AND a.status = 'approved' "
            "AND a.used_at IS NULL)",
            (timeutil.today_str(),),
        ).fetchall()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    for (content,) in rows:
        try:
            if json.loads(content).get("images"):
                return True
        except (ValueError, AttributeError):
            continue
    return False
