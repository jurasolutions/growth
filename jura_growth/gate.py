"""The brand gate every outgoing item passes before it is queued, sent or posted.

A failure blocks the item, logs the reasons and posts them to #alerts. The
agent may regenerate once; a second failure drops the item (foundation PRD
§5.6). Attempts are counted per item key in `qa_attempts`, so the rule holds
across separate `jura-growth` calls within a run.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from jura_growth import brand_check, discord, log, timeutil

MAX_ATTEMPTS = 2


@dataclass
class GateResult:
    status: str  # pass, retry, dropped
    result: brand_check.Result
    attempts: int

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def message(self) -> str:
        if self.passed:
            return "pass"
        reasons = "\n".join(f"  - {r}" for r in self.result.reasons())
        if self.status == "retry":
            return f"fail (attempt {self.attempts} of {MAX_ATTEMPTS}; regenerate once)\n{reasons}"
        return f"fail (attempt {self.attempts} of {MAX_ATTEMPTS}; item dropped)\n{reasons}"


def gate(
    conn: sqlite3.Connection,
    item_key: str,
    text: str,
    *,
    agent: str,
    alert: bool = True,
    **check_args,
) -> GateResult:
    result = brand_check.check(text, **check_args)
    row = conn.execute("SELECT attempts FROM qa_attempts WHERE item_key = ?", (item_key,)).fetchone()
    previous = row["attempts"] if row else 0

    if previous >= MAX_ATTEMPTS:
        log.event(conn, "brand.dropped", {"item": item_key, "reason": "already dropped"}, agent=agent)
        return GateResult("dropped", result, previous)

    if result.passed:
        log.event(conn, "brand.pass", {"item": item_key, "attempt": previous + 1}, agent=agent)
        conn.execute("DELETE FROM qa_attempts WHERE item_key = ?", (item_key,))
        return GateResult("pass", result, previous + 1)

    attempts = previous + 1
    conn.execute(
        "INSERT INTO qa_attempts (item_key, agent, attempts, last_issues_json, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (item_key) DO UPDATE SET attempts = excluded.attempts, "
        "last_issues_json = excluded.last_issues_json, updated_at = excluded.updated_at",
        (item_key, agent, attempts, json.dumps(result.as_dict()["issues"]), timeutil.stamp()),
    )
    status = "retry" if attempts < MAX_ATTEMPTS else "dropped"
    log.event(
        conn,
        f"brand.{'fail' if status == 'retry' else 'dropped'}",
        {"item": item_key, "attempt": attempts, "issues": result.reasons()},
        level="warning",
        agent=agent,
    )
    if alert:
        verdict = "regenerating once" if status == "retry" else "dropped"
        reasons = "\n".join(f"- {r}" for r in result.reasons()[:8])
        discord.alert(conn, f"Brand check failed for `{item_key}` ({verdict}):\n{reasons}", agent=agent)
    return GateResult(status, result, attempts)
