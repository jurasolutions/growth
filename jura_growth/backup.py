"""Nightly backup of `growth.db`, keeping 14 days, plus pruning of transcripts, the
one-pager's pictures and grids, and the Discord outbox (`retention` in
config/settings.yaml). Each plug-in's own `retention(conn)` hook runs first, so
tonight's copy doesn't hold what it removed."""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from jura_growth import agents, caps, config, discord, log, paths, timeutil


def plugin_retention(conn: sqlite3.Connection) -> dict:
    """Each plug-in's `retention(conn)`, by name. One that breaks never stops the backup."""
    found: dict = {}
    for module in agents.plugins():
        hook = getattr(module, "retention", None)
        if not callable(hook):
            continue
        name = getattr(module, "NAME", module.__name__)
        try:
            found[name] = hook(conn)
        except Exception as error:  # noqa: BLE001
            log.event(conn, "backup.retention_failed", {"agent": name, "error": type(error).__name__}, level="error")
    return found


def backup(conn: sqlite3.Connection) -> Path:
    retained = plugin_retention(conn)
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
    grids = prune_pictures()
    outbox = prune_outbox()
    log.event(conn, "backup.written", {"file": str(target), "removed": removed, "transcripts_pruned": pruned,
                                       "browser_work_pruned": work, "grids_pruned": grids, "outbox_pruned": outbox,
                                       **{f"{name.replace('-', '_')}_retention": kept for name, kept in retained.items()}})
    return target


def prune_outbox() -> int:
    """Delete Discord outbox days older than `caps.OUTBOX_DAYS`, or `retention.outbox_days` if shorter. A
    message Discord refused can hold what a person wrote, and nothing replays this folder."""
    keep = caps.effective(caps.OUTBOX_DAYS, config.settings().get("retention", {}).get("outbox_days"))
    cutoff = timeutil.today() - timedelta(days=keep - 1)
    folder = discord.outbox_dir()
    count = 0
    for file in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        try:
            day = date.fromisoformat(file.stem)
        except ValueError:
            continue
        if day < cutoff:
            file.unlink()
            count += 1
    return count


# What the one-pager writes, by name and date: grid-<day>.png, picture-<day>.png and .html.
_DATED_PICTURE = re.compile(r"(?:grid|picture)-(\d{4}-\d{2}-\d{2})\.(?:png|html)")


def prune_pictures() -> int:
    """Delete the one-pager's dated pictures and pages older than
    `retention.one_pager_days` (14 by default, the grid's own span): each shows
    what growth.db holds, and a page keeps its approval reasons as text."""
    keep = int(config.settings().get("retention", {}).get("one_pager_days", 14))
    cutoff = timeutil.today() - timedelta(days=keep - 1)
    folder = paths.one_pager_dir()
    count = 0
    for file in sorted(folder.iterdir()) if folder.exists() else []:
        named = _DATED_PICTURE.fullmatch(file.name)
        try:
            day = date.fromisoformat(named.group(1)) if named else None
        except ValueError:
            continue
        if day is None:
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
