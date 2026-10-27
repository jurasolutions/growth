"""How many build handoffs one answer to Dispatch holds (technical review N5; code review 12).

Dispatch reads build handoffs in one answer, `jura-growth remote --json -- apps handoffs`, at most
`JSON_LIMIT` bytes, measured one way: the answer's compact JSON in UTF-8 (`size()`). Remote wraps
the apps plug-in's own `apps handoffs --json` in its envelope (`contract`, `ok`, `answer`,
`exit_code` and a `text` of at most 1,900 characters). So the plug-in fits its handoffs within
`HANDOFF_LIMIT`, which leaves `ENVELOPE` bytes for that envelope, and whatever it hands out fits
Dispatch's answer too. Both fit with the one policy, `fit()`; remote's own fit is the backstop.
The plug-in imports this module; the core never imports the plug-in.
"""

from __future__ import annotations

import json
from typing import Callable

JSON_LIMIT = 64 * 1024
# Remote's envelope at its largest: 1,900 characters of text at 6 bytes each once escaped (a
# control character as \u00XX), plus its other fields. `test_handoff_fit.py` checks it holds.
ENVELOPE = 12 * 1024
HANDOFF_LIMIT = JSON_LIMIT - ENVELOPE
TOO_LARGE = f"the PRD is too large to hand out in one answer ({JSON_LIMIT // 1024} KB)"


def encode(answer: dict) -> str:
    """An answer as it is printed: compact JSON, non-ASCII as written."""
    return json.dumps(answer, ensure_ascii=False)


def size(answer: dict) -> int:
    return len(encode(answer).encode("utf-8"))


def fit(entries: list[dict], *, wrap: Callable[[dict], dict], limit: int = JSON_LIMIT, more: int = 0) -> dict:
    """`{"handoffs": [...], "more": n}` for `entries`, oldest first, such that
    `size(wrap(that))` is at most `limit`.

    An entry that fits beside the ones taken is taken. An entry whose handoff wouldn't fit even
    once every earlier handoff is built (beside only the entries without one, which never leave
    on their own) is taken without it, `TOO_LARGE` as its problem, so it never holds up the
    entries after it. Any other entry waits in `more` for a later poll. `more` starts from what
    an earlier fit already left out."""
    most = more + len(entries)  # the count's widest value, so the measure never comes in short

    def fits(handoffs: list[dict]) -> bool:
        return size(wrap({"handoffs": handoffs, "more": most})) <= limit

    taken: list[dict] = []
    waiting = more
    for entry in entries:
        if fits([*taken, entry]):
            taken.append(entry)
            continue
        staying = [e for e in taken if e.get("handoff") is None]
        if entry.get("handoff") is not None and not fits([*staying, entry]):
            named = {**entry, "handoff": None, "problem": TOO_LARGE}
            if fits([*taken, named]):
                taken.append(named)
                continue
        waiting += 1
    return {"handoffs": taken, "more": waiting}
