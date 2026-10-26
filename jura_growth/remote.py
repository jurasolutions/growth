"""`jura-growth remote`: control commands from Discord, through Dispatch (MC SC10, §4.7, §5.10; ADR 0004).

Dispatch reaches the growth Mac one way only: SSH with a forced command, over
Tailscale. The forced command is `bin/growth-remote`, which splits
`SSH_ORIGINAL_COMMAND` into words without a shell and runs

    jura-growth remote [--actor discord:<id>] [--ref <ref>] [--json] -- <command…>

This module then:

1. refuses whenever a scheduled run's `JURA_GROWTH_JOB` is set (and
   `headless.NEVER` has already refused it before it starts);
2. checks the origin: `origin.detect_ssh()`, which needs the forced command's
   variable, a root `sshd` ancestor and no Claude Code ancestor or marker.
   Tests pass an origin in process as `ctx.obj["origin"]`; nothing outside a
   Python process can;
3. checks the actor against `CONTROL_DISCORD_USER_ID`. That is attribution and
   a consistency check: the guard is the SSH key and Dispatch's allowlist;
4. matches the words against `ALLOWLIST` and builds the real command's
   arguments from them. Free words (a note, a reason) go after `--`, so none
   of them is ever read as an option;
5. runs that command in process, with the origin and actor in the click
   context, where `approve` and `skip` find them (ticket 04b);
6. answers with at most `TEXT_LIMIT` characters of text masked for Discord
   (`privacy.for_discord`), and an exit code. With `--json`, a versioned
   object (`docs/dispatch-contract.md`);
7. writes one `remote.command` event with the actor, the words, the ref and
   the answer, never the command's output.

Anything not on the allowlist exits 2 with a line starting "refused:".
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from dataclasses import dataclass
from typing import Callable

import click

from jura_growth import approvals, approvals_cli, config, db, log, origin, pause, privacy

CONTRACT = 1
TEXT_LIMIT = 1900  # Dispatch adds its own words; Discord takes 2,000
JSON_LIMIT = 64 * 1024
OK, FAILED, REFUSED = 0, 1, 2  # the exit codes of commands that aren't decisions
ANSWER_FOR_EXIT = {code: answer for answer, code in approvals_cli.EXIT_CODES.items()}
_DISCORD_ACTOR = re.compile(r"discord:\d+")


class Refusal(Exception):
    """The words aren't a control command; the text says why."""


@dataclass(frozen=True)
class Entry:
    """One control command: how Ting Yu types it, and how it becomes the real
    command's arguments. `decision` commands answer from the closed enum."""

    usage: str
    argv: Callable[[list[str], str | None], list[str]]
    decision: bool = False


# --- the builders: the words after the command's name -> the real command's arguments ----------


def _none(name: str) -> Callable[[list[str], str | None], list[str]]:
    def build(words: list[str], ref: str | None) -> list[str]:
        if words:
            raise Refusal(f"`{name}` takes nothing after it")
        return name.split()

    return build


def _positional(name: str, low: int, high: int) -> Callable[[list[str], str | None], list[str]]:
    def build(words: list[str], ref: str | None) -> list[str]:
        if not low <= len(words) <= high:
            raise Refusal(f"`{name}` takes {_count(low, high)}")
        return [*name.split(), "--", *words]

    return build


def _count(low: int, high: int) -> str:
    if low == high:
        return f"{low} word{'s' if low != 1 else ''} after it"
    return f"{low} to {high} words after it"


def _decision(name: str) -> Callable[[list[str], str | None], list[str]]:
    def build(words: list[str], ref: str | None) -> list[str]:
        if not words:
            raise Refusal(f"say which request: `{name} A-nnnn`")
        return [name, *(["--ref", ref] if ref else []), "--", *words]

    return build


def _pause(words: list[str], ref: str | None) -> list[str]:
    if not words:
        raise Refusal("say which agent, or all: `pause <agent|all> [reason]`")
    reason = " ".join(words[1:]) or "paused from Discord"
    return ["pause", f"--reason={reason}", "--", words[0]]


def _requeue_shadow(words: list[str], ref: str | None) -> list[str]:
    argv = ["outreach", "requeue-shadow"]
    rest = list(words)
    while rest:
        word = rest.pop(0)
        if word == "--dry-run":
            argv.append(word)
        elif word == "--since" and rest:
            argv.append(f"--since={rest.pop(0)}")
        elif word.startswith("--since="):
            argv.append(word)
        else:
            raise Refusal("`outreach requeue-shadow` takes only --since YYYY-MM-DD and --dry-run")
    return argv


