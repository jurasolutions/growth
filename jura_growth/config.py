"""Settings and secrets.

Settings come from `config/settings.yaml`; each agent may keep its own
`config/<agent>.yaml`. Secrets come from the environment, then from `.env` in
the repo root (mode 600). A value of `keychain:<service>` is read from the
macOS Keychain instead, so either storage choice works without code changes.

Secret values are never logged or printed. `redact()` scrubs them from
anything that is, and `redacted_output()` from everything the CLI writes.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

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
    global _secrets
    for cached in (settings, agent_config, _env_file):
        clear = getattr(cached, "cache_clear", None)  # tests may swap these out
        if clear:
            clear()
    _secrets = None


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
        return _keychain(value.removeprefix("keychain:"))
    return value


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


def secret_values() -> tuple[str, ...]:
    """The configured secret values, longest first.

    A configured secret is a setting named in `.env` or `.env.example` whose
    name says it is one (key, token, secret, password, webhook), read from the
    environment or `.env`, or any setting stored as a `keychain:` reference,
    resolved. Ordinary settings (hosts, ports, account ids) are not masked.
    """
    global _secrets, _finding_secrets
    if _secrets is not None:
        return _secrets
    if _finding_secrets:  # something printed while `.env` was being read
        return ()
    _finding_secrets = True
    try:
        file = _env_file()
        found = set()
        for name in set(file) | set(_parse_env(paths.REPO_ROOT / ".env.example")):
            raw = os.environ.get(name)
            if raw is None:
                raw = file.get(name, "")
            if raw.startswith("keychain:"):
                value = _keychain(raw.removeprefix("keychain:")) or ""
            elif _SECRET_KEYS.search(name):
                value = raw
            else:
                continue
            if len(value) >= MIN_SECRET_LENGTH:
                found.add(value)
        _secrets = tuple(sorted(found, key=len, reverse=True))
    finally:
        _finding_secrets = False
    return _secrets


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
        for secret_value in secret_values():
            value = value.replace(secret_value, "[redacted]")
        for pattern in _SECRET_VALUES:
            value = pattern.sub("[redacted]", value)
        return value
    return value


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
