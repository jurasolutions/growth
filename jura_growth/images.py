"""Image files the engine renders or attaches."""

from __future__ import annotations

import os
import struct

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(path: str | os.PathLike[str]) -> tuple[int, int] | None:
    """(width, height) from a PNG's IHDR chunk, or None if it isn't a PNG."""
    with open(path, "rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    return width, height