# Sorted by command, one entry per line, so tickets 09, 12 and browser-publishing#03 each add
# their rows in a hunk of their own. `docs/dispatch-contract.md` lists them in the same order.
ALLOWLIST: dict[str, Entry] = {
    "approvals": Entry("approvals [kind]", _positional("approvals", 0, 1)),
    "approve": Entry("approve <A-nnnn> [key=value …] [note]", _decision("approve"), decision=True),
    "community removed": Entry("community removed <group-id>", _positional("community removed", 1, 1)),
    "outreach requeue-shadow": Entry("outreach requeue-shadow [--since YYYY-MM-DD] [--dry-run]", _requeue_shadow),
    "pause": Entry("pause <agent|all> [reason]", _pause),
    "resume": Entry("resume <agent|all>", _positional("resume", 1, 1)),
    "skip": Entry("skip <A-nnnn> [note]", _decision("skip"), decision=True),
    "social skip": Entry("social skip <date> <platform>", _positional("social skip", 2, 2)),
    "status": Entry("status", _none("status")),
}


def match(words: list[str]) -> tuple[str, Entry, list[str]]:
    """The allowlisted command the words name, its entry and the words after
    it. Two-word commands first. Raises `Refusal` for anything else."""
    for size in (2, 1):
        name = " ".join(words[:size])
        if len(words) >= size and name in ALLOWLIST:
            return name, ALLOWLIST[name], list(words[size:])
    typed = " ".join(words[:2]) or "nothing"
    raise Refusal(f"`{_short(typed)}` isn't a control command. Send one of: {', '.join(ALLOWLIST)}")


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- the answer ---------------------------------------------------------------------------------


@dataclass
class Reply:
    exit_code: int
    answer: str
    text: str
    approvals: list[dict] | None = None
    origin: str | None = None  # the origin's kind, once it was checked

    @property
    def ok(self) -> bool:
        return self.exit_code == OK


def _answer_for(entry: Entry | None, code: int) -> str:
    if entry is not None and entry.decision and code in ANSWER_FOR_EXIT:
        return ANSWER_FOR_EXIT[code]
    return approvals.RECORDED if code == OK else approvals.REFUSED


def _defuse(text: str) -> str:
    """No mention in the answer can ping anyone, whatever Dispatch does."""
    text = re.sub(r"@(everyone|here)", "@​\\1", text)
    return text.replace("<@", "<@​")


def _cut(text: str, limit: int = TEXT_LIMIT) -> str:
    """At most `limit` characters: cut at a line where that keeps at least
    half, then a note of what was left out."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[: limit - 40]
    at = head.rfind("\n")
    head = head[:at] if at >= len(head) // 2 else head.rstrip() + " …"
    left = len(text.splitlines()) - len(head.splitlines())
    return head + "\n" + (f"(cut: {left} more line{'s' if left != 1 else ''})" if left > 0 else "(cut)")


def _usage_refusal(text: str) -> str:
    """A click usage error, as one "refused:" line."""
    errors = [line.strip()[len("Error: "):] for line in text.splitlines() if line.strip().startswith("Error: ")]
    return f"refused: {errors[-1] if errors else 'the command was not understood'}"


# --- running the command ---------------------------------------------------------------------------


def _run(ctx: click.Context, argv: list[str], obj: dict) -> tuple[int, str]:
    """The real command, in this process, with its output captured."""
    root = ctx.find_root().command
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            root.main(args=argv, prog_name="jura-growth", standalone_mode=True, obj=obj)
            code = OK
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else (OK if stop.code is None else FAILED)
            if isinstance(stop.code, str):
                buffer.write(stop.code)
        except Exception as error:  # noqa: BLE001 - the answer says it failed, masked like the rest
            buffer.write(f"failed: {type(error).__name__}: {error}")
            code = FAILED
    return code, buffer.getvalue()


def _attribution(actor: str | None) -> str | None:
    """Why the actor can't send control commands, or None."""
    if not actor or not _DISCORD_ACTOR.fullmatch(actor):
        return "a control command needs --actor discord:<id>"
    control = config.secret("CONTROL_DISCORD_USER_ID")
    if not control:
        return "CONTROL_DISCORD_USER_ID isn't set, so the sender can't be checked"
    if actor != f"discord:{control}":
        return f"{actor} isn't the control user"
    return None


def handle(ctx: click.Context, words: list[str], *, actor: str | None, ref: str | None) -> Reply:
    """Everything but printing and the event."""
    obj = ctx.obj if isinstance(ctx.obj, dict) else {}
    job = log.current_job()
    if job:
        return Reply(REFUSED, approvals.REFUSED, f"refused: a `{job}` run can't send control commands.")
    found = obj["origin"] if "origin" in obj else origin.detect_ssh()
    if not isinstance(found, origin.Origin) or not found.human:
        why = getattr(found, "reason", None) or origin.NOT_DISPATCH
        return Reply(REFUSED, approvals.REFUSED, f"refused: {why}.", origin=origin.NOT_HUMAN)
    problem = _attribution(actor)
    if problem:
        return Reply(REFUSED, approvals.REFUSED, f"refused: {problem}.", origin=found.kind)
    try:
        name, entry, rest = match(words)
        argv = entry.argv(rest, ref)
    except Refusal as refusal:
        return Reply(REFUSED, approvals.REFUSED, f"refused: {refusal}.", origin=found.kind)
    code, text = _run(ctx, argv, {"origin": found, "actor": actor})
    if code == REFUSED and not text.lstrip().startswith("refused:"):
        text = _usage_refusal(text)
    if not entry.decision and code not in (OK, REFUSED):
        code = FAILED
    if entry.decision and code not in ANSWER_FOR_EXIT:
        code = FAILED
    reply = Reply(code, _answer_for(entry, code), text, origin=found.kind)
    if name == "resume" and pause.pause_file_active():
        reply.text = reply.text.rstrip() + "\nThe PAUSE file can only be removed on the Mac; until then it pauses everything."
    if name == "approvals" and code == OK:
        reply.approvals = _listed(rest[0] if rest else None)
    return reply


def _listed(kind: str | None) -> list[dict]:
    with db.session() as conn:
        return approvals_cli.listed(conn, kind)


# --- the command -------------------------------------------------------------------------------------


def _masked(reply: Reply) -> Reply:
    """The text and the listing as they may reach Discord."""
    try:
        with db.session() as conn:
            privacy.load_for_masking(conn)
    except Exception:  # noqa: BLE001 - masking still runs on what is known; secrets go first
        pass
    reply.text = _cut(_defuse(privacy.for_discord(reply.text)))
    if reply.approvals is not None:
        reply.approvals = [
            {k: _defuse(privacy.for_discord(v)) if isinstance(v, str) else v for k, v in item.items()}
            for item in reply.approvals
        ]
    return reply


def payload(reply: Reply) -> str:
    """The `--json` answer: `{contract, ok, answer, exit_code, text, approvals?}`, at most
    `JSON_LIMIT` bytes. Listed requests are dropped from the end to fit."""
    body: dict = {"contract": CONTRACT, "ok": reply.ok, "answer": reply.answer, "exit_code": reply.exit_code,
                  "text": reply.text}
    if reply.approvals is not None:
        body["approvals"] = list(reply.approvals)
    encoded = json.dumps(body, ensure_ascii=False)
    while len(encoded.encode("utf-8")) > JSON_LIMIT and body.get("approvals"):
        body["approvals"].pop()
        encoded = json.dumps(body, ensure_ascii=False)
    return encoded


def _record(words: list[str], actor: str | None, ref: str | None, reply: Reply) -> None:
    """One `remote.command` event: who, what, and the answer. Never the output."""
    try:
        with db.session() as conn:
            log.event(conn, "remote.command", {"actor": actor, "words": list(words), "ref": ref, "origin": reply.origin,
                                               "answer": reply.answer, "exit_code": reply.exit_code},
                      level="info" if reply.exit_code == OK else "warning")
    except Exception:  # noqa: BLE001 - the answer still goes back; the mirror line may be all there is
        pass


def register(cli: click.Group) -> None:
    @cli.command("remote", context_settings={"allow_interspersed_args": False, "ignore_unknown_options": True})
    @click.option("--actor", help="Who sent it: discord:<id> (attribution).")
    @click.option("--ref", help="Dispatch's delivery reference: <message id>:<delivery id>.")
    @click.option("--json", "as_json", is_flag=True, help="Answer as JSON (docs/dispatch-contract.md).")
    @click.argument("words", nargs=-1, type=click.UNPROCESSED)
    @click.pass_context
    def remote_command(ctx, actor, ref, as_json, words) -> None:
        """A control command from Discord, through Dispatch's SSH forced command only."""
        words = list(words)
        reply = _masked(handle(ctx, words, actor=actor, ref=ref))
        _record(words, actor, ref, reply)
        click.echo(payload(reply) if as_json else reply.text)
        ctx.exit(reply.exit_code)
