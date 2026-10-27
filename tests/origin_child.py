"""`jura-growth`, as a real process, with one test kind loaded (seam S13).

The fake kind in `approval_world.py` lives in the test's memory, so a subprocess can't see it.
This kind keeps each item's text in a file under the data folder, so the test and the subprocess
agree on the content. Run as

    python tests/origin_child.py approve A-0001

It changes nothing about how a decision is refused: the subprocess runs the real `approve` and
`skip`, which refuse in any terminal (ADR 0004).
"""

from __future__ import annotations

import sys
import types
from datetime import timedelta

from jura_growth import agents, approvals, paths

KIND = "file-item"
AGENT = "file-item-agent"


def item_path(subject: str):
    return paths.data_dir() / "file-items" / subject.replace(":", "_")


def write_item(subject: str, text: str) -> None:
    path = item_path(subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FileKind:
    name = KIND
    decision_args = ()

    def content(self, conn, subject):
        path = item_path(subject)
        return path.read_bytes() if path.exists() else None

    def preview(self, conn, subject):
        path = item_path(subject)
        return approvals.Preview(title=f"file item {subject}", text=path.read_text() if path.exists() else "", reason="a test asked")

    def deadlines(self, conn, subject, now):
        return approvals.Deadlines(decide_by=now + timedelta(days=2), use_by=now + timedelta(days=3))


PLUGIN = types.SimpleNamespace(NAME=AGENT, approval_kinds=lambda: {KIND: FileKind()}, __name__="file_item_plugin")


def plugins_with_kind(real):
    return lambda: (*real(), PLUGIN)


if __name__ == "__main__":
    agents.plugins = plugins_with_kind(agents.plugins)
    from jura_growth.cli import main

    sys.argv = ["jura-growth", *sys.argv[1:]]
    main()
