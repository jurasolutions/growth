"""Kill switches.

- `jura-growth pause <agent|all>` and `jura-growth resume <agent|all>`.
- A `PAUSE` file in the repo root pauses everything, even if the database is
  broken. It is checked first, before the database is opened.
- An agent pauses itself after N failed runs in a row (settings:
  `auto_pause_after_failures`) and says so in #alerts.

`all` covers every agent except the system jobs (digest, backup), which keep
running so the pause shows up in the digest.
"""

from __future__ import annotations

import sqlite3

from jura_growth import config, discord, log, paths, timeutil


def pause_file_active() -> bool:
    return paths.pause_file().exists()


def system_agents() -> set[str]:
    return set(config.settings().get("system_agents", []))


def is_paused(conn: sqlite3.Connection | None, agent: str) -> str | None:
    """The reason `agent` is paused, or None if it may run."""
    if pause_file_active():
        reason = paths.pause_file().read_text(encoding="utf-8").strip() or "PAUSE file present"
        return f"PAUSE file: {reason}"
    if conn is None:
        return None
    row = conn.execute(
        "SELECT reason FROM pause_flags WHERE agent = ? AND paused = 1", (agent,)
    ).fetchone()
    if row:
        return row["reason"] or "paused"
    if agent not in system_agents():
        row = conn.execute("SELECT reason FROM pause_flags WHERE agent = 'all' AND paused = 1").fetchone()
        if row:
            return f"all paused: {row['reason'] or 'paused'}"
    return None


def pause(conn: sqlite3.Connection, agent: str, reason: str, *, notify: bool = True) -> None:
    conn.execute(
        "INSERT INTO pause_flags (agent, paused, reason, set_at) VALUES (?, 1, ?, ?) "
        "ON CONFLICT (agent) DO UPDATE SET paused = 1, reason = excluded.reason, set_at = excluded.set_at",
        (agent, reason, timeutil.stamp()),
    )
    log.event(conn, "pause", {"agent": agent, "reason": reason}, level="warning", agent=agent)
    if notify:
        discord.alert(conn, f"Paused `{agent}`: {reason}. Resume with `jura-growth resume {agent}`.", agent=agent)


def resume(conn: sqlite3.Connection, agent: str) -> None:
    if agent == "all":
        conn.execute("UPDATE pause_flags SET paused = 0, set_at = ?", (timeutil.stamp(),))
    else:
        conn.execute("UPDATE pause_flags SET paused = 0, set_at = ? WHERE agent = ?", (timeutil.stamp(), agent))
    log.event(conn, "resume", {"agent": agent}, agent=agent)
    discord.post(conn, "alerts", f"**{agent}**: resumed.", dedupe=False)


def flags(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM pause_flags WHERE paused = 1 ORDER BY agent")]


def check_auto_pause(conn: sqlite3.Connection, agent: str) -> bool:
    """Pause `agent` if its last N finished runs all failed. True if it paused."""
    limit = int(config.settings().get("auto_pause_after_failures", 3))
    recent = conn.execute(
        "SELECT status FROM runs WHERE agent = ? AND status IN ('ok', 'failed') ORDER BY id DESC LIMIT ?",
        (agent, limit),
    ).fetchall()
    if len(recent) == limit and all(r["status"] == "failed" for r in recent):
        if not is_paused(conn, agent):
            pause(conn, agent, f"{limit} failed runs in a row")
            return True
    return False
