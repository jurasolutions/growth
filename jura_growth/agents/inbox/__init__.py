"""Inbox watch: every reaction to Jura reported, every reply approved
(prd/pending/prd-jura-inbox-watch-2026-10-31.md).

This agent sees mail, triages it, reports it, and sends the replies Ting Yu approves:

- `store`: the record of every reaction, and `store.record`, the one way in.
- `mail`: the mail intake. Read-only IMAP, the noise filter, a lead's reply recorded as the 16:45
  check would, website enquiries, Jura's own mail dropped.
- `triage`: what the model may do, and everything that holds whatever it does.
- `checks`: the brand channels for a reply, `inbox-email` and `inbox-social`.
- `report`: one message per conversation in #mission-control, retried until delivered.
- `kinds`: the `email-reply` approval kind: what a reply is, its card, and what each answer does.
- `send`: `inbox send-due`, which claims an approved reply and sends exactly that.
- `steer`: `redraft`, `reword`, `draft`, `done` and `unsuppress`, which come only from Discord through `remote`.
- `signals`: reactions with no person writing: app usage and spam complaints.
- `text_retention`: what "closes" means for each state, and removing a person's words 90 days after.
- `one_pager`: R4's section, Replies waiting, which `/growth inbox list` shows on request, the lines
  `/growth pending` lists and the morning picture's count.
- `watch`: what a watch run may record, and what its records come to. The jobs that drive the browser
  belong to the `inbox_browser` plug-in, which has its own pause flag. Its commands are here, because
  a second `inbox` click group would silently replace this one.
- `job`: the job's precheck.
- `commands`: `jura-growth inbox status | pending | submit | send-due`, a watch run's `watch-targets`,
  `observe` and `stopped`, and Ting Yu's `list`, `reword`, `redraft`, `draft`, `done` and `unsuppress`.
- `settings`: the limits in `caps.py`, tightened by `config/inbox.yaml`.

Job `inbox-check` runs every 15 minutes, 07:00 to 23:45 SGT. Its precheck reads the mail and reports
what needs no model. Claude starts only when something waits for triage (`prompts/inbox-check.md`).
Job `inbox-send` runs every 10 minutes, 08:00 to 22:00 SGT, with no model.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

NAME = "inbox"
MIGRATIONS = Path(__file__).parent / "migrations"
# Claude Code runs these unasked (its permissions page, "read-only commands"), and a Read rule doesn't
# stop `grep -r`. Triage's Bash only ever runs `jura-growth`, so it can do without every one of them.
_READ_COMMANDS = ("cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "find", "ls", "tree", "wc", "which", "diff", "stat", "du",
                  "cd", "git", "sed", "awk", "sort", "uniq", "cut", "tr", "strings", "xxd", "od", "file", "less", "more", "env",
                  "printenv", "ps", "pwd", "echo", "python", "python3", "sqlite3", "curl", "wget")
# Under `data/growth/`. Not a blanket `**`: a deny would hit triage's own scratch folder.
_NOT_FOR_TRIAGE = ("growth.db*", "transcripts/**", "backups/**", "discord-outbox/**", "runs/**", "launchd/**", "one-pager/**",
                   "work/publish/**", "work/inbox-watch/**", "work/inbox-reply/**")


def register(cli) -> None:
    from jura_growth.agents.inbox.commands import inbox_group

    cli.add_command(inbox_group)


def approval_kinds() -> dict:
    from jura_growth.agents.inbox import kinds

    return kinds.kinds()


def channels() -> dict:
    from jura_growth.agents.inbox import checks

    return checks.channels()


def precheck(job: str, conn: sqlite3.Connection):
    if job != "inbox-check":
        return None
    from jura_growth.agents.inbox import job as inbox_job

    return inbox_job.precheck(conn)


def permissions(job: str):
    """Triage's two commands, and the rules around what it could read (technical review, B4; code
    review 02, SEC-1). The runner starts it in an empty folder, adds only its scratch folder, and
    fences its file tools to those two. These are the second layer: its Bash needs none of the
    commands that read, and the data it must not see is named. None of this is proved on a double:
    `reviews/uat.md` has the canary row for the real model. With `--strict-mcp-config` and no
    `--chrome` it has no MCP tools to deny."""
    if job != "inbox-check":
        return None
    from jura_growth import headless, paths

    denied = [f"Read(/{paths.data_dir()}/{place})" for place in _NOT_FOR_TRIAGE]
    return headless.Permissions(
        commands=("inbox pending", "inbox submit"),
        disallowed_tools=("WebSearch", "WebFetch", *denied, f"Read(/{paths.outputs_dir()}/**)",
                          *(f"Bash({command}:*)" for command in _READ_COMMANDS)),
    )


def after_run(conn: sqlite3.Connection, job: str, run_id: int | None, outcome):
    """Triage's last word, failing closed: the runner keeps a run's own outcome when this raises, and
    that outcome holds the model's words. So any exception here ends in a fixed outcome of ours."""
    if job != "inbox-check":
        return None
    from jura_growth.agents.inbox import triage

    try:
        return triage.after_run(conn, run_id, outcome)
    except Exception as error:  # noqa: BLE001 - see the docstring
        return triage.failed_closed(conn, run_id, outcome, error)


