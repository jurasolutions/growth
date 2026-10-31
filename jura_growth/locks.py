"""Exclusive locks between processes, as files under `data/growth/locks/`.

`held(name)` takes an fcntl lock without waiting and yields whether it got it;
`is_held(name)` asks whether another process holds it now.
The runner holds one per job (`<job>.lock`), and the outreach sender holds
`outreach-send.lock` around every `send-due`, so two runs never overlap.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from jura_growth import paths

# The skip reason when a job's lock is taken: its previous run hasn't finished.
STILL_GOING = "previous run still going"
# The one lock every browser job takes, since they share Chrome and the accounts (ADR 0006).
BROWSER = "browser"


def _path(name: str) -> Path:
    return paths.data_dir() / "locks" / f"{name}.lock"


@contextmanager
def held(name: str) -> Iterator[bool]:
    path = paths.writable(_path(name))
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


def is_held(name: str) -> bool:
    """Whether another process holds the lock now. It takes the lock for a
    moment to find out, and creates nothing if no lock file exists."""
    if not _path(name).exists():
        return False
    with held(name) as got:
        return not got
