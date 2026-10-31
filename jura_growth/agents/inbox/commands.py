"""`jura-growth inbox ...`. Every `inbox` command is registered here: a second click group with the
same name would silently replace this one (technical review, the attack list)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from jura_growth import caps, db, timeutil
from jura_growth.agents.inbox import send, store, triage


@click.group("inbox")
def inbox_group() -> None:
    """The inbox watch: every reaction reported."""


@inbox_group.command("status")
def status() -> None:
    """Counts, and each mailbox's last good check. Never a name, an address or anyone's words."""
    with db.session() as conn:
        day = timeutil.today_str()
        counts = {**store.day_counts(conn, day), **store.open_counts(conn)}
        click.echo(
            f"today: {counts['reactions']} reactions, {counts['noise']} noise; "
            f"open: {counts['hand_replies']} needing a hand reply, {counts['unreported']} not yet reported"
        )
        checks = store.with_prefix(conn, store.LAST_SUCCESS)
        for label, stamp in checks:
            click.echo(f"{label} mailbox: last good check {stamp}")
        if not checks:
            click.echo("no good mail check yet")


@inbox_group.command("pending")
@click.option("--json", "as_json", is_flag=True, help="What triage reads: every waiting conversation and the grounds for a draft.")
def pending(as_json: bool) -> None:
    """What waits for triage. With --json, hands it out, which counts an attempt inside a run."""
    with db.session() as conn:
        if as_json:
            click.echo(json.dumps(triage.hand_out(conn), ensure_ascii=False, indent=1))
            return
        waiting = store.waiting_for_triage(conn)
        click.echo(f"{len(waiting)} message{'s' if len(waiting) != 1 else ''} waiting for triage")


@inbox_group.command("submit")
@click.option("--file", "file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="One JSON object: id, class, priority, language, draft. In a run, in its scratch folder.")
def submit(file: Path) -> str:
    """Hand in one conversation's class and draft. A person's words never go on a command line."""
    raw = file.read_bytes()
    try:
        payload = None if len(raw) > caps.INBOX_SUBMIT_BYTES else json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        payload = None
    with db.session() as conn:
        outcome = triage.submit(conn, payload)
    click.echo(outcome.text())
    if outcome.exit_code:
        sys.exit(outcome.exit_code)
    return outcome.lines[0]


@inbox_group.command("send-due")
def send_due() -> str:
    """Claim each approved reply and send exactly what was approved. Job `inbox-send` runs this."""
    with db.session() as conn:
        summary = send.send_due(conn)
    click.echo(summary or "nothing to send")
    return summary
