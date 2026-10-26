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
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from jura_growth import paths

RESEND_ENV = "JURA_GROWTH_RESEND_BASE_URL"
D1_ENV = "JURA_GROWTH_D1_BASE_URL"
PAIR = (RESEND_ENV, D1_ENV)
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


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


def url_problem(variable: str) -> str | None:
    """Why the base URL in `variable` may not be used, or None (also None when it is unset)."""
    base = os.environ.get(variable)
    if not base:
        return None
    parts = urlsplit(base)
    if parts.scheme != "http" or parts.hostname not in _LOOPBACK:
        return f"{variable} must point at the local UAT stub (http://127.0.0.1:<port>), not {base}"
    problem = temporary_data_problem()
    return f"{variable} is for the UAT stub only, and {problem}" if problem else None


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
