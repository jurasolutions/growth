"""Nightly backup of `growth.db`, keeping 14 days, plus transcript pruning."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from jura_growth import config, log, paths, timeutil


def backup(conn: sqlite3.Connection) -> Path:
    target = paths.writable(paths.data_dir() / "backups" / f"growth-{timeutil.today_str()}.db")
    if target.exists():
        target.unlink()
    destination = sqlite3.connect(target)
    try:
        conn.backup(destination)
    finally:
        destination.close()
    removed = prune_backups()
    pruned = prune_transcripts()
    log.event(conn, "backup.written", {"file": str(target), "removed": removed, "transcripts_pruned": pruned})
    return target


def prune_backups() -> list[str]:
    keep = int(config.settings().get("retention", {}).get("backups_days", 14))
    cutoff = timeutil.today() - timedelta(days=keep - 1)
    removed = []
    for file in sorted((paths.data_dir() / "backups").glob("growth-*.db")):
        try:
            day = date.fromisoformat(file.stem.removeprefix("growth-"))
        except ValueError:
            continue
        if day < cutoff:
            file.unlink()
            removed.append(file.name)
    return removed


def prune_transcripts() -> int:
    keep = int(config.settings().get("retention", {}).get("transcripts_days", 30))
    cutoff = timeutil.today() - timedelta(days=keep)
    count = 0
    root = paths.data_dir() / "transcripts"
    if not root.exists():
        return 0
    for folder in root.iterdir():
        try:
            day = date.fromisoformat(folder.name)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(folder)
            count += 1
    return count
