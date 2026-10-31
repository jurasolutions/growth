"""The publish job's hooks (browser publishing PRD §5.8).

- `precheck` (before Claude starts) raises when the fixture platform is set but refused (BP-07),
  so the run fails before anything is read. Then it runs `items.sync()` in a committed transaction and posts the
  cards that raised (`cards.sweep_safely()`), so a changed post gets its new card whether or not
  anything is due (code review 02, B1). Then a claim an earlier run left open settles as
  `unknown`, pauses `publish` and alerts (`settle_orphans`, final review Sp1), and the run is
  skipped as paused. Then an auth variable that would hide the Chrome tools is
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
from jura_growth.agents.publish import audit, claim, commands, fixture, items, outcomes, scope

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
    if settle_orphans(conn, None):  # the runner holds the publish lock and no run has claimed yet
        return pause.is_paused(conn, items.AGENT)
    problem = auth_problem("the publish job needs the claude.ai login")
    if problem:
        return problem
    if not claim.claimable(conn):
        return agents.NothingToDo(claim.NOTHING_DUE)
    return None


def auth_problem(needs: str) -> str | None:
    """Why a browser job can't start: a variable that would hide the Chrome tools (AC-P9.5)."""
    for name in AUTH_VARIABLES:
        if os.environ.get(name):
            return (f"{name} is set, so Claude Code would start without the Chrome tools; remove it from the "
                    f"environment scheduled runs get ({needs})")
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
       A join the run recorded is set back; a community post it recorded as posted is kept (it may
       be live) and named, in the error and on its summary line, as a record to check.
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
    undone: list[int] = []
    if failures:
        from jura_growth.agents.community import groups as groups_mod

        with db.transaction(conn):
            log.event(conn, "publish.audit_failed", {"failures": failures}, level="error", agent=items.AGENT,
                      run_id=run_id)
            pause.pause(conn, items.AGENT, f"the audit of run {run_id} failed", notify=False)
            undone = groups_mod.undo_joins(conn, run_id)
    if found.no_browser and not claimed:
        _no_browser(conn, run_id)

    # A post recorded by a run whose audit failed stays posted (it may be live, and `planned`
    # would invite a repost), but it is named as a record to check (code review 05, S1).
    doubted = [item for item in claimed if failures and _posted_in_group(item)]
    lines = [_line(conn, item) + (" · the audit failed" if item in doubted else "") for item in claimed]
    lines += [f"Warning: {w}" for w in found.warnings]
    if claimed:
        summary = "\n".join(lines)
    else:
        summary = "nothing claimed" + ("; no browser was connected" if found.no_browser else "")
    model_failed = outcome.status == "failed"
    errors = list(unknown)
    if failures:
        errors.append(f"The audit of run {run_id} failed: {'; '.join(failures)}. Publishing is paused for every "
                      f"item until you resume it: {commands.RESUME}.")
        if undone:
            named = ", ".join(f"group {group_id}" for group_id in undone)
            errors.append(f"What the run recorded for the join of {named} was set back: check the group by hand.")
        errors += [f"{_shown(conn, item)}'s posted record for group {outcomes.group_of(item)} may be wrong: check the "
                   f"group, and the Page's own timeline." for item in doubted]
    stops = [item for item in claimed if item.state == "stopped"]
    if model_failed and not errors:
        errors = [_failure(conn, item, run_id) for item in claimed] or [ending(outcome.error, run_id, " before claiming anything")]
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

    nouns = {"posted": "post", **{outcome: words.noun for outcome, words in outcomes.WORDS.items()}}
    tally = {**{word: 0 for word in nouns}, "stopped": 0, "unknown": 0}
    for item in claimed:
        if item.state == "done":
            tally[item.outcome if item.outcome in outcomes.WORDS else "posted"] += 1
        elif item.state in tally:
            tally[item.state] += 1
    return [count(n, nouns[word]) if word in nouns else f"{n} {word}" for word, n in tally.items() if n]