def setup_gaps() -> list:
    from jura_growth import health
    from jura_growth.agents.inbox import mail

    return [health.Gap(name, ok=False) for name in mail.setup_gaps()]


def health(conn: sqlite3.Connection) -> list[str]:
    """Reports waiting on Discord, and a mailbox that can't be read. Reads only."""
    from jura_growth.agents.inbox import store

    try:
        waiting = store.open_counts(conn)["unreported"]
        lines = [f"Inbox: {problem}" for _, problem in store.with_prefix(conn, store.PROBLEM)]
    except sqlite3.OperationalError:  # not migrated yet: nothing has been read
        return []
    if waiting:
        lines.append(f"Inbox: {waiting} reaction{'s' if waiting != 1 else ''} not yet reported in #mission-control")
    return lines


def retention(conn: sqlite3.Connection) -> dict:
    """PRD §4, from the nightly backup, which keeps running when `inbox` is paused."""
    from jura_growth.agents.inbox import text_retention

    return text_retention.prune(conn)


def one_pager_section(conn: sqlite3.Connection, since: str):
    """R4, on the read model's read-only connection: reads only, and calls no kind's `content()`."""
    from jura_growth.agents.inbox import one_pager

    return one_pager.section(conn, since)


def pending(conn: sqlite3.Connection) -> list:
    """`jura-growth pending`: reads only, and calls no kind's `content()` (`one_pager.pending_items`)."""
    from jura_growth.agents.inbox import one_pager

    return one_pager.pending_items(conn)


def digest(conn: sqlite3.Connection, day: str) -> dict:
    """R5: counts only, never a name, an address or a word anyone wrote. `inbox_to_answer` is the morning
    picture's count of what only he can move."""
    from jura_growth.agents.inbox import one_pager, store

    counts = {**store.day_counts(conn, day), **store.open_counts(conn), "to_answer": one_pager.to_answer(conn)}
    if not any(counts.values()):
        return {"figures": {}, "lines": [], "brief": []}
    reactions = counts["reactions"]
    parts = [f"{reactions} reaction{'s' if reactions != 1 else ''}", f"{counts['noise']} filtered as noise"]
    if counts["waiting"]:
        parts.append(f"{counts['waiting']} waiting on you")
    if counts["hand_replies"]:
        parts.append(f"{counts['hand_replies']} needing a hand reply")
    if counts["unreported"]:
        parts.append(f"{counts['unreported']} not yet reported")
    return {
        "figures": {f"inbox_{name}": number for name, number in counts.items()},
        "lines": ["Inbox: " + ", ".join(parts)],
        "brief": [f"{reactions} reaction{'s' if reactions != 1 else ''}"] if reactions else [],
    }
