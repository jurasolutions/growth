"""Settings and secrets.

Settings come from `config/settings.yaml`; each agent may keep its own
`config/<agent>.yaml`. Secrets come from the environment, then from `.env` in
the repo root (mode 600). A value of `keychain:<service>` is read from the
macOS Keychain instead, so either storage choice works without code changes.

Secret values are never logged. `redact()` scrubs them from anything that is.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

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
    for cached in (settings, agent_config, _env_file):
        clear = getattr(cached, "cache_clear", None)  # tests may swap these out
        if clear:
            clear()


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


def redact(value: Any) -> Any:
    """A copy of `value` with secret-looking keys and values masked."""
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if _SECRET_KEYS.search(str(k)) and v else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for pattern in _SECRET_VALUES:
            value = pattern.sub("[redacted]", value)
        return value
    return value
