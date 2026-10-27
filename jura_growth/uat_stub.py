"""The guard on the UAT stub's base URLs (X13; tickets 06 and 18).

`uat.md` points Resend and D1 at one local stub (`uv run python -m tests.resend_stub`) with
`JURA_GROWTH_RESEND_BASE_URL` and `JURA_GROWTH_D1_BASE_URL`. This module is the one place that
decides whether they may be used:

- each must be a loopback http URL;
- the data folder must be a temporary one, so a real run can never send through the stub, read its
  empty suppression list, or be fooled into thinking it did;
- they are a pair: with either set, both must be. A stubbed suppression list must never meet real
  Resend, and stubbed sends must never be checked against the real D1.

A refused URL is never swapped for the real service: callers raise, and `live_problems` lists why.

`loopback_problem` is the one loopback guard: the stubs' URLs here and the publish rehearsal's
fixture site (`agents/publish/fixture.py`, BP-07) both go through it. It reads a URL the way a
browser's WHATWG parser would, refusing anything the two parsers could read differently.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from jura_growth import paths

RESEND_ENV = "JURA_GROWTH_RESEND_BASE_URL"
D1_ENV = "JURA_GROWTH_D1_BASE_URL"
PAIR = (RESEND_ENV, D1_ENV)
LOOPBACK = ("127.0.0.1", "localhost", "::1")
# Anything a browser reads differently from Python's `urlsplit`: a backslash (read as `/`),
# percent-encoding, a user name, whitespace or a control character (stripped), and any non-ASCII
# character (folded by IDNA, so `。` reads as `.`). Code review 07, B1.
_UNSAFE = re.compile(r"[\\%@\s\x00-\x1f\x7f]|[^\x00-\x7f]")


class StubRefused(RuntimeError):
    pass


def _temporary(folder: Path) -> bool:
    roots = {Path(tempfile.gettempdir()), Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders")}
    return any(root.exists() and paths.is_within(folder, root.resolve()) for root in roots)


def temporary_data_problem() -> str | None:
    """Why the data folder isn't a temporary one the UAT stub may serve, or None."""
    value = os.environ.get("JURA_GROWTH_DATA_DIR")
    if not value:
        return "JURA_GROWTH_DATA_DIR isn't set: point it at a folder made with `mktemp -d`"
    folder = Path(value).resolve()
    if paths.is_within(folder, paths.JURA_ROOT) or not _temporary(folder):
        return f"the data folder {folder} is not a temporary folder: make one with `mktemp -d`, outside jurasolutions/"
    return None


def loopback_url_ok(value: str, hosts: tuple[str, ...] = LOOPBACK, *, bare: bool = False) -> bool:
    """Whether `value` is a plain `http://` URL on exactly one of `hosts`, read as a browser reads
    it: no character the parsers disagree on (`_UNSAFE`), a well-formed port, and, with `bare`,
    no path beyond `/`, query or fragment."""
    if _UNSAFE.search(value):
        return False
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises on a malformed port
    except ValueError:
        return False
    if bare and (parts.path not in ("", "/") or parts.query or parts.fragment or "?" in value or "#" in value):
        return False
    return parts.scheme == "http" and parts.hostname in hosts


def loopback_problem(variable: str, *, hosts: tuple[str, ...] = LOOPBACK, bare: bool = False,
                     expected: str = "the local UAT stub (http://127.0.0.1:<port>)",
                     purpose: str = "the UAT stub") -> str | None:
    """Why the loopback URL in `variable` may not be used, or None (also None when it is unset):
    it must pass `loopback_url_ok`, and the data folder must be a temporary one."""
    value = os.environ.get(variable)
    if not value:
        return None
    if not loopback_url_ok(value, hosts, bare=bare):
        return f"{variable} must point at {expected}, not {value}"
    problem = temporary_data_problem()
    return f"{variable} is for {purpose} only, and {problem}" if problem else None


def url_problem(variable: str) -> str | None:
    """Why the base URL in `variable` may not be used, or None (also None when it is unset)."""
    return loopback_problem(variable)


def pair_problem() -> str | None:
    """Why the two base URLs don't make a pair, or None (both set, or neither)."""
    present = [variable for variable in PAIR if os.environ.get(variable)]
    if len(present) != 1:
        return None
    (have,) = present
    (missing,) = [variable for variable in PAIR if variable != have]
    return (f"{have} is set but {missing} isn't: the UAT stub stands in for Resend and D1 together, "
            f"so set both to it (http://127.0.0.1:<port>) or neither")


def base(variable: str, refused: type[StubRefused] = StubRefused) -> str | None:
    """The stub's base URL for `variable`, without a trailing slash, or None when neither stub
    URL is set. Raises `refused` with the reason when the URL, or the pair, may not be used."""
    problem = url_problem(variable) or pair_problem()
    if problem:
        raise refused(problem)
    value = os.environ.get(variable)
    return value.rstrip("/") if value else None
