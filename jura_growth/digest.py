"""The 17:30 daily digest and the morning brief's figures.

`jura-growth digest` writes `data/growth/daily-summary.json`, posts the day to
#daily-digest and keeps a copy at `outputs/growth/digests/YYYY-MM-DD.md`.

The 08:00 morning brief reads `daily-summary.json` (written the evening
before) and prints its `brief_line` in the Jura section.

Each agent plug-in adds its own figures through `digest(conn, day)`.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable

from jura_growth import agents, db, discord, holidays, log, pause, paths, privacy, timeutil

FIGURES_UNAVAILABLE = "digest figures unavailable"


def spend(conn: sqlite3.Connection, day: str) -> float:
    """Headless Claude spend on one SGT day: the `cost_usd` recorded on runs
    that started that day (every stamp is SGT). Recorded figures only: a run
    still going has none yet, and nothing is projected."""
    return db.scalar(conn, "SELECT round(sum(cost_usd), 2) FROM runs WHERE substr(started_at, 1, 10) = ?", (day,)) or 0.0


def build(conn: sqlite3.Connection, day: str | None = None, *, reraise: Callable[[Exception], bool] | None = None) -> dict:
    """The day's figures. One plug-in's error never breaks the digest, unless `reraise` says the
    caller would rather know: the read model retries a lock instead of losing figures to it."""
    day = day or timeutil.today_str()
    runs = db.rows(
        conn,
        "SELECT agent, status, count(*) AS n FROM runs WHERE substr(started_at, 1, 10) = ? "
        "GROUP BY agent, status ORDER BY agent",
        (day,),
    )
    by_agent: dict[str, dict[str, int]] = {}
    for row in runs:
        by_agent.setdefault(row["agent"], {})[row["status"]] = row["n"]
    failures = db.rows(
        conn,
        "SELECT agent, job, error FROM runs WHERE status = 'failed' AND substr(started_at, 1, 10) = ? ORDER BY id",
        (day,),
    )
    paused = pause.flags(conn)
    if pause.pause_file_active():
        paused.insert(0, {"agent": "all", "reason": "PAUSE file present"})
    cost = spend(conn, day)

    figures: dict = {}
    lines: list[str] = []
    brief: list[str] = []
    for module in agents.plugins():
        part_of = getattr(module, "digest", None)
        if not part_of:
            continue
        try:
            part = part_of(conn, day) or {}
        except Exception as error:  # noqa: BLE001 - one agent never breaks the digest
            if reraise and reraise(error):
                raise
            lines.append(f"{module.NAME}: {FIGURES_UNAVAILABLE} ({type(error).__name__})")
            continue
        figures.update(part.get("figures", {}))
        lines += part.get("lines", [])
        brief += part.get("brief", [])

    for name, error in agents.BROKEN.items():
        lines.append(f"{name}: plug-in failed to load ({error[:120]})")
        brief.append(f"{name} plug-in broken")
    if paused:
        brief.append("paused: " + ", ".join(p["agent"] for p in paused))
    if failures:
        brief.append(f"{len(failures)} failed run{'s' if len(failures) != 1 else ''}")
    reminder = holidays.coverage_warning()
    return {
        "date": day,
        "generated_at": timeutil.stamp(),
        "runs": by_agent,
        "failures": failures,
        "paused": paused,
        "claude_cost_usd": cost or 0.0,
        "figures": figures,
        "lines": lines,
        "reminders": [reminder] if reminder else [],
        "brief_line": f"Jura growth, {day}: " + ("; ".join(brief) if brief else "no agent activity recorded") + ".",
    }


def render(summary: dict) -> str:
    out = [f"**Jura growth digest, {summary['date']}**", ""]
    out += [f"- {line}" for line in summary["lines"]] or ["- No agent figures yet."]
    if summary["runs"]:
        out += ["", "Runs today:"]
        for agent, counts in summary["runs"].items():
            parts = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
            out.append(f"- {agent}: {parts}")
    if summary["failures"]:
        out += ["", "Failures:"]
        out += [f"- {f['agent']} `{f['job']}`: {(f['error'] or '')[:200]}" for f in summary["failures"]]
    if summary["paused"]:
        out += ["", "Paused:"]
        out += [f"- {p['agent']}: {p.get('reason') or ''}" for p in summary["paused"]]
    if summary["claude_cost_usd"]:
        out += ["", f"Headless Claude spend today: US${summary['claude_cost_usd']:.2f}"]
    for reminder in summary["reminders"]:
        out += ["", f"Reminder: {reminder}"]
    return "\n".join(out)


def run(conn: sqlite3.Connection, day: str | None = None, *, post: bool = True) -> dict:
    if post:
        privacy.load_for_masking(conn)  # the runs it reports were written by other processes
    summary = build(conn, day)
    json_path = paths.writable(paths.data_dir() / "daily-summary.json")
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    text = render(summary)
    md_path = paths.writable(paths.outputs_dir() / "digests" / f"{summary['date']}.md")
    md_path.write_text(text + "\n", encoding="utf-8")
    if post:
        discord.post(conn, "daily-digest", text, username="Jura growth · digest")
    log.event(conn, "digest.written", {"date": summary["date"], "json": str(json_path), "md": str(md_path)})
    return summary
