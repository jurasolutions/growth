"""`jura-growth inbox ...`. Every `inbox` command is registered here: a second click group with the
same name would silently replace this one (technical review, the attack list)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from jura_growth import caps, db, log, timeutil
from jura_growth.agents.inbox import store, triage, watch



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
        for line in watch.status_lines(conn):
            click.echo(line)


@inbox_group.command("watch-targets")
def watch_targets() -> None:
    """What a watch run reads now: the pages, the surfaces and the posts, as JSON."""
    with db.session() as conn:
        click.echo(json.dumps(watch.targets(conn), ensure_ascii=False, indent=1))


@inbox_group.command("observe")
@click.option("--file", "observations_file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="A JSON list of what the run read (prompts/inbox-watch.md).")
def observe(observations_file: Path) -> None:
    """Record what a watch run read. Prints counts, and a fixed reason for anything refused: nothing
    from the file comes back, since it holds hostile text."""
    run_id = log.current_run_id()
    if run_id is None:
        raise click.ClickException("refused: only a watch run records what it read")
    if observations_file.stat().st_size > watch.OBSERVE_FILE_BYTES:
        raise click.ClickException(f"refused: the file is over {watch.OBSERVE_FILE_BYTES} bytes, so split it")
    try:
        observations = watch.parse_file(observations_file.read_bytes())
    except ValueError as error:
        raise click.ClickException(f"refused: {error}") from None
    with db.session() as conn:
        click.echo(json.dumps(watch.observe(conn, run_id, observations).as_dict()))


@inbox_group.command("stopped")
@click.option("--reason", required=True, type=click.Choice(sorted(watch.STOP_REASONS)))
def stopped(reason: str) -> None:
    """A stop signal: pauses the watch and publishing, since they share the accounts, and alerts once."""
    with db.session() as conn:
        watch.stop(conn, log.current_run_id(), reason)
    click.echo(f"stopped ({reason}): inbox-browser and publish are paused")


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
