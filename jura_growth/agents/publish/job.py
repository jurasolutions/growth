"""The publish job's hooks (browser publishing PRD §5.8).

- `precheck` (before Claude starts): an auth variable that would hide the Chrome tools is a plain
  skip Ting Yu should see (AC-P9.5). Otherwise it runs `items.sync()` in a committed transaction
  and posts the cards that raised (`cards.sweep_safely()`), so a changed post gets its new card
  whether or not anything is due (code review 02, B1), then asks `claim.claimable()`, read-only:
  nothing claimable is `NothingToDo("nothing due")`, a quiet run with no Claude (AC-P8.2).
- `setup_gaps`: the same auth variables, by name, for `jura-growth status`.
- `after_run`: see its docstring.
- `run_update`: "Produced:" for a run that claimed an item, and no update for any other run
  (`run_update: claimed-only`).
"""

from __future__ import annotations

import os
import sqlite3

from jura_growth import agents, cards, db, discord, log, pause, timeutil, transcripts
from jura_growth.agents.publish import audit, claim, commands, items, scope

# With either set, Claude Code keeps Chrome integration off, even with --chrome (spike §1).
AUTH_VARIABLES = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def precheck(job: str, conn: sqlite3.Connection):
    """A skip reason, `NothingToDo`, or None to start the run."""
    if job != "publish":
        return None
    for name in AUTH_VARIABLES:
        if os.environ.get(name):
            return (f"{name} is set, so Claude Code would start without the Chrome tools; remove it from the "
                    f"environment scheduled runs get (the publish job needs the claude.ai login)")
    with db.transaction(conn):
        items.sync(conn)
    cards.sweep_safely(conn)
    if not claim.claimable(conn):
        return agents.NothingToDo(claim.NOTHING_DUE)
    return None


def setup_gaps() -> list:
    from jura_growth.health import Gap

    return [Gap(name, ok=not os.environ.get(name), must_be_unset=True) for name in AUTH_VARIABLES]


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """The run's last word, before its row, the alert and auto-pause see the outcome (BP §5.8).

    1. Settle as `unknown` this run's open claims, and any left by an earlier run that ended
       without its own `after_run` (the process was killed); that fails the run and pauses
       `publish`. A Terminal claim (no run) is left to Ting Yu, who can `publish resolve` it.
    2. Audit the run's transcript (`audit.py`): any failure fails the run and pauses `publish`.
    3. A run that found no browser and claimed nothing alerts once a day (AC-P9.4).
    4. A run that claimed an item gets a summary written here from the item's own record (the
       A-id, the platform, what happened, and the URL or stop reason), never the model's text,
       so neither the run row nor the run update can quote page text.

    None when nothing changes: no claim, no finding, no unknown item."""
    if run_id is None:
        return None
    from jura_growth import runner

    unknown = _settle_unknown(conn, run_id)
    claimed = _claimed_by(conn, run_id)
    found = _audit(run_id, claimed)
    if found.failures:
        with db.transaction(conn):
            log.event(conn, "publish.audit_failed", {"failures": found.failures}, level="error", agent=items.AGENT,
                      run_id=run_id)
            pause.pause(conn, items.AGENT, f"the audit of run {run_id} failed", notify=False)
    if found.no_browser and not claimed:
        _no_browser(conn, run_id)
    if not (unknown or claimed or found.failures):
        return None

    errors = list(unknown)
    if found.failures:
        errors.append(f"The audit of run {run_id} failed: {'; '.join(found.failures)}. Publishing is paused for "
                      f"every item until you resume it: {commands.RESUME}.")
    lines = [_line(conn, item) for item in claimed] + [f"Warning: {w}" for w in found.warnings]
    status = "failed" if errors or outcome.status == "failed" else outcome.status
    if not errors and status == "failed":
        errors = [line for line in lines if " · stopped" in line] or [outcome.error]
    summary = "\n".join(lines) if claimed else outcome.summary
    return runner.Outcome(status, summary=summary, error=" ".join(errors) if status == "failed" else "",
                          cost_usd=outcome.cost_usd)


