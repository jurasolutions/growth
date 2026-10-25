"""The Discord double (test strategy v3 §2).

Every channel's webhook points at `https://discord.invalid/api/webhooks/<n>/not-a-real-token`,
and `discord.httpx.Client` is replaced by one on an `httpx.MockTransport` that records each
request. `.invalid` never resolves, so a post that slips past the patch fails at the network
guard instead of reaching Discord.

Use it from a test file with `from discord_double import discord_double` and ask for the
`discord_double` fixture. Not in `conftest.py`: one ticket owns that file per wave.

Modes:
- `accept` (default): posts answer 204, or 200 with a message id for `?wait=true`; edits 200.
- `500` and `429`: every post gets that answer, so `discord.post()` retries, then falls back to
  the outbox. Retry waits are skipped.
- `unreachable`: every request raises `httpx.ConnectError`.
- `edit-fails`: posts are accepted, `PATCH …/messages/<id>` answers 404.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest

from jura_growth import config, discord

# Channels later tickets add, set up here too so their posts reach the double from day one.
EXTRA_CHANNELS = ("mission-control", "approvals")
MODES = ("accept", "500", "429", "unreachable", "edit-fails")


@dataclass
class Request:
    """One request the double received, decoded."""

    channel: str
    method: str
    url: str
    content: str | None = None
    username: str | None = None
    flags: int | None = None
    allowed_mentions: dict | None = None
    components: list | None = None
    payload_json: str | None = None
    files: list[tuple[str, bytes]] = field(default_factory=list)
    message_id: str | None = None

    def texts(self) -> list[str]:
        """Everything in the request a person could read: the payload and each attachment."""
        found = [self.url, json.dumps(self.payload(), ensure_ascii=False)]
        if self.payload_json:
            found.append(self.payload_json)
        for name, body in self.files:
            found += [name, body.decode("utf-8", errors="replace"), body.decode("latin-1")]
        return found

    def payload(self) -> dict:
        return {
            "content": self.content,
            "username": self.username,
            "flags": self.flags,
            "allowed_mentions": self.allowed_mentions,
            "components": self.components,
        }


class DiscordDouble:
    def __init__(self, monkeypatch: pytest.MonkeyPatch):
        self.mode = "accept"
        self.requests: list[Request] = []
        self.urls: dict[str, str] = {}
        self._channel_by_id: dict[str, str] = {}
        self._next_message = 1000
        monkeypatch.delenv("JURA_GROWTH_DISCORD", raising=False)
        for n, channel in enumerate(dict.fromkeys([*discord.channels(), *EXTRA_CHANNELS]), start=1):
            url = f"https://discord.invalid/api/webhooks/{n}/not-a-real-token"
            monkeypatch.setenv(discord.env_name(channel), url)
            self.urls[channel] = url
            self._channel_by_id[str(n)] = channel
        # Only discord.py's own httpx: other doubles (Resend, D1, page fetches) keep theirs.
        monkeypatch.setattr(discord, "httpx", _HttpxFor(self._handle))
        monkeypatch.setattr(discord.time, "sleep", lambda seconds: None)
        config.reset_caches()

    # --- what tests read ---------------------------------------------------

    def posts(self, channel: str | None = None) -> list[Request]:
        return [r for r in self.requests if r.method == "POST" and (channel is None or r.channel == channel)]

    def contents(self, channel: str | None = None) -> list[str]:
        return [r.content or "" for r in self.posts(channel)]

    def texts(self) -> list[str]:
        return [text for request in self.requests for text in request.texts()]

    # --- the transport -----------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")  # ['', 'api', 'webhooks', n, token, ...]
        channel = self._channel_by_id.get(parts[3] if len(parts) > 3 else "", "?")
        recorded = Request(channel=channel, method=request.method, url=str(request.url))
        self._decode(request, recorded)
        self.requests.append(recorded)

        if self.mode == "unreachable":
            raise httpx.ConnectError("discord.invalid does not resolve", request=request)
        if self.mode == "500":
            return httpx.Response(500)
        if self.mode == "429":
            return httpx.Response(429, json={"retry_after": 0.01})
        if request.method == "PATCH":
            recorded.message_id = parts[-1]
            return httpx.Response(404) if self.mode == "edit-fails" else httpx.Response(200, json={"id": parts[-1]})
        if request.url.params.get("wait") == "true":
            self._next_message += 1
            recorded.message_id = str(self._next_message)
            return httpx.Response(200, json={"id": recorded.message_id})
        return httpx.Response(204)

    @staticmethod
    def _decode(request: httpx.Request, recorded: Request) -> None:
        body = request.read()
        kind = request.headers.get("content-type", "")
        payload: dict = {}
        if kind.startswith("application/json"):
            payload = json.loads(body)
        elif kind.startswith("multipart/form-data"):
            for name, filename, data in _multipart_parts(body, kind):
                if name == "payload_json":
                    recorded.payload_json = data.decode("utf-8")
                    payload = json.loads(recorded.payload_json)
                else:
                    recorded.files.append((filename or name, data))
        recorded.content = payload.get("content")
        recorded.username = payload.get("username")
        recorded.flags = payload.get("flags")
        recorded.allowed_mentions = payload.get("allowed_mentions")
        recorded.components = payload.get("components")


class _HttpxFor:
    """`httpx` as discord.py sees it: the real module, except that every Client it makes
    talks to the double."""

    def __init__(self, handler):
        self._handler = handler

    def Client(self, *args, **kwargs):  # noqa: N802 - stands in for httpx.Client
        return httpx.Client(transport=httpx.MockTransport(self._handler))

    def __getattr__(self, name):
        return getattr(httpx, name)


def _multipart_parts(body: bytes, content_type: str):
    boundary = content_type.split("boundary=", 1)[1].strip('"').encode()
    for chunk in body.split(b"--" + boundary):
        # Each part sits between CRLFs that belong to the framing, not to the file.
        chunk = chunk.removeprefix(b"\r\n").removesuffix(b"\r\n")
        if not chunk or chunk.startswith(b"--"):
            continue
        head, _, data = chunk.partition(b"\r\n\r\n")
        headers = head.decode("utf-8", errors="replace")
        name = _header_value(headers, "name")
        filename = _header_value(headers, "filename")
        yield name, filename, data


def _header_value(headers: str, key: str) -> str | None:
    marker = f' {key}="'
    if marker not in headers:
        return None
    return headers.split(marker, 1)[1].split('"', 1)[0]


@pytest.fixture
def discord_double(monkeypatch) -> DiscordDouble:
    return DiscordDouble(monkeypatch)
