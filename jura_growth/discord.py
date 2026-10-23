"""Posting to the "Jura HQ" Discord server through channel webhooks.

Write-only: the growth engine never reads Discord. SQLite stays the log of
record and Discord is the readable feed.

Each channel has its own webhook in `DISCORD_WEBHOOK_<CHANNEL>` (the channel
name upper-cased, dashes to underscores). A channel without a webhook is not
an error: the message goes to `data/growth/discord-outbox/YYYY-MM-DD.jsonl`
instead, so nothing is lost while the server is being set up.
`JURA_GROWTH_DISCORD=off` forces that path (the tests use it).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from jura_growth import config, log, paths, timeutil

MAX_CONTENT = 2000
MAX_FILES = 10


@dataclass
class PostResult:
    channel: str
    delivered: bool
    reason: str = ""
    messages: int = 0


def channels() -> list[str]:
    return list(config.settings()["discord"]["channels"])


def env_name(channel: str) -> str:
    return "DISCORD_WEBHOOK_" + channel.upper().replace("-", "_")


def webhook(channel: str) -> str | None:
    if os.environ.get("JURA_GROWTH_DISCORD") == "off":
        return None
    return config.secret(env_name(channel))


def content_hash(content: str, files: list[Path]) -> str:
    digest = hashlib.sha256(content.encode("utf-8"))
    for file in files:
        digest.update(Path(file).name.encode("utf-8"))
        digest.update(Path(file).read_bytes())
    return digest.hexdigest()


def split(content: str, limit: int = MAX_CONTENT) -> list[str]:
    """Break a long message at line boundaries into Discord-sized pieces."""
    if len(content) <= limit:
        return [content]
    pieces, current = [], ""
    for line in content.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            pieces.append(current)
            current = ""
        current += line
    if current:
        pieces.append(current)
    return [piece.rstrip("\n") for piece in pieces if piece.strip()]


def post(
    conn: sqlite3.Connection | None,
    channel: str,
    content: str,
    *,
    files: list[Path] | None = None,
    username: str | None = None,
    dedupe: bool = True,
    client: httpx.Client | None = None,
) -> PostResult:
    if channel not in channels():
        raise ValueError(f"unknown Discord channel {channel!r}; expected one of {channels()}")
    files = [Path(f) for f in (files or [])]
    if len(files) > MAX_FILES:
        raise ValueError(f"Discord takes at most {MAX_FILES} files per message")

    digest = content_hash(content, files)
    if dedupe and conn is not None and _posted_today(conn, channel, digest):
        return PostResult(channel, delivered=False, reason="already posted today")

    url = webhook(channel)
    if not url:
        _outbox(channel, content, files, username)
        _record(conn, channel, digest, delivered=False)
        log.event(conn, "discord.outbox", {"channel": channel, "chars": len(content)}, level="warning")
        return PostResult(channel, delivered=False, reason=f"{env_name(channel)} not set; saved to outbox")

    pieces = split(content)
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        for index, piece in enumerate(pieces):
            last = index == len(pieces) - 1
            _send(client, url, piece, files if last else [], username)
    except DiscordError as error:
        log.event(conn, "discord.error", {"channel": channel, "error": str(error)}, level="error")
        return PostResult(channel, delivered=False, reason=str(error))
    finally:
        if owns_client:
            client.close()

    _record(conn, channel, digest, delivered=True)
    log.event(conn, "discord.post", {"channel": channel, "chars": len(content), "files": len(files)})
    return PostResult(channel, delivered=True, messages=len(pieces))


def alert(conn: sqlite3.Connection | None, text: str, *, agent: str | None = None) -> PostResult:
    """Post to #alerts and log a warning event. Alerts are never deduplicated."""
    who = agent or log.current_agent() or "growth"
    log.event(conn, "alert", {"text": text}, level="warning", agent=who)
    return post(conn, "alerts", f"**{who}**: {text}", username=f"Jura growth · {who}", dedupe=False)


class DiscordError(RuntimeError):
    pass


def _send(client: httpx.Client, url: str, content: str, files: list[Path], username: str | None) -> None:
    payload = {"content": content, "allowed_mentions": {"parse": []}}
    if username:
        payload["username"] = username[:80]
    for attempt in range(3):
        if files:
            multipart = {"payload_json": (None, json.dumps(payload), "application/json")}
            for i, file in enumerate(files):
                multipart[f"files[{i}]"] = (file.name, file.read_bytes())
            response = client.post(url, files=multipart)
        else:
            response = client.post(url, json=payload)
        if response.status_code == 429 and attempt < 2:
            retry_after = float(response.json().get("retry_after", 1.0))
            time.sleep(min(retry_after, 10.0))
            continue
        if response.status_code >= 500 and attempt < 2:
            time.sleep(2.0)
            continue
        if response.status_code >= 300:
            # Never include the URL: it is the secret.
            raise DiscordError(f"Discord answered {response.status_code}")
        return
    raise DiscordError("Discord kept refusing the message")


def _posted_today(conn: sqlite3.Connection, channel: str, digest: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM discord_posts WHERE channel = ? AND content_hash = ? AND substr(ts, 1, 10) = ? AND delivered = 1",
        (channel, digest, timeutil.today_str()),
    ).fetchone()
    return row is not None


def _record(conn: sqlite3.Connection | None, channel: str, digest: str, *, delivered: bool) -> None:
    if conn is None:
        return
    conn.execute(
        "INSERT INTO discord_posts (channel, ts, content_hash, delivered) VALUES (?, ?, ?, ?)",
        (channel, timeutil.stamp(), digest, int(delivered)),
    )


def _outbox(channel: str, content: str, files: list[Path], username: str | None) -> None:
    path = paths.writable(paths.data_dir() / "discord-outbox" / f"{timeutil.today_str()}.jsonl")
    record = {
        "ts": timeutil.stamp(),
        "channel": channel,
        "username": username,
        "content": content,
        "files": [str(f) for f in files],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
