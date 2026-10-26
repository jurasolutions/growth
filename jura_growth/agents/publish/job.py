"""The publish job's hooks (browser publishing PRD §5.8).

- `precheck` (before Claude starts) raises when the fixture platform is set but refused (BP-07),
  so the run fails before anything is read. Then it runs `items.sync()` in a committed transaction and posts the
  cards that raised (`cards.sweep_safely()`), so a changed post gets its new card whether or not
  anything is due (code review 02, B1). Then an auth variable that would hide the Chrome tools is
  a plain skip Ting Yu should see (AC-P9.5), and nothing claimable (`claim.claimable()`,
  read-only) is `NothingToDo("nothing due")`, a quiet run with no Claude (AC-P8.2).
- `setup_gaps`: the same auth variables, by name, for `jura-growth status`.
- `after_run`: see its docstring.
- `run_update`: "Produced:" for a run that claimed an item, and no update for any other run
  (`run_update: claimed-only`).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from jura_growth import agents, cards, db, discord, log, pause, timeutil, transcripts
from jura_growth.agents.publish import audit, claim, commands, fixture, items, scope

# With either set, Claude Code keeps Chrome integration off, even with --chrome (spike §1).
AUTH_VARIABLES = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
# How a run that failed before claiming anything ended, in words of our own: the runner's own
# failures by their prefix, and anything else (the model's `FAIL:` line) as one closed phrase.
ENDINGS = (
    ("timed out", "timed out"),
    ("no result from claude", "ended with no result from Claude Code"),
    ("claude ", "ended with a Claude Code error"),
)
MODEL_FAILED = "ended FAIL:"


def precheck(job: str, conn: sqlite3.Connection):
    """A skip reason, `NothingToDo`, or None to start the run. A fixture platform its guard
    refuses (`fixture.py`, BP-07) raises before anything is read, so the run fails and alerts."""
    fixture.active()
    with db.transaction(conn):
        items.sync(conn)
    cards.sweep_safely(conn)
    for name in AUTH_VARIABLES:
        if os.environ.get(name):
            return (f"{name} is set, so Claude Code would start without the Chrome tools; remove it from the "
                    f"environment scheduled runs get (the publish job needs the claude.ai login)")
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
    2. Audit the run's transcript (`audit.py`), and hash each claimed item's image copies again
       against its approval (code review 03, S-8): any failure fails the run and pauses `publish`.
    3. A run that found no browser and claimed nothing alerts once a day (AC-P9.4).
    4. Replace the summary and the error with words of our own (code review 03, B1): the A-id,
       the platform, what happened, the URL or the closed stop reason, and the run id. The
       model's summary, its `FAIL:` line and anything it quoted from a page never reach the run
       row, #alerts or the run update; the run's transcript keeps them for 7 days.
    5. A run whose only failure is a stop is marked as already alerted: `publish stopped` posted
       the stop's one alert (code review 03, S-4)."""
    if run_id is None:
        return None
    from jura_growth import runner

    unknown = _settle_unknown(conn, run_id)
    claimed = _claimed_by(conn, run_id)
    found = _audit(run_id, claimed)
    failures = found.failures + _copy_problems(conn, claimed)
    if failures:
        with db.transaction(conn):
            log.event(conn, "publish.audit_failed", {"failures": failures}, level="error", agent=items.AGENT,
                      run_id=run_id)
            pause.pause(conn, items.AGENT, f"the audit of run {run_id} failed", notify=False)
    if found.no_browser and not claimed:
        _no_browser(conn, run_id)

    lines = [_line(conn, item) for item in claimed] + [f"Warning: {w}" for w in found.warnings]
    if claimed:
        summary = "\n".join(lines)
    else:
        summary = "nothing claimed" + ("; no browser was connected" if found.no_browser else "")
    model_failed = outcome.status == "failed"
    errors = list(unknown)
    if failures:
        errors.append(f"The audit of run {run_id} failed: {'; '.join(failures)}. Publishing is paused for every "
                      f"item until you resume it: {commands.RESUME}.")
    stops = [item for item in claimed if item.state == "stopped"]
    if model_failed and not errors:
        errors = [_failure(conn, item, run_id) for item in claimed] or [_ending(outcome.error, run_id)]
    status = "failed" if errors else outcome.status
    return runner.Outcome(status, summary=summary, error=" ".join(errors), cost_usd=outcome.cost_usd,
                          alerted=bool(stops) and not unknown and not failures)


def run_update(conn: sqlite3.Connection, run) -> list[str] | None:
    """"Produced:" for a run that claimed an item (`1 post`, `1 stopped`); None posts no update
    (`run_update: claimed-only`)."""
    claimed = _claimed_by(conn, run.id) if run.id is not None else []
    if not claimed:
        return None
    from jura_growth.run_update import count

    words = {"posted": 0, "stopped": 0, "unknown": 0}
    for item in claimed:
        if item.state == "done":
            words["posted"] += 1
        elif item.state in words:
            words[item.state] += 1
    return [count(n, "post") if word == "posted" else f"{n} {word}" for word, n in words.items() if n]


def _claimed_by(conn: sqlite3.Connection, run_id: int) -> list[items.Item]:
    rows = conn.execute("SELECT * FROM publish_items WHERE run_id = ? AND claimed_at IS NOT NULL ORDER BY id",
                        (run_id,)).fetchall()
    return [items.Item.from_row(r) for r in rows]


def _shown(conn: sqlite3.Connection, item: items.Item) -> str:
    record = items.claimed_request(conn, item)
    return record.id if record else item.label


