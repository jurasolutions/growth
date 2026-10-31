"""Inbox watch's browser half: the jobs that read the social platforms (ADR 0006).

A second plug-in only so it has its own pause flag, run set and auto-pause count:
`jura-growth pause inbox` stops the mail, and `jura-growth pause inbox-browser` stops the browser. It
stays thin. It has no `register`, because a second `inbox` click group would silently replace the
first, so every `inbox` command is registered by the `inbox` plug-in, and no `MIGRATIONS`. It imports
`inbox` at the top: if that is broken, this is too, and closed.

- `scope`: what a watch run may do. It can't click.
- `job`: the hooks. The audit fails a run and pauses this agent; a stop signal pauses `publish` too.

Job `inbox-watch` reads hourly, 09:05 to 21:05 SGT, and `inbox-reply` posts one approved reply a run,
every 20 minutes, 09:10 to 20:50 SGT. The `social-reply` kind is declared here, for this agent's pause flag.
"""

from __future__ import annotations

import sqlite3

from jura_growth.agents import inbox as _inbox  # noqa: F401 - see the docstring

NAME = "inbox-browser"


def permissions(job: str):
    from jura_growth.agents.inbox_browser import scope

    return scope.permissions(job)


def precheck(job: str, conn: sqlite3.Connection):
    from jura_growth.agents.inbox_browser import job as watch_job

    if job == "inbox-reply":
        return watch_job.reply_precheck(conn)
    return watch_job.precheck(conn) if job == "inbox-watch" else None


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """The watch's checks, failing closed: the runner keeps a run's own outcome when this raises, and
    that outcome holds the model's words and has had no audit."""
    if job not in ("inbox-watch", "inbox-reply"):
        return None
    from jura_growth.agents.inbox_browser import job as watch_job

    try:
        hook = watch_job.reply_after_run if job == "inbox-reply" else watch_job.after_run
        return hook(conn, job, run_id, outcome)
    except Exception as error:  # noqa: BLE001 - fail closed, whatever went wrong
        return watch_job.failed_closed(conn, run_id, outcome, error)


def approval_kinds() -> dict:
    from jura_growth.agents.inbox import social

    return social.kinds()


def setup_gaps() -> list:
    """The page addresses in `config/inbox.yaml`. The auth variables are the publish plug-in's check."""
    from jura_growth import health
    from jura_growth.agents.inbox import watch

    return [health.Gap("INBOX_WATCH_PAGES", ok=False)] if watch.page_problems() else []


def health(conn: sqlite3.Connection) -> list[str]:
    """A surface it hasn't been able to read for over 3 of the watch's hours. Reads only."""
    from jura_growth.agents.inbox import watch

    return watch.blind_lines(conn)