def run_update_channel(conn: sqlite3.Connection, run) -> str | None:
    """The item's channel (BP §5.9): `#community` when the run claimed a group item."""
    claimed = _claimed_by(conn, run.id) if run.id is not None else []
    return "community" if any(item.kind in outcomes.GROUP_KINDS for item in claimed) else None


def _claimed_by(conn: sqlite3.Connection, run_id: int) -> list[items.Item]:
    rows = conn.execute("SELECT * FROM publish_items WHERE run_id = ? AND claimed_at IS NOT NULL ORDER BY id",
                        (run_id,)).fetchall()
    return [items.Item.from_row(r) for r in rows]


def _posted_in_group(item: items.Item) -> bool:
    """A community post this run recorded as posted."""
    return item.kind == items.COMMUNITY_POST_ITEM and item.state == "done" and item.outcome == "posted"


def _shown(conn: sqlite3.Connection, item: items.Item) -> str:
    record = items.claimed_request(conn, item)
    return record.id if record else item.label


def _line(conn: sqlite3.Connection, item: items.Item) -> str:
    """`A-0001 · Facebook Page · posted · <url>`, from the item's own record. A community item
    names its group by the register's id, never by text a page or a run wrote."""
    from jura_growth.agents.social.settings import load

    try:
        where = load().platforms[item.platform].label
    except Exception:  # noqa: BLE001 - the label is only for reading
        where = item.platform
    if item.kind in outcomes.GROUP_KINDS:
        where = f"Facebook group {outcomes.group_of(item)}"
    if item.state == "done" and item.outcome in outcomes.WORDS:
        what = outcomes.WORDS[item.outcome].line
        if item.outcome == outcomes.QUESTIONS:
            answers = outcomes.answers_request(conn, item)
            what += f"; the answers wait for your decision as {answers.id}" if answers else "; no answers were raised"
    elif item.state == "done":
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


def ending(error: str, run_id: int, when: str = "") -> str:
    """How a run ended, in closed words: the model's own are withheld."""
    phrase = next((words for prefix, words in ENDINGS if (error or "").startswith(prefix)), MODEL_FAILED)
    return f"Run {run_id} {phrase}{when}; its words are withheld (run {run_id}'s transcript keeps them)."


def _audit(run_id: int, claimed: list[items.Item]) -> audit.Audit:
    path = transcripts.find(run_id)
    if path is None:
        return audit.Audit()
    approved = [text for item in claimed for text in _approved_texts(item)]
    images = [str(copy) for item in claimed for copy in item.content.get("copies", [])]
    # Only the claimed item's own platform: an item posted on another enabled platform fails (B1).
    # While the fixture platform is on, only the fixture site (BP-07).
    own = tuple(dict.fromkeys(item.platform for item in claimed)) or None
    # A group item is held to its own group's address as well (code review 06, B1).
    places = [item.target_url for item in claimed if item.kind in outcomes.GROUP_KINDS]
    return audit.audit(transcripts.read(path), hosts=scope.browser_hosts(own), approved=approved, images=images,
                       site=fixture.active(), places=places)


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
    """The outcome when the checks themselves broke (`publish.after_run`, B3)."""
    return checks_failed(conn, run_id, outcome, error, agent=items.AGENT, event="publish.checks_failed",
                         paused=f"Publishing is paused for every item until you resume it: {commands.RESUME}.")


def checks_failed(conn: sqlite3.Connection, run_id: int | None, outcome, error: Exception, *, agent: str, event: str, paused: str):
    """A browser run nobody could check: failed, with a fixed reason naming the run and the error's
    type only, and its agent paused. Logging and the pause are tried, and neither can stop the failed
    outcome from standing."""
    from jura_growth import runner

    name = type(error).__name__
    for step in (
        lambda: log.event(conn, event, {"error": name}, level="error", agent=agent, run_id=run_id),
        lambda: pause.pause(conn, agent, f"the checks after run {run_id} couldn't run", notify=False),
    ):
        try:
            step()
        except Exception:  # noqa: BLE001 - the failed outcome stands whatever happens here
            pass
    return runner.Outcome(
        "failed",
        summary=f"the checks after run {run_id} couldn't run",
        error=f"The checks after run {run_id} couldn't run ({name}), so the run is treated as failed. {paused}",
        cost_usd=getattr(outcome, "cost_usd", None),
    )