def _line(conn: sqlite3.Connection, item: items.Item) -> str:
    """`A-0001 · Facebook Page · posted · <url>`, from the item's own record."""
    from jura_growth.agents.social.settings import load

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
    return f"{_shown(conn, item)} · {where} · {what}"


def _failure(conn: sqlite3.Connection, item: items.Item, run_id: int) -> str:
    """Why a run that claimed `item` failed, in a closed form: its stop reason, or that the run
    ended `FAIL:` after the item was recorded."""
    shown = _shown(conn, item)
    if item.state == "stopped":
        reason = item.stop_reason or "unidentified"
        return f"{shown} stopped in run {run_id}: {reason} ({commands.STOP_REASONS.get(reason, 'a stop signal')})."
    return (f"Run {run_id} {MODEL_FAILED} after {shown} was recorded as {item.state}; its words are withheld "
            f"(run {run_id}'s transcript keeps them).")


def _ending(error: str, run_id: int) -> str:
    phrase = next((words for prefix, words in ENDINGS if (error or "").startswith(prefix)), MODEL_FAILED)
    return f"Run {run_id} {phrase} before claiming anything; its words are withheld (run {run_id}'s transcript keeps them)."


def _audit(run_id: int, claimed: list[items.Item]) -> audit.Audit:
    path = transcripts.find(run_id)
    if path is None:
        return audit.Audit()
    approved = [text for item in claimed for text in _approved_texts(item)]
    images = [str(copy) for item in claimed for copy in item.content.get("copies", [])]
    # Only the claimed item's own platform: an item posted on another enabled platform fails (B1).
    # While the fixture platform is on, only the fixture site (BP-07).
    own = tuple(dict.fromkeys(item.platform for item in claimed)) or None
    return audit.audit(transcripts.read(path), hosts=scope.browser_hosts(own), approved=approved, images=images,
                       site=fixture.active())


def _approved_texts(item: items.Item) -> list[str]:
    """What a run may type for `item`: the post's text, or each approved membership answer."""
    content = item.content
    texts = [content["text"]] if content.get("text") else []
    return texts + [str(pair.get("answer", "")) for pair in content.get("answers") or [] if isinstance(pair, dict)]


def _copy_problems(conn: sqlite3.Connection, claimed: list[items.Item]) -> list[str]:
    """Each claimed item's image copies must still be there and hold exactly the approved bytes:
    a missing copy is one the audit can't clear (code review 03, N1)."""
    problems = []
    for item in claimed:
        images = item.content.get("images") or []
        for number, (copy, image) in enumerate(zip(item.content.get("copies") or [], images), start=1):
            path = Path(copy)
            if not path.is_file():
                problems.append(f"image copy {number} of {_shown(conn, item)} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != image.get("sha256"):
                problems.append(f"image copy {number} of {_shown(conn, item)} no longer holds the approved image")
    return problems


def failed_closed(conn: sqlite3.Connection, run_id: int | None, outcome, error: Exception):
    """The outcome when the checks themselves broke (`publish.after_run`, B3): failed, with a
    fixed reason naming the run and the error's type only, and publishing paused. Logging and
    the pause are tried, and neither can stop the failed outcome from standing."""
    from jura_growth import runner

    name = type(error).__name__
    for step in (
        lambda: log.event(conn, "publish.checks_failed", {"error": name}, level="error", agent=items.AGENT, run_id=run_id),
        lambda: pause.pause(conn, items.AGENT, f"the checks after run {run_id} couldn't run", notify=False),
    ):
        try:
            step()
        except Exception:  # noqa: BLE001 - the failed outcome stands whatever happens here
            pass
    return runner.Outcome(
        "failed",
        summary=f"the checks after run {run_id} couldn't run",
        error=(f"The checks after run {run_id} couldn't run ({name}), so the run is treated as failed. Publishing "
               f"is paused for every item until you resume it: {commands.RESUME}."),
        cost_usd=getattr(outcome, "cost_usd", None),
    )


def _no_browser(conn: sqlite3.Connection, run_id: int) -> None:
    """Log it, and alert only on the first such run of the day (AC-P9.4). `discord.alert` posts
    every time it is called, and the text is the same each slot, so the once-a-day rule is kept
    here, from the day's `publish.no_browser` events, rather than by Discord's dedupe."""
    today = timeutil.today_str()
    earlier = db.scalar(conn, "SELECT count(*) FROM events WHERE kind = 'publish.no_browser' AND ts LIKE ?", (f"{today}%",))
    log.event(conn, "publish.no_browser", {"run": run_id}, level="warning", agent=items.AGENT, run_id=run_id)
    if earlier:
        return
    discord.alert(conn, f"No browser was connected when the publish job ran (run {run_id}), so nothing was posted. "
                        "Approved items stay approved until their deadline. On the Mac, open Chrome with the Claude "
                        "extension signed in to the same account as Claude Code. This is the only alert about it "
                        "today.", agent=items.AGENT)


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
            shown = _shown(conn, found)
            log.event(conn, "publish.unknown", {"item": found.label, "approval": shown}, level="error",
                      agent=items.AGENT, run_id=run_id)
            settled.append(shown)
        pause.pause(conn, items.AGENT, f"{', '.join(settled)} may or may not have been posted", notify=False)
    return [f"{shown} was claimed in run {run_id}, but the run recorded neither done nor stopped, so it may or may "
            f"not have been posted. It won't be tried again, and publish is paused. Check the page, then settle it: "
            f"/growth publish resolve {shown} posted --url <url>, or /growth publish resolve {shown} not-posted."
            for shown in settled]
