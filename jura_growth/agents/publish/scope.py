"""What the publish run may do: its commands and its Chrome tools (BP §4.7, AC-P9.2, ADR 0005).

- **Commands:** `publish next`, `publish done`, `publish stopped` and `publish note-rules`
  (BP-06). Nothing else, so `publish resolve`, `resume` and every decision stay Ting Yu's.
- **Tab tools by name:** `tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp` and
  `list_connected_browsers`. They read and open tabs, never a page.
- **Page tools only by domain:** one `ClaudeInChromeDomain(<host>)` rule per host of each platform
  this build drives (`hosts.BROWSER_PLATFORMS`) that is in `browser` mode in `config/social.yaml`.
  No page tool is allowed by name: a tool-name allow covers every site. While the fixture
  platform is on (`fixture.py`, BP-07), the fixture host is the only one.
- **Denied by name:** the scripting, network, console, shortcut, recording, browser-switching,
  batch and resize tools, `upload_image`, web search and fetch, and `file_upload` unless the item
  `publish next` would hand out now has an image.

Every list here is a deny or a narrowing. Nothing in config can add a host or a tool.
"""

from __future__ import annotations

import sqlite3

from jura_growth import paths, timeutil
from jura_growth.agents.publish import fixture, hosts

CHROME = "mcp__claude-in-chrome__"
COMMANDS = ("publish next", "publish done", "publish stopped", "publish note-rules")
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


def browser_hosts(platforms: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """The hosts of `platforms`, or of every enabled platform when None. The domain rules take
    the enabled union, since they are set before anything is claimed; the audit takes only the
    claimed item's own platform (code review 04, B1).

    While the fixture platform is on (`fixture.py`, BP-07), the fixture host is the only one,
    whatever `platforms` names, for the argv and the audit alike. A refused fixture raises; it
    never falls back to the real hosts."""
    site = fixture.active()
    if site is not None:
        return (site.host,)
    names = enabled_platforms() if platforms is None else [p for p in platforms if p in hosts.BROWSER_HOSTS]
    return tuple(dict.fromkeys(host for name in names for host in hosts.BROWSER_HOSTS[name]))


def domain_rules() -> list[str]:
    return [f"ClaudeInChromeDomain({host})" for host in browser_hosts()]


def permissions():
    from jura_growth.headless import Permissions

    rules = domain_rules()  # first: a refused fixture raises before growth.db is read
    denied = [CHROME + tool for tool in DENIED_TOOLS] + list(DENIED_OTHER)
    if not next_has_image():
        denied.append(FILE_UPLOAD)
    return Permissions(
        commands=COMMANDS,
        allowed_tools=(*(CHROME + tool for tool in TAB_TOOLS), *rules),
        disallowed_tools=tuple(denied),
    )


def next_has_image() -> bool:
    """Whether an approved, unclaimed item for today carries an image: the item `publish next`
    could hand out (`claim.approved_ready`). Read-only, through the read model's opener, and
    False (deny the upload) when growth.db can't be read."""
    from jura_growth import mission
    from jura_growth.agents.publish import claim

    path = paths.db_path()
    if not path.exists():
        return False
    try:
        conn = mission.open_read_only(path)
    except sqlite3.Error:
        return False
    try:
        return any(item.content.get("images") for item in claim.approved_ready(conn, timeutil.today_str()))
    except (sqlite3.Error, ValueError):
        return False
    finally:
        conn.close()
