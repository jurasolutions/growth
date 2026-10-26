"""Run updates: one Discord message per run of the jobs that ask for one
(MC SC3, §5.5).

The runner calls `after_run` once on every path a run can take except the
PAUSE file: a pause-flag, schedule or precheck skip; a quiet run with nothing
to do; a finished run, after its row, the alert and auto-pause; and the lock
skip, with `conn=None`, so the database is never opened. The runner wraps the
call, so an error here is logged and never changes the run.

A job asks for run updates with `run_update: true` in `config/settings.yaml`,
or with `run_update: claimed-only` for an update only when the plug-in's
`run_update()` gives one (the publish job: only a run that claimed an item,
never a skip, a quiet run or the lock skip). The message goes to the agent
plug-in's `RUN_UPDATE_DISCORD_CHANNEL`, or the channel its optional
`run_update_channel(conn, run)` names for that run:

    **social** · ok · 07:00 SGT · 4m 12s · US$0.41 · run 1287
    > Drafted LinkedIn, Facebook and Instagram for "PayNow QR for small shops".
    Produced: 3 drafts, 3 images
    Waiting for you: A-0153, A-0154, A-0155 (social posts)

- A run that started gives its status, start, length, cost and id, the
  summary as a quote, the plug-in's "Produced:" line and the approval
  requests the run raised. A failed run adds its error in one line.
- A skip gives its reason on the first line. The lock skip has no
  connection, so it carries nothing from the database.
- A quiet run (a precheck's `NothingToDo`, or a quiet job with nothing to
  do) has no run row and reads "nothing to do", with the precheck's reason.
  It is told apart by its path (status ok, no run id), not by its summary.
- A precheck that raises (a typo in an agent's config) is a failed run:
  the runner records its row, alerts, counts it toward auto-pause and posts
  its update. Anything else that raises out of the runner (a database or
  programming error) never reaches this module, so it posts no update, and
  launchd's log keeps the traceback.

The plug-in's `run_update(conn, run) -> list[str] | None` gives the
"Produced:" items for a run with a connection; None posts nothing. If it
raises, the error is logged as `run.after_run_error` and the update posts
without that line.

Model-written text (summaries, and errors, which can quote a summary's
`FAIL:` line) is untrusted: it is masked through `privacy.for_discord()`
first, then cut to `caps.RUN_UPDATE_TEXT_CHARS` and escaped, so it can't
leave the quote, open a code block, make a masked link or ping anyone. A
failed run's quote leaves out the lines its error line already shows. Posts
keep `allowed_mentions` empty and embeds off.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jura_growth import agents, approvals, caps, discord, log, privacy, timeutil

if TYPE_CHECKING:
    from jura_growth.runner import Outcome

LIMIT = caps.RUN_UPDATE_TEXT_CHARS
CLAIMED_ONLY = "claimed-only"
_STATUS_PREFIX = re.compile(r"^\s*[*_`>]*\s*(?:OK|SKIP|FAIL):\s*", re.I)


@dataclass(frozen=True)
class Run:
    """What a plug-in's `run_update()` is told about the run. `id` is None
    for a quiet run and the lock skip, which have no run row."""

    id: int | None
    job: str
    agent: str
    status: str  # ok, failed, skipped
    summary: str
    error: str
    cost_usd: float | None
    started_at: str
    finished_at: str | None


def count(number: int, noun: str) -> str:
    """`3 drafts`, `1 image`: for plug-ins writing their "Produced:" items."""
    return f"{number} {noun if number == 1 else noun + 's'}"


def after_run(conn: sqlite3.Connection | None, job: str, spec: dict, run_id: int | None, outcome: Outcome) -> None:
    """Post the run update for this run, if its job asks for one."""
    mode = spec.get("run_update")
    if mode is not True and mode != CLAIMED_ONLY:
        return
    agent = spec["agent"]
    module = agents.by_name(agent)
    discord_channel = getattr(module, "RUN_UPDATE_DISCORD_CHANNEL", None)
    if not discord_channel:
        raise LookupError(f"job {job} has run_update on, but agent {agent} names no RUN_UPDATE_DISCORD_CHANNEL")
    hook = getattr(module, "run_update", None)
    if mode == CLAIMED_ONLY and (conn is None or run_id is None or hook is None):
        return  # only the plug-in can say a run claimed something, and only for a run with a row
    run = _run(conn, job, agent, run_id, outcome)
    produced: list[str] | None = []  # None: the plug-in couldn't say
    if conn is not None:
        privacy.load_for_masking(conn)  # summaries come from another process
        if hook:
            try:
                produced = hook(conn, run)
            except Exception as error:  # noqa: BLE001 - the update still posts
                log.event(
                    conn,
                    "run.after_run_error",
                    {"job": job, "hook": f"{agent}.run_update", "error": f"{type(error).__name__}: {error}"[:500]},
                    level="error",
                    agent=agent,
                    run_id=run_id,
                )
                produced = None
                if mode == CLAIMED_ONLY:
                    return  # it can't say whether the run claimed anything
            else:
                if produced is None:
                    return  # the plug-in asks for no update for this run
    text = build(run, produced, approvals.raised_by(conn, run_id) if conn is not None and run_id is not None else [])
    discord_channel = _channel_for(conn, module, agent, run) or discord_channel
    discord.post(conn, discord_channel, text, username=f"Jura growth · {job}", dedupe=False, suppress_embeds=True)


def _channel_for(conn: sqlite3.Connection | None, module, agent: str, run: Run) -> str | None:
    """The plug-in's `run_update_channel(conn, run)`, when it has one and names a channel for this
    run (the publish job: `#community` for a group item); otherwise None, and the update goes to
    `RUN_UPDATE_DISCORD_CHANNEL`. An error is logged and falls back the same way."""
    hook = getattr(module, "run_update_channel", None)
    if hook is None or conn is None or run.id is None:
        return None
    try:
        return hook(conn, run)
    except Exception as error:  # noqa: BLE001 - the update still posts, to the default channel
        log.event(conn, "run.after_run_error", {"hook": f"{agent}.run_update_channel",
                                                "error": f"{type(error).__name__}: {error}"[:500]},
                  level="error", agent=agent, run_id=run.id)
        return None


def _run(conn: sqlite3.Connection | None, job: str, agent: str, run_id: int | None, outcome: Outcome) -> Run:
    started, finished = timeutil.stamp(), None
    if conn is not None and run_id is not None:
        row = conn.execute("SELECT started_at, finished_at FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row:
            started, finished = row["started_at"], row["finished_at"]
    return Run(run_id, job, agent, outcome.status, outcome.summary or "", outcome.error or "", outcome.cost_usd, started, finished)


def build(run: Run, produced: list[str] | None, raised: list[approvals.Approval]) -> str:
    """The run update's text."""
    when = f"{timeutil.parse(run.started_at).strftime('%H:%M')} SGT"
    if run.status == "skipped":
        return _header(run, f"skipped: {untrusted_line(run.summary)}", when)
    if run.id is None:
        reason = untrusted_line(run.summary)
        return _header(run, f"nothing to do: {reason}" if reason else "nothing to do", when)

    parts = [run.status, when]
    if run.finished_at:
        parts.append(_duration(run.started_at, run.finished_at))
    if run.cost_usd is not None:
        parts.append(f"US${run.cost_usd:.2f}")
    lines = [_header(run, " · ".join(parts), None)]
    error = run.error if run.status == "failed" else ""
    if error:
        lines.append(f"Error: {untrusted_line(error)}")
    lines += _quote(run.summary, besides=error)
    if produced is not None:
        lines.append(f"Produced: {', '.join(produced) if produced else 'nothing'}")
    if raised:
        lines.append(f"Waiting for you: {_waiting(raised)}")
    return "\n".join(lines)


