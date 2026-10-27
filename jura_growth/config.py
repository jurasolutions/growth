"""Settings and secrets.

Settings come from `config/settings.yaml`; each agent may keep its own
`config/<agent>.yaml`. Secrets come from the environment, then from `.env` in
the repo root (mode 600). A value of `keychain:<service>` is read from the
macOS Keychain instead, so either storage choice works without code changes.

Secret values are never logged or printed. `redact()` scrubs them from
anything that is, and `redacted_output()` from everything the CLI writes.
"""

from __future__ import annotations

import html
import json
import os
import re
import stat
import subprocess
import sys
import urllib.parse
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterator

import yaml

from jura_growth import paths


@lru_cache(maxsize=None)
def settings() -> dict[str, Any]:
    return _load_yaml(paths.config_dir() / "settings.yaml")


@lru_cache(maxsize=None)
def agent_config(agent: str) -> dict[str, Any]:
    path = paths.config_dir() / f"{agent}.yaml"
    return _load_yaml(path) if path.exists() else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def read_lines(name: str) -> list[str]:
    """A config text file as a list, without blank lines or # comments."""
    path = paths.config_dir() / name
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def reset_caches() -> None:
    global _secrets, _masking_loaded
    for cached in (settings, agent_config, _env_file):
        clear = getattr(cached, "cache_clear", None)  # tests may swap these out
        if clear:
            clear()
    _secrets = None
    _masking_loaded = False
    _from_keychain.clear()
    for forget in _reset_hooks:
        forget()


_reset_hooks: list[Callable[[], None]] = []


def on_reset(forget: Callable[[], None]) -> None:
    """Call `forget()` from `reset_caches()`: for modules that learn values to mask (privacy)."""
    if forget not in _reset_hooks:
        _reset_hooks.append(forget)


# --- secrets ---------------------------------------------------------------


@lru_cache(maxsize=None)
def _env_file() -> dict[str, str]:
    path = paths.env_file()
    if not path.exists():
        return {}
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            f"warning: {path} is readable by other users; run `chmod 600 {path}`",
            file=sys.stderr,
        )
    return _parse_env(path)


def _parse_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def secret(name: str) -> str | None:
    """A secret by name, or None if it isn't set anywhere."""
    value = os.environ.get(name)
    if value is None:
        value = _env_file().get(name)
    if not value:
        return None
    if value.startswith("keychain:"):
        resolved = _keychain(value.removeprefix("keychain:"))
        if resolved and len(resolved) >= MIN_SECRET_LENGTH:
            _from_keychain.add(resolved)  # masked from now on (secret_values)
        return resolved
    return value


def is_set(name: str) -> bool:
    """Whether a setting has a value in the environment or `.env`, without
    reading it: a `keychain:` reference counts as set and the Keychain is
    never asked (setup gaps are names and booleans only, MC §4.3)."""
    value = os.environ.get(name)
    if value is None:
        value = _env_file().get(name)
    return bool(value and value.strip())


def require(name: str) -> str:
    value = secret(name)
    if not value:
        raise MissingSecret(name)
    return value


class MissingSecret(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"{name} is not set (see .env.example)")
        self.name = name


def _keychain(service: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


# --- redaction -------------------------------------------------------------

_SECRET_KEYS = re.compile(r"(key|token|secret|password|webhook|authorization)", re.I)
_SECRET_VALUES = [
    re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+"),
    re.compile(r"\bre_[A-Za-z0-9_]{16,}"),  # Resend
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"),  # Anthropic
    re.compile(r"\bwhsec_[A-Za-z0-9+/=]{16,}"),  # Svix
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}"),
]


# Shorter values would mask ordinary words; no real key or token is this short.
MIN_SECRET_LENGTH = 8

_secrets: tuple[str, ...] | None = None
_finding_secrets = False
_from_keychain: set[str] = set()
_masking_loaded = False


def load_secrets_for_masking() -> None:
    """Read every `keychain:` setting now, so `redact()` masks those values too.

    `secret_values()` only knows the Keychain values this process has read
    itself. A message built from disk (a run summary, a transcript, another
    process's output) can still carry one, so a builder of such a message
    calls this first, through `privacy.load_for_masking()`: today
    `discord.alert()`, the digest and `jura-growth discord post`. It runs the
    Keychain lookups once per process; later calls do nothing.
    """
    global _masking_loaded
    if _masking_loaded:
        return
    _masking_loaded = True
    file = _env_file()
    names = set(file) | set(_parse_env(paths.REPO_ROOT / ".env.example"))
    names |= {name for name, value in os.environ.items() if value.startswith("keychain:")}
    for name in sorted(names):
        raw = os.environ.get(name)
        if raw is None:
            raw = file.get(name, "")
        if raw.startswith("keychain:"):
            secret(name)