def run_update(conn: sqlite3.Connection, run) -> list[str] | None:
    """"Produced:" for a run that claimed an item (`1 post`, `1 stopped`); None posts no update
    (`run_update: claimed-only`)."""
    if run.id is None:
        return None
    claimed = _claimed_by(conn, run.id)
    if not claimed:
        return None
    from jura_growth.run_update import count

    words = {"posted": 0, "stopped": 0, "unknown": 0}
    for item in claimed:
        if item.state == "done":
            words["posted"] += 1
        elif item.state in words:
            words[item.state] += 1
    produced = [count(n, "post") if word == "posted" else f"{n} {word}" for word, n in words.items() if n]
    return produced


def _claimed_by(conn: sqlite3.Connection, run_id: int) -> list[items.Item]:
    rows = conn.execute("SELECT * FROM publish_items WHERE run_id = ? AND claimed_at IS NOT NULL ORDER BY id",
                        (run_id,)).fetchall()
    return [items.Item.from_row(r) for r in rows]


def _line(conn: sqlite3.Connection, item: items.Item) -> str:
    """`A-0001 · Facebook Page · posted · <url>`, from the item's own record."""
    from jura_growth.agents.social.settings import load

    record = items.claimed_request(conn, item)
    shown = record.id if record else item.label
    try:
        where = load().platforms[item.platform].label
    except Exception:  # noqa: BLE001 - the label is only for reading
        where = item.platform
    if item.state == "done":
        what = f"posted · {item.post_url}"
        if item.live_text_matches == 0:
            what += " · the live text doesn't match the approved text; publishing is paused"
    elif item.state == "stopped":
        what = f"stopped · {item.stop_reason}: {commands.STOP_REASONS.get(item.stop_reason or '', 'a stop signal')}"
    elif item.state == "unknown":
        what = "unknown · it may or may not have been posted"
    else:
        what = item.state
    return f"{shown} · {where} · {what}"


def _audit(run_id: int, claimed: list[items.Item]) -> audit.Audit:
    path = transcripts.find(run_id)
    if path is None:
        return audit.Audit()
    approved = [item.content.get("text", "") for item in claimed]
    images = [str(copy) for item in claimed for copy in item.content.get("copies", [])]
    return audit.audit(transcripts.read(path), hosts=scope.browser_hosts(), approved=approved, images=images)


def _no_browser(conn: sqlite3.Connection, run_id: int) -> None:
    """Log it, and alert only on the first such run of the day (AC-P9.4)."""
    today = timeutil.today_str()
    earlier = db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'publish.no_browser' AND ts LIKE ?", (f"{today}%",))
    log.event(conn, "publish.no_browser", {"run": run_id}, level="warning", agent=items.AGENT, run_id=run_id)
    if earlier:
        return
    discord.alert(conn, "No browser was connected when the publish job ran, so nothing was posted. Approved items stay "
                        "approved until their deadline. On the Mac, open Chrome with the Claude extension signed in to "
                        "the same account as Claude Code. This is the only alert about it today.", agent=items.AGENT)


def _settle_unknown(conn: sqlite3.Connection, run_id: int) -> list[str]:
    """Mark open claims `unknown`, pause `publish`, and return the #alerts lines that say how to
    settle each."""
    rows = conn.execute(
        "SELECT p.* FROM publish_items p LEFT JOIN runs r ON r.id = p.run_id WHERE p.state = 'claimed' "
        "AND p.run_id IS NOT NULL AND (p.run_id = ? OR r.id IS NULL OR r.status != 'running') ORDER BY p.id",
        (run_id,),
    ).fetchall()
    open_items = [items.Item.from_row(r) for r in rows]
    if not open_items:
        return []
    settled = []
    with db.transaction(conn):
        for found in open_items:
            conn.execute("UPDATE publish_items SET state = 'unknown', finished_at = ? WHERE id = ? AND state = 'claimed'",
                         (timeutil.stamp(), found.id))
            record = items.claimed_request(conn, found)
            shown = record.id if record else found.label
            log.event(conn, "publish.unknown", {"item": found.label, "approval": shown}, level="error",
                      agent=items.AGENT, run_id=run_id)
            settled.append(shown)
        pause.pause(conn, items.AGENT, f"{', '.join(settled)} may or may not have been posted", notify=False)
    return [f"{shown} was claimed, but the run recorded neither done nor stopped, so it may or may not have "
            f"been posted. It won't be tried again, and publish is paused. Check the page, then settle it: "
            f"/growth publish resolve {shown} posted --url <url>, or /growth publish resolve {shown} not-posted."
            for shown in settled]
