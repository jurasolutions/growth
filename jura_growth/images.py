"""Image files the engine renders or attaches.

The render helper: an HTML page, built on `design-system/` tokens, drawn to a
PNG by headless Google Chrome. The caller passes Chrome's path and limits in
(`Chrome`), so the core reads no agent's settings: the social cards
(`agents/social/render.py`) and the one-pager's grid both come through here.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jura_growth import paths

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class RenderError(RuntimeError):
    pass


def png_size(path: str | os.PathLike[str]) -> tuple[int, int] | None:
    """(width, height) from a PNG's IHDR chunk, or None if it isn't a PNG."""
    with open(path, "rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return width, height


# The chunks a PNG's pixels need. Every other chunk (text, metadata, anything
# private) is dropped before an image leaves for Discord.
PIXEL_CHUNKS = (b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND")


def pixels_only(data: bytes) -> bytes | None:
    """The PNG with only the chunks in PIXEL_CHUNKS, so nothing but the picture
    goes out; None if `data` isn't a well-formed PNG."""
    if not data.startswith(PNG_SIGNATURE):
        return None
    out, at = [PNG_SIGNATURE], len(PNG_SIGNATURE)
    while at < len(data):
        if at + 8 > len(data):
            return None
        (length,) = struct.unpack(">I", data[at : at + 4])
        kind = data[at + 4 : at + 8]
        end = at + 12 + length
        if end > len(data):
            return None
        if kind in PIXEL_CHUNKS:
            out.append(data[at:end])
        at = end
        if kind == b"IEND":
            break
    return b"".join(out)


# --- rendering with headless Chrome ---------------------------------------------------


def design_system() -> Path:
    """`jurasolutions/design-system/`: read-only, linked by file URL."""
    return paths.JURA_ROOT / "design-system"


@dataclass(frozen=True)
class Chrome:
    """Which Chrome to run and how long to give it. `JURA_GROWTH_CHROME`,
    when set, overrides `path` (`chrome_path`)."""

    path: str | os.PathLike[str]
    virtual_time_budget_ms: int = 8000
    timeout_seconds: int = 60


def chrome_path(configured: str | os.PathLike[str]) -> Path | None:
    """`JURA_GROWTH_CHROME` or else `configured`, if it is an executable file."""
    candidate = Path(os.environ.get("JURA_GROWTH_CHROME") or configured)
    return candidate if candidate.exists() and os.access(candidate, os.X_OK) else None


def run_chrome(args: list[str], chrome: Chrome, *, offline: bool) -> subprocess.CompletedProcess:
    """Headless Chrome on a throwaway profile. `offline` switches its host
    resolver off, so the page can't reach the network."""
    binary = chrome_path(chrome.path)
    if not binary:
        raise RenderError(f"Google Chrome not found at {os.environ.get('JURA_GROWTH_CHROME') or chrome.path}")
    profile = tempfile.mkdtemp(prefix="jura-chrome-")
    argv = [
        str(binary),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--mute-audio",
        f"--user-data-dir={profile}",
        f"--virtual-time-budget={chrome.virtual_time_budget_ms}",
    ]
    if offline:
        argv.append("--host-resolver-rules=MAP * ~NOTFOUND")
    try:
        return subprocess.run(argv + args, capture_output=True, text=True, timeout=chrome.timeout_seconds)
    except subprocess.TimeoutExpired as error:
        raise RenderError(f"Chrome took longer than {chrome.timeout_seconds}s") from error
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def screenshot(page: str, out: Path, width: int, height: int, *, chrome: Chrome, offline: bool = False) -> Path:
    """Draw the HTML `page` to the PNG `out`, exactly `width` by `height`."""
    out = paths.writable(Path(out))
    with tempfile.TemporaryDirectory(prefix="jura-card-") as folder:
        source = Path(folder) / "card.html"
        source.write_text(page, encoding="utf-8")
        if out.exists():
            out.unlink()
        result = run_chrome([f"--window-size={width},{height}", f"--screenshot={out}", source.as_uri()], chrome, offline=offline)
    if not out.exists():
        raise RenderError(f"Chrome wrote no image (exit {result.returncode}): {(result.stderr or '')[-300:]}")
    actual = png_size(out)
    if actual is None:
        raise RenderError(f"{out.name} is not a PNG")
    if actual != (width, height):
        raise RenderError(f"{out.name} is {actual[0]}×{actual[1]}, expected {width}×{height}")
    return out