def _no_browser(conn: sqlite3.Connection, run_id: int) -> None:
    """Log it, and alert only on the first such run of the day (AC-P9.4). `discord.alert` posts
    every time it is called, and the text is the same each slot, so the once-a-day rule is kept
    here, from the day's `publish.no_browser` events, rather than by Discord's dedupe."""
    no_browser_once(conn, run_id, items.AGENT, "publish.no_browser",
                    f"No browser was connected when the publish job ran (run {run_id}), so nothing was posted. "
                    "Approved items stay approved until their deadline.")


def no_browser_once(conn: sqlite3.Connection, run_id: int, agent: str, event: str, opening: str) -> None:
    """Log a run that found no browser, and alert only on the first of the day."""
    today = timeutil.today_str()
    earlier = db.scalar(conn, "SELECT count(*) FROM events WHERE kind = ? AND ts LIKE ?", (event, f"{today}%"))
    log.event(conn, event, {"run": run_id}, level="warning", agent=agent, run_id=run_id)
    if earlier:
        return
    discord.alert(conn, f"{opening} On the Mac, open Chrome with the Claude extension signed in to the same account as "
                        "Claude Code. This is the only alert about it today.", agent=agent)


def settle_orphans(conn: sqlite3.Connection, run_id: int | None) -> list[str]:
    """Settle the claims an earlier publish run left open, and alert (AC-P10.1, final review Sp1).

    A run that was killed (a hard sleep, a reboot) never reaches its `after_run`, so its row can
    still say `running` when the next slot starts. Only call this while holding the publish job's
    lock: the precheck (`run_id` None, nothing claimed yet) or `publish next` inside a run. Then no
    live sibling run can hold a claim, so every `claimed` item with a run other than `run_id` is
    an orphan, whatever its run's row says. A Terminal claim (no run) is left to Ting Yu. Each
    orphan settles as `unknown` and `publish` pauses, as `_settle_unknown` does; the lines are
    alerted here, because no later `after_run` sees them. Returns those lines."""
    rows = conn.execute(
        "SELECT * FROM publish_items WHERE state = 'claimed' AND run_id IS NOT NULL AND run_id IS NOT ? ORDER BY id",
        (run_id,),
    ).fetchall()
    lines = _settle(conn, run_id, rows)
    if lines:
        discord.alert(conn, " ".join(lines), agent=items.AGENT)
    return lines


def _settle_unknown(conn: sqlite3.Connection, run_id: int) -> list[str]:
    """Mark open claims `unknown`, pause `publish`, and return the #alerts lines that say how to
    settle each."""
    rows = conn.execute(
        "SELECT p.* FROM publish_items p LEFT JOIN runs r ON r.id = p.run_id WHERE p.state = 'claimed' "
        "AND p.run_id IS NOT NULL AND (p.run_id = ? OR r.id IS NULL OR r.status != 'running') ORDER BY p.id",
        (run_id,),
    ).fetchall()
    return _settle(conn, run_id, rows)


def _settle(conn: sqlite3.Connection, run_id: int | None, rows: list) -> list[str]:
    """Mark these claimed rows `unknown`, pause `publish`, and return one #alerts line for each,
    naming the run that claimed it and both `publish resolve` forms."""
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
            settled.append((shown, found.run_id))
        pause.pause(conn, items.AGENT, f"{', '.join(s for s, _ in settled)} may or may not have been posted",
                    notify=False)
    return [f"{shown} was claimed in run {claimed_in}, but the run recorded neither done nor stopped, so it may or "
            f"may not have been posted. It won't be tried again, and publish is paused. Check the page, then settle "
            f"it: /growth publish resolve {shown} posted --url <url>, or /growth publish resolve {shown} not-posted."
            for shown, claimed_in in settled]
