"""Posting to the "Jura HQ" Discord server through channel webhooks.

Write-only: the growth engine never reads Discord. SQLite stays the log of
record and Discord is the readable feed.

Each channel has its own webhook in `DISCORD_WEBHOOK_<CHANNEL>` (the channel
name upper-cased, dashes to underscores). A channel without a webhook is not
an error: the message goes to `data/growth/discord-outbox/YYYY-MM-DD.jsonl`
instead, so nothing is lost while the server is being set up.
`JURA_GROWTH_DISCORD=off` forces that path (the tests use it).

A message Discord doesn't take (unreachable, timed out, or refused) goes to
the same outbox, and `post()` reports it as not delivered instead of raising.
A failing run must still record itself and auto-pause when Discord is down.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import httpx

from jura_growth import config, images, log, paths, privacy, timeutil

MAX_CONTENT = 2000
MAX_FILES = 10
_FENCE = "```"
_REOPEN = _FENCE + "\n"
_CLOSE = "\n" + _FENCE


@dataclass
class PostResult:
    channel: str
    delivered: bool
    reason: str = ""
    messages: int = 0
    # With `wait=True`: each message's id, and the text each piece carried
    # as sent (masked), in order. A card keeps the first of each. A post that
    # failed part way lists the ids of the pieces that did go out.
    message_ids: list[str | None] = field(default_factory=list)
    pieces: list[str] = field(default_factory=list)


def channels() -> list[str]:
    return list(config.settings()["discord"]["channels"])


def env_name(channel: str) -> str:
    return "DISCORD_WEBHOOK_" + channel.upper().replace("-", "_")


def webhook(channel: str) -> str | None:
    if os.environ.get("JURA_GROWTH_DISCORD") == "off":
        return None
    return config.secret(env_name(channel))


def webhook_set(channel: str) -> bool:
    """Whether the channel has a webhook, without reading it (setup gaps)."""
    return os.environ.get("JURA_GROWTH_DISCORD") != "off" and config.is_set(env_name(channel))


def content_hash(content: str, files: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256(content.encode("utf-8"))
    for name, body in files:
        digest.update(name.encode("utf-8"))
        digest.update(body)
    return digest.hexdigest()


@dataclass
class Attachment:
    """A file as it goes to Discord: its name and bytes masked (`sent`), and the
    secret-masked original the dedupe hash covers (`hashed`)."""

    path: Path
    sent: tuple[str, bytes]
    hashed: tuple[str, bytes]


def attachment(path: Path, own_copy=()) -> Attachment | str:
    """The file ready to attach, or why it can't be.

    A text file goes through the same masking as the message. A PNG goes only
    if the engine made it (it sits in the data or outputs folder), with
    only the chunks its pixels need. Nothing else is attached: its contents can't be checked.
    """
    path = Path(path)
    name = privacy.for_discord(path.name)
    try:
        data = path.read_bytes()
    except OSError as error:
        return f"{name} was not attached ({type(error).__name__})"
    if data.startswith(images.PNG_SIGNATURE):
        if not _engine_file(path):
            return f"{name} was not attached (only images the engine made)"
        clean = images.pixels_only(data)
        if clean is None:
            return f"{name} was not attached (not a readable PNG)"
        return Attachment(path, (name, clean), (config.redact(path.name), clean))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is None or "\x00" in text:
        return f"{name} was not attached (only text files and images the engine made)"
    sent = privacy.for_discord(text, own_copy=own_copy).encode("utf-8")
    return Attachment(path, (name, sent), (config.redact(path.name), config.redact(text).encode("utf-8")))


def _engine_file(path: Path) -> bool:
    target = path.resolve()
    for folder in (paths.data_dir(), paths.outputs_dir()):
        root = Path(folder).resolve()
        if target == root or root in target.parents:
            return True
    return False


def split(content: str, limit: int = MAX_CONTENT, *, first_room: int = 0) -> list[str]:
    """Break a long message at line boundaries into Discord-sized pieces.

    A code fence stays balanced: a piece that ends inside one closes it, and the next opens it
    again, with room kept for both, so what's in the fence reads the same whichever piece holds
    it. A fence line never ends a piece on its own. `first_room` keeps that many characters free
    in the first piece, for a message whose first line grows when it is edited later (a card)."""
    room = limit - first_room
    if len(content) <= room:
        return [content]
    pieces: list[str] = []
    current, fenced = "", False

    def flush() -> None:
        nonlocal current, room
        body = current.rstrip("\n")
        last = body.rsplit("\n", 1)[-1]
        if fenced and last.lstrip().startswith(_FENCE) and last.count(_FENCE) % 2:
            body = body[: -len(last)].rstrip("\n")  # the opening line alone: it moves to the next piece
        elif fenced:
            body += _CLOSE
        if body.strip():
            pieces.append(body)
        current, room = (_REOPEN if fenced else ""), limit

    for line in content.splitlines(keepends=True):
        while True:
            toggles = line.count(_FENCE) % 2 == 1
            free = room - len(current) - (len(_CLOSE) if fenced != toggles else 0)
            if len(line) <= free:
                break
            if current not in ("", _REOPEN):
                flush()
                continue
            # The line alone is longer than a piece: cut it.
            chunk, line = line[:free], line[free:]
            current += chunk
            if chunk.count(_FENCE) % 2:
                fenced = not fenced
            flush()
        current += line
        if toggles:
            fenced = not fenced
    flush()
    return pieces


def post(
    conn: sqlite3.Connection | None,
    channel: str,
    content: str,
    *,
    files: list[Path] | None = None,
    username: str | None = None,
    dedupe: bool = True,
    suppress_embeds: bool = False,
    client: httpx.Client | None = None,
    own_copy: list[str] | tuple[str, ...] = (),
    wait: bool = False,
    components: list[dict] | None = None,
    first_piece_room: int = 0,
    files_first: bool = False,
    silent: bool = False,
    patience: float | None = None,
) -> PostResult:
    """Post `content` (and `files`) to a channel, or save it to the outbox.

    With `wait`, each piece is posted with `?wait=true` and the result lists
    the message ids Discord gave back and the text each piece carried, so the
    message can be edited later (`edit()`; approval cards, MC §4.6 A12).

    `components` (Approve and Skip buttons, MC §4.8 D5) go on the first
    piece only, the one a card edits, with `?with_components=true`: Discord
    takes them only through a webhook its application owns (Dispatch's).
    The approval cards decide when to send them (`approvals.post_buttons`).

    A long message splits (`split`), with `first_piece_room` characters kept free in its first
    piece. Files go on the last piece, or with `files_first` on the first, beside the buttons.

    `silent` posts without a notification. `patience` is how many seconds each piece may take,
    retries included, for a message that must not hold up its caller; past that it goes to the
    outbox like any other that Discord didn't take.

    The last line of defence (MC §4.3, §4.4): the content, username, file names
    and text files go through `privacy.for_discord()`, after `privacy.learn()`
    has read the named contacts from the database. Nothing here asks the
    Keychain; builders whose text comes from another process call
    `privacy.load_for_masking()` first. `own_copy` names the parts of
    `content` that are Jura's own outgoing text, kept as written.

    The dedupe hash covers the content with secrets masked but personal data
    as written, so posts to two different people never dedupe as one.
    """
    _require(channel)
    given = [Path(f) for f in (files or [])]
    if len(given) > MAX_FILES:
        raise ValueError(f"Discord takes at most {MAX_FILES} files per message")

    privacy.learn(conn)
    prepared = [attachment(f, own_copy) for f in given]
    attached = [a for a in prepared if isinstance(a, Attachment)]
    held_back = [a for a in prepared if isinstance(a, str)]
    if held_back:
        log.event(conn, "discord.attachment_refused", {"channel": channel, "files": held_back}, level="warning")
        content = content + "\n" + "\n".join(f"({reason})" for reason in held_back)
    digest = content_hash(config.redact(content), [a.hashed for a in attached])
    content = privacy.for_discord(content, own_copy=own_copy)
    username = privacy.for_discord(username) if username else username
    uploads = [a.sent for a in attached]
    saved = [privacy.for_discord(str(a.path)) for a in attached]  # where each file is, for the outbox
    if dedupe and conn is not None and _posted_today(conn, channel, digest):
        return PostResult(channel, delivered=False, reason="already posted today")

    url = webhook(channel)
    if not url:
        _outbox(channel, content, saved, username)
        _record(conn, channel, digest, delivered=False)
        log.event(conn, "discord.outbox", {"channel": channel, "chars": len(content)}, level="warning")
        return PostResult(channel, delivered=False, reason=f"{env_name(channel)} not set; saved to outbox")

    pieces = split(content, first_room=first_piece_room)
    with_files = 0 if files_first else len(pieces) - 1
    message_ids: list[str | None] = []
    try:
        with _using(client) as http:
            for index, piece in enumerate(pieces):
                response = _send(http, url, piece, uploads if index == with_files else [], username, suppress_embeds, wait=wait,
                                 components=components if index == 0 else None, silent=silent, patience=patience)
                if wait:
                    message_ids.append(_message_id(response))
    except DiscordError as error:
        _outbox(channel, content, saved, username)
        _record(conn, channel, digest, delivered=False)
        log.event(conn, "discord.error", {"channel": channel, "error": str(error)}, level="error")
        return PostResult(channel, delivered=False, reason=f"{error}; saved to outbox", message_ids=message_ids)

    _record(conn, channel, digest, delivered=True)
    log.event(conn, "discord.post", {"channel": channel, "chars": len(content), "files": len(uploads)})
    return PostResult(
        channel, delivered=True, messages=len(pieces), message_ids=message_ids, pieces=pieces if wait else []
    )


def edit(
    conn: sqlite3.Connection | None,
    channel: str,
    message_id: str,
    content: str,
    *,
    client: httpx.Client | None = None,
    components: list[dict] | None = None,
) -> PostResult:
    """Replace the text of a message this channel's webhook posted.
    `components` replaces its buttons too (`[]` removes them); None leaves
    them as they are.

    Masked like a post, mentioning nobody, never split (an edited card's
    first piece stays one message) and never saved to the outbox: an edit
    that doesn't reach Discord is reported, and the caller decides what to
    post instead. Edits don't notify (MC §5.1, decided cards)."""
    _require(channel)
    privacy.learn(conn)
    content = privacy.for_discord(content)[:MAX_CONTENT]
    url = webhook(channel)
    if not url:
        return PostResult(channel, delivered=False, reason=f"{env_name(channel)} not set")
    target = f"{url.rstrip('/')}/messages/{message_id}"
    try:
        with _using(client) as http:
            payload: dict = {"content": content, "allowed_mentions": {"parse": []}}
            if components is not None:
                payload["components"] = components
            _deliver(http, "PATCH", target, payload, [], params={"with_components": "true"} if components is not None else None)
    except DiscordError as error:
        log.event(conn, "discord.edit_failed", {"channel": channel, "error": str(error)}, level="warning")
        return PostResult(channel, delivered=False, reason=str(error))
    log.event(conn, "discord.edit", {"channel": channel, "chars": len(content)})
    return PostResult(channel, delivered=True, messages=1)


def delete(conn: sqlite3.Connection | None, channel: str, message_id: str, *, client: httpx.Client | None = None) -> PostResult:
    """Delete a message this channel's webhook posted. A failure is reported, never raised."""
    _require(channel)
    url = webhook(channel)
    if not url:
        return PostResult(channel, delivered=False, reason=f"{env_name(channel)} not set")
    try:
        with _using(client) as http:
            _deliver(http, "DELETE", f"{url.rstrip('/')}/messages/{message_id}", {}, [])
    except DiscordError as error:
        log.event(conn, "discord.delete_failed", {"channel": channel, "error": str(error)}, level="warning")
        return PostResult(channel, delivered=False, reason=str(error))
    log.event(conn, "discord.delete", {"channel": channel})
    return PostResult(channel, delivered=True, messages=1)


def _require(channel: str) -> None:
    if channel not in channels():
        raise ValueError(f"unknown Discord channel {channel!r}; expected one of {channels()}")


@contextmanager
def _using(client: httpx.Client | None) -> Iterator[httpx.Client]:
    """The caller's client as it is, or one of our own, closed after."""
    if client is not None:
        yield client
        return
    with httpx.Client(timeout=30) as own:
        yield own


def _message_id(response: httpx.Response) -> str | None:
    try:
        value = response.json().get("id")
    except (ValueError, AttributeError):
        return None
    return str(value) if value else None


def alert(conn: sqlite3.Connection | None, text: str, *, agent: str | None = None) -> PostResult:
    """Post to #alerts and log a warning event. Alerts are never deduplicated.

    `alert` is a message builder, not the last line of defence: an alert can
    carry text from another process (an error, a summary), so it loads the
    masking values first, Keychain included."""
    privacy.load_for_masking(conn)
    who = agent or log.current_agent() or "growth"
    log.event(conn, "alert", {"text": text}, level="warning", agent=who)
    return post(conn, "alerts", f"**{who}**: {text}", username=f"Jura growth · {who}", dedupe=False)


class DiscordError(RuntimeError):
    pass


SUPPRESS_EMBEDS = 1 << 2  # Discord message flag: no link previews
SUPPRESS_NOTIFICATIONS = 1 << 12  # Discord message flag: posted, with no notification


def _send(
    client: httpx.Client,
    url: str,
    content: str,
    files: list[tuple[str, bytes]],
    username: str | None,
    suppress_embeds: bool = False,
    *,
    wait: bool = False,
    components: list[dict] | None = None,
    silent: bool = False,
    patience: float | None = None,
) -> httpx.Response:
    payload: dict = {"content": content, "allowed_mentions": {"parse": []}}
    flags = (SUPPRESS_EMBEDS if suppress_embeds else 0) | (SUPPRESS_NOTIFICATIONS if silent else 0)
    if flags:
        payload["flags"] = flags
    if username:
        payload["username"] = username[:80]
    params = {}
    if wait:
        params["wait"] = "true"
    if components is not None:
        payload["components"] = components
        params["with_components"] = "true"
    return _deliver(client, "POST", url, payload, files, params=params or None, patience=patience)


def _deliver(
    client: httpx.Client,
    method: str,
    url: str,
    payload: dict,
    files: list[tuple[str, bytes]],
    *,
    params: dict | None = None,
    patience: float | None = None,
) -> httpx.Response:
    give_up = None if patience is None else time.monotonic() + patience
    for attempt in range(3):
        allowed = {} if give_up is None else {"timeout": max(give_up - time.monotonic(), 0.1)}
        try:
            if files:
                multipart: dict = {"payload_json": (None, json.dumps(payload), "application/json")}
                for i, (name, body) in enumerate(files):
                    multipart[f"files[{i}]"] = (name, body)
                response = client.request(method, url, files=multipart, params=params, **allowed)
            else:
                response = client.request(method, url, json=payload, params=params, **allowed)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            # Only the error's type: httpx messages can quote the URL, which is the secret.
            raise DiscordError(f"Discord could not be reached ({type(error).__name__})") from None
        wait = _retry_after(response) if response.status_code == 429 else 2.0 if response.status_code >= 500 else None
        if wait is not None and attempt < 2 and (give_up is None or time.monotonic() + wait < give_up):
            time.sleep(wait)
            continue
        if response.status_code >= 300:
            # Never include the URL: it is the secret.
            raise DiscordError(f"Discord answered {response.status_code}")
        return response
    raise DiscordError("Discord kept refusing the message")


def _retry_after(response: httpx.Response) -> float:
    """Seconds a 429 asks us to wait, at most 10. One second if the answer doesn't say
    (Cloudflare's rate-limit page in front of Discord is HTML, not JSON)."""
    try:
        seconds = float(response.json().get("retry_after", 1.0))
    except (ValueError, TypeError, AttributeError):
        return 1.0
    if not seconds >= 0:  # negative, or NaN
        return 1.0
    return min(seconds, 10.0)


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


def outbox_dir(data: Path | None = None) -> Path:
    """Where messages wait when Discord didn't take them: one JSONL file per SGT day."""
    return (data or paths.data_dir()) / "discord-outbox"


def _outbox(channel: str, content: str, files: list[str], username: str | None) -> None:
    path = paths.writable(outbox_dir() / f"{timeutil.today_str()}.jsonl")
    record = {
        "ts": timeutil.stamp(),
        "channel": channel,
        "username": username,
        "content": content,
        "files": files,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
