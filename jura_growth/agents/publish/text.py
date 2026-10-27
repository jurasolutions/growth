"""The one normal form for comparing posted text (BP QA Q9; final review St3).

The transcript audit (`audit.py`) and `publish done --live-text-file` (`commands.py`) must agree on
whether the text a run typed, or the text live on the page, matches the approved text. Both use
`normal()`. This is for comparing only: the approval's hash covers the exact bytes (ADR 0003).
"""

from __future__ import annotations

import re
import unicodedata


def normal(text: str) -> str:
    """Unicode NFC, every run of whitespace collapsed to one space, and trimmed."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def same(approved: str, live: str) -> bool:
    """The live text matches the approved text after `normal()`; any other difference is a
    mismatch."""
    return normal(approved) == normal(live)