def _header(run: Run, middle: str, when: str | None) -> str:
    parts = [f"**{run.job}**", middle] + ([when] if when else [])
    if run.id is not None:
        parts.append(f"run {run.id}")
    return " · ".join(parts)


def _duration(started: str, finished: str) -> str:
    seconds = max(0, int((timeutil.parse(finished) - timeutil.parse(started)).total_seconds()))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _waiting(raised: list[approvals.Approval]) -> str:
    """`A-0153, A-0154 (social posts); A-0160 (group rules)`, oldest first."""
    by_kind: dict[str, list[str]] = {}
    for approval in raised:
        by_kind.setdefault(approval.kind, []).append(approval.id)
    return "; ".join(f"{', '.join(ids)} ({_plural(kind)})" for kind, ids in by_kind.items())


def _plural(kind: str) -> str:
    words = kind.replace("-", " ").replace("_", " ")
    return words if words.endswith("s") else words + "s"


# --- untrusted text ----------------------------------------------------------


def _clean(text: str) -> str:
    """Masked first, so a cut never leaves part of a secret behind.

    A finance line's placeholder becomes a plain "[removed]": this text goes
    into a line of the update, and `discord.post()` masks again, which would
    drop that whole line (the header, for a skip) for the placeholder's words."""
    return privacy.for_discord(text or "").replace(privacy.FINANCE, privacy.REMOVED).strip()


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("`", "\\`")
    text = text.replace("](", "]\\(")  # no masked links: [approve here](https://...) stays plain text
    text = re.sub(r"@(everyone|here)", "@​\\1", text)
    return text.replace("<@", "<@​")


def _cut(text: str) -> str:
    text = text[:LIMIT]
    if text.endswith("\\") and (len(text) - len(text.rstrip("\\"))) % 2:
        text = text[:-1]  # never leave half an escape
    return text


def untrusted_line(text: str) -> str:
    """Untrusted text as one line (MC §4.3): masked, on one line, with backslashes, backticks,
    masked links and mentions escaped, and cut to `LIMIT` characters. The one-pager quotes a
    failed run's error through this too (`health.strip`, final review Sp2)."""
    return _cut(_escape(" ".join(_clean(text).split())))


def _quote(summary: str, *, besides: str = "") -> list[str]:
    """The summary as a quote block of at most `LIMIT` characters, without
    the lines that only repeat `besides` (a failed run's error line)."""
    shown = " ".join(_clean(besides).split())
    kept = [line for line in _clean(summary).splitlines() if not shown or " ".join(line.split()) != shown]
    text = _STATUS_PREFIX.sub("", "\n".join(kept).strip(), count=1)
    lines = [line.strip() for line in _escape(text).splitlines() if line.strip()]
    text = _cut("\n".join(lines))
    lines = [line for line in text.splitlines() if line.strip()]
    return ["> " + ("\\" + line if line.startswith(">") else line) for line in lines]  # a > can't start a quote of its own
