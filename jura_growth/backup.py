"""Nightly backup of `growth.db`, keeping 14 days, plus pruning of transcripts
and the one-pager's grid PNGs (`retention` in config/settings.yaml)."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from jura_growth import caps, config, log, paths, timeutil


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
    work = prune_browser_work()
    grids = prune_grids()
    log.event(conn, "backup.written", {"file": str(target), "removed": removed, "transcripts_pruned": pruned,
                                       "browser_work_pruned": work, "grids_pruned": grids})
    return target


def prune_grids() -> int:
    """Delete one-pager grids older than `retention.one_pager_days` (14 by
    default, the grid's own span): each is a picture of what growth.db holds."""
    keep = int(config.settings().get("retention", {}).get("one_pager_days", 14))
    cutoff = timeutil.today() - timedelta(days=keep - 1)
    folder = paths.one_pager_dir()
    count = 0
    for file in sorted(folder.glob("grid-*.png")) if folder.exists() else []:
        try:
            day = date.fromisoformat(file.stem.removeprefix("grid-"))
        except ValueError:
            continue
        if day < cutoff:
            file.unlink()
            count += 1
    return count


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


def _browser_days() -> int:
    """`caps.BROWSER_TRANSCRIPT_DAYS`, or `retention.browser_transcripts_days` if shorter."""
    configured = config.settings().get("retention", {}).get("browser_transcripts_days")
    return caps.effective(caps.BROWSER_TRANSCRIPT_DAYS, configured)


def prune_browser_work() -> int:
    """Delete what the jobs in `caps.THIRD_PARTY_TEXT_JOBS` left in their scratch folders
    (`work/<job>/`) once it is as old as their transcripts may get: the live text a run read back
    from a page, triage's drafts, and the read-only image copies. Judged by the newest file in each entry. Returns how many entries went."""
    cutoff = (timeutil.now_sgt() - timedelta(days=_browser_days())).timestamp()
    count = 0
    for job in sorted(caps.THIRD_PARTY_TEXT_JOBS):
        folder = paths.work_dir(job)
        for entry in sorted(folder.iterdir()) if folder.exists() else []:
            files = [entry, *entry.rglob("*")] if entry.is_dir() else [entry]
            if max(f.stat().st_mtime for f in files) >= cutoff:
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            count += 1
    return count


def prune_transcripts() -> int:
    """Delete day folders older than `retention.transcripts_days` (30), and, sooner, the
    transcripts of the jobs in `caps.THIRD_PARTY_TEXT_JOBS`, which hold third-party text: after
    `caps.BROWSER_TRANSCRIPT_DAYS` (7), or `retention.browser_transcripts_days` if shorter
    (BP §4.7). Returns how many folders and browser transcripts went."""
    keep = int(config.settings().get("retention", {}).get("transcripts_days", 30))
    cutoff = timeutil.today() - timedelta(days=keep)
    browser_cutoff = timeutil.today() - timedelta(days=_browser_days())
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
        elif day < browser_cutoff:
            for job in caps.THIRD_PARTY_TEXT_JOBS:
                for file in folder.glob(f"*-{job}.jsonl"):
                    file.unlink()
                    count += 1
    return count
