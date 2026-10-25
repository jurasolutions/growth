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