def secret_values() -> tuple[str, ...]:
    """The configured secret values, longest first.

    These are the settings named in `.env` or `.env.example` whose name says
    they are secrets (key, token, secret, password, webhook, authorization),
    read from the environment or `.env`, plus every `keychain:` value this
    process has read through `secret()`. A Keychain value is never looked up
    just to mask it: one that was never read can't be printed. Ordinary
    settings (hosts, ports, account ids) are not masked.
    """
    global _secrets, _finding_secrets
    if _secrets is None:
        if _finding_secrets:  # something printed while `.env` was being read
            return tuple(_from_keychain)
        _finding_secrets = True
        try:
            file = _env_file()
            found = set()
            for name in set(file) | set(_parse_env(paths.REPO_ROOT / ".env.example")):
                raw = os.environ.get(name)
                if raw is None:
                    raw = file.get(name, "")
                if _SECRET_KEYS.search(name) and not raw.startswith("keychain:") and len(raw) >= MIN_SECRET_LENGTH:
                    found.add(raw)
            _secrets = tuple(found)
        finally:
            _finding_secrets = False
    return tuple(sorted({*_secrets, *_from_keychain}, key=len, reverse=True))


def redact(value: Any) -> Any:
    """A copy of `value` with secret-looking keys, configured secret values and
    secret-looking values masked."""
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if _SECRET_KEYS.search(str(k)) and v else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        known = secret_values()
        for form in _encoded_forms(known):
            value = value.replace(form, "[redacted]")
        for pattern in _SECRET_VALUES:
            value = pattern.sub("[redacted]", value)
        return _mask_pieces(value, known)
    return value


@lru_cache(maxsize=8)
def _encoded_forms(values: tuple[str, ...]) -> tuple[str, ...]:
    """Each secret value as written, and as it reads once URL-encoded (either case of hex),
    HTML-escaped or JSON-escaped, longest first."""
    forms = set(values)
    for value in values:
        quoted = urllib.parse.quote(value, safe="")
        forms |= {
            quoted,
            re.sub(r"%[0-9A-F]{2}", lambda m: m.group(0).lower(), quoted),
            urllib.parse.quote_plus(value, safe=""),
            html.escape(value),
            json.dumps(value, ensure_ascii=False)[1:-1],
        }
    return tuple(sorted((f for f in forms if len(f) >= MIN_SECRET_LENGTH), key=len, reverse=True))


def _mask_pieces(text: str, values: tuple[str, ...]) -> str:
    """Mask any run of MIN_SECRET_LENGTH or more characters taken from a secret:
    what a cut such as `error[:500]` leaves of one, at its start, its end or
    from the middle. Each match grows to the longest run of the secret it is.

    For a URL (a webhook) only the last path segment, the token, counts: the
    start of the URL is the same for every webhook and every ordinary link.
    """
    tokens, windows = _windows(values)
    if windows is None:
        return text
    spans = []
    for match in windows.finditer(text):
        start, end = match.span()
        if spans and start < spans[-1][1]:
            continue
        while end < len(text) and any(text[start : end + 1] in t for t in tokens):
            end += 1
        while start > 0 and any(text[start - 1 : end] in t for t in tokens):
            start -= 1
        if spans and start <= spans[-1][1]:
            start = spans.pop()[0]
        spans.append((start, end))
    for start, end in reversed(spans):
        text = text[:start] + "[redacted]" + text[end:]
    return text


@lru_cache(maxsize=8)
def _windows(values: tuple[str, ...]) -> tuple[tuple[str, ...], re.Pattern | None]:
    tokens = tuple(
        token
        for token in (v.rstrip("/").rsplit("/", 1)[-1] if "://" in v else v for v in values)
        if len(token) >= MIN_SECRET_LENGTH
    )
    windows = {t[i : i + MIN_SECRET_LENGTH] for t in tokens for i in range(len(t) - MIN_SECRET_LENGTH + 1)}
    if not windows:
        return tokens, None
    return tokens, re.compile("|".join(re.escape(w) for w in sorted(windows)))


class _RedactingStream:
    """stdout or stderr, with `redact()` applied to every write.

    It accepts text only and hides the underlying `buffer`, so click and
    `print` can't write around it.
    """

    def __init__(self, inner):
        self._inner = inner

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("this stream takes text")
        self._inner.write(redact(text))
        return len(text)

    def __getattr__(self, name: str):
        if name == "buffer":
            raise AttributeError(name)
        return getattr(self._inner, name)


@contextmanager
def redacted_output() -> Iterator[None]:
    """Mask secret values in everything written to stdout and stderr meanwhile."""
    saved = sys.stdout, sys.stderr
    if not isinstance(sys.stdout, _RedactingStream):
        sys.stdout = _RedactingStream(sys.stdout)
    if not isinstance(sys.stderr, _RedactingStream):
        sys.stderr = _RedactingStream(sys.stderr)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved
