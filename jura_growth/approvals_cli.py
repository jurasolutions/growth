"""`jura-growth approvals`, `approve` and `skip` (MC §4.6 A8 to A10, §5.10; ticket 04b).

Ting Yu lists, approves and skips requests from a real terminal by typing
the request's six-character code. No agent process can:

1. `headless.NEVER` holds all three, so a scheduled run is refused before
   the command starts, and Claude Code's rules for every claude job deny them.
2. Each command refuses on its own whenever `JURA_GROWTH_JOB` is set.
3. `approve` and `skip` take their origin from `origin.detect()` (a TTY, no
   `claude` ancestor, the typed code), unless the in-process click context
   carries one (`ctx.obj["origin"]`), which only ticket 11's `remote`
   dispatcher sets. There is no flag and no environment variable for it.

Every decision answers one of `approvals.ANSWERS`, each with its own exit
code (`EXIT_CODES`); ticket 11's `docs/dispatch-contract.md` lists them.

    jura-growth approvals [kind]
    jura-growth approve A-0412 [key=value ...] [note ...] [--ref <ref>]
    jura-growth skip A-0412 [note ...] [--ref <ref>]
"""

from __future__ import annotations

import os
import re
import sys

import click

from jura_growth import approvals, cards, db, headless, log, origin, timeutil

EXIT_CODES = {
    approvals.RECORDED: 0,
    approvals.REFUSED: 2,
    approvals.EXPIRED: 3,
    approvals.SUPERSEDED: 4,
    approvals.ALREADY_DECIDED: 5,
    approvals.ALREADY_USED: 6,
    approvals.UNKNOWN_ID: 7,
}
LIST_LIMIT = 15
_ARG = re.compile(r"[a-z][a-z_]*=.*")


def refuse_in_a_run(what: str) -> None:
    """Layer 2: refused whenever a scheduled run's label is set, whatever
    `NEVER` and the job's permissions say."""
    job = os.environ.get("JURA_GROWTH_JOB")
    if job:
        raise headless.Refused(f"refused: a `{job}` run can't {what}; only Ting Yu can, from Terminal or Dispatch")


def split_words(words: tuple[str, ...]) -> tuple[dict[str, str], str]:
    """Leading `key=value` words are the decision's arguments; the rest is
    a note."""
    args: dict[str, str] = {}
    rest: list[str] = []
    for word in words:
        if not rest and _ARG.fullmatch(word):
            key, _, value = word.partition("=")
            args[key] = value
        else:
            rest.append(word)
    return args, " ".join(rest)


def _origin(ctx: click.Context, shown: str) -> tuple[origin.Origin, str | None]:
    obj = ctx.obj if isinstance(ctx.obj, dict) else {}
    if "origin" in obj:  # set only by `remote` (ticket 11), in process
        return obj["origin"], obj.get("actor")
    return origin.detect(f"Type {shown}'s code (on its card, or in `jura-growth approvals`): "), None


def _decide(ctx: click.Context, approval_id: str, decision: str, words: tuple[str, ...], ref: str | None) -> None:
    refuse_in_a_run("decide an approval request")
    if decision == "approve":
        args, note = split_words(words)
    else:
        args, note = {}, " ".join(words)
    number = approvals.parse_id(approval_id)
    shown = approvals.format_id(number) if number is not None else approval_id
    found, actor = _origin(ctx, shown)
    with db.session() as conn:
        answer = approvals.decide(conn, approval_id, decision, actor=actor, origin=found, source_ref=ref, args=args)
        if answer.answer == approvals.RECORDED and note and answer.approval is not None:
            log.event(conn, "approval.note", {"approval": answer.approval.id, "decision": decision, "note": note,
                                              "actor": answer.approval.decided_by})
        try:
            approvals.post_unposted(conn)
        except Exception as error:  # noqa: BLE001 - the decision stands; the next sweep edits the card
            print(f"warning: the card was not edited: {type(error).__name__}: {error}", file=sys.stderr)
    click.echo(answer.text)
    ctx.exit(EXIT_CODES[answer.answer])


def _listing(conn, kind: str | None) -> list[str]:
    now = timeutil.now_sgt()
    waiting = [a for a in approvals.pending(conn) if kind is None or a.kind == kind]
    # A plain read: a request past its decide-by is no longer offered, though
    # its lapse is written later (A17), and content is judged on decision.
    lapsed = [a for a in waiting if timeutil.parse(a.decide_by) <= now]
    live = [a for a in waiting if timeutil.parse(a.decide_by) > now]
    if not waiting:
        return [f"No {cards.label(kind)} requests are waiting." if kind else "No requests are waiting."]
    registry = approvals.kinds()
    lines = []
    for approval in live[:LIST_LIMIT]:
        registered = registry.get(approval.kind)
        try:
            title = registered.kind.preview(conn, approval.subject).title if registered else "(its plug-in isn't loaded)"
        except Exception as error:  # noqa: BLE001
            title = f"(no preview: {type(error).__name__})"
        lines.append(f"{approval.id} · {cards.label(approval.kind)} · decide by {cards.when(approval.decide_by)} · "
                     f"code {approval.code} · {title}")
    hidden = live[LIST_LIMIT:]
    if hidden:
        by_kind: dict[str, int] = {}
        for approval in hidden:
            by_kind[approval.kind] = by_kind.get(approval.kind, 0) + 1
        if kind is not None:
            lines.append(f"and {len(hidden)} more: decide these first, then /growth approvals {kind} again")
        elif len(by_kind) == 1:
            lines.append(f"and {len(hidden)} more: /growth approvals {next(iter(by_kind))}")
        else:
            listed = ", ".join(f"/growth approvals {name} ({count})" for name, count in sorted(by_kind.items()))
            lines.append(f"and {len(hidden)} more: {listed}")
    if lapsed:
        many = len(lapsed) != 1
        lines.append(f"{len(lapsed)} more passed {'their' if many else 'its'} decide-by and expire{'' if many else 's'} unanswered.")
    return lines


def register(cli: click.Group) -> None:
    @cli.command("approvals")
    @click.argument("kind", required=False)
    def approvals_command(kind) -> None:
        """Pending approval requests, the 15 soonest to lapse first."""
        refuse_in_a_run("list approval requests")
        with db.session() as conn:
            click.echo("\n".join(_listing(conn, kind)))

    @cli.command("approve")
    @click.argument("approval_id")
    @click.argument("words", nargs=-1)
    @click.option("--ref", help="Dispatch's delivery reference; the same one twice answers once.")
    @click.pass_context
    def approve_command(ctx, approval_id, words, ref) -> None:
        """Approve A-nnnn, typing its code. Then any key=value arguments, then a note."""
        _decide(ctx, approval_id, "approve", words, ref)

    @cli.command("skip")
    @click.argument("approval_id")
    @click.argument("words", nargs=-1)
    @click.option("--ref", help="Dispatch's delivery reference; the same one twice answers once.")
    @click.pass_context
    def skip_command(ctx, approval_id, words, ref) -> None:
        """Skip A-nnnn, typing its code. Allowed until it is used. Then a note."""
        _decide(ctx, approval_id, "skip", words, ref)
