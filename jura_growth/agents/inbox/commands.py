"""`jura-growth inbox ...`. Every `inbox` command is registered here: a second click group with the
same name would silently replace this one (technical review, the attack list)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from jura_growth import approvals_cli, caps, config, db, log, mission, origin, privacy, timeutil
from jura_growth.agents.inbox import one_pager, reply_run, send, steer, store, triage, watch



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


@inbox_group.command("send-due")
def send_due() -> str:
    """Claim each approved reply and send exactly what was approved. Job `inbox-send` runs this."""
    with db.session() as conn:
        summary = send.send_due(conn)
    click.echo(summary or "nothing to send")
    return summary


@inbox_group.command("reply-due")
def reply_due() -> None:
    """What a reply run reads before any claim: the target and whose words. Never the reply, as JSON."""
    with db.session() as conn:
        click.echo(json.dumps(reply_run.hand_out(conn, run_id=log.current_run_id()), ensure_ascii=False, indent=1))


@inbox_group.command("reply-next")
@click.option("--json", "as_json", is_flag=True, help="Always JSON: kept so the command reads as `publish next` does.")
@click.option("--read-file", "read_file", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="What the run found on the target (prompts/inbox-reply.md), by its full path.")
def reply_next(as_json: bool, read_file: Path) -> None:
    """Judge what the run read, and claim at most one reply. Prints the text only if it was claimed."""
    raw = read_file.read_bytes() if read_file.stat().st_size <= caps.INBOX_READ_FILE_BYTES else b""
    with db.session() as conn:
        click.echo(json.dumps(reply_run.next_reply(conn, reply_run.parse_read(raw), run_id=log.current_run_id()), ensure_ascii=False, indent=1))


@inbox_group.command("reply-done")
@click.argument("approval_id", metavar="A-ID")
@click.option("--url", help="The address of the thread or comment you read the reply back from.")
@click.option("--live-text-file", "live_text_file", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="The reply's words as the page shows them, by the file's full path.")
@click.option("--not-sent", "not_sent", is_flag=True, help="Nothing was sent: the page stopped it before the send.")
def reply_done(approval_id: str, url: str | None, live_text_file: Path | None, not_sent: bool) -> None:
    """Record what became of this run's claim."""
    if not_sent == bool(url or live_text_file) or (not not_sent and not (url and live_text_file)):
        raise click.UsageError("a post needs --url and --live-text-file; a reply that didn't go needs --not-sent")
    live = None
    if live_text_file is not None:
        if live_text_file.stat().st_size > caps.INBOX_READ_FILE_BYTES:
            raise click.ClickException("refused: that file is too long to be one reply")
        live = live_text_file.read_text(encoding="utf-8", errors="replace")
    with db.session() as conn:
        recorded, line = reply_run.done(conn, approval_id, url=url, live=live, run_id=log.current_run_id())
    if not recorded:
        raise click.ClickException(line)
    click.echo(line)


@inbox_group.command("list")
def listed() -> None:
    """Replies waiting, as the one-pager shows it (R4), with every open item rather than the first ten."""
    with db.session() as conn:
        privacy.load_for_masking(conn)
        since = mission.last_one_pager(conn, config.settings()["jobs"], timeutil.now_sgt()).isoformat(timespec="seconds")
        click.echo("\n".join(one_pager.lines(conn, since, limit=None)))


def _from_dispatch(ctx: click.Context, what: str, work) -> None:
    """Only Ting Yu steers: a run is refused whatever it declared, and without the origin only `remote`
    puts in the click context, typed in Terminal, it does nothing (ADR 0004)."""
    approvals_cli.refuse_in_a_run(what)
    found = ctx.obj.get("origin") if isinstance(ctx.obj, dict) else None
    if not isinstance(found, origin.Origin) or not found.human:
        click.echo(f"refused: this comes only from Discord: `/growth inbox {ctx.info_name} ...`.")
        ctx.exit(2)
    with db.session() as conn:
        answer = work(conn)
    click.echo(answer.text)
    ctx.exit(answer.exit_code)


@inbox_group.command("reword")
@click.argument("approval_id")
@click.argument("words", nargs=-1, required=True)
@click.pass_context
def reword(ctx: click.Context, approval_id: str, words: tuple[str, ...]) -> None:
    """His exact words become A-nnnn's draft, after the brand check. A word `//` is a paragraph break."""
    _from_dispatch(ctx, "change a draft", lambda conn: steer.reword(conn, approval_id, words))


@inbox_group.command("redraft")
@click.argument("approval_id")
@click.argument("words", nargs=-1, required=True)
@click.pass_context
def redraft(ctx: click.Context, approval_id: str, words: tuple[str, ...]) -> None:
    """The next triage redrafts A-nnnn with his guidance. The card stays open until the new one is up."""
    _from_dispatch(ctx, "change a draft", lambda conn: steer.redraft(conn, approval_id, words))


@inbox_group.command("draft")
@click.argument("label")
@click.argument("words", nargs=-1)
@click.pass_context
def draft(ctx: click.Context, label: str, words: tuple[str, ...]) -> None:
    """Ask triage for a draft on I-nnnn, where the model said no reply was needed."""
    _from_dispatch(ctx, "ask for a draft", lambda conn: steer.draft(conn, label, words))


@inbox_group.command("done")
@click.argument("label")
@click.pass_context
def done(ctx: click.Context, label: str) -> None:
    """Clear I-nnnn's conversation from Replies waiting: a hand reply he has given, or a lapsed line."""
    _from_dispatch(ctx, "clear an inbox item", lambda conn: steer.done(conn, label))


@inbox_group.command("unsuppress")
@click.argument("label")
@click.pass_context
def unsuppress(ctx: click.Context, label: str) -> None:
    """Lift a suppression that came from I-nnnn's reply, and restore its lead. Nothing else is lifted."""
    _from_dispatch(ctx, "lift a suppression", lambda conn: steer.unsuppress(conn, label))
