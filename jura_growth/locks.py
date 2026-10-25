"""Exclusive locks between processes, as files under `data/growth/locks/`.

`held(name)` takes an fcntl lock without waiting and yields whether it got it.
The runner holds one per job (`<job>.lock`), and the outreach sender holds
`outreach-send.lock` around every `send-due`, so two runs never overlap.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from typing import Iterator

from jura_growth import paths


@contextmanager
def held(name: str) -> Iterator[bool]:
    path = paths.writable(paths.data_dir() / "locks" / f"{name}.lock")
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()
