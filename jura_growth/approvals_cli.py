"""`jura-growth approvals`, `approve` and `skip` (MC §4.6 A8 to A10 as amended
2026-10-26, §5.10; ADR 0004).

Decisions come only from #approvals, through Dispatch over SSH. Typed in
Terminal, `approve` and `skip` refuse and point there, and nothing is
recorded: a process started from an interactive Claude session could pass any
terminal check (ADR 0004). A Touch ID ticket may bring Terminal decisions back.

`approve` and `skip` decide only when the in-process click context carries an
origin (`ctx.obj["origin"]` and the Discord `actor`), which only ticket 11's
`remote` dispatcher sets, after `origin.detect_ssh()`. There is no flag and no
environment variable for it. Every decision answers one of
`approvals.ANSWERS`, each with its own exit code (`EXIT_CODES`); ticket 11's
`docs/dispatch-contract.md` lists them.

No scheduled run may use any of the three: `headless.NEVER` refuses them
before they start, and each refuses again on its own whenever a run's
`JURA_GROWTH_JOB` is set.

`approvals [kind]` is a plain read: the pending requests, the 15 soonest to
lapse first.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

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
    """Refused whenever a scheduled run's label is set, whatever `NEVER` and
    the job's permissions say."""
    job = log.current_job()
    if job:
        raise headless.Refused(f"refused: a `{job}` run can't {what}; only Ting Yu can, in #approvals")


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


def _decide(ctx: click.Context, approval_id: str, decision: str, words: tuple[str, ...], ref: str | None) -> None:
    refuse_in_a_run("decide an approval request")
    obj = ctx.obj if isinstance(ctx.obj, dict) else {}
    if "origin" not in obj:  # only `remote` (ticket 11) puts one there, in process
        click.echo(f"refused: {origin.TERMINAL_OFF}.")
        ctx.exit(EXIT_CODES[approvals.REFUSED])
    if decision == "approve":
        args, note = split_words(words)
    else:
        args, note = {}, " ".join(words)
    with db.session() as conn:
        answer = approvals.decide(conn, approval_id, decision, actor=obj.get("actor"), origin=obj["origin"],
                                  source_ref=ref, args=args)
        if answer.answer == approvals.RECORDED and note and answer.approval is not None:
            log.event(conn, "approval.note", {"approval": answer.approval.id, "decision": decision, "note": note,
                                              "actor": answer.approval.decided_by})
        cards.sweep_safely(conn)
    click.echo(answer.text)
    ctx.exit(EXIT_CODES[answer.answer])


def _title(conn, approval, registered) -> str:
    if registered is None:
        return "(its plug-in isn't loaded)"
    try:
        return registered.kind.preview(conn, approval.subject).title
    except Exception as error:  # noqa: BLE001
        return f"(no preview: {type(error).__name__})"


def waiting(conn, kind: str | None) -> tuple[list[tuple[approvals.Approval, datetime]], int]:
    """The one selection both listings show: pending requests (of `kind`)
    still in time, soonest to lapse first (decide-by, then id), each with its
    decide-by; and how many more are pending but past it. A plain read: their
    lapse is written later (A17), and content is judged on decision."""
    now = timeutil.now_sgt()
    pending = [(a, timeutil.parse(a.decide_by)) for a in approvals.pending(conn) if kind is None or a.kind == kind]
    live = sorted(((a, due) for a, due in pending if due > now), key=lambda pair: (pair[1], pair[0].number))
    return live, len(pending) - len(live)


def listed(conn, kind: str | None) -> list[dict]:
    """The requests `approvals [kind]` shows, as data for `remote --json`,
    each with the `key=value` arguments an approve must carry (no buttons
    for those)."""
    registry = approvals.kinds()
    found = []
    for approval, _ in waiting(conn, kind)[0][:LIST_LIMIT]:
        registered = registry.get(approval.kind)
        found.append({"id": approval.id, "kind": approval.kind, "decide_by": approval.decide_by,
                      "title": _title(conn, approval, registered),
                      "args": list(getattr(registered.kind, "decision_args", None) or ()) if registered else []})
    return found


def _listing(conn, kind: str | None) -> list[str]:
    live, lapsed = waiting(conn, kind)
    if not live and not lapsed:
        return [f"No {cards.label(kind)} requests are waiting." if kind else "No requests are waiting."]
    registry = approvals.kinds()
    lines = []
    for approval, due in live[:LIST_LIMIT]:
        title = _title(conn, approval, registry.get(approval.kind))
        lines.append(f"{approval.id} · {cards.label(approval.kind)} · decide by {cards.when_at(due)} · {title}")
    if lapsed:
        lines.append(f"{lapsed} more passed {'their' if lapsed != 1 else 'its'} decide-by and "
                     f"expire{'' if lapsed != 1 else 's'} unanswered.")
    hidden = Counter(approval.kind for approval, _ in live[LIST_LIMIT:])
    total = sum(hidden.values())
    if total:
        if kind is not None:
            lines.append(f"and {total} more: decide these first, then /growth approvals {kind} again")
        elif len(hidden) == 1:
            lines.append(f"and {total} more: /growth approvals {next(iter(hidden))}")
        else:
            listed = ", ".join(f"/growth approvals {name} ({count})" for name, count in sorted(hidden.items()))
            lines.append(f"and {total} more: {listed}")
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
        """Approve A-nnnn from #approvals (through Dispatch). Refused in Terminal."""
        _decide(ctx, approval_id, "approve", words, ref)

    @cli.command("skip")
    @click.argument("approval_id")
    @click.argument("words", nargs=-1)
    @click.option("--ref", help="Dispatch's delivery reference; the same one twice answers once.")
    @click.pass_context
    def skip_command(ctx, approval_id, words, ref) -> None:
        """Skip A-nnnn from #approvals (through Dispatch). Refused in Terminal."""
        _decide(ctx, approval_id, "skip", words, ref)
