"""`jura-growth inbox ...`. Every `inbox` command is registered here: a second click group with the
same name would silently replace this one (technical review, the attack list)."""

from __future__ import annotations

import click

from jura_growth import db, timeutil
from jura_growth.agents.inbox import store


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
